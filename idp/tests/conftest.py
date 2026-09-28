"""공통 테스트 Fixture. TDD 인프라."""
import pytest
import sys
import os

# idp/app 모듈을 import 할 수 있도록 경로 추가 (현재 tests/ 의 상위인 idp/ 를 추가)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.config import TestConfig
from app.models import db as _db


@pytest.fixture(scope="session")
def app():
    """테스트용 Flask 앱 생성"""
    app = create_app(TestConfig)
    yield app


@pytest.fixture(scope="function")
def db(app):
    """각 테스트마다 깨끗한 DB 상태 보장"""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Flask 테스트 클라이언트"""
    return app.test_client()


@pytest.fixture
def sample_user(db):
    """테스트용 사용자 생성"""
    from app.models import IdpUser
    user = IdpUser(
        username="testuser",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        active=True,
        roles=["Public"],
    )
    user.set_password("TestPass123!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def sample_oauth_client(db):
    """테스트용 OAuth2 Client 생성"""
    from app.models import OAuth2Client
    oauth_client = OAuth2Client(
        client_id="test-client",
        client_secret="test-secret",
        client_name="Test App",
        redirect_uris="http://localhost/callback",
        grant_types="authorization_code refresh_token",
        scope="openid profile email",
        policy_mapping={}
    )
    db.session.add(oauth_client)
    db.session.commit()
    return oauth_client


@pytest.fixture
def auth_code(db, sample_user, sample_oauth_client):
    """테스트용 Authorization Code 생성"""
    from app.repositories.oauth_repo import OAuthRepository
    repo = OAuthRepository()
    code = repo.create_authorization_code(
        client_id=sample_oauth_client.client_id,
        redirect_uri="http://localhost/callback",
        scope="openid profile email",
        user_id=sample_user.id,
    )
    repo.commit()
    return code


@pytest.fixture
def access_token(db, sample_user, sample_oauth_client):
    """테스트용 Access Token 생성"""
    from app.repositories.oauth_repo import OAuthRepository
    repo = OAuthRepository()
    token = repo.create_token(
        user_id=sample_user.id,
        client_id=sample_oauth_client.client_id,
        scope="openid profile email",
        expires_in=3600,
    )
    repo.commit()
    return token
