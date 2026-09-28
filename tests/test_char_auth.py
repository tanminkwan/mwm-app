"""특성화 테스트 — 인증 계약.

지금 동작하는 방식을 고정한다. FAB·Flask 업그레이드 시 회귀 탐지용이다.
"""
import json

from tests.conftest import TEST_PASSWORD, TEST_USERNAME

LOGIN_URL = '/login/'
REST_LOGIN_URL = '/api/v1/security/login'


def test_login_page_is_public(anon_client):
    assert anon_client.get(LOGIN_URL).status_code == 200


def test_session_login_redirects(anon_client):
    resp = anon_client.post(LOGIN_URL,
                       data={"username": TEST_USERNAME,
                             'password': TEST_PASSWORD},
                       follow_redirects=False)
    # 성공 시 302 로 index 로 보낸다 (실패하면 200 으로 폼을 다시 그린다)
    assert resp.status_code == 302


def test_session_login_rejects_bad_password(anon_client):
    """잘못된 비밀번호도 302 로 리다이렉트된다 (FAB 는 플래시로 알린다).

    상태코드만으로는 성공과 구분되지 않으므로, 보호된 화면이 여전히
    로그인으로 튕기는지로 인증 실패를 확인한다.
    """
    resp = anon_client.post(LOGIN_URL,
                       data={"username": TEST_USERNAME,
                             "password": "wrong-password"},
                       follow_redirects=False)
    assert resp.status_code == 302

    protected = anon_client.get("/agentmodelview/list/", follow_redirects=False)
    assert protected.status_code == 302
    assert "/login/" in protected.headers["Location"]


def test_rest_login_issues_jwt(client):
    resp = client.post(
        REST_LOGIN_URL,
        data=json.dumps({'username': TEST_USERNAME,
                         'password': TEST_PASSWORD,
                         'provider': 'db', 'refresh': True}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    assert 'access_token' in resp.json
    assert 'refresh_token' in resp.json


def test_rest_login_rejects_bad_password(client):
    resp = client.post(
        REST_LOGIN_URL,
        data=json.dumps({'username': TEST_USERNAME,
                         'password': 'wrong-password', 'provider': 'db'}),
        content_type='application/json',
    )
    assert resp.status_code == 401


def test_protected_api_requires_bearer(anon_client):
    """인증 헤더가 없으면 401 과 함께 그 사실을 알린다."""
    resp = anon_client.get("/api/v1/batch/list")
    assert resp.status_code == 401
    assert 'Authorization' in resp.json['msg']


def test_jwt_from_rest_login_is_accepted(client):
    """REST 로그인으로 받은 토큰이 보호된 API 에서 통한다.

    PyJWT 2.10+ 는 `sub` 를 문자열로 요구하지만 FAB 는 정수 user.id 를 넣는다.
    `config.py` 의 `JWT_VERIFY_SUB = False` 가 이 조합을 성립시킨다.
    이 테스트가 깨지면 그 설정을 먼저 확인할 것.
    """
    login = client.post(
        REST_LOGIN_URL,
        data=json.dumps({'username': TEST_USERNAME,
                         'password': TEST_PASSWORD,
                         'provider': 'db', 'refresh': True}),
        content_type='application/json',
    )
    token = login.json['access_token']

    resp = client.get('/api/v1/batch/list',
                      headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
