"""추가 커버리지 테스트: JoinRole, ColumnRole 전략, Email 충돌, run.py 등"""
import os
import tempfile
import pytest
from unittest.mock import patch
from sqlalchemy import create_engine

from app.services.sync_service import (
    SyncService, JoinRoleSyncStrategy, ColumnRoleSyncStrategy,
)
from app.repositories.user_repo import UserRepository
from app.repositories.oauth_repo import OAuthRepository
from app.services.oauth_service import OAuthService
from app.models import db as _db, IdpUser


class TestJoinRoleSyncStrategy:
    def _setup_join_db(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_uri = f"sqlite:///{db_path}"
        engine = create_engine(db_uri)
        raw = engine.raw_connection()
        cur = raw.cursor()
        cur.execute(
            "CREATE TABLE ab_user ("
            "  id INTEGER PRIMARY KEY, username VARCHAR(64),"
            "  email VARCHAR(320), first_name VARCHAR(64),"
            "  last_name VARCHAR(64), password VARCHAR(256), active BOOLEAN)"
        )
        cur.execute(
            "CREATE TABLE ab_role (id INTEGER PRIMARY KEY, name VARCHAR(64))"
        )
        cur.execute(
            "CREATE TABLE ab_user_role ("
            "  id INTEGER PRIMARY KEY, user_id INTEGER, role_id INTEGER)"
        )
        cur.execute("INSERT INTO ab_user VALUES (1,'admin','a@t.com','A','U','pw',1)")
        cur.execute("INSERT INTO ab_role VALUES (1,'Admin'),(2,'Viewer')")
        cur.execute("INSERT INTO ab_user_role VALUES (1,1,1),(2,1,2)")
        raw.commit()
        cur.close()
        return db_uri, db_path, engine

    def test_join_role_strategy(self):
        db_uri, db_path, engine = self._setup_join_db()
        try:
            strategy = JoinRoleSyncStrategy()
            config = {
                "role_source": {
                    "type": "join",
                    "join_table": "ab_user_role",
                    "join_user_column": "user_id",
                    "join_role_column": "role_id",
                    "role_table": "ab_role",
                    "role_id_column": "id",
                    "role_name_column": "name",
                }
            }
            roles = strategy.get_roles(engine, config, 1)
            assert "Admin" in roles
            assert "Viewer" in roles
        finally:
            os.unlink(db_path)


class TestColumnRoleSyncStrategy:
    def _setup_column_db(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_uri = f"sqlite:///{db_path}"
        engine = create_engine(db_uri)
        raw = engine.raw_connection()
        cur = raw.cursor()
        cur.execute(
            "CREATE TABLE users ("
            "  id INTEGER PRIMARY KEY, username VARCHAR(64),"
            "  email VARCHAR(320), role VARCHAR(100), active BOOLEAN)"
        )
        cur.execute("INSERT INTO users VALUES (1,'u1','u@t.com','Admin,Editor',1)")
        cur.execute("INSERT INTO users VALUES (2,'u2','u2@t.com',NULL,1)")
        raw.commit()
        cur.close()
        return db_uri, db_path, engine

    def test_column_role_strategy(self):
        db_uri, db_path, engine = self._setup_column_db()
        try:
            strategy = ColumnRoleSyncStrategy()
            config = {
                "table": "users",
                "id_column": "id",
                "role_source": {"type": "column", "column_name": "role"},
            }
            roles = strategy.get_roles(engine, config, 1)
            assert roles == ["Admin", "Editor"]
        finally:
            os.unlink(db_path)

    def test_column_role_strategy_null(self):
        db_uri, db_path, engine = self._setup_column_db()
        try:
            strategy = ColumnRoleSyncStrategy()
            config = {
                "table": "users",
                "id_column": "id",
                "role_source": {"type": "column", "column_name": "role"},
            }
            roles = strategy.get_roles(engine, config, 2)
            assert roles == []
        finally:
            os.unlink(db_path)


class TestSyncEmailConflict:
    def _setup_source(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_uri = f"sqlite:///{db_path}"
        engine = create_engine(db_uri)
        raw = engine.raw_connection()
        cur = raw.cursor()
        cur.execute(
            "CREATE TABLE ab_user ("
            "  id INTEGER PRIMARY KEY, username VARCHAR(64),"
            "  email VARCHAR(320), first_name VARCHAR(64),"
            "  last_name VARCHAR(64), password VARCHAR(256), active BOOLEAN)"
        )
        cur.execute(
            "INSERT INTO ab_user VALUES "
            "(1,'newuser','conflict@test.com','A','U','pw',1)"
        )
        raw.commit()
        cur.close()
        return db_uri, db_path

    def test_sync_email_conflict(self, app, db):
        db_uri, db_path = self._setup_source()
        sync_config = {
            "test_source": {
                "description": "test",
                "db_uri": db_uri,
                "table": "ab_user",
                "id_column": "id",
                "column_mapping": {
                    "username": "username", "email": "email",
                    "first_name": "first_name", "last_name": "last_name",
                    "active": "active",
                },
                "filter": "active = 1",
                "sync_password": False,
                "auto_sync_interval_minutes": 0,
            }
        }
        try:
            with app.app_context():
                # IDP에 같은 email로 직접 생성
                user = IdpUser(
                    username="existing", email="conflict@test.com", active=True
                )
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


class TestSyncNoRoleSource:
    def test_sync_without_role_source(self, app, db):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_uri = f"sqlite:///{db_path}"
        engine = create_engine(db_uri)
        raw = engine.raw_connection()
        cur = raw.cursor()
        cur.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64),"
            "  email VARCHAR(320), active BOOLEAN)"
        )
        cur.execute("INSERT INTO users VALUES (1,'norole','nr@t.com',1)")
        raw.commit()
        cur.close()

        sync_config = {
            "nr_source": {
                "description": "no role",
                "db_uri": db_uri,
                "table": "users",
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
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    result = service.sync_users("nr_source")
                assert result["created"] == 1
        finally:
            os.unlink(db_path)


class TestSyncNoFilter:
    def test_sync_without_filter(self, app, db):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_uri = f"sqlite:///{db_path}"
        engine = create_engine(db_uri)
        raw = engine.raw_connection()
        cur = raw.cursor()
        cur.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64),"
            "  email VARCHAR(320), active BOOLEAN)"
        )
        cur.execute("INSERT INTO users VALUES (1,'nofilter','nf@t.com',1)")
        raw.commit()
        cur.close()

        sync_config = {
            "nf_source": {
                "description": "no filter",
                "db_uri": db_uri,
                "table": "users",
                "id_column": "id",
                "column_mapping": {
                    "username": "username", "email": "email", "active": "active",
                },
                "sync_password": False,
                "auto_sync_interval_minutes": 0,
            }
        }
        try:
            with app.app_context():
                with patch.object(SyncService, 'get_sync_sources',
                                  return_value=sync_config):
                    service = SyncService(UserRepository())
                    result = service.sync_users("nf_source")
                assert result["created"] == 1
        finally:
            os.unlink(db_path)


class TestOAuthServiceExpiredCode:
    def test_exchange_expired_code(self, app, db, sample_user, sample_oauth_client):
        import time
        from app.models import OAuth2AuthorizationCode
        with app.app_context():
            code = OAuth2AuthorizationCode(
                code="expired_test_code",
                client_id="test-client",
                redirect_uri="http://localhost/callback",
                scope="openid profile email",
                user_id=sample_user.id,
                expires_at=int(time.time()) - 100,
            )
            _db.session.add(code)
            _db.session.commit()

            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="expired"):
                service.exchange_code_for_token(
                    "expired_test_code", "test-client", "test-secret",
                    "http://localhost/callback",
                )

    def test_exchange_code_client_mismatch(self, app, db, sample_user,
                                            sample_oauth_client):
        import time
        from app.models import OAuth2AuthorizationCode
        with app.app_context():
            code = OAuth2AuthorizationCode(
                code="mismatch_test_code",
                client_id="other-client-id",
                redirect_uri="http://localhost/callback",
                scope="openid",
                user_id=sample_user.id,
                expires_at=int(time.time()) + 300,
            )
            _db.session.add(code)
            _db.session.commit()

            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="Client mismatch"):
                service.exchange_code_for_token(
                    "mismatch_test_code", "test-client", "test-secret",
                    "http://localhost/callback",
                )

    def test_userinfo_expired_token(self, app, db, sample_user, sample_oauth_client):
        import time
        from app.models import OAuth2Token
        with app.app_context():
            token = OAuth2Token(
                access_token="expired_access",
                refresh_token="expired_refresh",
                token_type="Bearer",
                scope="openid",
                expires_in=0,
                expires_at=int(time.time()) - 100,
                user_id=sample_user.id,
                client_id="test-client",
            )
            _db.session.add(token)
            _db.session.commit()

            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="expired"):
                service.get_userinfo("expired_access")


class TestOAuthRepoEdgeCases:
    def test_get_all_clients(self, app, db, sample_oauth_client):
        with app.app_context():
            repo = OAuthRepository()
            clients = repo.get_all_clients()
            assert len(clients) >= 1

    def test_rollback(self, app, db):
        with app.app_context():
            repo = UserRepository()
            repo.rollback()  # Should not raise

    def test_oauth_rollback(self, app, db):
        with app.app_context():
            repo = OAuthRepository()
            repo.rollback()


class TestSyncAPIConnectionError:
    def test_sync_api_connection_error(self, client, db):
        bad_config = {
            "bad": {
                "description": "Bad",
                "db_uri": "postgresql://bad:bad@nonexistent:5432/bad",
                "table": "users", "id_column": "id",
                "column_mapping": {"username": "username", "email": "email"},
                "filter": "", "sync_password": False,
                "auto_sync_interval_minutes": 0,
            }
        }
        with patch.object(SyncService, 'get_sync_sources',
                          return_value=bad_config):
            resp = client.post("/api/sync/bad")
            assert resp.status_code == 502
