from flask_appbuilder.api import BaseApi, expose, protect
from app import appbuilder
from app.sqls.monitor import (
    get_cert_expiry_stat,
    get_cert_expiry_stat_jeus,
    get_ica_cert_expiry_stat,
    get_ica_cert_expiry_stat_jeus
)

class MonitorRestApi(BaseApi):
    resource_name = 'monitor'
    
    # ------------------ 기존 LEAF 인증서용 (REST 마이그레이션) ------------------
    @expose('/cert_expiry_stat', methods=['GET'])
    @protect(allow_browser_login=True)
    def get_cert_expiry_stat(self):
        result = get_cert_expiry_stat()
        return self.response(200, cert_expiry_stat=result)

    @expose('/cert_expiry_stat_jeus', methods=['GET'])
    @protect(allow_browser_login=True)
    def get_cert_expiry_stat_jeus(self):
        result = get_cert_expiry_stat_jeus()
        return self.response(200, cert_expiry_stat_jeus=result)

    # ------------------ 신규 ICA 인증서용 ------------------
    @expose('/ica_cert_expiry_stat', methods=['GET'])
    @protect(allow_browser_login=True)
    def get_ica_cert_expiry_stat(self):
        result = get_ica_cert_expiry_stat()
        return self.response(200, ica_cert_expiry_stat=result)

    @expose('/ica_cert_expiry_stat_jeus', methods=['GET'])
    @protect(allow_browser_login=True)
    def get_ica_cert_expiry_stat_jeus(self):
        result = get_ica_cert_expiry_stat_jeus()
        return self.response(200, ica_cert_expiry_stat_jeus=result)

# API 등록
appbuilder.add_api(MonitorRestApi)
