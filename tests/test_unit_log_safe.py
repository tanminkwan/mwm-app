"""log_safe — 로그에 넣는 외부 값의 줄바꿈 이스케이프 (CodeQL py/log-injection)."""
import logging

import pytest

from app.log_safe import log_safe

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('value, expected', [
    ('plain', 'plain'),
    ('a\nINFO forged line', 'a\\nINFO forged line'),
    ('a\r\nb', 'a\\r\\nb'),
    (None, 'None'),
    (['x\ny'], "['x\\ny']"),
])
def test_log_safe(value, expected):
    assert log_safe(value) == expected


def test_internal_error_context_cannot_forge_a_log_line(caplog):
    from app.api.errors import internal_error_message
    with caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError('x')
        except RuntimeError:
            internal_error_message('batch zz\nCRITICAL forged')
    assert '\nCRITICAL forged' not in caplog.records[-1].getMessage()
