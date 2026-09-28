from flask import g, request, redirect, flash, url_for
from flask_wtf.csrf import generate_csrf
from flask_appbuilder import ModelView, BaseView, expose, has_access
from flask_appbuilder.models.sqla.interface import SQLAInterface
from .common import get_mw_user
import pandas as pd
from app import appbuilder, db
from app.sqls.itam_import import WAS_COLUMNS, WEB_COLUMNS, resolve_columns
from app.models.itam import ItWas, ItWeb, \
    ItItamWasCompare, ItItamWebCompare, ItLeebalsoWasCompare, ItLeebalsoWebCompare
import logging

log = logging.getLogger(__name__)

class ItWasModelView(ModelView):
    datamodel = SQLAInterface(ItWas)
    
    list_title = "IT WAS 구성정보"
    add_title = "IT WAS 구성정보 추가"
    edit_title = "IT WAS 구성정보 수정"
    show_title = "IT WAS 구성정보 상세"
    
    list_columns = [
        'config_id', 'config_name', 'host_id', 'biz_system', 'run_env', 
        'config_status', 'jeus_version', 'service_ip'
    ]
    
    label_columns = {
        'config_id': '구성번호',
        'config_name': '구성명',
        'host_id': '설치호스트명',
        'biz_system': '업무시스템',
        'biz_team': '업무팀',
        'gw_ip': 'OS대표IP(GW기준)',
        'service_ip': '서비스IP',
        'run_env': '운용환경',
        'config_status': '구성상태',
        'install_user': '설치계정명',
        'jeus_version': 'JEUS버전',
        'os_type': 'OS종류',
        'os_ver': 'OS버전',
        'domain_name': '도메인명',
        'base_port': 'BASE포트',
        'java_version': 'JAVA버전',
        'embed_web_yn': '내장WEB사용여부',
        'embed_web_port': '내장WEB노드포트',
        'embed_web_ssl_yn': '내장WEBSSL사용여부',
        'was_ssl_yn': 'WASSSL사용여부',
        'os_kernel': 'OS커널',
        'cpu_core': 'CPU(Core)',
        'mem_gb': 'MEM(GB)',
        'hw_name': '하드웨어네임',
        'hw_group': '하드웨어그룹',
        'dept_team': '담당팀',
        'cust_p_mngr': '고객담당자(정)',
        'cust_s_mngr': '고객담당자(부)',
        'ito_p_mngr': 'ITO담당자(정)',
        'ito_s_mngr': 'ITO담당자(부)',
        'create_on': '생성일시'
    }

class ItWebModelView(ModelView):
    datamodel = SQLAInterface(ItWeb)
    
    list_title = "IT WEB 구성정보"
    add_title = "IT WEB 구성정보 추가"
    edit_title = "IT WEB 구성정보 수정"
    show_title = "IT WEB 구성정보 상세"
    
    list_columns = [
        'config_id', 'config_name', 'host_id', 'biz_system', 'run_env', 
        'config_status', 'webtob_version', 'service_ip'
    ]
    
    label_columns = {
        'config_id': '구성번호',
        'config_name': '구성명',
        'host_id': '설치호스트명',
        'biz_system': '업무시스템',
        'biz_team': '업무팀',
        'gw_ip': 'OS대표IP(GW기준)',
        'service_ip': '서비스IP',
        'run_env': '운용환경',
        'config_status': '구성상태',
        'install_user': '설치계정명',
        'webtob_version': 'Webtob버전',
        'os_type': 'OS종류',
        'os_ver': 'OS버전',
        'node_port': '노드포트',
        'ssl_yn': 'SSL사용여부',
        'ev_cert_yn': 'EV인증서여부',
        'server_loc': 'WEB서버위치',
        'os_kernel': 'OS커널',
        'cpu_core': 'CPU(Core)',
        'mem_gb': 'MEM(GB)',
        'hw_name': '하드웨어네임',
        'hw_group': '하드웨어그룹',
        'dept_team': '담당팀',
        'cust_p_mngr': '고객담당자(정)',
        'cust_s_mngr': '고객담당자(부)',
        'ito_p_mngr': 'ITO담당자(정)',
        'ito_s_mngr': 'ITO담당자(부)',
        'create_on': '생성일시'
    }

class ItExcelImportView(BaseView):
    route_base = "/it_import"
    default_view = "upload"
    
    @expose("/upload", methods=['GET', 'POST'])
    @has_access
    def upload(self):
        if request.method == 'POST':
            file = request.files.get('file')
            import_type = request.form.get('type') # 'was' or 'web'
            
            if not file or file.filename == '':
                flash("파일을 선택해주세요.", "danger")
                return redirect(url_for(".upload"))
            
            try:
                df = pd.read_excel(file)
                # Normalize column names (remove newlines, spaces)
                df.columns = [str(c).replace('\n', ' ').strip() for c in df.columns]
                
                if import_type == 'was':
                    self.import_was(df)
                elif import_type == 'web':
                    self.import_web(df)
                else:
                    flash("잘못된 요청입니다.", "danger")
                    return redirect(url_for(".upload"))
                
                db.session.commit()
                flash(f"{import_type.upper()} 데이터 임포트 완료", "success")
            except Exception as e:
                db.session.rollback()
                log.error(f"Excel import error: {str(e)}")
                flash(f"임포트 실패: {str(e)}", "danger")
                
            return redirect(url_for(".upload"))
            
        return self.render_template("itam_upload.html", csrf_token=generate_csrf())

    def import_was(self, df):
        mapping = resolve_columns(df.columns, WAS_COLUMNS)
        db.session.query(ItWas).delete()
        
        for _, row in df.iterrows():
            config_id = str(row.get('구성번호')).strip()
            if not config_id or config_id == 'nan':
                continue
                
            item = ItWas(config_id=config_id)
            db.session.add(item)
            
            for kor, eng in mapping.items():
                if kor in row:
                    val = str(row[kor]) if pd.notna(row[kor]) else None
                    setattr(item, eng, val)
            
            item.user_id = g.user.username

    def import_web(self, df):
        mapping = resolve_columns(df.columns, WEB_COLUMNS)
        db.session.query(ItWeb).delete()

        for _, row in df.iterrows():
            config_id = str(row.get('구성번호')).strip()
            if not config_id or config_id == 'nan':
                continue

            item = ItWeb(config_id=config_id)
            db.session.add(item)

            for kor, eng in mapping.items():
                if kor in row:
                    val = str(row[kor]) if pd.notna(row[kor]) else None
                    setattr(item, eng, val)
            
            item.user_id = g.user.username


# ============================================================
# ITAM 대사 결과 ModelView (4개)
# ============================================================

class ItItamWasCompareModelView(ModelView):
    datamodel = SQLAInterface(ItItamWasCompare)
    
    list_title = "ITAM WAS 기준 대사 결과"
    show_title = "ITAM WAS 기준 대사 결과 상세"
    edit_title = "ITAM WAS 기준 대사 결과 수정"
    
    list_columns = ['config_id', 'error_type', 'error_content', 'action_yn', 'create_on']
    search_columns = ['config_id', 'error_type', 'action_yn']
    
    label_columns = {
        'config_id': 'ITAM 구성번호',
        'error_type': '오류 항목',
        'error_content': '오류 내용',
        'action_yn': '조치구분',
        'create_on': '생성일시'
    }
    
    edit_columns = ['action_yn']


class ItItamWebCompareModelView(ModelView):
    datamodel = SQLAInterface(ItItamWebCompare)
    
    list_title = "ITAM WEB 기준 대사 결과"
    show_title = "ITAM WEB 기준 대사 결과 상세"
    edit_title = "ITAM WEB 기준 대사 결과 수정"
    
    list_columns = ['config_id', 'error_type', 'error_content', 'action_yn', 'create_on']
    search_columns = ['config_id', 'error_type', 'action_yn']
    
    label_columns = {
        'config_id': 'ITAM 구성번호',
        'error_type': '오류 항목',
        'error_content': '오류 내용',
        'action_yn': '조치구분',
        'create_on': '생성일시'
    }
    
    edit_columns = ['action_yn']


class ItLeebalsoWasCompareModelView(ModelView):
    datamodel = SQLAInterface(ItLeebalsoWasCompare)
    
    list_title = "미들웨어관리소 WAS 기준 대사 결과"
    show_title = "미들웨어관리소 WAS 기준 대사 결과 상세"
    edit_title = "미들웨어관리소 WAS 기준 대사 결과 수정"
    
    list_columns = ['leebalso_id', 'error_type', 'error_content', 'action_yn', 'create_on']
    search_columns = ['error_type', 'action_yn']
    
    label_columns = {
        'leebalso_id': '미들웨어관리소 WAS ID',
        'error_type': '오류 항목',
        'error_content': '오류 내용',
        'action_yn': '조치구분',
        'create_on': '생성일시'
    }
    
    edit_columns = ['action_yn']


class ItLeebalsoWebCompareModelView(ModelView):
    datamodel = SQLAInterface(ItLeebalsoWebCompare)
    
    list_title = "미들웨어관리소 WEB 기준 대사 결과"
    show_title = "미들웨어관리소 WEB 기준 대사 결과 상세"
    edit_title = "미들웨어관리소 WEB 기준 대사 결과 수정"
    
    list_columns = ['leebalso_id', 'error_type', 'error_content', 'action_yn', 'create_on']
    search_columns = ['error_type', 'action_yn']
    
    label_columns = {
        'leebalso_id': '미들웨어관리소 WEB ID',
        'error_type': '오류 항목',
        'error_content': '오류 내용',
        'action_yn': '조치구분',
        'create_on': '생성일시'
    }
    
    edit_columns = ['action_yn']


# ============================================================
# ITAM 대사 실행 화면
# ============================================================

class ItamCompareView(BaseView):
    route_base = "/itam_compare"
    default_view = "list"
    
    @expose('/list')
    @has_access
    def list(self):
        return self.render_template('itam_compare.html', csrf_token=generate_csrf())


# ============================================================
# 메뉴 등록
# ============================================================

# ITAM 대사 메뉴
appbuilder.add_view(
    ItExcelImportView,
    "Excel 파일 업로드",
    icon="fa-upload",
    category="ITAM 대사"
)
appbuilder.add_separator("ITAM 대사")
appbuilder.add_view(
    ItWasModelView,
    "IT WAS 구성정보",
    icon="fa-server",
    category="ITAM 대사"
)
appbuilder.add_view(
    ItWebModelView,
    "IT WEB 구성정보",
    icon="fa-globe",
    category="ITAM 대사"
)
appbuilder.add_separator("ITAM 대사")
appbuilder.add_view(
    ItamCompareView,
    "대사 실행",
    icon="fa-play",
    category="ITAM 대사"
)
appbuilder.add_separator("ITAM 대사")
appbuilder.add_view(
    ItItamWasCompareModelView,
    "ITAM WAS 기준 대사",
    icon="fa-exchange",
    category="ITAM 대사"
)
appbuilder.add_view(
    ItItamWebCompareModelView,
    "ITAM WEB 기준 대사",
    icon="fa-exchange",
    category="ITAM 대사"
)
appbuilder.add_view(
    ItLeebalsoWasCompareModelView,
    "MWM WAS 기준 대사",
    icon="fa-exchange",
    category="ITAM 대사"
)
appbuilder.add_view(
    ItLeebalsoWebCompareModelView,
    "MWM WEB 기준 대사",
    icon="fa-exchange",
    category="ITAM 대사"
)
