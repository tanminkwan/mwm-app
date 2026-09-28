"""API 오류 응답에 내부 예외 문구를 싣지 않는다 (CodeQL py/stack-trace-exposure).

예전에는 `except Exception as e: return jsonify(error=str(e))` 가 흔했다 — DB 오류라면 SQL·테이블명·접속 정보,
SMTP 오류라면 서버 응답이 그대로 클라이언트에 갔다.
이제 예외는 추적 정보와 함께 **로그에만** 남기고, 응답에는 일반 메시지와 로그를 찾을 참조 ID 만 준다.
의도한 검증 메시지("host_id is required" 등)는 그대로다.
"""
import json
import logging
import re

import pytest

SECRET = 'SECRET-DETAIL relation "mw_server" password=hunter2'
REF = re.compile(r'\(ref: ([0-9a-f]{8})\)')


def _boom(*args, **kwargs):
    raise RuntimeError(SECRET)


def _assert_generic(resp, caplog, key):
    assert resp.status_code == 500
    body = resp.get_json()
    assert SECRET not in json.dumps(body, ensure_ascii=False)
    m = REF.search(body[key])
    assert m, body
    # 로그에는 참조 ID 와 원래 예외가 함께 남는다 — 운영자가 찾을 수 있어야 한다
    assert m.group(1) in caplog.text
    assert SECRET in caplog.text


def test_internal_error_helper(app, caplog):
    from app.api.errors import internal_error
    with app.test_request_context(), caplog.at_level(logging.ERROR):
        try:
            _boom()
        except RuntimeError:
            resp, status = internal_error('context', key='error')
    resp.status_code = status
    _assert_generic(resp, caplog, 'error')


def test_markdown_to_html(client, auth_headers, monkeypatch, caplog):
    monkeypatch.setattr('app.api.common_api.convert_md_to_html', _boom)
    with caplog.at_level(logging.ERROR):
        resp = client.post('/api/v1/markdown/to_html', json={'content': '# x'}, headers=auth_headers)
    _assert_generic(resp, caplog, 'error')


def test_email_send_failure(client, auth_headers, monkeypatch, caplog):
    # send_mail 은 예외 대신 (False, str(e)) 를 돌려준다
    monkeypatch.setattr('app.api.common_api.send_mail', lambda **kw: (False, SECRET))
    with caplog.at_level(logging.ERROR):
        resp = client.post('/api/v1/email/send', json={
            'sender_name': 's', 'receivers': 'a@example.com', 'subject': 's', 'content': 'c'},
            headers=auth_headers)
    _assert_generic(resp, caplog, 'error')


def test_batch_run(client, auth_headers, monkeypatch, caplog):
    import app.sqls.batch as batch
    monkeypatch.setitem(batch.batch_function_registry, 'zz_boom', 'test')
    monkeypatch.setattr(batch, 'zz_boom', _boom, raising=False)
    with caplog.at_level(logging.ERROR):
        resp = client.post('/api/v1/batch/run/zz_boom', json={}, headers=auth_headers)
    _assert_generic(resp, caplog, 'message')


def test_itam_run_all(client, monkeypatch, caplog):
    # @has_access — 세션 로그인 클라이언트로 부른다
    monkeypatch.setattr('app.api.itam_compare_api.run_all_compare', _boom)
    with caplog.at_level(logging.ERROR):
        resp = client.post('/api/v1/itam-compare/run-all')
    _assert_generic(resp, caplog, 'message')


@pytest.fixture
def server_row(client, auth_headers):
    """edit/delete 대상 — 실제로 만들고 끝나면 지운다."""
    host_id = 'zz-internal-error-test'
    client.post('/api/v1/mw_server/add', data=json.dumps({'host_id': host_id}), headers=auth_headers)
    yield host_id
    client.delete(f'/api/v1/mw_server/delete/{host_id}', headers=auth_headers)


# app/sqls/server.py 가 내부 오류를 (None, str(e)) 로 돌려주던 경로
def test_server_add_internal_error(client, auth_headers, monkeypatch, caplog):
    monkeypatch.setattr('app.sqls.server._update_server_fields', _boom)
    with caplog.at_level(logging.ERROR):
        resp = client.post('/api/v1/mw_server/add', data=json.dumps({'host_id': 'zz-never-created'}),
                           headers=auth_headers)
    _assert_generic(resp, caplog, 'message')


def test_server_edit_internal_error(client, auth_headers, server_row, monkeypatch, caplog):
    monkeypatch.setattr('app.sqls.server._update_server_fields', _boom)
    with caplog.at_level(logging.ERROR):
        resp = client.put(f'/api/v1/mw_server/edit/{server_row}', data=json.dumps({}), headers=auth_headers)
    _assert_generic(resp, caplog, 'message')


def test_server_delete_internal_error(client, auth_headers, server_row, monkeypatch, caplog):
    import app.sqls.server as server
    monkeypatch.setattr(server.db.session, 'delete', _boom)
    with caplog.at_level(logging.ERROR):
        resp = client.delete(f'/api/v1/mw_server/delete/{server_row}', headers=auth_headers)
    _assert_generic(resp, caplog, 'message')


def test_validation_messages_are_kept(client, auth_headers):
    resp = client.post('/api/v1/mw_server/add', data=json.dumps({}), headers=auth_headers)
    assert resp.status_code == 400
    assert resp.get_json()['message'] == 'host_id is required'
