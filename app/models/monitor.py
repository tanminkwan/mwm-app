from flask import g, url_for
from markupsafe import Markup
from flask_appbuilder import Model
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column, Integer, String, ForeignKey\
, DateTime, Enum, UniqueConstraint, ForeignKeyConstraint\
, Table, Date, Float
from sqlalchemy.types import ARRAY
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from flask_appbuilder.models.mixins import FileColumn
from flask_appbuilder.models.decorators import renders
from flask_appbuilder.filemanager import get_file_original_name
from .was import MwWas
from .common import get_user, WasInstanceStatusEnum, LocationEnum

class MoGridConfig(Model):
    __tablename__ = "mo_grid_config"
    t__table_comment = {"comment":"Table 조회 Configuration"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False)
    grid_key         = Column(String(30), nullable=False)
    title            = Column(String(100), nullable=False)
    table_name       = Column(String(50), nullable=False)
    columns          = Column(String(1000), nullable=False)
    headers          = Column(String(500), nullable=False)
    seperator        = Column(String(10))
    condition_columns = Column(String(500))
    condition_labels = Column(String(500))
    widths           = Column(String(500))
    file_name        = Column(String(100))
    page_dblclick    = Column(String(100))
    default_condition = Column(String(1000))
    rows_per_page    = Column(Integer)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(grid_key)

    __table_args__ = (
        t__table_comment,
    )

    def __repr__(self):
        return self.grid_key + ':' + self.title

class MoWasInstanceStatus(Model):
    __tablename__ = "mo_was_instance_status"
    t__table_comment = {"comment":"WAS instance 상태"}
    function_comments = {'t__status':'WAS instance 상태'}

    id               = Column(Integer, primary_key=True, nullable=False)
    was_id           = Column(String(30), ForeignKey('mw_was.was_id'), nullable=False) #WAS도메인 ID
    was_instance_id  = Column(String(30), nullable=False)
    was_instance_status = Column(Enum(WasInstanceStatusEnum), info={'enum_class':WasInstanceStatusEnum}, nullable=False) 
    host_id          = Column(String(30), ForeignKey('mw_server.host_id'), nullable=False)
    landscape        = Column(Enum(LocationEnum), info={'enum_class':LocationEnum}) #운영/이관/개발/DR 구분 (manual)
    user_id          = Column(String(50), default=get_user, nullable=False)
    update_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    mw_was           = relationship('MwWas')
    UniqueConstraint(was_id, was_instance_id)

    __table_args__ = (
        t__table_comment,
    )

    def __repr__(self):
        return self.was_id + ':' + self.was_instance_id

    def t__status(self):

        t = datetime.now() - self.update_on

        # Check 일시 30분 경과 Check
        return self.was_instance_status.name if t.seconds < 60*30 else 'NOTCHECKED'

class MoWasStatusTemplate(Model):
    __tablename__ = "mo_was_status_template"
    t__table_comment = {"comment":"WAS instance 상태 report template"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False)
    was_id           = Column(String(30), ForeignKey('mw_was.was_id'), nullable=False) #WAS도메인 ID
    was_instance_group = Column(String(100), nullable=False)
    wi_01            = Column(String(30))
    wi_02            = Column(String(30))
    wi_03            = Column(String(30))
    wi_04            = Column(String(30))
    wi_05            = Column(String(30))
    wi_06            = Column(String(30))
    wi_07            = Column(String(30))
    wi_08            = Column(String(30))
    wi_09            = Column(String(30))
    wi_10            = Column(String(30))
    wi_11            = Column(String(30))
    wi_12            = Column(String(30))
    wi_13            = Column(String(30))
    wi_14            = Column(String(30))
    wi_15            = Column(String(30))
    wi_16            = Column(String(30))
    wi_17            = Column(String(30))
    wi_18            = Column(String(30))
    wi_19            = Column(String(30))
    wi_20            = Column(String(30))
    wi_21            = Column(String(30))
    wi_22            = Column(String(30))
    wi_23            = Column(String(30))
    wi_24            = Column(String(30))
    wi_25            = Column(String(30))
    comment          = Column(String(500))
    user_id          = Column(String(50), default=get_user, nullable=False)
    update_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    mw_was           = relationship('MwWas')
    UniqueConstraint(was_id, was_instance_group)

    __table_args__ = (
        t__table_comment,
    )

    def __repr__(self):
        return self.was_id + ':' + self.was_instance_group

class MoWasStatusReport(Model):
    __tablename__ = "mo_was_status_report"
    t__table_comment = {"comment":"WAS instance 상태 report"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False)
    reported_time    = Column(String(30), nullable=False)    
    was_id           = Column(String(30), nullable=False)
    was_instance_group = Column(String(100), nullable=False)
    checked_date     = Column(DateTime(), nullable=False)    
    wi_01            = Column(String(30))
    wi_02            = Column(String(30))
    wi_03            = Column(String(30))
    wi_04            = Column(String(30))
    wi_05            = Column(String(30))
    wi_06            = Column(String(30))
    wi_07            = Column(String(30))
    wi_08            = Column(String(30))
    wi_09            = Column(String(30))
    wi_10            = Column(String(30))
    wi_11            = Column(String(30))
    wi_12            = Column(String(30))
    wi_13            = Column(String(30))
    wi_14            = Column(String(30))
    wi_15            = Column(String(30))
    wi_16            = Column(String(30))
    wi_17            = Column(String(30))
    wi_18            = Column(String(30))
    wi_19            = Column(String(30))
    wi_20            = Column(String(30))
    wi_21            = Column(String(30))
    wi_22            = Column(String(30))
    wi_23            = Column(String(30))
    wi_24            = Column(String(30))
    wi_25            = Column(String(30))
    wi_01_stat       = Column(String(30))
    wi_02_stat       = Column(String(30))
    wi_03_stat       = Column(String(30))
    wi_04_stat       = Column(String(30))
    wi_05_stat       = Column(String(30))
    wi_06_stat       = Column(String(30))
    wi_07_stat       = Column(String(30))
    wi_08_stat       = Column(String(30))
    wi_09_stat       = Column(String(30))
    wi_10_stat       = Column(String(30))
    wi_11_stat       = Column(String(30))
    wi_12_stat       = Column(String(30))
    wi_13_stat       = Column(String(30))
    wi_14_stat       = Column(String(30))
    wi_15_stat       = Column(String(30))
    wi_16_stat       = Column(String(30))
    wi_17_stat       = Column(String(30))
    wi_18_stat       = Column(String(30))
    wi_19_stat       = Column(String(30))
    wi_20_stat       = Column(String(30))
    wi_21_stat       = Column(String(30))
    wi_22_stat       = Column(String(30))
    wi_23_stat       = Column(String(30))
    wi_24_stat       = Column(String(30))
    wi_25_stat       = Column(String(30))
    comment          = Column(String(500))
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    
    UniqueConstraint(reported_time, was_id, was_instance_group)

    __table_args__ = (
        t__table_comment,
    )
    
    def __repr__(self):
        return self.reported_time + ':' + self.was_id


    def getColoredBackGround(self, src_obj, tar_obj):

        bkcolor_map = {'RUNNING':'#AED6F1', 'STANDBY':'green', 'SHUTDOWN':'red', 'FAILED':'red', 'NOVALUE':'black'}
        color_map = {'RUNNING':'black', 'STANDBY':'black', 'SHUTDOWN':'white', 'FAILED':'white', 'NOVALUE':'white'}
        try:
            color = color_map[src_obj]
            bkcolor = bkcolor_map[src_obj]
            text = '<p style="background-color:' + bkcolor + ';color:' + color + ';text-align:center;">' + tar_obj + '</p>'
        except KeyError as e:
            text = ""
        return text

    @renders('comment')
    def c_comment(self):
        comment = self.comment if self.comment else ''
        return Markup('<p style="white-space:nowrap;font-size:11px">'+ comment +'</p>')

    @renders('wi_01')
    def c_wi_01(self):
        return Markup(self.getColoredBackGround(self.wi_01_stat, self.wi_01))

    @renders('wi_02')
    def c_wi_02(self):
        return Markup(self.getColoredBackGround(self.wi_02_stat, self.wi_02))

    @renders('wi_03')
    def c_wi_03(self):
        return Markup(self.getColoredBackGround(self.wi_03_stat, self.wi_03))

    @renders('wi_04')
    def c_wi_04(self):
        return Markup(self.getColoredBackGround(self.wi_04_stat, self.wi_04))

    @renders('wi_05')
    def c_wi_05(self):
        return Markup(self.getColoredBackGround(self.wi_05_stat, self.wi_05))

    @renders('wi_06')
    def c_wi_06(self):
        return Markup(self.getColoredBackGround(self.wi_06_stat, self.wi_06))

    @renders('wi_07')
    def c_wi_07(self):
        return Markup(self.getColoredBackGround(self.wi_07_stat, self.wi_07))

    @renders('wi_08')
    def c_wi_08(self):
        return Markup(self.getColoredBackGround(self.wi_08_stat, self.wi_08))

    @renders('wi_09')
    def c_wi_09(self):
        return Markup(self.getColoredBackGround(self.wi_09_stat, self.wi_09))

    @renders('wi_10')
    def c_wi_10(self):
        return Markup(self.getColoredBackGround(self.wi_10_stat, self.wi_10))

    @renders('wi_11')
    def c_wi_11(self):
        return Markup(self.getColoredBackGround(self.wi_11_stat, self.wi_11))

    @renders('wi_12')
    def c_wi_12(self):
        return Markup(self.getColoredBackGround(self.wi_12_stat, self.wi_12))

    @renders('wi_13')
    def c_wi_13(self):
        return Markup(self.getColoredBackGround(self.wi_13_stat, self.wi_13))

    @renders('wi_14')
    def c_wi_14(self):
        return Markup(self.getColoredBackGround(self.wi_14_stat, self.wi_14))

    @renders('wi_15')
    def c_wi_15(self):
        return Markup(self.getColoredBackGround(self.wi_15_stat, self.wi_15))

    @renders('wi_16')
    def c_wi_16(self):
        return Markup(self.getColoredBackGround(self.wi_16_stat, self.wi_16))

    @renders('wi_17')
    def c_wi_17(self):
        return Markup(self.getColoredBackGround(self.wi_17_stat, self.wi_17))

    @renders('wi_18')
    def c_wi_18(self):
        return Markup(self.getColoredBackGround(self.wi_18_stat, self.wi_18))

    @renders('wi_19')
    def c_wi_19(self):
        return Markup(self.getColoredBackGround(self.wi_19_stat, self.wi_19))

    @renders('wi_20')
    def c_wi_20(self):
        return Markup(self.getColoredBackGround(self.wi_20_stat, self.wi_20))

    @renders('wi_21')
    def c_wi_21(self):
        return Markup(self.getColoredBackGround(self.wi_21_stat, self.wi_21))

    @renders('wi_22')
    def c_wi_22(self):
        return Markup(self.getColoredBackGround(self.wi_22_stat, self.wi_22))

    @renders('wi_23')
    def c_wi_23(self):
        return Markup(self.getColoredBackGround(self.wi_23_stat, self.wi_23))

    @renders('wi_24')
    def c_wi_24(self):
        return Markup(self.getColoredBackGround(self.wi_24_stat, self.wi_24))

    @renders('wi_25')
    def c_wi_25(self):
        return Markup(self.getColoredBackGround(self.wi_25_stat, self.wi_25))

class MoGcParsedLog(Model):
    __tablename__ = "mo_gc_parsed_log"
    t__table_comment = {"comment":"GC 파싱 로그"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False)
    host_id          = Column(String(30), nullable=False)
    was_instance_id  = Column(String(30), nullable=False)
    start_date       = Column(DateTime(), nullable=False, index=True)
    duration         = Column(Float)
    end_date         = Column(DateTime())
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint('host_id', 'was_instance_id', 'start_date', name='uq_gc_parsed_log'),
        t__table_comment,
    )
