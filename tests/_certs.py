"""테스트용 인증서를 만든다 (HOWTO_021). 인증서 파일은 저장소에 두지 않는다."""
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def _name(cn, org='pytest'):
    attrs = [x509.NameAttribute(NameOID.COUNTRY_NAME, 'KR'),
             x509.NameAttribute(NameOID.ORGANIZATION_NAME, org)]
    if cn is not None:
        attrs.append(x509.NameAttribute(NameOID.COMMON_NAME, cn))
    return x509.Name(attrs)


def make_cert(cn, ca=False, issuer=None, not_after=None, serial=None, basic_constraints=True):
    """(cert, key) 를 돌려준다. issuer=(cert, key) 가 없으면 자체 서명."""
    key = ec.generate_private_key(ec.SECP256R1())
    not_after = not_after or datetime(2027, 11, 30, 23, 59, 59, tzinfo=timezone.utc)
    subject = _name(cn)
    issuer_name, issuer_key = (issuer[0].subject, issuer[1]) if issuer else (subject, key)
    builder = (x509.CertificateBuilder()
               .subject_name(subject)
               .issuer_name(issuer_name)
               .public_key(key.public_key())
               .serial_number(serial or x509.random_serial_number())
               .not_valid_before(not_after - timedelta(days=365))
               .not_valid_after(not_after))
    if basic_constraints:
        builder = builder.add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    return builder.sign(issuer_key, hashes.SHA256()), key


def chain():
    """root → 중간 CA → leaf(CN=www.pytest.co.kr)."""
    root = make_cert('pytest Root CA', ca=True)
    ica = make_cert('pytest Intermediate CA', ca=True, issuer=root)
    leaf = make_cert('www.pytest.co.kr', issuer=ica)
    return root, ica, leaf


def pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def der(cert):
    return cert.public_bytes(serialization.Encoding.DER)


def key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
