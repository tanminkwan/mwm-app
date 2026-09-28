from app import appbuilder, db
from flask import jsonify, request, render_template
from flask_appbuilder.api import BaseApi, ModelRestApi, expose, protect
from flask_appbuilder.models.sqla.interface import SQLAInterface
from flask_appbuilder import has_access
from app.sqls.server import get_servers, add_server, update_server, delete_server
from app.sqls.was import get_next_old_was_text, get_next_old_web_text
from app.sqls.monitor import select_row
from app.models.was import MwServer
from app.sqls.agent_dml import AutorunResult
import json
import difflib
from datetime import datetime
from app.api.errors import is_internal_error

class MwServerApi(BaseApi):
    resource_name = 'mw_server'

    @expose('/list', methods=['GET'])
    @protect(allow_browser_login=True)
    def list(self):
        """List all servers or filter by host_id"""
        host_id = request.args.get('host_id')
        
        if host_id:
            server = get_servers(host_id)
            if not server:
                return jsonify({'message': f'Server {host_id} not found'}), 404
            return jsonify(self._serialize_server(server))
        
        servers = get_servers()
        return jsonify([self._serialize_server(s) for s in servers])

    @expose('/add', methods=['POST'])
    @protect()
    def add(self):
        """Create a new server"""
        try:
            data = json.loads(request.data)
        except Exception:
            return jsonify({'message': 'Invalid JSON'}), 400

        server, msg = add_server(data)
        if not server:
            return jsonify({'message': msg}), 500 if is_internal_error(msg) else 400
            
        return jsonify({'message': 'Created', 'id': server.id, 'host_id': server.host_id}), 201

    @expose('/edit/<host_id>', methods=['PUT'])
    @protect()
    def edit(self, host_id):
        """Update an existing server"""
        try:
            data = json.loads(request.data)
        except Exception:
            return jsonify({'message': 'Invalid JSON'}), 400

        server, msg = update_server(host_id, data)
        if not server:
            return jsonify({'message': msg}), 500 if is_internal_error(msg) else 404 if "not found" in msg else 400
            
        return jsonify({'message': 'Updated', 'host_id': host_id}), 200

    @expose('/delete/<host_id>', methods=['DELETE'])
    @protect()
    def delete(self, host_id):
        """Delete a server"""
        success, msg = delete_server(host_id)
        if not success:
            return jsonify({'message': msg}), 404 if "not found" in msg else 500
            
        return jsonify({'message': 'Deleted', 'host_id': host_id}), 200

    def _serialize_server(self, server):
        return {
            'id': server.id,
            'host_id': server.host_id,
            'server_name': server.server_name,
            'landscape': server.landscape.name if server.landscape else None,
            'os_type': server.os_type.name if server.os_type else None,
            'encoding': server.encoding.name if server.encoding else None,
            'jdk_version': server.jdk_version,
            'ip_address': server.ip_address,
            'vip_address': server.vip_address,
            'running_type': server.running_type.name if server.running_type else None,
            'primary_host_id': server.primary_host_id,
            'dr_host_id': server.dr_host_id,
            'use_yn': server.use_yn.name if server.use_yn else None
        }

class MWConfigurationApi(BaseApi):

    resource_name = 'config'

    @expose('/httpm', methods=['POST'])
    @protect()
    def httpm_config(self, **kwargs):

        data = json.loads(request.data)

        if not data.get('content'):
            return jsonify({'return_code':-2,'message':'content must be included'}), 401
        elif not data.get('host_id'):
            return jsonify({'return_code':-2,'message':'host_id must be included'}), 401
    
        content   = data['content']
        host_id   = data['host_id']
        sys_user = data['sys_user'] if data.get('sys_user') else ''

        rtn, msg = AutorunResult()._update_httpm(host_id, content, sys_user=sys_user)
        db.session.commit()

        if rtn < 0:
            return jsonify({'return_code':rtn, 'msg':msg}), 400

        return jsonify({'return_code':rtn, 'msg':msg}), 201

    @expose('/jeusdomain', methods=['POST'])
    @protect()
    def jeusDomainConfig(self, **kwargs):

        data = json.loads(request.data)

        if not data.get('content'):
            return jsonify({'return_code':-2,'message':'content must be included'}), 401
        elif not data.get('host_id'):
            return jsonify({'return_code':-2,'message':'host_id must be included'}), 401
        elif not data.get('domain_id'):
            return jsonify({'return_code':-2,'message':'domain_id must be included'}), 401
    
        content   = data['content']
        host_id   = data['host_id']
        domain_id = data['domain_id']
        sys_user = data['sys_user'] if data.get('sys_user') else ''
        
        domain_info = dict(
            host_id = host_id,
            domain_id = domain_id,
            content = content,
            sys_user = sys_user,
            agent_id = '',
        )

        rtn, msg = AutorunResult.update_domain(domain_info)
        db.session.commit()

        if rtn < 0:
            return jsonify({'return_code':rtn, 'msg':msg}), 400

        return jsonify({'return_code':rtn, 'msg':msg}), 201

    @expose('/webmain', methods=['POST'])
    @protect()
    def webmainConfig(self, **kwargs):

        data = json.loads(request.data)

        if not data.get('content'):
            return jsonify({'return_code':-2,'message':'content must be included'}), 401
        elif not data.get('host_id'):
            return jsonify({'return_code':-2,'message':'host_id must be included'}), 401
        elif not data.get('domain_id'):
            return jsonify({'return_code':-2,'message':'domain_id must be included'}), 401
        elif not data.get('was_instance_id'):
            return jsonify({'return_code':-2,'message':'was_instance_id must be included'}), 401
    
        content   = data['content']
        host_id   = data['host_id']
        domain_id = data['domain_id']
        was_instance_id = data['was_instance_id']
        
        rtn, msg = AutorunResult()._updateWebMain(host_id, domain_id, was_instance_id, content)
        db.session.commit()

        return jsonify({'return_code':rtn, 'msg':msg}), 201

class MwDiffApi(BaseApi):
    resource_name = 'diff'
    route_base = '/diff'

    @expose('/was/<id>', methods=['GET'])
    @has_access
    def diff_was(self, id):
        """WAS 변경 이력을 비교하여 결과를 반환합니다.
        ---
        get:
          summary: WAS 변경 이력 비교
          description: 특정 변경 이력 ID를 기반으로 이전 설정과 현재 설정을 비교하는 HTML 페이지를 반환합니다.
          parameters:
          - name: id
            in: path
            description: WAS 변경 이력(mw_was_change_history) 레코드 ID
            required: true
            schema:
              type: integer
          responses:
            200:
              description: 비교 결과 페이지 (HTML)
            404:
              description: 해당 ID의 이력을 찾을 수 없음
        """

        row, _ = select_row('mw_was_change_history',{'id':id})
        title = f'{row.mw_was} updated at {row.create_on.strftime("%Y-%m-%d %H:%M:%S")}'

        old_domain, new_domain = get_next_old_was_text(id=id)

        return render_template('diff.html'\
            , title=title
            , text1=old_domain
            , text2=new_domain
            , base_template=appbuilder.base_template
            , appbuilder=appbuilder
            )

    @expose('/web/<id>', methods=['GET'])
    @has_access
    def diff_web(self, id):
        """WEB 변경 이력을 비교하여 결과를 반환합니다.
        ---
        get:
          summary: WEB 변경 이력 비교
          description: 특정 변경 이력 ID를 기반으로 이전 설정과 현재 설정을 비교하는 HTML 페이지를 반환합니다.
          parameters:
          - name: id
            in: path
            description: WEB 변경 이력(mw_web_change_history) 레코드 ID
            required: true
            schema:
              type: integer
          responses:
            200:
              description: 비교 결과 페이지 (HTML)
            404:
              description: 해당 ID의 이력을 찾을 수 없음
        """

        row, _ = select_row('mw_web_change_history',{'id':id})
        title = f'{row.mw_web} updated at {row.create_on.strftime("%Y-%m-%d %H:%M:%S")}'

        old_httpm, new_httpm = get_next_old_web_text(id=id)

        return render_template('diff.html'\
            , title=title
            , text1=old_httpm
            , text2=new_httpm
            , base_template=appbuilder.base_template
            , appbuilder=appbuilder
            )

appbuilder.add_api(MwServerApi)
appbuilder.add_api(MWConfigurationApi)
appbuilder.add_api(MwDiffApi)

class MwDiffDataApi(BaseApi):
    resource_name = 'diff_data'
    route_base = '/diff_data'

    @expose('/was/list', methods=['GET'])
    @protect(allow_browser_login=True)
    def get_was_diff_list(self):
        """WAS 변경 이력 리스트를 조회합니다.
        ---
        get:
          summary: WAS 변경 이력 리스트 조회
          description: >
            일자 구간 및 WAS 도메인 ID를 기반으로 변경 이력 목록을 조회합니다.
            시작일(start_date)과 종료일(end_date)이 모두 없으면 일자 조건 없이
            가장 최근에 변경된 내역 1건만 조회합니다.
            시작일 또는 종료일이 하나라도 지정되면 해당 구간의 전체 내역을 조회합니다.
          parameters:
          - name: start_date
            in: query
            description: 시작일 (YYYY-MM-DD). 미지정 시 시작일 조건 없음
            required: false
            schema:
              type: string
          - name: end_date
            in: query
            description: 종료일 (YYYY-MM-DD). 미지정 시 종료일 조건 없음
            required: false
            schema:
              type: string
          - name: domain_id
            in: query
            description: WAS 도메인 ID
            required: false
            schema:
              type: string
          responses:
            200:
              description: 변경 이력 목록. 결과 배열은 data 키로 감싸서 반환됩니다.
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      data:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: integer
                              description: 변경 이력(mw_was_change_history) 레코드 ID
                            domain_id:
                              type: string
                              description: WAS 도메인 ID
                            create_on:
                              type: string
                              description: 변경 일시 (YYYY-MM-DD HH:MM:SS)
                    example:
                      data:
                      - id: 7
                        domain_id: PICI_Domain
                        create_on: '2026-02-23 14:40:00'
        """
        from app.models.was import MwWas, MwWaschangeHistory
        
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        domain_id = request.args.get('domain_id')

        query = db.session.query(MwWaschangeHistory).join(MwWas)

        if start_date_str:
            query = query.filter(MwWaschangeHistory.create_on >= datetime.strptime(start_date_str, '%Y-%m-%d'))
        if end_date_str:
            # 종료일 포함을 위해 23:59:59까지 설정하거나 다음날 00:00:00 이전으로 설정
            query = query.filter(MwWaschangeHistory.create_on <= datetime.strptime(end_date_str + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        if domain_id:
            query = query.filter(MwWas.was_id == domain_id)

        query = query.order_by(MwWaschangeHistory.create_on.desc())

        # 시작일/종료일이 모두 없으면 가장 최근 변경 내역 1건만 조회
        if not start_date_str and not end_date_str:
            query = query.limit(1)

        results = query.all()

        return self.response(200, data=[
            {
                'id': r.id,
                'domain_id': r.mw_was.was_id,
                'create_on': r.create_on.strftime("%Y-%m-%d %H:%M:%S")
            } for r in results
        ])

    @expose('/web/list', methods=['GET'])
    @protect(allow_browser_login=True)
    def get_web_diff_list(self):
        """WEB 변경 이력 리스트를 조회합니다.
        ---
        get:
          summary: WEB 변경 이력 리스트 조회
          description: >
            일자 구간 및 WEB 호스트 ID를 기반으로 변경 이력 목록을 조회합니다.
            시작일(start_date)과 종료일(end_date)이 모두 없으면 일자 조건 없이
            가장 최근에 변경된 내역 1건만 조회합니다.
            시작일 또는 종료일이 하나라도 지정되면 해당 구간의 전체 내역을 조회합니다.
          parameters:
          - name: start_date
            in: query
            description: 시작일 (YYYY-MM-DD). 미지정 시 시작일 조건 없음
            required: false
            schema:
              type: string
          - name: end_date
            in: query
            description: 종료일 (YYYY-MM-DD). 미지정 시 종료일 조건 없음
            required: false
            schema:
              type: string
          - name: host_id
            in: query
            description: WEB 호스트 ID
            required: false
            schema:
              type: string
          responses:
            200:
              description: 변경 이력 목록. 결과 배열은 data 키로 감싸서 반환됩니다.
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      data:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: integer
                              description: 변경 이력(mw_web_change_history) 레코드 ID
                            host_id:
                              type: string
                              description: WEB 서버 Host ID
                            port:
                              type: integer
                              description: WEB 서비스 Port
                            create_on:
                              type: string
                              description: 변경 일시 (YYYY-MM-DD HH:MM:SS)
                    example:
                      data:
                      - id: 3
                        host_id: devhost01
                        port: 8080
                        create_on: '2026-02-23 14:40:00'
        """
        from app.models.was import MwWeb, MwWebchangeHistory
        
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        host_id = request.args.get('host_id')

        query = db.session.query(MwWebchangeHistory).join(MwWeb)

        if start_date_str:
            query = query.filter(MwWebchangeHistory.create_on >= datetime.strptime(start_date_str, '%Y-%m-%d'))
        if end_date_str:
            query = query.filter(MwWebchangeHistory.create_on <= datetime.strptime(end_date_str + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        if host_id:
            query = query.filter(MwWeb.host_id == host_id)

        query = query.order_by(MwWebchangeHistory.create_on.desc())

        # 시작일/종료일이 모두 없으면 가장 최근 변경 내역 1건만 조회
        if not start_date_str and not end_date_str:
            query = query.limit(1)

        results = query.all()

        return self.response(200, data=[
            {
                'id': r.id,
                'host_id': r.mw_web.host_id,
                'port': r.mw_web.port,
                'create_on': r.create_on.strftime("%Y-%m-%d %H:%M:%S")
            } for r in results
        ])

    @expose('/was/<id>', methods=['GET'])
    @protect(allow_browser_login=True)
    def get_was_diff_data(self, id):
        """WAS 변경 이력 데이터를 JSON으로 반환합니다. (Unified Diff 포함)
        ---
        get:
          summary: WAS 변경 이력 데이터 조회
          description: 특정 변경 이력 ID를 기반으로 이전 설정, 현재 설정 및 Unified Diff 데이터를 JSON으로 반환합니다.
          parameters:
          - name: id
            in: path
            description: WAS 변경 이력(mw_was_change_history) 레코드 ID
            required: true
            schema:
              type: integer
          responses:
            200:
              description: 변경 이력 데이터 및 Diff (JSON)
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      domain_id:
                        type: string
                        description: WAS 도메인 ID
                      old:
                        type: string
                        description: 이전 설정 텍스트
                      new:
                        type: string
                        description: 현재 설정 텍스트
                      create_on:
                        type: string
                        description: 변경 일시
                      unified_diff:
                        type: string
                        description: Unified Diff 결과
            404:
              description: 해당 ID의 이력을 찾을 수 없음
        """
        row, _ = select_row('mw_was_change_history', {'id': id})
        if not row:
            return self.response(404, message="History not found")

        old_text, new_text = get_next_old_was_text(id=id)
        
        diff = difflib.unified_diff(
            (old_text or "").splitlines(), 
            (new_text or "").splitlines(), 
            fromfile='previous', tofile='current', lineterm=''
        )
        unified_diff = "\n".join(list(diff))
        
        return self.response(200, 
            domain_id=row.mw_was.was_id,
            old=old_text, 
            new=new_text, 
            create_on=row.create_on.strftime("%Y-%m-%d %H:%M:%S"),
            unified_diff=unified_diff
        )

    @expose('/web/<id>', methods=['GET'])
    @protect(allow_browser_login=True)
    def get_web_diff_data(self, id):
        """WEB 변경 이력 데이터를 JSON으로 반환합니다. (Unified Diff 포함)
        ---
        get:
          summary: WEB 변경 이력 데이터 조회
          description: 특정 변경 이력 ID를 기반으로 이전 설정, 현재 설정 및 Unified Diff 데이터를 JSON으로 반환합니다.
          parameters:
          - name: id
            in: path
            description: WEB 변경 이력(mw_web_change_history) 레코드 ID
            required: true
            schema:
              type: integer
          responses:
            200:
              description: 변경 이력 데이터 및 Diff (JSON)
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      host_id:
                        type: string
                        description: WEB 서버 Host ID
                      port:
                        type: integer
                        description: WEB 서비스 Port
                      old:
                        type: string
                        description: 이전 설정 텍스트
                      new:
                        type: string
                        description: 현재 설정 텍스트
                      create_on:
                        type: string
                        description: 변경 일시
                      unified_diff:
                        type: string
                        description: Unified Diff 결과
            404:
              description: 해당 ID의 이력을 찾을 수 없음
        """
        row, _ = select_row('mw_web_change_history', {'id': id})
        if not row:
            return self.response(404, message="History not found")

        old_text, new_text = get_next_old_web_text(id=id)
        
        diff = difflib.unified_diff(
            (old_text or "").splitlines(), 
            (new_text or "").splitlines(), 
            fromfile='previous', tofile='current', lineterm=''
        )
        unified_diff = "\n".join(list(diff))
        
        return self.response(200, 
            host_id=row.mw_web.host_id,
            port=row.mw_web.port,
            old=old_text, 
            new=new_text, 
            create_on=row.create_on.strftime("%Y-%m-%d %H:%M:%S"),
            unified_diff=unified_diff
        )

appbuilder.add_api(MwDiffDataApi)
