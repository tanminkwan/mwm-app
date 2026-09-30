"""응답 보안 헤더·세션 쿠키 속성·IdP 장애 처리 (HOWTO_020 §6, ZAP baseline 2026-09-30).

nginx 도 헤더를 붙이지 않으므로 앱이 붙인다.
"""
import pytest
import requests

from app import app as flask_app


@pytest.mark.parametrize('path', ['/login/', '/static/js/moment.js'])
def test_security_headers(anon_client, path):
    h = anon_client.get(path).headers
    assert h['X-Frame-Options'] == 'SAMEORIGIN'
    assert h['X-Content-Type-Options'] == 'nosniff'
    assert h['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert 'camera=()' in h['Permissions-Policy']
    csp = h['Content-Security-Policy']
    assert "frame-ancestors 'self'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp


def test_session_cookie_attributes(anon_client):
    response = anon_client.get('/login/')
    cookies = [v for k, v in response.headers.items() if k == 'Set-Cookie' and v.startswith('session=')]
    assert cookies, 'login 화면이 세션 쿠키를 주지 않았다'
    assert 'SameSite=Lax' in cookies[0]
    assert 'HttpOnly' in cookies[0]


def test_cookie_config():
    assert flask_app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    assert flask_app.config['REMEMBER_COOKIE_SAMESITE'] == 'Lax'
    assert flask_app.config['REMEMBER_COOKIE_HTTPONLY'] is True


def test_idp_login_when_idp_is_down(anon_client, monkeypatch):
    """IdP 에 닿지 못하면 500 대신 로그인 화면으로 돌아간다."""
    from app.idp_auth import oauth

    def _down(*args, **kwargs):
        raise requests.exceptions.ConnectionError('connection refused')
    monkeypatch.setattr(oauth.mwm_idp, 'authorize_redirect', _down)

    response = anon_client.get('/idp/login')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_idp_callback_does_not_show_exception_text(anon_client, monkeypatch):
    from app.idp_auth import oauth

    def _boom(*args, **kwargs):
        raise RuntimeError('secret-internal-detail')
    monkeypatch.setattr(oauth.mwm_idp, 'authorize_access_token', _boom)

    response = anon_client.get('/idp/callback', follow_redirects=True)
    assert b'secret-internal-detail' not in response.data
