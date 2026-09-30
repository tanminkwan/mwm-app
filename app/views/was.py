from flask import g, render_template, Flask, request, jsonify\
     , send_file, redirect, url_for, render_template_string, flash, abort
from flask_appbuilder.models.sqla.interface import SQLAInterface
from flask_appbuilder import BaseView, ModelView, ModelRestApi, MultipleView, MasterDetailView
from flask_appbuilder import expose, has_access
from flask_appbuilder.actions import action
from flask_appbuilder.api import ModelRestApi, BaseApi, expose, safe, rison, protect
from flask_appbuilder.models.sqla.filters import get_field_setup_query, BaseFilter\
    , FilterEqualFunction, FilterNotEqual, FilterInFunction, FilterStartsWith, FilterEqual, FilterGreater, FilterSmaller
from app import app, appbuilder, db #, mongoClient, dbMongo, footprint, vv_P_secs
#from .models import Server, JeusContainer, Host
from app.models.was import MwServer, MwWas, MwWasInstance, MwWeb, MwWebVhost, MwWasHttpListener\
    , MwWasWebtobConnector, MwWebReverseproxy, MwDatasource, MwApplication\
    , MwWebServer, MwWebUri, MwWaschangeHistory, MwWebchangeHistory\
    , MwBizCategory, MwAppMaster, MwDBMaster, MwWebDomain, MwWebSsl\
    , MwEtcSslDomain
from app.models.knowledge import UtTag, UtHtmlContent
from app.sqls.was import get_was_instance_id, get_landscape
from app.sqls.relationship import get_was_relationship, get_web_relationship
from app.sqls.agent import insert_command_master, get_agent, get_agents, create_connect_ssl_for_httplistener, create_connect_ssl_real_ip_for_httplistener, create_connect_ssl_real_ip
from app.sqls.batch import create_ssl_info, re_register_web_from_text, re_register_was_from_text
from app.sqls.monitor import select_row, select_item, select_items
from .common import FilterStartsWithFunction, FilterNotNull, FilterIsNull, \
    get_mw_user, get_userid, ShowWithIds, ListAdvanced, visible_to_current_user

import json
# Excel
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta

# Chart
#import io
#import plotly.express as px

class DatasourceModelView(ModelView):
    
    datamodel = SQLAInterface(MwDatasource)
    
    list_title   = "WAS Datasource 목록"    
    list_columns = ['was_id', 'was_name', 'datasource_id', 'db_jndi_id', 'vender_name'\
                   , 'db_user_id', 'db_dbms_id', 'db_pool_min', 'db_pool_max', 'db_server_name', 'datasource_class_name']
    label_columns = {'was_id':'WAS'
                    ,'was_name':'WAS 명'
                    ,'datasource_id':'DataSource Id'
                    ,'db_jndi_id':'Export(JNDI) 이름'
                    ,'db_property':'DB 접속정보'
                    ,'vender_name':'JDBC Vendor'
                    ,'db_server_name':'DB 서버'
                    ,'db_dbms_id':'DB 명'
                    ,'datasource_class_name':'JDBC Class'
                    ,'db_user_id':'DB User'
                    ,'db_pool_min':'DB Pool Min'
                    ,'db_pool_max':'DB Pool Max'
                    ,'db_pool_step':'DB Pool Step'
                    ,'db_pool_period':'DB Pool Perid'}

    search_columns = ['mw_was', 'db_user_id', 'db_dbms_id', 'db_server_name']



class WaschangeHistoryModelView(ModelView):
    
    datamodel = SQLAInterface(MwWaschangeHistory)
    show_template = 'showWithJson.html'
    show_widget  = ShowWithIds
    
    extra_args = {'buttonList':[
            {'text':'WAS 속성 변경내역','id':'json-button','onclick':'renderJson("Changed Object","WAS 속성 변경내역")'}
          , {'text':'WAS 변경 전 내역','id':'json-button','onclick':'renderJson("Old Was Object","WAS 변경 전 내역")'}
        ]}

    list_title   = "WAS Config 변경 이력"    
    list_columns = ['show_diff', 'mw_was.was_id', 'create_on']
    label_columns = {
        'show_diff':'Diff',
        'mw_was.was_id':'WAS',
        'create_on':'변경일시'
        }

    search_columns = ['mw_was','create_on']
    base_order = ('create_on', 'desc')
    base_permissions = ['can_list', 'can_show', 'can_delete']



class ApplicationModelView(ModelView):
    
    datamodel = SQLAInterface(MwApplication)

    list_title   = "WAS Application 목록"    
    list_columns = ['was_id', 'application_id', 'application_home', 'context_path'\
                    ,'filtered_text', 'deploy_type']
    label_columns = {'was_id':'WAS'
                    ,'application_id':'Application ID'
                    ,'application_home':'Application 배포 위치'
                    ,'context_path':'Context Path'
                    ,'filtered_text':'색출정보'
                    ,'deploy_type':'배포Type'}

    search_columns = ['mw_was']


class WasHttpListenerModelView(ModelView):

    datamodel = SQLAInterface(MwWasHttpListener)

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_title   = "WAS Http Listener 목록"    
    list_columns = ['was_id', 'was_instance_id', 'host_id', 'webconnection_id', 'listen_port', 'min_thread_pool_count', 'max_thread_pool_count', 'ssl_yn', 'domain_name'\
                    ,'ssl_cn', 'ssl_notafter', 'ssl_update_dt']
    label_columns = {'was_id':'WAS Domain'
                    ,'was_instance_id':'MS intance id'
                    ,'host_id':'HOST ID'
                    ,'webconnection_id':'Web Connection ID'
                    ,'listen_port':'서비스Port'
                    ,'ssl_yn':'SSL 여부'
                    ,'domain_name':'도메인명'
                    ,'ssl_cn': 'CN'
                    ,'ssl_update_dt':'인증서 확인일'
                    ,'ssl_notafter':'만료일'
                    ,'min_thread_pool_count':'Min Thread pool 개수'
                    ,'max_thread_pool_count':'Max Thread pool 개수'}

    search_columns = ['ssl_yn', 'was_id', 'mw_was_instance', 'webconnection_id']

    edit_exclude_columns = ['httplistener_object','create_on']
    add_exclude_columns = ['httplistener_object','create_on']
    search_exclude_columns = ['httplistener_object']

    extra_args = {
        'inputList':[
         {'text':'WAS ID','id':'was-id','combind':'0','condition':'_flt_2_was_id=','size':20}
        ],
        'buttonList':[
         {'text':'SSL만 조회','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_ssl_yn=YES'},
        ],
        }

    @action("call_connect_ssl", "Call Connect SSL", "", "fa-rocket", single=False)
    def callConnectSSL(self, items):
        for item in items:
            success, msg = create_connect_ssl_for_httplistener(item)
            if not success:
                flash(msg, 'warning')
            else:
                flash(f"{item.domain_name}:{item.listen_port} - {msg}", 'info')

        self.update_redirect()
        return redirect(self.get_redirect())

    @action("call_connect_ssl_real_ip", "Call connect SSL(real ip)", "Are you sure you want to call connect SSL with Real IP?", "fa-lock", single=False)
    def callConnectSSLRealIp(self, items):
        for item in items:
            success, msg = create_connect_ssl_real_ip_for_httplistener(item)
            if not success:
                flash(msg, 'warning')
            else:
                flash(f"{item.domain_name}:{item.listen_port} (IP: {item.mw_was_instance.mw_server.ip_address}) - {msg}", 'info')

        self.update_redirect()
        return redirect(self.get_redirect())



class WasWebtobConnectorModelView(ModelView):

    datamodel = SQLAInterface(MwWasWebtobConnector)

    list_title   = "WAS Webtob Connector 목록"    
    list_columns = ['was_id', 'was_instance_id', 'host_id', 'webconnection_id', 'web_host_id'\
                    ,'jsv_port', 'jsv_id', 'thread_pool_count', 'disable_pipe','web_home']
    label_columns = {'was_id':'WAS Domain'
                    ,'was_instance_id':'MS intance id'
                    ,'host_id':'HOST ID'
                    ,'webconnection_id':'Web Connection ID'
                    ,'web_host_id':'Web서버 host id'
                    ,'jsv_port':'Web서버 JSV Port'
                    ,'jsv_id':'JSV ID'
                    ,'web_home':'webtob home'
                    ,'thread_pool_count':'JSV Session 개수'}

    search_columns = ['was_id', 'mw_was_instance', 'web_host_id']

    edit_exclude_columns = ['webtobconnector_object','create_on']
    add_exclude_columns = ['webtobconnector_object','create_on']
    search_exclude_columns = ['webtobconnector_object']



class WasInstanceModelView(ModelView):

    datamodel = SQLAInterface(MwWasInstance)

    list_title   = "WAS Instance 목록"    
    list_columns = ['was_id', 'was_instance_id', 'landscape', 'was_instance_port'\
                    , 'host_id', 'c_os_type', 'c_ip_address','min_heap_size', 'max_heap_size', 'clustered_yn'\
                    , 'colored_apm_type', 'use_yn', 'mw_datasource', 'mw_application']
    label_columns = {'was_id':'WAS Domain'
                    ,'was_instance_id':'MS intance id'
                    ,'was_instance_port':'Port'
                    ,'host_id':'설치 장비'
                    ,'c_os_type':'OS'
                    ,'newgeneration_yn':'차세대'
                    ,'c_ip_address':'IP'
                    ,'min_heap_size':'Min Heep Size(M)'
                    ,'max_heap_size':'Max Heep Size(M)'
                    ,'clustered_yn':'Clustering'
                    ,'apm_type':'APM'
                    ,'use_yn':'사용구분'
                    ,'colored_apm_type':'APM'
                    ,'mw_datasource':'Data Source'
                    ,'mw_application':'Application'}

    edit_exclude_columns = ['create_on']
    base_order = ('was_instance_id', 'asc')
    search_columns = ['was_id', 'was_instance_id', 'host_id', 'apm_type'\
                    ,'min_heap_size', 'max_heap_size', 'clustered_yn']


    related_views = [WasWebtobConnectorModelView, WasHttpListenerModelView]

class WasCommonView(ModelView):
    
    datamodel = SQLAInterface(MwWas)

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    extra_args = {
        'buttonList':[
         {'text':'운영','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_landscape=PROD'}
        ,{'text':'개발','id':'toggle_bt2','bt_group':'1','onclick':'_flt_0_landscape=DEV'}
        ,{'text':'이관','id':'toggle_bt3','bt_group':'1','onclick':'_flt_0_landscape=TEST'}
        ,{'text':'차세대','id':'toggle_bt3','bt_group':'2','onclick':'_flt_0_newgeneration_yn=YES'}
        ,{'text':'유지','id':'toggle_bt4','bt_group':'2','onclick':'_flt_0_newgeneration_yn=NO'}
        ],
        'selectList':[
         {'text':'Hostname','id':'host-selector','combind':'0','type':'parent'}
        ],
        'inputList':[
         {'text':'WAS 이름','id':'was-name','combind':'0','condition':'_flt_2_was_name=','size':20}
        ]
        }

    list_columns = ['c_was_id', 'was_name', 'colored_landscape'\
                    , 'sys_user', 'located_host_id', 'c_os_type', 'link_ip_address', 'running_type', 'standby_host_id'\
                    , 'view_domaininfo','view_relationship']
    label_columns = {'c_was_id':'WAS Domain'
                    ,'was_name':'WAS 이름'
                    ,'newgeneration_yn':'차세대'
                    ,'adminserver_name':'AdminServer 이름'
                    ,'landscape':'Landscape'
                    ,'colored_landscape':'Landscape'
                    ,'t__it_incharge':'담당자'
                    ,'sys_user':'서버계정'
                    ,'running_type':'이중화'
                    ,'standby_host_id':'StandBy'
                    ,'located_host_id':'설치 node'
                    ,'c_os_type':'OS'
                    ,'link_ip_address':'IP'
                    ,'view_domaininfo':'Config'
                    ,'view_relationship':'관계도'}

    edit_exclude_columns = ['cluster_object','was_object','license_update_date','jeus_properties_update_date','create_on']
    add_exclude_columns = ['cluster_object','was_object','license_update_date','jeus_properties_update_date','create_on']
    search_exclude_columns = ['cluster_object','was_object']
    show_exclude_columns = ['cluster_object', 'was_object']
    base_order = ('c_was_id', 'asc')

class WasModelView(WasCommonView):
    list_title   = "JEUS 목록"    
    base_filters = [['use_yn', FilterEqual, 'YES']]
    related_views = [WasInstanceModelView, ApplicationModelView, DatasourceModelView, WaschangeHistoryModelView]

    @action("call_filtered_info","Update Findings in App","","fa-rocket",single=False)
    def callFilteredInfo(self, items):
        for item in items:
            agent_rec = get_agent(item.agent_id)
            if not agent_rec:
                continue
            recs, _ = select_items('mw_application', 'application_home', dict(was_id=item.was_id))
            for rec in recs:
                addparam = item.was_id
                if rec.application_home.endswith(".war"):
                    addparam += ' ' + rec.application_home
                elif rec.application_home.endswith(".jar"):
                    continue
                else:
                    addparam += ' ' + rec.application_home

                if item.mw_server.os_type.name == 'WINDOWS':
                    addparam += ' ' + '^.*log4.*.jar'
                    insert_command_master('EXE.FILTER4WIN', [agent_rec.agent_id], addparam)
                elif item.mw_server.os_type.name == 'HPUX':
                    addparam += ' ' + '*log4*.jar'
                    insert_command_master('RUN.FILTER', [agent_rec.agent_id], addparam, out_CID=True)
                else:
                    filter_dict = dict(was_id=item.was_id
                                    , application_home=rec.application_home)
                    appRec, _ = \
                            select_item('mw_application', 'application_id', filter_dict)
                    addparam += ' ' + '*log4*.jar' + ' ' + appRec.application_id
                    insert_command_master('EXE.FILTER', [agent_rec.agent_id], addparam)

        db.session.commit()
        self.update_redirect()
        return redirect(self.get_redirect())

    @action("re_register","Was Text 기반 재등록","진짜로?","fa-rocket",single=False)
    def re_register(self, items):
        for item in items:
            rtn, msg = re_register_was_from_text('UI_ACTION', item.id)
            if rtn > 0:
                flash(f"WAS '{item.was_id}' re-registered successfully.", "success")
            else:
                flash(f"WAS '{item.was_id}' re-registration failed: {msg}", "danger")
            db.session.commit()
        self.update_redirect()
        return redirect(self.get_redirect())

class WasDisusedModelView(WasCommonView):
    list_title   = "JEUS 불용 목록"
    base_filters = [['use_yn', FilterEqual, 'NO']]

    @action("activate", "사용 전환", "정말 사용으로 전환하시겠습니까?", "fa-play", single=False)
    def activate(self, items):
        for item in items:
            item.use_yn = 'YES'
            db.session.add(item)
        db.session.commit()
        return redirect(self.get_redirect())

class WasLinkView(ModelView):
    
    datamodel = SQLAInterface(MwWas)

    list_title   = "JEUS 목록(차세대-운영)"    
    list_columns = ['was_id', 'was_name', 'link_ip_address', 'located_host_id', 'newgeneration_yn', 'colored_landscape'\
                    , 't__it_incharge']
    label_columns = {'was_id':'WAS Domain'
                    ,'was_name':'WAS 이름'
                    ,'newgeneration_yn':'차세대'
                    ,'adminserver_name':'AdminServer 이름'
                    ,'landscape':'운영/이관/개발/DR'
                    ,'colored_landscape':'운영/이관/개발/DR'
                    ,'t__it_incharge':'담당자'
                    ,'located_host_id':'설치 node'
                    ,'link_ip_address':'WebAdmin Link'}

    search_exclude_columns = ['cluster_object','was_object']

    base_filters = [['landscape', FilterEqual, 'PROD']
                    ,['newgeneration_yn', FilterEqual, 'YES']
                    ]
    base_order = ('was_id', 'asc')    
    base_permissions = ['can_list']
    
    related_views = [WasInstanceModelView, ApplicationModelView, DatasourceModelView]

class WasLicenseView(ModelView):
    
    datamodel = SQLAInterface(MwWas)

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    extra_args = {
        'buttonList':[
         {'text':'운영','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_landscape=PROD'}
        ,{'text':'개발','id':'toggle_bt2','bt_group':'1','onclick':'_flt_0_landscape=DEV'}
        ,{'text':'이관','id':'toggle_bt3','bt_group':'1','onclick':'_flt_0_landscape=TEST'}
        ,{'text':'차세대','id':'toggle_bt3','bt_group':'2','onclick':'_flt_0_newgeneration_yn=YES'}
        ,{'text':'유지','id':'toggle_bt4','bt_group':'2','onclick':'_flt_0_newgeneration_yn=NO'}
        ],
        'selectList':[
         {'text':'Hostname','id':'host-selector','combind':'0','type':'parent'}
        ],
        'inputList':[
         {'text':'WAS 이름','id':'was-name','combind':'0','condition':'_flt_2_was_name=','size':20}
        ]
        }

    list_title   = "JEUS License 정보"    
    list_columns = ['c_was_id', 'was_name', 'link_ip_address', 'located_host_id'\
                    , 'newgeneration_yn', 'colored_landscape', 'use_yn'\
                    , 'license_update_date', 'license_cpu', 'license_edition', 'version_info'\
                    , 'license_hostname', 'license_issue_date', 'license_due_date'
                    ]
    label_columns = {'c_was_id':'WAS Domain'
                    ,'was_name':'WAS 이름'
                    ,'newgeneration_yn':'차세대'
                    ,'adminserver_name':'AdminServer 이름'
                    ,'landscape':'운영/이관/개발/DR'
                    ,'colored_landscape':'운영/이관/개발'
                    ,'use_yn':'사용여부'
                    ,'license_update_date':'license 확인'
                    ,'license_cpu':'CPU수량'
                    ,'license_edition':'Edition'
                    ,'version_info':'WAS 버젼'
                    ,'license_hostname':'license서버'
                    ,'license_issue_date':'license발급일'
                    ,'license_due_date':'license만료일'
                    ,'located_host_id':'WAS node'
                    ,'link_ip_address':'IP Address'}
    show_columns = ['license_text']
    search_exclude_columns = ['cluster_object','was_object']

    formatters_columns={'license_update_date': lambda x:x.strftime('%Y-%m-%d %H:%M') if x else ''
                        ,'license_issue_date': lambda x:x.strftime('%Y-%m-%d') if x else ''
                        ,'license_due_date': lambda x:x.strftime('%Y-%m-%d') if x else ''}


    base_order = ('was_id', 'asc')    
    base_permissions = ['can_list','can_show']

    @action("call_file_jeus_license","Update Jeus License","","fa-rocket",single=False)
    def callFileJeusLicense(self, items):

        for item in items:

            if item.mw_server.os_type.name == 'WINDOWS':
                agent_id = item.located_host_id.upper() + '_' + item.sys_user + '_J'
            else:
                agent_id = item.located_host_id + '_' + item.sys_user + '_J'

            agent_rec = get_agent(agent_id)

            if not agent_rec:
                continue

            addparam = item.was_id

            filter_dict = dict(mapping_key='DOMAIN_HOME'
                            , target_file_name=item.was_id
                            , agent_id=agent_id)
            rec, _ = select_row('ag_command_helper', filter_dict)

            if rec:
                addparam += ' ' + rec.string_to_replace
            else:
                addparam += ' /sw/jeus/bin/'

            #JEUS7, JEUS8 인 경우 ExeScript 실행
            if item.mw_server.os_type.name == 'WINDOWS':
                insert_command_master('EXE.JEUS.LICENSE4WIN', [agent_rec.agent_id], addparam)
            elif item.mw_server.os_type.name == 'HPUX':
                insert_command_master('RUN.JEUS.LICENSE', [agent_rec.agent_id], addparam, out_CID=True)
            else:
                insert_command_master('EXE.JEUS.LICENSE', [agent_rec.agent_id], addparam)

        db.session.commit()

        self.update_redirect()
        return redirect(self.get_redirect())

class WebLicenseView(ModelView):
    
    datamodel = SQLAInterface(MwWeb)

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    extra_args = {
        'buttonList':[
         {'text':'운영-차세대','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_newgeneration_yn=YES&_flt_0_landscape=PROD'}
        ,{'text':'운영-유지','id':'toggle_bt2','bt_group':'1','onclick':'_flt_0_newgeneration_yn=NO&_flt_0_landscape=PROD'}
        ,{'text':'개발-차세대','id':'toggle_bt3','bt_group':'1','onclick':'_flt_0_newgeneration_yn=YES&_flt_0_landscape=DEV'}
        ,{'text':'개발-유지','id':'toggle_bt4','bt_group':'1','onclick':'_flt_0_newgeneration_yn=NO&_flt_0_landscape=DEV'}
        ,{'text':'이관-차세대','id':'toggle_bt5','bt_group':'1','onclick':'_flt_0_newgeneration_yn=YES&_flt_0_landscape=TEST'}
        ,{'text':'이관-유지','id':'toggle_bt6','bt_group':'1','onclick':'_flt_0_newgeneration_yn=NO&_flt_0_landscape=TEST'}
        ],
        'selectList':[
         {'text':'Hostname','id':'host-selector','combind':'0','type':'parent'}
        ],
        'inputList':[
         {'text':'WEB 이름','id':'web-name','combind':'0','condition':'_flt_2_web_name=','size':20}
        ]
        }

    list_title   = "WEBTOB License 정보"    
    list_columns = ['c_host_id', 'c_ip_address', 'port', 'colored_landscape','newgeneration_yn'\
                    , 'web_name','port', 'colored_built_type', 'use_yn'\
                    , 'license_update_date', 'license_cpu', 'license_edition'\
                    , 'license_hostname', 'license_issue_date', 'license_due_date'
                    ]
    label_columns = {'c_host_id':'Host ID'
                    ,'port':'Port'
                    ,'newgeneration_yn':'차세대여부'
                    ,'colored_landscape':'Landscape'
                    ,'web_name':'설명'
                    ,'port':'Port'
                    ,'doc_dir':'DOC root'
                    ,'c_ip_address':'IP'
                    ,'colored_built_type':'내장/외장'
                    ,'use_yn':'사용여부'
                    ,'license_update_date':'license 확인'
                    ,'license_cpu':'CPU수량'
                    ,'license_edition':'Edition'
                    ,'license_hostname':'license서버'
                    ,'license_issue_date':'license발급일'
                    ,'license_due_date':'license만료일'
                    ,'located_host_id':'WAS node'
                    ,'link_ip_address':'IP Address'}

    show_columns = ['license_text']
    search_exclude_columns = ['ssl_object','proxy_ssl_object','logging_object','errordocument_object'\
                            , 'ext_object', 'tcpgw_object', 'httpm_object']

    formatters_columns={'license_update_date': lambda x:x.strftime('%Y-%m-%d %H:%M') if x else ''
                        ,'license_issue_date': lambda x:x.strftime('%Y-%m-%d') if x else ''
                        ,'license_due_date': lambda x:x.strftime('%Y-%m-%d') if x else ''}


    base_order = ('host_id', 'asc')
    base_permissions = ['can_list','can_show']

    @action("call_file_webtob_license","Update Webtob License","","fa-rocket",single=False)
    def callFileWebtobLicense(self, items):

        for item in items:

            agent_rec = get_agent(item.agent_id)

            if not agent_rec:
                continue

            addparam = item.host_id + '__' + str(item.port) + ' ' + item.web_home + '/bin/' + ' ' + item.web_home + '/license/license.dat'

            #HPUX 인 경우 ExeScript 의 stdout을 못가져옴
            if item.mw_server.os_type.name == 'WINDOWS':
                addparam = addparam.replace('/','\\')
                insert_command_master('EXE.WEBTOB.LICENSE4WIN', [agent_rec.agent_id], addparam)
            elif item.mw_server.os_type.name == 'HPUX':
                insert_command_master('RUN.WEBTOB.LICENSE', [agent_rec.agent_id], addparam, out_CID=True)
            else:
                insert_command_master('EXE.WEBTOB.LICENSE', [agent_rec.agent_id], addparam)

        db.session.commit()

        self.update_redirect()
        return redirect(self.get_redirect())

class WebVhostModelView(ModelView):

    datamodel = SQLAInterface(MwWebVhost)

    list_title   = "WEBTOB VHOST 목록"    
    list_columns = ['mw_web', 'vhost_id', 'web_ports', 'ssl_yn','urlrewrite_yn'\
                    ,'domain_name','host_alias','mw_web_uri','mw_web_server'\
                    ,'mw_web_reverseproxy']
    label_columns = {'mw_web':'WEB'
                    ,'vhost_id':'VHOST ID'
                    ,'web_ports':'Web Port'
                    ,'domain_name':'Domain 이름'
                    ,'host_alias':'HOST ALIAS'
                    ,'urlrewrite_yn':'URL Rewrite 여부'
                    ,'ssl_yn':'SSL 여부'
                    ,'mw_web_uri':'URI'
                    ,'mw_web_server':'Server'
                    ,'mw_web_reverseproxy':'Reverse Proxy'}
                    
    edit_exclude_columns = ['uri_object','create_on']
    add_exclude_columns = ['uri_object','create_on']
    search_exclude_columns = ['uri_object']



    @action("call_url_rewrite","Call URL Rewrite","","fa-rocket",single=False)
    def callUrlRewrote(self, items):

        for item in items:

            agent_rec = get_agent(item.mw_web.agent_id)

            if not agent_rec:
                continue

            insert_command_master('READ.URLREWRITE', [agent_rec.agent_id]\
                    , item.urlrewrite_config)

        db.session.commit()

        self.update_redirect()
        return redirect(self.get_redirect())

class WebSslModelView(ModelView):

    datamodel = SQLAInterface(MwWebSsl)

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_title   = "WEBTOB SSL File 목록"    
    list_columns = ['host_id', 'mw_web.web_name', 'ssl_certi','notbefore','notafter'\
                    ,'t__cn','mw_web_domain','update_dt']
    label_columns = {'host_id':'Host ID'
                    ,'mw_web.web_name':'Web서버'
                    ,'ssl_certi':'SSL Certificate File'
                    ,'notbefore':'시작일'
                    ,'notafter':'만료일'
                    ,'t__cn':'CN'
                    ,'mw_web_domain':'Domain들'
                    ,'update_dt':'확인일시'
                    }
    search_columns = ['host_id', 'notafter', 'update_dt', 'ssl_certi']
    formatters_columns={'update_dt': lambda x: x.strftime('%Y.%m.%d %H:%M') if x else ''}         


    extra_args = {
        'inputList':[
         {'text':'HOSTNAME','id':'host-name','combind':'0','condition':'_flt_2_host_id=','size':20}
        ]
        }

class WebDomainModelView(ModelView):

    datamodel = SQLAInterface(MwWebDomain)

    def almost_expired():
        now = datetime.now()
        plus_15 = now + timedelta(days=30)
        filter_str = f'_flt_1_notafter={now.strftime("%m/%d/%Y")}&_flt_2_notafter={plus_15.strftime("%m/%d/%Y")}'
        return filter_str
    
    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_title   = "WEBTOB Domain 목록"    
    list_columns = ['host_id', 'mw_web_vhost.mw_web.web_name', 't__domain', 'ssl_yn'\
                    ,'t__ssl_certi','notbefore','notafter','notbefore_ca','notafter_ca','t__cn','update_dt']
    label_columns = {'host_id':'Host ID'
                    ,'mw_web_vhost.mw_web.web_name':'Web서버'
                    ,'t__domain':'URL'
                    ,'ssl_yn':'SSL 여부'
                    ,'t__ssl_certi':'SSL Certificate File'
                    ,'notbefore':'시작일'
                    ,'notafter':'만료일'
                    ,'notbefore_ca':'시작일(ICA)'
                    ,'notafter_ca':'만료일(ICA)'
                    ,'t__cn':'CN'
                    ,'update_dt':'확인일시'
                    }
    search_columns = ['host_id', 'ssl_yn', 'domain_name','notafter', 'notafter_ca'\
                    , 'update_dt', 'ssl_certi']
    formatters_columns={'update_dt': lambda x:x.strftime('%Y.%m.%d %H:%M') if x is not None else ""}             
    base_filters = []
    
    search_form_query_rel_fields = {}
    
    search_filters = {
        'notafter': [FilterIsNull, FilterGreater, FilterSmaller],
        'notafter_ca': [FilterIsNull, FilterGreater, FilterSmaller],
        'update_dt': [FilterIsNull, FilterGreater, FilterSmaller]
    }
    
    extra_args = {
        'inputList':[
         {'text':'HOSTNAME','id':'host-name','combind':'0','condition':'_flt_2_host_id=','size':20}
        ],
        'buttonList':[
         {'text':'SSL만 조회','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_ssl_yn=YES'},
         {'text':'SSL만료 임박','id':'toggle_bt2','bt_group':'2','onclick':almost_expired()}
        ],
        }

    @action("call_connect_ssl","Call Connect SSL","","fa-rocket",single=False)
    def callConnectSSL(self, items):

        for item in items:

            if item.ssl_yn.name == 'YES':

                agent_rec = get_agent(item.mw_web_vhost.mw_web.agent_id)

                if not agent_rec:
                    continue

                insert_command_master('CALL.GET_SSL_CERTI', [agent_rec.agent_id], item.domain_name+':'+item.port)

        db.session.commit()

        self.update_redirect()
        return redirect(self.get_redirect())

    @action("call_connect_ssl_real_ip", "Call connect SSL(real ip)", "Are you sure you want to call connect SSL with Real IP?", "fa-lock", single=False)
    def callConnectSSLRealIp(self, items):
        for item in items:
            if item.ssl_yn.name == 'YES':
                agent_rec = get_agent(item.mw_web_vhost.mw_web.agent_id)
                if not agent_rec:
                    continue

                # Real IP 추출
                real_ip = ""
                if item.mw_web_vhost and item.mw_web_vhost.mw_web and item.mw_web_vhost.mw_web.mw_server:
                    real_ip = item.mw_web_vhost.mw_web.mw_server.ip_address

                create_connect_ssl_real_ip(agent_rec.agent_id, item.domain_name, item.port, real_ip)

        db.session.commit()
        self.update_redirect()
        return redirect(self.get_redirect())

class WebServerModelView(ModelView):
    
    datamodel = SQLAInterface(MwWebServer)

    list_title   = "WEBTOB SERVER 목록"    
    list_columns = ['mw_web', 'svr_id', 'svr_type', 'min_proc_count', 'max_proc_count', 'mw_web_vhost', 'mw_was_webtobconnector']
    label_columns = {'mw_web':'WEB'
                    ,'svr_id':'SVR ID'
                    ,'svr_type':'SVR Type'
                    ,'min_proc_count':'session min'
                    ,'max_proc_count':'session max'
                    ,'mw_web_vhost':'V Host'
                    ,'mw_was_webtobconnector':'WAS정보'}

    edit_exclude_columns = ['monitor_now', 'monitor_history', 'create_on']
    add_exclude_columns = ['monitor_now', 'monitor_history', 'create_on']
    search_exclude_columns = ['monitor_now', 'monitor_history'] 


class WebUriModelView(ModelView):
    
    datamodel = SQLAInterface(MwWebUri)

    list_title   = "WEBTOB URI 목록"    
    list_columns = ['mw_web', 'uri_id', 'svr_type', 'uri','mw_web_server','mw_web_vhost']
    label_columns = {'mw_web':'WEB'
                    ,'uri_id':'URI 이름'
                    ,'svr_type':'SVR Type'
                    ,'uri':'URI'
                    ,'mw_web_server':'Server이름'
                    ,'mw_web_vhost':'V Host'}

    edit_exclude_columns = ['create_on']
    add_exclude_columns = ['create_on']



class WebReverseproxyModelView(ModelView):
    
    datamodel = SQLAInterface(MwWebReverseproxy)

    list_title   = "WEBTOB REVERSE PROXY 목록"    
    list_columns = ['mw_web', 'reverseproxy_id', 'context_path', 'ssl_yn'\
                    ,'target_ip_address','target_port','target_context_path'\
                    ,'max_connection_count','mw_web_vhost']
    label_columns = {'mw_web':'WEB'
                    ,'reverseproxy_id':'Reverse Proxy 이름'
                    ,'context_path':'Context Path'
                    ,'ssl_yn':'SSL 여부'
                    ,'target_ip_address':'Target IP'
                    ,'target_port':'Target Port'
                    ,'target_context_path':'Target Context Path'
                    ,'max_connection_count':'Max Conn Count'
                    ,'mw_web_vhost':'V Host'
                    }

    edit_exclude_columns = ['create_on']
    add_exclude_columns = ['create_on']



class WebchangeHistoryModelView(ModelView):
    
    datamodel = SQLAInterface(MwWebchangeHistory)
    show_template = 'showWithJson.html'
    show_widget  = ShowWithIds

    extra_args = {'buttonList':[
            {'text':'WEB 속성 변경내역','id':'json-button','onclick':'renderJson("Changed Object","WEB 속성 변경내역")'}
          , {'text':'WEB 변경 전 내역','id':'json-button','onclick':'renderJson("Old Httpm Object","WEB 변경 전 내역")'}
        ]}

    list_title   = "WEBTOB Config 변경 이력"    
    list_columns = ['show_diff', 'mw_web.host_id', 'mw_web.port', 'create_on']
    label_columns = {
        'show_diff':'Diff',        
        'mw_web.host_id':'Host ID',
        'mw_web.port':'Port',
        'create_on':'변경일시'
        }

    search_columns = ['mw_web','create_on']
    base_order = ('create_on', 'desc')
    base_permissions = ['can_list', 'can_show', 'can_delete']


class WebCommonView(ModelView):
    
    datamodel = SQLAInterface(MwWeb)

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    extra_args = {
        'buttonList':[
         {'text':'운영-차세대','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_newgeneration_yn=YES&_flt_0_landscape=PROD'}
        ,{'text':'운영-유지','id':'toggle_bt2','bt_group':'1','onclick':'_flt_0_newgeneration_yn=NO&_flt_0_landscape=PROD'}
        ,{'text':'개발-차세대','id':'toggle_bt3','bt_group':'1','onclick':'_flt_0_newgeneration_yn=YES&_flt_0_landscape=DEV'}
        ,{'text':'개발-유지','id':'toggle_bt4','bt_group':'1','onclick':'_flt_0_newgeneration_yn=NO&_flt_0_landscape=DEV'}
        ,{'text':'이관-차세대','id':'toggle_bt5','bt_group':'1','onclick':'_flt_0_newgeneration_yn=YES&_flt_0_landscape=TEST'}
        ,{'text':'이관-유지','id':'toggle_bt6','bt_group':'1','onclick':'_flt_0_newgeneration_yn=NO&_flt_0_landscape=TEST'}
        ],
        'selectList':[
         {'text':'Hostname','id':'host-selector','combind':'0','type':'parent'}
        ],
        'inputList':[
         {'text':'WEB 이름','id':'web-name','combind':'0','condition':'_flt_2_web_name=','size':20}
        ]
        }

    list_columns = ['c_host_id', 'c_ip_address', 'jsv_port', 'colored_landscape','newgeneration_yn', 'linked_was'\
                    , 'web_name','colored_built_type', 'sys_user', 'c_ssl_yn' \
                    , 'service_port', 'view_relationship', 'view_webinfo']
    label_columns = {'c_host_id':'Host ID'
                    ,'jsv_port':'JSV Port'
                    ,'linked_was':'연결 WAS'
                    ,'newgeneration_yn':'차세대여부'
                    ,'colored_landscape':'Landscape'
                    ,'web_name':'설명'
                    ,'service_port':'Port'
                    ,'doc_dir':'DOC root'
                    ,'c_ip_address':'IP'
                    ,'colored_built_type':'내장/외장'
                    ,'c_ssl_yn':'SSL설치여부'
                    ,'sys_user':'서버계정'
                    ,'mw_was':'연결 WAS'
                    ,'view_relationship':'구성도'
                    ,'view_webinfo':'http.m' }

    edit_exclude_columns = ['ssl_object', 'logging_object', 'errordocument_object'\
            , 'proxy_ssl_object', 'tcpgw_object', 'httpm_object','ext_object', 'license_object', 'create_on']
    add_exclude_columns = ['ssl_object', 'logging_object', 'errordocument_object'\
            , 'proxy_ssl_object', 'tcpgw_object', 'httpm_object', 'ext_object', 'license_object', 'create_on']
    search_exclude_columns = ['ssl_object', 'logging_object', 'errordocument_object'\
            , 'proxy_ssl_object', 'tcpgw_object', 'httpm_object', 'ext_object', 'license_object']
    show_exclude_columns = ['ssl_object', 'logging_object', 'errordocument_object'\
            , 'proxy_ssl_object', 'tcpgw_object', 'httpm_object', 'ext_object', 'license_object']

    base_order = ('host_id', 'asc')

class WebModelView(WebCommonView):
    list_title   = "WEBTOB 목록"    
    base_filters = [['use_yn', FilterEqual, 'YES']]
    related_views = [WebServerModelView, WebVhostModelView, WebUriModelView, WebReverseproxyModelView]

    @action("multi","Excel Download","","fa-rocket",single=False)
    def myaction(self, items):
        output = BytesIO()
        df = pd.read_sql(sql = "select * from mw_web", con = db.session.bind)
        writer = pd.ExcelWriter(output, engine="xlsxwriter")
        df.to_excel(writer, 'data', index=False)
        writer.save()
        output.seek(0)
        return send_file(output, download_name='mw_web.xlsx', as_attachment=True)


    @action("re_register","Web Text 기반 재등록","진짜로?","fa-rocket",single=False)
    def re_register(self, items):
        for item in items:
            rtn, msg = re_register_web_from_text('UI_ACTION', item.id)
            if rtn > 0:
                flash(f"Web '{item.host_id}' re-registered successfully.", "success")
            else:
                flash(f"Web '{item.host_id}' re-registration failed: {msg}", "danger")
            db.session.commit()
        self.update_redirect()
        return redirect(self.get_redirect())

class WebDisusedModelView(WebCommonView):
    list_title   = "WEBTOB 불용 목록"
    base_filters = [['use_yn', FilterEqual, 'NO']]

    @action("activate", "사용 전환", "정말 사용으로 전환하시겠습니까?", "fa-play", single=False)
    def activate(self, items):
        for item in items:
            item.use_yn = 'YES'
            db.session.add(item)
        db.session.commit()
        return redirect(self.get_redirect())


class EtcSslDomainCommonView(ModelView):

    datamodel = SQLAInterface(MwEtcSslDomain)

    def almost_expired():
        now = datetime.now()
        plus_30 = now + timedelta(days=30)
        filter_str = f'_flt_1_notafter={now.strftime("%m/%d/%Y")}&_flt_2_notafter={plus_30.strftime("%m/%d/%Y")}'
        return filter_str

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_columns = ['host_id', 't__domain', 'notbefore', 'notafter',
                    't__cn', 'managed_yn', 'description', 'update_dt']
    label_columns = {
        'host_id': 'Host ID',
        't__domain': 'URL',
        'notbefore': '시작일',
        'notafter': '만료일',
        't__cn': 'CN',
        'managed_yn': 'MW관리대상',
        'description': '설명',
        'update_dt': '확인일시',
        'use_yn': '사용여부',
        'agent_id': 'Agent ID',
        'domain_name': 'Domain',
        'port': 'Port',
    }

    edit_columns = ['host_id', 'domain_name', 'port', 'agent_id', 'description',
                    'use_yn']
    add_columns  = ['host_id', 'domain_name', 'port', 'agent_id', 'description',
                    'use_yn']

    search_columns = ['host_id', 'domain_name', 'notafter', 'update_dt',
                      'managed_yn']

    search_filters = {
        'notafter': [FilterIsNull, FilterGreater, FilterSmaller],
        'update_dt': [FilterIsNull, FilterGreater, FilterSmaller]
    }

    formatters_columns = {
        'update_dt': lambda x: x.strftime('%Y.%m.%d %H:%M') if x else '',
        'notafter': lambda x: x.strftime('%Y-%m-%d') if x else '',
        'notbefore': lambda x: x.strftime('%Y-%m-%d') if x else '',
    }

    extra_args = {
        'inputList': [
            {'text': 'HOSTNAME', 'id': 'host-name', 'combind': '0',
             'condition': '_flt_2_host_id=', 'size': 20}
        ],
        'buttonList': [
            {'text': 'SSL만료 임박', 'id': 'toggle_bt1', 'bt_group': '1',
             'onclick': almost_expired()}
        ],
    }

    base_order = ('host_id', 'asc')

    @action("call_connect_ssl", "Call Connect SSL", "", "fa-rocket", single=False)
    def callConnectSSL(self, items):
        for item in items:
            if not item.agent_id:
                continue

            agent_rec = get_agent(item.agent_id)

            if not agent_rec:
                continue

            insert_command_master('CALL.GET_SSL_CERTI',
                                 [agent_rec.agent_id],
                                 item.domain_name + ':' + item.port)

        db.session.commit()
        self.update_redirect()
        return redirect(self.get_redirect())

    @action("call_connect_ssl_real_ip", "Call connect SSL(real ip)", "Are you sure you want to call connect SSL with Real IP?", "fa-lock", single=False)
    def callConnectSSLRealIp(self, items):
        for item in items:
            if not item.agent_id:
                continue

            agent_rec = get_agent(item.agent_id)
            if not agent_rec:
                continue

            # Real IP 추출
            real_ip = ""
            if item.mw_server:
                real_ip = item.mw_server.ip_address

            create_connect_ssl_real_ip(agent_rec.agent_id, item.domain_name, item.port, real_ip)

        db.session.commit()
        self.update_redirect()
        return redirect(self.get_redirect())


class EtcSslDomainModelView(EtcSslDomainCommonView):
    list_title = "기타 SSL Domain"
    base_filters = [['use_yn', FilterEqual, 'YES']]


class EtcSslDomainDisusedModelView(EtcSslDomainCommonView):
    list_title = "불용 기타 SSL Domain"
    base_filters = [['use_yn', FilterEqual, 'NO']]
    base_permissions = ['can_list', 'can_show', 'can_edit', 'can_delete']


class BizCategoryModelView(ModelView):
    
    datamodel = SQLAInterface(MwBizCategory)

    list_title   = "업무 구분 목록"    
    list_columns = ['biz_category', 'biz_category_name', 'mw_was', 'mw_web']
    label_columns = {'biz_category':'업무 구분 코드'
                    ,'biz_category_name':'업무 명칭'
                    ,'mw_was':'WAS'
                    ,'mw_web':'WEB'
                    }

    edit_exclude_columns = ['create_on']
    add_exclude_columns = ['create_on']


    related_views = [WasModelView, WebModelView]

class DBMasterModelView(ModelView):
    
    datamodel = SQLAInterface(MwDBMaster)

    list_title   = "DB Master"    
    list_columns = ['db_dbms_id', 'landscape', 'vender_name', 'db_server_name', 'db_server_port', 'description', 'mw_app_master']
    label_columns = {'db_dbms_id':'DBMS id'
                    ,'landscape':'Landscape'
                    ,'vender_name':'Vendor'
                    ,'mw_app_master':'Applications'
                    ,'description':'설명'
                    ,'db_server_name':'DB Server'
                    ,'db_server_port':'DB Service port'
                    }

    edit_exclude_columns = ['create_on']
    add_exclude_columns = ['create_on']



class AppMasterModelView(ModelView):
    
    datamodel = SQLAInterface(MwAppMaster)

    list_template = 'listWithJson.html'

    extra_args = {
        'buttonList':[
         {'text':'운영','id':'toggle_bt1','bt_group':'1','onclick':'_flt_0_landscape=PROD'}
        ,{'text':'개발','id':'toggle_bt2','bt_group':'1','onclick':'_flt_0_landscape=DEV'}
        ],
        'inputList':[
         {'text':'App ID','id':'app-id','combind':'0','condition':'_flt_2_app_id=','size':12}
        ,{'text':'App 이름','id':'app-name','combind':'0','condition':'_flt_2_app_name=','size':12}
        ,{'text':'Host ID','id':'app-server','combind':'0','condition':'_flt_2_app_servers=','size':12}
        ]
        }

    list_title   = "Application Master"    
    list_columns = ['app_id', 'landscape', 'app_name', 'description', 'app_servers','mw_db_master','mw_was_instance']
    label_columns = {'app_id':'App id'
                    ,'landscape':'Landscape'
                    ,'app_name':'App 이름'
                    ,'description':'설명/특이사항'
                    ,'app_servers':'appliaction 설치 서버'
                    ,'mw_db_master':'사용 DB'
                    ,'mw_was_instance':'WAS Instacne'
                    }

    edit_exclude_columns = ['create_on']
    add_exclude_columns = ['create_on']

    base_filters = [['app_id', FilterNotEqual, 'NOAPP']
                    ]

class ServerModelView(ModelView):

    datamodel = SQLAInterface(MwServer)
    
    list_title   = "서버 목록"    
    list_columns = ['host_id', 'server_name', 'colored_landscape', 'ip_address', 'vip_address', 'colored_os'\
                    , 'jdk_version', 'running_type','was_yn', 'web_yn']
    label_columns = {'host_id':'Host Name'
                    ,'server_name':'서버이름'
                    ,'landscape':'Landscape'
                    ,'colored_landscape':'Landscape'
                    ,'os_type':'OS 종류'
                    ,'colored_os':'OS 종류'
                    ,'encoding':'OS엔코딩'
                    ,'jdk_version':'JDK 버전'
                    ,'ip_address':'ip address'
                    ,'vip_address':'vip address'
                    ,'running_type':'A-S 구분'
                    ,'primary_host_id':'Primary서버'
                    ,'mw_was_instance':'WAS'
                    ,'web_yn':'WEB Y/N'
                    ,'was_yn':'WAS Y/N'
                    ,'ut_tag':'업무 도메인'
                    ,'ut_tag_itdep':'업무부서'
                    ,'ut_tag_bizdep':'IT부서'
                     }

    edit_columns = ['host_id', 'server_name', 'landscape', 'os_type'\
                    , 'encoding', 'ip_address', 'vip_address', 'jdk_version'\
                    ,'running_type', 'primary_host_id', 'ut_tag', 'ut_tag_itdep', 'ut_tag_bizdep']

    add_columns = ['host_id', 'server_name', 'landscape', 'os_type'\
                    , 'encoding', 'ip_address', 'vip_address', 'jdk_version'\
                    ,'running_type', 'primary_host_id', 'ut_tag', 'ut_tag_itdep', 'ut_tag_bizdep']

    search_columns = ['host_id', 'ip_address', 'vip_address', 'landscape', 'running_type']

    base_order = ('host_id', 'asc')    



    related_views = [WasModelView, WebModelView]

    @action("multi","Excel Download","","fa-rocket",single=False)
    def myaction(self, items):
        output = BytesIO()
    
        df = pd.read_sql(sql = "select * from mw_server", con = db.session.bind)

        writer = pd.ExcelWriter(output, engine="xlsxwriter")
        df.to_excel(writer, 'data', index=False)
        writer.save()
        output.seek(0)
        return send_file(output, download_name='mw_server.xlsx', as_attachment=True)

class MasterDetailViews(MasterDetailView):
    datamodel = SQLAInterface(MwWas)
    master_div_width = 2
    related_views = [WasInstanceModelView]

class ShortQueries(BaseApi):

    resource_name = 'select'

    @expose('/web_yn/<host_id>/<app_id>', methods=['GET'])
    #@protect()
    def web_yn(self, host_id, app_id):
        print (host_id, app_id)
        return jsonify({'return_code':1}), 201



# class FootPrintApi(BaseApi):
# 
#     resource_name = 'footprint'
# 
#     @expose('/footprint', methods=['POST'])
# #    @protect(allow_browser_login=True)
#     def postFootPrint(self, **kwargs):
#         data = json.loads(request.data)
#         records = data['payLoad']
#         [r.update({'ip':request.remote_addr}) for r in records]
#         print(records)
#         rtn = footprint.insert_many(records)
#         print('rtn:',rtn.inserted_ids)
#         if rtn:
#             return jsonify({'return_code':1}), 201


# /json/htmlviewer 가 읽을 수 있는 (테이블, 본문 컬럼, 제목 컬럼) — getHtmlButton 호출과 맞춘다
HTML_VIEWER_FIELDS = {
    ('ut_html_content', 'content_html', 'content_name'): UtHtmlContent,
}


class JsonView(BaseView):

    route_base = '/json'
    default_view = 'jsonviewer'

    @expose('/htmlviewer/<table_name>/<column_name>/<tcolumn_name>/<key>', methods=['GET'])
    @has_access
    def htmlviewer(self, table_name, column_name, tcolumn_name, key):

        # 주소의 테이블·컬럼 이름을 그대로 쓰면 아무 테이블이나 읽힌다 (예: ab_user.password).
        # getHtmlButton 이 만드는 조합만 받고, 목록 화면과 같은 그룹 기준으로 거른다.
        model = HTML_VIEWER_FIELDS.get((table_name, column_name, tcolumn_name))
        if model is None or not key.isdigit():
            abort(404)

        row = visible_to_current_user(model).filter(model.id == int(key)).first()
        if row is None:
            abort(404)

        return jsonify({'html':getattr(row, column_name), 'title':getattr(row, tcolumn_name)})

    @expose('/jsonviewer/<category>/<key>', methods=['GET'])
    @has_access
    def jsonviewer(self, category, key):

        if category == 'WAS':
            item, _ = select_item('mw_was', 'was_object', {'was_id':key})
        elif category == 'WEB':
            host_id, port = key.split('__')
            item, _ = select_item('mw_web', 'httpm_object', {'host_id':host_id,'port':port})

        return jsonify({'json':item[0]})

    @expose('/relationship/<category>/<key>', methods=['GET'])
    @has_access
    def relationship(self, category, key):

        if category == 'WAS':
            json = get_was_relationship(key)
        elif category == 'WEB':
            host_id, port = key.split('__')
            json = get_web_relationship(host_id, int(port))

        return jsonify({'json':json})

class ExampleApi(BaseApi):

    resource_name = 'example'
    greeting_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string"
                }
            }
        }
    apispec_parameter_schemas = {
            "greeting_schema": greeting_schema
        }

    @expose('/greeting', methods=['GET'])
    @protect(allow_browser_login=True)
    @rison(greeting_schema)    
    def greeting(self, **kwargs):
        """Greeting
        ---
        get:
            responses:
                200:
                    description: 사용자에게 인사하기
                    content:
                        application/json:
                            schema:
                                type: object
                                properties:
                                    message:
                                        type: string
                400:
                    $ref: '#/components/responses/400'
                                        
        """
        if 'name' in kwargs['rison']:
            return self.response(
                200,
                message=f"Hello {kwargs['rison']['name']}"
                )
        return self.response_400(message="잘못된 parameter")

    @expose('/error')
    @protect()
    @safe
    def error(self):
        """Error 500
        ---
        get:
            responses:
                500:
                    $ref: '#/components/responses/500'
        """
        raise Exception

@app.errorhandler(404)
def page_not_found(e):
    return (
        render_template(
            "404.html", base_template=appbuilder.base_template, appbuilder=appbuilder
        ),
        404,
    )

db.create_all()

# ---------------------------------------------------------
# 미사용(use_yn='NO') 도메인에 속한 데이터 조회 제한 로직 (Ver 2.0)
# ---------------------------------------------------------
# 1-hop 관계는 점(.) 표기법 사용, 2-hop 이상은 FilterInFunction을 사용하여 조인 오류 방지
def get_active_was_ids():
    return [r.was_id for r in db.session.query(MwWas.was_id).filter(MwWas.use_yn == 'YES').all()]

def get_active_web_ids():
    return [r.id for r in db.session.query(MwWeb.id).filter(MwWeb.use_yn == 'YES').all()]

def get_active_vhost_ids():
    return [r.id for r in db.session.query(MwWebVhost.id).join(MwWeb).filter(MwWeb.use_yn == 'YES').all()]

was_filter_targets = [
    (WasInstanceModelView, 'mw_was.use_yn', FilterEqual, 'YES'),
    (DatasourceModelView, 'mw_was.use_yn', FilterEqual, 'YES'),
    (ApplicationModelView, 'mw_was.use_yn', FilterEqual, 'YES'),
    (WasHttpListenerModelView, 'was_id', FilterInFunction, get_active_was_ids),
    (WasWebtobConnectorModelView, 'was_id', FilterInFunction, get_active_was_ids)
]

web_filter_targets = [
    (WebServerModelView, 'mw_web.use_yn', FilterEqual, 'YES'),
    (WebUriModelView, 'mw_web.use_yn', FilterEqual, 'YES'),
    (WebReverseproxyModelView, 'mw_web.use_yn', FilterEqual, 'YES'),
    (WebVhostModelView, 'mw_web.use_yn', FilterEqual, 'YES'),
    (WebSslModelView, 'mw_web.use_yn', FilterEqual, 'YES'),
    (WebDomainModelView, 'mw_web_vhost_id', FilterInFunction, get_active_vhost_ids)
]

for view, path, flt, val in was_filter_targets + web_filter_targets:
    if not hasattr(view, 'base_filters') or view.base_filters is None:
        view.base_filters = []
    view.base_filters.append([path, flt, val])


appbuilder.add_view(
    ServerModelView,
    "서버 목록",
    icon="fa-folder-open-o",
    category="Server",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    DBMasterModelView,
    "DB Master",
    icon="fa-folder-open-o",
    category="Server",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    AppMasterModelView,
    "App Master",
    icon="fa-folder-open-o",
    category="Server",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    WasModelView,
    "WAS 목록",
    icon="fa-folder-open-o",
    category="Was",
    category_icon="fa-envelope"
)
"""
appbuilder.add_view(
    MasterDetailViews,
    "WAS별 MS 목록",
    icon="fa-envelope",
    category="Was"
)
"""
appbuilder.add_view(
    WasInstanceModelView,
    "JEUS MS 목록",
    icon="fa-folder-open-o",
    category="Was"
)
appbuilder.add_view(
    WasHttpListenerModelView,
    "Was Http Listener 목록",
    icon="fa-folder-open-o",
    category="Was"
)
appbuilder.add_view(
    WasWebtobConnectorModelView,
    "Was Webtob Connector 목록",
    icon="fa-folder-open-o",
    category="Was"
)
appbuilder.add_view(
    DatasourceModelView,
    "Datasource 목록",
    icon="fa-folder-open-o",
    category="Was"
)
appbuilder.add_view(
    ApplicationModelView,
    "Application 목록",
    icon="fa-folder-open-o",
    category="Was"
)
appbuilder.add_separator("Was")
appbuilder.add_view(
    WaschangeHistoryModelView,
    "WAS Config 변경이력",
    icon="fa-folder-open-o",
    category="Was",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    WasLicenseView,
    "JEUS License 정보",
    icon="fa-folder-open-o",
    category="Was"
)
appbuilder.add_view(
    WasDisusedModelView,
    "JEUS 불용 목록",
    icon="fa-trash-o",
    category="Was"
)
appbuilder.add_view(
    WasLinkView,
    "JEUS WebAdmin Link(차세대-운영)",
    icon="fa-folder-open-o",
    category="Was"
)
appbuilder.add_view(
    WebModelView,
    "WEB 목록",
    icon="fa-folder-open-o",
    category="Web",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    WebServerModelView,
    "Web Server 목록",
    icon="fa-folder-open-o",
    category="Web"
)
appbuilder.add_view(
    WebUriModelView,
    "Web URI 목록",
    icon="fa-folder-open-o",
    category="Web"
)
appbuilder.add_view(
    WebReverseproxyModelView,
    "Reverse Proxy 목록",
    icon="fa-folder-open-o",
    category="Web"
)
appbuilder.add_view(
    WebVhostModelView,
    "Web VHost 목록",
    icon="fa-folder-open-o",
    category="Web"
)
appbuilder.add_view(
    WebSslModelView,
    "SSL FILE 목록",
    icon="fa-folder-open-o",
    category="Web"
)
appbuilder.add_view(
    WebDomainModelView,
    "Domain 이름 목록",
    icon="fa-folder-open-o",
    category="Web"
)
appbuilder.add_separator("Web")
appbuilder.add_view(
    WebchangeHistoryModelView,
    "WEBTOB Config 변경이력",
    icon="fa-folder-open-o",
    category="Web",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    WebLicenseView,
    "WEBTOB License 정보",
    icon="fa-folder-open-o",
    category="Web"
)
appbuilder.add_view(
    WebDisusedModelView,
    "WEBTOB 불용 목록",
    icon="fa-trash-o",
    category="Web"
)
appbuilder.add_separator("Web")
appbuilder.add_view(
    EtcSslDomainModelView,
    "기타 SSL Domain",
    icon="fa-globe",
    category="Web"
)
appbuilder.add_view(
    EtcSslDomainDisusedModelView,
    "불용 기타 SSL Domain",
    icon="fa-trash-o",
    category="Web"
)

"""
appbuilder.add_view(
    MutipleViews,
    "Multi View",
    icon="fa-envelope",
    category="Servers"
)
appbuilder.add_api(HostModelApi)
appbuilder.add_api(JeusContainerModelApi)
"""
appbuilder.add_api(ExampleApi)
# appbuilder.add_api(FootPrintApi)
appbuilder.add_api(ShortQueries)
appbuilder.add_api(JsonView)