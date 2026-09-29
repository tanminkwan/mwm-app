"""Agent 가 보내는 MQTT 수신 상태 (`X-Mqtt-Status` 헤더) 파싱·집계 (HOWTO_019).

Agent 는 명령 폴링(GET /api/v1/command/<agent_id>)에 헤더를 싣는다.

    X-Mqtt-Status: connected;since=1790660594;events=0;last_msg=1790660700
    X-Mqtt-Status: unstable;since=1790664000;events=3;reason=rc=32109 Connection lost

첫 토큰이 state, 나머지는 **첫 '=' 기준** key/value 다 (reason 값에 '=' 가 들어간다).
헤더는 신뢰할 수 없는 입력이다 — 여기 함수는 예외를 내지 않는다.
DB·Flask 에 의존하지 않는다 (단위 테스트: tests/test_unit_mqtt_status.py).
"""
from datetime import datetime, timedelta

# ag_agent 컬럼. 헤더가 없으면 모두 None 으로 비운다 → MQTT 모수에서 빠진다
COLUMNS = ('mqtt_state', 'mqtt_since', 'mqtt_events',
           'mqtt_last_msg', 'mqtt_reason', 'mqtt_raw')

CONNECTED = 'connected'
UNKNOWN = 'unknown'
# 목록 정렬 순서이기도 하다 — 경고 먼저, 정상은 마지막
WARNING_STATES = ('unstable', 'never_connected', 'not_started')
KNOWN_STATES = (CONNECTED,) + WARNING_STATES
STATES = WARNING_STATES + (UNKNOWN, CONNECTED)

MAX_INPUT = 1024
MAX_REASON = 120
MAX_RAW = 300
# Agent 시계가 이만큼 넘게 미래면 믿지 않는다
MAX_CLOCK_SKEW = timedelta(days=1)


def _is_count(value):
    # '²' 처럼 isdigit() 이 참인데 int() 가 실패하는 유니코드 숫자를 막는다
    return value.isascii() and value.isdigit()


def _epoch(value, now):
    if not _is_count(value):
        return None
    try:
        t = datetime.fromtimestamp(int(value))
    except (OverflowError, OSError, ValueError):
        return None
    return None if t > now + MAX_CLOCK_SKEW else t


# ag_agent.mqtt_events 는 INTEGER — 넘으면 UPDATE 가 실패해 폴링 응답까지 깨진다
MAX_EVENTS = 2**31 - 1


def _count(value):
    if not _is_count(value):
        return None
    n = int(value)
    return n if n <= MAX_EVENTS else None


def parse_mqtt_status(raw, now):
    """헤더 원문 → ag_agent 컬럼 dict. 헤더가 없거나 비어 있으면 None."""
    if raw is None:
        return None
    text = raw.strip()[:MAX_INPUT]
    tokens = [t.strip() for t in text.split(';')]
    if not any(tokens):
        return None

    state = tokens[0].lower()
    fields = {}
    for token in tokens[1:]:
        key, sep, value = token.partition('=')
        if sep:
            fields[key.strip()] = value.strip()

    reason = fields.get('reason', '')[:MAX_REASON]
    return {
        'mqtt_state': state if state in KNOWN_STATES else UNKNOWN,
        'mqtt_since': _epoch(fields.get('since', ''), now),
        'mqtt_events': _count(fields.get('events', '')),
        'mqtt_last_msg': _epoch(fields.get('last_msg', ''), now),
        'mqtt_reason': reason or None,
        'mqtt_raw': text[:MAX_RAW],
    }


def mqtt_columns(raw, now):
    """폴링 한 번에 저장할 값. 헤더가 없으면 6개 모두 None (MQTT 비대상)."""
    return parse_mqtt_status(raw, now) or dict.fromkeys(COLUMNS)


def summarize(rows):
    """(landscape, state) 목록 → landscape 별 state 수. landscape 가 없으면 'NON'."""
    stat = {}
    for landscape, state in rows:
        key = landscape or 'NON'
        s = stat.setdefault(key, dict(landscape=key, total=0, **dict.fromkeys(KNOWN_STATES + (UNKNOWN,), 0)))
        s['total'] += 1
        s[state if state in KNOWN_STATES else UNKNOWN] += 1
    return list(stat.values())


def sort_key(state, since):
    """경고 먼저(STATES 순), 같은 state 안에서는 since 오래된 순. since 없으면 뒤로."""
    rank = STATES.index(state) if state in STATES else STATES.index(UNKNOWN)
    return (rank, since is None, since or datetime.min)
