"""webInfo 인자 해석 — `_create_ssl_info` / `_create_domain_name_info` (app/sqls/webtob_dml.py).

두 함수는 배치 함수(createSslInfo)로 노출된다. 인자는 dict 이거나, 스케줄러·배치 API 를 거쳐
dict 리터럴 문자열(`"{'host_id': 'h1', 'port': '8080'}"`)로 들어온다.

예전에는 문자열을 `eval()` 했다 — `POST /api/v1/batch/run/createSslInfo` 에
`params: ["__import__('os').system(...)"]` 를 보내면 **서버에서 임의 코드가 실행됐다**
(CodeQL py/code-injection, critical).
리터럴만 해석하고, 코드는 실행하지 않아야 한다.
"""
import pytest

from app.sqls.webtob_dml import _create_domain_name_info, _create_ssl_info, _parse_web_info

pytestmark = pytest.mark.unit

# 아래 공격 문자열이 실행되면 여기에 값이 들어간다
EXECUTED = []
PAYLOAD = "__import__('tests.test_unit_webtob_web_info', fromlist=['x']).EXECUTED.append(1)"


@pytest.fixture(autouse=True)
def _clear():
    EXECUTED.clear()


def test_a_dict_is_used_as_is():
    info = {'host_id': 'h1', 'port': '8080'}
    assert _parse_web_info(info) is info


def test_a_dict_literal_string_is_parsed():
    assert _parse_web_info("{'host_id': 'h1', 'port': '8080'}") == {'host_id': 'h1', 'port': '8080'}


def test_code_in_the_string_is_not_executed():
    with pytest.raises(ValueError):
        _parse_web_info(PAYLOAD)
    assert EXECUTED == []


@pytest.mark.parametrize("value", ["['h1', '8080']", "'h1'", "8080"])
def test_a_literal_that_is_not_a_dict_is_rejected(value):
    with pytest.raises(ValueError):
        _parse_web_info(value)


@pytest.mark.parametrize("func", [_create_ssl_info, _create_domain_name_info])
def test_the_batch_entry_points_reject_code_without_running_it(func):
    # DB 에 닿기 전에 거절한다 — 그래서 단위 테스트로 돈다
    rtn, msg = func(PAYLOAD)
    assert rtn == 0
    assert msg
    assert EXECUTED == []
