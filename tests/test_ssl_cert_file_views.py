"""SSL 인증서 파일 화면 — 등록(추출)·수정(이름만)·삭제 (HOWTO_021 §2, §3).

S3 는 띄우지 않는다. 파일 내용은 load_ag_file_bytes 를 바꿔 넣는다.
"""
from datetime import date, datetime

import pytest

from app import db
from app.models.agent import AgFile
from app.models.common import SslCertTypeEnum
from app.models.was import MwSslCertFile
from tests._certs import chain, make_cert, pem

NAME = 'pt-'          # cert_name 은 30byte 이내라 접두어를 짧게 둔다
FILE = 'pytest-sslcert-'
ADD = '/sslcertfilemodelview/add'


def _cleanup():
    db.session.query(MwSslCertFile).filter(MwSslCertFile.cert_name.like(NAME + '%')).delete(
        synchronize_session=False)
    db.session.query(AgFile).filter(AgFile.file_name.like(FILE + '%')).delete(
        synchronize_session=False)
    db.session.commit()


@pytest.fixture(scope='module')
def certs():
    return chain()


@pytest.fixture
def ag_file(app, monkeypatch):
    """ag_file 행을 만들고, 그 파일의 내용을 content 로 돌려주게 한다."""
    with app.app_context():
        _cleanup()
    contents = {}
    monkeypatch.setattr('app.sqls.ssl_cert.load_ag_file_bytes', lambda f: contents[f.id])

    def _make(content, name='leaf.pem', version='0000.0000.0001'):
        with app.app_context():
            rec = AgFile(agent_type='JAVAAGENT', file=f'uuid_sep_{FILE}{name}',
                         file_version=version, user_id='pytest')
            db.session.add(rec)
            db.session.commit()
            contents[rec.id] = content
            return rec.id

    yield _make

    with app.app_context():
        _cleanup()


def _add(client, file_id, name, received='2026-10-01', receiver='홍길동'):
    return client.post(ADD, data={'ag_file': file_id, 'cert_name': name,
                                  'received_date': received, 'receiver_name': receiver},
                       follow_redirects=True)


def _rows(app):
    with app.app_context():
        return db.session.query(MwSslCertFile).filter(
            MwSslCertFile.cert_name.like(NAME + '%')).order_by(MwSslCertFile.id).all()


def test_add_extracts_leaf(app, client, ag_file, certs):
    leaf = certs[2][0]
    file_id = ag_file(pem(leaf))
    res = _add(client, file_id, NAME + '2026.11-EV-bank')
    assert res.status_code == 200

    [row] = _rows(app)
    assert row.cert_type == SslCertTypeEnum.LEAF
    assert row.cn == 'www.pytest.co.kr'
    assert row.notafter == datetime(2027, 12, 1, 8, 59, 59)
    assert row.serial == format(leaf.serial_number, 'X')
    assert row.file_name == FILE + 'leaf.pem'
    assert row.ag_file_id == file_id
    assert row.received_date == date(2026, 10, 1)
    assert row.receiver_name == '홍길동'
    assert row.user_id


def test_add_extracts_intermediate(app, client, ag_file, certs):
    _add(client, ag_file(pem(certs[1][0]), name='ica.pem'), NAME + 'ica')
    [row] = _rows(app)
    assert row.cert_type == SslCertTypeEnum.CA


def test_add_bulk(app, client, ag_file, certs):
    cert, _ = make_cert('*.com.kr', issuer=certs[1])
    _add(client, ag_file(pem(cert)), NAME + '2026.12-bulk')
    [row] = _rows(app)
    assert row.cn == '*.com.kr'


def test_extract_failure_shows_error_and_saves_nothing(app, client, ag_file):
    res = _add(client, ag_file(b'not a certificate'), NAME + 'bad')
    assert '인증서 파일이 아니거나' in res.get_data(as_text=True)
    assert _rows(app) == []


def test_chain_file_is_rejected(app, client, ag_file, certs):
    res = _add(client, ag_file(pem(certs[2][0]) + pem(certs[1][0])), NAME + 'chain')
    assert '1개짜리 파일만' in res.get_data(as_text=True)
    assert _rows(app) == []


@pytest.mark.parametrize('name, ok', [
    (NAME + '가' * 9, True),      # 3 + 27 = 30 byte
    (NAME + '가' * 10, False),    # 3 + 30 = 33 byte (13 글자)
    (NAME + 'a' * 27, True),      # 30 byte
    (NAME + 'a' * 28, False),     # 31 byte
])
def test_name_is_limited_to_30_bytes(app, client, ag_file, certs, name, ok):
    _add(client, ag_file(pem(certs[2][0])), name)
    assert len(_rows(app)) == (1 if ok else 0)


def test_duplicate_name_is_rejected(app, client, ag_file, certs):
    file_id = ag_file(pem(certs[2][0]))
    _add(client, file_id, NAME + 'dup')
    _add(client, file_id, NAME + 'dup')
    assert len(_rows(app)) == 1


def test_same_certificate_twice_with_other_names(app, client, ag_file, certs):
    file_id = ag_file(pem(certs[2][0]))
    _add(client, file_id, NAME + 'one')
    _add(client, file_id, NAME + 'two')
    assert len(_rows(app)) == 2


@pytest.mark.parametrize('field', ['received_date', 'receiver_name', 'ag_file'])
def test_required_fields(app, client, ag_file, certs, field):
    data = {'ag_file': ag_file(pem(certs[2][0])), 'cert_name': NAME + 'req',
            'received_date': '2026-10-01', 'receiver_name': '홍길동'}
    data[field] = ''
    client.post(ADD, data=data, follow_redirects=True)
    assert _rows(app) == []


def test_add_form_lists_files_by_name(client, ag_file, certs):
    ag_file(pem(certs[2][0]), name='leaf.pem', version='0000.0000.0007')
    html = client.get(ADD).get_data(as_text=True)
    assert f'{FILE}leaf.pem (0000.0000.0007)' in html


def test_edit_changes_name_only(app, client, ag_file, certs):
    _add(client, ag_file(pem(certs[2][0])), NAME + 'before')
    [before] = _rows(app)

    form = client.get(f'/sslcertfilemodelview/edit/{before.id}').get_data(as_text=True)
    assert 'name="cert_name"' in form
    for other in ('receiver_name', 'received_date', 'ag_file', 'cn', 'notafter'):
        assert f'name="{other}"' not in form

    client.post(f'/sslcertfilemodelview/edit/{before.id}',
                data={'cert_name': NAME + 'after', 'receiver_name': '변경', 'cn': 'evil'},
                follow_redirects=True)
    [after] = _rows(app)
    assert after.cert_name == NAME + 'after'
    assert after.receiver_name == '홍길동'
    assert after.cn == before.cn
    assert after.notafter == before.notafter


def test_edit_name_is_limited_to_30_bytes(app, client, ag_file, certs):
    _add(client, ag_file(pem(certs[2][0])), NAME + 'keep')
    [row] = _rows(app)
    client.post(f'/sslcertfilemodelview/edit/{row.id}', data={'cert_name': NAME + '가' * 10},
                follow_redirects=True)
    assert _rows(app)[0].cert_name == NAME + 'keep'


def test_list_and_show(app, client, ag_file, certs):
    _add(client, ag_file(pem(certs[2][0])), NAME + 'listed')
    [row] = _rows(app)
    listing = client.get('/sslcertfilemodelview/list/').get_data(as_text=True)
    assert NAME + 'listed' in listing
    assert 'www.pytest.co.kr' in listing
    show = client.get(f'/sslcertfilemodelview/show/{row.id}').get_data(as_text=True)
    assert 'CN=pytest Intermediate CA' in show


def test_delete(app, client, ag_file, certs):
    _add(client, ag_file(pem(certs[2][0])), NAME + 'gone')
    [row] = _rows(app)
    client.post(f'/sslcertfilemodelview/delete/{row.id}', follow_redirects=True)
    assert _rows(app) == []


def test_deleting_ag_file_keeps_certificate(app, client, ag_file, certs):
    file_id = ag_file(pem(certs[2][0]))
    _add(client, file_id, NAME + 'orphan')
    with app.app_context():
        db.session.query(AgFile).filter_by(id=file_id).delete()
        db.session.commit()
    [row] = _rows(app)
    assert row.ag_file_id is None
    assert row.file_name == FILE + 'leaf.pem'


def test_anonymous_cannot_list(anon_client):
    res = anon_client.get('/sslcertfilemodelview/list/')
    assert res.status_code in (302, 401)
