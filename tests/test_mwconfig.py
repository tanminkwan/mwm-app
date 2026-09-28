"""MWConfigurationApi (`/api/v1/config/*`) 테스트."""
import json

import pytest

from app.sqls.agent_dml import AutorunResult

HTTPM_URL = '/api/v1/config/httpm'


def test_httpm_config_requires_auth(client):
    """인증 없이 호출하면 401 과 함께 인증 헤더 누락을 알린다."""
    response = client.post(HTTPM_URL, json={'host_id': '123'})

    assert response.status_code == 401
    assert 'Authorization' in response.json['msg']


def test_httpm_config_missing_content(client, auth_headers):
    response = client.post(
        HTTPM_URL,
        data=json.dumps({'host_id': '123'}),
        headers=auth_headers,
        content_type='application/json',
    )

    assert response.status_code == 401
    assert response.json == {'return_code': -2,
                             'message': 'content must be included'}


def test_httpm_config_missing_host_id(client, auth_headers):
    response = client.post(
        HTTPM_URL,
        data=json.dumps({'content': 'some_content'}),
        headers=auth_headers,
        content_type='application/json',
    )

    assert response.status_code == 401
    assert response.json == {'return_code': -2,
                             'message': 'host_id must be included'}


def test_httpm_config_success(client, auth_headers, monkeypatch):
    """`_update_httpm` 을 대체해 파싱·DB 반영 없이 계약만 확인한다."""
    monkeypatch.setattr(AutorunResult, '_update_httpm',
                        lambda self, *a, **kw: (0, 'success'))

    response = client.post(
        HTTPM_URL,
        data=json.dumps({'host_id': 'example-host-01',
                         'content': 'some_content'}),
        headers=auth_headers,
        content_type='application/json',
    )

    assert response.status_code == 201
    assert response.json == {'return_code': 0, 'msg': 'success'}


def test_httpm_config_update_failure(client, auth_headers, monkeypatch):
    """`_update_httpm` 이 음수를 반환하면 400 으로 내려간다."""
    monkeypatch.setattr(AutorunResult, '_update_httpm',
                        lambda self, *a, **kw: (-1, 'parse error'))

    response = client.post(
        HTTPM_URL,
        data=json.dumps({'host_id': 'example-host-01',
                         'content': 'bad_content'}),
        headers=auth_headers,
        content_type='application/json',
    )

    assert response.status_code == 400
    assert response.json == {'return_code': -1, 'msg': 'parse error'}
