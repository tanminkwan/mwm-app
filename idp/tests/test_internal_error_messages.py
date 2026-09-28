"""IdP 오류 응답에 내부 예외 문구를 싣지 않는다 (CodeQL py/stack-trace-exposure).

| 경로 | 예전 |
| :--- | :--- |
| `POST /api/sync/<source>` 502 | SQLAlchemy 연결 오류 원문 — 원본 DB 의 호스트·포트·사용자 |
| 동기화 결과 `errors` | 행별 예외 원문 (SQL 등) |
| `/oauth/authorize` POST 실패 화면 | 모든 예외 원문 |

예외는 참조 ID 와 함께 로그에만 남긴다. 의도한 검증 메시지(`Username conflict: …` 등)는 그대로다.
"""
import logging
import re
from unittest.mock import patch

from app.repositories.user_repo import UserRepository
from app.services.sync_service import SyncService

SECRET = 'connection to server at "db.internal" (10.0.0.9), port 5432 failed: password for user "sync"'
REF = re.compile(r"\(ref: ([0-9a-f]{8})\)")

BAD_SOURCE = {"bad": {
    "description": "Bad", "db_uri": "postgresql://sync:pw@db.internal:5432/mw",
    "table": "users", "id_column": "id",
    "column_mapping": {"username": "username", "email": "email"},
    "filter": "", "sync_password": False, "auto_sync_interval_minutes": 0,
}}


def _assert_hidden(text, caplog):
    assert SECRET not in text
    m = REF.search(text)
    assert m, text
    assert m.group(1) in caplog.text and SECRET in caplog.text


def test_sync_connection_failure_hides_the_db_error(client, db, api_headers, caplog):
    with patch.object(SyncService, "get_sync_sources", return_value=BAD_SOURCE), \
         patch("app.services.sync_service.create_engine", side_effect=RuntimeError(SECRET)), \
         caplog.at_level(logging.ERROR):
        resp = client.post("/api/sync/bad", headers=api_headers)
    assert resp.status_code == 502
    _assert_hidden(resp.get_json()["error"], caplog)


def test_sync_query_failure_hides_the_db_error(client, db, api_headers, caplog):
    class Engine:
        def connect(self):
            raise RuntimeError(SECRET)
    with patch.object(SyncService, "get_sync_sources", return_value=BAD_SOURCE), \
         patch("app.services.sync_service.create_engine", return_value=Engine()), \
         caplog.at_level(logging.ERROR):
        resp = client.post("/api/sync/bad", headers=api_headers)
    assert resp.status_code == 502
    _assert_hidden(resp.get_json()["error"], caplog)


def test_unknown_source_message_is_kept(client, db, api_headers):
    resp = client.post("/api/sync/nope", headers=api_headers)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Unknown sync source: nope"


def test_per_row_internal_errors_are_hidden(app, db, caplog):
    rows = [(1, "u1", "u1@example.com")]

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql):
            class R:
                def fetchall(self):
                    return rows
            return R()

    class Engine:
        def connect(self):
            return Conn()

    with patch.object(SyncService, "get_sync_sources", return_value=BAD_SOURCE), \
         patch("app.services.sync_service.create_engine", return_value=Engine()), \
         caplog.at_level(logging.ERROR):
        service = SyncService(UserRepository())
        with patch.object(service.user_repo, "create", side_effect=RuntimeError(SECRET)):
            result = service.sync_users("bad")
    assert len(result["errors"]) == 1
    assert result["errors"][0].startswith("sync_id=1: ")
    _assert_hidden(result["errors"][0], caplog)


def test_authorize_failure_page_hides_the_error(client, db, sample_user, sample_oauth_client, caplog):
    with patch("app.services.oauth_service.OAuthService.create_authorization_code",
               side_effect=RuntimeError(SECRET)), caplog.at_level(logging.ERROR):
        resp = client.post("/oauth/authorize", data={
            "client_id": "test-client", "redirect_uri": "http://localhost/callback",
            "response_type": "code", "username": "testuser", "password": "TestPass123!"})
    assert resp.status_code == 500
    _assert_hidden(resp.get_data(as_text=True), caplog)


def test_authorize_validation_message_is_shown(client, db, sample_user, sample_oauth_client):
    resp = client.post("/oauth/authorize", data={
        "client_id": "test-client", "redirect_uri": "http://evil.example/cb",
        "response_type": "code", "username": "testuser", "password": "TestPass123!"})
    assert "Invalid redirect_uri" in resp.get_data(as_text=True)
