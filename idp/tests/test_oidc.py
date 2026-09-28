import pytest
import jwt
import json
from app.services.oidc_service import OIDCService

def test_oidc_discovery(client):
    """OIDC Discovery 엔드포인트가 올바른 메타데이터를 반환하는지 테스트"""
    response = client.get("/.well-known/openid-configuration")
    assert response.status_code == 200
    data = response.get_json()
    
    assert data["issuer"].rstrip("/") == "http://localhost:5000"
    assert "/oauth/authorize" in data["authorization_endpoint"]
    assert "/oauth/token" in data["token_endpoint"]
    assert "/oauth/jwks" in data["jwks_uri"]
    assert "openid" in data["scopes_supported"]
    assert "RS256" in data["id_token_signing_alg_values_supported"]
    assert "groups" in data["claims_supported"]

def test_oidc_jwks(client):
    """JWKS 엔드포인트가 유효한 RSA 공개키를 반환하는지 테스트"""
    response = client.get("/oauth/jwks")
    assert response.status_code == 200
    data = response.get_json()
    
    assert "keys" in data
    assert len(data["keys"]) > 0
    key = data["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert "n" in key
    assert "e" in key
    assert key["kid"] == "mwm-idp-key-1"

def test_id_token_generation_in_token_exchange(client, db, sample_user, sample_oauth_client):
    """Authorization Code 교환 시 id_token이 포함되는지 테스트 (OIDC)"""
    from app.repositories.oauth_repo import OAuthRepository
    repo = OAuthRepository()
    
    # 1. Authorization Code 생성 (nonce 포함)
    nonce = "test-nonce-123"
    code = repo.create_authorization_code(
        client_id=sample_oauth_client.client_id,
        redirect_uri="http://localhost/callback",
        scope="openid profile email groups",
        user_id=sample_user.id,
        nonce=nonce
    )
    repo.commit()
    
    # 2. Token 교환 요청
    response = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code.code,
        "client_id": sample_oauth_client.client_id,
        "client_secret": sample_oauth_client.client_secret,
        "redirect_uri": "http://localhost/callback",
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert "access_token" in data
    assert "id_token" in data # ID Token 존재 확인
    
    # 3. ID Token 디코딩 및 검증 (서명 검증은 일단 생략하거나 무시하고 페이로드 확인)
    id_token = data["id_token"]
    # Note: decode 시 options={"verify_signature": False} 로 페이로드만 확인 가능
    payload = jwt.decode(id_token, options={"verify_signature": False})
    
    assert payload["iss"] == "http://localhost:5000"
    assert payload["sub"] == sample_user.username
    assert payload["aud"] == sample_oauth_client.client_id
    assert payload["nonce"] == nonce
    assert payload["preferred_username"] == sample_user.username
    assert "groups" in payload
    assert "Public" in payload["groups"]
    assert "roles" in payload
    assert "policy" in payload

def test_id_token_not_generated_without_openid_scope(client, db, sample_user, sample_oauth_client):
    """openid 스코프가 없을 때는 id_token이 생성되지 않는지 테스트"""
    from app.repositories.oauth_repo import OAuthRepository
    repo = OAuthRepository()
    
    # scope에서 openid 제외
    code = repo.create_authorization_code(
        client_id=sample_oauth_client.client_id,
        redirect_uri="http://localhost/callback",
        scope="profile email", 
        user_id=sample_user.id
    )
    repo.commit()
    
    response = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code.code,
        "client_id": sample_oauth_client.client_id,
        "client_secret": sample_oauth_client.client_secret,
        "redirect_uri": "http://localhost/callback",
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert "access_token" in data
    assert "id_token" not in data # ID Token 미발급 확인

def test_oidc_service_jwks_encoding(app):
    """OIDCService가 RSA n, e 값을 올바르게 인코딩하는지 테스트"""
    with app.app_context():
        service = OIDCService()
        jwks = service.get_jwks()
        key = jwks["keys"][0]
        
        # n, e 값이 존재하고 문자열인지 확인
        assert isinstance(key["n"], str)
        assert isinstance(key["e"], str)
        
        # Base64URL 인코딩 특성 확인 (Padding '=' 가 없어야 함)
        assert "=" not in key["n"]
        assert "=" not in key["e"]
