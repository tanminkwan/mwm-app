import logging
import json
import re
import sys
from io import BytesIO
from datetime import datetime, timedelta
from flask import g, request, jsonify, send_file, current_app
from flask_appbuilder.api import BaseApi, expose, protect
from flask_jwt_extended import create_refresh_token

from app import appbuilder, db
from app.sqls.agent_dml import AutorunResult
from app.file_manager.s3.filemanager import S3FileManager
from app.sqls.agent import (
    check_agent_approved,
    check_agent_updated,
    send_commands,
    add_result,
    add_agent,
    get_latest_file,
    update_expiration
)
from app.models.agent import AgCommandMaster, AgAgent, AgAgentGroup, AgCommandType\
    , AgCommandDetail, AgResult
from app.models.common import PeriodicTypeEnum, YnEnum, TargetToSendEnum, get_uuid
from app.models.was import MwWasInstance
from app.models.knowledge import UtTag
from app.log_safe import log_safe

class CommandApi(BaseApi):

    resource_name = 'command'

    @expose('/<agent_id>/<agent_version>', methods=['GET'])
    @protect()
    def command(self, agent_id, agent_version):

        logging.debug(f"command is called. agent_id / agent_version : {agent_id} / {agent_version}")

        rtn , msg = check_agent_approved(agent_id)
        if rtn < 0:
            return jsonify({'return_code':rtn, 'message':msg}), 201

        rtn , msg = check_agent_updated(agent_version)
        if rtn < 0:
            return jsonify({'return_code':rtn, 'message':msg}), 201

        rtn , data = send_commands(agent_id, agent_version)

        db.session.commit()

        return jsonify({'return_code':rtn, 'message':'OK', 'data':data}), 200

    @expose('/<agent_id>/<agent_version>/<agent_type>', methods=['GET'])
    @protect()
    def command_v2(self, agent_id, agent_version, agent_type):
        
        rtn , msg = check_agent_approved(agent_id)
        if rtn < 0:
            return jsonify({'return_code':rtn, 'message':msg}), 201

        rtn , msg = check_agent_updated(agent_version)
        if rtn < 0:
            return jsonify({'return_code':rtn, 'message':msg}), 201

        rtn , data = send_commands(agent_id, agent_version, agent_type)

        db.session.commit()

        return jsonify({'return_code':rtn, 'message':'OK', 'data':data}), 200

    @expose('/<agent_id>/<agent_version>/<agent_type>/<agent_status>', methods=['GET'])
    @protect()
    def command_v4(self, agent_id, agent_version, agent_type, agent_status):

        logging.debug(f"command_v4 is called. agent_id : {agent_id}")

        rtn , msg = check_agent_approved(agent_id)
        if rtn < 0:
            return jsonify({'return_code':rtn, 'message':msg}), 201

        rtn , msg = check_agent_updated(agent_version)
        if rtn < 0:
            return jsonify({'return_code':rtn, 'message':msg}), 201

        rtn , data = send_commands(agent_id, agent_version, agent_type)

        #최초 접속인 경우
        if agent_status == 'BOOT':

            boot_info = dict(command_class = 'BOOT')

            # MQTT 접속 정보. Agent 가 브로커 주소를 하드코딩하지 않게 한다.
            # 비밀번호는 내려주지 않는다 - Agent 계정은 브로커 passwd/acl 에
            # 별도 프로비저닝되어야 하며, username 은 agent_id 와 같다.
            if current_app.config.get('MQTT_ENABLED'):
                boot_info.update(
                        mqtt_enabled         = True,
                        mqtt_broker_host     = current_app.config['MQTT_BROKER_HOST'],
                        mqtt_broker_port     = current_app.config['MQTT_BROKER_PORT'],
                        mqtt_username        = agent_id,
                        mqtt_topic           = current_app.config['MQTT_CMD_TOPIC'].format(agent_id=agent_id),
                        mqtt_broadcast_topic = current_app.config['MQTT_BROADCAST_TOPIC'],
                        mqtt_qos             = current_app.config['MQTT_QOS'],
                    )
            else:
                boot_info.update(mqtt_enabled=False)

            data.append(boot_info)

        db.session.commit()

        logging.debug(f"command_v4 returned data : {data}")

        return jsonify({'return_code':rtn, 'message':'OK', 'data':data}), 200

    @expose('/<agent_id>', methods=['GET'])
    @protect()
    def command_v3(self, agent_id):

        logging.debug(f"command_v3 is called. agent_id : {agent_id}")

        rtn , msg = check_agent_approved(agent_id)
        if rtn < 0:
            return jsonify({'return_code':rtn, 'message':msg}), 201

        rtn , data = send_commands(agent_id)

        db.session.commit()

        return jsonify({'return_code':rtn, 'message':'OK', 'data':data}), 200

    @expose('/result', methods=['POST'])
    @protect()
    def agent(self, **kwargs):

        data = json.loads(request.data)

        if not data.get('agent_id'):
            return jsonify({'return_code':-2,'message':'agent_id does not exist'}), 201
        elif not data.get('command_id'):
            return jsonify({'return_code':-2,'message':'command_id does not exist'}), 201
        elif not data.get('repetition_seq'):
            return jsonify({'return_code':-2,'message':'command_id does not exist'}), 201
        elif not data.get('host_id'):
            return jsonify({'return_code':-2,'message':'host_id does not exist'}), 201
        elif data.get('result_text') == None :
            return jsonify({'return_code':-2,'message':'result_text does not exist'}), 201

        rtn , result_id = add_result(data)

        db.session.commit()

        #Result 상태가 'CREATE' 인 경우 Auto Run Result 수행
        if rtn > 0:

            msg = ''
            try:
                ar = AutorunResult(result_id=result_id)
                rtn2, msg = ar.call_autorun_func()
            except Exception as e:
                excType, excValue, traceback = sys.exc_info()
                logging.error(f'call_autorun_func Error : 1{excType} 2{excValue} 3{traceback}')
                rtn2 = -1

            if rtn2 > 0:
                db.session.commit()
            else:
                command_id = data.get('command_id')
                logging.error(f'call_autorun_func [command_id:{log_safe(command_id)}][msg:{log_safe(msg)}]')
                db.session.rollback()

        return jsonify({'return_code':1, 'message':'OK'}), 200

class AgentApi(BaseApi):

    resource_name = 'agent'

    @expose('/boot', methods=['POST'])
    @protect()
    def agentBoot(self, **kwargs):
        return jsonify({'return_code':1, 'message':'OK'}), 200

    @expose('/agent', methods=['POST'])
    @protect()
    def agent(self, **kwargs):

        data = json.loads(request.data)

        ip_address = request.remote_addr

        if not data.get('agent_id'):
            return jsonify({'return_code':-2,'message':'agent_id does not exist'}), 401
        elif not data.get('host_id'):
            return jsonify({'return_code':-2,'message':'host_id does not exist'}), 401
        elif not data.get('agent_type'):
            return jsonify({'return_code':-2,'message':'agent_type does not exist'}), 401

        agent_id   = data['agent_id']
        host_id    = data['host_id']
        agent_type = data['agent_type']
        installation_path  = data['installation_path']

        rtn , msg = add_agent(agent_id, host_id, agent_type, ip_address, installation_path=installation_path)
        
        return jsonify({'return_code':1, 'message':'OK'}), 200

    @expose('/download/<agent_type>/<file_name>', methods=['GET'])
    @protect()
    def download_file(self, agent_type, file_name):

        #get file name from db
        realname = get_latest_file(agent_type, file_name)

        if not realname:
            return jsonify({'return_code':-1, 'message':'File not found'}), 404

        fm = S3FileManager()
        file_body = fm.get_file(realname)

        return send_file(BytesIO(file_body), download_name=file_name, as_attachment=True)
        
    @expose('/getRefreshToken/<agent_id>', methods=['GET'])
    @protect()
    def getRefreshToken(self, agent_id):

        refresh_token = create_refresh_token(g.user.id , expires_delta=timedelta(days=15))
        expiration_date = datetime.now() + timedelta(days=15)
        rtn , msg = update_expiration(agent_id, expiration_date, refresh_token)
        if rtn < 0:
            return jsonify({'return_code':rtn, 'message':msg, 'refresh_token':''}), 401
        return jsonify({'return_code':rtn, 'message':'OK', 'refresh_token':refresh_token}), 200

appbuilder.add_api(CommandApi)
appbuilder.add_api(AgentApi)

# JSON 규격에서 백슬래시 뒤에 올 수 있는 문자는 " \\ / b f n r t u 뿐이다.
# 그 외 문자가 오면 "Invalid \\escape" 로 파싱이 실패하는데,
# Windows 경로({"path":"C:\\temp\\log"} 를 의도한 {"path":"C:\temp\log"}) 처럼
# 이스케이프가 빠진 채 저장되는 경우가 많다.
# 이런 백슬래시를 찾아 \\ 로 바꿔주기 위한 패턴이다.
INVALID_JSON_ESCAPE = re.compile(r'\\(?!["\\/bfnrtu])')


def parse_json_text(raw_text):
    r"""Text 컬럼 값이 JSON 이면 파싱해서, 아니면 원본 문자열 그대로 반환한다.

    ag_result.result_text 와 ag_command_detail.additional_params 에 함께 쓴다.
    두 컬럼 모두 Text 라 여러 형태가 섞여 들어온다.
      1) 정상 JSON 문자열 : 예) '{"domain":"www.example.com","certs":[...]}'
      2) 깨진 JSON 문자열 : 예) '{"a":"ttt\iii"}'  (\i 는 JSON 이 허용하지 않는 이스케이프)
      3) 일반 문자열      : 예) 'nginx restart', 추출된 로그 본문 등

    1), 2) 는 호출자가 다시 json.loads 하지 않도록 dict/list 로 풀어서 반환하고,
    3) 은 원본 문자열을 그대로 반환한다.

    2) 를 살리는 이유는 에이전트/사용자가 Windows 경로나 정규식을 넣을 때
    백슬래시를 이스케이프하지 않고 저장하는 사례가 잦기 때문이다.
    이 경우 백슬래시를 살린 채(\i -> 값에 그대로 \i 로 남는다) 파싱한다.

    주의: json.loads 는 '123', 'true', '"abc"' 같은 스칼라 문자열도 성공하지만,
    이런 값은 원래 의미가 "문자열 값" 이므로 dict/list 일 때만 파싱 결과를
    채택하고 나머지는 원본 문자열을 유지한다.
    """
    # None 또는 빈 문자열은 파싱할 것이 없으므로 그대로 돌려준다.
    if not raw_text:
        return raw_text

    # 1차 : 있는 그대로 파싱
    parsed = try_json_loads(raw_text)

    # 2차 : JSON object/array 로 보이는데 1차가 실패했다면
    #       잘못된 백슬래시 이스케이프를 보정한 뒤 다시 파싱해 본다.
    #       (로그 본문 같은 일반 텍스트는 { [ 로 시작하지 않으므로 이 경로를 타지 않는다)
    if parsed is None:
        stripped = raw_text.strip()
        if stripped[:1] in ('{', '['):
            parsed = try_json_loads(INVALID_JSON_ESCAPE.sub(r'\\\\', raw_text))

    # JSON object / array 만 구조화된 값으로 간주한다.
    if isinstance(parsed, (dict, list)):
        return parsed

    # JSON 이 아닌 평범한 문자열(또는 스칼라) -> 원본 유지
    return raw_text


def try_json_loads(text):
    """json.loads 를 시도하고 실패하면 None 을 반환한다."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


class CommandMasterApi(BaseApi):

    resource_name = 'command_master'

    @expose('/create', methods=['POST'])
    @protect()
    def create(self):
        """즉시 실행 가능한 CommandMaster 데이터를 생성합니다. (API Key 인증 지원)
        ---
        post:
          summary: CommandMaster 즉시 실행 명령 생성
          description: 외부 시스템에서 API Key를 사용하여 즉시 실행 가능한 명령어(CommandMaster)를 생성합니다.
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    command_type_id:
                      type: string
                      description: 실행할 명령어 타입 ID
                      example: "NEWGEN.Read.http.m"
                    broadcast_callback:
                      type: string
                      description: 브로드캐스트용 콜백 함수명 (선택)
                    target_agent_id:
                      type: array
                      items:
                        type: string
                      description: 대상 에이전트 ID 목록 (선택, 단일 문자열도 가능)
                    target_agent_group_id:
                      type: array
                      items:
                        type: string
                      description: 대상 에이전트 그룹 ID 목록 (선택, 단일 문자열도 가능)
                    parameters:
                      type: object
                      description: 명령어 실행 시 필요한 추가 파라미터 (JSON 객체 또는 문자열)
                      example: {"module": "nginx", "restart": true}
                    command_sender:
                      type: string
                      enum: [SERVER, MQTT]
                      default: SERVER
                      description: >
                        전달 방식. SERVER 는 Agent 의 REST 폴링으로 전달(기본).
                        MQTT 는 생성 직후 브로커로 즉시 push 하여 폴링 지연을 없앤다.
                        MQTT 발행이 실패하면 자동으로 REST 폴링으로 fallback 된다.
                      example: MQTT
          responses:
            201:
              description: 생성 성공
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      return_code:
                        type: integer
                        example: 1
                      message:
                        type: string
                        example: "OK"
                      command_id:
                        type: string
                        description: 생성된 명령어의 UUID
            400:
              description: 필수 파라미터 누락 등 잘못된 요청
        """
        try:
            data = json.loads(request.data) if request.data else request.json
        except Exception:
            return jsonify({'return_code': -1, 'message': 'Invalid JSON'}), 400

        if not data:
            return jsonify({'return_code': -1, 'message': 'Empty payload'}), 400

        command_type_id = data.get('command_type_id')
        if not command_type_id:
            return jsonify({'return_code': -2, 'message': 'command_type_id is required'}), 400

        command_type = db.session.query(AgCommandType).filter_by(command_type_id=command_type_id).first()
        if not command_type:
            return jsonify({'return_code': -2, 'message': f'Invalid command_type_id: {command_type_id}'}), 400

        broadcast_callback = data.get('broadcast_callback')
        target_agent_id = data.get('target_agent_id')
        target_agent_group_id = data.get('target_agent_group_id')

        if not (broadcast_callback or target_agent_id or target_agent_group_id):
            return jsonify({'return_code': -2, 'message': 'Target must be specified (broadcast_callback, target_agent_id, or target_agent_group_id)'}), 400

        parameters = data.get('parameters', '')
        if parameters is None:
            parameters = ''
        elif isinstance(parameters, (dict, list)):
            parameters = json.dumps(parameters)

        # 전달 방식. 기본은 SERVER(Agent 가 REST 폴링으로 가져감).
        # MQTT 를 주면 서버가 commit 직후 cmd/{agent_id}/req 로 즉시 push 한다.
        # 발행이 실패하면 status 가 CREATE 로 남아 REST 폴링으로 fallback 된다.
        command_sender = data.get('command_sender', 'SERVER')

        if command_sender not in TargetToSendEnum.__members__:
            return jsonify({'return_code': -2,
                            'message': f'Invalid command_sender: {command_sender}. '
                                       f'Use one of {list(TargetToSendEnum.__members__)}'}), 400

        new_command_id = get_uuid()

        cmd_master = AgCommandMaster(
            command_id=new_command_id,
            ag_command_type=command_type,
            periodic_type=PeriodicTypeEnum.IMMEDIATE,
            additional_params=parameters,
            publish_yn=YnEnum.YES,
            cancel_yn=YnEnum.NO,
            finished_yn=YnEnum.NO,
            command_sender=TargetToSendEnum[command_sender],
            result_receiver=TargetToSendEnum.SERVER,
            broadcast_callback=broadcast_callback
        )

        if target_agent_id:
            agent_ids = [target_agent_id] if isinstance(target_agent_id, str) else target_agent_id
            agents = db.session.query(AgAgent).filter(AgAgent.agent_id.in_(agent_ids)).all()
            if agents:
                cmd_master.ag_agent.extend(agents)
                
        if target_agent_group_id:
            group_ids = [target_agent_group_id] if isinstance(target_agent_group_id, str) else target_agent_group_id
            groups = db.session.query(AgAgentGroup).filter(AgAgentGroup.agent_group_id.in_(group_ids)).all()
            if groups:
                cmd_master.ag_agent_group.extend(groups)

        try:
            db.session.add(cmd_master)
            db.session.commit()
            return jsonify({'return_code': 1, 'message': 'OK', 'command_id': new_command_id}), 201
        except Exception as e:
            db.session.rollback()
            logging.error(f'Error creating CommandMaster: {str(e)}')
            return jsonify({'return_code': -1, 'message': 'Internal Server Error'}), 500

    @expose('/extract_log', methods=['POST'])
    @protect(allow_browser_login=True)
    def extract_log(self):
        """특정 조건에 맞는 로그 추출 Command 등록
        ---
        post:
          summary: WAS 에러 로그 추출 명령 등록
          description: 특정 날짜, 시간, 키워드 등의 조건에 맞는 WAS 에러 로그를 추출하도록 CommandMaster를 생성하고 에이전트에 하달합니다.
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  required:
                    - host_id
                    - was_instance_id
                    - date
                    - time_from
                    - time_to
                  properties:
                    host_id:
                      type: string
                      description: 대상 서버 ID
                      example: "uok01a"
                    was_instance_id:
                      type: string
                      description: 대상 WAS 인스턴스 ID
                      example: "uok01a_servlet_engine1"
                    date:
                      type: string
                      description: 추출 기준 날짜 (yyyymmdd 형식)
                      example: "20260825"
                    time_from:
                      type: string
                      description: 추출 시작 시간 (hhmmss 형식)
                      example: "140439"
                    time_to:
                      type: string
                      description: 추출 종료 시간 (hhmmss 형식)
                      example: "150000"
                    file_name:
                      type: string
                      description: 대상 로그 파일명. (선택) 입력하지 않을 경우 시스템이 날짜에 맞춰 자동 생성합니다. 'file' 이라는 키로도 입력 가능.
                    keywords:
                      type: array
                      items:
                        type: string
                      description: 검색할 키워드 목록 (선택) 기본값은 ["Exception", "Fail"] 입니다.
                      example: ["Exception", "Fail", "Error"]
                    dateRegex:
                      type: array
                      items:
                        type: object
                      description: 날짜 포맷 정규식 배열 (선택). 입력하지 않을 경우 시스템에 등록된 태그에서 동적으로 조회합니다.
          responses:
            201:
              description: 생성 성공
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      return_code:
                        type: integer
                        example: 1
                      message:
                        type: string
                        example: "OK"
                      command_id:
                        type: string
                        description: 생성된 명령어의 UUID
            400:
              description: 필수 파라미터 누락, 유효하지 않은 포맷 등 잘못된 요청
            500:
              description: 서버 내부 에러
        """
        try:
            data = json.loads(request.data) if request.data else request.json
        except Exception:
            return jsonify({'return_code': -1, 'message': 'Invalid JSON'}), 400

        if not data:
            return jsonify({'return_code': -1, 'message': 'Empty payload'}), 400

        host_id = data.get('host_id')
        was_instance_id = data.get('was_instance_id')
        date = data.get('date') # yyyymmdd
        time_from = data.get('time_from') # hhmmss
        time_to = data.get('time_to') # hhmmss
        file_name = data.get('file_name', data.get('file', ''))
        keywords = data.get('keywords', ["Exception", "Fail"])
        date_regex_param = data.get('dateRegex')

        if not all([host_id, was_instance_id, date, time_from, time_to]):
            return jsonify({'return_code': -2, 'message': 'Missing required parameters (host_id, was_instance_id, date, time_from, time_to)'}), 400

        # 1. 파일명 생성 로직
        if not file_name:
            today_str = datetime.now().strftime("%Y%m%d")
            if date == today_str:
                file_name = f"/log/jeus/{was_instance_id}/JeusServer.log"
            else:
                file_name = f"/log/jeus/{was_instance_id}/JeusServer_{date}.log"
        
        # 2. Target Agent 찾기
        target_agent = None
        cand_agents = [
            f"{host_id}_jeus_J",
            f"{host_id}_webtob_J"
        ]
        
        for cand in cand_agents:
            agent = db.session.query(AgAgent).filter(AgAgent.agent_id == cand, AgAgent.approved_yn == 'YES').first()
            if agent:
                target_agent = agent
                break
                
        if not target_agent:
            agent = db.session.query(AgAgent).filter(AgAgent.agent_id.like(f"{host_id}_%_J"), AgAgent.approved_yn == 'YES').first()
            if agent:
                target_agent = agent

        if not target_agent:
            return jsonify({'return_code': -1, 'message': f'Approved agent not found for host: {host_id}'}), 400

        # 3. Command Type 검증
        command_type_id = "EXTRACT.LOG"
        command_type = db.session.query(AgCommandType).filter_by(command_type_id=command_type_id).first()
        if not command_type:
            return jsonify({'return_code': -2, 'message': f'Invalid command_type_id: {command_type_id}'}), 400

        # 4. 로그 포맷 정규식 (dateRegex) 추출 로직
        if date_regex_param:
            date_regex_list = date_regex_param
        else:
            was_instance = db.session.query(MwWasInstance).filter_by(was_instance_id=was_instance_id).first()
            if not was_instance:
                return jsonify({'return_code': -2, 'message': 'Invalid was_instance_id'}), 400
                
            was_id = was_instance.was_id
            tag_name = f"MS-{was_id[1:]}-{was_instance_id.split('_')[0]}"
            
            date_regex_list = []
            ms_tag = db.session.query(UtTag).filter_by(tag=tag_name).first()
            if ms_tag:
                # 상위 tag 조회
                for parent_tag in ms_tag.ut_parent_tag:
                    if parent_tag.tag.startswith('log.format') and parent_tag.value1:
                        try:
                            date_regex_list.append(json.loads(parent_tag.value1))
                        except Exception as e:
                            logging.error(f'Error parsing log.format tag value1: {str(e)}')
                            pass

        # 5. Parameters (추가 파라미터 구성)
        parameters = {
            "file": file_name,
            "targetDate": date,
            "startTime": time_from,
            "endTime": time_to,
            "keywords": keywords,
            "dateRegex": date_regex_list,
            "abbreviatePrefix": "\tat "
        }
        
        new_command_id = get_uuid()

        cmd_master = AgCommandMaster(
            command_id=new_command_id,
            ag_command_type=command_type,
            periodic_type=PeriodicTypeEnum.IMMEDIATE,
            additional_params=json.dumps(parameters),
            publish_yn=YnEnum.YES,
            cancel_yn=YnEnum.NO,
            finished_yn=YnEnum.NO,
            command_sender=TargetToSendEnum.SERVER,
            result_receiver=TargetToSendEnum.SERVER
        )
        
        cmd_master.ag_agent.append(target_agent)

        try:
            db.session.add(cmd_master)
            db.session.commit()
            return jsonify({'return_code': 1, 'message': 'OK', 'command_id': new_command_id}), 201
        except Exception as e:
            db.session.rollback()
            logging.error(f'Error creating CommandMaster EXTRACT.LOG: {str(e)}')
            return jsonify({'return_code': -1, 'message': 'Internal Server Error'}), 500

    @expose('/result', methods=['GET'])
    @protect(allow_browser_login=True)
    def result(self):
        """Command 실행 결과(ag_result) 최근 1건을 조회합니다.
        ---
        get:
          summary: Command 실행 결과 조회
          description: >
            command_id / agent_id / host_id 중 하나 이상을 조건으로 실행 결과(ag_result)를 조회합니다.
            조건에 해당하는 결과가 여러 건인 경우 create_on 기준 가장 최근 1건만 반환합니다.
            해당 결과의 Command Detail(ag_command_detail) 정보인 command_type_id, command_class,
            additional_params 도 함께 반환합니다.
          parameters:
          - name: command_id
            in: query
            description: 명령어 ID (ag_command_master.command_id)
            required: false
            schema:
              type: string
          - name: agent_id
            in: query
            description: 에이전트 ID
            required: false
            schema:
              type: string
          - name: host_id
            in: query
            description: HOST 이름
            required: false
            schema:
              type: string
          responses:
            200:
              description: 조회 성공
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      return_code:
                        type: integer
                        example: 1
                      message:
                        type: string
                        example: "OK"
                      data:
                        type: object
                        nullable: true
                        description: 조회된 결과. 조건에 맞는 결과가 없으면 null
                        properties:
                          id:
                            type: integer
                          command_id:
                            type: string
                          agent_id:
                            type: string
                          repetition_seq:
                            type: integer
                          host_id:
                            type: string
                          key_value1:
                            type: string
                          key_value2:
                            type: string
                          result_text:
                            description: >
                              실행 결과 본문. 저장된 값이 JSON(object/array) 형태이면
                              파싱된 JSON 으로, 그 외 일반 텍스트면 문자열 그대로 반환한다.
                              백슬래시 이스케이프가 깨진 JSON 도 보정해서 파싱한다.
                            oneOf:
                            - type: object
                            - type: array
                            - type: string
                            nullable: true
                          result_hash:
                            type: string
                          result_status:
                            type: string
                          result_message:
                            type: string
                          create_on:
                            type: string
                            description: 결과 생성 일시 (YYYY-MM-DD HH:MM:SS)
                          complited_date:
                            type: string
                            nullable: true
                            description: 완료 일시 (YYYY-MM-DD HH:MM:SS)
                          command_type_id:
                            type: string
                            description: ag_command_detail.command_type_id
                          command_class:
                            type: string
                            description: ag_command_detail.command_class
                          additional_params:
                            description: >
                              ag_command_detail.additional_params.
                              저장된 값이 JSON(object/array) 형태이면 파싱된 JSON 으로,
                              그 외 일반 문자열이면 문자열 그대로 반환한다.
                              백슬래시 이스케이프가 깨진 JSON 도 보정해서 파싱한다.
                            oneOf:
                            - type: object
                            - type: array
                            - type: string
                            nullable: true
            400:
              description: 조회 조건 누락
        """
        # 1. 조회 조건 파싱
        #    셋 다 선택 항목이지만 전체 조회를 막기 위해 최소 1개는 반드시 있어야 한다.
        command_id = request.args.get('command_id')
        agent_id = request.args.get('agent_id')
        host_id = request.args.get('host_id')

        if not (command_id or agent_id or host_id):
            return jsonify({'return_code': -2, 'message': 'At least one of command_id, agent_id, host_id is required'}), 400

        # 2. ag_result 와 ag_command_detail 조인
        #    두 테이블은 (command_id, agent_id, repetition_seq) 조합이 연결 키다.
        #    모델에 선언된 AgResult.ag_command_detail relationship 대신 명시적 조인을 쓰는 이유는
        #    models/agent.py 의 ForeignKeyConstraint 가 __table_args__ 에 등록되지 않아
        #    실제 테이블에 붙지 않기 때문이다.
        #    결과만 있고 detail 이 없는 데이터도 조회되도록 outer join 을 사용한다.
        query = db.session.query(AgResult, AgCommandDetail)\
            .outerjoin(AgCommandDetail,
                       (AgCommandDetail.command_id == AgResult.command_id)
                       & (AgCommandDetail.agent_id == AgResult.agent_id)
                       & (AgCommandDetail.repetition_seq == AgResult.repetition_seq))

        # 3. 입력된 조건만 AND 로 붙인다. (미입력 항목은 조건에서 제외)
        if command_id:
            query = query.filter(AgResult.command_id == command_id)
        if agent_id:
            query = query.filter(AgResult.agent_id == agent_id)
        if host_id:
            query = query.filter(AgResult.host_id == host_id)

        # 4. 여러 건이면 create_on 기준 최근 1건만 반환한다.
        #    create_on 이 같은 초에 여러 건 쌓이는 경우를 대비해 id 역순을 2차 정렬로 둔다.
        rec = query.order_by(AgResult.create_on.desc(), AgResult.id.desc()).first()

        # 조건에 맞는 결과가 없는 것은 에러가 아니므로 200 + data:None 으로 응답한다.
        if not rec:
            return jsonify({'return_code': 0, 'message': 'No result found', 'data': None}), 200

        result, detail = rec

        # 5. 응답 구성
        #    - Enum 컬럼(result_status, command_class)은 JSON 직렬화가 안 되므로 .name 으로 변환
        #    - DateTime 컬럼은 'YYYY-MM-DD HH:MM:SS' 문자열로 변환
        #    - detail 이 없을 수 있으므로(outer join) command_* 항목은 None 방어
        data = {
            'id': result.id,
            'command_id': result.command_id,
            'agent_id': result.agent_id,
            'repetition_seq': result.repetition_seq,
            'host_id': result.host_id,
            'key_value1': result.key_value1,
            'key_value2': result.key_value2,
            # result_text 도 agent 가 수집 결과를 JSON 으로 올리는 경우가 많다.
            # JSON 이면 파싱해서 내려주고, 로그 본문 같은 일반 텍스트면 원본 그대로 둔다.
            'result_text': parse_json_text(result.result_text),
            'result_hash': result.result_hash,
            'result_status': result.result_status.name if result.result_status else None,
            'result_message': result.result_message,
            'create_on': result.create_on.strftime("%Y-%m-%d %H:%M:%S") if result.create_on else None,
            'complited_date': result.complited_date.strftime("%Y-%m-%d %H:%M:%S") if result.complited_date else None,
            'command_type_id': detail.command_type_id if detail else None,
            'command_class': detail.command_class.name if detail and detail.command_class else None,
            # additional_params 는 JSON 문자열일 수도, 일반 문자열일 수도 있다.
            # JSON 이면 파싱해서 JSON 그대로 내려준다. (parse_json_text 참고)
            'additional_params': parse_json_text(detail.additional_params) if detail else None
        }

        return jsonify({'return_code': 1, 'message': 'OK', 'data': data}), 200

appbuilder.add_api(CommandMasterApi)
