"""`httpm_to_dict()` — WebTOB `http.m` 파서 단위 테스트 (WS-5-7).

## 왜 이 함수부터인가

`app/sqls/` 는 코드의 41% 를 차지하면서 라인 커버리지 13%, 분기 2% 다(TASK 5-4).
그중 `httpm_to_dict()` 는 **입력이 문자열, 출력이 dict 인 순수 함수**라
DB 없이 검증할 수 있다. 파서부터 시작한 이유다.

## 성격: 특성화 테스트

명세 문서가 없으므로 **"옳은 동작"이 아니라 "현재 동작"을 고정한다.**
결함으로 보이는 것도 그대로 고정하고 `결함:` 주석을 단다.
고칠 때 무엇이 바뀌는지 이 테스트가 보여준다.
"""
import pytest

from app.sqls.webtob_dml import httpm_to_dict

pytestmark = pytest.mark.unit


SAMPLE = '''*DOMAIN
sample_domain

*NODE
webhost1    WEBTOBDIR="/sw/webtob",
              SHMKEY = 54000,
              PORT = "15843",
              ERRORDOCUMENT = "400,401,403",
              #Options="IgnoreExpect100Continue",
              UpperDirRestrict = Y,
              LOGGING = "acc_node"

*VHOST
vhost1        PORT = "8080",
              HOSTNAME = "a.example.com",
              HOSTALIAS = "b.example.com, c.example.com",
              DOCROOT = "/docs"
vhost2        PORT = "8443",
              HOSTNAME = "d.example.com"

*SERVER
svr1          SVGNAME = grp1, MinProc = 1, MaxProc = 5   # trailing comment
'''


# --- 구조 -------------------------------------------------------------------

def test_categories_become_top_level_keys():
    """`*NODE` 같은 줄이 최상위 키가 되고, 값은 항목 dict 의 리스트다."""
    result = httpm_to_dict(SAMPLE)

    assert set(result) == {'NODE', 'VHOST', 'SERVER'}
    assert [type(v) for v in result.values()] == [list, list, list]


def test_domain_section_is_discarded():
    """`*DOMAIN` 은 통째로 버려진다.

    위치에 따른 동작은 `test_domain_section_is_discarded_wherever_it_appears` 참조.
    """
    result = httpm_to_dict(SAMPLE)

    assert 'DOMAIN' not in result
    assert not any('sample_domain' in str(v) for v in result.values())


def test_item_name_is_taken_from_the_unindented_token():
    """들여쓰지 않은 줄의 첫 토큰이 그 항목의 `NAME` 이 된다."""
    result = httpm_to_dict(SAMPLE)

    assert [v['NAME'] for v in result['VHOST']] == ['vhost1', 'vhost2']
    assert result['NODE'][0]['NAME'] == 'webhost1'


def test_keys_are_uppercased():
    """`UpperDirRestrict` → `UPPERDIRRESTRICT`. 원본 대소문자는 보존되지 않는다."""
    node = httpm_to_dict(SAMPLE)['NODE'][0]

    assert 'UPPERDIRRESTRICT' in node
    assert 'UpperDirRestrict' not in node
    assert node['UPPERDIRRESTRICT'] == 'Y'


# --- 값 처리 ----------------------------------------------------------------

def test_quoted_value_keeps_its_commas():
    """따옴표 안의 쉼표는 구분자로 쓰이지 않는다."""
    node = httpm_to_dict(SAMPLE)['NODE'][0]

    assert node['ERRORDOCUMENT'] == '400,401,403'


def test_only_four_keys_become_lists():
    """`VHOSTNAME` / `HOSTNAME` / `HOSTALIAS` / `LOGGING` 만 리스트가 된다.

    값이 하나뿐이어도 리스트다. 나머지는 전부 문자열이다.
    """
    result = httpm_to_dict(SAMPLE)

    assert result['NODE'][0]['LOGGING'] == ['acc_node']
    assert result['VHOST'][0]['HOSTNAME'] == ['a.example.com']
    assert result['VHOST'][0]['HOSTALIAS'] == ['b.example.com', 'c.example.com']
    assert result['VHOST'][0]['PORT'] == '8080'
    assert result['NODE'][0]['SHMKEY'] == '54000'


def test_item_without_any_value_yields_name_only():
    result = httpm_to_dict('*SVRGROUP\ngrp1\n')

    assert result == {'SVRGROUP': [{'NAME': 'grp1'}]}


# --- 주석과 줄 이음 ---------------------------------------------------------

def test_comments_are_stripped():
    """`#` 로 시작하는 줄과 줄 끝 주석 모두 사라진다."""
    result = httpm_to_dict(SAMPLE)

    assert 'OPTIONS' not in result['NODE'][0]
    assert result['SERVER'][0]['MAXPROC'] == '5'


def test_backslash_continuation_is_joined():
    result = httpm_to_dict('*NODE\nn1  PORT = 80, \\\n    DOCROOT = "/d"\n')

    assert result['NODE'][0] == {'PORT': '80', 'DOCROOT': '/d', 'NAME': 'n1'}


# --- 결함 -------------------------------------------------------------------

def test_first_line_quoted_value_loses_internal_spaces():
    """항목의 **첫 줄**에서는 따옴표 안쪽 공백이 사라진다. 이어지는 줄은 보존된다.

    `line.split()` 후 `''.join(...)` 으로 구분자 없이 다시 붙이기 때문이다.

    **문제 없음으로 판단했다 (2026-09-27).** 실제 `http.m` 을 파싱해 확인한 결과
    첫 줄에 공백 든 따옴표 값이 오는 곳은 `LOGGING.OPTION`("sync, env=!image" →
    "sync,env=!image", 옵션 목록이라 의미 동일)과 `SVRGROUP.VHOSTNAME`(리스트 키라
    분리 후 strip 되어 결과 동일)뿐이었다. **손상된 값 0건.**

    고칠 계획이 없으므로 이 테스트는 동작을 기록해 두는 용도다.
    같은 논거로 다시 수정을 제안하지 말 것 — TASK 5-7 §4.3 참조.
    """
    first_line = httpm_to_dict('*NODE\nn1  METHOD = "GET, POST", PORT = 80\n')
    continued = httpm_to_dict('*NODE\nn1  PORT = 80,\n    METHOD = "GET, POST"\n')

    assert first_line['NODE'][0]['METHOD'] == 'GET,POST'      # 공백 소실
    assert continued['NODE'][0]['METHOD'] == 'GET, POST'      # 공백 보존


@pytest.mark.parametrize('position', ['first', 'middle', 'last'])
def test_domain_section_is_discarded_wherever_it_appears(position):
    """`*DOMAIN` 은 위치와 도메인 이름에 관계없이 결과에서 빠진다.

    예전에는 `*DOMAIN` 을 섹션이 아니라 **건너뛸 한 줄**로 취급했다. 그래서 맨 앞이 아니면
    도메인 이름 줄이 **직전 섹션의 항목**으로 붙었고, 이를 막으려고 고객사 도메인 이름을
    건너뛰기 목록에 하드코딩했었다(WS-4-11). 이제 정식 섹션으로 파싱한 뒤 버린다.
    """
    domain = '*DOMAIN\nany_domain_name\n'
    node = '*NODE\nn1  PORT = 80\n'
    vhost = '*VHOST\nv1  PORT = 8080\n'
    content = {
        'first':  domain + node + vhost,
        'middle': node + domain + vhost,
        'last':   node + vhost + domain,
    }[position]

    assert httpm_to_dict(content) == {
        'NODE': [{'PORT': '80', 'NAME': 'n1'}],
        'VHOST': [{'PORT': '8080', 'NAME': 'v1'}],
    }


def test_domain_section_attributes_do_not_leak():
    """`*DOMAIN` 아래의 속성도 다른 섹션으로 새지 않는다."""
    content = '*NODE\nn1  PORT = 80\n*DOMAIN\ndom1  SECURITY = N\n'

    assert httpm_to_dict(content) == {'NODE': [{'PORT': '80', 'NAME': 'n1'}]}
