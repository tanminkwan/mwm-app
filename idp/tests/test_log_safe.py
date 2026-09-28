"""log_safe — 로그에 넣는 외부 값의 줄바꿈 이스케이프 (CodeQL py/log-injection)."""
import logging

from app.log_safe import log_safe


def test_log_safe_escapes_newlines():
    assert log_safe("u\nINFO forged\r") == "u\\nINFO forged\\r"


def test_created_username_cannot_forge_a_log_line(app, db, caplog):
    from app.repositories.user_repo import UserRepository
    from app.services.user_service import UserService
    with caplog.at_level(logging.INFO):
        UserService(UserRepository()).create_user("evil\nINFO admin logged in", "e@example.com", "LongPass123!")
    assert all("\nINFO admin" not in r.getMessage() for r in caplog.records)
