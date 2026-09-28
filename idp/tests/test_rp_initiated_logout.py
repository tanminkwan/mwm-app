import pytest
from flask import url_for
from app.models import OAuth2Client

def test_discovery_includes_end_session_endpoint(client):
    """Discovery 엔드포인트에 end_session_endpoint가 포함되어 있는지 확인"""
    response = client.get("/.well-known/openid-configuration")
    assert response.status_code == 200
    data = response.get_json()
    assert "end_session_endpoint" in data
    assert data["end_session_endpoint"].endswith("/logout")

def test_simple_logout(client, sample_user):
    """기본 로그아웃 기능 테스트 (파라미터 없음)"""
    # 로그인 시뮬레이션
    with client.session_transaction() as sess:
        sess['_user_id'] = str(sample_user.id)
    
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    # 로그아웃 후 세션이 비어있어야 함
    with client.session_transaction() as sess:
        assert '_user_id' not in sess
    assert b"Successfully logged out" in response.data

def test_rp_initiated_logout_valid_uri(client, sample_user, sample_oauth_client):
    """등록된 redirect_uri를 사용한 RP-Initiated Logout 테스트"""
    # 로그인 시뮬레이션
    with client.session_transaction() as sess:
        sess['_user_id'] = str(sample_user.id)
    
    redirect_uri = "http://localhost/callback" # sample_oauth_client에 등록된 URI
    response = client.get(f"/logout?post_logout_redirect_uri={redirect_uri}")
    
    # 등록된 URI이므로 해당 주소로 리다이렉트되어야 함
    assert response.status_code == 302
    assert response.headers["Location"].startswith(redirect_uri)
    
    # 세션도 종료되어야 함
    with client.session_transaction() as sess:
        assert '_user_id' not in sess

def test_rp_initiated_logout_invalid_uri(client, sample_user):
    """등록되지 않은 redirect_uri 사용 시 기본 로그아웃(Index 리다이렉트) 테스트"""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(sample_user.id)
    
    invalid_uri = "http://malicious-site.com/callback"
    response = client.get(f"/logout?post_logout_redirect_uri={invalid_uri}", follow_redirects=True)
    
    # 잘못된 URI이므로 기본 인덱스로 리다이렉트되고 메시지 표시
    assert response.status_code == 200
    assert b"Successfully logged out" in response.data
    # 세션은 종료되어야 함
    with client.session_transaction() as sess:
        assert '_user_id' not in sess

def test_rp_initiated_logout_with_state(client, sample_user, sample_oauth_client):
    """state 파라미터가 리다이렉트 시 보존되는지 테스트"""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(sample_user.id)
    
    redirect_uri = "http://localhost/callback"
    state = "test-state-123"
    response = client.get(f"/logout?post_logout_redirect_uri={redirect_uri}&state={state}")
    
    assert response.status_code == 302
    assert f"state={state}" in response.headers["Location"]
