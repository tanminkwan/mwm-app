from flask import g, url_for, current_app
from flask_appbuilder import Model
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column, Text, Integer, String, ForeignKey\
, DateTime, Enum, UniqueConstraint, ForeignKeyConstraint\
, Table, Date
from sqlalchemy.orm import relationship
import enum
from markupsafe import Markup, escape
from datetime import datetime
from flask_appbuilder.models.mixins import FileColumn
from flask_appbuilder.filemanager import get_file_original_name
from flask_appbuilder.models.decorators import renders
from .common import get_user, getColoredText, PeriodicTypeEnum, CommandClassEnum\
    , CommandStatusEnum, YnEnum, ResultStatusEnum, AgentTypeEnum, IntervalTypeEnum\
    , TargetToSendEnum, AutorunTypeEnum, LocationEnum, AgentSubTypeEnum, get_uuid

assoc_agent_agentgroup = Table('ag_agent_agentgroup', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_agent_group', Integer\
                                  , ForeignKey('ag_agent_group.id', ondelete='CASCADE')),
                                  Column('id_of_agent', Integer\
                                  , ForeignKey('ag_agent.id', ondelete='CASCADE'))
)

class AgAgentGroup(Model):
    __tablename__ = "ag_agent_group"

    id               = Column(Integer, primary_key=True, nullable=False)
    agent_group_id   = Column(String(30), nullable=False)
    agent_group_name = Column(String(300))
    agent_type       = Column(Enum(AgentTypeEnum), info={'enum_class':AgentTypeEnum})
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(agent_group_id)

    ag_agent    = relationship('AgAgent', secondary=assoc_agent_agentgroup\
                                , backref='ag_agent_group')

    def __repr__(self):
        return self.agent_group_id

class AgAgent(Model):
    __tablename__ = "ag_agent"

    id         = Column(Integer, primary_key=True, nullable=False)
    agent_id   = Column(String(30), nullable=False)
    agent_name = Column(String(300))
    agent_type = Column(Enum(AgentTypeEnum), info={'enum_class':AgentTypeEnum}, nullable=False)
    agent_sub_type = Column(Enum(AgentSubTypeEnum), info={'enum_class':AgentSubTypeEnum})
    agent_version = Column(String(50))
    host_id    = Column(String(30)) #HOST 이름
    ip_address = Column(String(20), nullable=False) #IP address
    installation_path = Column(String(300), comment='Installation Path')
    landscape   = Column(Enum(LocationEnum), info={'enum_class':LocationEnum}) #운영/이관/개발/DR 구분 (manual)
    approved_yn = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), nullable=False)
    last_checked_date      = Column(DateTime())    
    token_expiration_date  = Column(DateTime())
    refresh_token = Column(String(500))

    user_id    = Column(String(50), default=get_user, nullable=False)
    create_on  = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(agent_id)

    def __repr__(self):
        return self.agent_id

    @renders('last_checked_date')
    def c_last_checked(self):

        if self.last_checked_date:
            t_gap = datetime.now() - self.last_checked_date
            gap = t_gap.total_seconds()
        else:
            gap = 500
        
        offline_threshold = current_app.config.get('AGENT_OFFLINE_MINUTES', 5) * 60
        
        if self.approved_yn.name == 'NO':
            text = '<p style="color:#2B3856;text-align:center;animation:blink 1s ease-in-out infinite alternate"><b>미승인</b></p>'
        elif self.token_expiration_date and self.token_expiration_date <= datetime.now():
            text = '<p style="background-color:#2B1B17;color:#E5E4E2;text-align:center"><b>Token 만료</b></p>'
        elif gap < offline_threshold:
            text = '<p style="background-color:#5CB3FF;color:#FFFFFF;text-align:center;animation:blink 1s ease-in-out infinite alternate"><b>OnLine</b></p>'
        elif gap >= offline_threshold and gap <= 86400:
            text = '<p style="background-color:#C0C0C0;text-align:center;"><b>OffLine</b></p>'
        else:
            text = '<p style="background-color:#800000;color:#E5E4E2;text-align:center"><b>장기미사용</b></p>'
        return Markup(text)
    
class AgCommandType(Model):

    __tablename__ = "ag_command_type"

    id                = Column(Integer, primary_key=True, nullable=False)
    command_type_id   = Column(String(50), nullable=False)
    command_type_name = Column(String(100))
    command_class     = Column(Enum(CommandClassEnum), info={'enum_class':CommandClassEnum})
    target_file_path = Column(String(300))
    target_file_name = Column(String(100))
    user_id           = Column(String(50), default=get_user, nullable=False)
    create_on         = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(command_type_id)

    def __repr__(self):
        return self.command_type_id

assoc_agentgroup_commandmaster = Table('ag_agentgroup_commandmaster', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_agent_group', Integer, ForeignKey('ag_agent_group.id', ondelete='CASCADE')),
                                  Column('id_of_command_master', Integer, ForeignKey('ag_command_master.id', ondelete='CASCADE'))
)

assoc_agent_commandmaster = Table('ag_agent_commandmaster', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_agent', Integer, ForeignKey('ag_agent.id', ondelete='CASCADE')),
                                  Column('id_of_command_master', Integer, ForeignKey('ag_command_master.id', ondelete='CASCADE'))
)

class AgAutorunResult(Model):
    __tablename__ = "ag_autorun_result"

    id                = Column(Integer, primary_key=True, nullable=False)
    autorun_id        = Column(String(50), nullable=False)
    autorun_type      = Column(Enum(AutorunTypeEnum), info={'enum_class':AutorunTypeEnum}, nullable=False) 
    target_file_name  = Column(String(100))
    command_id        = Column(String(30))
    autorun_func      = Column(String(100), nullable=False)
    autorun_param     = Column(String(200))
    user_id           = Column(String(50), default=get_user, nullable=False)
    create_on         = Column(DateTime(), default=datetime.now, nullable=False)   

    def __repr__(self):
        return self.autorun_key

class AgCommandHelper(Model):
    __tablename__ = "ag_command_helper"

    id                = Column(Integer, primary_key=True, nullable=False)
    mapping_key       = Column(String(50), nullable=False)
    target_file_name  = Column(String(100), nullable=False)
    agent_id          = Column(String(30), ForeignKey('ag_agent.agent_id', ondelete='CASCADE'), nullable=False)
    string_to_replace = Column(String(300))
    user_id           = Column(String(50), default=get_user, nullable=False)
    create_on         = Column(DateTime(), default=datetime.now, nullable=False)   
    ag_agent          = relationship('AgAgent') 
    UniqueConstraint(mapping_key, target_file_name, agent_id, string_to_replace)

    def __repr__(self):
        return self.mapping_key

class AgCommandMaster(Model):
    __tablename__ = "ag_command_master"

    id               = Column(Integer, primary_key=True, nullable=False)
    command_id       = Column(String(30), default=get_uuid, nullable=False)
    command_type_id  = Column(String(50), ForeignKey('ag_command_type.command_type_id'), nullable=False)
    periodic_type    = Column(Enum(PeriodicTypeEnum), info={'enum_class':PeriodicTypeEnum})
    time_to_exe      = Column(DateTime())
    time_to_stop     = Column(DateTime())
    cycle_to_exe     = Column(Integer)
    interval_type    = Column(Enum(IntervalTypeEnum), info={'enum_class':IntervalTypeEnum})
    additional_params= Column(Text)
    publish_yn       = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), nullable=False)
    cancel_yn        = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), nullable=False)
    finished_yn      = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"))
    command_sender   = Column(Enum(TargetToSendEnum), info={'enum_class':TargetToSendEnum}, server_default=("SERVER"), nullable=False)
    result_receiver  = Column(Enum(TargetToSendEnum), info={'enum_class':TargetToSendEnum}, server_default=("SERVER"), nullable=False)
    target_object    = Column(String(50))
    broadcast_callback = Column(String(100), comment='Broadcast Callback 함수명')
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(command_id)

    ag_command_type  = relationship('AgCommandType')    

    ag_agent        = relationship('AgAgent', secondary=assoc_agent_commandmaster, backref='ag_command_master')
    ag_agent_group  = relationship('AgAgentGroup', secondary=assoc_agentgroup_commandmaster, backref='ag_command_master')

    def __repr__(self):
        return self.command_id


class AgCommandDetail(Model):
    __tablename__ = "ag_command_detail"

    id               = Column(Integer, primary_key=True, nullable=False)
    command_id       = Column(String(30), ForeignKey('ag_command_master.command_id'), nullable=False)
    agent_id         = Column(String(30), ForeignKey('ag_agent.agent_id'), nullable=False)
    repetition_seq   = Column(Integer, nullable=False) 
    command_type_id  = Column(String(50), ForeignKey('ag_command_type.command_type_id'), nullable=False)
    command_class    = Column(Enum(CommandClassEnum), info={'enum_class':CommandClassEnum})
    target_file_path = Column(String(300))
    target_file_name = Column(String(100))
    additional_params= Column(Text)
    command_status   = Column(Enum(CommandStatusEnum), info={'enum_class':CommandStatusEnum}, nullable=False)
    result_received_date = Column(DateTime())    
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(command_id, agent_id, repetition_seq)

    ag_command_master = relationship('AgCommandMaster')    
    ag_command_type   = relationship('AgCommandType')    
    ag_agent          = relationship('AgAgent')
    ag_result         = relationship('AgResult', back_populates='ag_command_detail', cascade='all,delete', passive_deletes=True)

    def __repr__(self):
        return self.command_id + '[' + self.agent_id + ']:' + str(self.repetition_seq) 

    @renders('command_status')
    def colored_command_status(self):
        return Markup(getColoredText(self.command_status))

class AgResult(Model):

    __tablename__ = "ag_result"

    id                = Column(Integer, primary_key=True, nullable=False)
    command_id        = Column(String(30), nullable=False)
    agent_id          = Column(String(30), nullable=False)    
    repetition_seq    = Column(Integer, nullable=False) 
    host_id           = Column(String(30), nullable=False, index=True) #HOST 이름
    key_value1        = Column(String(200), nullable=False, index=True)
    key_value2        = Column(String(200), nullable=False)
    result_text       = Column(Text)
    result_hash       = Column(String(200))
    result_status     = Column(Enum(ResultStatusEnum), info={'enum_class':ResultStatusEnum}, server_default=("CREATE"), nullable=False)
    result_message    = Column(Text)
    user_id           = Column(String(50), default=get_user, nullable=False)
    create_on         = Column(DateTime(), default=datetime.now, nullable=False, index=True)    
    complited_date    = Column(DateTime(), index=True)    

    UniqueConstraint(command_id, agent_id, repetition_seq, host_id, key_value1, key_value2)
    ForeignKeyConstraint(
        [command_id, agent_id, repetition_seq],
        ['ag_command_detail.command_id', 'ag_command_detail.agent_id', 'ag_command_detail.repetition_seq'],
        ondelete='CASCADE'
        )
    
    ag_command_detail  = relationship('AgCommandDetail')

    def __repr__(self):
        return self.ag_command_detail.command_id + ':' + self.host_id + ':' + self.key_value1

    @renders('result_status')
    def colored_result_status(self):
        return Markup(getColoredText(self.result_status))

    @renders('result_text')
    def sub_result(self):
        sub_result = escape(self.result_text[:100])
        return Markup(sub_result)

class AgFile(Model):
    __tablename__ = "ag_file"
    
    id               = Column(Integer, primary_key=True, nullable=False)
    agent_type       = Column(Enum(AgentTypeEnum), info={'enum_class':AgentTypeEnum}, nullable=False)
    file_name        = Column(String(50), nullable=False)
    file_version     = Column(String(50), default='0000.0000.0000', nullable=False)
    file             = Column(FileColumn, nullable=False)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(agent_type, file_name, file_version)

    def download(self):
        url='/common/download/'+str(self.file)
        return Markup(f'<a href="{url}" target="_blank">Download</a>')

    def get_filename(self):
        return get_file_original_name(str(self.file))
