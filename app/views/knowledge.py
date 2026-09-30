from flask import g, redirect, render_template, Response, send_file, request, jsonify, abort
from flask_babel import lazy_gettext
from flask_appbuilder.models.sqla.interface import SQLAInterface
from flask_appbuilder.models.sqla.filters import FilterStartsWith
from flask_appbuilder import ModelView, expose, has_access
from flask_appbuilder.actions import action
from flask_appbuilder.api import BaseApi, expose, protect
from flask_appbuilder.filemanager import get_file_original_name, FileManager, uuid_namegen
from wtforms import TextAreaField, SelectField
from app.fieldwidgets import FlexibleDateTimeField, NativeDateTimeWidget
from app import app, db, appbuilder, con_val, PLANTUML_URL
from app.models.knowledge import UtTag, UtTagKm, UtFile, UtResource, UtResourceAddedText, UtHtmlContent\
    , UtMdContent, UtKmGroup
from app.models.common import get_user, get_date, get_uuid
from .common import FilterStartsWithFunction, FilterContainsFunction, FilterGroupMulti, FilterGroupRelation\
    , TagType, TagMustContains, ListAdvanced, ShowWithIds, get_group_str, get_group_list, GroupSelectField\
    , visible_to_current_user
from app.mail_sender import send_mail, get_emails_from_tags, get_attachments_from_s3, convert_md_to_html
from app.file_manager.s3.filemanager import S3FileManager, S3FileUploadField
from datetime import datetime
import re
import zlib
import base64
import requests
import requests
import logging
from app.api.errors import internal_error

log = logging.getLogger(__name__)

@db.event.listens_for(UtFile, 'before_insert')
def set_file_name(mapper, connection, target):
    target.file_name = get_file_original_name(str(target.file))    

@db.event.listens_for(UtMdContent, 'before_update')
def update_md_content_update(mapper, connection, target):
    target.update_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@db.event.listens_for(UtHtmlContent, 'before_update')
def update_html_content_update(mapper, connection, target):
    target.update_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class UtTagModelView(ModelView):

    datamodel = SQLAInterface(UtTag)
    
    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_title   = "Tag"
    list_columns = ['tag', 'label', 'ut_child_tag', 'ut_parent_tag']
    label_columns = {'ut_child_tag':'하위Tag'
                    ,'ut_parent_tag':'상위Tag'
                    }

    edit_exclude_columns = ['user_id', 'create_on']
    add_exclude_columns = ['user_id', 'create_on']

    extra_args = {
        'inputList':[
         {'text':'TAG 검색','id':'tag-name','combind':'0','condition':'_flt_2_tag=','size':20}
        ]
        }

class UtTagKmModelView(ModelView):

    datamodel = SQLAInterface(UtTagKm)
    
    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_title   = "지식관리 Tag"
    list_columns = ['tag', 'label', 'value1', 'ut_child_tag', 'ut_parent_tag']
    label_columns = {'ut_child_tag':'하위Tag'
                    ,'ut_parent_tag':'상위Tag'
                    }

    edit_exclude_columns = ['user_id', 'create_on']
    add_exclude_columns = ['user_id', 'create_on']

    extra_args = {
        'inputList':[
         {'text':'TAG 검색','id':'tag-name','combind':'0','condition':'_flt_2_tag=','size':20}
        ]
        }

class UtResourceAddedTextModelView(ModelView):

    datamodel = SQLAInterface(UtResourceAddedText)
    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced


    list_title   = "Resource 부가정보"
    list_columns = ['ut_tag','ut_resource','resource_added_name']
    edit_exclude_columns = ['user_id','create_on']
    add_exclude_columns = ['user_id','create_on']

    validators_columns = {
                    'ut_tag':[TagType('부가정보')]
                }

class RoleSelectField(SelectField):
    """SelectField that shows all _role roles from the system."""
    # WTForms 3.2 부터 (value, label, selected, render_kw) 4-튜플이어야 한다 (tests/test_char_select_fields.py)
    def iter_choices(self):
        try:
            from app import db
            from flask_appbuilder.security.sqla.models import Role
            all_roles = db.session.query(Role).filter(Role.name.contains('_role')).order_by(Role.name).all()
            yield ('', '-- 선택 --', not self.data, {})
            for r in all_roles:
                yield (r.name, r.name, self.data == r.name, {})
        except Exception:
            yield ('', '(없음)', True, {})

    def pre_validate(self, form):
        pass  # choices are dynamic

class UtKmGroupModelView(ModelView):

    datamodel = SQLAInterface(UtKmGroup)

    list_title   = "지식관리 그룹"
    add_title    = "지식관리 그룹 등록"
    edit_title   = "지식관리 그룹 수정"
    list_columns = ['group_name']
    label_columns = {'group_name':'그룹 이름'}
    add_columns  = ['group_name']
    edit_columns = ['group_name']

    description_columns = {
        'group_name': (
            '시스템에 등록된 Role(xxx_role) 중 하나를 선택합니다.<br>'
            '• 여기에 등록된 그룹은 지식 콘텐츠의 <b>공개그룹</b>으로 사용됩니다.<br>'
            '• 콘텐츠 편집 시 공개그룹을 지정하면, 해당 Role을 가진 사용자만 열람할 수 있습니다.<br>'
            '• 공개그룹이 지정되지 않은 콘텐츠는 <b>전체 공개</b>됩니다.'
        )
    }

    add_form_extra_fields = edit_form_extra_fields = {
        'group_name': RoleSelectField('그룹 이름', description='시스템 Role 중 선택')
    }

class UtHtmlContentModelView(ModelView):

    datamodel = SQLAInterface(UtHtmlContent)
    add_template = 'add_summer.html'
    edit_template = 'edit_summer.html'

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced


    list_title   = "지식정보(html 형식)"
    list_columns = ['show_html','ut_tag','content_name','user_id','user_name','update_on','create_on','pop_html']
    label_columns = {'show_html':'조회/발송','ut_tag':'지식유형','user_id':'작성자 ID','user_name':'작성자','update_on':'최종수정일시','create_on':'최초생성일시'
                    ,'ut_kmgroup':'공개그룹'}

    edit_exclude_columns = ['user_id', 'create_on','update_on','group_id','ut_tagkm']
    add_exclude_columns = ['user_id', 'create_on','update_on','group_id','ut_tagkm']

    add_form_query_rel_fields = {
        'ut_tag': [['tag', FilterStartsWith, '지식유형-']]
    }
    edit_form_query_rel_fields = {
        'ut_tag': [['tag', FilterStartsWith, '지식유형-']]
    }

    base_permissions = ['can_list', 'can_add', 'can_edit', 'can_delete']
    base_order = ('create_on', 'desc')

    base_filters = [['ut_kmgroup', FilterGroupRelation, get_group_list]]

    extra_args = {
        'summer_column':'content_html',
        'tags_column':'search_tags',
        'plantuml_url':PLANTUML_URL+"/png/",
        'selectList':[
         {'text':'지식유형','id':'tag-selector','combind':'1','type':'parent','condition':{'operator':'and','column':'tag','value':'지식유형'}}
        ],
        'inputList':[
         {'text':'제목 검색','id':'content-name','combind':'1','condition':'_flt_2_content_name=','size':12}
        ,{'text':'TAG 검색','id':'search-tags','combind':'1','condition':'_flt_2_search_tags=','size':12}
        ]
    }

    @action("copyHtmlContents"
            ,"지식 Copy 하기"
            ,"Copy the selected Contents?"
            ,icon="fa-copy"
            ,single=False
    )
    def copyHtmlContents(self, items):
        self.update_redirect()
        for item in items:
            new_content              = item.__class__()
            new_content.content_id   = get_uuid()
            new_content.content_html = item.content_html
            new_content.content_name = "Copied_" + item.content_name
            new_content.search_tags = item.search_tags
            new_content.update_on    = get_date()
            new_content.create_on    = get_date()
            new_content.ut_file      = item.ut_file
            new_content.ut_tag       = item.ut_tag
            
            self.datamodel.add(new_content)
        return redirect(self.get_redirect())



    def _link_uploaded_files(self, item):
        """Link drag-and-drop uploaded files to the HtmlContent item."""
        uploaded_file_ids = request.form.get('uploaded_file_ids', '')
        if uploaded_file_ids:
            file_ids = [int(fid.strip()) for fid in uploaded_file_ids.split(',') if fid.strip()]
            if file_ids:
                existing_ids = [f.id for f in item.ut_file]
                for fid in file_ids:
                    if fid not in existing_ids:
                        file_obj = db.session.query(UtFile).get(fid)
                        if file_obj:
                            item.ut_file.append(file_obj)
                db.session.commit()

    def post_add(self, item):
        self._link_uploaded_files(item)

    def post_update(self, item):
        self._link_uploaded_files(item)

class UtMdContentModelView(ModelView):

    datamodel = SQLAInterface(UtMdContent)
    add_template = 'add_md2.html'
    edit_template = 'edit_md2.html'

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_title   = "지식정보(Markdown 형식)"
    list_columns = ['show_md','ut_tag','content_name','user_id','user_name','update_on','create_on','download']
    label_columns = {'show_md':'조회/발송','ut_tag':'지식유형','user_id':'작성자 ID','user_name':'작성자','update_on':'최종수정일시','create_on':'최초생성일시'
                    ,'ut_kmgroup':'공개그룹'}

    edit_exclude_columns = ['user_id', 'create_on','group_id','ut_tagkm']
    add_exclude_columns = ['user_id', 'create_on','update_on','group_id','ut_tagkm']

    add_form_query_rel_fields = {
        'ut_tag': [['tag', FilterStartsWith, '지식유형-']]
    }

    base_permissions = ['can_list', 'can_add', 'can_edit', 'can_delete']
    base_order = ('create_on', 'desc')

    base_filters = [['ut_kmgroup', FilterGroupRelation, get_group_list]]

    edit_form_extra_fields = {
        # FAB 기본 위젯은 시분초를 입력할 수 없다. app/fieldwidgets.py 참조.
        'update_on': FlexibleDateTimeField('수정 일시', widget=NativeDateTimeWidget())
    }
    edit_form_query_rel_fields = {
        'ut_tag': [['tag', FilterStartsWith, '지식유형-']]
    }

    extra_args = {
        'summer_column':'content_md',
        'tags_column':'search_tags',
        'selectList':[
         {'text':'지식유형','id':'tag-selector','combind':'1','type':'parent','condition':{'operator':'and','column':'tag','value':'지식유형'}}
        ],
        'inputList':[
         {'text':'제목 검색','id':'content-name','combind':'1','condition':'_flt_2_content_name=','size':12}
        ,{'text':'TAG 검색','id':'search-tags','combind':'1','condition':'_flt_2_search_tags=','size':12}
        ]
    }

    @action("copyMdContents"
            ,"지식 Copy 하기"
            ,"Copy the selected Contents?"
            ,icon="fa-copy"
            ,single=False
    )
    def copyMdContents(self, items):
        self.update_redirect()
        for item in items:
            new_content              = item.__class__()
            new_content.content_id   = get_uuid()
            new_content.content_md = item.content_md
            new_content.content_name = "Copied_" + item.content_name
            new_content.search_tags = item.search_tags
            new_content.update_on    = get_date()
            new_content.create_on    = get_date()
            new_content.ut_file      = item.ut_file
            new_content.ut_tag       = item.ut_tag
            
            self.datamodel.add(new_content)
        return redirect(self.get_redirect())



    def _link_uploaded_files(self, item):
        """Link drag-and-drop uploaded files to the MdContent item."""
        uploaded_file_ids = request.form.get('uploaded_file_ids', '')
        if uploaded_file_ids:
            file_ids = [int(fid.strip()) for fid in uploaded_file_ids.split(',') if fid.strip()]
            if file_ids:
                existing_ids = [f.id for f in item.ut_file]
                for fid in file_ids:
                    if fid not in existing_ids:
                        file_obj = db.session.query(UtFile).get(fid)
                        if file_obj:
                            item.ut_file.append(file_obj)
                db.session.commit()

    def post_add(self, item):
        self._link_uploaded_files(item)

    def post_update(self, item):
        self._link_uploaded_files(item)

class UtFileModelView(ModelView):
    datamodel = SQLAInterface(UtFile)

    label_columns = {'ut_html_content':"지식정보(Html)", 'ut_md_content':"지식정보(Markdown)", "file_name": "File Name", "download": "Download"}
    add_columns   = ['ut_html_content','ut_md_content','file']
    edit_columns  = ['ut_html_content','ut_md_content','file']
    list_columns  = ['ut_html_content','ut_md_content','file_name','file','download','create_on']
    show_columns  = ['file', 'file_name','download', 'user_id','create_on']

    base_order = ('create_on', 'desc')

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

class UtResourceModelView(ModelView):

    datamodel = SQLAInterface(UtResource)
    
    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_title   = "Resource"
    list_columns = ['resource_id', 'resource_name', 'host_id', 'mw_server.ip_address', 'service_port', 'sys_user', 't__landscape', 't__resourcetype', 't__incharge', 't__ha', 'resource_description']
    edit_exclude_columns = ['user_id','create_on']
    add_exclude_columns = ['user_id','create_on']


    description_columns = {'ut_tag':"'리소스유형', 'LANDSCAPE', '시스템'은 필수입니다."}
    validators_columns = {
                    'ut_tag':[TagMustContains(['리소스유형','LANDSCAPE'])]
                }

    extra_args = {
        'selectList':[
         {'text':'리소스유형','id':'tag-selector','combind':'0','type':'parent','condition':{'operator':'and','column':'tag','value':'리소스유형'}}
         ,{'text':'LANDSCAPE','id':'tag-selector','combind':'0','type':'parent','condition':{'operator':'and','column':'tag','value':'LANDSCAPE'}}
        ]
        }

    related_views = [UtResourceAddedTextModelView]

class UtApi(BaseApi):

    route_base = '/ut'

    @expose('/htmlcontent/<param>', methods=['GET'])
    @has_access
    def uthtmlcontent(self, param=None):

        title = ''
        html = ''
        update_on = ''
        files = []

        # 목록과 같은 그룹 기준 — id 를 바꿔 다른 그룹 문서를 열지 못하게 한다 (HOWTO_020 §6)
        row = visible_to_current_user(UtHtmlContent).filter(UtHtmlContent.id == int(param)).first()
        if row is None:
            abort(404)

        if row:
            title = row.content_name
            html  = row.content_html
            update_on = row.update_on.strftime("%Y-%m-%d %H:%M:%S")
            
            if row.ut_file:
                for f in row.ut_file:
                    files.append(dict(
                        file_name=f.file_name
                       ,file=f.file
                    ))

        return render_template('show_raw.html'\
            , title=title
            , html=html
            , update_on=update_on
            , update_page='/uthtmlcontentmodelview/edit/'+param
            , content_id=param
            , files=files
            , base_template=appbuilder.base_template
            , appbuilder=appbuilder
            )

    @expose('/mdcontent/<param>', methods=['GET'])
    @has_access
    def utmdcontent(self, param=None):

        title = ''
        html = ''
        update_on = ''
        files = []

        row = visible_to_current_user(UtMdContent).filter(UtMdContent.id == int(param)).first()
        if row is None:
            abort(404)

        if row:
            title = row.content_name
            md  = row.content_md
            update_on = row.update_on.strftime("%Y-%m-%d %H:%M:%S")
            
            if row.ut_file:
                for f in row.ut_file:
                    files.append(dict(
                        file_name=f.file_name
                       ,file=f.file
                    ))

        return render_template('show_md2.html'\
            , plantuml_url=PLANTUML_URL+"/png/"
            , title=title
            , md=md
            , update_on=update_on
            , update_page='/utmdcontentmodelview/edit/'+param
            , content_id=param
            , files=files
            , base_template=appbuilder.base_template
            , appbuilder=appbuilder
            )

    @expose('/mdcontent.download/<content_id>', methods=['GET'])
    @has_access
    def mddownload(self, content_id):

        row = visible_to_current_user(UtMdContent).filter(UtMdContent.content_id == content_id).first()
        if row is None:
            abort(404)

        md = row.content_md or ''

        return Response(md, 
            mimetype="text/plain",
            headers={"Content-Disposition":"attachment;filename="+content_id+".md"})

    @expose('/upload_file', methods=['POST'])
    @has_access
    def upload_file(self):
        """Drag & Drop file upload API.
        Saves file to S3 and creates UtFile record.
        Returns file_id, file_name, download_url.
        """
        if 'file' not in request.files:
            return jsonify(error='No file provided'), 400

        file = request.files['file']
        if not file.filename:
            return jsonify(error='Empty filename'), 400

        try:
            # Generate unique filename and save to S3
            file_manager = S3FileManager()
            s3_filename = uuid_namegen(file)
            file_data = file.read()
            file_manager.save_file(file_data, s3_filename)

            # Create UtFile record
            ut_file = UtFile()
            ut_file.file = s3_filename
            ut_file.file_name = file.filename
            ut_file.user_id = g.user.username if g.user else 'system'
            db.session.add(ut_file)
            db.session.commit()

            return jsonify(
                file_id=ut_file.id,
                file_name=file.filename,
                s3_filename=s3_filename,
                download_url='/common/download/' + s3_filename
            ), 200

        except Exception:
            db.session.rollback()
            return internal_error('knowledge request failed', key='error')

    @expose('/email_tags', methods=['GET'])
    @has_access
    def email_tags(self):
        """Return list of '이메일-' tags with their email addresses (value1)."""
        tag_prefix = con_val.get('TAG_EMAILS', '이메일-')
        tags = db.session.query(UtTag).filter(UtTag.tag.startswith(tag_prefix)).order_by(UtTag.tag).all()
        result = []
        for t in tags:
            result.append({
                'tag': t.tag,
                'emails': t.value1 or ''
            })
        return jsonify(tags=result)

    @expose('/htmlcontent/<int:content_id>/send_email', methods=['POST'])
    @has_access
    def send_html_email(self, content_id):
        """Send email for a specific HtmlContent from the show page."""
        from premailer import transform
        row = visible_to_current_user(UtHtmlContent).filter(UtHtmlContent.id == content_id).first()
        if not row:
            return jsonify(error='Content not found'), 404

        data = request.get_json() or {}
        emails = get_emails_from_tags(data.get('tag_names', []), data.get('manual_emails', ''), db.session, UtTag)
        if not emails:
            return jsonify(error='발송 대상 이메일이 없습니다.'), 400

        files = get_attachments_from_s3(row.ut_file, S3FileManager)

        try:
            inlined_html = transform(row.content_html) if row.content_html else ''
            send_mail(con_val['SMTP_HOST'], con_val['SMTP_PORT']
                    , con_val.get('SMTP_SENDER', ''), g.user.username
                    , emails, row.content_name, inlined_html
                    , files=files
                    , use_tls=con_val.get('SMTP_USE_TLS', False)
                    , username=con_val.get('SMTP_USERNAME')
                    , password=con_val.get('SMTP_PASSWORD'))
            return jsonify(success=True, message=f'{len(emails)}명에게 발송 완료', emails=emails)
        except Exception:
            return internal_error('Email send failed', key='error')

    @expose('/mdcontent/<int:content_id>/send_email', methods=['POST'])
    @has_access
    def send_md_email(self, content_id):
        """Send email for a specific MdContent from the show page."""
        row = visible_to_current_user(UtMdContent).filter(UtMdContent.id == content_id).first()
        if not row:
            return jsonify(error='Content not found'), 404

        data = request.get_json() or {}
        emails = get_emails_from_tags(data.get('tag_names', []), data.get('manual_emails', ''), db.session, UtTag)
        if not emails:
            return jsonify(error='발송 대상 이메일이 없습니다.'), 400

        files = get_attachments_from_s3(row.ut_file, S3FileManager)

        kroki_url = con_val.get('KROKI_URL', 'http://mwm-kroki:8000').rstrip('/')
        inlined_html, inline_images = convert_md_to_html(row.content_md, kroki_url)

        try:
            send_mail(con_val['SMTP_HOST'], con_val['SMTP_PORT']
                    , con_val.get('SMTP_SENDER', ''), g.user.username
                    , emails, row.content_name, inlined_html
                    , files=files
                    , use_tls=con_val.get('SMTP_USE_TLS', False)
                    , username=con_val.get('SMTP_USERNAME')
                    , password=con_val.get('SMTP_PASSWORD')
                    , inline_images=inline_images)
            return jsonify(success=True, message=f'{len(emails)}명에게 발송 완료', emails=emails)
        except Exception:
            return internal_error('Email send failed', key='error')

#appbuilder.add_separator("Server")
appbuilder.add_separator("Server")
appbuilder.add_view(
    UtResourceModelView,
    "Resource",
    icon="fa-folder-open-o",
    category="Server",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    UtResourceAddedTextModelView,
    "Resource 부가정보(TEXT)",
    icon="fa-folder-open-o",
    category="Server",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    UtTagModelView,
    "마스터정보Tag",
    icon="fa-folder-open-o",
    category="지식관리",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    UtTagKmModelView,
    "지식관리Tag",
    icon="fa-folder-open-o",
    category="지식관리",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    UtKmGroupModelView,
    "지식관리그룹",
    icon="fa-users",
    category="지식관리",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    UtHtmlContentModelView,
    "지식정보(Html)",
    icon="fa-folder-open-o",
    category="지식관리",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    UtMdContentModelView,
    "지식정보(Markdown)",
    icon="fa-folder-open-o",
    category="지식관리",
    category_icon="fa-envelope"
)
appbuilder.add_view(
    UtFileModelView,
    "지식정보(File)",
    icon="fa-folder-open-o",
    category="지식관리",
    category_icon="fa-envelope"
)
appbuilder.add_api(UtApi)
