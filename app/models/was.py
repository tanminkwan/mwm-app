from flask import g, url_for
from flask_appbuilder import Model
from markupsafe import Markup
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy import Column, Integer, String, ForeignKey\
, DateTime, Enum, UniqueConstraint, ForeignKeyConstraint\
, Table, Date, Text
from sqlalchemy.orm import relationship, validates
import enum
from datetime import datetime
from flask_appbuilder.models.mixins import FileColumn
from flask_appbuilder.models.decorators import renders
from flask_appbuilder.filemanager import get_file_original_name
from .common import get_user, EncodingEnum, WarEnum, WebconnEnum, BuiltEnum\
    , ApmEnum, SvrTypeEnum, RunEnum, YnEnum, LocationEnum, OSEnum, RuningTypeEnum\
    , getColoredText, isNotNull, getJsonButton, getDiagramButton, SslCertTypeEnum

assoc_dbmaster_appmaster = Table('mw_dbmaster_appmaster', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_dbmaster', Integer, ForeignKey('mw_db_master.id', ondelete='CASCADE')),
                                  Column('id_of_appmaster', Integer, ForeignKey('mw_app_master.id', ondelete='CASCADE'))
)    

class MwDBMaster(Model):
    __tablename__ = "mw_db_master"
    t__table_comment = {"comment":"DB Master"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    landscape        = Column(Enum(LocationEnum), info={'enum_class':LocationEnum}, comment='Landscape', nullable=False) #운영/이관/개발/DR 구분 (manual)
    db_dbms_id       = Column(String(50), comment='DBMS id', nullable=False) # DBMS ID (auto)
    vender_name      = Column(String(50), comment='Vendor') # Vendor (auto)
    db_server_name   = Column(String(50), comment='DB Server') # DB Server IP (auto)
    db_server_port   = Column(Integer, comment='DB Service port') # DB Server Port (auto)
    description      = Column(String(500), comment='설명')
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(landscape, db_dbms_id)

    __table_args__ = (
        t__table_comment,
    )

    def __repr__(self):
        return self.db_dbms_id

class MwAppMaster(Model):
    __tablename__ = "mw_app_master"
    t__table_comment = {"comment":"Application Master"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    app_id           = Column(String(50), comment='application id', nullable=False)
    app_name         = Column(String(200), comment='appliaction 명칭')
    app_servers      = Column(String(200), comment='appliaction 설치 서버')
    description      = Column(Text, comment='설명')
    landscape        = Column(Enum(LocationEnum), info={'enum_class':LocationEnum}, comment='Landscape') #운영/이관/개발/DR 구분 (manual)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(app_id)

    __table_args__ = (
        t__table_comment,
    )

    mw_was_instance  = relationship('MwWasInstance')
    mw_db_master  = relationship('MwDBMaster', secondary=assoc_dbmaster_appmaster, backref='mw_app_master')

    def __repr__(self):
        return self.app_id

class MwBizCategory(Model):
    __tablename__ = "mw_biz_category"
    t__table_comment = {"comment":"Application code"}
    function_comments = {}


    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    biz_category     = Column(String(50), nullable=False)
    biz_category_name = Column(String(200))
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    __table_args__ = (
        t__table_comment,
    )

    UniqueConstraint(biz_category)

    def __repr__(self):
        return self.biz_category + ':' + self.biz_category_name

class MwDatasource(Model):
    __tablename__ = "mw_datasource"
    t__table_comment = {"comment":"WAS의 Datasource"}
    function_comments = {}


    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    was_id           = Column(String(30), ForeignKey('mw_was.was_id', ondelete='CASCADE'), nullable=False, comment='WAS domain id') #HOST 이름 (auto)
    datasource_id    = Column(String(50), nullable=False, comment='Datasource id') #datasource ID (auto)
    db_jndi_id       = Column(String(50), comment='Export(JNDI) 이름') # Export(JNDI) 이름 (auto)
    datasource_type  = Column(String(50), comment='Datasource Type') # Datasource Type (auto)
    datasource_class_name  = Column(String(200), comment='JDBC Class') # JDBC Class (auto)
    vender_name      = Column(String(50), comment='Vendor') # Vendor (auto)
    db_server_name   = Column(String(50), comment='DB Server') # DB Server IP (auto)
    db_server_port   = Column(Integer, comment='DB Service port') # DB Server Port (auto)
    db_dbms_id       = Column(String(50), comment='DBMS id') # DBMS ID (auto)
    db_user_id       = Column(String(30), comment='DBMS user') # DB User (auto)
    db_property      = Column(String(1000), comment='DBMS 접속정보') # DB 접속정보 (auto)
    stmt_query_timeout     = Column(Integer, comment='SQL timeout') # SQL timeout (auto)
    db_pool_min      = Column(Integer, comment='DB Pool Min') # DB Pool Min (auto)
    db_pool_max      = Column(Integer, comment='DB Pool Max') # DB Pool Max (auto)
    db_pool_step     = Column(Integer, comment='DB Pool Step') # DB Pool Step (auto)
    db_pool_period   = Column(Integer, comment='DB Pool Period') # DB Pool Step (auto)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    mw_was           = relationship('MwWas')
    UniqueConstraint(was_id, datasource_id)

    __table_args__ = (
        t__table_comment,
    )

    def __repr__(self):
        return self.datasource_id + ':' + self.db_user_id

    def was_name(self):
        was_name = self.mw_was.was_name if self.mw_was.was_name else ''
        return Markup('<p style="color:blue;">' + was_name + '</p>')

assoc_datasource_instance = Table('mw_datasource_wasinstance', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_datasource', Integer, ForeignKey('mw_datasource.id', ondelete='CASCADE')),
                                  Column('id_of_was_instance', Integer, ForeignKey('mw_was_instance.id', ondelete='CASCADE'))
)

class MwApplication(Model):
    __tablename__ = "mw_application"
    t__table_comment = {"comment":"WAS에 deploy된 Application"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    was_id           = Column(String(30), ForeignKey('mw_was.was_id', ondelete='CASCADE'), nullable=False, comment='WAS domain id') #WAS도메인 ID
    application_id   = Column(String(30), nullable=False, comment='Application id') #Application ID (auto)
    application_desc = Column(String(30), comment='Application 설명') #Application 설명 (manual)
    application_home = Column(String(200), comment='Application 배포 위치') # Application 배포 위치 (auto)
    context_path     = Column(String(200), comment='Context Path') # Context Path (auto)
    deploy_type      = Column(Enum(WarEnum), info={'enum_class':WarEnum}, comment='배포Type') #배포Type (auto)
    filtered_text    = Column(Text, comment='색출 정보') # 정보(auto:json)
    filtered_update_date = Column(DateTime(), comment='색출 정보 갱신일시')
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    mw_was           = relationship('MwWas')
    UniqueConstraint(was_id, application_id)

    __table_args__ = (
        t__table_comment,
    )

    def __repr__(self):
        return self.application_id

assoc_application_instance = Table('mw_application_wasinstance', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_application', Integer, ForeignKey('mw_application.id', ondelete='CASCADE')),
                                  Column('id_of_was_instance', Integer, ForeignKey('mw_was_instance.id', ondelete='CASCADE'))
)    

class MwWaschangeHistory(Model):
    __tablename__ = "mw_was_change_history"
    t__table_comment = {"comment":"WAS 변경 이력"}
    function_comments = {}
    
    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    mw_was_id        = Column(Integer, ForeignKey('mw_was.id', ondelete='CASCADE'), nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    old_was_object   = Column(JSONB, comment='변경전 WAS 정보') # domian.xml 또는 JEUSMain.xml 정보(auto:json)
    changed_object   = Column(JSONB, comment='변경 내역') # 변경내역 (auto:json)
    user_id          = Column(String(50), default=get_user, nullable=False)
    old_was_text     = Column(Text, comment='변경전 WAS 정보') # domian.xml 또는 JEUSMain.xml 정보(auto:json)
    
    UniqueConstraint(mw_was_id, create_on)

    __table_args__ = (
        t__table_comment,
    )

    mw_was        = relationship('MwWas', back_populates='mw_was_change_history')

    def show_diff(self):
        return Markup('<a href="/diff/was/'+str(self.id)+'" class="btn btn-sm btn-default" data-toggle="tooltip" rel="tooltip" title="" data-original-title="레코드 보기"><i class="fa fa-search"></i></a>')

    def __repr__(self):
        return self.mw_was.was_id + '(' + self.create_on.strftime('%Y-%m-%d %H:%M') + ')'

assoc_tag_was = Table('ut_tag_was', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_was', Integer, ForeignKey('mw_was.id', ondelete='CASCADE'))
)    

assoc_tag_wasinstance = Table('ut_tag_wasinstance', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_wasinstance', Integer, ForeignKey('mw_was_instance.id', ondelete='CASCADE'))
)    

assoc_tag_web = Table('ut_tag_web', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_web', Integer, ForeignKey('mw_web.id', ondelete='CASCADE'))
)    

assoc_tag_server = Table('ut_tag_server', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_server', Integer, ForeignKey('mw_server.id', ondelete='CASCADE'))
)    

assoc_tag_server_itdep = Table('ut_tag_server_itdep', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_server', Integer, ForeignKey('mw_server.id', ondelete='CASCADE'))
)    

assoc_tag_server_bizdep = Table('ut_tag_server_bizdep', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_server', Integer, ForeignKey('mw_server.id', ondelete='CASCADE'))
)    

assoc_was_web = Table('mw_was_web', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_was', Integer, ForeignKey('mw_was.id', ondelete='CASCADE')),
                                  Column('id_of_web', Integer, ForeignKey('mw_web.id', ondelete='CASCADE'))
)

class MwWas(Model):
    __tablename__ = "mw_was"
    t__table_comment = {"comment":"WAS domain"}
    function_comments = {}
    
    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    was_id           = Column(String(30), nullable=False, comment='WAS domain id') #WAS도메인 ID (auto)
    was_name         = Column(String(50), comment='WAS 이름/용도') # WAS도메인 이름 (manual)
    newgeneration_yn = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='차세대여부') #차세대 구분 (manual)
    adminserver_name = Column(String(30), comment='adminserver 이름') # AdminServer 이름
#    adminserver_url  = Column(String(200)) # AdminServer url
#    adminserver_port = Column(Integer, nullable=False) #관리 port
    was_home         = Column(String(200), comment='JEUS home') # WAS 위치(bin 기준?) (manual)
    log_home         = Column(String(200), comment='JEUS log home') # Domain Log 위치 (auto)
    landscape        = Column(Enum(LocationEnum), info={'enum_class':LocationEnum}, comment='Landscape') #운영/이관/개발/DR 구분 (manual)
    running_type     = Column(Enum(RuningTypeEnum), info={'enum_class':RuningTypeEnum}, comment='HA구성') #Active/StandBy 구분 (Manual)
    standby_host_id    = Column(String(30), comment='HA구성이 A-S인 경우 StandBy 서버 Host id') #Active-StandBy 인 경우 StandBy 장비
    located_host_id  = Column(String(30), ForeignKey('mw_server.host_id'), nullable=False, comment='설치서버') #WAS 도메인 설치 node (auto:adminServer->node-name)
    production_mode  = Column(String(30)) # Production 구분
    sys_user      = Column(String(50), comment='서버 계정') # WEB 서버 이름 (manual)
    use_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("YES"), nullable=False, comment='사용여부') #사용여부 (Manual)
    cluster_object   = Column(JSONB, comment='Clustering 정보') # Clustering 정보(auto:json)

    license_cpu        = Column(Integer, comment='License CPU') # License 허용 CPU
    license_edition    = Column(String(50), comment='License edition') # License edition
    license_hostname   = Column(String(50), comment='License hostname') # License hostname
    license_type       = Column(String(50), comment='License type') # License type
    license_issue_date = Column(DateTime(), comment='License 발급일') # License 발급일
    license_due_date   = Column(DateTime(), comment='License 만료일') # License 만료일
    license_text     = Column(Text, comment='License 정보') # License 정보(auto:json)
    license_update_date = Column(DateTime(), comment='License 정보 갱신일시')

    version_info     = Column(Text, comment='Version 정보') # Version 정보
    blackout_info     = Column(Text, comment='Blackout 정보')

    jeus_properties_text = Column(Text, comment='jeus properties 정보') # jeus properties 정보
    jeus_properties_update_date = Column(DateTime(), comment='jeus properties 정보 갱신일시')
    
    agent_id         = Column(String(30), comment='MW Agent ID') # MW Agent ID

    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    was_object       = Column(JSONB, comment='domain.xml 또는 JEUSMain.xml 전체 정보') # domian.xml 또는 JEUSMain.xml 정보(auto:json)
    was_text         = Column(Text, comment='WAS 정보') # domian.xml 또는 JEUSMain.xml 정보(auto:json)

    UniqueConstraint(was_id)

    @validates('located_host_id')
    def validate_located_host_id(self, key, host_id):
        if host_id:
            return host_id.lower()
        return host_id

    __table_args__ = (
        t__table_comment,
    )

    mw_application   = relationship('MwApplication', back_populates='mw_was', cascade='all,delete', passive_deletes=True)
    mw_datasource    = relationship('MwDatasource', back_populates='mw_was', cascade='all,delete', passive_deletes=True)
    mw_was_instance  = relationship('MwWasInstance', back_populates='mw_was', cascade='all,delete', passive_deletes=True)
    mw_was_change_history = relationship('MwWaschangeHistory', back_populates='mw_was', cascade='all,delete', passive_deletes=True)
    mw_server        = relationship('MwServer') 
    ut_tag = relationship('UtTag', secondary=assoc_tag_was, backref='mw_was')
    mw_web = relationship('MwWeb', secondary=assoc_was_web, back_populates='mw_was')

    def __repr__(self):
        return self.was_id

    @renders('landscape')
    def colored_landscape(self):
        return Markup(getColoredText(self.landscape))

    @renders('was_id')
    def c_was_id(self):
        if self.agent_id:
            colored_was_id = '<p>' + self.was_id + '</p>'
        else:
            colored_was_id = '<p style="color:#641E16;background-color:#CCD1D1;text-align:center">' + self.was_id + '</p>'

        return Markup(colored_was_id)

    def c_ip_address(self):
        ip = self.mw_server.ip_address
        return Markup('<p style="color:blue;">' + ip + '</p>')

    def c_os_type(self):
        os = self.mw_server.os_type.name
        return os

    def t__jeusprop_yn(self):
        return 'YES' if self.jeus_properties_text else 'NO'

    def t__java_home(self):
        specific_str = 'JAVA_HOME'

        if self.jeus_properties_text:
            lines = [line for line in self.jeus_properties_text.split('\n') if specific_str in line]
            return '\n'.join(lines)
        else:
            return ''

    def t__diamo(self):
        specific_str = 'diamo'
        if self.jeus_properties_text:
            lines = [line for line in self.jeus_properties_text.split('\n') if specific_str in line]
            return '\n'.join(lines)
        else:
            return ''

    def t__it_incharge(self):
        rtn = None
        t = next((t for t in self.ut_tag if t.tag.startswith('시스템')),None)
        if t:
            rtn = next((p.label for p in t.ut_parent_tag if p.tag.startswith('IT-담당자-정')),None)

        return rtn

    def link_ip_address(self):
        ip = self.mw_server.ip_address if self.mw_server.ip_address is not None else "Null"
        return Markup('<a href="http://'+ ip +':19736/webadmin/login" target="_blank" style="color:blue;">' + ip + '</a>')

    def view_domaininfo(self):
        return Markup(getJsonButton('WAS',self.was_id,'^_^'))

    def view_relationship(self):
        return Markup(getDiagramButton('WAS',self.was_id,'^_^'))

assoc_httplistener_etcssldomain = Table('assoc_httplistener_etcssldomain', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_httplistener', Integer, ForeignKey('mw_was_httplistener.id', ondelete='CASCADE')),
                                  Column('id_of_etcssldomain', Integer, ForeignKey('mw_etc_ssl_domain.id', ondelete='CASCADE'))
)

class MwWasHttpListener(Model):
    __tablename__ = "mw_was_httplistener"
    t__table_comment = {"comment":"WAS instance의 http listener"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    was_id           = Column(String(30), nullable=False, comment='WAS domain id') #WAS도메인 ID
    was_instance_id  = Column(String(30), nullable=False, comment='WAS instance id') #MS ID
    webconnection_id = Column(String(30), nullable=False, comment='Web Connector ID') #Web Connection ID (auto)
    listen_port      = Column(Integer, nullable=False, comment='listener port') # listener port (auto)
    ssl_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='SSL 사용여부')
    domain_name      = Column(String(200), comment='도메인명')
    min_thread_pool_count = Column(Integer, comment='Http Thread min 개수') #Http Thread min 개수 (auto)
    max_thread_pool_count = Column(Integer, comment='Http Thread max 개수') #Http Thread max 개수 (auto)
    httplistener_object   = Column(JSONB, comment='httplistener 정보') # httplistener 정보(auto:json)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(was_id, was_instance_id, webconnection_id)
    ForeignKeyConstraint(
        [was_id, was_instance_id],
        ['mw_was_instance.was_id', 'mw_was_instance.was_instance_id'],
        ondelete='CASCADE'
        )

    __table_args__ = (
        t__table_comment,
    )

    mw_was_instance = relationship('MwWasInstance')
    mw_etc_ssl_domain = relationship('MwEtcSslDomain', secondary=assoc_httplistener_etcssldomain, backref='mw_was_httplistener')

    def __repr__(self):
        return self.webconnection_id + '[' + str(self.listen_port) + ']'

    def host_id(self):
        return Markup(self.mw_was_instance.host_id)

    def ssl_notafter(self):
        if self.mw_etc_ssl_domain and self.mw_etc_ssl_domain[0].notafter:
            return self.mw_etc_ssl_domain[0].notafter.strftime('%Y-%m-%d %H:%M:%S')
        return ''

    def ssl_update_dt(self):
        if self.mw_etc_ssl_domain and self.mw_etc_ssl_domain[0].update_dt:
            return self.mw_etc_ssl_domain[0].update_dt.strftime('%Y-%m-%d %H:%M:%S')
        return ''

    def ssl_cn(self):
        if self.mw_etc_ssl_domain:
            return self.mw_etc_ssl_domain[0].t__cn()
        return ''

    def https_yn(self):
        
        return Markup(self.mw_was_instance.host_id)

assoc_webtobconn_webserver = Table('mw_webtobconn_webserver', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_webtobconn', Integer, ForeignKey('mw_was_webtobconnector.id', ondelete='CASCADE')),
                                  Column('id_of_webserver', Integer, ForeignKey('mw_web_server.id', ondelete='CASCADE'))
)

class MwWasWebtobConnector(Model):
    __tablename__ = "mw_was_webtobconnector"
    t__table_comment = {"comment":"WAS instance의 webtob connection"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    was_id           = Column(String(30), nullable=False, comment='WAS domain id') #WAS도메인 ID
    was_instance_id  = Column(String(30), nullable=False, comment='WAS instance id') #MS ID
    webconnection_id = Column(String(30), nullable=False, comment='Web Connector ID') #Web Connection ID (auto)
    web_host_id      = Column(String(30), comment='Web서버') #Web서버 host id(auto)
    real_web_host_id = Column(String(30), comment='Web서버 HOST ID') #node 이름 (auto)
    web_home         = Column(String(100), comment='Web서버 local home') #Web서버 local home(auto)
    jsv_port         = Column(Integer, nullable=False, comment='JSV port') # JSV port (auto)
    jsv_id           = Column(String(30), comment='JSV Id') #JSV Id (auto)
    web_hth_count    = Column(Integer, default=1, comment='Web서버 hth 개수') #Web서버 hth 개수 (auto)
    web_reconnect_interval = Column(Integer, comment='Reconnect interval') #webtob connector reconnect interval(ms) (auto)
    thread_pool_count      = Column(Integer, comment='Http Thread 최대개수') #Http Thread 최대개수 (auto)
    disable_pipe     = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='내장Webtob pipeline사용구분(사용시=false)')
    webtobconnector_object = Column(JSONB, comment='webconnection 정보') # webconnection 정보(auto:json)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(was_id, was_instance_id, webconnection_id)
    ForeignKeyConstraint(
        [was_id, was_instance_id],
        ['mw_was_instance.was_id', 'mw_was_instance.was_instance_id'],
        ondelete='CASCADE'
        )

    __table_args__ = (
        t__table_comment,
    )

    mw_was_instance = relationship('MwWasInstance')
    mw_web_server   = relationship('MwWebServer', secondary=assoc_webtobconn_webserver, backref='mw_was_webtobconnector')

    def __repr__(self):
        return self.was_instance_id + '[' + self.jsv_id + ']'

    def host_id(self):
        return Markup(self.mw_was_instance.host_id)

class MwWasInstance(Model):
    __tablename__ = "mw_was_instance"
    t__table_comment = {"comment":"WAS instance"}
    function_comments = {'t__xecure_yn':'xecure 사용 여부'}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    was_id           = Column(String(30), ForeignKey('mw_was.was_id', ondelete='CASCADE'), nullable=False, comment='WAS domain id') #WAS도메인 ID
    was_instance_id    = Column(String(30), nullable=False, comment='WAS instance id') #WAS Server ID (auto)
    was_instance_port  = Column(Integer, comment='서비스Port') #MS port (auto)
    was_instance_name  = Column(String(50), comment='Instance명/업무명') # 업무명 (Manual)
    host_id          = Column(String(30), ForeignKey('mw_server.host_id'), nullable=False, comment='HOST ID') #node 이름 (auto)
    min_heap_size    = Column(Integer, comment='Min Heap size') #Min Heap size (auto:parsing)
    max_heap_size    = Column(Integer, comment='Max Heap size') #Max Heap size (auto:parsing)
    file_encoding       = Column(Enum(EncodingEnum), info={'enum_class':EncodingEnum}, comment='File Encoding type') #엔코딩 (auto:parsing)
    jvm_option       = Column(String(2000), comment='JVM Option') #jvm_option (auto:parsing)
    log_home         = Column(String(500), comment='JEUS log home') #log path (auto)
    engine_command   = Column(String(30), comment='JEUS6 전용 WEBMain.xml 식별정보') #JEUS6 전용 WEBMain.xml 식별정보 (auto)    
    apm_type         = Column(Enum(ApmEnum), info={'enum_class':ApmEnum}, server_default=("NONE"), nullable=False, comment='APM 종류') #사용여부 (Manual)
    use_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("YES"), nullable=False, comment='사용여부') #사용여부 (Manual)
    clustered_yn     = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='Clustering여부') #Clustering 구분 (auto:parsing)
    app_id           = Column(String(50), ForeignKey('mw_app_master.app_id'), comment='application id', nullable=False)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(was_id, was_instance_id)

    @validates('host_id')
    def validate_host_id(self, key, host_id):
        if host_id:
            return host_id.lower()
        return host_id

    __table_args__ = (
        t__table_comment,
    )

    mw_app_master    = relationship('MwAppMaster')    
    mw_was           = relationship('MwWas')    
    mw_server        = relationship('MwServer')    
    mw_was_webtobconnector = relationship('MwWasWebtobConnector', back_populates='mw_was_instance', cascade='all,delete', passive_deletes=True)
    mw_was_httplistener = relationship('MwWasHttpListener', back_populates='mw_was_instance', cascade='all,delete', passive_deletes=True)
    ut_tag = relationship('UtTag', secondary=assoc_tag_wasinstance, backref='mw_was_instance')

    mw_datasource    = relationship('MwDatasource', secondary=assoc_datasource_instance, backref='mw_was_instance')
    mw_application   = relationship('MwApplication', secondary=assoc_application_instance, backref='mw_was_instance')
    
    def __repr__(self):
        return self.was_id + '.' + self.was_instance_id

    @renders('apm_type')
    def colored_apm_type(self):
        return Markup(getColoredText(self.apm_type))

    def t__xecure_yn(self):
        return 'YES' if 'xecure' in self.jvm_option else 'NO'

    def landscape(self):
        return self.mw_was.landscape.name if self.mw_was.landscape is not None else None

    def newgeneration_yn(self):
        return self.mw_was.newgeneration_yn.name if self.mw_was.newgeneration_yn is not None else None

    def running_type(self):
        return self.mw_was.running_type.name if self.mw_was.running_type is not None else None

    def c_ip_address(self):
        ip = self.mw_server.ip_address
        return Markup('<p style="color:blue;">' + ip + '</p>')

    def c_os_type(self):
        os = self.mw_server.os_type.name
        return os

    def t__gclog_yn(self):
        gcs = ['verbosegclog','loggc','verbosegc:file']
        return next(('YES' for g in gcs if g in self.jvm_option), 'NO')

class MwWeb(Model):
    __tablename__ = "mw_web"
    t__table_comment = {"comment":"Web 서버"}
    function_comments = {"t__ssl_yn":"ssl setting 여부 (YES/NO)"
                        ,"t__ssl":"ssl 정보 (변환 : JSON -> STRING)"
                        ,"t__tcpgw_yn":"TCP GW 정의 여부 (YES/NO)"
                        ,"t__tcpgw":"TCP GW 정보"
                        ,"t__ssl_certifile":"Certi file 이름"
                        ,"t__domain":"domain"
                        ,"t__ssl_domain":"SSL용 domain"
                        ,"t__it_incharge":"담당자"
                        }

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    host_id          = Column(String(30), ForeignKey('mw_server.host_id'), nullable=False, comment='HOST ID')
    port             = Column(Integer, nullable=False, comment='Port') # port (auto)
    jsv_port         = Column(Integer, nullable=False, comment='JSV Port') # JSV port (auto)
    hth_count        = Column(Integer, default=1, comment='HTH 개수') # HTH 개수 (auto)
    built_type       = Column(Enum(BuiltEnum), info={'enum_class':BuiltEnum}, comment='Built Type') #외장형/내장형 구분 (manual)
    landscape        = Column(Enum(LocationEnum), info={'enum_class':LocationEnum}, comment='Landscape') #운영/이관/개발/DR 구분 (manual)
    newgeneration_yn = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='차세대여부') #차세대 구분 (manual)
    service_port     = Column(String(50), comment='http service port') # Service port (auto)
    node_name        = Column(String(100), comment='node name in http.m') # node 이름(http.m기준) (auto)
    web_name         = Column(String(50), comment='web서버 이름/용도') # WEB 서버 이름 (manual)
    web_home         = Column(String(200), comment='web서버 home') # WEB 설치 위치(http.m WEBTOBDIR) (auto)
    doc_dir          = Column(String(200), comment='doc root 위치') # doc root 위치 (auto)
    acc_dir          = Column(String(200), comment='access log 위치') # log 파일 위치 (auto)
    sys_user      = Column(String(50), comment='서버 계정') # WEB 서버 이름 (manual)
    running_type     = Column(Enum(RuningTypeEnum), info={'enum_class':RuningTypeEnum}, comment='HA구성') #Active/StandBy 구분 (Manual)
    standby_host_id  = Column(String(30), comment='HA구성이 A-S인 경우 StandBy 서버 Host id') #Active-StandBy 인 경우 StandBy 장비
    use_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("YES"), nullable=False, comment='사용여부') #사용여부 (Manual)
    ssl_object       = Column(JSONB, comment='SSL 인증서 정보') # SSL 인증서 정보(auto:json)
    proxy_ssl_object = Column(JSONB) # SSL 인증서 정보(auto:json)
    logging_object   = Column(JSONB, comment='Logging 정보') # Logging 정보(auto:json)
    errordocument_object = Column(JSONB, comment='error document 정보') # error document 정보(auto:json)
    ext_object       = Column(JSONB, comment='ext 정보') # ext document 정보(auto:json)
    tcpgw_object     = Column(JSONB, comment='TCP Gateway 정보') # TCP Gateway 정보(auto:json)
    httpm_object     = Column(JSONB, comment='http.m 전체 정보') # httpm 전체 정보(auto:json)

    license_cpu        = Column(Integer, comment='License CPU') # License 허용 CPU
    license_edition    = Column(String(50), comment='License edition') # License edition
    license_hostname   = Column(String(50), comment='License hostname') # License hostname
    license_type       = Column(String(50), comment='License type') # License type
    license_issue_date = Column(DateTime(), comment='License 발급일') # License 발급일
    license_due_date   = Column(DateTime(), comment='License 만료일') # License 만료일
    license_text     = Column(Text, comment='License 정보') # License 정보(auto:json)
    license_update_date = Column(DateTime(), comment='License 정보 갱신일시')

    version_info     = Column(Text, comment='Version 정보') # Version 정보

    agent_id         = Column(String(30), comment='MW Agent ID') # MW Agent ID
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    web_text         = Column(Text, comment='WEB 정보') # http.m 정보

    tmp_text1 = Column(String(500))
    tmp_text2 = Column(String(500))
    tmp_text3 = Column(String(500))
    tmp_text4 = Column(String(500))
    tmp_text5 = Column(String(500))
    tmp_text6 = Column(String(500))
    tmp_text7 = Column(String(500))
    tmp_text8 = Column(String(500))

    #UniqueConstraint(host_id, jsv_port)
    UniqueConstraint(host_id, port)

    @validates('host_id')
    def validate_host_id(self, key, host_id):
        if host_id:
            return host_id.lower()
        return host_id

    __table_args__ = (
        t__table_comment,
    )

    ut_tag = relationship('UtTag', secondary=assoc_tag_web, backref='mw_web')

    mw_server        = relationship('MwServer')
    mw_web_server    = relationship('MwWebServer', back_populates='mw_web', cascade='all,delete', passive_deletes=True)
    mw_web_uri       = relationship('MwWebUri', back_populates='mw_web', cascade='all,delete', passive_deletes=True)
    mw_web_reverseproxy = relationship('MwWebReverseproxy', back_populates='mw_web', cascade='all,delete', passive_deletes=True)
    mw_web_vhost     = relationship('MwWebVhost', back_populates='mw_web', cascade='all,delete', passive_deletes=True)
    mw_web_ssl       = relationship('MwWebSsl', back_populates='mw_web', cascade='all,delete', passive_deletes=True)
    mw_was           = relationship('MwWas', secondary=assoc_was_web, back_populates='mw_web')
    mw_web_change_history = relationship('MwWebchangeHistory', back_populates='mw_web', cascade='all,delete', passive_deletes=True)
    
    def __repr__(self):
        return self.host_id+'['+ str(self.port) +']'

    @renders('mw_was')
    def linked_was(self):
        return ", ".join([was.was_id for was in self.mw_was])

    @renders('landscape')
    def colored_landscape(self):
        return Markup(getColoredText(self.landscape))

    @renders('built_type')
    def colored_built_type(self):
        return Markup(getColoredText(self.built_type))

    @renders('host_id')
    def c_host_id(self):
        if self.agent_id:
            colored_host_id = '<p>' + self.host_id + '</p>'
        else:
            colored_host_id = '<p style="color:#641E16;background-color:#CCD1D1;text-align:center">' + self.host_id + '</p>'

        return Markup(colored_host_id)

    def c_ip_address(self):
        ip = self.mw_server.ip_address
        return Markup('<p style="color:blue;">' + ip if ip is not None else "" + '</p>')

    def t__domainInfo_yn(self):

        rtn = 'NO'
        if self.mw_web_vhost:

            for v in self.mw_web_vhost:
                if v.mw_web_domain:
                    rtn = 'YES'
                    break

        return rtn

    def t__it_incharge(self):
        rtn = None
        t = next((t for t in self.ut_tag if t.tag.startswith('시스템')),None)
        if t:
            rtn = next((p.label for p in t.ut_parent_tag if p.tag.startswith('IT-담당자-정')),None)

        return rtn

    def c_domainInfo_yn(self):
        rtn = self.t__domainInfo_yn()
        return Markup('<p style="color:blue;">' + 'YES' if rtn == 'YES' else 'NO' + '</p>')

    def t__ssl_yn(self):
        return 'YES' if self.ssl_object else 'NO'

    def t__ssl(self):

        rtn = ''
        ssl = self.ssl_object
        if ssl:
            r_list = []
            for k in ssl[0]:
                if k == 'NAME':
                    continue
                r_list.append(k + ':' + ssl[0][k])
            rtn = ', '.join(r_list)            

        return rtn

    def t__domain(self):

        rtn = []

        if not self.httpm_object or not self.httpm_object.get('VHOST'):
            return ''

        vhosts = self.httpm_object['VHOST']

        for v in vhosts:
            if v.get('HOSTNAME'):
                rtn += v['HOSTNAME']
            if v.get('HOSTALIAS'):
                rtn += v['HOSTALIAS']

        rtn_dist = list(dict.fromkeys(rtn))
        rtn_string = ', '.join(rtn_dist)  

        return rtn_string

    def t__ssl_domain(self):

        rtn = []

        if not self.httpm_object or not self.httpm_object.get('VHOST'):
            return ''

        vhosts = self.httpm_object['VHOST']

        for v in vhosts:
            if v.get('SSLFLAG') and v['SSLFLAG'] == 'Y':
                
                if v.get('HOSTNAME'):
                    rtn += v['HOSTNAME']
                if v.get('HOSTALIAS'):
                    rtn += v['HOSTALIAS']

        rtn_dist = list(dict.fromkeys(rtn))
        rtn_string = ', '.join(rtn_dist)  

        return rtn_string

    def t__ssl_certifile(self):

        rtn = []
        ssl = self.ssl_object
        if ssl and ssl[0]['CERTIFICATEFILE']:
            for s in ssl:
                rtn.append(s['CERTIFICATEFILE'])

        rtn_string = ', '.join(rtn)
        return rtn_string

    def t__tcpgw_yn(self):
        return 'YES' if self.tcpgw_object else 'NO'

    def t__tcpgw(self):

        rtn = ''
        tcpgw = self.tcpgw_object
        
        r_list = []
            
        if tcpgw:
            for k in tcpgw:

                if k.get('LISTEN'):
                    port = k['LISTEN'].split(':')[1]
                else:
                    port = k['PORT']
                
                target = k['SERVERADDRESS'].replace(' ','').split(',')
                r_list.append({'port':port,'target':target})
                
        return str(r_list) if r_list else ''

    def c_ssl_yn(self):
        return Markup('<p style="color:blue;">' + 'YES' if self.ssl_object else 'NO' + '</p>')

    def view_webinfo(self):
        param = self.host_id + '__' + str(self.port)
        return Markup(getJsonButton('WEB',param,'^_^'))

    def view_relationship(self):
        param = self.host_id + '__' + str(self.port)
        return Markup(getDiagramButton('WEB',param,'^_^'))


class MwWebchangeHistory(Model):
    __tablename__ = "mw_web_change_history"
    t__table_comment = {"comment":"WEB 변경 이력"}
    function_comments = {}
    
    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    mw_web_id        = Column(Integer, ForeignKey('mw_web.id', ondelete='CASCADE'), nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    old_httpm_object = Column(JSONB, comment='변경전 http.m 정보') # http.m 정보(auto:json)
    changed_object   = Column(JSONB, comment='변경 내역') # 변경내역 (auto:json)
    user_id          = Column(String(50), default=get_user, nullable=False)
    old_web_text     = Column(Text, comment='변경전 WEB 정보') # http.m 정보

    UniqueConstraint(mw_web_id, create_on)

    __table_args__ = (
        t__table_comment,
    )

    mw_web           = relationship('MwWeb', back_populates='mw_web_change_history')

    def show_diff(self):
        return Markup('<a href="/diff/web/'+str(self.id)+'" class="btn btn-sm btn-default" data-toggle="tooltip" rel="tooltip" title="" data-original-title="레코드 보기"><i class="fa fa-search"></i></a>')


class MwWebServer(Model):
    __tablename__ = "mw_web_server"
    t__table_comment = {"comment":"http.m server정보"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    #host_id          = Column(String(30), nullable=False, comment='HOST ID')
    #jsv_port         = Column(Integer, nullable=False, comment='JSV Port') # JSV port (auto)
    mw_web_id        = Column(Integer, ForeignKey('mw_web.id', ondelete='CASCADE'), nullable=False)
    svr_id           = Column(String(30), nullable=False, comment='Server ID(JSV ID와 일치)') #JSV Id (auto)
    svr_type         = Column(Enum(SvrTypeEnum), comment='Server Type') #Server Type (auto)
    min_proc_count   = Column(Integer, comment='Process min 개수') #jsv process 최소개수 (auto)
    max_proc_count   = Column(Integer, comment='Process max 개수') #jsv process 최대개수 (auto)
    request_level_ping_yn = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='Request Level Ping 여부') #Request Level Ping 여부 (auto)
    monitor_now      = Column(JSON, comment='서버현재상태')
    monitor_history  = Column(JSONB, comment='서버상태History')

    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    
    UniqueConstraint(mw_web_id, svr_id)
    """
    UniqueConstraint(host_id, jsv_port, svr_id)
    ForeignKeyConstraint(
        [host_id, jsv_port],
        ['mw_web.host_id', 'mw_web.jsv_port'],
        )
    """

    __table_args__ = (
        t__table_comment,
    )

    mw_web                 = relationship('MwWeb')

    def t__aqcnt(self):

        monitor_now = self.monitor_now

        if not monitor_now or not monitor_now.get('aqcnt'):
            return ''

        aqcnt = monitor_now['aqcnt']

        return aqcnt

    def __repr__(self):
        return self.svr_id+'('+ self.mw_web.host_id +')'
        #return self.svr_id+' MIN:'+str(self.min_proc_count)+',MAX:'+str(self.max_proc_count)

assoc_webserver_vhost = Table('mw_webserver_webvhost', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_web_server', Integer, ForeignKey('mw_web_server.id', ondelete='CASCADE')),
                                  Column('id_of_web_vhost', Integer, ForeignKey('mw_web_vhost.id', ondelete='CASCADE'))
)    

assoc_weburi_webserver = Table('mw_weburi_webserver', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_web_uri', Integer, ForeignKey('mw_web_uri.id', ondelete='CASCADE')),
                                  Column('id_of_web_server', Integer, ForeignKey('mw_web_server.id', ondelete='CASCADE'))
)

class MwWebUri(Model):
    __tablename__ = "mw_web_uri"
    t__table_comment = {"comment":"http.m uri정보"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    #host_id          = Column(String(30), nullable=False, comment='HOST ID')
    #jsv_port         = Column(Integer, nullable=False, comment='JSV Port') # JSV port (auto)
    mw_web_id        = Column(Integer, ForeignKey('mw_web.id', ondelete='CASCADE'), nullable=False)
    uri_id           = Column(String(30), nullable=False, comment='URI 이름') #URI 이름 (auto)
    svr_type         = Column(Enum(SvrTypeEnum), comment='Server Type') #Server Type (auto)
    uri              = Column(String(500), nullable=False, comment='URI') #URI (auto)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(mw_web_id, uri_id)
    """
    UniqueConstraint(host_id, jsv_port, uri_id)
    ForeignKeyConstraint(
        [host_id, jsv_port],
        ['mw_web.host_id', 'mw_web.jsv_port'],
        )
    """
    __table_args__ = (
        t__table_comment,
    )

    mw_web           = relationship('MwWeb')
    mw_web_server    = relationship('MwWebServer', secondary=assoc_weburi_webserver, backref='mw_web_uri')

    def __repr__(self):
        return self.uri_id+':'+self.uri

assoc_weburi_vhost = Table('mw_weburi_webvhost', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_web_uri', Integer, ForeignKey('mw_web_uri.id', ondelete='CASCADE')),
                                  Column('id_of_web_vhost', Integer, ForeignKey('mw_web_vhost.id', ondelete='CASCADE'))
)    

class MwWebReverseproxy(Model):
    __tablename__ = "mw_web_reverseproxy"
    t__table_comment = {"comment":"http.m reverse proxy정보"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    #host_id          = Column(String(30), nullable=False, comment='HOST ID')
    #jsv_port         = Column(Integer, nullable=False, comment='JSV Port') # JSV port (auto)
    mw_web_id        = Column(Integer, ForeignKey('mw_web.id', ondelete='CASCADE'), nullable=False)
    reverseproxy_id  = Column(String(30), nullable=False, comment='Reverse Proxy ID') # reverse proxy id (auto)
    context_path     = Column(String(100), comment='Context Path') #context path (auto)
    ssl_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='SSL 인증서 여부') #SSL 인증서 여부 (auto)
    target_ip_address= Column(String(100), comment='Reverse Proxy target ip') #reverse proxy target ip (auto)
    target_port      = Column(Integer, comment='Reverse Proxy target port') #reverse proxy target port (auto)
    target_context_path  = Column(String(100), comment='Reverse Proxy target context path') #reverse proxy target path (auto)
    max_connection_count = Column(Integer, comment='Max WebSocketConnections') #MaxWebSocketConnections (auto)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(mw_web_id, reverseproxy_id)
    """
    UniqueConstraint(host_id, jsv_port, reverseproxy_id)
    ForeignKeyConstraint(
        [host_id, jsv_port],
        ['mw_web.host_id', 'mw_web.jsv_port'],
        )
    """
    __table_args__ = (
        t__table_comment,
    )

    mw_web           = relationship('MwWeb')

    def __repr__(self):
        return self.reverseproxy_id+'('+ self.target_ip_address + ':'+str(self.target_port)+')'

assoc_webreverseproxy_vhost = Table('mw_webreverseproxy_webvhost', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_web_reverseproxy', Integer, ForeignKey('mw_web_reverseproxy.id', ondelete='CASCADE')),
                                  Column('id_of_web_vhost', Integer, ForeignKey('mw_web_vhost.id', ondelete='CASCADE'))
)    

class MwWebVhost(Model):
    __tablename__ = "mw_web_vhost"
    t__table_comment = {"comment":"http.m virtual host정보"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    #host_id          = Column(String(30), nullable=False, comment='HOST ID')
    #jsv_port         = Column(Integer, nullable=False, comment='JSV Port') # JSV port (auto)
    mw_web_id        = Column(Integer, ForeignKey('mw_web.id', ondelete='CASCADE'), nullable=False)
    vhost_id         = Column(String(30), nullable=False, comment='Virtual Host ID') # web서버 vhost (auto)
    web_ports        = Column(String(100), comment='서비스 port') #WEB port (auto)
    domain_name      = Column(String(100), comment='Domain 이름') #domain 이름 (auto)
    host_alias       = Column(String(500), comment='HOST ALIAS') #HOST ALIAS (auto)
    doc_dir          = Column(String(200), comment='DOC root') # DOC root (auto)
    acc_dir          = Column(String(200), comment='Access log 위치') # Access log 위치 (auto:parsing)
    ssl_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='SSL 인증서 여부') #SSL 인증서 여부 (auto)
    ssl_name         = Column(String(100), comment='SSL Name')
    urlrewrite_yn    = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='URL Rewrite 여부')
    urlrewrite_config      = Column(String(200), comment='URL Rewrite config 파일 위치')
    urlrewrite_text        = Column(Text, comment='URL Rewrite config 파일 내용')
    urlrewrite_update_date = Column(DateTime(), comment='URL Rewrite 갱신일시')
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(mw_web_id, vhost_id)
    """
    UniqueConstraint(host_id, jsv_port, vhost_id)
    ForeignKeyConstraint(
        [host_id, jsv_port],
        ['mw_web.host_id', 'mw_web.jsv_port'],
        )
    """
    __table_args__ = (
        t__table_comment,
    )

    mw_web           = relationship('MwWeb')
    mw_web_domain    = relationship('MwWebDomain', back_populates='mw_web_vhost', cascade='all,delete', passive_deletes=True)    
    mw_web_server    = relationship('MwWebServer', secondary=assoc_webserver_vhost, backref='mw_web_vhost')
    mw_web_uri       = relationship('MwWebUri', secondary=assoc_weburi_vhost, backref='mw_web_vhost')
    mw_web_reverseproxy = relationship('MwWebReverseproxy', secondary=assoc_webreverseproxy_vhost, backref='mw_web_vhost')
    
    def __repr__(self):
        return self.vhost_id

assoc_webssl_domain = Table('mw_webssl_webdomain', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_web_ssl', Integer, ForeignKey('mw_web_ssl.id', ondelete='CASCADE')),
                                  Column('id_of_web_domain', Integer, ForeignKey('mw_web_domain.id', ondelete='CASCADE'))
)    

class MwWebSsl(Model):
    __tablename__ = "mw_web_ssl"
    t__table_comment = {"comment":"SSL 정보"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    host_id          = Column(String(30), nullable=False, comment='HOST ID')
    #jsv_port         = Column(Integer, nullable=False, comment='JSV Port') # JSV port (auto)
    mw_web_id        = Column(Integer, ForeignKey('mw_web.id', ondelete='CASCADE'), nullable=False)
    ssl_name         = Column(String(100), nullable=False, comment='SSL Name')
    ssl_certi        = Column(String(200), comment='SSL Certificate File')
    ssl_certikey     = Column(String(200), comment='SSL Certificate Key File')
    ssl_cacerti      = Column(String(200), comment='SSL CA Certificate File')
    ssl_protocols    = Column(String(200), comment='SSL Protocols')
    ssl_ciphers      = Column(String(300), comment='SSL Ciphers')
    notbefore        = Column(DateTime(), comment='유효기간시작')
    notafter         = Column(DateTime(), comment='유효기간만료')
    subject          = Column(String(300), comment='주제')
    serial           = Column(String(100), comment='일련번호')
    issuer           = Column(String(300), comment='발급자')
    notbefore_ca     = Column(DateTime(), comment='유효기간시작(CA)')
    notafter_ca      = Column(DateTime(), comment='유효기간만료(CA)')
    subject_ca       = Column(String(300), comment='주제(CA)')
    serial_ca        = Column(String(100), comment='일련번호(CA)')
    issuer_ca        = Column(String(300), comment='발급자(CA)')
    update_dt        = Column(DateTime())    
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(mw_web_id, ssl_name)
    """
    UniqueConstraint(host_id, jsv_port, ssl_name)
    ForeignKeyConstraint(
        [host_id, jsv_port],
        ['mw_web.host_id', 'mw_web.jsv_port']
        )
    """
    __table_args__ = (
        t__table_comment,
    )

    mw_web        = relationship('MwWeb')

    def t__cn(self):

        subject = self.subject

        if not subject:
            return ''

        start = subject.find('CN=')

        if start < 0:
            result = ''
        else:
            subject = subject.replace('/',',')
            end = subject[start:].find(',')
            if end < 0:
                end = len(subject[start:])

            result = subject[start:start+end]

        return result

    def __repr__(self):
        return self.host_id+'['+ str(self.ssl_certi) +']'

class MwWebDomain(Model):
    __tablename__ = "mw_web_domain"
    t__table_comment = {"comment":"Domain name 및 SSL 정보"}
    function_comments = {"t__domain":"domain name : port"}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    host_id          = Column(String(30), nullable=False, comment='HOST ID')
    #jsv_port         = Column(Integer, nullable=False, comment='JSV Port') # JSV port (auto)
    #vhost_id         = Column(String(30), nullable=False, comment='Virtual Host ID') # web서버 vhost (auto)
    mw_web_vhost_id  = Column(Integer, ForeignKey('mw_web_vhost.id', ondelete='CASCADE'), nullable=False)
    domain_name      = Column(String(100), nullable=False, comment='Domain 이름') #domain 이름 (auto)
    port             = Column(String(10), nullable=False, comment='서비스 port') #WEB port (auto)
    ssl_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, comment='SSL 인증서 여부') #SSL 인증서 여부 (auto)
    ssl_certi        = Column(String(200), comment='SSL Certificate File')
    ssl_certikey     = Column(String(200), comment='SSL Certificate Key File')
    ssl_cacerti      = Column(String(200), comment='SSL CA Certificate File')
    notbefore    = Column(DateTime(), comment='유효기간시작')
    notafter     = Column(DateTime(), comment='유효기간만료')
    subject      = Column(String(300), comment='주제')
    serial       = Column(String(100), comment='일련번호')
    issuer       = Column(String(300), comment='발급자')
    notbefore_ca = Column(DateTime(), comment='유효기간시작(CA)')
    notafter_ca  = Column(DateTime(), comment='유효기간만료(CA)')
    subject_ca   = Column(String(300), comment='주제(CA)')
    serial_ca    = Column(String(100), comment='일련번호(CA)')
    issuer_ca    = Column(String(300), comment='발급자(CA)')
    update_dt    = Column(DateTime())    

    notbefore_file   = Column(DateTime(), comment='유효기간시작(Certi파일기준)')
    notafter_file    = Column(DateTime(), comment='유효기간만료(Certi파일기준)')
    subject_file     = Column(String(300), comment='주제(Certi파일기준)')
    serial_file      = Column(String(100), comment='일련번호(Certi파일기준)')
    issuer_file      = Column(String(300), comment='발급자(Certi파일기준)')
    file_update_dt   = Column(DateTime())
    notbefore_domain = Column(DateTime(), comment='유효기간시작(domain접속기준)')
    notafter_domain  = Column(DateTime(), comment='유효기간만료(domain접속기준)')
    subject_domain   = Column(String(300), comment='주제(domain접속기준)')
    serial_domain    = Column(String(100), comment='일련번호(domain접속기준)')
    issuer_domain    = Column(String(300), comment='발급자(domain접속기준)')
    domain_update_dt = Column(DateTime())    
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(mw_web_vhost_id, domain_name, port)
    """
    UniqueConstraint(host_id, jsv_port, vhost_id, domain_name, port)
    ForeignKeyConstraint(
        [host_id, jsv_port, vhost_id],
        ['mw_web_vhost.host_id', 'mw_web_vhost.jsv_port', 'mw_web_vhost.vhost_id'],
        )
    """
    __table_args__ = (
        t__table_comment,
    )

    mw_web_vhost = relationship('MwWebVhost')
    mw_web_ssl   = relationship('MwWebSsl', secondary=assoc_webssl_domain, backref='mw_web_domain')


    def t__domain(self):
        return self.domain_name + ':' + self.port

    def t__ssl_certi(self):

        result = ''
        for ssl in self.mw_web_ssl:
            result = ssl.ssl_certi
            break

        return result

    def t__cn(self):

        subject = self.subject

        if not subject:
            return ''

        start = subject.find('CN=')

        if start < 0:
            result = subject
        else:
            subject = subject.replace('/',',')
            end = subject[start:].find(',')
            if end < 0:
                end = len(subject[start:])

            result = subject[start:start+end]

        return result

    def t__cn_in_file(self):

        subject = self.subject_file

        if not subject:
            return ''

        start = subject.find('CN=')

        if start < 0:
            result = ''
        else:
            subject = subject.replace('/',',')
            end = subject[start:].find(',')
            if end < 0:
                end = len(subject[start:])

            result = subject[start:start+end]

        return result

    def t__cn_in_domain(self):

        subject = self.subject_domain

        if not subject:
            return ''

        start = subject.find('CN=')

        if start < 0:
            result = ''
        else:
            subject = subject.replace('/',',')
            end = subject[start:].find(',')
            if end < 0:
                end = len(subject[start:])

            result = subject[start:start+end]

        return result

    def __repr__(self):
        return self.domain_name + ':' + self.port

class MwEtcSslDomain(Model):
    __tablename__ = "mw_etc_ssl_domain"
    t__table_comment = {"comment": "기타 SSL Domain"}
    function_comments = {"t__domain": "domain name : port"}

    id            = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    host_id       = Column(String(30), ForeignKey('mw_server.host_id'), nullable=False, comment='HOST ID')
    domain_name   = Column(String(100), nullable=False, comment='Domain 이름')
    port          = Column(String(10), nullable=False, comment='서비스 port')
    notbefore     = Column(DateTime(), comment='유효기간시작')
    notafter      = Column(DateTime(), comment='유효기간만료')
    subject       = Column(String(300), comment='주제')
    serial        = Column(String(100), comment='일련번호')
    issuer        = Column(String(300), comment='발급자')
    notbefore_ca  = Column(DateTime(), comment='유효기간시작(CA)')
    notafter_ca   = Column(DateTime(), comment='유효기간만료(CA)')
    subject_ca    = Column(String(300), comment='주제(CA)')
    serial_ca     = Column(String(100), comment='일련번호(CA)')
    issuer_ca     = Column(String(300), comment='발급자(CA)')
    update_dt     = Column(DateTime())
    agent_id      = Column(String(30), comment='수집 Agent ID')
    description   = Column(String(500), comment='설명')
    use_yn        = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("YES"), nullable=False, comment='사용여부')
    managed_yn    = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), nullable=False, comment='미들웨어 관리대상여부')
    user_id       = Column(String(50), default=get_user, nullable=False)
    create_on     = Column(DateTime(), default=datetime.now, nullable=False)

    UniqueConstraint(host_id, domain_name, port)

    @validates('host_id')
    def validate_host_id(self, key, host_id):
        if host_id:
            return host_id.lower()
        return host_id

    __table_args__ = (
        t__table_comment,
    )

    mw_server = relationship('MwServer')

    def t__domain(self):
        return self.domain_name + ':' + self.port

    def t__cn(self):
        subject = self.subject
        if not subject:
            return ''
        start = subject.find('CN=')
        if start < 0:
            result = subject
        else:
            subject = subject.replace('/', ',')
            end = subject[start:].find(',')
            if end < 0:
                end = len(subject[start:])
            result = subject[start:start+end]
        return result

    def __repr__(self):
        return self.domain_name + ':' + self.port


class MwSslCertFile(Model):
    __tablename__ = "mw_ssl_cert_file"
    t__table_comment = {"comment": "SSL 인증서 파일 (HOWTO_021)"}

    id = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    cert_name = Column(String(30), unique=True, nullable=False, comment='이름 (UTF-8 30byte 이내)')
    ag_file_id = Column(Integer, ForeignKey('ag_file.id', ondelete='SET NULL'), comment='원본 파일')
    file_name = Column(String(50), nullable=False, comment='등록 시점의 파일 이름')
    received_date = Column(Date(), nullable=False, comment='접수일')
    receiver_name = Column(String(50), nullable=False, comment='접수자 이름')
    cert_type = Column(Enum(SslCertTypeEnum), info={'enum_class': SslCertTypeEnum}, nullable=False, comment='Leaf/중간 CA')
    subject = Column(String(300), comment='주제')
    cn = Column(String(200), comment='CN')
    serial = Column(String(100), comment='일련번호')
    issuer = Column(String(300), comment='발급자')
    notbefore = Column(DateTime(), comment='유효기간시작')
    notafter = Column(DateTime(), comment='유효기간만료')
    user_id = Column(String(50), default=get_user, nullable=False)
    create_on = Column(DateTime(), default=datetime.now, nullable=False)

    __table_args__ = (
        t__table_comment,
    )

    ag_file = relationship('AgFile')

    def __repr__(self):
        return self.cert_name


class MwServer(Model):
    __tablename__ = "mw_server"
    t__table_comment = {"comment":"Server Master"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    host_id          = Column(String(30), nullable=False, comment='HOST ID') #HOST 이름 (Manual)
    server_name      = Column(String(100)) # 서버이름 ex)코어뱅킹 AP#1 (Manual)
    landscape        = Column(Enum(LocationEnum), info={'enum_class':LocationEnum}, comment='Landscape') #운영/이관/개발/DR 구분 (Manual)
#    system_code      = Column(String(50), nullable=False) #시스템 코드
#    web_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, nullable=False) #WEB여부
#    was_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, nullable=False) #WAS여부
    os_type          = Column(Enum(OSEnum), info={'enum_class':OSEnum}, comment='OS 종류') #OS 종류 (Manual)
    encoding         = Column(Enum(EncodingEnum), info={'enum_class':EncodingEnum}, comment='엔코딩') #OS엔코딩 (Manual)
    jdk_version      = Column(String(20)) #JDK version (Manual)
    ip_address       = Column(String(20), comment='IP address') #IP address (Manual)
    vip_address      = Column(String(100), comment='접근 가능한 모든 IP address들') #VIP address (Manual)
    running_type     = Column(Enum(RunEnum), info={'enum_class':RunEnum}) #Active/StandBy 구분 (Manual)
    primary_host_id  = Column(String(30)) #StandBy의 경우 Primary 서버 HOST 이름 (Manual)
    dr_host_id       = Column(String(30), comment='DR HOST ID') #HOST 이름 (Manual)
    use_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("YES"), nullable=False) #사용여부 (Manual)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(host_id)
    
    @validates('host_id')
    def validate_host_id(self, key, host_id):
        if host_id:
            return host_id.lower()
        return host_id

    __table_args__ = (
        t__table_comment,
    )
    
    mw_was_instance  = relationship('MwWasInstance')
    mw_web           = relationship('MwWeb')

    ut_tag = relationship('UtTag', secondary=assoc_tag_server, backref='mw_server')
    ut_tag_itdep = relationship('UtTag', secondary=assoc_tag_server_itdep, backref='mw_server_itdep')
    ut_tag_bizdep = relationship('UtTag', secondary=assoc_tag_server_bizdep, backref='mw_server_bizdep')

    def __repr__(self):
        return self.host_id

    @renders('os_type')
    def colored_os(self):
        return Markup(getColoredText(self.os_type))

    @renders('landscape')
    def colored_landscape(self):
        return Markup(getColoredText(self.landscape))

    def web_yn(self):
        return Markup(isNotNull(self.mw_web))

    def was_yn(self):
        return Markup(isNotNull(self.mw_was_instance))

