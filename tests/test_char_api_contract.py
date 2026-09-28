"""특성화 테스트 — REST API 계약.

응답의 상태코드와 JSON 키를 고정한다. HTML 구조가 아니라 계약을 보므로
FAB 업그레이드를 넘어서도 유효하다.
"""
import json

import pytest


def test_health_returns_healthy(anon_client):
    """헬스체크는 인증 없이 접근 가능하고 형태가 고정되어 있다."""
    resp = anon_client.get('/common/health')
    assert resp.status_code == 200
    assert resp.json == {'status': 'healthy'}


def test_batch_registry_shape(client, auth_headers):
    """배치 레지스트리는 {함수명: 설명} 형태의 객체다."""
    resp = client.get('/api/v1/batch/list', headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json, dict)
    assert len(resp.json) > 0
    assert all(isinstance(k, str) and isinstance(v, str)
               for k, v in resp.json.items())


@pytest.mark.parametrize('removed_func', [
    'delete_kafka_topic',       # TASK 3-1
    'produce_repeated_message',  # TASK 3-1
    'stop_update_was_status',    # TASK 3-1
    'deleteKafkaTopic',          # legacy alias
    'produceRepeatedMessage',
    'stopUpdateWasStatus',
])
def test_removed_batch_functions_are_gone(client, auth_headers, removed_func):
    resp = client.get('/api/v1/batch/list', headers=auth_headers)
    assert removed_func not in resp.json


@pytest.fixture(scope='module')
def seeded_command_type(app):
    """`command_type_id` 검증을 통과하기 위한 최소 시드.

    이 fixture 가 필요하다는 사실 자체가 `REPORT_seed_data_dependencies.md` 가
    지적한 **사전 적재 데이터 의존**을 보여준다 (WS-3-6). 빈 DB 에서는
    `ag_command_type` 에 행이 없어 API 가 `Invalid command_type_id` 로 먼저 막힌다.
    """
    from app import db
    from app.models.agent import AgCommandType
    from app.models.common import CommandClassEnum

    with app.app_context():
        existing = db.session.query(AgCommandType).filter_by(
            command_type_id='PYTEST.TYPE').first()
        if not existing:
            db.session.add(AgCommandType(
                command_type_id='PYTEST.TYPE',
                command_type_name='pytest 전용 command type',
                command_class=CommandClassEnum.ServerFunc,
                target_file_name='sync_role_permissions',
                user_id='pytest',
            ))
            db.session.commit()
        yield 'PYTEST.TYPE'


@pytest.mark.parametrize('sender', ['KAFKA', 'SERVER_N_KAFKA', 'BOGUS'])
def test_command_sender_rejects_removed_enum(client, auth_headers,
                                             seeded_command_type, sender):
    """Kafka 제거(TASK 3-8) 이후 허용값은 SERVER / MQTT 뿐이다."""
    resp = client.post(
        '/api/v1/command_master/create',
        data=json.dumps({'command_type_id': seeded_command_type,
                         'command_sender': sender,
                         'target_agent_id': 'no-such-agent',
                         'periodic_type': 'IMMEDIATE'}),
        headers={**auth_headers, 'Content-Type': 'application/json'},
    )
    assert resp.status_code == 400
    assert resp.json['return_code'] == -2
    assert f'Invalid command_sender: {sender}' in resp.json['message']
    assert "['SERVER', 'MQTT']" in resp.json['message']
