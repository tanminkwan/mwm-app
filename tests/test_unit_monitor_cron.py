"""`_is_now_in_any_cron_range()` 단위 테스트 (WS-5-7 2차).

WAS 상태 알림의 **점검 시간대 제외** 판정에 쓰인다.
`"<크론식>:<지속분>"` 을 쉼표나 줄바꿈으로 여러 개 나열하고,
현재 시각이 그중 한 구간에라도 들면 True 다.

`now` 를 인자로 받으므로 시각을 고정해 결정적으로 검증할 수 있다.
"""
from datetime import datetime

import pytest

from app.sqls.monitor import _is_now_in_any_cron_range

pytestmark = pytest.mark.unit

# 2026-09-28 은 월요일. 09:00 크론이 09:15 기준 직전 발화다.
MONDAY_0915 = datetime(2026, 9, 28, 9, 15)


def test_inside_the_window_is_true():
    """09:00 시작 + 30분 = 09:00~09:30. 09:15 는 그 안이다."""
    assert _is_now_in_any_cron_range('0 9 * * 1-5:30', MONDAY_0915) is True


def test_outside_the_window_is_false():
    """09:00 시작 + 10분 = 09:00~09:10. 09:15 는 이미 지났다."""
    assert _is_now_in_any_cron_range('0 9 * * 1-5:10', MONDAY_0915) is False


def test_window_is_measured_from_the_previous_firing():
    """직전 발화 시각부터 잰다.

    03:00 크론의 직전 발화는 당일 03:00 이고 60분 구간은 04:00 에 끝난다.
    09:15 는 포함되지 않는다.
    """
    assert _is_now_in_any_cron_range('0 3 * * *:60', MONDAY_0915) is False
    # 같은 크론이라도 구간이 길면 포함된다 (03:00 + 600분 = 13:00)
    assert _is_now_in_any_cron_range('0 3 * * *:600', MONDAY_0915) is True


def test_any_one_matching_entry_is_enough():
    """쉼표로 여러 개를 나열하면 **하나라도** 맞으면 True 다."""
    assert _is_now_in_any_cron_range(
        '0 9 * * 1-5:10, 0 3 * * *:600', MONDAY_0915) is True


def test_entries_may_be_separated_by_newlines():
    assert _is_now_in_any_cron_range(
        '0 9 * * 1-5:10\n0 3 * * *:600', MONDAY_0915) is True


def test_spaces_around_the_duration_are_tolerated():
    assert _is_now_in_any_cron_range('0 9 * * 1-5: 30', MONDAY_0915) is True


@pytest.mark.parametrize('value', ['', None], ids=['empty', 'none'])
def test_empty_expression_means_no_window(value):
    assert _is_now_in_any_cron_range(value, MONDAY_0915) is False


def test_missing_duration_raises_with_an_example_in_the_message():
    """지속 시간이 없으면 **예외**다. 조용히 False 를 돌려주지 않는다.

    설정 오타를 숨기지 않겠다는 선택이다.
    """
    with pytest.raises(ValueError, match=r"잘못된 형식"):
        _is_now_in_any_cron_range('0 9 * * 1-5', MONDAY_0915)


def test_malformed_cron_expression_propagates_from_croniter():
    """크론식 자체가 틀리면 croniter 의 예외가 그대로 올라온다."""
    with pytest.raises(Exception, match=r'(?i)columns'):
        _is_now_in_any_cron_range('nonsense:30', MONDAY_0915)
