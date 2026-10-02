"""SSL 인증서 적용 현황 — 모수·대상·적용 여부·API·화면 (HOWTO_021 §4)."""
from datetime import date, datetime

import pytest

from app import db
from app.models.common import LocationEnum, YnEnum
from app.models.was import (MwEtcSslDomain, MwServer, MwSslCertFile, MwWeb, MwWebDomain,
                            MwWebVhost)
from app.sqls.monitor import get_cert_expiry_stat
from app.sqls.ssl_cert import cn_of, get_ssl_cert_apply, parse_certificate
from tests._certs import chain, make_cert, pem

HOST = 'pytest-sslapply'
NAME = 'pt-apply-'
CN = 'www.pt-apply.co.kr'
BULK = '*.pt-apply.com.kr'
EXPIRY = datetime(2027, 12, 1, 8, 59, 59)       # tests._certs 기본 만료일의 KST
OTHER = datetime(2026, 12, 1, 8, 59, 59)
API = '/api/v1/monitor/ssl_cert_apply/{}'


def _cleanup():
    db.session.query(MwSslCertFile).filter(MwSslCertFile.cert_name.like(NAME + '%')).delete(
        synchronize_session=False)
    db.session.query(MwEtcSslDomain).filter(MwEtcSslDomain.host_id.like(HOST + '%')).delete(
        synchronize_session=False)
    for web in db.session.query(MwWeb).filter(MwWeb.host_id.like(HOST + '%')):
        db.session.delete(web)          # vhost·domain 은 FK CASCADE
    db.session.flush()
    db.session.query(MwServer).filter(MwServer.host_id.like(HOST + '%')).delete(
        synchronize_session=False)
    db.session.commit()


def _web(host, port, landscape, use_yn, domains):
    web = MwWeb(host_id=host, port=port, jsv_port=port + 1, landscape=LocationEnum[landscape],
                use_yn=use_yn, user_id='pytest')
    db.session.add(web)
    db.session.flush()
    vhost = MwWebVhost(mw_web_id=web.id, vhost_id='vh1', user_id='pytest')
    db.session.add(vhost)
    db.session.flush()
    for i, d in enumerate(domains):
        db.session.add(MwWebDomain(host_id=host, mw_web_vhost_id=vhost.id, domain_name=d.get('name', f'd{i}.pt'),
                                   port=str(443 + i), ssl_yn=d.get('ssl_yn', YnEnum.YES),
                                   subject=d.get('subject'), notafter=d.get('notafter'),
                                   subject_ca=d.get('subject_ca'), notafter_ca=d.get('notafter_ca'),
                                   user_id='pytest'))


@pytest.fixture(scope='module')
def certs():
    return chain()


@pytest.fixture(scope='module')
def leaf(certs):
    return make_cert(CN, issuer=certs[1])[0]


@pytest.fixture
def data(app, certs):
    """WEB/ETC 도메인. 각 행의 기대 결과는 domain_name 에 적어 둔다."""
    with app.app_context():
        _cleanup()
        db.session.add(MwServer(host_id=HOST, landscape=LocationEnum.PROD, user_id='pytest'))
        db.session.add(MwServer(host_id=HOST + '-dev', landscape=LocationEnum.DEV, user_id='pytest'))
        db.session.flush()
        _web(HOST, 18080, 'PROD', YnEnum.YES, [
            dict(name='applied.pt', subject=f'CN={CN}, O=pytest', notafter=EXPIRY,
                 subject_ca='CN=pytest Intermediate CA', notafter_ca=EXPIRY),
            dict(name='slash-upper.pt', subject=f'/C=KR/O=pytest/CN={CN.upper()}', notafter=OTHER,
                 subject_ca='CN=old CA', notafter_ca=OTHER),
            dict(name='unknown.pt', subject=f'CN={CN}', notafter=None),
            dict(name='partial.pt', subject=f'CN={CN}.kr', notafter=EXPIRY),
            dict(name='no-ssl.pt', subject=f'CN={CN}', notafter=EXPIRY, ssl_yn=YnEnum.NO),
            dict(name='no-cn.pt', subject='No Valid Certificate.'),
            dict(name='bulk.pt', subject=f'CN={BULK}', notafter=EXPIRY),
            dict(name='bulk-host.pt', subject='CN=www.pt-apply.com.kr', notafter=EXPIRY),
        ])
        _web(HOST, 18090, 'PROD', YnEnum.NO, [
            dict(name='unused-web.pt', subject=f'CN={CN}', notafter=EXPIRY),
        ])
        db.session.add(MwEtcSslDomain(host_id=HOST + '-dev', domain_name='etc-applied.pt', port='8443',
                                      subject=f'CN={CN}', notafter=EXPIRY, use_yn=YnEnum.YES,
                                      user_id='pytest'))
        db.session.add(MwEtcSslDomain(host_id=HOST, domain_name='etc-unused.pt', port='8443',
                                      subject=f'CN={CN}', notafter=EXPIRY, use_yn=YnEnum.NO,
                                      user_id='pytest'))
        db.session.commit()

    def register(cert, name):
        with app.app_context():
            rec = MwSslCertFile(cert_name=NAME + name, file_name='x.pem', received_date=date(2026, 10, 1),
                                receiver_name='pytest', user_id='pytest', **parse_certificate(pem(cert)))
            db.session.add(rec)
            db.session.commit()
            return rec.id

    yield register

    with app.app_context():
        _cleanup()


def _apply(app, cert_id):
    with app.app_context():
        return get_ssl_cert_apply(cert_id)


def _mine(result):
    return {r['domain'].split(':')[0]: r for r in result['rows'] if r['host_id'].startswith(HOST)}


@pytest.mark.parametrize('subject, cn', [
    ('CN=a.co.kr, O=x', 'a.co.kr'),
    ('O=x, CN=a.co.kr', 'a.co.kr'),
    ('/C=KR/O=x/CN=a.co.kr', 'a.co.kr'),
    ('C=KR, O=x, CN = a.co.kr', 'a.co.kr'),
    ('CN=*.com.kr', '*.com.kr'),
    ('No Valid Certificate.', None),
    ('', None),
    (None, None),
])
def test_cn_of(subject, cn):
    assert cn_of(subject) == cn


def test_ca_target_count_equals_cert_expiry_stat_plus_etc(app, data, certs):
    """CA 대상 = 전체: WEB 은 cert_expiry_stat 모수와 같고, ETC 는 mw_etc_ssl_domain(use_yn=YES)."""
    result = _apply(app, data(certs[1][0], 'ca-count'))
    with app.app_context():
        web_total = get_cert_expiry_stat()[-1]['total']
        etc_total = db.session.query(MwEtcSslDomain).filter(MwEtcSslDomain.use_yn == YnEnum.YES).count()
    assert result['summary']['target'] == web_total + etc_total


def test_leaf_targets_and_status(app, data, leaf):
    result = _apply(app, data(leaf, 'leaf'))
    mine = _mine(result)
    assert set(mine) == {'applied.pt', 'slash-upper.pt', 'unknown.pt', 'etc-applied.pt'}
    assert mine['applied.pt']['status'] == '적용'
    assert mine['slash-upper.pt']['status'] == '미적용'
    assert mine['unknown.pt']['status'] == '미확인'
    assert mine['etc-applied.pt']['status'] == '적용'


def test_leaf_row_fields(app, data, leaf):
    mine = _mine(_apply(app, data(leaf, 'fields')))
    web, etc = mine['applied.pt'], mine['etc-applied.pt']
    assert web['source'] == 'WEB' and web['landscape'] == 'PROD'
    assert web['domain'] == 'applied.pt:443'
    assert web['notafter'] == '2027-12-01 08:59:59'
    assert web['subject'] == f'CN={CN}, O=pytest'
    assert etc['source'] == 'ETC' and etc['landscape'] == 'DEV'


def test_leaf_summary(app, data, leaf):
    result = _apply(app, data(leaf, 'summary'))
    rows = result['rows']
    summary = result['summary']
    assert summary['target'] == len(rows)
    assert summary['applied'] == sum(r['status'] == '적용' for r in rows)
    assert summary['not_applied'] == sum(r['status'] == '미적용' for r in rows)
    assert summary['unknown'] == sum(r['status'] == '미확인' for r in rows)
    assert 'population' not in summary      # 전체 모수는 보이지 않는다 — 대상이 모수다
    assert result['cert']['cn'] == CN
    assert result['cert']['notafter'] == '2027-12-01 08:59:59'


def test_rows_are_sorted_not_applied_first(app, data, leaf):
    statuses = [r['status'] for r in _apply(app, data(leaf, 'sort'))['rows']]
    order = {'미적용': 0, '미확인': 1, '적용': 2}
    assert statuses == sorted(statuses, key=order.get)


def test_bulk_matches_wildcard_cn_only(app, data, certs):
    cert, _ = make_cert(BULK, issuer=certs[1])
    mine = _mine(_apply(app, data(cert, 'bulk')))
    assert set(mine) == {'bulk.pt'}
    assert mine['bulk.pt']['status'] == '적용'


def test_like_wildcards_in_cn_are_literal(app, data, certs):
    # '_' 는 LIKE 의 한 글자 와일드카드다. 'www.pt-apply.co.kr' 행이 잡히면 안 된다
    cert, _ = make_cert('www.pt_apply.co.kr', issuer=certs[1])
    assert _mine(_apply(app, data(cert, 'underscore'))) == {}


def test_ca_targets_whole_population(app, data, certs):
    result = _apply(app, data(certs[1][0], 'ca'))
    mine = _mine(result)
    assert {'applied.pt', 'no-cn.pt', 'bulk.pt', 'etc-applied.pt'} <= set(mine)
    assert {'no-ssl.pt', 'unused-web.pt', 'etc-unused.pt'}.isdisjoint(mine)
    assert mine['applied.pt']['status'] == '적용'
    assert mine['applied.pt']['subject'] == 'CN=pytest Intermediate CA'
    assert mine['slash-upper.pt']['status'] == '미적용'
    assert mine['no-cn.pt']['status'] == '미확인'
    assert mine['etc-applied.pt']['status'] == '미확인'    # etc 행은 notafter_ca 가 없다


def test_unknown_cert(app):
    assert _apply(app, 999999999) is None


def test_api(client, data, leaf):
    cert_id = data(leaf, 'api')
    res = client.get(API.format(cert_id))
    assert res.status_code == 200
    body = res.get_json()
    assert set(body) >= {'cert', 'summary', 'rows'}
    assert body['cert']['cert_name'] == NAME + 'api'
    assert body['cert']['cert_type'] == 'LEAF'


def test_api_not_found(client):
    assert client.get(API.format(999999999)).status_code == 404


def test_api_requires_login(anon_client):
    assert anon_client.get(API.format(1)).status_code == 401


def test_page(client, data, leaf):
    cert_id = data(leaf, 'page')
    html = client.get(f'/sslcertapplyview/?cert_id={cert_id}').get_data(as_text=True)
    assert NAME + 'page' in html
    assert API.format('') in html
    assert '전체 모수' not in html
    assert "' / 대상 ' + s.target" in html


def test_page_requires_login(anon_client):
    assert anon_client.get('/sslcertapplyview/').status_code in (302, 401)
