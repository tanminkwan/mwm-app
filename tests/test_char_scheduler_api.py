"""Flask-APScheduler REST API 는 항상 꺼 둔다 (HOWTO_020 §6).

켜져 있으면 `/scheduler/jobs` 가 인증 없이 작업을 조회·추가·실행하게 해 준다. 추가할 때 실행할 함수를
문자열(`module:function`)로 받으므로 인증 없는 원격 코드 실행이 된다.
"정기 JOB 목록" 화면은 로그인해야 쓰는 읽기 전용 `/monitor/jobs.json` 을 쓴다.
"""
import pytest

from app import app as flask_app


@pytest.mark.parametrize('method, path', [
    ('get', '/scheduler'),
    ('get', '/scheduler/jobs'),
    ('post', '/scheduler/jobs'),
    ('post', '/scheduler/jobs/job_ag_finish_commands/run'),
])
def test_scheduler_api_is_not_served(anon_client, method, path):
    response = getattr(anon_client, method)(path, json={'id': 'x', 'func': 'os:getcwd', 'trigger': 'date'})
    assert response.status_code == 404


def test_scheduler_api_is_disabled_in_config():
    assert flask_app.config['SCHEDULER_API_ENABLED'] is False


def test_job_list_requires_login(anon_client):
    response = anon_client.get('/monitor/jobs.json')
    assert response.status_code in (302, 401, 403)


def test_job_list_for_logged_in_user(client):
    response = client.get('/monitor/jobs.json')
    assert response.status_code == 200
    jobs = response.json
    assert isinstance(jobs, list)
    for job in jobs:
        assert set(job) >= {'id', 'name', 'func', 'trigger', 'next_run_time'}
