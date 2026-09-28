"""사용자 데이터 접근 계층. SOLID-SRP: DB CRUD 조작만 담당."""
from app.models import db, IdpUser


class UserRepository:
    """IdpUser 테이블에 대한 CRUD 연산"""

    def get_by_id(self, user_id):
        return db.session.get(IdpUser, user_id)

    def get_by_username(self, username):
        return IdpUser.query.filter_by(username=username).first()

    def get_by_email(self, email):
        return IdpUser.query.filter_by(email=email).first()

    def get_by_sync(self, sync_source, sync_id):
        return IdpUser.query.filter_by(
            sync_source=sync_source, sync_id=str(sync_id)
        ).first()

    def get_all(self, active_only=False):
        query = IdpUser.query
        if active_only:
            query = query.filter_by(active=True)
        return query.all()

    def get_synced_users(self, sync_source):
        return IdpUser.query.filter_by(sync_source=sync_source).all()

    def create(self, **kwargs):
        password = kwargs.pop("password", None)
        user = IdpUser(**kwargs)
        if password:
            user.set_password(password)
        db.session.add(user)
        db.session.flush()
        return user

    def update(self, user, **kwargs):
        password = kwargs.pop("password", None)
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        if password:
            user.set_password(password)
        db.session.flush()
        return user

    def delete(self, user):
        """논리 삭제: active=False 처리"""
        user.active = False
        db.session.flush()
        return user

    def commit(self):
        db.session.commit()

    def rollback(self):
        db.session.rollback()
