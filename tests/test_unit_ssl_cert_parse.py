"""SSL 인증서 파일 파싱 — parse_certificate (HOWTO_021 §3.4)."""
from datetime import datetime, timezone

import pytest

from app.models.common import SslCertTypeEnum
from app.sqls.ssl_cert import parse_certificate
from tests._certs import chain, der, key_pem, make_cert, pem

pytestmark = pytest.mark.unit


@pytest.fixture(scope='module')
def certs():
    return chain()


def test_pem_leaf(certs):
    _, ica, (leaf, _) = certs
    info = parse_certificate(pem(leaf))
    assert info['cert_type'] == SslCertTypeEnum.LEAF
    assert info['cn'] == 'www.pytest.co.kr'
    assert 'CN=www.pytest.co.kr' in info['subject']
    assert 'CN=pytest Intermediate CA' in info['issuer']
    assert info['serial'] == format(leaf.serial_number, 'X')


def test_der_leaf(certs):
    leaf = certs[2][0]
    assert parse_certificate(der(leaf))['cn'] == 'www.pytest.co.kr'


def test_intermediate_ca(certs):
    ica = certs[1][0]
    info = parse_certificate(pem(ica))
    assert info['cert_type'] == SslCertTypeEnum.CA
    assert info['cn'] == 'pytest Intermediate CA'


def test_no_basic_constraints_is_leaf(certs):
    cert, _ = make_cert('legacy.pytest.co.kr', issuer=certs[1], basic_constraints=False)
    assert parse_certificate(pem(cert))['cert_type'] == SslCertTypeEnum.LEAF


def test_bulk_wildcard_cn(certs):
    cert, _ = make_cert('*.com.kr', issuer=certs[1])
    assert parse_certificate(pem(cert))['cn'] == '*.com.kr'


def test_dates_are_kst_naive_seconds(certs):
    """Agent 수집값(_get_ssl_datetime: GMT + 9h, naive)과 같은 규칙 — 적용 여부 식별 키."""
    after = datetime(2027, 11, 30, 23, 59, 59, 999999, tzinfo=timezone.utc)
    cert, _ = make_cert('date.pytest.co.kr', issuer=certs[1], not_after=after)
    info = parse_certificate(pem(cert))
    assert info['notafter'] == datetime(2027, 12, 1, 8, 59, 59)
    assert info['notafter'].tzinfo is None
    assert info['notbefore'] == datetime(2026, 12, 1, 8, 59, 59)


@pytest.mark.parametrize('data, message', [
    (b'', '인증서'),
    (b'not a certificate', '인증서'),
    (b'-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n', '인증서'),
])
def test_garbage_is_rejected(data, message):
    with pytest.raises(ValueError, match=message):
        parse_certificate(data)


def test_chain_file_is_rejected(certs):
    _, ica, leaf = certs
    with pytest.raises(ValueError, match='1개'):
        parse_certificate(pem(leaf[0]) + pem(ica[0]))


def test_root_is_rejected(certs):
    with pytest.raises(ValueError, match='루트'):
        parse_certificate(pem(certs[0][0]))


def test_private_key_is_rejected(certs):
    leaf, key = certs[2]
    with pytest.raises(ValueError, match='개인키'):
        parse_certificate(pem(leaf) + key_pem(key))


def test_leaf_without_cn_is_rejected(certs):
    cert, _ = make_cert(None, issuer=certs[1])
    with pytest.raises(ValueError, match='CN'):
        parse_certificate(pem(cert))
