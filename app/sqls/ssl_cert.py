"""SSL 인증서 파일 등록·적용 현황 (HOWTO_021)."""
import json
import logging
from datetime import date, datetime, timedelta, timezone

from cryptography import x509
from cryptography.x509.oid import NameOID

from app import db
from app.models.common import SslCertTypeEnum, YnEnum
from app.models.was import MwEtcSslDomain, MwServer, MwSslCertFile, MwWeb, MwWebDomain, MwWebVhost

# Agent 수집값(_get_ssl_datetime: GMT + 9h, naive)과 같은 규칙으로 저장한다 — 적용 여부를 만료일로 식별한다
KST = timezone(timedelta(hours=9))


def _kst_naive(dt):
    return dt.astimezone(KST).replace(tzinfo=None, microsecond=0)


def _load(data):
    if b'PRIVATE KEY-----' in data:
        raise ValueError('개인키가 들어 있는 파일은 등록할 수 없습니다.')
    try:
        if b'-----BEGIN' in data:
            return x509.load_pem_x509_certificates(data)
        return [x509.load_der_x509_certificate(data)]
    except ValueError:
        raise ValueError('인증서 파일이 아니거나 읽을 수 없는 형식입니다 (PEM/DER).')


def load_ag_file_bytes(ag_file):
    """ag_file 의 파일 내용을 S3 에서 읽는다 (agent_api.download_file 과 같은 방식)."""
    from app.file_manager.s3.filemanager import S3FileManager
    return S3FileManager().get_file(str(ag_file.file))


def extract_from_ag_file(ag_file):
    """ag_file 의 인증서 정보 + 파일 이름. 읽지 못하거나 등록할 수 없는 파일이면 ValueError."""
    try:
        data = load_ag_file_bytes(ag_file)
    except Exception:
        logging.exception('ssl cert file read failed: ag_file.id=%s', ag_file.id)
        raise ValueError('파일을 읽지 못했습니다.')
    info = parse_certificate(data)
    info['file_name'] = ag_file.file_name
    return info


def parse_certificate(data):
    """인증서 1개짜리 파일(PEM/DER)에서 정보를 뽑는다. 등록할 수 없는 파일이면 ValueError."""
    certs = _load(data or b'')
    if len(certs) != 1:
        raise ValueError(f'인증서가 {len(certs)}개 들어 있습니다. 인증서 1개짜리 파일만 등록할 수 있습니다.')
    cert = certs[0]

    try:
        is_ca = cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        is_ca = False
    if is_ca and cert.subject == cert.issuer:
        raise ValueError('루트 인증서는 등록 대상이 아닙니다.')

    cns = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = cns[0].value if cns else None
    if not is_ca and not cn:
        raise ValueError('CN 이 없는 leaf 인증서입니다.')

    return dict(
        cert_type=SslCertTypeEnum.CA if is_ca else SslCertTypeEnum.LEAF,
        subject=cert.subject.rfc4514_string(),
        cn=cn,
        serial=format(cert.serial_number, 'X'),
        issuer=cert.issuer.rfc4514_string(),
        notbefore=_kst_naive(cert.not_valid_before_utc),
        notafter=_kst_naive(cert.not_valid_after_utc),
    )


# ---------------------------------------------------------------------------
# 적용 현황 (HOWTO_021 §4)
# ---------------------------------------------------------------------------
STATUS_ORDER = {'미적용': 0, '미확인': 1, '적용': 2}
LANDSCAPE_ORDER = {'PROD': 0, 'TEST': 1, 'DEV': 2, 'DR': 3}


def cn_of(subject):
    """subject 의 CN 값. 'CN=a, O=b' 와 '/C=KR/CN=a' 둘 다 받는다. 없으면 None."""
    for part in (subject or '').replace('/', ',').split(','):
        key, sep, value = part.partition('=')
        if sep and key.strip().upper() == 'CN':
            return value.strip() or None
    return None


def _fmt(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None


def _web_query():
    """모수 WEB — get_cert_expiry_stat() 과 같은 조인·필터."""
    return db.session.query(MwWebDomain, MwWeb.landscape)\
        .join(MwWebVhost, MwWebDomain.mw_web_vhost_id == MwWebVhost.id)\
        .join(MwWeb, MwWebVhost.mw_web_id == MwWeb.id)\
        .filter(MwWeb.use_yn == YnEnum.YES, MwWebDomain.ssl_yn == YnEnum.YES)


def _etc_query():
    return db.session.query(MwEtcSslDomain, MwServer.landscape)\
        .outerjoin(MwServer, MwServer.host_id == MwEtcSslDomain.host_id)\
        .filter(MwEtcSslDomain.use_yn == YnEnum.YES)


def _like_escape(text):
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _status(current, expected):
    if current is None:
        return '미확인'
    return '적용' if current.replace(microsecond=0) == expected.replace(microsecond=0) else '미적용'


def get_ssl_cert_apply(cert_id):
    """인증서 하나의 적용 대상과 적용 여부. 없는 cert_id 면 None.

    LEAF: 현재 leaf CN == 파일 CN (대소문자 무시, 문자열 비교 — bulk 는 CN=*.com.kr 끼리). 만료일 notafter 로 식별
    CA:   모수 전체. 만료일 notafter_ca 로 식별
    """
    cert = db.session.get(MwSslCertFile, cert_id)
    if cert is None:
        return None
    is_leaf = cert.cert_type == SslCertTypeEnum.LEAF

    sources = (('WEB', MwWebDomain, _web_query()), ('ETC', MwEtcSslDomain, _etc_query()))
    rows = []
    for source, model, query in sources:
        if is_leaf:
            # 후보만 SQL 로 가져오고 CN 은 아래에서 정확히 비교한다 (cn 컬럼 없이 동적 파싱, §4.3)
            query = query.filter(model.subject.ilike(f'%{_like_escape(cert.cn)}%', escape='\\'))
        for rec, landscape in query:
            if is_leaf:
                if (cn_of(rec.subject) or '').lower() != cert.cn.lower():
                    continue
                subject, notafter = rec.subject, rec.notafter
            else:
                subject, notafter = rec.subject_ca, rec.notafter_ca
            rows.append(dict(
                source=source,
                landscape=landscape.name if landscape else None,
                host_id=rec.host_id,
                domain=f'{rec.domain_name}:{rec.port}',
                subject=subject,
                notafter=_fmt(notafter),
                status=_status(notafter, cert.notafter),
            ))

    rows.sort(key=lambda r: (STATUS_ORDER[r['status']], LANDSCAPE_ORDER.get(r['landscape'], 9), r['domain']))

    def count(status):
        return sum(r['status'] == status for r in rows)

    return dict(
        cert=dict(id=cert.id, cert_name=cert.cert_name, cert_type=cert.cert_type.name,
                  cn=cert.cn, notafter=_fmt(cert.notafter)),
        summary=dict(target=len(rows),
                     applied=count('적용'), not_applied=count('미적용'), unknown=count('미확인')),
        rows=rows,
    )


# ---------------------------------------------------------------------------
# 만료 주의 메일 — [서버내부기능] notify_ssl_cert_expiry (HOWTO_021 §10)
# ---------------------------------------------------------------------------
NOTIFY_TAG = '이메일-MW'
NOTIFY_SUBJECT = '[SSL 인증서 만료 주의]'


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def parse_notify_params(params):
    """'{"dday": [60, 30, 7], "last_dday": 3}' → ([60, 30, 7], 3). 형식이 틀리면 ValueError."""
    usage = '파라미터 형식: {"dday": [60, 30, 7], "last_dday": 3}'
    try:
        data = json.loads(params or '')
    except ValueError:
        raise ValueError(usage)
    dday = data.get('dday') if isinstance(data, dict) else None
    last_dday = data.get('last_dday') if isinstance(data, dict) else None
    if not isinstance(dday, list) or not all(_is_int(d) for d in dday) or not _is_int(last_dday):
        raise ValueError(usage)
    return dday, last_dday


def select_expiring_certs(dday, last_dday, today=None):
    """남은 일수가 dday 중 하나와 같거나 last_dday 보다 작은 인증서. [(cert, 남은 일수)], 남은 일수 순.

    만료된 인증서(만료 시각이 지금보다 이전)는 뺀다 — 오늘 만료라도 시각이 지났으면 대상이 아니다.
    """
    today = today or date.today()
    result = []
    for cert in db.session.query(MwSslCertFile).filter(MwSslCertFile.notafter > datetime.now()):
        days = (cert.notafter.date() - today).days
        if days in dday or days < last_dday:
            result.append((cert, days))
    return sorted(result, key=lambda item: (item[1], item[0].cert_name))


def _md_cell(text):
    return str(text if text is not None else '-').replace('|', '\\|')


def build_expiry_markdown(items, dday, last_dday, today):
    lines = [
        f'# SSL 인증서 만료 주의 ({today:%Y-%m-%d})',
        '',
        f'남은 일수가 {", ".join(map(str, dday)) or "-"} 일이거나 {last_dday} 일보다 적은 인증서입니다. '
        '적용 여부는 도메인의 현재 인증서 만료일로 판단합니다 (SSL 인증서 적용 현황 화면과 같음).',
        '',
        '| 인증서 | 구분 | CN | 만료일 | 남은 일수 | 적용 | 미적용 | 미확인 | 대상 |',
        '| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    for cert, days in items:
        s = get_ssl_cert_apply(cert.id)['summary']
        lines.append('| ' + ' | '.join(_md_cell(v) for v in (
            cert.cert_name, cert.cert_type.value, cert.cn, f'{cert.notafter:%Y-%m-%d}', days,
            s['applied'], s['not_applied'], s['unknown'], s['target'])) + ' |')
    return '\n'.join(lines) + '\n'


def notify_ssl_cert_expiry(params, today=None):
    """만료가 다가온 인증서를 Markdown 지식으로 등록하고, 그 지식을 '이메일-MW' 주소로 보낸다.

    대상 인증서가 없으면 아무것도 하지 않는다. (rtn, msg) — rtn 1 성공, 0 실패.
    """
    from app.mail_sender import get_emails_from_tags
    from app.models.knowledge import UtMdContent, UtTag
    from app.views.knowledge import send_md_content_email

    dday, last_dday = parse_notify_params(params)
    today = today or date.today()
    items = select_expiring_certs(dday, last_dday, today)
    if not items:
        return 1, '만료 주의 대상 인증서가 없습니다.'

    emails = get_emails_from_tags([NOTIFY_TAG], '', db.session, UtTag)
    if not emails:
        return 0, f"'{NOTIFY_TAG}' 태그(value1)에 수신 주소가 없습니다."

    doc = UtMdContent(content_name=f'{NOTIFY_SUBJECT} {today:%Y-%m-%d} {len(items)}건',
                      content_md=build_expiry_markdown(items, dday, last_dday, today),
                      search_tags='SSL인증서,만료주의')
    db.session.add(doc)
    db.session.commit()

    ok, msg = send_md_content_email(doc, emails, '미들웨어관리소')
    if not ok:
        return 0, f'지식 {doc.content_id} 은 등록했으나 메일 발송 실패: {msg}'
    return 1, f'{len(items)}건, {len(emails)}명에게 발송 (지식 {doc.content_id})'
