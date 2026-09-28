"""Edge case 커버리지 테스트: 미커버 라인 전용"""
import os
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine

from app.services.oauth_service import OAuthService
from app.services.sync_service import SyncService
from app.repositories.user_repo import UserRepository
from app.repositories.oauth_repo import OAuthRepository
from app.models import db as _db, IdpUser, OAuth2Token, OAuth2AuthorizationCode


class TestOAuthInvalidClientInExchange:
    """oauth_service.py line 42: Invalid client_id in exchange"""

    def test_exchange_invalid_client(self, app, db, sample_oauth_client):
        with app.app_context():
            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="Invalid client_id"):
                service.exchange_code_for_token(
                    "some_code", "nonexistent-client", "secret", "http://x"
                )


class TestOAuthInvalidRefreshCredentials:
    """oauth_service.py line 79: Invalid client credentials in refresh"""

    def test_refresh_bad_secret(self, app, db, sample_oauth_client):
        with app.app_context():
            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="Invalid client credentials"):
                service.refresh_access_token(
                    "some_refresh", "test-client", "wrong-secret"
                )

    def test_refresh_nonexistent_client(self, app, db):
        with app.app_context():
            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="Invalid client credentials"):
                service.refresh_access_token("some_refresh", "ghost", "secret")


class TestOAuthUserinfoUserNotFound:
    """oauth_service.py line 111: user not found for valid token"""

    def test_userinfo_user_deleted(self, app, db, sample_oauth_client):
        with app.app_context():
            # 토큰은 존재하는데 사용자가 없는 경우
            token = OAuth2Token(
                access_token="orphan_token",
                refresh_token="orphan_refresh",
                token_type="Bearer",
                scope="openid",
                expires_in=3600,
                expires_at=int(time.time()) + 3600,
                user_id=99999,  # 존재하지 않는 user_id
                client_id="test-client",
            )
            _db.session.add(token)
            _db.session.commit()

            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="User not found"):
                service.get_userinfo("orphan_token")


class TestSyncExistingUserUsernameConflict:
    """sync_service.py lines 156-159: existing synced user username conflict"""

    def test_sync_update_username_conflict(self, app, db):
        """기존 동기화 사용자의 username이 다른 사용자와 충돌"""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_uri = f"sqlite:///{db_path}"
        engine = create_engine(db_uri)
        raw = engine.raw_connection()
        cur = raw.cursor()
        cur.execute(
            "CREATE TABLE t (id INTEGER PRIMARY KEY, username VARCHAR(64),"
            " email VARCHAR(320), active BOOLEAN)"
        )
        cur.execute("INSERT INTO t VALUES (1,'conflicting','a@t.com',1)")
        raw.commit()
        cur.close()

        sync_config = {
            "s1": {
                "description": "test",
                "db_uri": db_uri,
                "table": "t",
                "id_column": "id",
                "column_mapping": {
                    "username": "username", "email": "email", "active": "active",
                },
                "filter": "",
                "sync_password": False,
                "auto_sync_interval_minutes": 0,
            }
        }
        try:
            with app.app_context():
                # 먼저 동기화해서 synced user 생성
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    SyncService(UserRepository()).sync_users("s1")

                # IDP에 직접 "conflicting2" 사용자 생성
                u = IdpUser(username="conflicting2", email="c2@t.com", active=True)
                _db.session.add(u)
                _db.session.commit()

                # 외부 DB에서 username을 "conflicting2"로 변경 (충돌)
                ext_engine = create_engine(db_uri)
                raw2 = ext_engine.raw_connection()
                raw2.cursor().execute(
                    "UPDATE t SET username='conflicting2' WHERE id=1"
                )
                raw2.commit()

                # 재동기화 → username 충돌
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    result = SyncService(UserRepository()).sync_users("s1")

                assert len(result["errors"]) >= 1
                assert "conflict" in result["errors"][0].lower()
        finally:
            os.unlink(db_path)


class TestSyncRowLevelException:
    """sync_service.py lines 183-185: per-row exception handling"""

    def test_sync_row_exception(self, app, db):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_uri = f"sqlite:///{db_path}"
        engine = create_engine(db_uri)
        raw = engine.raw_connection()
        cur = raw.cursor()
        cur.execute(
            "CREATE TABLE t (id INTEGER PRIMARY KEY, username VARCHAR(64),"
            " email VARCHAR(320), active BOOLEAN)"
        )
        cur.execute("INSERT INTO t VALUES (1,'u1','u1@t.com',1)")
        raw.commit()
        cur.close()

        sync_config = {
            "err_source": {
                "description": "test",
                "db_uri": db_uri,
                "table": "t",
                "id_column": "id",
                "column_mapping": {
                    "username": "username", "email": "email", "active": "active",
                },
                "filter": "",
                "sync_password": False,
                "auto_sync_interval_minutes": 0,
            }
        }
        try:
            with app.app_context():
                # Mock user_repo.create to raise
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    with patch.object(
                        service.user_repo, 'create',
                        side_effect=RuntimeError("DB error")
                    ):
                        result = service.sync_users("err_source")

                assert len(result["errors"]) >= 1
                assert "DB error" in result["errors"][0]
        finally:
            os.unlink(db_path)


class TestRouteAuthorizeException:
    """routes.py lines 87-88: Exception in create_authorization_code"""

    def test_authorize_code_creation_error(self, client, db, sample_user,
                                            sample_oauth_client):
        with patch(
            "app.routes.OAuthService.create_authorization_code",
            side_effect=RuntimeError("DB crashed"),
        ):
            resp = client.post(
                "/oauth/authorize?client_id=test-client"
                "&redirect_uri=http://localhost/callback"
                "&response_type=code",
                data={"username": "testuser", "password": "TestPass123!"},
            )
            assert resp.status_code == 500


class TestApiSyncConnectionError:
    """api.py line 120: sync connection error returns 502"""

    def test_sync_api_502(self, client, db):
        with patch.object(
            SyncService, 'sync_users',
            side_effect=ConnectionError("Cannot connect")
        ):
            with patch.object(
                SyncService, 'get_sync_sources',
                return_value={"src": {}}
            ):
                resp = client.post("/api/sync/src")
                assert resp.status_code == 502


class TestUserRepoGetByEmail:
    """user_repo.py line 46: get_by_email usage"""

    def test_user_repo_get_by_email(self, app, db, sample_user):
        with app.app_context():
            repo = UserRepository()
            user = repo.get_by_email("test@example.com")
            assert user is not None
            assert user.username == "testuser"
            assert repo.get_by_email("nonexistent@x.com") is None
