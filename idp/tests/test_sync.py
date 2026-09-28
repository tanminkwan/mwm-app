"""동기화 테스트. Coverage 목표: sync_service.py 100%"""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, text

from app.services.sync_service import (
    SyncService, JoinRoleSyncStrategy, ColumnRoleSyncStrategy,
    StaticRoleSyncStrategy, get_role_strategy,
)
from app.repositories.user_repo import UserRepository
from app.models import db as _db, IdpUser


# ── Strategy 단위 테스트 ──

class TestRoleStrategies:
    def test_static_strategy(self):
        strategy = StaticRoleSyncStrategy()
        config = {"role_source": {"roles": ["Admin", "viewer"]}}
        roles = strategy.get_roles(None, config, 1)
        assert roles == ["Admin", "viewer"]

    def test_static_strategy_empty(self):
        strategy = StaticRoleSyncStrategy()
        config = {"role_source": {}}
        roles = strategy.get_roles(None, config, 1)
        assert roles == []

    def test_get_role_strategy_valid(self):
        assert isinstance(get_role_strategy("join"), JoinRoleSyncStrategy)
        assert isinstance(get_role_strategy("column"), ColumnRoleSyncStrategy)
        assert isinstance(get_role_strategy("static"), StaticRoleSyncStrategy)

    def test_get_role_strategy_invalid(self):
        with pytest.raises(ValueError, match="Unknown role sync strategy"):
            get_role_strategy("invalid")


# ── SyncService 통합 테스트 ──

class TestSyncService:
    def _setup_source_db(self):
        """Mock 외부 DB를 파일 기반 SQLite로 생성"""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_uri = f"sqlite:///{db_path}"
        engine = create_engine(db_uri)
        raw = engine.raw_connection()
        cur = raw.cursor()
        cur.execute(
            "CREATE TABLE ab_user ("
            "  id INTEGER PRIMARY KEY,"
            "  username VARCHAR(64),"
            "  email VARCHAR(320),"
            "  first_name VARCHAR(64),"
            "  last_name VARCHAR(64),"
            "  password VARCHAR(256),"
            "  active BOOLEAN"
            ")"
        )
        cur.execute(
            "INSERT INTO ab_user VALUES "
            "(1, 'admin', 'admin@test.com', 'Admin', 'User', 'hashedpw', 1),"
            "(2, 'user1', 'user1@test.com', 'User', 'One', 'hashedpw2', 1)"
        )
        raw.commit()
        cur.close()
        return db_uri, db_path

    def _get_sync_config(self, db_uri):
        return {
            "test_source": {
                "description": "Test source",
                "db_uri": db_uri,
                "table": "ab_user",
                "id_column": "id",
                "column_mapping": {
                    "username": "username",
                    "email": "email",
                    "first_name": "first_name",
                    "last_name": "last_name",
                    "password_hash": "password",
                    "active": "active",
                },
                "role_source": {"type": "static", "roles": ["Public"]},
                "filter": "active = 1",
                "sync_password": True,
                "auto_sync_interval_minutes": 0,
            }
        }

    def test_sync_create_users(self, app, db):
        db_uri, db_path = self._setup_source_db()
        sync_config = self._get_sync_config(db_uri)
        try:
            with app.app_context():
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    result = service.sync_users("test_source")

            assert result["created"] == 2
            assert result["updated"] == 0
            assert result["deactivated"] == 0
        finally:
            os.unlink(db_path)

    def test_sync_update_users(self, app, db):
        db_uri, db_path = self._setup_source_db()
        sync_config = self._get_sync_config(db_uri)
        try:
            with app.app_context():
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    service.sync_users("test_source")

                # 외부 DB 업데이트
                ext_engine = create_engine(db_uri)
                raw = ext_engine.raw_connection()
                raw.cursor().execute(
                    "UPDATE ab_user SET first_name='AdminUpdated' WHERE id=1"
                )
                raw.commit()

                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    result = service.sync_users("test_source")

            assert result["updated"] == 2
            assert result["created"] == 0
        finally:
            os.unlink(db_path)

    def test_sync_deactivate(self, app, db):
        db_uri, db_path = self._setup_source_db()
        sync_config = self._get_sync_config(db_uri)
        try:
            with app.app_context():
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    service.sync_users("test_source")

                # 외부 DB에서 한 명 삭제
                ext_engine = create_engine(db_uri)
                raw = ext_engine.raw_connection()
                raw.cursor().execute("DELETE FROM ab_user WHERE id=2")
                raw.commit()

                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    result = service.sync_users("test_source")

            assert result["deactivated"] == 1
        finally:
            os.unlink(db_path)

    def test_sync_roles_static(self, app, db):
        db_uri, db_path = self._setup_source_db()
        sync_config = self._get_sync_config(db_uri)
        try:
            with app.app_context():
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    service.sync_users("test_source")

                user = IdpUser.query.filter_by(username="admin").first()
                assert user.roles == ["Public"]
        finally:
            os.unlink(db_path)

    def test_sync_no_password(self, app, db):
        db_uri, db_path = self._setup_source_db()
        sync_config = self._get_sync_config(db_uri)
        sync_config["test_source"]["sync_password"] = False
        try:
            with app.app_context():
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    service.sync_users("test_source")

                user = IdpUser.query.filter_by(username="admin").first()
                assert user.password_hash is None
        finally:
            os.unlink(db_path)

    def test_sync_password_copy(self, app, db):
        db_uri, db_path = self._setup_source_db()
        sync_config = self._get_sync_config(db_uri)
        try:
            with app.app_context():
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    service.sync_users("test_source")

                user = IdpUser.query.filter_by(username="admin").first()
                assert user.password_hash == "hashedpw"
        finally:
            os.unlink(db_path)

    def test_sync_username_conflict(self, app, db):
        db_uri, db_path = self._setup_source_db()
        sync_config = self._get_sync_config(db_uri)
        try:
            with app.app_context():
                user = IdpUser(username="admin", email="direct@example.com",
                               active=True)
                _db.session.add(user)
                _db.session.commit()

                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    result = service.sync_users("test_source")

                assert len(result["errors"]) >= 1
                assert "conflict" in result["errors"][0].lower()
        finally:
            os.unlink(db_path)

    def test_sync_invalid_source(self, app, db):
        with app.app_context():
            service = SyncService(UserRepository())
            with pytest.raises(ValueError, match="Unknown sync source"):
                service.sync_users("nonexistent")

    def test_sync_db_connection_error(self, app, db):
        bad_config = {
            "bad_source": {
                "description": "Bad",
                "db_uri": "postgresql://bad:bad@nonexistent:5432/bad",
                "table": "users",
                "id_column": "id",
                "column_mapping": {"username": "username", "email": "email"},
                "filter": "",
                "sync_password": False,
                "auto_sync_interval_minutes": 0,
            }
        }
        with app.app_context():
            with patch.object(SyncService, 'get_sync_sources',
                              return_value=bad_config):
                service = SyncService(UserRepository())
                with pytest.raises(ConnectionError):
                    service.sync_users("bad_source")


class TestSyncAPI:
    def test_sync_api_invalid_source(self, client, db):
        resp = client.post("/api/sync/nonexistent")
        assert resp.status_code == 404

    def test_sync_status(self, client, db):
        resp = client.get("/api/sync/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "available_sources" in data
