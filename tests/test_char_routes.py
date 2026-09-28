"""특성화 테스트 — 화면 가용성과 제거된 라우트.

라우트 목록을 하드코딩하지 않는다. `app.url_map` 에서 런타임에 수집하므로
화면이 추가·제거되면 테스트가 자동으로 따라간다.
"""
import pytest

# 오픈소스 전환 때 제거한 라우트. 되살아나면 알아차려야 한다.
REMOVED_ROUTES = [
    '/monitor/agentOffsets',        # TASK 3-1 (Kafka offset 조회)
    '/monitor/agentOffsetList',     # TASK 3-1 §9 (Agent Health List 화면)
    '/monitor/sendDailyReport',     # TASK 3-9 (Daily Report)
    '/api/v1/dailyreport/',         # TASK 3-9
    '/gtgroupusersview/list/',      # TASK 3-2 (GitLab)
    '/api/v1/git/webhook',          # TASK 3-2
]


def _list_view_rules(app):
    return sorted({r.rule for r in app.url_map.iter_rules()
                   if r.rule.endswith('/list/') and 'GET' in r.methods})


def test_list_views_exist(app):
    """등록된 list view 가 있어야 한다. 0 이면 뷰 등록 자체가 깨진 것이다."""
    assert len(_list_view_rules(app)) >= 50


def test_all_list_views_render(app, client):
    """등록된 모든 list view 가 200 을 돌려준다.

    FAB 업그레이드 시 가장 먼저 깨지는 지점이다. 하나라도 실패하면
    어떤 화면인지 이름으로 드러난다.
    """
    failures = {}
    for rule in _list_view_rules(app):
        status = client.get(rule).status_code
        if status != 200:
            failures[rule] = status

    assert not failures, f'200 이 아닌 화면: {failures}'


def test_list_views_require_login(app, anon_client):
    """미인증 상태에서는 로그인으로 리다이렉트된다."""
    rule = _list_view_rules(app)[0]
    resp = anon_client.get(rule, follow_redirects=False)
    assert resp.status_code == 302
    assert '/login/' in resp.headers['Location']


@pytest.mark.parametrize('route', REMOVED_ROUTES)
def test_removed_routes_are_gone(app, route):
    """제거한 기능의 라우트가 되살아나지 않았는지 확인한다."""
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert route not in rules
