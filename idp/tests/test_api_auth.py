"""관리 API 인증 (app/api.py 의 require_api_key).

관리 API 는 `Authorization: Bearer <API 키>` 와 Admin 또는 PowerUser 역할을 요구한다.
/api/userinfo 만 예외다 — OAuth2 access token 으로 인증한다 (test_api.py::TestUserInfo).
"""
import pytest

from app.models import IdpUser

# /api 아래에서 API 키 없이 열려 있어도 되는 엔드포인트
PUBLIC_ENDPOINTS = {"api.userinfo"}


def _admin_api_routes(app):
    """API 키로 보호돼야 하는 (method, url) 전부. URL 변수는 1 로 채운다."""
    routes = []
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith("api.") or rule.endpoint in PUBLIC_ENDPOINTS:
            continue
        url = rule.rule
        for arg in rule.arguments:
            url = url.replace(f"<int:{arg}>", "1").replace(f"<{arg}>", "x")
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            routes.append((method, url))
    return routes


def _user_with_key(db, key, roles, active=True):
    user = IdpUser(username=f"u-{key}", email=f"{key}@example.com",
                   active=active, roles=roles, api_key=key)
    db.session.add(user)
    db.session.commit()
    return {"Authorization": f"Bearer {key}"}


def test_every_admin_route_is_listed(app):
    # 라우트 목록이 비면 아래 검사가 아무것도 확인하지 않은 채 통과한다
    assert len(_admin_api_routes(app)) == 12


def test_every_admin_route_rejects_a_missing_key(app, client, db):
    for method, url in _admin_api_routes(app):
        resp = client.open(url, method=method)
        assert resp.status_code == 401, f"{method} {url}"


def test_every_admin_route_rejects_an_unknown_key(app, client, db):
    headers = {"Authorization": "Bearer mwm_sk_does_not_exist"}
    for method, url in _admin_api_routes(app):
        resp = client.open(url, method=method, headers=headers)
        assert resp.status_code == 401, f"{method} {url}"


@pytest.mark.parametrize("header", ["mwm_sk_x", "Basic mwm_sk_x", "Bearer "])
def test_malformed_authorization_header_is_rejected(client, db, header):
    resp = client.get("/api/users", headers={"Authorization": header})
    assert resp.status_code == 401


def test_a_key_without_an_admin_role_is_forbidden(client, db):
    headers = _user_with_key(db, "mwm_sk_public", ["Public"])
    resp = client.get("/api/users", headers=headers)
    assert resp.status_code == 403


def test_a_key_with_no_roles_is_forbidden(client, db):
    headers = _user_with_key(db, "mwm_sk_noroles", None)
    resp = client.get("/api/users", headers=headers)
    assert resp.status_code == 403


@pytest.mark.parametrize("role", ["Admin", "PowerUser"])
def test_admin_and_poweruser_keys_are_accepted(client, db, role):
    headers = _user_with_key(db, f"mwm_sk_{role.lower()}", [role])
    resp = client.get("/api/users", headers=headers)
    assert resp.status_code == 200


def test_a_deactivated_users_key_is_rejected(client, db):
    # 비활성 사용자는 로그인할 수 없다(UserService.authenticate). API 키도 같아야 한다 —
    # mwm-app 에서 지워져 동기화로 비활성화된 관리자의 키가 계속 통하면 안 된다
    headers = _user_with_key(db, "mwm_sk_inactive", ["Admin"], active=False)
    resp = client.get("/api/users", headers=headers)
    assert resp.status_code == 401
