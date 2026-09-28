"""`get_real_web_host_id()` 단위 테스트 (WS-5-7 2차).

WebTOB 설정에 적힌 연결 대상이 실제로 어느 서버인지 판정한다.
루프백 표기는 요청한 쪽 호스트로, IP 는 조회로, 나머지는 그대로 쓴다.
"""
import pytest

from app.sqls import relationship

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('loopback', ['localhost', '127.0.0.1', '<domain-socket>'])
def test_loopback_forms_resolve_to_the_requesting_host(loopback):
    """루프백은 설정 파일을 가진 서버 자신을 뜻한다."""
    assert relationship.get_real_web_host_id(loopback, 'webhost1') == 'webhost1'


def test_a_plain_hostname_is_used_as_is():
    assert relationship.get_real_web_host_id('other-host', 'webhost1') == 'other-host'


def test_an_ipv4_address_is_looked_up(monkeypatch):
    """IPv4 형태면 `get_host_id()` 로 호스트명을 찾는다."""
    monkeypatch.setattr(relationship, 'get_host_id', lambda ip: f'resolved-{ip}')

    assert relationship.get_real_web_host_id('10.0.0.5', 'webhost1') == 'resolved-10.0.0.5'


def test_lookup_result_is_returned_even_when_it_is_none(monkeypatch):
    """조회에 실패해도 그대로 돌려준다. 호출 측이 None 을 처리해야 한다."""
    monkeypatch.setattr(relationship, 'get_host_id', lambda ip: None)

    assert relationship.get_real_web_host_id('10.0.0.5', 'webhost1') is None


def test_hostname_that_merely_contains_digits_is_not_treated_as_an_ip(monkeypatch):
    """IP 판정은 네 자리 점 표기 전체와 정확히 맞을 때만이다."""
    monkeypatch.setattr(relationship, 'get_host_id',
                        lambda ip: pytest.fail('조회가 일어나면 안 된다'))

    assert relationship.get_real_web_host_id('10.0.0.5.example.com', 'webhost1') \
        == '10.0.0.5.example.com'
