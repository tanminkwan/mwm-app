"""내부 오류 응답 (CodeQL py/stack-trace-exposure).

예외 문구(DB 오류의 SQL·테이블명, SMTP 서버 응답 등)는 클라이언트에 주지 않는다.
**로그에는 추적 정보와 함께** 남기고, 응답에는 일반 메시지와 그 로그를 찾을 참조 ID 만 준다.

    except Exception:
        return internal_error('일괄 대사 실행 오류')                 # (jsonify, 500)

    except Exception:
        return None, internal_error_message('mwm add_server Error')  # (결과, 메시지) 를 돌려주는 함수에서

의도한 검증 메시지("host_id is required" 등)에는 쓰지 않는다 — 그대로 돌려준다.
반드시 except 블록 안에서 부른다 (현재 예외를 로그에 싣는다).
"""
import logging
import secrets

from flask import jsonify

from app.log_safe import log_safe

INTERNAL_ERROR = 'Internal Server Error'

log = logging.getLogger(__name__)


def internal_error_message(context, detail=None):
    """현재 예외를 참조 ID 와 함께 로그에 남기고, 클라이언트용 메시지를 돌려준다.

    예외 대신 실패 문구만 받은 경우(예: send_mail 의 (False, str(e)))는 detail 로 넘긴다.
    """
    ref = secrets.token_hex(4)
    if detail is None:
        log.exception('[ref: %s] %s', ref, log_safe(context))
    else:
        log.error('[ref: %s] %s: %s', ref, log_safe(context), log_safe(detail))
    return f'{INTERNAL_ERROR} (ref: {ref})'


def is_internal_error(message):
    return isinstance(message, str) and message.startswith(INTERNAL_ERROR)


def internal_error(context, key='message', status=500, detail=None):
    """internal_error_message 를 JSON 응답으로. (response, status) 를 돌려준다."""
    return jsonify({key: internal_error_message(context, detail)}), status
