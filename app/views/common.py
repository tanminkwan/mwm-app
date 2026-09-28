from flask import g
from flask_appbuilder import BaseView, expose, has_access
from flask_appbuilder.models.sqla.filters import BaseFilter, get_field_setup_query
from flask_appbuilder.fieldwidgets import BS3TextFieldWidget
from flask_appbuilder.widgets import ShowWidget, ListWidget
from wtforms.validators import ValidationError, StopValidation
from wtforms import SelectField
import enum
from app.sqls.monitor import get_last_reported_time, select_row
from app.models.common import get_group, get_groups
import requests
import json
from app import app
import logging

def get_mw_user():
    roles = [ r.name for r in g.user.roles]
    if 'mw_role' in roles or 'Admin' in roles:
        return ''
    else:
        return g.user.username

def get_group_str():
    roles = [ r.name for r in g.user.roles]
    group = get_group()
    print("Group : ", group)
    if 'Admin' in roles:
        return ''
    elif group:
        return group
    else:
        return 'XXX'

def get_group_list():
    """Return list of all _role groups for the current user.
    Returns empty list for Admin (meaning no filter = see all).
    Returns ['XXX'] if user has no _role (meaning see nothing).
    """
    roles = [r.name for r in g.user.roles]
    if 'Admin' in roles:
        return []
    groups = get_groups()
    return groups if groups else ['XXX']

def get_userid():
    return g.user.username

def get_reporttime():
    return get_last_reported_time()

class ShowWithIds(ShowWidget):
    template = 'widgets/showWithIds.html'

class ListAdvanced(ListWidget):
    template = 'widgets/listWithSafeFormatter.html'

class ReadOnlyField(BS3TextFieldWidget):
    def __call__(self, field, **kwargs):
        kwargs['readonly'] = 'true'
        return super(ReadOnlyField, self).__call__(field, **kwargs)

class GroupSelectField(SelectField):
    """Dynamic SelectField that populates choices with current user's _role roles.
    For Admin users without _role, fetches all _role roles from the system.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def iter_choices(self):
        try:
            roles = [r.name for r in g.user.roles]
            groups = get_groups()
            if not groups and 'Admin' in roles:
                # Admin: fetch all _role roles from the system
                from app import db
                from flask_appbuilder.security.sqla.models import Role
                all_roles = db.session.query(Role).filter(Role.name.contains('_role')).all()
                groups = [r.name for r in all_roles]
            if not groups:
                yield ('', '(없음)', self.data == '')
            for group in groups:
                yield (group, group, self.data == group)
        except Exception:
            yield ('', '(없음)', True)

    def pre_validate(self, form):
        pass  # Allow any value since choices are dynamic

class FilterStartsWithFunction(BaseFilter):
    name = "Filter view with a function"
    arg_name = "eqf"

    def apply(self, query, func):
        query, field = get_field_setup_query(query, self.model, self.column_name)
        return query.filter(field.ilike(func() + "%%"))
    
class FilterContainsFunction(BaseFilter):
    name = "Filter view with a function"
    arg_name = "eqf"

    def apply(self, query, func):
        query, field = get_field_setup_query(query, self.model, self.column_name)
        return query.filter(field.contains(func()))

class FilterGroupMulti(BaseFilter):
    """Filter that supports multiple group values with OR condition.
    The function should return a list of group strings.
    Empty list means no filter (Admin sees all).
    """
    name = "Filter view with multiple groups"
    arg_name = "eqf"

    def apply(self, query, func):
        from sqlalchemy import or_
        query, field = get_field_setup_query(query, self.model, self.column_name)
        groups = func()
        if not groups:
            return query  # Admin: no filter
        conditions = [field.contains(g) for g in groups]
        return query.filter(or_(*conditions))

class FilterGroupRelation(BaseFilter):
    """Filter based on many-to-many group relationship.
    Shows records that have matching groups OR no groups at all (전체 공개)
    OR created by the current user (본인 작성).
    The function should return a list of group_name strings.
    Empty list means no filter (Admin sees all).
    """
    name = "Filter by group relationship"
    arg_name = "grprel"

    def apply(self, query, func):
        from sqlalchemy import or_
        from app.models.knowledge import UtKmGroup

        groups = func()
        if not groups:
            return query  # Admin: no filter

        rel = getattr(self.model, self.column_name)
        # Records that have at least one matching group
        has_matching = rel.any(UtKmGroup.group_name.in_(groups))
        # Records that have NO groups at all (visible to all)
        has_none = ~rel.any()
        # Records created by the current user
        is_mine = self.model.user_id == g.user.username

        return query.filter(or_(has_matching, has_none, is_mine))

class FilterIsNull(BaseFilter):
    name = "Is null or empty"
    arg_name = "null"

    def apply(self, query, value):
        query, field = get_field_setup_query(query, self.model, self.column_name)
        return query.filter(field == None)

class FilterNotNull(BaseFilter):
    name = "Is not null and not empty"
    arg_name = "nn"

    def apply(self, query, value):
        query, field = get_field_setup_query(query, self.model, self.column_name)
        return query.filter(field != None)

def call_notification(text):

        logging.info(f"call_notification is called. msg : {text}")

        headers = {'Content-Type':'application/json;charset=utf-8'}
        data = {"msg": text}
        url = app.config['NOTIFICATION_URL']

        resp = requests.post(url, data=json.dumps(data), headers=headers, verify=False)

        if resp.status_code != 200:
            logging.error(f'notification 연계시 Error발생 : {str(resp.status_code)}')
            return

        results = resp.json()

        logging.info(f'Return : {results}')

        return

class RequiredOnContidion(object):

    def __init__(self, fieldname, value, message=None):
        self.fieldnames = fieldname if isinstance(fieldname, list) else [fieldname]
        self.message = message
        # If fieldnames is a list, value should ideally be a list of lists or a list of values
        # To keep it simple and backward compatible:
        self.values = value if isinstance(value, list) else [value]
        
    def __call__(self, form, field):
        condition_met = True
        
        for i, fname in enumerate(self.fieldnames):
            try:
                other = form[fname]
            except KeyError:
                raise ValidationError(field.gettext("Invalid field name '%s'.") % fname)

            if isinstance(other.data, enum.Enum):
                real_data = other.data.name
            else:
                real_data = other.data
            
            # Match against the corresponding value in self.values
            # If self.values is shorter than fieldnames, we check against the first value or use indices
            target_value = self.values[i] if i < len(self.values) else self.values[0]
            
            # If target_value is a list, check if real_data is in it. Otherwise, direct comparison.
            if isinstance(target_value, list):
                if real_data not in target_value:
                    condition_met = False
                    break
            else:
                if real_data != target_value:
                    condition_met = False
                    break
        
        if condition_met and not field.data:
            message = self.message
            if message is None:
                message = field.gettext('This field is required')
            raise StopValidation(message)

class ValidateBatchFunctionName:

    def __call__(self, form, field):

        try:
            other = form['command_class']
        except KeyError:
            raise ValidationError(field.gettext(f"Invalid field name 'command_class'."))

        if isinstance(other.data, enum.Enum):
            real_data = other.data.name
        else:
            real_data = other.data

        from app.sqls.batch import batch_function_registry
        
        if real_data == 'ServerFunc' and \
            not batch_function_registry.get(field.data):
            raise StopValidation(field.gettext(f"Invalid Function name : {field.data}."))

class TagType(object):

    def __init__(self, tagtype):
        self.tagtype = tagtype

    def __call__(self, form, field):

        tag = field.data.tag
        
        if not tag.startswith(self.tagtype):
            d = {
                'other_label': self.tagtype,
                'other_name': self.tagtype
            }
            message = field.gettext('\'%(other_name)s\'로 시작하는 Tag를 선택하세요.')

            raise ValidationError(message % d)

class TagMustContains(object):

    def __init__(self, tagtypes):
        self.tagtypes = tagtypes

    def __call__(self, form, field):

        if not field.data:
            raise ValidationError(field.gettext("Tag를 선택하여 주세요."))

        for rec in field.data:
            for tagtype in self.tagtypes:
                if rec.tag.startswith(tagtype):
                    self.tagtypes.remove(tagtype)

        if self.tagtypes:
            t = ','.join(self.tagtypes)
            message = field.gettext("다음 tag type들을 추가하시기 바랍니다. '%s'.") % t
            raise ValidationError(message)

class TokenView(BaseView):
    route_base = "/token"
    default_view = "manage"
    
    @expose("/manage")
    @has_access
    def manage(self):
        return self.render_template("token_manage.html")