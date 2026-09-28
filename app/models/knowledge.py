from flask import g, url_for
from flask_appbuilder import Model
from flask_appbuilder.filemanager import get_file_original_name
from flask_appbuilder.models.mixins import FileColumn
from markupsafe import Markup
from sqlalchemy import Column, Integer, String, ForeignKey\
, DateTime, Enum, UniqueConstraint, ForeignKeyConstraint\
, Table, Date, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
import enum
from datetime import datetime
from .common import get_user, get_group, get_date, get_uuid, YnEnum, getTagWithType\
    , getTagValueWithType, getHtmlButton

assoc_tag_resource = Table('ut_tag_resource', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_resource', Integer, ForeignKey('ut_resource.id', ondelete='CASCADE'))
)    

assoc_tag_htmlcontent = Table('ut_tag_htmlcontent', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_htmlcontent', Integer, ForeignKey('ut_html_content.id', ondelete='CASCADE'))
)    

assoc_tagkm_htmlcontent = Table('ut_tagkm_htmlcontent', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag_km.id', ondelete='CASCADE')),
                                  Column('id_of_htmlcontent', Integer, ForeignKey('ut_html_content.id', ondelete='CASCADE'))
)    

assoc_file_htmlcontent = Table('ut_file_htmlcontent', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_file', Integer, ForeignKey('ut_file.id', ondelete='CASCADE')),
                                  Column('id_of_htmlcontent', Integer, ForeignKey('ut_html_content.id', ondelete='CASCADE'))
)    

assoc_tag_mdcontent = Table('ut_tag_mdcontent', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_mdcontent', Integer, ForeignKey('ut_md_content.id', ondelete='CASCADE'))
)    

assoc_tagkm_mdcontent = Table('ut_tagkm_mdcontent', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag_km.id', ondelete='CASCADE')),
                                  Column('id_of_mdcontent', Integer, ForeignKey('ut_md_content.id', ondelete='CASCADE'))
)    

assoc_file_mdcontent = Table('ut_file_mdcontent', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_file', Integer, ForeignKey('ut_file.id', ondelete='CASCADE')),
                                  Column('id_of_mdcontent', Integer, ForeignKey('ut_md_content.id', ondelete='CASCADE'))
)    

assoc_tagkm_tagkm = Table('ut_tagkm_tagkm', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_parent_tag', Integer, ForeignKey('ut_tag_km.id', ondelete='CASCADE')),
                                  Column('id_of_child_tag', Integer, ForeignKey('ut_tag_km.id', ondelete='CASCADE'))
)    

assoc_tag_tag = Table('ut_tag_tag', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_parent_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_child_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE'))
)    

assoc_kmgroup_htmlcontent = Table('ut_kmgroup_htmlcontent', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_group', Integer, ForeignKey('ut_km_group.id', ondelete='CASCADE')),
                                  Column('id_of_htmlcontent', Integer, ForeignKey('ut_html_content.id', ondelete='CASCADE'))
)    

assoc_kmgroup_mdcontent = Table('ut_kmgroup_mdcontent', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_group', Integer, ForeignKey('ut_km_group.id', ondelete='CASCADE')),
                                  Column('id_of_mdcontent', Integer, ForeignKey('ut_md_content.id', ondelete='CASCADE'))
)    

class UtTag(Model):
    __tablename__ = "ut_tag"
    t__table_comment = {"comment":"TAG"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    tag              = Column(String(500), nullable=False, comment='TAG')
    label            = Column(String(100), comment='LABEL')
    value1           = Column(String(500), comment='부가정보1')
    value2           = Column(String(500), comment='부가정보2')
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=get_date, nullable=False)    

    __table_args__ = (
        Index('ix_ut_tag_gin'
	        , func.string_to_array(tag, '-')
	        , postgresql_using='gin'
	    ),
        t__table_comment
    )

    UniqueConstraint(tag)

    ut_child_tag = relationship('UtTag', secondary=assoc_tag_tag\
        , primaryjoin   = "UtTag.id==ut_tag_tag.c.id_of_parent_tag"\
        , secondaryjoin = "UtTag.id==ut_tag_tag.c.id_of_child_tag")

    ut_parent_tag = relationship('UtTag', secondary=assoc_tag_tag\
        , overlaps = 'ut_child_tag'
        , primaryjoin   = "UtTag.id==ut_tag_tag.c.id_of_child_tag"\
        , secondaryjoin = "UtTag.id==ut_tag_tag.c.id_of_parent_tag")

    def __repr__(self):
        return self.tag

class UtTagKm(Model):
    __tablename__ = "ut_tag_km"
    t__table_comment = {"comment":"지식관리용 TAG"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    tag              = Column(String(500), nullable=False, comment='TAG')
    label            = Column(String(100), comment='LABEL')
    value1           = Column(String(500), comment='부가정보1')
    value2           = Column(String(500), comment='부가정보2')
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=get_date, nullable=False)    

    __table_args__ = (
        Index('ix_ut_tag_km_gin'
	        , func.string_to_array(tag, '-')
	        , postgresql_using='gin'
	    ),
        t__table_comment
    )

    UniqueConstraint(tag)

    ut_child_tagkm = relationship('UtTagKm', secondary=assoc_tagkm_tagkm\
        , primaryjoin   = "UtTagKm.id==ut_tagkm_tagkm.c.id_of_parent_tag"\
        , secondaryjoin = "UtTagKm.id==ut_tagkm_tagkm.c.id_of_child_tag")

    ut_parent_tagkm = relationship('UtTagKm', secondary=assoc_tagkm_tagkm\
        , overlaps = 'ut_child_tagkm'
        , primaryjoin   = "UtTagKm.id==ut_tagkm_tagkm.c.id_of_child_tag"\
        , secondaryjoin = "UtTagKm.id==ut_tagkm_tagkm.c.id_of_parent_tag")

    def __repr__(self):
        return self.tag

class UtResource(Model):

    __tablename__ = "ut_resource"
    t__table_comment = {"comment":"Resource"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    resource_id      = Column(String(100), nullable=False, comment='Resource ID')
    resource_name    = Column(String(500), comment='Resource Name')
    resource_description  = Column(String(500), comment='Resource Description')
    host_id          = Column(String(30), ForeignKey('mw_server.host_id'), nullable=False, comment='HOST ID')
    service_port     = Column(String(50), comment='http service port') # Service port
    sys_user      = Column(String(50), comment='서버 계정') # WEB 서버 이름 (manual)
    agent_id         = Column(String(30), comment='MW Agent ID') # MW Agent ID
    use_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("YES"), nullable=False, comment='사용여부') #사용여부 (Manual)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=get_date, nullable=False)    

    UniqueConstraint(resource_id)

    __table_args__ = (
        t__table_comment
    )

    mw_server        = relationship('MwServer') 
    ut_tag = relationship('UtTag', secondary=assoc_tag_resource, backref='ut_resource')
    ut_resource_added_text = relationship('UtResourceAddedText', back_populates='ut_resource', cascade='all,delete', passive_deletes=True)

    def __repr__(self):
        return self.resource_id

    def t__landscape(self):
        return getTagValueWithType(self.ut_tag,'LANDSCAPE')        

    def t__resourcetype(self):
        return getTagValueWithType(self.ut_tag, '리소스유형')

    def t__ha(self):
        return getTagValueWithType(self.ut_tag, '이중화')

    def t__incharge(self):
        t = next((t for t in self.ut_tag if t.tag.startswith('시스템')),None)        
        return t.ut_parent_tag if t else None

class UtResourceAddedText(Model):

    __tablename__ = "ut_resource_added_text"
    t__table_comment = {"comment":"Resource TEXT Type 부가정보"}
    function_comments = {}

    id              = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    ut_resource_id  = Column(Integer, ForeignKey('ut_resource.id', ondelete='CASCADE'), nullable=False)
    ut_tag_id       = Column(Integer, ForeignKey('ut_tag.id'), nullable=False)
    resource_added_name = Column(String(100), comment='부가정보 이름')
    resource_added_text = Column(Text, comment='부가정보')
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=get_date, nullable=False)    

    ut_tag  = relationship('UtTag')
    ut_resource  = relationship('UtResource')

    __table_args__ = (
        t__table_comment
    )

    def __repr__(self):
        return self.resource_added_name

class UtKmGroup(Model):
    __tablename__ = "ut_km_group"
    t__table_comment = {"comment":"지식관리 그룹"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    group_name       = Column(String(50), nullable=False, comment='그룹 이름')

    UniqueConstraint(group_name)

    __table_args__ = (
        t__table_comment,
    )

    def __repr__(self):
        return self.group_name

class UtHtmlContent(Model):

    __tablename__ = "ut_html_content"
    t__table_comment = {"comment":"지식창고"}
    function_comments = {}

    id              = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    content_id      = Column(String(100), default=get_uuid, nullable=False, comment='컨텐트 ID')
    content_name    = Column(String(200), comment='컨텐츠 이름')
    content_html    = Column(Text, comment='컨텐츠 내용')
    search_tags     = Column(String(500), comment='SEARCH TAGS')    
    user_id         = Column(String(50), default=get_user, nullable=False)
    group_id         = Column(String(50), default=get_group)
    update_on       = Column(DateTime(), default=get_date, nullable=False)    
    create_on       = Column(DateTime(), default=get_date, nullable=False)    

    UniqueConstraint(content_id)

    ut_tag = relationship('UtTag', secondary=assoc_tag_htmlcontent, backref='ut_html_content')
    ut_tagkm = relationship('UtTagKm', secondary=assoc_tagkm_htmlcontent, backref='ut_html_content')
    ut_file = relationship('UtFile', secondary=assoc_file_htmlcontent, backref='ut_html_content')
    ut_kmgroup = relationship('UtKmGroup', secondary=assoc_kmgroup_htmlcontent, backref='ut_html_content')

    __table_args__ = (
        t__table_comment
    )

    def __repr__(self):
        return datetime.now().strftime("%y-%m-%d %H:%M") + '_' + self.content_name

    def user_name(self):
        from flask_appbuilder.security.sqla.models import User
        from sqlalchemy.orm import Session
        session = Session.object_session(self)
        if session and self.user_id:
            u = session.query(User).filter_by(username=self.user_id).first()
            if u:
                return u.first_name
        return self.user_id or ''

    def pop_html(self):
        return Markup(getHtmlButton('ut_html_content','content_html','content_name',str(self.id),'^_^'))
    def show_html(self):
        return Markup('<a href="/ut/htmlcontent/'+str(self.id)+'" class="btn btn-sm btn-default" data-toggle="tooltip" rel="tooltip" title="" data-original-title="레코드 보기"><i class="fa fa-search"></i></a>')

class UtMdContent(Model):

    __tablename__ = "ut_md_content"
    t__table_comment = {"comment":"지식창고(md)"}
    function_comments = {}

    id              = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    content_id      = Column(String(100), default=get_uuid, nullable=False, comment='컨텐트 ID')
    content_name    = Column(String(200), comment='컨텐츠 이름')
    content_md    = Column(Text, comment='컨텐츠 내용')
    search_tags     = Column(String(500), comment='SEARCH TAGS')    
    user_id         = Column(String(50), default=get_user, nullable=False)
    group_id        = Column(String(50), default=get_group)
    update_on       = Column(DateTime, default=get_date, nullable=False)    
    create_on       = Column(DateTime, default=get_date, nullable=False)    

    UniqueConstraint(content_id)

    ut_tag = relationship('UtTag', secondary=assoc_tag_mdcontent, backref='ut_md_content')
    ut_tagkm = relationship('UtTagKm', secondary=assoc_tagkm_mdcontent, backref='ut_md_content')
    ut_file = relationship('UtFile', secondary=assoc_file_mdcontent, backref='ut_md_content')
    ut_kmgroup = relationship('UtKmGroup', secondary=assoc_kmgroup_mdcontent, backref='ut_md_content')

    __table_args__ = (
        t__table_comment
    )

    def __repr__(self):
        return datetime.now().strftime("%y-%m-%d %H:%M") + '_' + self.content_name

    def user_name(self):
        from flask_appbuilder.security.sqla.models import User
        from sqlalchemy.orm import Session
        session = Session.object_session(self)
        if session and self.user_id:
            u = session.query(User).filter_by(username=self.user_id).first()
            if u:
                return u.first_name
        return self.user_id or ''

    def show_md(self):
        return Markup('<a href="/ut/mdcontent/'+str(self.id)+'" class="btn btn-sm btn-default" data-toggle="tooltip" rel="tooltip" title="" data-original-title="레코드 보기"><i class="fa fa-search"></i></a>')

    def download(self):
        return Markup(
            '<a href="/ut/mdcontent.download/'+str(self.content_id)+'">Download</a>')
        
class UtFile(Model):
    __tablename__ = "ut_file"
    t__table_comment = {"comment":"지식창고 File"}
    function_comments = {}
    
    id               = Column(Integer, primary_key=True, nullable=False)
    file_name        = Column(String(50), nullable=False)
    file             = Column(FileColumn, nullable=False)
    file_description = Column(String(500))
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=get_date, nullable=False)    

    __table_args__ = (
        t__table_comment
    )

    def __repr__(self):
        return self.file_name


    def download(self):
        url='/common/download/'+str(self.file)
        return Markup(f'<a href="{url}" target="_blank">Download</a>')
            
    def get_filename(self):
        return get_file_original_name(str(self.file))

"""
assoc_tag_resource_tag = Table('ut_tag_resource_tag', Model.metadata,
                                  Column('id', Integer, primary_key=True),
                                  Column('id_of_tag', Integer, ForeignKey('ut_tag.id', ondelete='CASCADE')),
                                  Column('id_of_resource_tag', Integer, ForeignKey('ut_resource_tag.id', ondelete='CASCADE'))
)    

class UtResourceTag(Model):
    __tablename__ = "ut_resource_tag"
    t__table_comment = {"comment":"Resource TAG"}
    function_comments = {}

    id               = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    tag              = Column(String(500), nullable=False, comment='TAG')
    source           = Column(String(100), comment='리소스 원천')
    use_yn           = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("YES"), nullable=False, comment='사용여부') #사용여부 (Manual)
    user_id          = Column(String(50), default=get_user, nullable=False)
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)    

    UniqueConstraint(tag)

    __table_args__ = (
        Index('ix_ut_resource_tag_gin'
	        , func.string_to_array(tag, '-')
	        , postgresql_using='gin'
	    ),
        t__table_comment
    )

    ut_tag = relationship('UtTag', secondary=assoc_tag_resource_tag, backref='ut_resource_tag')
    mw_web           = relationship('MwWeb')
    mw_was           = relationship('MwWas')
    mw_was_instance  = relationship('MwWasInstance')


    def __repr__(self):
        return self.tag
"""