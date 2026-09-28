"""ITAM 엑셀 업로드의 헤더 → 컬럼 대응 (WS-4-6).

고객사 쪽 담당자 컬럼을 중립 이름(`cust_p_mngr` / `cust_s_mngr`)으로 바꾸면서 헤더 라벨도
`고객담당자(정/부)` 로 바꿨다. 예전 양식의 엑셀은 헤더 앞에 기관명이 붙어 있으므로,
정확히 일치하는 헤더가 없을 때는 **ITO 가 아닌 `…담당자(정)` / `…담당자(부)`** 를 고객 담당자로 받는다.
"""
import pytest

from app.sqls.itam_import import WAS_COLUMNS, WEB_COLUMNS, resolve_columns

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('mapping', [WAS_COLUMNS, WEB_COLUMNS], ids=['was', 'web'])
def test_exact_headers_map_to_columns(mapping):
    headers = ['구성번호', '고객담당자(정)', '고객담당자(부)', 'ITO담당자(정)', 'ITO담당자(부)']

    assert resolve_columns(headers, mapping) == {
        '구성번호': 'config_id',
        '고객담당자(정)': 'cust_p_mngr',
        '고객담당자(부)': 'cust_s_mngr',
        'ITO담당자(정)': 'ito_p_mngr',
        'ITO담당자(부)': 'ito_s_mngr',
    }


@pytest.mark.parametrize('mapping', [WAS_COLUMNS, WEB_COLUMNS], ids=['was', 'web'])
def test_org_prefixed_manager_headers_fall_back_to_customer_columns(mapping):
    """예전 양식: 기관명이 붙은 담당자 헤더도 고객 담당자로 받는다."""
    headers = ['구성번호', 'ABC담당자(정)', 'ABC담당자(부)', 'ITO담당자(정)']

    result = resolve_columns(headers, mapping)

    assert result['ABC담당자(정)'] == 'cust_p_mngr'
    assert result['ABC담당자(부)'] == 'cust_s_mngr'
    assert result['ITO담당자(정)'] == 'ito_p_mngr'


def test_exact_header_wins_over_fallback():
    """정확한 헤더가 있으면 대체 규칙은 쓰지 않는다 — 같은 컬럼을 두 번 덮어쓰지 않는다."""
    headers = ['고객담당자(정)', 'ABC담당자(정)']

    result = resolve_columns(headers, WAS_COLUMNS)

    assert result == {'고객담당자(정)': 'cust_p_mngr'}


def test_unknown_headers_are_ignored():
    assert resolve_columns(['구성번호', '비고', '담당팀장'], WAS_COLUMNS) == {'구성번호': 'config_id'}
