"""테이블 이름 → 모델 조회 (`app.sqls.monitor`) — 범용 조회·수정 함수가 쓴다.

FAB 5 에서 `db.Model` 이 FAB 의 `Model` 이 아니게 되어 조회 대상이 비었다. 배치 작업
(`notify_was_abnormal_status`)이 매분 `KeyError: 'mw_was'` 로 실패했다. 테스트 스위트가 이 경로를 덮지 않아
운영 로그에서야 드러났다.
"""
from app.sqls.monitor import _get_table_dict, get_all_tables


def test_app_tables_are_registered(app):
    tables = _get_table_dict()

    for name in ('mw_was', 'mw_web', 'mw_server', 'ag_agent', 'ag_command_type', 'it_was'):
        assert name in tables, name
    assert len(get_all_tables()) > 40
