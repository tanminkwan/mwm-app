"""IDP(OIDC) 로그인 콜백 — IDP 응답을 흉내 내 FAB 사용자 로그인까지 확인한다.

콜백은 IDP 토큰으로 userinfo 를 받아 같은 username 의 FAB 사용자로 로그인시킨다.
FAB 5 업그레이드에서 보안 관리자·로그인 API 가 바뀌어도 이 흐름이 유지되는지 본다.
"""
from unittest import mock

from tests.conftest import TEST_USERNAME


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _patched_idp(username):
    from app import idp_auth
    fake = mock.MagicMock()
    fake.authorize_access_token.return_value = {'access_token': 'x'}
    fake.get.return_value = _Resp({'username': username})
    return mock.patch.object(idp_auth.oauth, 'mwm_idp', fake, create=True)


def test_callback_logs_in_known_user(app):
    c = app.test_client()
    with _patched_idp(TEST_USERNAME):
        r = c.get('/idp/callback')

    assert r.status_code == 302
    assert '/login' not in r.headers['Location']
    assert c.get('/users/list/').status_code == 200      # 관리자 화면이 열린다 = 로그인됨


def test_callback_rejects_unknown_user(app):
    c = app.test_client()
    with _patched_idp('no-such-user'):
        r = c.get('/idp/callback')

    assert r.status_code == 302
    assert '/login' in r.headers['Location']
