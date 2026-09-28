"""내부 오류 메시지 (CodeQL py/stack-trace-exposure) — 본 앱 app/api/errors.py 와 같은 규칙.

예외 문구(SQLAlchemy 오류의 SQL·접속 대상, 라이브러리 내부 메시지)는 클라이언트에 주지 않는다.
로그에는 추적 정보와 함께 남기고, 응답에는 일반 메시지와 그 로그를 찾을 참조 ID 만 준다.
의도한 검증 메시지(`ValueError("Username already exists: …")` 등)에는 쓰지 않는다.
반드시 except 블록 안에서 부른다 (현재 예외를 로그에 싣는다).
"""
import logging
import secrets

from app.log_safe import log_safe

INTERNAL_ERROR = "Internal Server Error"

log = logging.getLogger(__name__)


def internal_error_message(context):
    ref = secrets.token_hex(4)
    log.exception("[ref: %s] %s", ref, log_safe(context))
    return f"{INTERNAL_ERROR} (ref: {ref})"
