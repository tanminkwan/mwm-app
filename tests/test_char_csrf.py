"""CSRF 보호 (ZAP full scan 2026-09-30, HOWTO_020 §6).

예전에는 CSRFProtect 가 없어 토큰 없는 FAB 삭제 POST 가 실제로 지웠다.
- 화면(BaseView) POST 는 Flask-WTF 가 검사한다.
- API(BaseApi)는 FAB 가 검사에서 빼는데, 로그인 쿠키로 인증된 요청은 앱이 따로 검사한다.
- JWT(Authorization 헤더)로 오는 Agent·외부 연동은 검사하지 않는다.

conftest 는 WTF_CSRF_ENABLED=False 로 돈다. 여기서만 켠다.
"""
import re

import pytest

from app import app as flask_app, db
from app.models.knowledge import UtHtmlContent


@pytest.fixture
def csrf_on(monkeypatch):
    monkeypatch.setitem(flask_app.config, 'WTF_CSRF_ENABLED', True)


# 테스트 클라이언트는 PREFERRED_URL_SCHEME=https 로 요청한다 — Flask-WTF 는 https 에서 Referer 도 확인한다
# (브라우저는 같은 출처 POST 에 Referer 를 보낸다. Referrer-Policy 도 허용한다)
SAME_ORIGIN = {'Referer': 'https://localhost/'}


def _token(client):
    html = client.get('/').get_data(as_text=True)
    return re.search(r'<meta name="csrf-token" content="([^"]+)"', html).group(1)


@pytest.fixture
def temp_role(app):
    with app.app_context():
        role = app.appbuilder.sm.add_role('pytest-csrf-role')
        role_id = role.id
    yield role_id
    with app.app_context():
        r = app.appbuilder.sm.find_role('pytest-csrf-role')
        if r:
            db.session.delete(r)
            db.session.commit()


@pytest.fixture
def html_doc(app):
    with app.app_context():
        doc = UtHtmlContent(content_name='csrf', content_html='<p>x</p>', user_id='pytest', group_id='')
        db.session.add(doc)
        db.session.commit()
        doc_id = doc.id
    yield doc_id
    with app.app_context():
        doc = db.session.get(UtHtmlContent, doc_id)
        if doc:
            db.session.delete(doc)
            db.session.commit()


def test_pages_expose_token_and_script(client):
    html = client.get('/').get_data(as_text=True)
    assert re.search(r'<meta name="csrf-token" content="[^"]+"', html)
    assert '/static/js/mwm_csrf.js' in html


def test_view_post_without_token_is_rejected(client, csrf_on, temp_role, app):
    assert client.post(f'/roles/delete/{temp_role}').status_code == 400
    with app.app_context():
        assert app.appbuilder.sm.find_role('pytest-csrf-role') is not None


def test_view_post_with_token_is_accepted(client, csrf_on, temp_role, app):
    response = client.post(f'/roles/delete/{temp_role}', headers={'X-CSRFToken': _token(client), **SAME_ORIGIN})
    assert response.status_code == 302
    with app.app_context():
        assert app.appbuilder.sm.find_role('pytest-csrf-role') is None


def test_cookie_authenticated_api_post_needs_token(client, csrf_on, html_doc, monkeypatch):
    monkeypatch.setattr('app.views.knowledge.send_mail', lambda *a, **k: pytest.fail('실제 메일 발송'))
    url = f'/ut/htmlcontent/{html_doc}/send_email'
    body = {'tag_names': [], 'manual_emails': ''}
    assert client.post(url, json=body).status_code == 400          # CSRF
    ok = client.post(url, json=body, headers={'X-CSRFToken': _token(client), **SAME_ORIGIN})
    assert ok.status_code == 400 and ok.json.get('error') == '발송 대상 이메일이 없습니다.'   # 토큰 통과 → 수신자 검사


def test_jwt_api_post_is_not_checked(csrf_on, anon_client, auth_headers):
    response = anon_client.post('/api/v1/markdown/to_html', json={'content': '# x'}, headers=auth_headers)
    assert response.status_code == 200


def test_api_login_without_cookie_is_not_checked(csrf_on, anon_client):
    """Agent 가 쓰는 /api/v1/security/login 은 쿠키가 없다 — CSRF 400 이 아니라 인증 결과를 받아야 한다."""
    response = anon_client.post('/api/v1/security/login',
                                json={'username': 'nobody', 'password': 'x', 'provider': 'db'})
    assert response.status_code == 401
