"""등록된 모든 화면이 열리는지 (특성화 — FAB·SQLAlchemy 메이저 업그레이드 안전망).

FAB 에 등록된 뷰마다 목록(list)·추가(add) 화면을 관리자로 연다. 서버 오류(5xx)가 나면 실패한다.
데이터가 거의 없는 테스트 DB 라 상세(show)·수정(edit)은 열지 않는다.
"""
import pytest
from flask_appbuilder import ModelView

# 업그레이드 전에도 이미 오류가 나던 화면 (기준선). 여기 있는 것은 이 테스트가 막지 않는다.
KNOWN_BROKEN = set()


def _urls(appbuilder):
    urls = []
    for view in appbuilder.baseviews:
        base = view.route_base
        if isinstance(view, ModelView):
            urls.append(f'{base}/list/')
            if 'can_add' in view.base_permissions:
                urls.append(f'{base}/add')
        elif getattr(view, 'default_view', None) and view.default_view != 'index':
            urls.append(f'{base}/{view.default_view}')
    return sorted(set(urls))


# 사용 중단 경고는 이 테스트의 관심사가 아니다 (다른 테스트가 오류로 막는다). 화면이 깨지는지만 본다
@pytest.mark.filterwarnings('ignore::DeprecationWarning')
def test_every_registered_view_renders(app, client):
    from app import appbuilder
    with app.app_context():
        urls = _urls(appbuilder)
    assert len(urls) > 50, urls   # 뷰 수집이 동작하는지

    broken = {}
    for url in urls:
        try:
            r = client.get(url)
        except Exception as e:   # TESTING 모드에서는 뷰 예외가 그대로 올라온다
            broken[url] = type(e).__name__
            continue
        if r.status_code >= 500:
            broken[url] = r.status_code
    print('checked %d urls' % len(urls))

    assert set(broken) - KNOWN_BROKEN == set(), broken
