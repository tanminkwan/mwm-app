import time
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, JSON

db = SQLAlchemy()


class IdpUser(db.Model, UserMixin):
    """IDP 사용자 모델"""
    __tablename__ = "idp_user"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    first_name = Column(String(64), nullable=False, default="")
    last_name = Column(String(64), nullable=False, default="")
    active = Column(Boolean, default=True, nullable=False)
    roles = Column(JSON, default=list)
    sync_source = Column(String(50), nullable=True)
    sync_id = Column(String(100), nullable=True)
    api_key = Column(String(128), unique=True, nullable=True, index=True) # API authentication key
    created_on = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_on = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "active": self.active,
            "roles": self.roles or [],
            "api_key": self.api_key,
            "sync_source": self.sync_source,
            "sync_id": self.sync_id,
            "created_on": self.created_on.isoformat() if self.created_on else None,
            "updated_on": self.updated_on.isoformat() if self.updated_on else None,
        }

    def __repr__(self):
        return f"<IdpUser {self.username}>"


class OAuth2Client(db.Model):
    """OAuth2 클라이언트 모델"""
    __tablename__ = "oauth2_client"

    id = Column(Integer, primary_key=True)
    client_id = Column(String(48), unique=True, nullable=False, index=True)
    client_secret = Column(String(120), nullable=False)
    client_name = Column(String(120), nullable=False)
    redirect_uris = Column(Text, nullable=False, default="")
    grant_types = Column(String(200), nullable=False, default="authorization_code")
    scope = Column(String(200), nullable=False, default="openid profile email")
    policy_mapping = Column(JSON, default=dict) # Role mapping for specific services (e.g., Minio)
    created_on = Column(DateTime, default=datetime.utcnow, nullable=False)

    def get_redirect_uris(self):
        return self.redirect_uris.split() if self.redirect_uris else []

    def check_redirect_uri(self, redirect_uri):
        return redirect_uri in self.get_redirect_uris()

    def check_client_secret(self, secret):
        return self.client_secret == secret

    def check_grant_type(self, grant_type):
        return grant_type in self.grant_types.split()

    def get_allowed_scope(self, scope):
        allowed = set(self.scope.split())
        requested = set(scope.split()) if scope else set()
        return " ".join(allowed & requested) if requested else self.scope

    def to_dict(self):
        return {
            "id": self.id,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "redirect_uris": self.get_redirect_uris(),
            "grant_types": self.grant_types.split(),
            "scope": self.scope,
            "policy_mapping": self.policy_mapping or {},
        }

    def __repr__(self):
        return f"<OAuth2Client {self.client_id}>"


class OAuth2AuthorizationCode(db.Model):
    """OAuth2 Authorization Code 모델 (임시, 1회용)"""
    __tablename__ = "oauth2_code"

    id = Column(Integer, primary_key=True)
    code = Column(String(120), unique=True, nullable=False, index=True)
    client_id = Column(String(48), nullable=False)
    redirect_uri = Column(Text, nullable=False)
    scope = Column(String(200), nullable=False, default="")
    user_id = Column(Integer, nullable=False)
    nonce = Column(String(128), nullable=True) # OIDC nonce
    expires_at = Column(Integer, nullable=False)

    def is_expired(self):
        return time.time() > self.expires_at

    def __repr__(self):
        return f"<OAuth2Code {self.code[:8]}...>"


class OAuth2Token(db.Model):
    """OAuth2 Access/Refresh Token 모델"""
    __tablename__ = "oauth2_token"

    id = Column(Integer, primary_key=True)
    token_type = Column(String(20), nullable=False, default="Bearer")
    access_token = Column(String(255), unique=True, nullable=False, index=True)
    refresh_token = Column(String(255), unique=True, nullable=True, index=True)
    scope = Column(String(200), nullable=False, default="")
    expires_in = Column(Integer, nullable=False)
    expires_at = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    client_id = Column(String(48), nullable=False)

    def is_expired(self):
        return time.time() > self.expires_at

    def to_dict(self):
        return {
            "token_type": self.token_type,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "expires_in": self.expires_in,
        }

    def __repr__(self):
        return f"<OAuth2Token {self.access_token[:8]}...>"
