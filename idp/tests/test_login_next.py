"""로그인 후 이동(`/login?next=`)은 이 서버 안의 경로로만 (CodeQL py/url-redirection).

예전에는 `next` 를 그대로 redirect 했다 — `/login?next=https://evil.example` 링크로 로그인시키면
진짜 IdP 로그인 뒤 가짜 사이트로 보내 피싱에 쓸 수 있었다.
Flask-Login 은 `@login_required` 화면에서 `next` 를 상대 경로로 만든다. 그 흐름은 그대로여야 한다.
(OAuth authorize 는 자체 로그인 폼을 쓰므로 `next` 를 거치지 않는다.)
"""
import pytest


def _login(client, next_url):
    return client.post("/login", query_string={"next": next_url},
                       data={"username": "testuser", "password": "TestPass123!"})


@pytest.mark.parametrize("next_url", [
    "/oauth/authorize?client_id=test-client&response_type=code",
    "/",
])
def test_a_local_path_is_followed(client, db, sample_user, next_url):
    resp = _login(client, next_url)
    assert resp.status_code == 302
    assert resp.headers["Location"] == next_url


@pytest.mark.parametrize("next_url", [
    "https://evil.example/phish",
    "//evil.example/phish",
    "/\\evil.example/phish",
    "\\\\evil.example",
    "javascript:alert(1)",
    "http:/evil.example",
])
def test_anything_else_goes_to_the_index(client, db, sample_user, next_url):
    resp = _login(client, next_url)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_a_protected_page_returns_after_login(client, db, sample_user):
    # @login_required 화면 → Flask-Login 이 /login?next=<상대 경로> 로 보낸다 → 로그인하면 돌아온다
    first = client.get("/clients")
    assert first.status_code == 302
    login_url = first.headers["Location"]
    assert login_url.startswith("/login?next=")
    back = client.post(login_url, data={"username": "testuser", "password": "TestPass123!"})
    assert back.status_code == 302
    assert back.headers["Location"] == "/clients"
