from app import db
from flask import g, current_app
from sqlalchemy.sql import update, func, sqltypes
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import insert, JSON
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import InstrumentedAttribute, ScalarAttributeImpl, ScalarObjectAttributeImpl, CollectionAttributeImpl
from app.models.agent import AgResult
from app.models.monitor import MoWasInstanceStatus, MoWasStatusTemplate, MoWasStatusReport\
    , MoGridConfig
from app.models.was import MwWas, MwWasInstance, MwWeb, MwWebVhost, MwWebDomain
from app.models.common import YnEnum, LocationEnum
import re
from croniter import croniter
import types
from sys import exc_info
import logging

def _get_table_dict():
    """Returns a dictionary of all tables defined in db.Model."""
    return {table.__tablename__: table for table in db.Model.__subclasses__()}

def _get_table_args():
    """Returns a dictionary of __table_args__ for all models."""
    result = {}
    for table in db.Model.__subclasses__():
        targs = getattr(table, '__table_args__', None)
        if isinstance(targs, tuple):
            # Last element of tuple is the dict with comment etc.
            for item in targs:
                if isinstance(item, dict):
                    result[table.__tablename__] = item
                    break
        elif isinstance(targs, dict):
            result[table.__tablename__] = targs
    return result

def get_all_tables():
    return [t for t in _get_table_dict()]

def select_row(table_name, filter_dict):
    table_dict = _get_table_dict()
    filter_list = []
    table = table_dict[table_name]

    for item in filter_dict:
        col = getattr(table, item)
        filter_list.append(col==filter_dict[item])

    rec = db.session.query(table)\
        .filter(*filter_list).first()

    return rec, 1 if rec else 0

def select_rows(table_name, filter_dict):
    table_dict = _get_table_dict()
    filter_list = []
    table = table_dict[table_name]

    for item in filter_dict:
        col = getattr(table, item)
        filter_list.append(col==filter_dict[item])

    recs = db.session.query(table)\
        .filter(*filter_list).all()

    return recs, 1 if recs else 0

 
def select_item(table_name, column_name, filter_dict):
    table_dict = _get_table_dict()
    filter_list = []
    table = table_dict[table_name]
    column = getattr(table, column_name)

    for item in filter_dict:
        col = getattr(table, item)
        filter_list.append(col==filter_dict[item])

    value = db.session.query(column)\
        .filter(*filter_list).first()

    return value, 1 if value else 0

def select_items(table_name, column_name, filter_dict):
    table_dict = _get_table_dict()
    filter_list = []
    table = table_dict[table_name]
    column = getattr(table, column_name)

    for item in filter_dict:
        col = getattr(table, item)
        filter_list.append(col==filter_dict[item])

    values = db.session.query(column)\
            .filter(*filter_list).distinct()
    
    return values, 1 if values else 0

def insert_row(table_name, insert_dict):
    table_dict = _get_table_dict()
    table = table_dict[table_name]

    if g and g.user:
        user_id = g.user.username
    else:
        user_id = 'scheduler'

    insert_dict.update(dict(user_id=user_id, create_on=datetime.now()))

    # Normalize host fields
    for field in ['host_id', 'located_host_id']:
        if field in insert_dict and isinstance(insert_dict[field], str):
            insert_dict[field] = insert_dict[field].lower()

    stmt = insert(table).values(insert_dict)

    try:
        result = db.session.execute(stmt)
        pk = result.inserted_primary_key
    except IntegrityError as e:
        return -1, 'UniqueViolation'

    return pk[0], 'OK'

def update_rows(table_name, update_dict, filter_dict):
    table_dict = _get_table_dict()
    filter_list = []
    table = table_dict[table_name]

    # Normalize update and filter fields
    for field in ['host_id', 'located_host_id']:
        if field in update_dict and isinstance(update_dict[field], str):
            update_dict[field] = update_dict[field].lower()
        if field in filter_dict and isinstance(filter_dict[field], str):
            filter_dict[field] = filter_dict[field].lower()

    for item in filter_dict:
        col = getattr(table, item)
        filter_list.append(col==filter_dict[item])

    rt = db.session.query(table)\
        .filter(*filter_list)\
        .update(update_dict)

    if rt < 1:
        return -1, table_name + ' data to update isn\'t found : '
    return 1, ''

def select_tags(table_name, column_name, seperator, filter_list):
    table_dict = _get_table_dict()
    table = table_dict[table_name]
    column = getattr(table, column_name)

    recs = db.session.query(table)\
        .filter(func.string_to_array(column,seperator).op("@>")(filter_list)).all()

    return recs, 1 if recs else 0

def get_model_info(table_name):
    table_dict = _get_table_dict()
    table_args = _get_table_args()
    table = None
    spec = dict(table_name=table_name,columns=[])
    if table_dict.get(table_name):
        
        table = table_dict[table_name]

        foreign = {f._colspec.split('.')[1]:f._colspec for f in table.__table__.foreign_keys}
        
        print('foreign :', foreign)
        #for f in table.__table__.foreign_keys:
        #    print('HHH : ', f._colspec, f._colspec.split('.')[1])
        #for it, tt in inspect(table).relationships.items():
        #    print('HHH :', type(it), tt.secondary, tt.__dict__)

        spec['table_comment'] = table_args[table_name]['comment']\
                             if table_args[table_name].get('comment') else ''
        t = table.__dict__

        for col in t:
            if col.startswith('t__') and type(t[col]) is types.FunctionType:
                print('HHH 3 : ', col, t[col], type(t[col]), type(t[col]) is types.FunctionType)
                spec['columns'].append(dict(
                    name=col
                   ,type='BIND FUNCTION'
                   ,comment=table.function_comments[col] if table.function_comments.get(col) else ''
                   ,foreign=''
                   ))
            if isinstance(t[col], InstrumentedAttribute):
                c = getattr(table, col)
                col_spec = ''
                col_comment = ''
                col_foreign = ''
                if isinstance(c.impl, ScalarObjectAttributeImpl):
                    col_spec = 'PARENT'
                    col_comment = table_args[col]['comment'] if table_args.get(col) and table_args[col].get('comment') else ''
                elif isinstance(c.impl, ScalarAttributeImpl):
                    col_spec = str(c.type)
                    col_comment = c.comment if c.comment else ''
                    col_foreign = foreign[col] if foreign.get(col) else ''
                elif isinstance(c.impl, CollectionAttributeImpl):
                    col_spec = 'CHILD'
                    col_comment = table_args[col]['comment'] if table_args.get(col) and table_args[col].get('comment') else ''
                    second = next( (tt.secondary for it, tt in inspect(table).relationships.items() if it == col), None)
                    #print('HHH2 : ',second)
                    if second != None:
                        col_spec = 'MbyN'

                spec['columns'].append(dict(
                    name=col
                   ,type=col_spec
                   ,comment=col_comment
                   ,foreign=col_foreign
                   ))
    else:
        return None
    
    return spec

def get_column_type(table_name, column_name):
    table_dict = _get_table_dict()
    obj = getattr(table_dict[table_name], column_name)
    print('TYPE : ',column_name, obj.type, type(obj.type))
    col_v = ''
    if isinstance(obj.type, sqltypes.Enum):
        col_v = 'enum'
    elif isinstance(obj.type, sqltypes.DateTime):
        col_v = 'datetime'
    elif isinstance(obj.type, sqltypes.Integer):
        col_v = 'int'
    elif column_name == 'tag':
        col_v = 'tag'
    else:
        col_v = 'str'

    return col_v

def get_target_table_name(table_name, column_name):
    table_dict = _get_table_dict()
    if isinstance(table_name, str):
        table = table_dict[table_name]
    else:
        table = table_name

    second = next( ( tt for it, tt in inspect(table).relationships.items() if it == column_name), None)
    return second.target.name

def _get_condition(table, condition):
    results = []
    for c in condition:
        column = getattr(table, c['column'])
        value = None
        #if isinstance(column.type, sqltypes.DateTime):
        #    value = c['value'].strptime('%Y-%m-%dT%H:%M')
        #else:
        #    value = c['value']
        value = c['value']

        if c['operator']=='eql':
            results.append(column==value)
        elif c['operator']=='like':
            results.append(column.like('%'+value+'%'))
        elif c['operator']=='neql':
            results.append(column!=value)
        elif c['operator']=='nlike':
            results.append(column.notlike('%'+value+'%'))
        elif c['operator']=='gt':
            results.append(column>=value)
        elif c['operator']=='lt':
            results.append(column<=value)
        elif c['operator']=='and':
            results.append(func.string_to_array(column,'-').op("@>")(value.split(',')))
        elif c['operator']=='or':
            results.append(func.string_to_array(column,'-').op("&&")(value.split(',')))

    return results

def select_rows2(table_name, column_name=None, condition=None, join_conditions=None\
                , distinct=True, sort_condition=None):
    table_dict = _get_table_dict()
    table     = table_dict[table_name]

    if column_name:
        column = getattr(table, column_name)
        if distinct:
            base_q    = db.session.query(column)
        else:
            base_q    = db.session.query(column, table.id)
    else:
        base_q    = db.session.query(table)

    if condition:
        flt   = _get_condition(table, condition)
        flt_q = base_q.filter(*flt)
    else:
        flt_q = base_q
    
    if join_conditions:
        join_q = flt_q
        for join_path, join_condition in join_conditions.items():
            path_parts = join_path.split('.')
            current_model = table
            # Keep track of the last joined entity/alias to join from and filter on
            last_alias = table 

            for i, part in enumerate(path_parts):
                # Get the relationship attribute from the current model
                rel_attr = getattr(current_model, part)
                
                # Get the target model from the relationship
                # Use inspection to find the target model properly
                mapper = rel_attr.property.mapper
                target_model = mapper.class_
                
                # Create an alias for joining (to avoid conflicts if the same table is joined multiple times or joined back to itself)
                new_alias = aliased(target_model)
                
                # Join to the new alias using the relationship attribute from the PREVIOUS alias/model
                # Wait, rel_attr was from current_model. We need the one from last_alias if it's an alias.
                # In SQLAlchemy, if last_alias is an alias of current_model, last_alias.part is the correct attribute.
                join_attr = getattr(last_alias, part)
                join_q = join_q.join(new_alias, join_attr)
                
                # Update for the next iteration
                current_model = target_model
                last_alias = new_alias

            # Apply filters on the LAST joined table in the path
            join_flt = _get_condition(last_alias, join_condition)
            join_q = join_q.filter(*join_flt)
    else:
        join_q = flt_q

    if sort_condition:
        sort = []
        for s in sort_condition:
            column = getattr(table, s['column'])
            if s.get('option') and s['option'] == 'desc':
                func = column.desc()
            else:
                func = column.asc()
            sort.append(func)
        join_q = join_q.order_by(*sort)

    print('mwm SQL :', join_q)
    try:
        # Explicitly fetching all results before the session has a chance to change state
        recs = join_q.all()
        # Create a static copy if it's an object with lazy-load potential to avoid closures later
        return recs, '' if recs else None
    except Exception as e:
        print(f"Error in select_rows2: {str(e)}")
        return None, str(e)

def get_grid_config(grid_key=None):

    if grid_key:
        return db.session.query(MoGridConfig)\
            .filter(MoGridConfig.grid_key==grid_key).first()
    else:
        return db.session.query(MoGridConfig).all()

def get_last_reported_time():
    
    result = db.session.query(func.max(MoWasStatusReport.reported_time)).first()

    if result[0]:
        return result[0]
    else:
        return 'novalue'

def get_was_status_template():

    result = []
    groups = []
    wit_recs = db.session.query(MoWasStatusTemplate).all()

    for wit_rec in wit_recs:

        host_id = wit_rec.mw_was.located_host_id
        was_id  = wit_rec.was_id
        dict_rec = wit_rec.__dict__
        groups.append(wit_rec.was_instance_group)

        for i in range(1, 16):

            was_instance_id = dict_rec['wi_'+str(i).zfill(2)]

            if not was_instance_id:
                continue

            was_instance_dict = dict(
                was_id  = was_id
               ,host_id = host_id
               ,was_instance_id = was_instance_id
               ,was_instance_group = wit_rec.was_instance_group
            )

            result.append(was_instance_dict)

    return result, groups

def _is_now_in_any_cron_range(cron_range_exprs, now=None):
    """
    여러 크론+범위 표현식을 확인해서 하나라도 현재 시간과 일치하면 True 반환
    """
    if not cron_range_exprs:
        return False
    
    def parse_cron_range_list(expr_list_str):
        """
		문자열을 개별 cron+range 표현식 리스트로 파싱
		"""
		# 쉼표나 줄바꿈을 기준으로 나눔
        lines = re.split(r'[,\n]+', expr_list_str)
        return [line.strip() for line in lines if line.strip()]
	
    now = now or datetime.now()
    entries = parse_cron_range_list(cron_range_exprs)

    for entry in entries:
        logging.debug(f"cron expression entry : {entry}")
        match = re.match(r'^(.+):\s*(\d+)$', entry)
        if not match:
            raise ValueError(f"잘못된 형식: {entry} (예: '0 9 * * 1-5:30')")
        
        cron_expr, duration_minutes = match.group(1), int(match.group(2))

        iter = croniter(cron_expr, now)
        start_time = iter.get_prev(datetime)
        end_time = start_time + timedelta(minutes=duration_minutes)

        if start_time <= now < end_time:
            return True  # 현재 시간이 포함되는 범위 발견

    return False

def get_not_running_was_list():

    uncheckedDomains = set()
    results1 = []
    results2 = []
    results3 = set()
    current_date = datetime.now()
    _threshold = timedelta(hours=1)

    # 변경: MwWas(landscape=PROD, use_yn=YES) 이고 MwWasInstance(use_yn=YES) 인 대상 조회
    instances = db.session.query(MwWasInstance).join(MwWas).filter(
        MwWas.landscape == LocationEnum.PROD,
        MwWas.use_yn == YnEnum.YES,
        MwWasInstance.use_yn == YnEnum.YES
    ).all()

    # Domain별 Blackout 정보 캐시 (여러 인스턴스가 동일 도메인에 속하므로 중복 체크 방지)
    blackout_cache = {}

    for instance in instances:
        was_id = instance.was_id
        
        if was_id not in blackout_cache:
            blackout_cache[was_id] = _is_now_in_any_cron_range(instance.mw_was.blackout_info)
        
        is_blacked_out = blackout_cache[was_id]

        if is_blacked_out:
            logging.debug(f"## was_id : {was_id} is_blacked_out : {is_blacked_out}")

        was_instance_id = instance.was_instance_id

        wis_rec = db.session.query(MoWasInstanceStatus)\
            .filter(MoWasInstanceStatus.update_on > current_date - _threshold\
                    , MoWasInstanceStatus.was_id==was_id\
                    , MoWasInstanceStatus.was_instance_id==was_instance_id).first()

        if wis_rec:
            if  wis_rec.was_instance_status.name == 'RUNNING':
                continue
            else:

                if not is_blacked_out:
                    results2.append(dict(
                        domain_id=was_id,
                        was_instance_group='Instance',
                        was_instance_id=was_instance_id,
                        was_instance_stat=wis_rec.was_instance_status.name,
                        host_id=wis_rec.host_id,
                    ))

                results3.add((was_id, instance.mw_was.agent_id))
        else:
            uncheckedDomains.add(was_id)
            results3.add((was_id, instance.mw_was.agent_id))

    for domain_id in uncheckedDomains:

        was_rec, _ = select_row('mw_was', {'was_id':domain_id})

        host_id = ''
        sys_user = ''
        if was_rec:
            host_id = was_rec.located_host_id
            sys_user = was_rec.sys_user
        
        results1.append(dict(
            domain_id=domain_id
           ,host_id=host_id
           ,sys_user=sys_user
        ))
    
    return results1, results2, results3

def create_was_status_report():

    current_date = datetime.now()
    _threshold = timedelta(hours=1)

    reported_time = current_date.strftime('%Y%m%d.%H%M%S')

    wit_recs = db.session.query(MoWasStatusTemplate)\
                .order_by(MoWasStatusTemplate.was_id.asc()).order_by(MoWasStatusTemplate.was_instance_group.asc()).all()

    for wit_rec in wit_recs:

        dict_rec = wit_rec.__dict__

        insert_dict = dict()
        for i in range(1, 26):

            was_instance_id = dict_rec['wi_'+str(i).zfill(2)]

            if not was_instance_id:
                continue

            insert_dict.update({'wi_'+str(i).zfill(2):was_instance_id})

            wis_rec = db.session.query(MoWasInstanceStatus)\
                .filter(MoWasInstanceStatus.update_on > current_date - _threshold\
                        , MoWasInstanceStatus.was_id==wit_rec.was_id\
                        , MoWasInstanceStatus.was_instance_id==was_instance_id).first()

            if wis_rec:
                was_instance_stat = wis_rec.was_instance_status.name
                insert_dict.update({'checked_date':wis_rec.update_on})
            else:
                was_instance_stat = 'NOVALUE'

            insert_dict.update({'wi_'+str(i).zfill(2)+'_stat':was_instance_stat})
            
        if not insert_dict.get('checked_date'):
            insert_dict['checked_date'] = current_date - _threshold

        insert_dict['reported_time']      = reported_time
        insert_dict['comment']            = wit_rec.comment
        insert_dict['was_id']             = wit_rec.was_id
        insert_dict['was_instance_group'] = wit_rec.was_instance_group
        insert_dict['user_id']            = g.user.username if g.user else 'scheduler'

        print('mwm insert_dict : ', insert_dict)
        
        stmt = insert(MoWasStatusReport).values(insert_dict)
        r = db.session.execute(stmt)

    db.session.commit()

    return 1, 'OK'


def test2():
    table_dict = _get_table_dict()
    print("HHH2")

    table_name  = 'mw_was_instance'
    table_name2 = 'ut_tag'
    table = table_dict[table_name]
    table2 = table_dict[table_name2]
    #data = create_refresh_token(identity='<username>')
    #print("token : ",data)
    """
    a = table2(tag='TESTTEST1',user_id='test')
    db.session.add(a)
    db.session.flush()
    b = db.session.get(table2, {'tag':'TESTTEST1'})

    #a = table2(tag='TESTTEST1',user_id='test2')
    #db.session.merge(a)
    
    
    print('a:',a)
    print('b:',b)
    stmt = insert(table2).values({'tag':'TESTTEST2','user_id':'test'})
    do_update_stmt = stmt.on_conflict_do_update(
                index_elements=['tag'],
                set_={'label':'TEST'}
            ).returning(table2.ut_parent_tag)
    result = db.session.execute(do_update_stmt)

    print('result : ', result)
    for rec in result:
        print(rec)
    """
    
def test():
    table_dict = _get_table_dict()
    print("HHH")

    table_name = 'ut_tag'
    mn_column_name = 'ut_parent_tag'
    join_table_name = 'ut_tag'
    condition_column_name = 'tag'
    filter_list = ['정보분석']
    
    mn_column_name2 = 'ut_child_tag'
    join_table_name2 = 'ut_tag'
    condition_column_name2 = 'tag'
    filter_list2 = ['정보분석']
    """
    table_name = 'mw_was'
    mn_column_name = 'mw_was_instance'
    join_table_name = 'mw_was_instance'
    condition_column_name = 'was_id'
    """

    table = table_dict[table_name]
    join_table = table_dict[join_table_name]
    aliased_table = aliased(join_table)
    aliased_table2 = aliased(join_table)
    condition_column = getattr(aliased_table, condition_column_name)
    condition_column2 = getattr(aliased_table2, condition_column_name2)
    mn_column = getattr(table, mn_column_name)
    mn_column2 = getattr(table, mn_column_name2)

    print('mn type : ', type(table))
    print('mn type2 : ', type(mn_column.impl))
    second = next( ( tt for it, tt in inspect(table).relationships.items() if it == mn_column_name), None)
                    #print('HHH2 : ',second)
    print('mn type3 : ', second.target.name)
    print('mn type3 : ', second.direction.name)
    print('mn type3 : ', second.remote_side)
    print('mn type3 : ', second._reverse_property)
    print('mn type3 : ', second.primaryjoin)
    print('mn type3 : ', second.secondaryjoin)
    print('mn type3 : ', second.backref)
    print('mn type3 : ', second.secondary)

    """
    recs = db.session.query(table)\
        .join(aliased_table, mn_column).first()


    """
    sql = db.session.query(table)\
        .filter(table.tag=='담당자-업무-박훈')\
        .join(aliased_table, mn_column)\
        .join(aliased_table2, mn_column2)\
        .filter(func.string_to_array(condition_column,'-').op("@>")(filter_list))\
        .filter(func.string_to_array(condition_column2,'-').op("@>")(filter_list2))            

    print('sql : ', sql)

    recs = sql.all()
    print('recs : ', recs)


def get_cert_expiry_stat():
    now = datetime.now()
    d7 = now + timedelta(days=7)
    d30 = now + timedelta(days=30)
    
    from sqlalchemy import case, func
    from app.models.was import MwWebDomain, MwWebVhost, MwWeb
    from app.models.common import YnEnum, LocationEnum
    
    status_case = case(
        (MwWebDomain.notafter == None, '미확인'),
        (MwWebDomain.notafter <= now, '만료'),
        (MwWebDomain.notafter <= d7, '임박'),
        (MwWebDomain.notafter <= d30, '주의'),
        else_='정상'
    ).label('status')
    
    query = db.session.query(status_case, MwWeb.landscape, func.count().label('count'))\
        .select_from(MwWebDomain)\
        .join(MwWebVhost, MwWebDomain.mw_web_vhost_id == MwWebVhost.id)\
        .join(MwWeb, MwWebVhost.mw_web_id == MwWeb.id)\
        .filter(MwWeb.use_yn == YnEnum.YES, MwWebDomain.ssl_yn == YnEnum.YES)\
        .group_by(status_case, MwWeb.landscape)
    
    results = query.all()
    
    stats_dict = {}
    statuses = ['정상', '주의', '임박', '만료', '미확인']
    landscapes = ['PROD', 'TEST', 'DEV']
    
    for status in statuses:
        stats_dict[status] = {l: 0 for l in landscapes}
        stats_dict[status]['total'] = 0
    
    for r in results:
        status = r.status
        landscape = r.landscape.name if r.landscape else 'UNKNOWN'
        count = r.count
        
        if status not in stats_dict:
            stats_dict[status] = {l: 0 for l in landscapes}
            stats_dict[status]['total'] = 0
            
        if landscape in landscapes:
            stats_dict[status][landscape] = count
        stats_dict[status]['total'] += count

    final_results = []
    for status in statuses:
        row = stats_dict[status]
        row['status'] = status
        final_results.append(row)
        
    total_row = {l: sum(stats_dict[s][l] for s in statuses) for l in landscapes}
    total_row['total'] = sum(total_row[l] for l in landscapes)
    total_row['status'] = '전체'
    final_results.append(total_row)
    
    return final_results
def get_cert_expiry_stat_jeus():
    now = datetime.now()
    d7 = now + timedelta(days=7)
    d30 = now + timedelta(days=30)
    
    from sqlalchemy import case, func
    from app.models.was import MwWasHttpListener, MwEtcSslDomain, MwWasInstance, MwWas
    from app.models.common import YnEnum, LocationEnum
    
    # [Bug Fix] mw_etc_ssl_domain이 없는 경우(Outer Join 결과가 NULL인 경우) '미확인'으로 분류
    status_case = case(
        (MwEtcSslDomain.notafter == None, '미확인'),
        (MwEtcSslDomain.notafter <= now, '만료'),
        (MwEtcSslDomain.notafter <= d7, '임박'),
        (MwEtcSslDomain.notafter <= d30, '주의'),
        else_='정상'
    ).label('status')
    
    # [Target] MwWas.use_yn == YES & MwWasHttpListener.ssl_yn == YES
    query = db.session.query(status_case, MwWas.landscape, func.count().label('count'))\
        .select_from(MwWasHttpListener)\
        .join(MwWasInstance, MwWasHttpListener.mw_was_instance)\
        .join(MwWas, MwWasInstance.mw_was)\
        .outerjoin(MwWasHttpListener.mw_etc_ssl_domain)\
        .filter(MwWas.use_yn == YnEnum.YES, MwWasInstance.use_yn != YnEnum.NO, MwWasHttpListener.ssl_yn == YnEnum.YES)\
        .group_by(status_case, MwWas.landscape)
    
    results = query.all()
    
    stats_dict = {}
    statuses = ['정상', '주의', '임박', '만료', '미확인']
    landscapes = ['PROD', 'TEST', 'DEV']
    
    for status in statuses:
        stats_dict[status] = {l: 0 for l in landscapes}
        stats_dict[status]['total'] = 0
    
    for r in results:
        status = r.status
        landscape = r.landscape.name if r.landscape else 'UNKNOWN'
        count = r.count
        
        if status not in stats_dict:
            stats_dict[status] = {l: 0 for l in landscapes}
            stats_dict[status]['total'] = 0
            
        if landscape in landscapes:
            stats_dict[status][landscape] = count
        stats_dict[status]['total'] += count

    final_results = []
    for status in statuses:
        row = stats_dict[status]
        row['status'] = status
        final_results.append(row)
        
    total_row = {l: sum(stats_dict[s][l] for s in statuses) for l in landscapes}
    total_row['total'] = sum(total_row[l] for l in landscapes)
    total_row['status'] = '전체'
    final_results.append(total_row)
    
    return final_results

def get_ica_cert_expiry_stat():
    now = datetime.now()
    d7 = now + timedelta(days=7)
    d30 = now + timedelta(days=30)
    
    from sqlalchemy import case, func
    from app.models.was import MwWebDomain, MwWebVhost, MwWeb
    from app.models.common import YnEnum, LocationEnum
    
    status_case = case(
        (MwWebDomain.notafter_ca == None, '미확인'),
        (MwWebDomain.notafter_ca <= now, '만료'),
        (MwWebDomain.notafter_ca <= d7, '임박'),
        (MwWebDomain.notafter_ca <= d30, '주의'),
        else_='정상'
    ).label('status')
    
    query = db.session.query(status_case, MwWeb.landscape, func.count().label('count'))\
        .select_from(MwWebDomain)\
        .join(MwWebVhost, MwWebDomain.mw_web_vhost_id == MwWebVhost.id)\
        .join(MwWeb, MwWebVhost.mw_web_id == MwWeb.id)\
        .filter(MwWeb.use_yn == YnEnum.YES, MwWebDomain.ssl_yn == YnEnum.YES)\
        .group_by(status_case, MwWeb.landscape)
    
    results = query.all()
    
    stats_dict = {}
    statuses = ['정상', '주의', '임박', '만료', '미확인']
    landscapes = ['PROD', 'TEST', 'DEV']
    
    for status in statuses:
        stats_dict[status] = {l: 0 for l in landscapes}
        stats_dict[status]['total'] = 0
    
    for r in results:
        status = r.status
        landscape = r.landscape.name if r.landscape else 'UNKNOWN'
        count = r.count
        
        if status not in stats_dict:
            stats_dict[status] = {l: 0 for l in landscapes}
            stats_dict[status]['total'] = 0
            
        if landscape in landscapes:
            stats_dict[status][landscape] = count
        stats_dict[status]['total'] += count

    final_results = []
    for status in statuses:
        row = stats_dict[status]
        row['status'] = status
        final_results.append(row)
        
    total_row = {l: sum(stats_dict[s][l] for s in statuses) for l in landscapes}
    total_row['total'] = sum(total_row[l] for l in landscapes)
    total_row['status'] = '전체'
    final_results.append(total_row)
    
    return final_results

def get_ica_cert_expiry_stat_jeus():
    now = datetime.now()
    d7 = now + timedelta(days=7)
    d30 = now + timedelta(days=30)
    
    from sqlalchemy import case, func
    from app.models.was import MwWasHttpListener, MwEtcSslDomain, MwWasInstance, MwWas
    from app.models.common import YnEnum, LocationEnum
    
    # [Bug Fix] mw_etc_ssl_domain이 없는 경우(Outer Join 결과가 NULL인 경우) '미확인'으로 분류
    status_case = case(
        (MwEtcSslDomain.notafter_ca == None, '미확인'),
        (MwEtcSslDomain.notafter_ca <= now, '만료'),
        (MwEtcSslDomain.notafter_ca <= d7, '임박'),
        (MwEtcSslDomain.notafter_ca <= d30, '주의'),
        else_='정상'
    ).label('status')
    
    # [Target] MwWas.use_yn == YES & MwWasHttpListener.ssl_yn == YES
    query = db.session.query(status_case, MwWas.landscape, func.count().label('count'))\
        .select_from(MwWasHttpListener)\
        .join(MwWasInstance, MwWasHttpListener.mw_was_instance)\
        .join(MwWas, MwWasInstance.mw_was)\
        .outerjoin(MwWasHttpListener.mw_etc_ssl_domain)\
        .filter(MwWas.use_yn == YnEnum.YES, MwWasInstance.use_yn != YnEnum.NO, MwWasHttpListener.ssl_yn == YnEnum.YES)\
        .group_by(status_case, MwWas.landscape)
    
    results = query.all()
    
    stats_dict = {}
    statuses = ['정상', '주의', '임박', '만료', '미확인']
    landscapes = ['PROD', 'TEST', 'DEV']
    
    for status in statuses:
        stats_dict[status] = {l: 0 for l in landscapes}
        stats_dict[status]['total'] = 0
    
    for r in results:
        status = r.status
        landscape = r.landscape.name if r.landscape else 'UNKNOWN'
        count = r.count
        
        if status not in stats_dict:
            stats_dict[status] = {l: 0 for l in landscapes}
            stats_dict[status]['total'] = 0
            
        if landscape in landscapes:
            stats_dict[status][landscape] = count
        stats_dict[status]['total'] += count

    final_results = []
    for status in statuses:
        row = stats_dict[status]
        row['status'] = status
        final_results.append(row)
        
    total_row = {l: sum(stats_dict[s][l] for s in statuses) for l in landscapes}
    total_row['total'] = sum(total_row[l] for l in landscapes)
    total_row['status'] = '전체'
    final_results.append(total_row)
    
    return final_results
