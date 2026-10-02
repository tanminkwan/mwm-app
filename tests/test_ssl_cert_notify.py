"""SSL 인증서 만료 주의 메일 — [서버내부기능] notify_ssl_cert_expiry (HOWTO_021 §10).

남은 일수가 dday 중 하나와 같거나 last_dday 보다 작은 인증서를 골라
Markdown 지식으로 등록하고, 그 지식을 '이메일-MW' 태그의 주소로 보낸다.
"""
from datetime import date, datetime, time, timedelta

import pytest

from app import db
from app.models.common import SslCertTypeEnum
from app.models.knowledge import UtMdContent, UtTag
from app.models.was import MwSslCertFile
from app.sqls.batch import batch_function_registry, run_batch_by_scheduler
from app.sqls.ssl_cert import notify_ssl_cert_expiry, parse_notify_params, select_expiring_certs

NAME = 'pt-notify-'
TAG = '이메일-MW'
SUBJECT = '[SSL 인증서 만료 주의]'
PARAMS = '{"dday": [60, 30, 7], "last_dday": 3}'


def _cleanup():
    db.session.query(MwSslCertFile).filter(MwSslCertFile.cert_name.like(NAME + '%')).delete(
        synchronize_session=False)
    for doc in db.session.query(UtMdContent).filter(UtMdContent.content_name.like(SUBJECT + '%')):
        db.session.delete(doc)
    db.session.commit()


@pytest.fixture
def sent(app, monkeypatch):
    """보낸 메일을 모은다 (실제 SMTP 금지). 이메일-MW 태그를 테스트 값으로 둔다."""
    mails = []

    def _capture(host, port, sender, sender_name, receivers, subject, content, **kw):
        mails.append(dict(sender_name=sender_name, receivers=sorted(receivers), subject=subject, content=content))
        return True, 'OK'
    monkeypatch.setattr('app.views.knowledge.send_mail', _capture)

    with app.app_context():
        _cleanup()
        tag = db.session.query(UtTag).filter_by(tag=TAG).first()
        original = (tag.value1 if tag else None, tag is not None)
        if not tag:
            tag = UtTag(tag=TAG, user_id='pytest')
            db.session.add(tag)
        tag.value1 = 'mw1@example.com, mw2@example.com,'
        db.session.commit()

    yield mails

    with app.app_context():
        _cleanup()
        tag = db.session.query(UtTag).filter_by(tag=TAG).first()
        if original[1]:
            tag.value1 = original[0]
        else:
            db.session.delete(tag)
        db.session.commit()


@pytest.fixture
def cert(app):
    """남은 일수 days 인 인증서를 등록한다."""
    def _make(name, days, cn=None, notafter=None):
        with app.app_context():
            notafter = notafter or datetime.combine(date.today() + timedelta(days=days), time(23, 59, 59))
            db.session.add(MwSslCertFile(cert_name=NAME + name, file_name='x.pem', received_date=date.today(),
                                         receiver_name='pytest', cert_type=SslCertTypeEnum.LEAF,
                                         cn=cn or f'{name}.pt-notify.co.kr', subject=f'CN={name}',
                                         notafter=notafter, user_id='pytest'))
            db.session.commit()
    return _make


def _mine(app, dday, last_dday):
    with app.app_context():
        return {c.cert_name[len(NAME):]: days for c, days in select_expiring_certs(dday, last_dday)
                if c.cert_name.startswith(NAME)}


def _docs(app):
    with app.app_context():
        return db.session.query(UtMdContent).filter(UtMdContent.content_name.like(SUBJECT + '%')).all()


# ---- 파라미터 ---------------------------------------------------------------

def test_params():
    assert parse_notify_params(PARAMS) == ([60, 30, 7], 3)
    assert parse_notify_params('{"dday": [], "last_dday": 0}') == ([], 0)


@pytest.mark.parametrize('params', [
    '', 'not json', '[60, 30]', '{"dday": [60]}', '{"last_dday": 3}',
    '{"dday": 60, "last_dday": 3}', '{"dday": ["60"], "last_dday": 3}',
    '{"dday": [60], "last_dday": "3"}', '{"dday": [true], "last_dday": 3}',
])
def test_bad_params(params):
    with pytest.raises(ValueError, match='dday'):
        parse_notify_params(params)


# ---- 대상 고르기 -------------------------------------------------------------

def test_select_dday_match_and_below_last_dday(app, sent, cert):
    for name, days in [('d60', 60), ('d59', 59), ('d30', 30), ('d7', 7), ('d4', 4),
                       ('d3', 3), ('d2', 2), ('d0', 0), ('expired', -5)]:
        cert(name, days)
    assert _mine(app, [60, 30, 7], 3) == {'d60': 60, 'd30': 30, 'd7': 7, 'd2': 2, 'd0': 0}


def test_expired_certs_are_excluded(app, sent, cert):
    """만료된 인증서는 대상이 아니다 — 오늘 만료라도 이미 지난 시각이면 뺀다."""
    cert('expired-today', 0, notafter=datetime.now() - timedelta(minutes=1))
    cert('expired-long-ago', -400)
    cert('expires-later-today', 0, notafter=datetime.now() + timedelta(minutes=5))
    assert _mine(app, [60, 30, 7], 3) == {'expires-later-today': 0}


def test_select_is_sorted_by_days_left(app, sent, cert):
    cert('late', 30)
    cert('soon', 1)
    with app.app_context():
        days = [d for c, d in select_expiring_certs([30], 3) if c.cert_name.startswith(NAME)]
    assert days == [1, 30]


# ---- 실행 -------------------------------------------------------------------

def test_nothing_to_notify_does_nothing(app, sent, cert):
    cert('far', 100)
    with app.app_context():
        rtn, msg = notify_ssl_cert_expiry(PARAMS)
    assert rtn == 1 and '없' in msg
    assert sent == []
    assert _docs(app) == []


def test_registers_knowledge_and_mails_it(app, sent, cert):
    cert('ev-bank', 30, cn='www.pt-notify.co.kr')
    cert('bulk', 2, cn='*.pt-notify.com.kr')
    cert('far', 100)
    with app.app_context():
        rtn, msg = notify_ssl_cert_expiry(PARAMS)
    assert rtn == 1

    [doc] = _docs(app)
    md = doc.content_md
    assert NAME + 'ev-bank' in md and NAME + 'bulk' in md
    assert NAME + 'far' not in md
    assert (date.today() + timedelta(days=30)).strftime('%Y-%m-%d') in md
    assert '| 30 |' in md and '| 2 |' in md
    assert md.index(NAME + 'bulk') < md.index(NAME + 'ev-bank')       # 남은 일수 적은 것 먼저
    for header in ('만료일', '남은 일수', '적용', '미적용', '미확인', '대상'):
        assert header in md

    [mail] = sent
    assert mail['receivers'] == ['mw1@example.com', 'mw2@example.com']
    assert mail['subject'] == doc.content_name
    assert NAME + 'ev-bank' in mail['content']        # 지식(Markdown)을 HTML 로 바꿔 보낸다
    assert '<table' in mail['content']


def test_counts_come_from_apply_status(app, sent, cert, monkeypatch):
    cert('counted', 7)
    monkeypatch.setattr('app.sqls.ssl_cert.get_ssl_cert_apply', lambda cert_id: {
        'summary': {'target': 9, 'applied': 5, 'not_applied': 3, 'unknown': 1}})
    with app.app_context():
        notify_ssl_cert_expiry(PARAMS)
    [doc] = _docs(app)
    assert '| 5 | 3 | 1 | 9 |' in doc.content_md


def test_no_recipients_fails_without_knowledge(app, sent, cert):
    cert('d7', 7)
    with app.app_context():
        db.session.query(UtTag).filter_by(tag=TAG).one().value1 = ''
        db.session.commit()
        rtn, msg = notify_ssl_cert_expiry(PARAMS)
    assert rtn == 0 and TAG in msg
    assert sent == []
    assert _docs(app) == []


def test_mail_failure_is_reported(app, sent, cert, monkeypatch):
    cert('d7', 7)
    monkeypatch.setattr('app.views.knowledge.send_mail', lambda *a, **k: (False, 'smtp down'))
    with app.app_context():
        rtn, msg = notify_ssl_cert_expiry(PARAMS)
    assert rtn == 0 and 'smtp down' in msg
    assert len(_docs(app)) == 1       # 지식은 남는다 — 화면에서 다시 보낼 수 있다


# ---- [서버내부기능] 등록 ------------------------------------------------------

def test_registered_as_server_function():
    assert 'notify_ssl_cert_expiry' in batch_function_registry
    assert 'SSL' in batch_function_registry['notify_ssl_cert_expiry']


def test_runs_through_scheduler_entry(app, sent, cert):
    cert('d7', 7)
    rtn, msg = run_batch_by_scheduler('pytest-no-such-command', 'notify_ssl_cert_expiry', PARAMS)
    assert rtn == 1, msg
    assert len(sent) == 1


def test_scheduler_entry_without_params_fails(app, sent, cert):
    cert('d7', 7)
    rtn, msg = run_batch_by_scheduler('pytest-no-such-command', 'notify_ssl_cert_expiry', '')
    assert rtn == 0 and 'dday' in msg
    assert sent == []
