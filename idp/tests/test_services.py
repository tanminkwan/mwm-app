"""서비스 계층 단위 테스트. Coverage 목표: services/ 100%"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.user_service import UserService
from app.services.oauth_service import OAuthService
from app.repositories.user_repo import UserRepository
from app.repositories.oauth_repo import OAuthRepository


class TestUserServiceAuth:
    def test_authenticate_success(self, app, db, sample_user):
        with app.app_context():
            service = UserService(UserRepository())
            user = service.authenticate("testuser", "TestPass123!")
            assert user is not None
            assert user.username == "testuser"

    def test_authenticate_wrong_password(self, app, db, sample_user):
        with app.app_context():
            service = UserService(UserRepository())
            user = service.authenticate("testuser", "wrong")
            assert user is None

    def test_authenticate_nonexistent_user(self, app, db):
        with app.app_context():
            service = UserService(UserRepository())
            user = service.authenticate("ghost", "password")
            assert user is None

    def test_authenticate_inactive_user(self, app, db, sample_user):
        with app.app_context():
            sample_user.active = False
            db.session.commit()
            service = UserService(UserRepository())
            user = service.authenticate("testuser", "TestPass123!")
            assert user is None


class TestUserServiceCRUD:
    def test_create_user_success(self, app, db):
        with app.app_context():
            service = UserService(UserRepository())
            user = service.create_user(
                username="svcuser", email="svc@example.com",
                password="ValidPass123!", first_name="S", last_name="V",
            )
            assert user.username == "svcuser"

    def test_create_user_dup_email(self, app, db, sample_user):
        with app.app_context():
            service = UserService(UserRepository())
            with pytest.raises(ValueError, match="Email already exists"):
                service.create_user(
                    username="other", email="test@example.com",
                    password="ValidPass123!",
                )

    def test_update_user_dup_email(self, app, db, sample_user):
        with app.app_context():
            service = UserService(UserRepository())
            user2 = service.create_user(
                username="user2", email="user2@example.com",
            )
            with pytest.raises(ValueError, match="Email already exists"):
                service.update_user(user2.id, email="test@example.com")

    def test_update_user_short_password(self, app, db, sample_user):
        with app.app_context():
            service = UserService(UserRepository())
            with pytest.raises(ValueError, match="Password must be at least"):
                service.update_user(sample_user.id, password="12")

    def test_get_user_not_found(self, app, db):
        with app.app_context():
            service = UserService(UserRepository())
            with pytest.raises(ValueError, match="User not found"):
                service.get_user(99999)

    def test_list_users_active_only(self, app, db, sample_user):
        with app.app_context():
            service = UserService(UserRepository())
            sample_user.active = False
            db.session.commit()
            users = service.list_users(active_only=True)
            usernames = [u.username for u in users]
            assert "testuser" not in usernames


class TestOAuthServiceEdgeCases:
    def test_refresh_token_client_mismatch(self, app, db, sample_user,
                                            sample_oauth_client, access_token):
        with app.app_context():
            # 다른 client 생성
            from app.models import OAuth2Client
            other = OAuth2Client(
                client_id="other-client", client_secret="other-secret",
                client_name="Other", redirect_uris="http://localhost/other",
                grant_types="authorization_code refresh_token",
                scope="openid",
            )
            db.session.add(other)
            db.session.commit()

            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="Client mismatch"):
                service.refresh_access_token(
                    access_token.refresh_token, "other-client", "other-secret"
                )

    def test_code_redirect_uri_mismatch(self, app, db, sample_user,
                                         sample_oauth_client, auth_code):
        with app.app_context():
            service = OAuthService(OAuthRepository(), UserRepository())
            with pytest.raises(ValueError, match="Redirect URI mismatch"):
                service.exchange_code_for_token(
                    auth_code.code, "test-client", "test-secret",
                    "http://wrong.com/callback"
                )
