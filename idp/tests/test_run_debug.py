"""IdP 개발용 실행(`python app/run.py`)은 디버거를 기본으로 켜지 않는다 (CodeQL py/flask-debug).

운영은 gunicorn 이 `app.run:app` 을 import 한다 — 그 경로는 app.run() 을 부르지 않는다.
켜려면 MWM_DEV_DEBUG=1.
"""
import os
import runpy

import pytest
from flask import Flask

RUN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'run.py')


@pytest.fixture
def captured(monkeypatch):
    # run.py 는 create_app() 을 운영 설정으로 부른다. 테스트에서는 TestConfig 로 바꿔 끼운다
    import app as app_pkg
    from app.config import TestConfig
    real_create_app = app_pkg.create_app
    monkeypatch.setattr(app_pkg, 'create_app', lambda: real_create_app(TestConfig))
    calls = []
    monkeypatch.setattr(Flask, 'run', lambda self, **kw: calls.append(kw))
    return calls


def test_debug_is_off_by_default(monkeypatch, captured):
    monkeypatch.delenv('MWM_DEV_DEBUG', raising=False)
    runpy.run_path(RUN_PY, run_name='__main__')
    assert captured[0]['debug'] is False


def test_debug_is_opt_in(monkeypatch, captured):
    monkeypatch.setenv('MWM_DEV_DEBUG', '1')
    runpy.run_path(RUN_PY, run_name='__main__')
    assert captured[0]['debug'] is True
