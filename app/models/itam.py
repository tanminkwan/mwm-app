from flask_appbuilder import Model
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from .common import get_user, YnEnum

class ItWas(Model):
    __tablename__ = "it_was"
    
    config_id          = Column(String(50), primary_key=True, nullable=False, comment='구성번호')
    config_name        = Column(String(500), comment='구성명')
    host_id            = Column(String(200), comment='설치호스트명')
    biz_system         = Column(String(500), comment='업무시스템')
    biz_team           = Column(String(200), comment='업무팀')
    gw_ip              = Column(String(100), comment='OS대표IP(GW기준)')
    service_ip         = Column(String(100), comment='서비스IP')
    run_env            = Column(String(100), comment='운용환경')
    config_status      = Column(String(100), comment='구성상태')
    install_user       = Column(String(100), comment='설치계정명')
    jeus_version       = Column(String(100), comment='JEUS버전')
    os_type            = Column(String(100), comment='OS종류')
    os_ver             = Column(String(100), comment='OS버전')
    domain_name        = Column(String(200), comment='도메인명')
    base_port          = Column(String(50), comment='BASE포트')
    java_version       = Column(String(100), comment='JAVA버전')
    embed_web_yn       = Column(String(10), comment='내장WEB사용여부')
    embed_web_port     = Column(String(50), comment='내장WEB노드포트')
    embed_web_ssl_yn   = Column(String(10), comment='내장WEBSSL사용여부')
    was_ssl_yn         = Column(String(10), comment='WASSSL사용여부')
    os_kernel          = Column(String(200), comment='OS커널')
    cpu_core           = Column(String(100), comment='CPU(Core)')
    mem_gb             = Column(String(100), comment='MEM(GB)')
    hw_name            = Column(String(200), comment='하드웨어네임')
    hw_group           = Column(String(200), comment='하드웨어그룹')
    dept_team          = Column(String(200), comment='담당팀')
    cust_p_mngr        = Column(String(100), comment='고객담당자(정)')
    cust_s_mngr        = Column(String(100), comment='고객담당자(부)')
    ito_p_mngr         = Column(String(100), comment='ITO담당자(정)')
    ito_s_mngr         = Column(String(100), comment='ITO담당자(부)')

    user_id            = Column(String(50), default=get_user, nullable=False)
    create_on          = Column(DateTime(), default=datetime.now, nullable=False)    

    def __repr__(self):
        return f"{self.config_id}:{self.domain_name}" if self.domain_name else str(self.config_id)

class ItWeb(Model):
    __tablename__ = "it_web"
    
    config_id          = Column(String(50), primary_key=True, nullable=False, comment='구성번호')
    config_name        = Column(String(500), comment='구성명')
    host_id            = Column(String(200), comment='설치호스트명')
    biz_system         = Column(String(500), comment='업무시스템')
    biz_team           = Column(String(200), comment='업무팀')
    gw_ip              = Column(String(100), comment='OS대표IP(GW기준)')
    service_ip         = Column(String(100), comment='서비스IP')
    run_env            = Column(String(100), comment='운용환경')
    config_status      = Column(String(100), comment='구성상태')
    install_user       = Column(String(100), comment='설치계정명')
    webtob_version     = Column(String(100), comment='Webtob버전')
    os_type            = Column(String(100), comment='OS종류')
    os_ver             = Column(String(100), comment='OS버전')
    node_port          = Column(String(50), comment='노드포트')
    ssl_yn             = Column(String(50), comment='SSL사용여부')
    ev_cert_yn         = Column(String(50), comment='EV인증서여부')
    server_loc         = Column(String(200), comment='WEB서버위치')
    os_kernel          = Column(String(200), comment='OS커널')
    cpu_core           = Column(String(100), comment='CPU(Core)')
    mem_gb             = Column(String(100), comment='MEM(GB)')
    hw_name            = Column(String(200), comment='하드웨어네임')
    hw_group           = Column(String(200), comment='하드웨어그룹')
    dept_team          = Column(String(200), comment='담당팀')
    cust_p_mngr        = Column(String(100), comment='고객담당자(정)')
    cust_s_mngr        = Column(String(100), comment='고객담당자(부)')
    ito_p_mngr         = Column(String(100), comment='ITO담당자(정)')
    ito_s_mngr         = Column(String(100), comment='ITO담당자(부)')

    user_id            = Column(String(50), default=get_user, nullable=False)
    create_on          = Column(DateTime(), default=datetime.now, nullable=False)    

    def __repr__(self):
        return f"{self.config_id}:{self.host_id}" if self.host_id else str(self.config_id)

class ItItamWasCompare(Model):
    """ITAM WAS 기준 대사 결과 (ITAM WAS + ITAM 내장WEB 대사 결과 포함)"""
    __tablename__ = "it_itam_was_compare"

    id            = Column(Integer, primary_key=True, nullable=False)
    config_id     = Column(String(50), ForeignKey('it_was.config_id', ondelete='CASCADE'), nullable=False, comment='ITAM WAS 구성번호')
    error_type    = Column(String(100), nullable=False, comment='오류 항목')
    error_content = Column(Text, comment='오류 내용')
    action_yn     = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), comment='조치구분')
    user_id       = Column(String(50), default=get_user, nullable=False)
    create_on     = Column(DateTime(), default=datetime.now, nullable=False)

    it_was = relationship('ItWas')

    def __repr__(self):
        return f"{self.config_id}:{self.error_type}"

class ItItamWebCompare(Model):
    """ITAM WEB 기준 대사 결과"""
    __tablename__ = "it_itam_web_compare"

    id            = Column(Integer, primary_key=True, nullable=False)
    config_id     = Column(String(50), ForeignKey('it_web.config_id', ondelete='CASCADE'), nullable=False, comment='ITAM WEB 구성번호')
    error_type    = Column(String(100), nullable=False, comment='오류 항목')
    error_content = Column(Text, comment='오류 내용')
    action_yn     = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), comment='조치구분')
    user_id       = Column(String(50), default=get_user, nullable=False)
    create_on     = Column(DateTime(), default=datetime.now, nullable=False)

    it_web = relationship('ItWeb')

    def __repr__(self):
        return f"{self.config_id}:{self.error_type}"

class ItLeebalsoWasCompare(Model):
    """미들웨어관리소 WAS 기준 대사 결과"""
    __tablename__ = "it_leebalso_was_compare"

    id            = Column(Integer, primary_key=True, nullable=False)
    leebalso_id   = Column(Integer, ForeignKey('mw_was.id', ondelete='CASCADE'), nullable=False, comment='미들웨어관리소 WAS ID')
    error_type    = Column(String(100), nullable=False, comment='오류 항목')
    error_content = Column(Text, comment='오류 내용')
    action_yn     = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), comment='조치구분')
    user_id       = Column(String(50), default=get_user, nullable=False)
    create_on     = Column(DateTime(), default=datetime.now, nullable=False)

    mw_was = relationship('MwWas')

    def __repr__(self):
        return f"{self.leebalso_id}:{self.error_type}"

class ItLeebalsoWebCompare(Model):
    """미들웨어관리소 WEB 기준 대사 결과"""
    __tablename__ = "it_leebalso_web_compare"

    id            = Column(Integer, primary_key=True, nullable=False)
    leebalso_id   = Column(Integer, ForeignKey('mw_web.id', ondelete='CASCADE'), nullable=False, comment='미들웨어관리소 WEB ID')
    error_type    = Column(String(100), nullable=False, comment='오류 항목')
    error_content = Column(Text, comment='오류 내용')
    action_yn     = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), comment='조치구분')
    user_id       = Column(String(50), default=get_user, nullable=False)
    create_on     = Column(DateTime(), default=datetime.now, nullable=False)

    mw_web = relationship('MwWeb')

    def __repr__(self):
        return f"{self.leebalso_id}:{self.error_type}"
