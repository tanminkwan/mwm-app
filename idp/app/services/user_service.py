"""사용자 비즈니스 로직. SOLID-SRP: 사용자 관련 검증/변환/정책만 담당."""
import logging

from flask import current_app

logger = logging.getLogger(__name__)


class UserService:
    """사용자 CRUD 비즈니스 로직. Repository를 주입받아 사용 (SOLID-DIP)."""

    def __init__(self, user_repo):
        self.user_repo = user_repo

    def get_user(self, user_id):
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")
        return user

    def get_user_by_username(self, username):
        return self.user_repo.get_by_username(username)

    def list_users(self, active_only=False):
        return self.user_repo.get_all(active_only=active_only)

    def create_user(self, username, email, password=None, first_name="",
                    last_name="", roles=None, sync_source=None, sync_id=None):
        # 중복 검증
        if self.user_repo.get_by_username(username):
            raise ValueError(f"Username already exists: {username}")
        if self.user_repo.get_by_email(email):
            raise ValueError(f"Email already exists: {email}")

        # 비밀번호 정책 검증
        if password:
            min_length = current_app.config.get("PASSWORD_MIN_LENGTH", 8)
            if len(password) < min_length:
                raise ValueError(
                    f"Password must be at least {min_length} characters"
                )

        user = self.user_repo.create(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            roles=roles or [],
            sync_source=sync_source,
            sync_id=sync_id,
        )
        self.user_repo.commit()
        logger.info(f"User created: {username}")
        return user

    def update_user(self, user_id, **kwargs):
        user = self.get_user(user_id)

        # username 변경 시 중복 검증
        new_username = kwargs.get("username")
        if new_username and new_username != user.username:
            if self.user_repo.get_by_username(new_username):
                raise ValueError(f"Username already exists: {new_username}")

        # email 변경 시 중복 검증
        new_email = kwargs.get("email")
        if new_email and new_email != user.email:
            if self.user_repo.get_by_email(new_email):
                raise ValueError(f"Email already exists: {new_email}")

        # 비밀번호 정책 검증
        password = kwargs.get("password")
        if password:
            min_length = current_app.config.get("PASSWORD_MIN_LENGTH", 8)
            if len(password) < min_length:
                raise ValueError(
                    f"Password must be at least {min_length} characters"
                )

        user = self.user_repo.update(user, **kwargs)
        self.user_repo.commit()
        logger.info(f"User updated: {user.username}")
        return user

    def delete_user(self, user_id):
        user = self.get_user(user_id)
        self.user_repo.delete(user)
        self.user_repo.commit()
        logger.info(f"User deactivated: {user.username}")
        return user

    def authenticate(self, username, password):
        user = self.user_repo.get_by_username(username)
        if not user or not user.active:
            return None
        if not user.check_password(password):
            return None
        return user
