"""알림 전송(call_notification)은 TLS 인증서를 검증한다 (CodeQL py/request-without-cert-validation).

예전에는 `verify=False` 로 고정돼 있어, 알림 서버로 가는 길목에서 누구든 서버를 사칭할 수 있었다.
폐쇄망 운영의 알림 서버가 사설 인증서일 수 있으므로 `NOTIFICATION_VERIFY` 로 바꿀 수 있다:
  true(기본) / false / CA 번들 파일 경로
"""
import os
import subprocess
import sys

import pytest
import requests

pytestmark = pytest.mark.unit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config_verify(value):
    env = {k: v for k, v in os.environ.items() if k != 'NOTIFICATION_VERIFY'}
    if value is not None:
        env['NOTIFICATION_VERIFY'] = value
    out = subprocess.run([sys.executable, '-c', 'import config; print(repr(config.NOTIFICATION_VERIFY))'],
                         cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.mark.parametrize('value, expected', [
    (None, 'True'), ('', 'True'), ('true', 'True'), ('TRUE', 'True'),
    ('false', 'False'), (' False ', 'False'),
    ('/certs/monitor-ca.pem', "'/certs/monitor-ca.pem'"),
], ids=['unset', 'empty', 'true', 'TRUE', 'false', 'False-spaces', 'ca-path'])
def test_config_parses_notification_verify(value, expected):
    assert _config_verify(value) == expected


@pytest.fixture
def posted(monkeypatch):
    calls = []

    class _Resp:
        status_code = 200

        def json(self):
            return {}

    def fake_post(url, **kw):
        calls.append(kw)
        return _Resp()
    monkeypatch.setattr(requests, 'post', fake_post)
    return calls


@pytest.mark.parametrize('setting', [True, False, '/certs/monitor-ca.pem'])
def test_call_notification_passes_the_setting_to_requests(monkeypatch, posted, setting):
    from app import app
    from app.views.common import call_notification
    monkeypatch.setitem(app.config, 'NOTIFICATION_VERIFY', setting)
    call_notification('msg')
    assert posted[0]['verify'] == setting


def test_a_tls_failure_is_logged_not_raised(monkeypatch, caplog):
    # WAS 상태 알림은 레코드마다 한 번씩 부른다. 하나가 실패해도 나머지와 배치 job 은 계속돼야 한다
    from app.views.common import call_notification

    def fail(url, **kw):
        raise requests.exceptions.SSLError('certificate verify failed')
    monkeypatch.setattr(requests, 'post', fail)
    call_notification('msg')
    assert 'certificate verify failed' in caplog.text
    assert 'NOTIFICATION_VERIFY' in caplog.text
