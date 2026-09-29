from app.appctx import with_app_context
import logging
from app import appbuilder, db
from flask import g, current_app
from sqlalchemy.sql import select, update, func
from sqlalchemy import null, text, or_, and_, not_, case
from datetime import datetime, timedelta
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert, JSON
from app.models.common import get_uuid
from app.mqtt import get_publisher
from app.mqtt.status import mqtt_columns
from app.models.agent import AgCommandType, AgCommandMaster, AgCommandDetail\
    , AgResult, AgAgentGroup, AgAgent, AgFile, AgCommandHelper, AgAutorunResult
from app.models.monitor import MoWasInstanceStatus
from app.models.was import MwWas, MwWeb, MwEtcSslDomain
from .was import get_domain_id_as_pk
from .relationship import get_host_id
from .monitor import select_row
from sys import exc_info
import json
import re

# ---- Broadcast Callback Registry ----
broadcast_callback_registry = {}

def register_broadcast_callback(name):
    """Decorator to register a broadcast callback function."""
    def decorator(func):
        broadcast_callback_registry[name] = func
        return func
    return decorator

@register_broadcast_callback('get_all_agents')
def get_all_agents(landscape=None):
    """Approved 된 전체 agent 목록을 return (landscape 필터링 지원)"""
    query = db.session.query(AgAgent).filter(AgAgent.approved_yn == 'YES')
    if landscape:
        query = query.filter(AgAgent.landscape == landscape)
    agents = query.all()
    return agents if agents else []

def _get_filtered_was_agents(landscape=None, newgeneration_only=False):
    """WAS 에이전트 목록을 가져오는 공통 내부 함수"""
    was_agent_ids = db.session.query(MwWas.agent_id)\
        .filter(MwWas.use_yn == 'YES', MwWas.agent_id != None, MwWas.agent_id != '')
    
    if newgeneration_only:
        was_agent_ids = was_agent_ids.filter(MwWas.newgeneration_yn == 'YES')

    was_agent_ids = was_agent_ids.distinct().all()
    agent_id_list = [r[0] for r in was_agent_ids]
    
    if not agent_id_list:
        return []
    
    query = db.session.query(AgAgent).filter(AgAgent.approved_yn == 'YES', AgAgent.agent_id.in_(agent_id_list))
    if landscape:
        query = query.filter(AgAgent.landscape == landscape)
        
    agents = query.all()
    return agents if agents else []

@register_broadcast_callback('get_was_agents')
def get_was_agents(landscape=None):
    """WAS(use_yn=YES)를 등록한 전체 approved agent 목록을 return (landscape 필터링 지원)"""
    return _get_filtered_was_agents(landscape=landscape, newgeneration_only=False)

@register_broadcast_callback('get_was_agents_newgen')
def get_was_agents_newgen(landscape=None):
    """차세대 WAS(newgeneration_yn=YES)를 등록한 approved agent 목록을 return (landscape 필터링 지원)"""
    return _get_filtered_was_agents(landscape=landscape, newgeneration_only=True)

@register_broadcast_callback('get_web_agents')
def get_web_agents(landscape=None):
    """WEB(use_yn=YES)를 등록한 전체 approved agent 목록을 return (landscape 필터링 지원)"""
    web_agent_ids = db.session.query(MwWeb.agent_id)\
        .filter(MwWeb.use_yn == 'YES', MwWeb.agent_id != None, MwWeb.agent_id != '').distinct().all()
    agent_id_list = [r[0] for r in web_agent_ids]
    if not agent_id_list:
        return []
    
    query = db.session.query(AgAgent).filter(AgAgent.approved_yn == 'YES', AgAgent.agent_id.in_(agent_id_list))
    if landscape:
        query = query.filter(AgAgent.landscape == landscape)
        
    agents = query.all()
    return agents if agents else []

def get_error_results(create_on=None):

    recs = None

    if create_on:
        recs = db.session.query(AgResult)\
            .filter(AgResult.create_on>=create_on\
                ,AgResult.result_status.in_(['FAILED','ERROR']))\
                .order_by(AgResult.create_on.desc()).all()
    
    if recs:
        return recs
    else:
        return None 

def get_result(id):

    rec = db.session.query(AgResult).filter(AgResult.id==id).first()

    if rec:
        return rec
    else:
        return None 

def get_autorun_func(command_id, target_file_name):

    logging.debug(f"get_autorun_func is called. command_id : {command_id} target_file_name : {target_file_name}")

    if command_id:

        result = db.session.query(AgAutorunResult)\
            .filter(AgAutorunResult.command_id==command_id\
                ,AgAutorunResult.autorun_type=='COMMAND').first()

        if result:
            return result.autorun_func, result.autorun_param

    if target_file_name:

        # Exact match first
        result = db.session.query(AgAutorunResult)\
            .filter(AgAutorunResult.target_file_name==target_file_name\
                ,AgAutorunResult.autorun_type=='FILENAME').first()

        if result:
            return result.autorun_func, result.autorun_param

        # Regex match
        results = db.session.query(AgAutorunResult)\
            .filter(AgAutorunResult.autorun_type=='FILENAME').all()

        for res in results:
            if res.target_file_name:
                try: 
                    if re.search(res.target_file_name, target_file_name):
                        logging.debug(f"Regex match found: {res.target_file_name} matches {target_file_name}")
                        return res.autorun_func, res.autorun_param
                except re.error:
                    continue

    return None, None

def create_connect_ssl_for_httplistener(item):
    if getattr(item.ssl_yn, 'name', item.ssl_yn) != 'YES' or not item.domain_name:
        return False, f"SSL 대상이 아니거나 도메인명이 설정되지 않았습니다. ({item.domain_name}:{item.listen_port})"

    # Agent 찾기 로직
    host_id = item.mw_was_instance.host_id.lower()
    agents = get_agents()
    if not agents:
        return False, f"해당 서버({host_id})에 사용 가능한 Agent가 존재하지 않습니다."
    
    matched_agents = [ag for ag in agents if host_id in ag.agent_id.lower()]
    if not matched_agents:
        return False, f"해당 서버({host_id})에 사용 가능한 Agent가 존재하지 않습니다."

    jeus_agents = [ag for ag in matched_agents if "_jeus" in ag.agent_id.lower()]
    if jeus_agents:
        matched_agents = jeus_agents

    matched_agents.sort(key=lambda x: x.agent_id)
    selected_agent_id = matched_agents[0].agent_id

    # `mw_etc_ssl_domain` 정보 확인 / 생성
    etc_domain = db.session.query(MwEtcSslDomain).filter_by(
        host_id=host_id,
        domain_name=item.domain_name,
        port=str(item.listen_port)
    ).first()

    if not etc_domain:
        etc_domain = MwEtcSslDomain(
            host_id=host_id,
            domain_name=item.domain_name,
            port=str(item.listen_port),
            managed_yn='YES',
            use_yn='YES',
            agent_id=selected_agent_id
        )
        db.session.add(etc_domain)

    # Association
    if etc_domain not in item.mw_etc_ssl_domain:
        item.mw_etc_ssl_domain.append(etc_domain)

    insert_command_master('CALL.GET_SSL_CERTI',
                         [selected_agent_id],
                         etc_domain.domain_name + ':' + etc_domain.port)

    db.session.commit()

    return True, "Call Connect SSL 명령이 생성되었습니다."

def create_connect_ssl_real_ip(agent_id, domain_name, port, ip):
    # JSON 파라미터 구성
    param_dict = {
        "domain_name": domain_name,
        "port": str(port),
        "ip": ip
    }
    json_param = json.dumps(param_dict)

    insert_command_master('CALL.GET_SSL_CERTI',
                         [agent_id],
                         json_param)
    db.session.commit()
    return True, f"SSL 접수 완료 (Real IP: {ip})"

def create_connect_ssl_real_ip_for_httplistener(item):
    if getattr(item.ssl_yn, 'name', item.ssl_yn) != 'YES' or not item.domain_name:
        return False, f"SSL 대상이 아니거나 도메인명이 설정되지 않았습니다. ({item.domain_name}:{item.listen_port})"

    # Agent 찾기 로직
    host_id = item.mw_was_instance.host_id.lower()
    agents = get_agents()
    if not agents:
        return False, f"해당 서버({host_id})에 사용 가능한 Agent가 존재하지 않습니다."
    
    matched_agents = [ag for ag in agents if host_id in ag.agent_id.lower()]
    if not matched_agents:
        return False, f"해당 서버({host_id})에 사용 가능한 Agent가 존재하지 않습니다."
    
    jeus_agents = [ag for ag in matched_agents if "_jeus" in ag.agent_id.lower()]
    if jeus_agents:
        matched_agents = jeus_agents

    matched_agents.sort(key=lambda x: x.agent_id)
    selected_agent_id = matched_agents[0].agent_id

    # `mw_etc_ssl_domain` 정보 확인 / 생성 (기존 로직 유지)
    etc_domain = db.session.query(MwEtcSslDomain).filter_by(
        host_id=host_id,
        domain_name=item.domain_name,
        port=str(item.listen_port)
    ).first()

    if not etc_domain:
        etc_domain = MwEtcSslDomain(
            host_id=host_id,
            domain_name=item.domain_name,
            port=str(item.listen_port),
            managed_yn='YES',
            use_yn='YES',
            agent_id=selected_agent_id
        )
        db.session.add(etc_domain)

    # Association
    if etc_domain not in item.mw_etc_ssl_domain:
        item.mw_etc_ssl_domain.append(etc_domain)

    # Real IP 추출 (mw_was_instance -> mw_server -> ip_address)
    real_ip = ""
    if item.mw_was_instance and item.mw_was_instance.mw_server:
        real_ip = item.mw_was_instance.mw_server.ip_address

    return create_connect_ssl_real_ip(selected_agent_id, item.domain_name, item.listen_port, real_ip)

def get_agent(agent_id, isApproved=False):

    rec = db.session.query(AgAgent)\
        .filter(func.lower(AgAgent.agent_id)==func.lower(agent_id)).first()

    if rec:
        if not isApproved or rec.approved_yn.name=='YES':
            return rec
        else:
            return None     
    else:
        return None 

def get_agents():

    recs = db.session.query(AgAgent)\
        .filter(AgAgent.approved_yn=='YES').all()

    if recs:
        return recs
    else:
        return None 


def get_mqtt_agents(now=None):
    """MQTT 대상 Agent — 승인 ∧ OnLine ∧ 마지막 폴링에 헤더 있음 (HOWTO_019 §3)."""
    now = now or datetime.now()
    gap_online = now - timedelta(minutes=current_app.config.get('AGENT_OFFLINE_MINUTES', 5))
    query = db.session.query(AgAgent).filter(
        AgAgent.approved_yn == 'YES',
        AgAgent.last_checked_date > gap_online,
        AgAgent.mqtt_state.isnot(None))
    return query.all()


def get_agent_stat():
    now = datetime.now()
    offline_min = current_app.config.get('AGENT_OFFLINE_MINUTES', 5)
    gap_online = now - timedelta(minutes=offline_min)
    gap_long_term = now - timedelta(hours=24)

    results = db.session.query(
                AgAgent.landscape,
                func.sum(1).label('total'),
                func.sum(case([(AgAgent.last_checked_date > gap_online, 1)], else_=0)).label('online'),
                func.sum(case([(and_(AgAgent.last_checked_date <= gap_online, AgAgent.last_checked_date > gap_long_term), 1)], else_=0)).label('offline'),
                func.sum(case([(or_(AgAgent.last_checked_date <= gap_long_term, AgAgent.last_checked_date == None), 1)], else_=0)).label('long_term_unused')
            )\
            .filter(AgAgent.approved_yn == 'YES')\
            .group_by(AgAgent.landscape).all()
    
    offline_recs = db.session.query(AgAgent)\
            .filter(AgAgent.last_checked_date <= gap_online, AgAgent.approved_yn == 'YES')\
            .order_by(AgAgent.last_checked_date.desc())\
            .all()

    if results:
        return results, offline_recs
    else:
        return None, None

def get_next_repetition_seq(command_id, agent_id):

    result = db.session.query(func.max(AgCommandDetail.repetition_seq))\
                .filter(AgCommandDetail.agent_id==agent_id, AgCommandDetail.command_id==command_id).first()

    if result[0] is None:
        rtn = 1
    else:
        rtn = result[0] + 1
    
    return rtn

def finish_commands(command_ids):

    stmt = update(AgCommandMaster)\
            .where(AgCommandMaster.command_id.in_(command_ids)).values(publish_yn='YES')
    db.session.execute(stmt)

def cancel_commands(command_ids):

    stmt = update(AgCommandMaster)\
            .where(AgCommandMaster.command_id.in_(command_ids)).values(finished_yn='YES')
    db.session.execute(stmt)

def get_command_helper(mapping_key, target_file_name, agent_id):

    commandHelper_recs = db.session.query(AgCommandHelper)\
                    .filter(AgCommandHelper.mapping_key==mapping_key\
                        ,AgCommandHelper.target_file_name==target_file_name\
                        ,AgCommandHelper.agent_id==agent_id).all()

    if commandHelper_recs:        
        return [r.string_to_replace for r in commandHelper_recs]
    else:
        return None

def finish_commands_by_scheduler():

    stmt = update(AgCommandMaster).where(\
                (AgCommandMaster.finished_yn=='NO') \
                & (\
                ((AgCommandMaster.periodic_type == 'IMMEDIATE') & (AgCommandMaster.publish_yn == 'YES'))\
                |((AgCommandMaster.periodic_type == 'ONETIME') & (AgCommandMaster.time_to_exe < datetime.now()))\
                |((AgCommandMaster.periodic_type == 'PERIODIC') & (AgCommandMaster.time_to_stop < datetime.now()))\
                )).values(finished_yn='YES')

    db.session.execute(stmt)

    db.session.commit()

# ---- MQTT 실시간 발송 ----

def _queue_mqtt_publish(item):
    """commit 이후에 발행할 Command 를 세션에 적재한다.

    발행을 commit 전에 하면 Agent 가 명령을 받아 결과를 먼저 POST 할 수 있고,
    그 시점에는 AgCommandDetail 이 아직 없어 결과가 유실된다.
    """
    db.session.info.setdefault('mqtt_pending', []).append(item)


def flush_mqtt_pending(session):
    """commit 직후 호출되어 적재된 Command 를 실제로 발행한다.

    발행에 성공한 건만 command_status 를 MQTT 로 올린다. 실패한 건은 CREATE 로
    남으므로 기존 REST 폴링이 그대로 가져간다(명령 유실 없음).
    """
    pending = session.info.pop('mqtt_pending', None)

    if not pending:
        return

    publisher = get_publisher()

    if not publisher:
        logging.warning('MQTT publisher 없음 - Command %d건을 REST 폴링으로 fallback', len(pending))
        return

    delivered = []

    for item in pending:
        rtn = publisher.send_message(item['topic'], item['message'], key=item['key'])
        if rtn > 0:
            delivered.append(item)

    logging.info('MQTT 발송: 성공 %d건 / 전체 %d건 (실패분은 REST 폴링으로 fallback)',
                 len(delivered), len(pending))

    if not delivered:
        return

    # 세션이 아니라 별도 커넥션으로 갱신한다. after_commit 안에서 db.session 을
    # 다시 commit 하면 이 핸들러가 재진입한다.
    try:
        with db.engine.begin() as conn:
            for item in delivered:
                conn.execute(
                    update(AgCommandDetail)
                    .where(AgCommandDetail.command_id == item['command_id'],
                           AgCommandDetail.agent_id == item['agent_id'],
                           AgCommandDetail.repetition_seq == item['repetition_seq'],
                           AgCommandDetail.command_status == 'CREATE')
                    .values(command_status='MQTT')
                )
    except Exception:
        # 갱신 실패 시 status 는 CREATE 로 남는다. Agent 가 push 로 이미 받았고
        # 폴링으로 한 번 더 받을 수 있으므로, Agent 측 멱등 처리가 필요하다.
        logging.exception('MQTT 발송 후 command_status 갱신 실패 (status 는 CREATE 유지)')


def create_command_detail(command):

    logging.debug(f'mwm create_command_detail {command}')

    if isinstance(command, str):

        command_rec = db.session.query(AgCommandMaster)\
                    .filter(AgCommandMaster.command_id==command).first()
    else:
  
        command_rec = command
        
    command_type_rec = db.session.query(AgCommandType)\
                .filter(AgCommandType.command_type_id==command_rec.command_type_id).first()

    target_file_path = command_type_rec.target_file_path
    target_file_name = command_type_rec.target_file_name

    rexp = re.compile(r'.*?(<<<)(.*?)(>>>)')
    m = rexp.match(target_file_path)
    befor_text = ''

    if m:
        befor_text = m[1]+m[2]+m[3]
            
    # Append all Agents and Agent groups of a command master into a list
    ags = []
    
    if command_rec.broadcast_callback:
        # Parse broadcast_callback name and parameters: e.g. "func_name(param1, param2)"
        cb_str = command_rec.broadcast_callback.strip()
        cb_name = cb_str
        cb_params_list = []
        
        if '(' in cb_str and cb_str.endswith(')'):
            cb_name = cb_str[:cb_str.find('(')].strip()
            params_raw = cb_str[cb_str.find('(')+1:-1].strip()
            if params_raw:
                cb_params_list = [p.strip() for p in params_raw.split(',')]

        # Call the registered broadcast callback function to get agents
        callback_func = broadcast_callback_registry.get(cb_name)
        if callback_func:
            if cb_params_list:
                # 지금은 첫번째 파라미터를 landscape로 넘김 (나중에 함수별로 상세화 가능)
                ags = callback_func(landscape=cb_params_list[0])
            else:
                ags = callback_func()
        else:
            logging.error(f"Broadcast callback '{cb_name}' not found in registry.")
            return 0, f"Broadcast callback '{cb_name}' not found."

    for agg in command_rec.ag_agent_group:
        for ag in agg.ag_agent:
            ags.append(ag)
    ags += command_rec.ag_agent

    # Remove duplicated agents by set func
    for ag in set(ags):

        # 아직 수행되지 않은 명령이 있으면 건너뛴다.
        # CREATE(폴링 대기) 외에 MQTT(전달 완료, 결과 대기)도 미수행 상태다.
        commandDetail_rec = db.session.query(AgCommandDetail)\
                    .filter(AgCommandDetail.command_id==command_rec.command_id\
                        , AgCommandDetail.agent_id==ag.agent_id\
                        , AgCommandDetail.command_status.in_(['CREATE', 'MQTT'])).first()

        if commandDetail_rec:
            continue

        target_file_paths = []
        if befor_text:

            after_texts = get_command_helper(m[2], target_file_name, ag.agent_id)

            if after_texts:
                for after_text in after_texts:
                    target_file_paths.append(target_file_path.replace(befor_text, after_text))
                #print("mwm 4 target_file_path : ", target_file_paths)
            else:
                logging.error("StringToReplace not exists : agent_id[%s] befor_text[%s] target_file_name[%s]"\
                        ,ag.agent_id, befor_text, target_file_name)
                continue
        else:
            target_file_paths.append(target_file_path)

        repetition_seq = get_next_repetition_seq(command_rec.command_id, ag.agent_id)
        logging.info('AgCommandDetail KEY SET : [%s][%s][%d]',command_rec.command_id,ag.agent_id,repetition_seq)

        for i, t in enumerate(target_file_paths):

            # REST 폴링 (기본)
            command_status = 'CREATE'

            sender = command_rec.command_sender.name
            mqtt_publisher = get_publisher() if sender == 'MQTT' else None

            # message 는 MQTT 에만 필요하다. get_result_hash 가 DB 조회라
            # broadcast 시 Agent 수만큼 쿼리가 늘어나므로 분기 안에서만 만든다.
            if mqtt_publisher:

                key = command_rec.command_id + '_' + str(repetition_seq + i)
                message = dict(
                    command_id        = command_rec.command_id,
                    repetition_seq    = repetition_seq + i,
                    command_class     = command_type_rec.command_class.name,
                    target_file_path  = target_file_paths[i],
                    target_file_name  = target_file_name,
                    additional_params = command_rec.additional_params,
                    result_receiver   = command_rec.result_receiver.name,
                    target_object     = command_rec.target_object,
                    result_hash       = get_result_hash(ag.agent_id, command_rec.command_id, repetition_seq + i)
                )

                # MQTT : 적재만 하고 실제 발행은 commit 이후에 한다.
                #        status 는 CREATE 로 두고, 발행 성공 시 MQTT 로 올린다.

                # Agent 는 MQTT 수신 시 cmdId 로 중복 실행을 걸러낸다.
                # (같은 cmdId 를 다시 받으면 무시) REST 폴링 payload 에는 없는
                # 필드이므로 MQTT 경로에서만 추가한다.
                mqtt_message = dict(message, cmdId=key)

                # Agent(Java) 는 이 필드들에 null 체크 없이 .length() 를 호출한다.
                # DB NULL 이 JSON null 로 나가면 NPE 로 명령이 조용히 버려지므로
                # (예외를 내부에서 삼켜 결과 보고조차 없다) 빈 문자열로 맞춘다.
                for _k in ('additional_params', 'target_object'):
                    if mqtt_message.get(_k) is None:
                        mqtt_message[_k] = ''

                _queue_mqtt_publish(dict(
                    topic          = current_app.config['MQTT_CMD_TOPIC'].format(agent_id=ag.agent_id),
                    key            = key,
                    message        = mqtt_message,
                    command_id     = command_rec.command_id,
                    agent_id       = ag.agent_id,
                    repetition_seq = repetition_seq + i,
                ))

            insert_dict = dict(
                    command_id        = command_rec.command_id,
                    agent_id          = ag.agent_id,
                    repetition_seq    = repetition_seq + i,
                    command_type_id   = command_rec.command_type_id,
                    command_class     = command_type_rec.command_class.name,
                    target_file_path  = target_file_paths[i],
                    target_file_name  = target_file_name,
                    additional_params = command_rec.additional_params,
                    command_status    = command_status,
                    user_id           = 'scheduler'
                )
            
            stmt = insert(AgCommandDetail).values(insert_dict)
            r = db.session.execute(stmt)
        
    stmt = update(AgCommandMaster).where(AgCommandMaster.id==command_rec.id).values(publish_yn='YES')
    db.session.execute(stmt)

    return 1, 'OK'

@with_app_context
def create_command_detail_by_sch(command_id):

    logging.debug('mwm create_command_detail_by_sch [%s]', command_id)

    try:

        create_command_detail(command_id)

        db.session.commit()

    except Exception as e:
        excType, excValue, traceback = exc_info()
        logging.error('An Error Occured : %s %s %s', excType, excValue, traceback)
        db.session.rollback()

    return 1, 'OK'

def send_command_immediately(agent_id, command_type_id):

    return 0, ''

def get_or_insert_command_type(command_class, target_file_path='', target_file_name=''):

    return 0, ''

def insert_command_master(command_type_id, agent_ids, additional_param='', add_CID=False, out_CID=False):

    command_id = get_uuid()
    insert_dict = dict(
                      command_id       = command_id
                    , command_type_id  = command_type_id
                    , periodic_type    = 'IMMEDIATE' 
                    , user_id          = 'scheduler'   
                    , publish_yn       = 'YES'                     
                    )

    param = ''

    if additional_param:
        param = additional_param

    if add_CID:
        param += ' ' + command_id
    
    if out_CID:
        param += ' > ' + command_type_id + '.out.' + command_id

    if param:
        insert_dict.update({'additional_params':param})

    stmt = insert(AgCommandMaster).values(insert_dict)
    db.session.execute(stmt)

    commandMaster_rec = db.session.query(AgCommandMaster)\
                    .filter(AgCommandMaster.command_id==command_id).first()

    agent_recs = db.session.query(AgAgent)\
                    .filter(AgAgent.agent_id.in_(agent_ids)).all()

    commandMaster_rec.ag_agent = agent_recs

    create_command_detail(command_id)

    return 1, ''

def get_closeto_token_expiry_bysch(days):

    subquery = db.session.query(AgCommandDetail.agent_id)\
                    .filter(AgCommandDetail.command_class=='GetRefreshToken',AgCommandDetail.command_status=='CREATE').subquery()

    agent_recs = db.session.query(AgAgent)\
                    .filter(or_(AgAgent.token_expiration_date<=datetime.now()+timedelta(days=days)\
                                ,AgAgent.token_expiration_date==None)\
                            ,~AgAgent.agent_id.in_(subquery)).all()

    if not agent_recs:
        return 0, 'No data is found'

    command_type_rec = db.session.query(AgCommandType)\
                        .filter(AgCommandType.command_class=='GetRefreshToken').first()

    if not command_type_rec:

        command_type_id = 'GetRefreshToken'
        insert_dict = dict(
                      command_type_id   = command_type_id
                    , command_type_name = 'Update Refresh Token'
                    , command_class     = 'GetRefreshToken'
                    , user_id           = 'scheduler'                    
                    )
        stmt = insert(AgCommandType).values(insert_dict)
        db.session.execute(stmt)
    
    else:
        command_type_id = command_type_rec.command_type_id

    command_id = get_uuid()
    insert_dict = dict(
                      command_id       = command_id
                    , command_type_id  = command_type_id
                    , periodic_type    = 'IMMEDIATE' 
                    , user_id          = 'scheduler'   
                    , publish_yn       = 'YES'                     
                    )
    stmt = insert(AgCommandMaster).values(insert_dict)
    db.session.execute(stmt)
    
    ag_command_master_rec = db.session.query(AgCommandMaster)\
                    .filter(AgCommandMaster.command_id==command_id).first()

    logging.debug(f'ag_command_master_rec :{ag_command_master_rec}')

    ag_command_master_rec.ag_agent = agent_recs

    for ag in agent_recs:

        insert_dict = dict(
                    command_id        = command_id,
                    agent_id          = ag.agent_id,
                    repetition_seq    = 1,
                    command_type_id   = command_type_id,
                    command_class     = 'GetRefreshToken',
                    command_status    = 'CREATE',
                    user_id           = 'scheduler'
                    )
        
        stmt = insert(AgCommandDetail).values(insert_dict)
        r = db.session.execute(stmt)

    db.session.commit()

    return 1, 'OK'

def check_agent_approved(agent_id):

    agent_rec = db.session.query(AgAgent)\
                    .filter(AgAgent.agent_id==agent_id).first()

    if not agent_rec:
        return -1, 'Agent Not Exists'
    elif agent_rec.approved_yn.value == 'NO':
        return -2, 'Not Approved Yet'
    else:
        return 1, 'OK'

def get_latest_file(agent_type, file_name):

    q1 = db.session.query(func.max(AgFile.file_version))\
                .filter(AgFile.agent_type==agent_type, AgFile.file_name==file_name).scalar_subquery()
    result = db.session.query(AgFile).filter(AgFile.agent_type==agent_type, AgFile.file_name==file_name, AgFile.file_version==q1).first()

    return result.file if result else '' 

def check_agent_updated(agent_version):

    return 1, 'OK'

def update_result_status(id, status, message):

    db.session.query(AgResult).filter(AgResult.id==id)\
               .update({AgResult.result_status:status\
                        ,AgResult.complited_date:datetime.now()\
                        ,AgResult.result_message:message})

    #db.session.commit()

def update_expiration(agent_id, expiration_date, refresh_token):

    rtn = db.session.query(AgAgent)\
                    .filter(AgAgent.agent_id==agent_id)\
                    .update({AgAgent.token_expiration_date:expiration_date\
                            ,AgAgent.refresh_token:refresh_token})

    if rtn < 1:
        return -1, 'Agent [' + agent_id + '] : not exists'
        
    db.session.commit()

    return 1, 'OK'

def get_result_hash(agent_id, command_id, repetition_seq):

    subquery = db.session.query(func.max(AgResult.repetition_seq))\
                    .filter(AgResult.command_id==command_id\
                            , AgResult.agent_id==agent_id\
                            , AgResult.repetition_seq < repetition_seq\
                            , AgResult.result_hash!=None).subquery()

    query = db.session.query(AgResult.result_hash)\
                    .filter(AgResult.command_id==command_id\
                            , AgResult.agent_id==agent_id\
                            , AgResult.repetition_seq.in_(subquery))

    result_hash_rec = db.session.query(AgResult.result_hash)\
                    .filter(AgResult.command_id==command_id\
                            , AgResult.agent_id==agent_id\
                            , AgResult.repetition_seq.in_(subquery)).first()

    if result_hash_rec:
        result_hash = result_hash_rec[0]
    else:
        result_hash = ""

    return result_hash

def send_commands(agent_id, agent_version='', agent_type='', update_mqtt=False, mqtt_header=None):
    """보낼 명령을 꺼내고 Agent 의 최종 확인 시각을 갱신한다.

    update_mqtt=True 면 X-Mqtt-Status 헤더(mqtt_header)로 MQTT 컬럼을 같은 UPDATE 에서 갱신한다.
    헤더가 없으면 비운다 → MQTT 모수에서 빠진다. BOOT 는 False 로 부른다 (HOWTO_019 §4.2).
    """

    logging.debug(f"send_commands is called. agent_id : {agent_id} {agent_version} {agent_type}")

    data = []
    command_detail_recs = db.session.query(AgCommandDetail)\
                    .filter(AgCommandDetail.agent_id==agent_id, AgCommandDetail.command_status=='CREATE').all()

    for r in command_detail_recs:

        result_hash = get_result_hash(agent_id, r.command_id, r.repetition_seq)

        data.append(dict(
                    command_id        = r.command_id,
                    repetition_seq    = r.repetition_seq,
                    command_class     = r.command_class.name,
                    target_file_path  = r.target_file_path,
                    target_file_name  = r.target_file_name,
                    additional_params = r.additional_params,
                    result_receiver   = r.ag_command_master.result_receiver.name,
                    target_object     = r.ag_command_master.target_object,
                    result_hash       = result_hash
                ))
        
    logging.debug(f"send_commands -> data : {data}")

    db.session.query(AgCommandDetail)\
                    .filter(AgCommandDetail.agent_id==agent_id, AgCommandDetail.command_status=='CREATE')\
                    .update({AgCommandDetail.command_status:'SENDED'})

    update_dict = {AgAgent.last_checked_date:datetime.now()}
    if agent_version:
        update_dict.update({AgAgent.agent_version:agent_version})
    if agent_type:
        update_dict.update({AgAgent.agent_type:agent_type})
    if update_mqtt:
        update_dict.update({getattr(AgAgent, k): v
                            for k, v in mqtt_columns(mqtt_header, datetime.now()).items()})

    db.session.query(AgAgent)\
                    .filter(AgAgent.agent_id==agent_id)\
                    .update(update_dict)

    return 1, data

def add_agent(agent_id, host_id, agent_type, ip_address, installation_path=''):

    insert_dict = dict(
                    agent_id   = agent_id,
                    agent_type = agent_type,
                    host_id    = host_id,
                    ip_address = ip_address,
                    installation_path   = installation_path
                    )
    stmt = insert(AgAgent).values(insert_dict)

    db.session.execute(stmt)
    db.session.commit()

    return 1, 'OK'

"""
def __getTag(agent_id, agent_type, host_id):

    user_id = agent_id[agent_id.find('_')+1:agent_id.rfind('_')]
    tag = 'MWAGENT-' + agent_type + '-' + host_id + '-' + user_id
    tag_id = insertResourceTag('ag_agent', tag)
    return tag_id
"""
def add_result(data):

    result_status = 'FAILED' if data.get('is_normal') and data['is_normal'] == 'false' else 'CREATE'
    command_status = 'FAILED' if data.get('is_normal') and data['is_normal'] == 'false' else 'COMPLITED'

    key_value1  = data['key_value1'] if data.get('key_value1') else 'NO VALUE'
    key_value2  = data['key_value2'] if data.get('key_value2') else 'NO VALUE'

    """
    if key_value1 == 'get_server_stat' and result_status == 'CREATE' :
        rtn, msg = updateWasStatus(key_value2, data['result_text'], data['host_id'])
        if rtn > 0:
            result_status = 'COMPLITED'
        else:
            result_status = 'ERROR'
            logging.error("updateWasStatus error : [%s]",msg)
    """
    if data['result_text'] == 'NO CHANGE':
        result_status = 'NOCHANGE'

    #print('data[is_normal] :',data['is_normal'],'rs :',result_status, ' cs :', command_status)
    insert_dict = dict(
                    command_id  = data['command_id'],
                    agent_id    = data['agent_id'],
                    repetition_seq  = data['repetition_seq'],
                    host_id     = data['host_id'],
                    key_value1  = key_value1,
                    key_value2  = key_value2,
                    result_status = result_status,
                    result_hash = data['result_hash'] if data.get('result_hash') else None,
                    result_text = data['result_text']
                    )
    stmt = insert(AgResult).values(insert_dict).returning(AgResult.id)

    result = db.session.execute(stmt)

    result_id = 0
    for r in result:
        result_id = r.id
        break

    db.session.query(AgCommandDetail)\
                    .filter(AgCommandDetail.agent_id==data['agent_id']\
                    , AgCommandDetail.repetition_seq==data['repetition_seq']\
                    , AgCommandDetail.command_id==data['command_id'])\
                    .update({AgCommandDetail.command_status:command_status\
                    ,AgCommandDetail.result_received_date:datetime.now()})

    return 1 if result_status == 'CREATE' else 0, result_id

def get_command_master(command_id):

    command_rec = db.session.query(AgCommandMaster)\
                    .filter(AgCommandMaster.command_id==command_id).first()

    return command_rec

def get_commands():

    command_recs = db.session.query(AgCommandMaster)\
                    .filter(AgCommandMaster.cancel_yn=='NO'
                            , AgCommandMaster.finished_yn=='NO'
                            , AgCommandMaster.periodic_type.in_(['ONETIME','PERIODIC'])
                            , or_(AgCommandMaster.periodic_type=='ONETIME', AgCommandMaster.interval_type!=None)
                            , or_(AgCommandMaster.time_to_stop > datetime.now(), AgCommandMaster.time_to_stop==None)
                            , or_(AgCommandMaster.periodic_type=='PERIODIC',AgCommandMaster.time_to_exe > datetime.now(), AgCommandMaster.time_to_exe==None)
                            ).all()

    return command_recs

def get_last_run_datetime(command_id):

    result = db.session.query(func.max(AgCommandDetail.create_on))\
                .filter(AgCommandDetail.command_id==command_id).first()

    return result[0]

def update_was_status(key_value2, result_text, host_id_of_agent):

    logging.info("mwm r_rec.key_value2 : [%s]",key_value2)
    logging.info("mwm r_rec.result_text : [%s]",result_text)

    try:
        param_rec  = json.loads(key_value2)
        result_rec = json.loads(result_text)

        # KAFKA STREAM 생성 시 JSON in JSON 인식이 안되는 문제 때문에 이원화됨
        if isinstance(result_rec, dict):
            results = result_rec['servers']
        elif isinstance(result_rec, list):
            results = result_rec

    except json.decoder.JSONDecodeError as e:
        #result_status_list.append('ERROR')
        return -1, 'JSON Parsing error'

    landscape = ''
    update_on = datetime.now()

    real_domain_id = param_rec['jmx_domain']
    url = param_rec['jmx_url']
        
    if url.startswith(('127.0.0.1','localhost')):
        host_id = host_id_of_agent
    else:
        ip_address = url[:url.find(':')]
        host_id = get_host_id(ip_address)

        if host_id == ip_address:
            logging.error("IP Address dosen't exist in Servers : [%s]",host_id)
        
    domain_id = get_domain_id_as_pk(host_id, real_domain_id)

    #print('host_id, real_domain_id, domain_id of get_domain_id_as_pk: ',host_id, real_domain_id, domain_id)
    was_rec, _ = select_row('mw_was', {'was_id':domain_id})

    if was_rec and was_rec.landscape:
        landscape = was_rec.landscape.name
    else:
        return -1, 'Landscape is not defined'

    for stat_r in results:

        # KAFKA STREAM 생성 시 JSON Array 인식이 안되는 문제 때문에 이원화됨
        if isinstance(stat_r, dict):
            d_server_name = stat_r['server_name']
            d_status      = stat_r['status']
        else:
            [d_server_name, d_status] = stat_r.split('__')

        if d_status in ['RUNNING','STANDBY','SHUTDOWN','FAILED']:
            was_instance_status = d_status
        elif d_status == 'READY':
            #status:1 RUNNING, 0: FAIL
            AppNotDeployed = next((True for app in stat_r['application_status']\
                                     if app['status']!='1'), False)
            if AppNotDeployed:
                was_instance_status = 'STANDBY'
            else:
                was_instance_status = 'RUNNING'
        else:
            was_instance_status = 'FAILED'

        update_dict = dict(
            host_id             = was_rec.located_host_id,
            was_instance_status = was_instance_status,
            landscape           = landscape,
            update_on           = update_on
        )
            
        insert_dict = update_dict.copy()
        insert_dict.update(
            was_id          = domain_id,
            was_instance_id = d_server_name,
            user_id         = 'scheduler'
        )

        stmt = insert(MoWasInstanceStatus).values(insert_dict)    
        do_update_stmt = stmt.on_conflict_do_update(
            index_elements=['was_id', 'was_instance_id'],
            set_=update_dict
        )
        db.session.execute(do_update_stmt)

    return 1, 'OK'

