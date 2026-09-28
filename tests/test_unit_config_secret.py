"""`config.py` 의 비밀 값은 기본값을 두지 않는다 (WS-1-2, WS-1-10).

- `SECRET_KEY` 는 `MWM_SECRET_KEY` 에서만 읽는다 (TASK 1-10). 예전에는 26바이트 키가
  하드코딩되어 있어 누구나 세션 쿠키·JWT 를 위조할 수 있었고, PyJWT 가
  `InsecureKeyLengthWarning` 을 냈다.
- DB 접속 문자열은 필수다. 선택 연동(S3·SMTP·IDP)의 비밀은 **빈 값이 기본**이다 (TASK 1-2).
  예전 기본값은 실제 자격증명이었다.

`config.py` 는 import 시점에 판정하므로 **새 프로세스에서 import** 해서 확인한다.
"""
import os
import subprocess
import sys
import warnings

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


OPTIONAL_SECRETS = ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                    'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_SENDER', 'IDP_CLIENT_SECRET')


def _run_config(expr, drop=(), **overrides):
    """`import config` 후 `expr` 을 출력한다. `drop` 의 환경변수는 지운다."""
    env = {k: v for k, v in os.environ.items() if k not in drop and k not in overrides}
    env.update({k: v for k, v in overrides.items() if v is not None})
    return subprocess.run([sys.executable, '-c', f'import config; print({expr})'],
                          cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60)


def _import_config(secret):
    return _run_config('len(config.SECRET_KEY)', MWM_SECRET_KEY=secret)


@pytest.mark.unit
@pytest.mark.parametrize('secret', [None, ''], ids=['unset', 'empty'])
def test_missing_secret_key_stops_startup(secret):
    """없으면 기동하지 않는다. 공개된 기본값으로 조용히 뜨는 것을 막는다."""
    result = _import_config(secret)

    assert result.returncode != 0
    assert 'MWM_SECRET_KEY' in result.stderr


@pytest.mark.unit
def test_short_secret_key_stops_startup():
    """32바이트 미만이면 기동하지 않는다 (RFC 7518 §3.2, HS256)."""
    result = _import_config('x' * 31)

    assert result.returncode != 0
    assert 'MWM_SECRET_KEY' in result.stderr
    assert '32' in result.stderr


@pytest.mark.unit
def test_secret_key_is_taken_from_the_environment():
    result = _import_config('k' * 32)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '32'


def test_jwt_signing_emits_no_insecure_key_warning(app):
    """JWT 는 `SECRET_KEY` 로 서명된다 (`JWT_SECRET_KEY` 미설정). 경고가 사라져야 한다."""
    from flask_jwt_extended import create_access_token, decode_token

    with app.app_context(), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        decode_token(create_access_token(identity='1'))

    assert not [w for w in caught if w.category.__name__ == 'InsecureKeyLengthWarning']


@pytest.mark.unit
@pytest.mark.parametrize('uri', [None, ''], ids=['unset', 'empty'])
def test_missing_database_uri_stops_startup(uri):
    """DB 접속 문자열에는 기본값이 없다. 예전 기본값은 계정·비밀번호를 담고 있었다."""
    result = _run_config('config.SQLALCHEMY_DATABASE_URI', MWM_DATABASE_URI=uri)

    assert result.returncode != 0
    assert 'MWM_DATABASE_URI' in result.stderr


@pytest.mark.unit
def test_database_uri_is_taken_from_the_environment():
    result = _run_config('config.SQLALCHEMY_DATABASE_URI', MWM_DATABASE_URI='postgresql://u:p@db:5432/x')

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'postgresql://u:p@db:5432/x'


@pytest.mark.unit
def test_optional_integration_secrets_default_to_empty():
    """S3·SMTP·IDP 는 선택 연동이다. 없으면 빈 값 — 앱은 뜨고 해당 기능만 실패한다."""
    result = _run_config('[getattr(config, k) for k in %r]' % (OPTIONAL_SECRETS,), drop=OPTIONAL_SECRETS)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == repr([''] * len(OPTIONAL_SECRETS))


@pytest.mark.unit
def test_smtp_server_is_configurable():
    """SMTP 서버는 SMTP_HOST / SMTP_PORT 로 받는다 (WS-4-5). 기본값은 예전과 같다."""
    default = _run_config('(config.SMTP_HOST, config.SMTP_PORT)', drop=('SMTP_HOST', 'SMTP_PORT'))
    custom = _run_config('(config.SMTP_HOST, config.SMTP_PORT)', SMTP_HOST='mail.example.com', SMTP_PORT='2525')

    assert default.returncode == 0, default.stderr
    assert default.stdout.strip() == "('smtp.gmail.com', 587)"
    assert custom.stdout.strip() == "('mail.example.com', 2525)"
