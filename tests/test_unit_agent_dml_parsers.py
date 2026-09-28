"""Agent 결과 텍스트 파서 단위 테스트 (WS-5-7 2차).

`AutorunResult` 의 파싱 보조 메서드들. 전부 `self` 를 쓰지 않으므로
인스턴스 없이 호출한다. 입력은 **에이전트가 보내온 텍스트**다.

1차와 같은 특성화 테스트다 — 관찰한 현재 동작을 고정한다.
"""
from datetime import datetime

import pytest

from app.sqls.agent_dml import AutorunResult

pytestmark = pytest.mark.unit

parse_filtered = AutorunResult._parse_filtered_info
parse_webtob_license = AutorunResult._parse_webtob_license_info
ssl_datetime = AutorunResult._get_ssl_datetime


# --- _parse_filtered_info : 'key: value' 중 관심 있는 두 개만 골라낸다 -------

def test_filtered_info_picks_known_keys_and_lowercases_them():
    result = parse_filtered(None, 'domain: d1\nApplication_Home: /opt/app\n')

    assert result == {'domain': 'd1', 'application_home': '/opt/app'}


def test_filtered_info_ignores_unknown_keys_and_plain_lines():
    result = parse_filtered(None, 'domain: d1\nwhatever: x\n소음\n')

    assert result == {'domain': 'd1'}


def test_filtered_info_splits_on_the_first_colon_only():
    """값에 콜론이 들어 있어도 잘리지 않는다."""
    result = parse_filtered(None, 'application_home: C:/opt/app\n')

    assert result == {'application_home': 'C:/opt/app'}


def test_filtered_info_returns_empty_dict_when_nothing_matches():
    assert parse_filtered(None, 'domain\n') == {}


# --- _parse_webtob_license_info ---------------------------------------------

LICENSE_TEXT = (
    'domain: host1__8080\n'
    'Edition: STANDARD\n'
    'License issue date: 2026/01/31\n'
    'License check by hostname: yes\n'
    'CPU license 4 cores\n'
)


def test_webtob_license_is_parsed_into_typed_fields():
    result = parse_webtob_license(None, LICENSE_TEXT)

    assert result == {
        'host_id': 'host1',
        'port': 8080,                                    # int
        'edition': 'STANDARD',
        'license issue date': datetime(2026, 1, 31),     # datetime
        'license check by hostname': 'yes',
        'cpu': 4,                                        # int, 'CPU license' 줄에서
    }


def test_webtob_license_bad_date_becomes_none_rather_than_failing():
    result = parse_webtob_license(None, 'domain: h__1\nLicense issue date: 31-01-2026\n')

    assert result['license issue date'] is None


def test_webtob_license_domain_is_matched_case_sensitively_unlike_the_others():
    """**비일관**: `domain` 만 대소문자를 가린다.

    수집 대상 판정은 `tlist[0].lower() in item_names` 로 **소문자로 낮춰서** 하는데,
    분해 분기만 `elif tlist[0] == 'domain'` 으로 **원문과 비교**한다.
    그래서 `Domain:` 은 분해되지 않고 통째로 `{'domain': ...}` 이 된다.

    호출부(`update_webtob_license_info`)는 `host_id` 가 없으면
    `'No data found'` 로 끝내므로, 대문자로 오면 **조용히 무시된다.**
    """
    lower = parse_webtob_license(None, 'domain: h__1\n')
    upper = parse_webtob_license(None, 'Domain: h__1\n')

    assert lower == {'host_id': 'h', 'port': 1}
    assert upper == {'domain': 'h__1'}        # 분해되지 않음 → host_id 없음


@pytest.mark.parametrize('domain_line, exc', [
    ('domain: host1\n', ValueError),        # '__' 구분자 없음
    ('domain: a__b__c\n', ValueError),      # 구분자가 둘
    ('domain: h__abc\n', ValueError),       # 포트가 숫자가 아님
], ids=['no-separator', 'two-separators', 'non-numeric-port'])
def test_webtob_license_malformed_domain_raises(domain_line, exc):
    """`domain` 행이 예상 형태가 아니면 **예외가 그대로 올라간다.**

    입력은 에이전트가 보내온 텍스트이고 호출부에 방어가 없다.
    날짜 파싱이 `try/except` 로 None 을 돌려주는 것과 대비된다.
    """
    with pytest.raises(exc):
        parse_webtob_license(None, domain_line)


# --- _get_ssl_datetime : 인증서 유효기간 문자열 → datetime ------------------

def test_ssl_datetime_gmt_is_shifted_to_kst():
    """`GMT` 표기는 **+9시간** 해서 KST 로 맞춘다."""
    notbefore, notafter = ssl_datetime(None, {
        'notbefore': 'Mon Jan  1 00:00:00 GMT 2026',
        'notafter': 'Tue Jan  1 00:00:00 GMT 2027',
    })

    assert notbefore == datetime(2026, 1, 1, 9, 0)
    assert notafter == datetime(2027, 1, 1, 9, 0)


def test_ssl_datetime_kst_is_taken_as_is():
    """`GMT` 가 아니면 `KST` 로 간주하고 그대로 쓴다."""
    notbefore, notafter = ssl_datetime(None, {
        'notbefore': 'Mon Jan  1 00:00:00 KST 2026',
        'notafter': 'Tue Jan  1 00:00:00 KST 2027',
    })

    assert notbefore == datetime(2026, 1, 1, 0, 0)
    assert notafter == datetime(2027, 1, 1, 0, 0)


def test_ssl_datetime_rejects_an_unparseable_string():
    with pytest.raises(ValueError):
        ssl_datetime(None, {'notbefore': 'bad', 'notafter': 'bad'})
