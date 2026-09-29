"""X-Mqtt-Status 헤더 파싱·집계 단위 테스트 (HOWTO_019 §2·§4.1·§5.1).

헤더는 Agent 가 명령 폴링(GET /api/v1/command/<agent_id>)에 싣는다.
형식: `state;key=value;...` — 첫 토큰이 state, 나머지는 첫 '=' 기준으로 나눈다.
"""
from datetime import datetime

import pytest

from app.mqtt.status import (
    COLUMNS,
    mqtt_columns,
    parse_mqtt_status,
    sort_key,
    summarize,
)

pytestmark = pytest.mark.unit

# 시계에 의존하지 않는다 (HOWTO_018 §4.3). 예시 epoch 보다 뒤인 고정 시각
NOW = datetime.fromtimestamp(1790670000)


def ts(epoch):
    return datetime.fromtimestamp(epoch)


# --- 계약 예시 (mwagent 가 준 4가지) ----------------------------------------

def test_connected_with_all_fields():
    raw = 'connected;since=1790660594;events=0;last_msg=1790660700'
    assert parse_mqtt_status(raw, NOW) == {
        'mqtt_state': 'connected',
        'mqtt_since': ts(1790660594),
        'mqtt_events': 0,
        'mqtt_last_msg': ts(1790660700),
        'mqtt_reason': None,
        'mqtt_raw': raw,
    }


def test_unstable_reason_keeps_equals_sign():
    """reason 값 안의 '=' 는 값의 일부다 — 첫 '=' 에서만 나눈다."""
    raw = 'unstable;since=1790664000;events=3;reason=rc=32109 Connection lost'
    got = parse_mqtt_status(raw, NOW)
    assert got['mqtt_state'] == 'unstable'
    assert got['mqtt_since'] == ts(1790664000)
    assert got['mqtt_events'] == 3
    assert got['mqtt_reason'] == 'rc=32109 Connection lost'
    assert got['mqtt_last_msg'] is None


def test_never_connected_reason_with_several_equals():
    raw = ('never_connected;since=1790660654;events=2;'
           'reason=rc=0 Unable to connect to server cause=Connection refused')
    got = parse_mqtt_status(raw, NOW)
    assert got['mqtt_state'] == 'never_connected'
    assert got['mqtt_reason'] == 'rc=0 Unable to connect to server cause=Connection refused'


def test_not_started_has_reason_only():
    got = parse_mqtt_status('not_started;reason=mqtt_broker_address not set', NOW)
    assert got['mqtt_state'] == 'not_started'
    assert got['mqtt_reason'] == 'mqtt_broker_address not set'
    assert got['mqtt_since'] is None
    assert got['mqtt_events'] is None
    assert got['mqtt_last_msg'] is None


def test_state_only():
    got = parse_mqtt_status('connected', NOW)
    assert got['mqtt_state'] == 'connected'
    assert got['mqtt_since'] is None and got['mqtt_events'] is None


# --- 헤더 없음 / 비어 있음 ----------------------------------------------------

@pytest.mark.parametrize('raw', [None, '', '   ', ';', ' ; ; '],
                         ids=['none', 'empty', 'spaces', 'semicolon', 'blank-tokens'])
def test_absent_or_blank_is_none(raw):
    assert parse_mqtt_status(raw, NOW) is None


def test_mqtt_columns_absent_clears_every_column():
    """헤더가 없어지면 6개 컬럼을 모두 비운다 → MQTT 모수에서 빠진다 (HOWTO_019 §3)."""
    assert mqtt_columns(None, NOW) == {c: None for c in COLUMNS}


def test_mqtt_columns_present_equals_parse():
    raw = 'connected;since=1790660594;events=0'
    assert mqtt_columns(raw, NOW) == parse_mqtt_status(raw, NOW)


def test_columns_are_the_six_in_howto():
    assert COLUMNS == ('mqtt_state', 'mqtt_since', 'mqtt_events',
                       'mqtt_last_msg', 'mqtt_reason', 'mqtt_raw')


# --- state 정규화 ------------------------------------------------------------

def test_state_is_case_insensitive_and_trimmed():
    assert parse_mqtt_status('  Connected ;events=0', NOW)['mqtt_state'] == 'connected'


def test_unknown_state_is_kept_as_unknown_with_raw():
    raw = 'reconnecting;since=1790660594;events=1'
    got = parse_mqtt_status(raw, NOW)
    assert got['mqtt_state'] == 'unknown'
    assert got['mqtt_raw'] == raw
    # 아는 필드는 그대로 읽는다
    assert got['mqtt_events'] == 1


def test_first_token_with_equals_is_unknown_state():
    """state 가 빠지고 key=value 로 시작하면 모르는 state 로 본다."""
    got = parse_mqtt_status('since=1790660594;events=1', NOW)
    assert got['mqtt_state'] == 'unknown'


# --- 필드 검증 ---------------------------------------------------------------

@pytest.mark.parametrize('value', ['abc', '-5', '1.5', '', '99999999999999999999', '²'],
                         ids=['text', 'negative', 'float', 'empty', 'overflow', 'unicode-digit'])
def test_bad_since_becomes_none(value):
    got = parse_mqtt_status(f'connected;since={value};events=0', NOW)
    assert got['mqtt_since'] is None
    assert got['mqtt_events'] == 0


def test_since_far_in_future_becomes_none():
    """지금보다 1일 넘게 미래면 믿지 않는다 (Agent 시계 오류)."""
    future = int(NOW.timestamp()) + 86400 + 60
    assert parse_mqtt_status(f'connected;since={future}', NOW)['mqtt_since'] is None


def test_since_slightly_in_future_is_kept():
    """서버·Agent 시계가 조금 어긋나는 것은 허용한다."""
    soon = int(NOW.timestamp()) + 30
    assert parse_mqtt_status(f'connected;since={soon}', NOW)['mqtt_since'] == ts(soon)


@pytest.mark.parametrize('value', ['x', '-1', '2.0', '', '²', '2147483648'],
                         ids=['text', 'negative', 'float', 'empty', 'unicode-digit', 'over-int32'])
def test_bad_events_becomes_none(value):
    assert parse_mqtt_status(f'unstable;events={value}', NOW)['mqtt_events'] is None


def test_events_at_int32_max_is_kept():
    assert parse_mqtt_status('unstable;events=2147483647', NOW)['mqtt_events'] == 2147483647


def test_bad_last_msg_becomes_none():
    assert parse_mqtt_status('connected;last_msg=soon', NOW)['mqtt_last_msg'] is None


def test_reason_is_cut_to_120():
    got = parse_mqtt_status('unstable;reason=' + 'x' * 200, NOW)
    assert got['mqtt_reason'] == 'x' * 120


def test_empty_reason_is_none():
    assert parse_mqtt_status('unstable;reason=', NOW)['mqtt_reason'] is None


def test_raw_is_cut_to_300():
    raw = 'unstable;reason=' + 'x' * 500
    assert parse_mqtt_status(raw, NOW)['mqtt_raw'] == raw[:300]


def test_input_over_1024_chars_is_truncated_before_parsing():
    """아주 긴 헤더도 예외 없이 처리한다. 1024자 뒤의 필드는 버린다."""
    raw = 'connected;reason=' + 'x' * 2000 + ';events=5'
    got = parse_mqtt_status(raw, NOW)
    assert got['mqtt_state'] == 'connected'
    assert got['mqtt_events'] is None


def test_unknown_keys_are_ignored():
    got = parse_mqtt_status('connected;broker=tcp://x;events=0', NOW)
    assert got['mqtt_events'] == 0
    assert 'broker' not in got


def test_duplicate_key_last_wins():
    assert parse_mqtt_status('unstable;events=1;events=4', NOW)['mqtt_events'] == 4


def test_token_without_equals_is_ignored():
    assert parse_mqtt_status('connected;garbage;events=2', NOW)['mqtt_events'] == 2


def test_keys_and_values_are_trimmed():
    got = parse_mqtt_status('connected; events = 3 ; reason = hi ', NOW)
    assert got['mqtt_events'] == 3
    assert got['mqtt_reason'] == 'hi'


@pytest.mark.parametrize('raw', ['\x00\x01', '=;=;=', ';;;;connected', 'é;since=é'],
                         ids=['control', 'only-equals', 'leading-empty', 'non-ascii'])
def test_garbage_never_raises(raw):
    parse_mqtt_status(raw, NOW)  # 예외가 나지 않으면 된다


# --- 집계·정렬 (대시보드) ----------------------------------------------------

def test_summarize_counts_by_landscape_and_state():
    rows = [
        ('PROD', 'connected'), ('PROD', 'connected'), ('PROD', 'unstable'),
        ('DEV', 'not_started'), ('DEV', 'unknown'), (None, 'never_connected'),
    ]
    got = {r['landscape']: r for r in summarize(rows)}
    assert got['PROD'] == {'landscape': 'PROD', 'total': 3, 'connected': 2, 'unstable': 1,
                           'never_connected': 0, 'not_started': 0, 'unknown': 0}
    assert got['DEV']['not_started'] == 1 and got['DEV']['unknown'] == 1
    assert got['DEV']['total'] == 2
    # landscape 가 없으면 기존 agent_stat 과 같이 'NON'
    assert got['NON']['never_connected'] == 1


def test_summarize_unexpected_state_counts_as_unknown():
    got = summarize([('PROD', 'total'), ('PROD', 'landscape')])[0]
    assert got['total'] == 2 and got['unknown'] == 2 and got['landscape'] == 'PROD'


def test_summarize_empty():
    assert summarize([]) == []


def test_sort_key_puts_warnings_first_then_oldest_since():
    rows = [
        ('connected', ts(1790660000)),
        ('unknown', None),
        ('not_started', None),
        ('unstable', ts(1790669000)),
        ('unstable', ts(1790661000)),
        ('never_connected', ts(1790662000)),
    ]
    ordered = sorted(rows, key=lambda r: sort_key(*r))
    assert ordered == [
        ('unstable', ts(1790661000)),
        ('unstable', ts(1790669000)),
        ('never_connected', ts(1790662000)),
        ('not_started', None),
        ('unknown', None),
        ('connected', ts(1790660000)),
    ]
