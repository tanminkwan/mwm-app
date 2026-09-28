"""JEUS 설정 파서 단위 테스트 — `_getJvmOptions()`, `_getDBparams()` (WS-5-7).

두 메서드 모두 `self` 를 쓰지 않는 순수 함수라 인스턴스 없이 호출한다
(`JeusDomain` 은 ABC 라 인스턴스화할 수 없다).

`test_unit_webtob_httpm.py` 와 같은 **특성화 테스트**다.
결함으로 보이는 동작도 그대로 고정하고 `결함:` 을 붙인다.
"""
import pytest

from app.sqls.jeus_dml import JeusDomain

pytestmark = pytest.mark.unit

get_jvm_options = JeusDomain._getJvmOptions
get_db_params = JeusDomain._getDBparams


# =============================================================================
# _getJvmOptions — (min_heap, max_heap, apm_type, 원본문자열) 을 돌려준다
# =============================================================================

def test_jvm_heap_sizes_are_parsed():
    min_heap, max_heap, apm, raw = get_jvm_options(None, '-Xms512m -Xmx2048m -Dfoo=bar')

    assert (min_heap, max_heap) == (512, 2048)
    assert apm == 'NONE'
    assert raw == '-Xms512m -Xmx2048m -Dfoo=bar'


def test_jvm_options_accept_a_list_and_join_with_newline():
    """리스트로 들어오면 개행으로 이어 붙인 문자열을 원본으로 돌려준다."""
    min_heap, max_heap, _, raw = get_jvm_options(None, ['-Xms1024m', '-Xmx4096m'])

    assert (min_heap, max_heap) == (1024, 4096)
    assert raw == '-Xms1024m\n-Xmx4096m'


def test_jvm_missing_heap_options_give_minus_one():
    assert get_jvm_options(None, '-Dfoo=bar')[:2] == (-1, -1)
    assert get_jvm_options(None, '')[:2] == (-1, -1)


@pytest.mark.parametrize('option, expected', [
    ('-javaagent:/opt/pharos.agent/x.jar', 'PHAROS'),
    ('-Djennifer.config=/opt/j.conf', 'JENNIFER'),
    ('-Dsomething.else=1', 'NONE'),
])
def test_jvm_apm_type_is_detected_from_the_option_string(option, expected):
    assert get_jvm_options(None, option)[2] == expected


@pytest.mark.parametrize('option, expected_mb', [
    ('-Xms2048m', 2048),
    ('-Xms2M', 2),
    ('-Xms2g', 2048),          # 1g = 1024m
    ('-Xms2G', 2048),
    ('-Xms1048576k', 1024),    # 1048576k = 1024m
    ('-Xms1t', 1024 * 1024),
])
def test_jvm_heap_units_are_converted_to_megabytes(option, expected_mb):
    """단위를 **환산**한다. 저장 단위는 MB 다 (TASK 5-7b).

    예전에는 마지막 한 글자를 잘라 버리기만 해서 `2g` 와 `2m` 이 똑같이 2 였다.
    """
    assert get_jvm_options(None, option)[0] == expected_mb


def test_jvm_heap_without_a_unit_is_read_as_bytes():
    """접미사가 없으면 JVM 규격대로 **바이트**로 읽는다.

    예전에는 마지막 숫자를 잘라 `-Xms512` 를 51 로 만들었다.
    512 바이트는 1MB 미만이므로 이제 0 이다.
    """
    assert get_jvm_options(None, '-Xms512 -Xmx2048')[:2] == (0, 0)
    assert get_jvm_options(None, f'-Xms{2 * 1024 ** 2}')[0] == 2


@pytest.mark.parametrize('option', ['-Xmsabc', '-Xms', '-Xms2gg', '-Xms1.5g'])
def test_jvm_heap_unparseable_values_give_minus_one(option):
    """해석할 수 없으면 조용히 틀린 값을 내지 않고 -1 을 돌려준다.

    소수점 표기(`1.5g`)는 JVM 도 받지 않는다.
    """
    assert get_jvm_options(None, option)[0] == -1


# =============================================================================
# _getDBparams — (서버명, 포트, DBMS ID) 를 돌려준다
# =============================================================================

RAC_URL = ('(DESCRIPTION=(ADDRESS_LIST='
           '(ADDRESS=(PROTOCOL=TCP)(HOST=db1.example.com)(PORT=1521))'
           '(ADDRESS=(PROTOCOL=TCP)(HOST=db2.example.com)(PORT=1521)))'
           '(CONNECT_DATA=(SERVICE_NAME=ORCL)))')


def test_db_params_single_host():
    assert get_db_params(
        None, '(ADDRESS=(HOST=db.example.com)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=ORCL))'
    ) == ('db.example.com', 1521, 'ORCL')


def test_db_params_multiple_hosts_are_joined_with_commas():
    """RAC 처럼 HOST 가 여러 개면 쉼표로 이어 붙인다. 포트는 **첫 번째만** 쓴다."""
    assert get_db_params(None, RAC_URL) == ('db1.example.com,db2.example.com', 1521, 'ORCL')


def test_db_params_are_case_insensitive():
    assert get_db_params(
        None, '(address=(host=db.example.com)(port=1521))(connect_data=(service_name=orcl))'
    ) == ('db.example.com', 1521, 'orcl')


def test_db_params_accept_database_name_as_well_as_service_name():
    assert get_db_params(
        None, '(HOST=db.example.com)(PORT=5432)(DATABASE_NAME=mydb)'
    ) == ('db.example.com', 5432, 'mydb')


def test_db_params_port_is_an_int_while_the_rest_are_strings():
    server, port, dbms = get_db_params(None, RAC_URL)

    assert isinstance(server, str) and isinstance(dbms, str)
    assert isinstance(port, int)


@pytest.mark.parametrize('db_property, expected', [
    # HOST 가 없으면 전부 None — 예외를 던지지 않는다
    ('jdbc:postgresql://db.example.com:5432/mydb', (None, None, None)),
    # 뒤쪽 항목만 없으면 거기서부터 None
    ('(HOST=db.example.com)', ('db.example.com', None, None)),
    ('(HOST=db.example.com)(PORT=1521)', ('db.example.com', 1521, None)),
])
def test_db_params_degrade_to_none_instead_of_raising(db_property, expected):
    """앞에서부터 순서대로 파싱하다 멈추며, 못 찾은 항목은 None 이다."""
    assert get_db_params(None, db_property) == expected
