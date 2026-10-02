"""SSL 인증서 파일·적용 현황 화면 (HOWTO_021)."""
from flask import request
from flask_appbuilder import BaseView, ModelView, expose, has_access
from flask_appbuilder.models.sqla.interface import SQLAInterface
from wtforms.validators import DataRequired, ValidationError

from app import appbuilder, db
from app.models.was import MwSslCertFile
from app.sqls import ssl_cert as ssl_cert_sql


class MaxBytes:
    """UTF-8 byte 길이 제한. String(n) 은 PostgreSQL 에서 글자 수 제한이라 따로 검사한다."""

    def __init__(self, limit):
        self.limit = limit

    def __call__(self, form, field):
        if field.data and len(field.data.encode('utf-8')) > self.limit:
            raise ValidationError(f'{self.limit}byte 이내로 입력하십시오 (한글은 글자당 3byte).')


class SslCertFileModelView(ModelView):
    datamodel = SQLAInterface(MwSslCertFile)
    list_title = "SSL 인증서 파일"

    add_columns = ['ag_file', 'cert_name', 'received_date', 'receiver_name']
    edit_columns = ['cert_name']
    list_columns = ['cert_name', 'cert_type', 'cn', 'notafter', 'file_name', 'received_date', 'receiver_name']
    show_columns = ['cert_name', 'cert_type', 'cn', 'subject', 'issuer', 'serial', 'notbefore', 'notafter',
                    'file_name', 'received_date', 'receiver_name', 'user_id', 'create_on']
    label_columns = {
        'cert_name': '이름', 'ag_file': '인증서 파일', 'received_date': '접수일', 'receiver_name': '접수자',
        'cert_type': '구분', 'cn': 'CN', 'notbefore': '유효기간시작', 'notafter': '유효기간만료',
        'file_name': '파일 이름',
    }
    description_columns = {'cert_name': '30byte 이내 (예: 2026.11-EV-bank, 2026.12-bulk)'}
    validators_columns = {'cert_name': [MaxBytes(30)], 'ag_file': [DataRequired()]}
    base_order = ('received_date', 'desc')

    def pre_add(self, item):
        # 여기서 난 예외는 FAB 가 flash(danger) 로 보이고 INSERT 하지 않는다 (HOWTO_021 §3.3)
        for key, value in ssl_cert_sql.extract_from_ag_file(item.ag_file).items():
            setattr(item, key, value)


class SslCertApplyView(BaseView):
    default_view = 'index'

    @expose('/')
    @has_access
    def index(self):
        certs = db.session.query(MwSslCertFile).order_by(MwSslCertFile.received_date.desc(),
                                                         MwSslCertFile.id.desc()).all()
        return self.render_template('ssl_cert_apply.html', certs=certs,
                                    selected=request.args.get('cert_id', type=int))


appbuilder.add_view(
    SslCertFileModelView,
    "SSL 인증서 파일",
    icon="fa-certificate",
    category="Monitor",
)
appbuilder.add_view(
    SslCertApplyView,
    "SSL 인증서 적용 현황",
    icon="fa-check-square-o",
    category="Monitor",
)
