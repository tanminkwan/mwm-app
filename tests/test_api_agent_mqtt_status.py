"""Agent MQTT 수신 상태 — 폴링 저장·대시보드·Agent 목록 (HOWTO_019).

- 폴링(GET /api/v1/command/<agent_id>)의 X-Mqtt-Status 헤더를 ag_agent 에 저장한다
- 헤더가 없어지면 비운다 → MQTT 모수에서 빠진다
- BOOT 는 건드리지 않는다
- 모수 = 승인 ∧ OnLine ∧ 헤더 있음
"""
from datetime import datetime, timedelta

import pytest

from app import db
from app.models.agent import AgAgent
from app.models.common import LocationEnum, YnEnum

PREFIX = 'pytest-mqtt-'
POLL = '/api/v1/command/{}'
BOOT = '/api/v1/command/{}/0000.0010.0001/JAVAAGENT/BOOT'
MQTT_COLUMNS = ('mqtt_state', 'mqtt_since', 'mqtt_events',
                'mqtt_last_msg', 'mqtt_reason', 'mqtt_raw')


def _cleanup():
    db.session.query(AgAgent).filter(AgAgent.agent_id.like(PREFIX + '%')).delete(
        synchronize_session=False)
    db.session.commit()


@pytest.fixture
def make_agent(app):
    """테스트 Agent 를 만든다. 끝나면 지운다 (이전 실행이 남긴 것도 먼저 지운다)."""
    with app.app_context():
        _cleanup()

    def _make(name, approved=True, online=True, landscape='PROD', **mqtt):
        with app.app_context():
            checked = datetime.now() if online else datetime.now() - timedelta(hours=1)
            rec = AgAgent(agent_id=PREFIX + name, agent_name=name,
                          agent_type='JAVAAGENT', ip_address='192.0.2.1',
                          landscape=LocationEnum[landscape],
                          approved_yn=YnEnum.YES if approved else YnEnum.NO,
                          last_checked_date=checked, user_id='pytest', **mqtt)
            db.session.add(rec)
            db.session.commit()
            return rec.agent_id

    yield _make

    with app.app_context():
        _cleanup()


def _row(app, agent_id):
    with app.app_context():
        rec = db.session.query(AgAgent).filter_by(agent_id=agent_id).one()
        return {c: getattr(rec, c) for c in MQTT_COLUMNS}


def _poll(client, auth_headers, agent_id, status=None, url=POLL):
    headers = dict(auth_headers)
    if status is not None:
        headers['X-Mqtt-Status'] = status
    return client.get(url.format(agent_id), headers=headers)


# --- 폴링 저장 ----------------------------------------------------------------

def test_poll_with_header_stores_status(app, client, auth_headers, make_agent):
    aid = make_agent('store')
    raw = 'unstable;since=1790664000;events=3;reason=rc=32109 Connection lost'

    res = _poll(client, auth_headers, aid, raw)

    assert res.status_code == 200
    assert res.get_json()['return_code'] == 1
    row = _row(app, aid)
    assert row['mqtt_state'] == 'unstable'
    assert row['mqtt_since'] == datetime.fromtimestamp(1790664000)
    assert row['mqtt_events'] == 3
    assert row['mqtt_reason'] == 'rc=32109 Connection lost'
    assert row['mqtt_raw'] == raw


def test_header_disappears_clears_status(app, client, auth_headers, make_agent):
    aid = make_agent('vanish')
    _poll(client, auth_headers, aid, 'connected;since=1790660594;events=0')
    assert _row(app, aid)['mqtt_state'] == 'connected'

    res = _poll(client, auth_headers, aid)

    assert res.status_code == 200
    assert _row(app, aid) == {c: None for c in MQTT_COLUMNS}


def test_boot_does_not_touch_status(app, client, auth_headers, make_agent):
    aid = make_agent('boot', mqtt_state='connected', mqtt_events=0)

    res = _poll(client, auth_headers, aid, url=BOOT)

    assert res.status_code == 200
    assert _row(app, aid)['mqtt_state'] == 'connected'


def test_v4_non_boot_poll_updates_status(app, client, auth_headers, make_agent):
    """구버전 경로(command_v4)로 주기 폴링해도 헤더 규칙은 같다."""
    aid = make_agent('v4', mqtt_state='connected')
    url = '/api/v1/command/{}/0000.0010.0001/JAVAAGENT/RUNNING'

    _poll(client, auth_headers, aid, url=url)

    assert _row(app, aid)['mqtt_state'] is None


def test_unapproved_agent_is_not_stored(app, client, auth_headers, make_agent):
    aid = make_agent('unapproved', approved=False)

    res = _poll(client, auth_headers, aid, 'connected;events=0')

    assert res.get_json()['return_code'] == -2
    assert _row(app, aid)['mqtt_state'] is None


def test_garbage_header_still_answers_poll(app, client, auth_headers, make_agent):
    """헤더가 망가져도 명령 폴링은 정상 응답한다 — 명령 수신이 더 중요하다."""
    aid = make_agent('garbage')

    res = _poll(client, auth_headers, aid, 'é\x7f;since=;;events=-1;=')

    assert res.status_code == 200
    assert res.get_json()['return_code'] == 1
    assert _row(app, aid)['mqtt_state'] == 'unknown'


# --- 대시보드 -----------------------------------------------------------------

@pytest.fixture
def population(make_agent):
    """모수 판정용 Agent 들. 대상은 앞의 셋뿐이다."""
    now = datetime.now()
    return {
        'ok':      make_agent('ok', mqtt_state='connected', mqtt_events=0,
                              mqtt_since=now - timedelta(hours=2)),
        'shaky':   make_agent('shaky', mqtt_state='unstable', mqtt_events=3,
                              mqtt_since=now - timedelta(minutes=10),
                              mqtt_reason='<script>alert(1)</script>'),
        'dev':     make_agent('dev', landscape='DEV', mqtt_state='not_started',
                              mqtt_reason='start_failed'),
        'offline': make_agent('offline', online=False, mqtt_state='connected'),
        'plain':   make_agent('plain'),
        'unappr':  make_agent('unappr', approved=False, mqtt_state='connected'),
    }


def _ours(items):
    return [i for i in items if i['agent_id'].startswith(PREFIX)]


def test_mqtt_agent_stat_counts_only_online_approved_with_header(client, population):
    res = client.get('/monitor/mqtt_agent_stat')

    assert res.status_code == 200
    body = res.get_json()
    agents = _ours(body['mqtt_agents'])
    assert {a['agent_id'] for a in agents} == {
        population['ok'], population['shaky'], population['dev']}

    stat = {s['landscape']: s for s in body['mqtt_stat']}
    assert stat['PROD']['connected'] >= 1 and stat['PROD']['unstable'] >= 1
    assert stat['DEV']['not_started'] >= 1


def test_mqtt_agent_list_is_warning_first(client, population):
    agents = _ours(client.get('/monitor/mqtt_agent_stat').get_json()['mqtt_agents'])

    assert [a['state'] for a in agents] == ['unstable', 'not_started', 'connected']
    shaky = agents[0]
    assert shaky['events'] == 3
    assert shaky['reason'] == '<script>alert(1)</script>'   # JSON 은 원문, 화면이 이스케이프
    assert shaky['last_msg'] is None


def test_mqtt_agent_stat_requires_login(anon_client):
    res = anon_client.get('/monitor/mqtt_agent_stat')
    assert res.status_code in (302, 401, 403)


# --- Agent 목록 ---------------------------------------------------------------

def _list(client, query):
    res = client.get('/agentmodelview/list/?' + query)
    assert res.status_code == 200
    return res.get_data(as_text=True)


def test_agent_list_shows_mqtt_badge_and_escapes_reason(client, population):
    html = _list(client, f'_flt_0_agent_id={PREFIX}')

    assert 'mqtt-badge' in html
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html


def test_agent_list_mqtt_filter_keeps_only_mqtt_agents(client, population):
    html = _list(client, f'_flt_0_agent_id={PREFIX}&_flt_7_mqtt_state=-')

    for key in ('ok', 'shaky', 'dev', 'offline', 'unappr'):
        assert population[key] in html
    assert population['plain'] not in html


def test_agent_model_badge_only_for_online_approved(app, population):
    with app.app_context():
        recs = {r.agent_id: r for r in db.session.query(AgAgent)
                .filter(AgAgent.agent_id.like(PREFIX + '%'))}
        assert 'mqtt-badge' in str(recs[population['ok']].c_mqtt_status())
        for key in ('offline', 'plain', 'unappr'):
            assert str(recs[population[key]].c_mqtt_status()) == ''


def test_dashboard_has_mqtt_cards_and_escapes_in_js(client):
    """대시보드는 카드 2개를 두고, Agent 값을 escHtml 로 넣는다 (따옴표 포함)."""
    html = client.get('/').get_data(as_text=True)

    assert 'id="mqtt-stat-card"' in html and 'id="mqtt-agent-card"' in html
    assert '/monitor/mqtt_agent_stat' in html
    assert "\"'\": '&#39;'" in html
    assert 'escHtml(a.reason' in html
