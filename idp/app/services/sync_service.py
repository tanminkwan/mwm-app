"""동기화 비즈니스 로직. SOLID-OCP: 전략 패턴으로 Role 동기화 확장 가능."""
import logging
from abc import ABC, abstractmethod

from flask import current_app
from sqlalchemy import create_engine, text
from app.models import db

logger = logging.getLogger(__name__)


# ── Role 동기화 전략 (SOLID-OCP, LSP) ──

class RoleSyncStrategy(ABC):
    """Role 동기화 전략 인터페이스"""

    @abstractmethod
    def get_roles(self, engine, config, user_id):
        """외부 DB에서 특정 사용자의 역할 목록을 반환"""
        pass


class JoinRoleSyncStrategy(RoleSyncStrategy):
    """JOIN 방식으로 역할 조회 (ab_user_role → ab_role)"""

    def get_roles(self, engine, config, user_id):
        rs = config["role_source"]
        sql = text(
            f"SELECT r.{rs['role_name_column']} "
            f"FROM {rs['join_table']} ur "
            f"JOIN {rs['role_table']} r ON ur.{rs['join_role_column']} = r.{rs['role_id_column']} "
            f"WHERE ur.{rs['join_user_column']} = :user_id"
        )
        with engine.connect() as conn:
            rows = conn.execute(sql, {"user_id": user_id}).fetchall()
        return [row[0] for row in rows]


class ColumnRoleSyncStrategy(RoleSyncStrategy):
    """단일 컬럼 값을 역할로 변환"""

    def get_roles(self, engine, config, user_id):
        rs = config["role_source"]
        column = rs.get("column_name", "role")
        table = config["table"]
        id_col = config["id_column"]

        sql = text(f"SELECT {column} FROM {table} WHERE {id_col} = :user_id")
        with engine.connect() as conn:
            row = conn.execute(sql, {"user_id": user_id}).fetchone()
        if row and row[0]:
            return [r.strip() for r in str(row[0]).split(",")]
        return []


class StaticRoleSyncStrategy(RoleSyncStrategy):
    """모든 동기화 사용자에 고정 역할 부여"""

    def get_roles(self, engine, config, user_id):
        return config["role_source"].get("roles", [])


# ── 전략 팩토리 ──

ROLE_STRATEGY_MAP = {
    "join": JoinRoleSyncStrategy,
    "column": ColumnRoleSyncStrategy,
    "static": StaticRoleSyncStrategy,
}


def get_role_strategy(strategy_type):
    """SOLID-OCP: 새 전략 추가 시 ROLE_STRATEGY_MAP에 등록만 하면 됨"""
    cls = ROLE_STRATEGY_MAP.get(strategy_type)
    if not cls:
        raise ValueError(f"Unknown role sync strategy: {strategy_type}")
    return cls()


# ── 동기화 서비스 ──

class SyncService:
    """범용 외부 DB 동기화 서비스. Repository를 주입받아 사용 (SOLID-DIP)."""

    def __init__(self, user_repo):
        self.user_repo = user_repo

    def get_sync_sources(self):
        return current_app.config.get("SYNC_SOURCES", {})

    def sync_users(self, source_name):
        """지정된 소스의 외부 DB에서 사용자를 동기화"""
        sources = self.get_sync_sources()
        if source_name not in sources:
            raise ValueError(f"Unknown sync source: {source_name}")

        config = sources[source_name]
        result = {"created": 0, "updated": 0, "deactivated": 0, "errors": []}

        try:
            engine = create_engine(config["db_uri"])
        except Exception as e:
            raise ConnectionError(f"Failed to connect to source DB: {e}")

        # 외부 사용자 조회
        col_mapping = config["column_mapping"]
        source_columns = list(col_mapping.values())
        id_column = config["id_column"]

        select_cols = ", ".join([id_column] + source_columns)
        sql = f"SELECT {select_cols} FROM {config['table']}"
        if config.get("filter"):
            sql += f" WHERE {config['filter']}"

        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql)).fetchall()
                columns = [id_column] + source_columns
        except Exception as e:
            raise ConnectionError(f"Failed to query source: {e}")

        # Role 전략 결정
        role_strategy = None
        if config.get("role_source"):
            strategy_type = config["role_source"].get("type", "static")
            role_strategy = get_role_strategy(strategy_type)

        # Upsert
        synced_ids = set()
        for row in rows:
            row_dict = dict(zip(columns, row))
            sync_id = str(row_dict[id_column])
            synced_ids.add(sync_id)

            try:
                # 컬럼 매핑 변환
                mapped = {}
                for idp_col, src_col in col_mapping.items():
                    if idp_col == "password_hash" and not config.get("sync_password"):
                        continue
                    mapped[idp_col] = row_dict.get(src_col)

                # Role 동기화
                if role_strategy:
                    mapped["roles"] = role_strategy.get_roles(
                        engine, config, row_dict[id_column]
                    )

                # 기존 레코드 확인
                existing = self.user_repo.get_by_sync(source_name, sync_id)

                if existing:
                    # username 충돌 체크 (다른 소스 또는 직접 생성 사용자)
                    username = mapped.get("username", existing.username)
                    dup = self.user_repo.get_by_username(username)
                    if dup and dup.id != existing.id:
                        result["errors"].append(
                            f"Username conflict: {username} (sync_id={sync_id})"
                        )
                        continue

                    self.user_repo.update(existing, **mapped)
                    result["updated"] += 1
                else:
                    # 신규 생성 시 중복 체크 (Race condition 방지를 위해 try-except 사용)
                    username = mapped.get("username")
                    email = mapped.get("email")
                    
                    try:
                        # Nested transaction (savepoint) 사용: 충돌 시 이 사용자에 대한 작업만 롤백
                        with db.session.begin_nested():
                            if username and self.user_repo.get_by_username(username):
                                raise ValueError(f"Username conflict: {username}")
                            if email and self.user_repo.get_by_email(email):
                                raise ValueError(f"Email conflict: {email}")

                            mapped["sync_source"] = source_name
                            mapped["sync_id"] = sync_id
                            self.user_repo.create(**mapped)
                            result["created"] += 1
                    except Exception as e:
                        # 이미 다른 워커가 생성했다면 update로 전환 시도
                        db.session.rollback() # Nested transaction만 롤백
                        existing = self.user_repo.get_by_sync(source_name, sync_id)
                        if existing:
                            self.user_repo.update(existing, **mapped)
                            result["updated"] += 1
                        else:
                            result["errors"].append(f"sync_id={sync_id}: {str(e)}")
                            continue

            except Exception as e:
                result["errors"].append(f"sync_id={sync_id}: {str(e)}")
                logger.error(f"Sync error for {source_name}/{sync_id}: {e}")

        # 외부에서 삭제된 사용자 비활성화
        existing_synced = self.user_repo.get_synced_users(source_name)
        for user in existing_synced:
            if user.sync_id not in synced_ids and user.active:
                self.user_repo.update(user, active=False)
                result["deactivated"] += 1

        self.user_repo.commit()
        logger.info(
            f"Sync '{source_name}' complete: "
            f"created={result['created']}, updated={result['updated']}, "
            f"deactivated={result['deactivated']}, errors={len(result['errors'])}"
        )
        return result
