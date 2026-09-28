import pytest
from flask import url_for
from flask_login import current_user

def test_sso_skip_login(client, sample_user, sample_oauth_client):
    """이미 로그인된 경우 로그인 페이지를 건너뛰고 바로 code를 발급받는지 테스트"""
    # 1. 로그인 요청 (POST)
    res = client.post(
        f'/oauth/authorize?response_type=code&client_id={sample_oauth_client.client_id}&redirect_uri={sample_oauth_client.redirect_uris}',
        data={'username': 'testuser', 'password': 'TestPass123!'},
        follow_redirects=False
    )
    assert res.status_code == 200
    assert 'code=' in res.data.decode()

    # 2. 동일 브라우저(client)로 다시 Authorize 요청 (GET) -> 로그인 폼 없이 바로 리다이렉트 되어야 함
    res = client.get(
        f'/oauth/authorize?response_type=code&client_id={sample_oauth_client.client_id}&redirect_uri={sample_oauth_client.redirect_uris}',
        follow_redirects=False
    )
    assert res.status_code == 200
    assert 'code=' in res.data.decode()
    assert b'login' not in res.data.lower()

def test_logout(client, sample_user):
    """로그아웃 기능 테스트"""
    # 1. /login 을 통해 로그인 처리
    client.post('/login', data={'username': 'testuser', 'password': 'TestPass123!'})
    
    # 2. 로그아웃 요청
    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200
    assert b'logged out' in res.data.lower()
