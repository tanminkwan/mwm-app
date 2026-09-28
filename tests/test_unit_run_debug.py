"""개발용 진입점 run.py 는 디버거를 기본으로 켜지 않는다 (CodeQL py/flask-debug).

운영은 gunicorn(supervisord.conf)으로 뜨지만 run.py 도 이미지에 들어간다.
Werkzeug 디버거는 브라우저에서 임의 코드를 실행하게 해 주므로, 0.0.0.0 에 기본으로 열려 있으면 안 된다.
켜려면 MWM_DEV_DEBUG=1.
"""
import os
import runpy

import pytest

pytestmark = pytest.mark.unit

RUN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'run.py')


@pytest.fixture
def captured(monkeypatch):
    from app import app
    calls = []
    monkeypatch.setattr(app, 'run', lambda **kw: calls.append(kw))
    return calls


def test_debug_is_off_by_default(monkeypatch, captured):
    monkeypatch.delenv('MWM_DEV_DEBUG', raising=False)
    runpy.run_path(RUN_PY, run_name='__main__')
    assert captured[0]['debug'] is False


def test_debug_is_opt_in(monkeypatch, captured):
    monkeypatch.setenv('MWM_DEV_DEBUG', '1')
    runpy.run_path(RUN_PY, run_name='__main__')
    assert captured[0]['debug'] is True


def test_importing_run_py_does_not_start_a_server(captured):
    runpy.run_path(RUN_PY, run_name='run')
    assert captured == []
