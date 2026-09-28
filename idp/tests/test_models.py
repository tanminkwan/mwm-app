"""모델 단위 테스트. Coverage 목표: models.py 100%"""
import time
import pytest
from sqlalchemy.exc import IntegrityError
from app.models import IdpUser, OAuth2Client, OAuth2AuthorizationCode, OAuth2Token


class TestIdpUser:
    def test_create_user(self, db):
        user = IdpUser(
            username="newuser", email="new@example.com",
            first_name="New", last_name="User", active=True,
        )
        db.session.add(user)
        db.session.commit()
        assert user.id is not None
        assert user.username == "newuser"
        assert user.active is True

    def test_unique_username(self, db, sample_user):
        dup = IdpUser(username="testuser", email="other@example.com")
        db.session.add(dup)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_unique_email(self, db, sample_user):
        dup = IdpUser(username="other", email="test@example.com")
        db.session.add(dup)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_password_hash(self, db):
        user = IdpUser(username="pwuser", email="pw@example.com")
        user.set_password("MySecret123!")
        db.session.add(user)
        db.session.commit()
        assert user.check_password("MySecret123!") is True
        assert user.check_password("wrong") is False

    def test_check_password_no_hash(self, db):
        user = IdpUser(username="nopw", email="nopw@example.com")
        db.session.add(user)
        db.session.commit()
        assert user.check_password("anything") is False

    def test_user_roles_json(self, db):
        user = IdpUser(
            username="roleuser", email="role@example.com",
            roles=["Admin", "mw_rgroup"],
        )
        db.session.add(user)
        db.session.commit()
        fetched = IdpUser.query.get(user.id)
        assert fetched.roles == ["Admin", "mw_rgroup"]

    def test_sync_fields(self, db):
        user = IdpUser(
            username="syncuser", email="sync@example.com",
            sync_source="mwm_app", sync_id="42",
        )
        db.session.add(user)
        db.session.commit()
        assert user.sync_source == "mwm_app"
        assert user.sync_id == "42"

    def test_to_dict(self, db, sample_user):
        d = sample_user.to_dict()
        assert d["username"] == "testuser"
        assert d["email"] == "test@example.com"
        assert "id" in d
        assert "roles" in d
        assert d["active"] is True

    def test_repr(self, db, sample_user):
        assert "testuser" in repr(sample_user)


class TestOAuth2Client:
    def test_create_client(self, db, sample_oauth_client):
        assert sample_oauth_client.client_id == "test-client"
        assert sample_oauth_client.id is not None

    def test_redirect_uris(self, db, sample_oauth_client):
        assert sample_oauth_client.check_redirect_uri("http://localhost/callback")
        assert not sample_oauth_client.check_redirect_uri("http://evil.com")

    def test_get_redirect_uris_empty(self, db):
        c = OAuth2Client(
            client_id="empty", client_secret="s",
            client_name="e", redirect_uris="",
        )
        assert c.get_redirect_uris() == []

    def test_check_client_secret(self, db, sample_oauth_client):
        assert sample_oauth_client.check_client_secret("test-secret")
        assert not sample_oauth_client.check_client_secret("wrong")

    def test_check_grant_type(self, db, sample_oauth_client):
        assert sample_oauth_client.check_grant_type("authorization_code")
        assert not sample_oauth_client.check_grant_type("implicit")

    def test_get_allowed_scope(self, db, sample_oauth_client):
        allowed = sample_oauth_client.get_allowed_scope("openid profile")
        assert "openid" in allowed
        assert "profile" in allowed

    def test_get_allowed_scope_none(self, db, sample_oauth_client):
        allowed = sample_oauth_client.get_allowed_scope(None)
        assert "openid" in allowed

    def test_to_dict(self, db, sample_oauth_client):
        d = sample_oauth_client.to_dict()
        assert d["client_id"] == "test-client"
        assert isinstance(d["redirect_uris"], list)

    def test_repr(self, db, sample_oauth_client):
        assert "test-client" in repr(sample_oauth_client)


class TestOAuth2AuthorizationCode:
    def test_create_code(self, db, auth_code):
        assert auth_code.code is not None
        assert auth_code.is_expired() is False

    def test_expired_code(self, db):
        code = OAuth2AuthorizationCode(
            code="expired123", client_id="test",
            redirect_uri="http://localhost/callback",
            scope="openid", user_id=1,
            expires_at=int(time.time()) - 100,
        )
        assert code.is_expired() is True

    def test_repr(self, db, auth_code):
        assert "..." in repr(auth_code)


class TestOAuth2Token:
    def test_create_token(self, db, access_token):
        assert access_token.access_token is not None
        assert access_token.refresh_token is not None
        assert access_token.is_expired() is False

    def test_expired_token(self, db):
        token = OAuth2Token(
            access_token="exp_at", refresh_token="exp_rt",
            token_type="Bearer", scope="openid",
            expires_in=0, expires_at=int(time.time()) - 100,
            user_id=1, client_id="test",
        )
        assert token.is_expired() is True

    def test_to_dict(self, db, access_token):
        d = access_token.to_dict()
        assert d["token_type"] == "Bearer"
        assert "access_token" in d
        assert "refresh_token" in d

    def test_repr(self, db, access_token):
        assert "..." in repr(access_token)
