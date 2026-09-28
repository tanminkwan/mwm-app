from app.appctx import with_app_context
from app import appbuilder, db, WAS_STATUS
from app.models.was import MwWasWebtobConnector, MwWebServer, MwWas, MwWeb, MwWebVhost\
        , MwWebDomain, MwWebSsl
from app.views.common import call_notification
from .relationship import get_web_servers
from .knowledge import insert_tag
from .agent import finish_commands, get_agent
from .monitor import update_rows, insert_row, select_rows, select_row, get_was_status_template, \
    get_not_running_was_list
from sqlalchemy.dialects.postgresql import insert
from . import webtob_dml, agent_dml
from datetime import datetime, timedelta
from datetime import datetime
import re, json
import functools
import inspect
import logging

batch_function_registry = {}

def batch_function(func):
    @functools.wraps(func)
    def batch_wrapper(command_id, *args, **kwargs):
        logging.info(f"[{command_id}] 시작: {func.__name__} - {datetime.now()}")
        try:
            # Check if func accepts command_id as the first positional argument or named argument
            sig = inspect.signature(func)
            if 'command_id' in sig.parameters:
                result = func(command_id, *args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # run_batch_by_scheduler 기능 수행
            finish_commands([command_id])
            db.session.commit()

            logging.info(f"[{command_id}] 작업 완료: {func.__name__} - 결과: {result}")
            if isinstance(result, tuple) and len(result) >= 2:
                return result
            return 1, 'OK'
        except Exception as e:
            logging.error(f"[{command_id}] 오류 발생: {func.__name__} - {e}")
            return 0, str(e)
    
    # Register the function in the global registry immediately
    batch_function_registry[func.__name__] = func.__doc__ or func.__name__
    
    return batch_wrapper

@with_app_context
def run_batch_by_scheduler(command_id, function_name, additional_param=''):
    try:
        # 전역 네임스페이스에서 함수 찾기
        func = globals()[function_name]
        if callable(func):
            if additional_param:
                return func(command_id, additional_param)
            else:
                return func(command_id)
        else:
            return 0, f"'{function_name}'은(는) 호출 가능한 함수가 아닙니다."
    except KeyError:
        return 0, f"함수 '{function_name}'을(를) 찾을 수 없습니다."
    except Exception as e:
        return 0, f"함수 실행 중 오류 발생: {str(e)}"

@batch_function
def update_resource_tag():
    """mw_was_instance tag 일괄 update"""
    #_update_resource_tag('ag_agent')
    #_update_resource_tag('mw_was')
    #_update_resource_tag('mw_web')
    _update_resource_tag()
    #update_was_resource_tag()
    #update_web_resource_tag()

def _update_resource_tag():

    recs, _ = select_rows('mw_was_instance', {})

    for rec in recs:

        if '_Domain' in rec.was_id and '_M' in rec.was_instance_id:
            tag1 = rec.was_id.replace('_Domain','')[1:]
            tag2 = rec.was_instance_id.split('_M')[0]
            tag = 'MS-' + tag1 + '_Domain-' + tag2
            tag_id = _upsert_tag(tag)
            row, _ = select_row('ut_tag',{'id':tag_id})
            rec.ut_tag = [row]

def _upsert_tag(tag):

    rtn = insert_tag(tag)
    return rtn

@batch_function
def notify_was_abnormal_status():
    _, recs, _ = get_not_running_was_list()

    logging.info(f"was_abnormal_status 건수 : {len(recs)}")
    [ call_notification(f"WAS_STATUS:{rec['was_instance_id']}-상태 비정상({rec['was_instance_stat']}.{rec['host_id']})") for rec in recs]

@batch_function
def update_was_status():
    """Updating WAS_STATUS"""
    # 모니터링대상 WAS List 조회
    recs, groups = get_was_status_template()

    for rec in recs:
        tmp_dict = dict(
            DOMAIN_ID = rec['was_id'],
            HOST_ID = rec['host_id'].upper(),
            SERVER_NAME = rec['was_instance_id'],
            WAS_INSTANCE_GROUP = rec['was_instance_group']
        )
        WAS_STATUS.update(
            #{rec['was_id']+'.'+rec['host_id'].upper()+'.'+rec['was_instance_id']:tmp_dict}
            {rec['was_id']+'.'+rec['was_instance_id']:tmp_dict}
            )
        WAS_STATUS.update(
            {'GROUPS':groups}
            )

    return 1, ''

@batch_function
def update_agent_id_info_in_web():

    print('updateAgentIdInfoInWeb started')
    web_recs = db.session.query(MwWeb).all()

    if not web_recs:
        return 0, ''

    for rec in web_recs:

        update_dict = {'agent_id':_get_agent(rec.sys_user, rec.host_id)}
        filter_dict = dict(
            host_id = rec.host_id
           ,port    = rec.port
        )
        update_rows('mw_web', update_dict, filter_dict)

    return 1, 'OK'

@batch_function
def update_agent_id_info_in_was():

    print('updateAgentIdInfoInWas started')
    was_recs = db.session.query(MwWas).all()

    if not was_recs:
        return 0, ''

    for rec in was_recs:

        update_dict = {'agent_id':_get_agent(rec.sys_user, rec.located_host_id)}
        filter_dict = dict(
            was_id     = rec.was_id
        )
        update_rows('mw_was', update_dict, filter_dict)

    return 1, 'OK'

def _get_agent(sys_user, host_id):
    rec = get_agent(host_id + '_' + sys_user + '_J', isApproved=True)
    return rec.agent_id if rec else ''

@batch_function
def update_url_rewrite_info():

    print('updateUrlRewriteInfo started')
    web_recs = db.session.query(MwWeb).all()

    if not web_recs:
        return 0, ''

    for rec in web_recs:

        httpm = rec.httpm_object
        if not httpm or not httpm.get('VHOST'):
            continue
        
        for vh in httpm['VHOST']:

            if not vh.get('URLREWRITE') or vh['URLREWRITE'] in ['N', 'n']:
                update_dict = dict(
                    urlrewrite_yn     = 'NO'
                )
            else:

                urlrewrite_config = vh['URLREWRITECONFIG'] if vh.get('URLREWRITECONFIG') else ''

                if '${WEBTOBDIR}' in urlrewrite_config:
                    urlrewrite_config = urlrewrite_config.replace('${WEBTOBDIR}', rec.web_home)

                update_dict = dict(
                    urlrewrite_yn     = 'YES'
                   ,urlrewrite_config = urlrewrite_config
                )

            filter_dict = dict(
                host_id  = rec.host_id
               ,port     = rec.port
               ,vhost_id = vh['NAME']
            )

            update_rows('mw_web_vhost',update_dict, filter_dict)


def _re_register_web_from_text(web_id):
    web_rec = db.session.query(MwWeb).filter(MwWeb.id == web_id).first()
    if not web_rec:
        return 0, 'No web data found'

    # 텍스트가 없더라도 재등록 시도는 한 것이므로 날짜 갱신
    web_rec.create_on = datetime.now()
    
    if not web_rec.web_text:
        return 0, 'No web text found'

    httpm_dict = webtob_dml.httpm_to_dict(web_rec.web_text)
    
    # newgeneration_yn 에 따라 적절한 클래스 사용
    if web_rec.newgeneration_yn.name == 'YES':
        h = webtob_dml.NewHttpm(web_rec.host_id, httpm_dict, web_rec.web_text, sys_user=web_rec.sys_user, domain_id="", agent_id=web_rec.agent_id)
    else:
        h = webtob_dml.OldHttpm(web_rec.host_id, httpm_dict, web_rec.web_text, sys_user=web_rec.sys_user, domain_id="", agent_id=web_rec.agent_id)
    
    return h.upsertWebtobHttpm()

@batch_function
def re_register_web_from_text(web_id):
    return _re_register_web_from_text(web_id)

def _re_register_was_from_text(was_id):
    was_rec = db.session.query(MwWas).filter(MwWas.id == was_id).first()
    if not was_rec:
        return 0, 'No was data found'

    # 텍스트가 없더라도 재등록 시도는 한 것이므로 날짜 갱신
    was_rec.create_on = datetime.now()

    if not was_rec.was_text:
        return 0, 'No was text found'

    domain_info = dict(
        domain_id = was_rec.was_id,
        host_id   = was_rec.located_host_id,
        content   = was_rec.was_text,
        sys_user  = was_rec.sys_user,
        agent_id  = was_rec.agent_id or '',
    )

    return agent_dml.AutorunResult.update_domain(domain_info, skip_check=True)

@batch_function
def re_register_was_from_text(was_id):
    return _re_register_was_from_text(was_id)

@batch_function
def re_register_all_was_from_text():
    """모든 WAS(JEUS) 설정을 DB 텍스트 기반으로 일괄 재등록"""
    was_recs = db.session.query(MwWas).filter(MwWas.use_yn == 'YES').all()
    count = 0
    errors = []
    for rec in was_recs:
        rtn, msg = _re_register_was_from_text(rec.id)
        if rtn > 0:
            count += 1
        else:
            errors.append(f"{rec.was_id}: {msg}")
    
    summary = f"Total {len(was_recs)} WAS processed. {count} succeeded."
    if errors:
        summary += f" Errors: {errors}"
    return count, summary

@batch_function
def re_register_all_web_from_text():
    """모든 Web(WebToB) 설정을 DB 텍스트 기반으로 일괄 재등록"""
    web_recs = db.session.query(MwWeb).filter(MwWeb.use_yn == 'YES').all()
    count = 0
    errors = []
    for rec in web_recs:
        rtn, msg = _re_register_web_from_text(rec.id)
        if rtn > 0:
            count += 1
        else:
            errors.append(f"{rec.host_id}:{rec.port}: {msg}")
    
    summary = f"Total {len(web_recs)} Web processed. {count} succeeded."
    if errors:
        summary += f" Errors: {errors}"
    return count, summary

@batch_function
def create_webtob_conn(domain_id=''):

    query = db.session.query(MwWasWebtobConnector)

    if domain_id:
        query = query.filter(MwWasWebtobConnector.was_id==domain_id)

    result = query.all()

    for r in result:

        web_recs = get_web_servers(r)

        if web_recs:
            r.mw_web_server = web_recs
        else:
            r.mw_web_server = []


@batch_function
def create_ssl_info(webInfo):
    return webtob_dml._create_ssl_info(webInfo)

updateResourceTag = update_resource_tag
updateWasStatus = update_was_status
updateAgentIdInfoInWeb = update_agent_id_info_in_web
updateAgentIdInfoInWas = update_agent_id_info_in_was
updateUrlRewriteInfo = update_url_rewrite_info
createSslInfo = create_ssl_info
createWebtobConn = create_webtob_conn

@batch_function
def sync_was_web_relationship():
    """WAS-WEB 관계 일괄 동기화 (Association Table 및 Built Type 갱신)"""
    from .relationship import update_was_web_relation
    return update_was_web_relation()

for old_name, new_func in [
    ('updateResourceTag', update_resource_tag),
    ('updateWasStatus', update_was_status),
    ('updateAgentIdInfoInWeb', update_agent_id_info_in_web),
    ('updateAgentIdInfoInWas', update_agent_id_info_in_was),
    ('updateUrlRewriteInfo', update_url_rewrite_info),
    ('createSslInfo', create_ssl_info),
    ('createWebtobConn', create_webtob_conn),
    ('sync_was_web_relationship', sync_was_web_relationship),
    ('re_register_all_was_from_text', re_register_all_was_from_text),
    ('re_register_all_web_from_text', re_register_all_web_from_text),
]:
    batch_function_registry[old_name] = new_func.__doc__ or old_name

# ---- Role/Permission Sync ----

# 메뉴 카테고리 → role 매핑. Was/Web은 mw_rgroup으로 통합.
MENU_CATEGORY_TO_ROLE = {
    'Server':        'server_rgroup',
    'Was':           'mw_rgroup',
    'Web':           'mw_rgroup',
    'Agent&Command': 'agent_rgroup',
    'Monitor':       'monitor_rgroup',
    'System':        'system_rgroup',
    '지식관리':       'knowledge_rgroup',
    'ITAM 대사':     'itam_rgroup',
    '나의 정보':       'api_rgroup',
}

# 모든 유저가 기본적으로 가져야 할 공통 권한 (Home, 프로필 등)
COMMON_VIEWS_FOR_ALL = [
    'MyIndexView', 'UserDBModelView', 'ResetPasswordView', 
    'UserInfoEditView', 'CommonApi'
]

@batch_function
def sync_role_permissions():
    """메뉴 및 API 기반 Role 자동 생성 및 권한 할당"""
    sm = appbuilder.sm
    role_perms = {}  # {role_name: set of (permission_name, view_menu_name)}

    def add_perms_for_view(role_name, view):
        """View 및 관련된 모든 권한(PVM)을 수집하여 role_perms에 추가"""
        if not view:
            return
        
        # 검색할 ViewMenu 이름 후보군
        v_names = set()
        v_names.add(view.__class__.__name__)
        if hasattr(view, 'view_name'):
            v_names.add(view.view_name)
        
        for name in v_names:
            if not name: continue
            pvm_list = db.session.query(sm.permissionview_model)\
                .join(sm.viewmenu_model)\
                .filter(sm.viewmenu_model.name == name).all()
            for pvm in pvm_list:
                if pvm.permission and pvm.view_menu:
                    role_perms[role_name].add((pvm.permission.name, pvm.view_menu.name))
        
        # related_views(상세 보기 등)에 대한 권한도 포함
        if hasattr(view, 'related_views'):
            for related_view_class in view.related_views:
                rv_name = related_view_class.__name__
                pvm_list = db.session.query(sm.permissionview_model)\
                    .join(sm.viewmenu_model)\
                    .filter(sm.viewmenu_model.name == rv_name).all()
                for pvm in pvm_list:
                    if pvm.permission and pvm.view_menu:
                        role_perms[role_name].add((pvm.permission.name, pvm.view_menu.name))

    # 1. 메뉴 기반 처리
    for menu_item in appbuilder.menu.menu:
        category_name = menu_item.name
        role_name = MENU_CATEGORY_TO_ROLE.get(category_name)
        if not role_name:
            continue

        if role_name not in role_perms:
            role_perms[role_name] = set()

        # 카테고리 메뉴 자체 접근권한
        role_perms[role_name].add(('menu_access', category_name))

        # 하위 메뉴 아이템 처리
        if hasattr(menu_item, 'childs'):
            for child in menu_item.childs:
                if hasattr(child, 'name') and child.name:
                    # 메뉴 접근 권한
                    role_perms[role_name].add(('menu_access', child.name))

                    # View 및 연관 View(related_views)의 모든 권한 수집
                    if hasattr(child, 'baseview') and child.baseview:
                        add_perms_for_view(role_name, child.baseview)

    # 2. API 기반 처리 (api_rgroup) - BaseApi 상속 클래스 동적 수집
    if 'api_rgroup' not in role_perms:
        role_perms['api_rgroup'] = set()
    
    from flask_appbuilder.api import BaseApi
    for view in appbuilder.baseviews:
        if isinstance(view, BaseApi):
            api_class_name = view.__class__.__name__
            # 공통 권한에 포함된 Api는 api_rgroup 수집에서 제외 (중복 방지)
            if api_class_name in COMMON_VIEWS_FOR_ALL:
                continue
            pvm_list = db.session.query(sm.permissionview_model)\
                .join(sm.viewmenu_model)\
                .filter(sm.viewmenu_model.name == api_class_name).all()
            for pvm in pvm_list:
                if pvm.permission and pvm.view_menu:
                    role_perms['api_rgroup'].add((pvm.permission.name, pvm.view_menu.name))

    # 3. 공통 기반 role 처리 (common_rgroup) - 로그인 및 기본 UI 유지용
    if 'common_rgroup' not in role_perms:
        role_perms['common_rgroup'] = set()
    
    for v_name in COMMON_VIEWS_FOR_ALL:
        pvm_list = db.session.query(sm.permissionview_model)\
            .join(sm.viewmenu_model)\
            .filter(sm.viewmenu_model.name == v_name).all()
        for pvm in pvm_list:
            if pvm.permission and pvm.view_menu:
                role_perms['common_rgroup'].add((pvm.permission.name, pvm.view_menu.name))
    
    # MyIndexView 에 대한 menu_access 는 명시적으로 추가 (등록 안되어 있을 수 있음)
    role_perms['common_rgroup'].add(('menu_access', 'Main'))
    role_perms['common_rgroup'].add(('menu_access', 'MyIndexView'))

    # 4. Variant Roles (_read_rgroup, _edit_rgroup) 생성
    variant_role_perms = {}
    for role_name, perms in role_perms.items():
        if not role_name.endswith('_rgroup'):
            continue
        
        # _read_rgroup: delete/add/edit 권한 제거
        read_role_name = role_name.replace('_rgroup', '_read_rgroup')
        read_perms = { (p, v) for p, v in perms if p not in ['can_add', 'can_edit', 'can_delete', 'muldelete'] }
        variant_role_perms[read_role_name] = read_perms
        
        # _edit_rgroup: delete 권한 제거
        edit_role_name = role_name.replace('_rgroup', '_edit_rgroup')
        edit_perms = { (p, v) for p, v in perms if p not in ['can_delete', 'muldelete'] }
        variant_role_perms[edit_role_name] = edit_perms
        
    role_perms.update(variant_role_perms)

    # 5. Role 생성/업데이트
    results = []
    for role_name, perms in role_perms.items():
        role = sm.find_role(role_name)
        if not role:
            role = sm.add_role(role_name)
            results.append(f"Created role: {role_name}")
        else:
            results.append(f"Updated role: {role_name}")

        role.permissions = []
        for perm_name, view_name in perms:
            pvm = sm.find_permission_view_menu(perm_name, view_name)
            if pvm:
                sm.add_permission_role(role, pvm)

    summary = '; '.join(results)
    logging.info(f"sync_role_permissions: {summary}")
    return 1, summary
