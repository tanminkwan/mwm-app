"""ITAM 대사 보조 함수 단위 테스트 (WS-5-7 2차).

`app/sqls/itam_compare.py` 의 값 정규화 3종.
1차(`test_unit_webtob_httpm.py`)와 같은 **특성화 테스트**다 —
관찰한 현재 동작을 고정한다.
"""
import pytest

from app.sqls.itam_compare import (
    _clean_port,
    _get_cleaned_was_id,
    _ssl_yn_matches,
)

pytestmark = pytest.mark.unit


# --- _ssl_yn_matches : ITAM 'Y'/'N' 과 미들웨어관리소 'YES'/'NO' 를 맞춘다 -----------

@pytest.mark.parametrize('itam, leebalso, expected', [
    ('Y', 'YES', True),
    ('N', 'NO', True),
    ('Y', 'NO', False),
    ('N', 'YES', False),
])
def test_ssl_yn_matches_pairs(itam, leebalso, expected):
    assert _ssl_yn_matches(itam, leebalso) is expected


@pytest.mark.parametrize('itam, leebalso', [('', ''), (None, None), ('X', 'MAYBE')])
def test_ssl_yn_treats_anything_not_y_or_yes_as_a_match(itam, leebalso):
    """판정은 `Y`/`YES` 인가 아닌가 두 갈래뿐이다.

    빈 값·None·알 수 없는 값은 전부 "SSL 아님"으로 묶여 서로 일치한다.
    """
    assert _ssl_yn_matches(itam, leebalso) is True


# --- _clean_port : 엑셀이 '15843.0' 으로 읽어오는 것을 되돌린다 --------------

@pytest.mark.parametrize('value, expected', [
    ('15843.0', '15843'),
    ('15843', '15843'),
    (' 8080 ', '8080'),
    (15843.0, '15843'),      # float 이 그대로 와도 문자열로 정규화된다
], ids=['str-with-.0', 'str-plain', 'str-padded', 'float'])
def test_clean_port_strips_the_excel_float_suffix(value, expected):
    assert _clean_port(value) == expected


@pytest.mark.parametrize('value', ['', None, 0])
def test_clean_port_returns_none_for_falsy_values(value):
    """**포트 0 도 None 이 된다.** 빈 값 검사가 falsy 기준이기 때문이다."""
    assert _clean_port(value) is None


def test_clean_port_only_strips_exactly_one_trailing_zero_decimal():
    """`.0` 만 떼어낸다. `.00` 은 그대로 남는다."""
    assert _clean_port('8080.00') == '8080.00'


# --- _get_cleaned_was_id : 환경 접미사를 떼어낸다 ----------------------------

@pytest.mark.parametrize('was_id, expected', [
    ('app_dev', 'app'),
    ('app_test', 'app'),
    ('app_A', 'app'),
    ('app_L', 'app'),
    ('app_N', 'app'),
    ('app', 'app'),          # 접미사 없음
])
def test_cleaned_was_id_strips_known_suffixes(was_id, expected):
    assert _get_cleaned_was_id(was_id) == expected


def test_cleaned_was_id_strips_only_one_suffix():
    """접미사가 겹쳐 있어도 **한 번만** 떼어낸다."""
    assert _get_cleaned_was_id('app_dev_test') == 'app_dev'


def test_cleaned_was_id_is_case_sensitive():
    """`_dev` 는 떼지만 `_DEV` 는 그대로 둔다."""
    assert _get_cleaned_was_id('app_DEV') == 'app_DEV'


@pytest.mark.parametrize('value', ['', None])
def test_cleaned_was_id_passes_falsy_values_through(value):
    assert _get_cleaned_was_id(value) == value
