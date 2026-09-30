from flask import g, render_template, request, jsonify\
     , redirect, url_for
from flask_appbuilder.filemanager import get_file_original_name
from flask_appbuilder.models.sqla.interface import SQLAInterface
from flask_appbuilder import BaseView, ModelView\
    , expose, has_access
from flask_appbuilder.widgets import ListBlock
from flask_appbuilder.actions import action
from flask_appbuilder.models.sqla.filters import FilterEqual
from app import appbuilder, db, scheduler
from app.models.agent import AgCommandType, AgCommandMaster, AgCommandDetail\
    , AgAgentGroup, AgAgent, AgResult, AgFile, AgCommandHelper, AgAutorunResult
import logging
from app.sqls.agent_dml import AutorunResult
from app.file_manager.s3.filemanager import S3FileManager, S3FileUploadField
from .common import FilterStartsWithFunction, get_mw_user\
    , ReadOnlyField, RequiredOnContidion, ValidateBatchFunctionName
from app.sqls.agent import cancel_commands, create_command_detail\
    , update_result_status, broadcast_callback_registry, flush_mqtt_pending
from app.models.common import PeriodicTypeEnum, TargetToSendEnum
from sqlalchemy import event

from wtforms import Form, StringField

#from wtforms.fields import TextField
from wtforms.validators import Regexp, EqualTo
from config import AGENT_OFFLINE_MINUTES
from datetime import datetime, timedelta
from app.jobs  import job_ag_create_job
from flask_appbuilder.filemanager import get_file_original_name
import json
import apscheduler
"""
@event.listens_for(db.session, 'after_attach')
def test(session, instance):
    print("after_attach : ")

@db.event.listens_for(AgCommandMaster.periodic_type, 'set')
def create_command_detail2(target, value, old_value, initiator):
    print("value :",value)
    print("old_value :",old_value)
    if value.name == 'IMMEDIATE' and old_value != 'IMMEDIATE':
        create_command_detail(connection, target)
@db.event.listens_for(AgCommandMaster, 'after_update')
def job_after_update_command(mapper, connection, target):
    
    print('mwm job_after_update_command')
    print(target)
"""
@db.event.listens_for(AgCommandMaster, 'after_insert')
def create_command_detail1(mapper, connection, target):
    
    logging.debug(f"after_insert create_command_detail1 called : {target}")
    # [서버내부기능] 이거나 주기가 있는 작업은 scheduler로 등록
    if target.periodic_type.name in ('PERIODIC','ONETIME') or target.ag_command_type.command_class.name == 'ServerFunc':
        job_ag_create_job(target)
    else:
        create_command_detail(target)

@db.event.listens_for(AgCommandMaster, 'after_delete')
def delete_command_job(mapper, connection, target):
    
    logging.debug(f"after_delete delete_command_job called : {target}")
    try:
        scheduler.remove_job('CreDetail_'+ target.command_id)
    except Exception as e:
        pass

    try:
        scheduler.remove_job('RunBatch_'+ target.command_id)
    except Exception as e:
        pass

def _force_immediate_for_mqtt(target):
    """command_sender 가 MQTT 면 실행구분을 IMMEDIATE 로 강제한다.

    IMMEDIATE 만이 after_insert 에서 create_command_detail() 을 동기 호출하는
    경로다. ONETIME/PERIODIC 은 APScheduler 에 등록되어 나중에 상세가 생성되므로
    '실시간 push' 라는 MQTT 도입 목적이 성립하지 않는다.
    """
    if not target.command_sender or target.command_sender.name != 'MQTT':
        return

    if target.periodic_type != PeriodicTypeEnum.IMMEDIATE:
        logging.info('command_sender=MQTT -> periodic_type 을 IMMEDIATE 로 강제 (요청값=%s)',
                     target.periodic_type)

    target.periodic_type = PeriodicTypeEnum.IMMEDIATE
    # 스케줄 관련 필드는 의미가 없어지므로 함께 비운다.
    # set_interval_type 훅에 의존하지 않도록 여기서 직접 정리해 등록 순서와 무관하게 한다.
    target.time_to_exe   = None
    target.time_to_stop  = None
    target.cycle_to_exe  = None
    target.interval_type = None


@db.event.listens_for(AgCommandMaster, 'before_insert')
def force_immediate_for_mqtt_on_insert(mapper, connection, target):
    _force_immediate_for_mqtt(target)


def _force_result_receiver_server(target):
    """결과 받는 곳은 SERVER 로 고정한다.

    Agent 는 결과를 REST 로만 보낸다. MQTT 는 명령을 내려보내는 채널(command_sender)이고,
    result_receiver 가 같은 enum 을 써서 고를 수 있었을 뿐이다 — 예전 Agent 는
    result_receiver=MQTT 명령의 결과를 어디로도 보내지 않았다.
    """
    target.result_receiver = TargetToSendEnum.SERVER


@db.event.listens_for(AgCommandMaster, 'before_insert')
def force_result_receiver_on_insert(mapper, connection, target):
    _force_result_receiver_server(target)


@db.event.listens_for(AgCommandMaster, 'before_update')
def force_result_receiver_on_update(mapper, connection, target):
    _force_result_receiver_server(target)


@db.event.listens_for(AgCommandMaster, 'before_update')
def force_immediate_for_mqtt_on_update(mapper, connection, target):
    _force_immediate_for_mqtt(target)


@db.event.listens_for(db.session, 'after_commit')
def flush_mqtt_pending_after_commit(session):
    """적재된 MQTT Command 를 commit 이후에 발행한다 (app/sqls/agent.py).

    적재분이 없으면 즉시 반환하므로 MQTT 와 무관한 commit 에는 영향이 없다.
    """
    try:
        flush_mqtt_pending(session)
    except Exception:
        # 발행 실패가 commit 을 되돌리게 해서는 안 된다.
        # 발행 못 한 Command 는 status CREATE 로 남아 REST 폴링이 처리한다.
        logging.exception('MQTT 발송 처리 중 예외 (REST 폴링으로 fallback)')


@db.event.listens_for(AgCommandMaster, 'before_insert')
def set_interval_type(mapper, connection, target):
    
    logging.debug(f"before_insert set_interval_type called : {target}")
    if target.periodic_type.name != 'PERIODIC':
        target.interval_type = None

@db.event.listens_for(AgFile, 'before_insert')
def set_file_name(mapper, connection, target):
    target.file_name = get_file_original_name(str(target.file))    

class AgentModelView(ModelView):
    
    datamodel = SQLAInterface(AgAgent)
    list_title    = "Agent 현황"
    list_columns  = ['agent_id', 'agent_type', 'agent_version', 'agent_name', 'agent_sub_type','c_last_checked',
                     'c_mqtt_status']
    label_columns = {'c_mqtt_status': 'MQTT'}
    list_template = 'listWithJson.html'
    list_widget = ListBlock
    extra_args = {
        'buttonList':[
         {'text':'PROD','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_landscape=PROD'}
        ,{'text':'DEV','id':'toggle_bt2','bt_group':'1','onclick':'_flt_0_landscape=DEV'}
        ,{'text':'TEST','id':'toggle_bt3','bt_group':'1','onclick':'_flt_0_landscape=TEST'}
        ,{'text':'OffLine','id':'toggle_bt3','bt_group':'1','onclick':'_flt_2_last_checked_date='+(datetime.now() - timedelta(minutes=AGENT_OFFLINE_MINUTES)).strftime("%Y-%m-%d+%H:%M:%S")}
        ,{'text':'Not Approved','id':'toggle_bt4','bt_group':'1','onclick':'_flt_0_approved_yn=NO'}
        ] + [
            # MQTT 헤더를 보낸 Agent (mqtt_state != '-' 는 SQL 에서 NULL 을 뺀다). 다른 그룹이라 PROD 등과 겹쳐 걸 수 있다
            {'text': 'MQTT', 'id': 'toggle_bt5', 'bt_group': '2', 'onclick': '_flt_7_mqtt_state=-'},
        ],
        'inputList':[
         {'text':'Hostname','id':'host-id','combind':'1','condition':'_flt_2_host_id=','size':20}
        ]
        }
    page_size = 100

    edit_columns = ['agent_id', 'agent_version', 'agent_name', 'landscape', 'agent_sub_type', 'ip_address', 'host_id', 'approved_yn']

    edit_form_extra_fields = {
        'agent_id': StringField('Agent Id', widget=ReadOnlyField())
      , 'agent_version': StringField('Agent Version', widget=ReadOnlyField())
      , 'ip_address': StringField('IP Address', widget=ReadOnlyField())
      , 'host_id': StringField('Host Id', widget=ReadOnlyField())
    }

    base_permissions = ['can_list', 'can_show', 'can_edit']


class CommandHelperModelView(ModelView):
    
    datamodel = SQLAInterface(AgCommandHelper)
    list_title    = "Command 파라메터 Replace 규칙"
    list_columns  = ['mapping_key','agent_id', 'target_file_name', 'string_to_replace']
    edit_columns  = ['mapping_key','ag_agent', 'target_file_name', 'string_to_replace']
    add_columns  = ['mapping_key','ag_agent', 'target_file_name', 'string_to_replace']
    label_columns = {"target_file_name": "대상 File/기능", "download": "Download"}

class AgentGroupModelView(ModelView):
    
    datamodel = SQLAInterface(AgAgentGroup)
    list_columns  = ['agent_group_id','agent_group_name', 'ag_agent']
    add_columns   = ['agent_group_id','agent_group_name', 'agent_type', 'ag_agent']
    edit_columns  = ['agent_group_id','agent_group_name', 'agent_type', 'ag_agent']


class FileModelView(ModelView):
    datamodel = SQLAInterface(AgFile)

    label_columns = {"file_name": "File Name", "download": "Download"}
    add_columns   = ['agent_type', 'file_version', 'file']
    edit_columns  = ['agent_type', 'file_version', 'file']
    list_columns  = ['agent_type', 'file_version', 'file_name','download','create_on']
    show_columns  = ['agent_type', 'file_version', 'file', 'file_name','download', 'user_id','create_on']

    validators_columns = {
                'file_version':[Regexp('\d{4}\.\d{4}\.\d{4}', message='format 0000.0000.0000')]
               , 'file_name':[EqualTo('get_filename', message='파일명이 일치하지 않습니다.')]
                }

    edit_form_extra_fields = add_form_extra_fields = {
        "file": S3FileUploadField("S3 File",
                                    description="",
                                    filemanager=S3FileManager,
                                )
    }

    def pre_delete(self, rel_obj):
        filename = getattr(rel_obj, 'file')
        file_obj = S3FileManager()
        file_obj.delete_file(filename)
        
class CommandTypeModelView(ModelView):
    
    datamodel = SQLAInterface(AgCommandType)
    list_title    = "Command Type"
    list_columns  = ['command_type_id', 'command_type_name', 'command_class', 'target_file_name', 'target_file_path']
    label_columns = {'command_type_id':'Command Type Id'
                    ,'command_type_name':'Command Type 설명'
                    ,'command_class':'호출되는 기능'
                    ,'target_file_path':'파일위치(새부기능)'
                    ,'target_file_name':'파일명(기능명)'
                     }
    edit_form_extra_fields = {
        'command_type_id': StringField('Command Type Id', widget=ReadOnlyField())
    }
    edit_columns = ['command_type_id', 'command_type_name', 'command_class', 'target_file_name', 'target_file_path']

    add_columns = ['command_type_id', 'command_type_name', 'command_class', 'target_file_name', 'target_file_path']



    validators_columns = {
                    'target_file_name':[ValidateBatchFunctionName()]
                }

class ResultModelView(ModelView):
    
    datamodel = SQLAInterface(AgResult)
    list_title    = "Command 처리 결과"

    list_template = 'listWithJson.html'
    extra_args = {
        'buttonList':[
         {'text':'WAS 상태','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_key_value1=get_server_stat'}
        ,{'text':'WAS 상태(X)','id':'toggle_bt2','bt_group':'1','onclick':'_flt_4_key_value1=get_server_stat'}
        ,{'text':'domain.xml','id':'toggle_bt3','bt_group':'1','onclick':'_flt_0_key_value1=domain.xml&_flt_1_result_status=NOCHANGE'}
        ,{'text':'JEUSMain.xml','id':'toggle_bt4','bt_group':'1','onclick':'_flt_0_key_value1=JEUSMain.xml&_flt_1_result_status=NOCHANGE'}
        ,{'text':'WEBMain.xml','id':'toggle_bt5','bt_group':'1','onclick':'_flt_0_key_value1=WEBMain.xml&_flt_1_result_status=NOCHANGE'}
        ,{'text':'http.m','id':'toggle_bt6','bt_group':'1','onclick':'_flt_0_key_value1=http.m&_flt_1_result_status=NOCHANGE'}
        ,{'text':'mwmanager','id':'toggle_bt7','bt_group':'1','onclick':'_flt_0_key_value1=mwmanager'}
        ],
        'selectList':[
         {'text':'Hostname','id':'host-selector','combind':'1','type':'child'}
        ,{'text':'Agent ID','id':'agent-selector','combind':'1','type':'child'}
        ],
        'inputList':[
         {'text':'Command ID','id':'command-id','combind':'0','condition':'_flt_3_command_id=','size':15}
        ]
        }

    list_columns  = ['command_id','agent_id', 'repetition_seq', 'host_id', 'key_value1'\
                    , 'colored_result_status', 'sub_result', 'create_on', 'key_value2','complited_date']
    label_columns = {'command_id':'Command ID'
                    ,'agent_id':'Agent ID'
                    ,'repetition_seq':'SEQ'
                    ,'host_id':'HOST ID'
                    ,'key_value1':'파일명(기능명)'
                    ,'key_value2':'파일위치(새부기능)'
                    ,'colored_result_status':'상태'
                    ,'sub_result':'수신정보'
                    ,'create_on':'수신일시'
                    ,'complited_date':'반영일시'
                     }

    edit_columns = ['host_id', 'key_value1', 'key_value2'\
                    , 'result_text', 'result_hash', 'result_status']

    search_columns = ['command_id','agent_id','host_id','key_value1','result_status','create_on']
    base_order = ('create_on', 'desc')
    base_permissions = ['can_list', 'can_show', 'can_edit', 'can_delete']

    formatters_columns={'create_on': lambda x: x.strftime('%Y.%m.%d %H:%M') if x else ''}
    


    @action("update_config","Update Config","진짜로?","fa-rocket",single=False)
    def update_config(self, items):

        for result in items:

            if result.result_status.name not in ['CREATE','ERROR']:
                continue

            file_name = result.key_value1
            rtn = 0

            ar = AutorunResult(result=result)

            rtn, msg = ar.call_autorun_func()
            
            if rtn == 0 and msg == 'No Autorun':
                ar.update_result_status('ERROR', 'Autorun mapping not found for: ' + file_name)
                
            db.session.commit()

        self.update_redirect()
        return redirect(self.get_redirect())

class CommandDetailModelView(ModelView):
    
    datamodel = SQLAInterface(AgCommandDetail)
    list_title    = "Agent별 Command 목록"    

    list_columns  = ['command_id', 'agent_id', 'repetition_seq', 'command_type_id'\
                    , 'command_class', 'target_file_path', 'target_file_name'\
                    , 'additional_params', 'colored_command_status', 'result_received_date']
    label_columns = {'command_id':'Command ID'
                    ,'agent_id':'Agent ID'
                    ,'repetition_seq':'SEQ'
                    ,'command_type_id':'Command Type ID'
                    ,'command_class':'수행기능'
                    ,'colored_command_status':'수행상태'
                    ,'result_received_date':'회신일시'
                     }

    base_permissions = ['can_list', 'can_show', 'can_delete']
    base_order   = ('create_on', 'desc')
    search_columns = ['command_id','agent_id','command_type_id','command_class']



    related_views = [ResultModelView]

class CommandMasterModelView(ModelView):
    
    datamodel = SQLAInterface(AgCommandMaster)
 
    list_title    = "Command 목록"    

    list_columns  = ['command_id', 'ag_command_type', 'periodic_type', 'ag_agent', 'ag_agent_group'\
                    , 'time_to_exe', 'interval_type', 'cycle_to_exe', 'time_to_stop', 'broadcast_callback', 'create_on']
    label_columns = {'command_id':'Command ID'
                    ,'ag_command_type':'Command Type ID'
                    ,'periodic_type':'실행 구분'
                    ,'ag_agent':'대상 Agent'
                    ,'ag_agent_group':'대상 Agent 그룹'
                    ,'time_to_exe':'최초실행일시'
                    ,'interval_type':'실행주기유형'
                    ,'cycle_to_exe':'실행주기(정수)'
                    ,'time_to_stop':'종료일시'
                    ,'additional_params':'Parameters'
                    ,'command_sender':'Command를 보내는 곳'
                    ,'result_receiver':'Result 받는 곳'
                    ,'target_object':'Target Object'
                    ,'broadcast_callback':'Broadcast Callback'
                     }

    add_columns  = ['command_id', 'ag_command_type', 'broadcast_callback', 'ag_agent', 'ag_agent_group', 'periodic_type'\
                    , 'command_sender', 'time_to_exe', 'interval_type', 'cycle_to_exe', 'time_to_stop'\
                    , 'additional_params', 'target_object']

    edit_columns  = ['command_id', 'ag_command_type', 'broadcast_callback', 'ag_agent', 'ag_agent_group', 'periodic_type'\
                    , 'command_sender', 'time_to_exe', 'interval_type', 'cycle_to_exe', 'time_to_stop'\
                    , 'additional_params', 'cancel_yn']

    add_template = 'agent/command_master_add.html'
    edit_template = 'agent/command_master_edit.html'

    base_order   = ('create_on', 'desc')
    extra_args   = {'broadcast_callbacks': list(broadcast_callback_registry.keys())}

    validators_columns = {
                    'cycle_to_exe':[RequiredOnContidion('periodic_type', 'PERIODIC', message='주기작업의 경우 필수입력항목입니다.')]
                  , 'time_to_exe':[RequiredOnContidion('periodic_type', 'ONETIME', message='1회성작업의 경우 필수입력항목입니다.')]
                }



    related_views = [CommandDetailModelView]

class CommandMasterAliveView(ModelView):
    
    datamodel = SQLAInterface(AgCommandMaster)

    list_title    = "활성 Command 목록"    
    list_columns  = ['command_id', 'ag_command_type', 'periodic_type', 'ag_agent', 'ag_agent_group'\
                    , 'time_to_exe', 'interval_type', 'cycle_to_exe', 'time_to_stop', 'create_on']
    label_columns = {'command_id':'Command ID'
                    ,'ag_command_type':'Command Type ID'
                    ,'periodic_type':'실행 구분'
                    ,'ag_agent':'대상 Agent'
                    ,'ag_agent_group':'대상 Agent 그룹'
                    ,'time_to_exe':'최초실행일시'
                    ,'interval_type':'실행주기유형'
                    ,'cycle_to_exe':'실행주기(정수)'
                    ,'time_to_stop':'종료일시'
                    ,'additional_params':'Parameters'
                     }

    base_order   = ('create_on', 'desc')

    base_filters = [['finished_yn', FilterEqual, 'NO']]
    base_permissions = ['can_list', 'can_show', 'can_edit']
    related_views = [CommandDetailModelView]

    @action("cancel_commands","Cancel Commands","진짜로?","fa-rocket",single=False)
    def cancel_commands(self, items):

        for cid in items:
            try:
                scheduler.remove_job('CreDetail_'+ cid.command_id)
            except apscheduler.jobstores.base.JobLookupError as e:
                print('cancel_commands : ',e)

        cids = [item.command_id for item in items]
        cancel_commands(cids)
        db.session.commit()

        self.update_redirect()
        return redirect(self.get_redirect())

class AutorunResultModelView(ModelView):
    
    datamodel = SQLAInterface(AgAutorunResult)

    list_title    = "Result 자동실행 목록"    
    list_columns  = ['autorun_id', 'autorun_type', 'target_file_name', 'command_id'\
                    , 'autorun_func', 'autorun_param', 'create_on']
    label_columns = {'autorun_id':'자동실행 JOB ID'
                    ,'autorun_type':'자동실행 Type'
                    ,'target_file_name':'대상파일/기능'
                    ,'command_id':'Command ID'
                    ,'autorun_func':'자동실행 기능'
                    ,'autorun_param':'Parameter'
                     }
    
    description_columns = {
        'target_file_name': '파일명, 기능명 또는 정규식(Regex)을 입력하십시오. (예: run\.agent\.(sh|bat))'
    }

    add_columns  = ['autorun_id', 'autorun_type', 'target_file_name', 'command_id'\
                    , 'autorun_func', 'autorun_param']

    edit_columns  = ['autorun_id', 'autorun_type', 'target_file_name', 'command_id'\
                    , 'autorun_func', 'autorun_param']

    base_order   = ('create_on', 'desc')

    validators_columns = {
                    'target_file_name':[RequiredOnContidion('autorun_type', 'FILENAME', message='대상 File 또는 기능명을 입력하세요.')]
                  , 'command_id':[RequiredOnContidion('autorun_type', 'COMMAND', message='Command ID를 입력하세요.')]
                }



class AjaxView(BaseView):

    route_base = '/ajax'
    default_view = 'ajax1'
	
    @expose('/ajax2', methods=['GET'])
    @has_access
    def ajax2(self):
        
        time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
		
        return jsonify({'time':time})

    @expose('/ajax1', methods=['GET'])
    @has_access
    def ajax1(self):
        
        time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
		
        return self.render_template("ajax1.html",name='mwm', time=time)



#appbuilder.add_view(AjaxView, "ajax test", category="ajax")
#appbuilder.add_link("ajax test", href="/ajax/ajax1", category="ajax")

appbuilder.add_view(
    AgentModelView,
    "Agent",
    icon="fa-folder-open-o",
    category="Agent&Command",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    AgentGroupModelView,
    "Agent 그룹",
    icon="fa-folder-open-o",
    category="Agent&Command"
)
appbuilder.add_separator("Agent&Command")
appbuilder.add_view(
    FileModelView,
    "Files",
    icon="fa-folder-open-o",
    category="Agent&Command"
)
appbuilder.add_separator("Agent&Command")
appbuilder.add_view(
    CommandTypeModelView,
    "Command 유형",
    icon="fa-folder-open-o",
    category="Agent&Command"
)
appbuilder.add_view(
    CommandHelperModelView,
    "Command 규칙 관리",
    icon="fa-folder-open-o",
    category="Agent&Command"
)
appbuilder.add_view(
    CommandMasterModelView,
    "Command 목록",
    icon="fa-folder-open-o",
    category="Agent&Command"
)
appbuilder.add_view(
    CommandMasterAliveView,
    "활성 Command 목록",
    icon="fa-folder-open-o",
    category="Agent&Command"
)
appbuilder.add_view(
    CommandDetailModelView,
    "Command 상세",
    icon="fa-folder-open-o",
    category="Agent&Command"
)
appbuilder.add_view(
    AutorunResultModelView,
    "Command 처리결과 자동 반영 설정",
    icon="fa-folder-open-o",
    category="Agent&Command"
)
appbuilder.add_view(
    ResultModelView,
    "Command 처리결과",
    icon="fa-folder-open-o",
    category="Agent&Command"
)