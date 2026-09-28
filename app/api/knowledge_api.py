import logging
from flask import request, jsonify
from flask_appbuilder.api import BaseApi, expose, protect
from app import appbuilder, db
from app.models.knowledge import UtMdContent

class KnowledgeApi(BaseApi):

    resource_name = 'knowledge'

    @expose('/mdcontent/list', methods=['GET'])
    @protect(allow_browser_login=True)
    def mdcontent_list(self):
        """mdcontent 목록 검색
        ---
        get:
          summary: mdcontent 목록 검색
          description: content_name 또는 search_tags 조건으로 mdcontent 목록을 조회합니다. 두 조건이 모두 주어질 경우 AND 조건으로 검색합니다.
          parameters:
            - in: query
              name: content_name
              schema:
                type: string
              description: 검색할 컨텐츠 이름 (부분 일치)
            - in: query
              name: search_tags
              schema:
                type: string
              description: 검색할 태그 (부분 일치)
            - in: query
              name: max
              schema:
                type: integer
                default: 100
              description: 최대 조회 건수
          responses:
            200:
              description: 검색 성공
            400:
              description: 검색 조건(content_name, search_tags) 누락
        """
        content_name = request.args.get('content_name')
        search_tags = request.args.get('search_tags')
        knowledge_type = request.args.get('knowledge_type')
        max_limit = request.args.get('max', default=100, type=int)

        if not content_name and not search_tags and not knowledge_type:
            return jsonify({'return_code': -1, 'message': 'content_name, search_tags, or knowledge_type is required'}), 400

        query = db.session.query(UtMdContent)

        if content_name:
            query = query.filter(UtMdContent.content_name.ilike(f"%{content_name}%"))

        if search_tags:
            query = query.filter(UtMdContent.search_tags.ilike(f"%{search_tags}%"))
            
        if knowledge_type:
            from app.models.knowledge import UtTag
            query = query.filter(UtMdContent.ut_tag.any(UtTag.tag.ilike(f"%{knowledge_type}%")))

        results = query.order_by(UtMdContent.create_on.desc()).limit(max_limit).all()

        data = []
        for r in results:
            data.append({
                'id': r.id,
                'content_id': r.content_id,
                'content_name': r.content_name,
                'search_tags': r.search_tags,
                'knowledge_tags': [t.tag for t in r.ut_tag] if r.ut_tag else [],
                'create_on': r.create_on.strftime('%Y-%m-%d %H:%M:%S') if r.create_on else None,
                'user_id': r.user_id
            })

        return jsonify({'return_code': 1, 'message': 'OK', 'data': data}), 200

    @expose('/mdcontent/<content_id>', methods=['GET'])
    @protect(allow_browser_login=True)
    def mdcontent_detail(self, content_id):
        """mdcontent 단건 조회
        ---
        get:
          summary: mdcontent 상세 조회
          description: content_id (UUID)를 사용하여 mdcontent 1건을 조회합니다.
          parameters:
            - in: path
              name: content_id
              required: true
              schema:
                type: string
              description: 조회할 mdcontent의 고유 ID
          responses:
            200:
              description: 조회 성공
            404:
              description: 해당 content_id를 찾을 수 없음
        """
        result = db.session.query(UtMdContent).filter_by(content_id=content_id).first()

        if not result:
            return jsonify({'return_code': -1, 'message': 'Not found'}), 404

        data = {
            'id': result.id,
            'content_id': result.content_id,
            'content_name': result.content_name,
            'content_md': result.content_md,
            'search_tags': result.search_tags,
            'knowledge_tags': [t.tag for t in result.ut_tag] if result.ut_tag else [],
            'create_on': result.create_on.strftime('%Y-%m-%d %H:%M:%S') if result.create_on else None,
            'update_on': result.update_on.strftime('%Y-%m-%d %H:%M:%S') if result.update_on else None,
            'user_id': result.user_id,
            'group_id': result.group_id
        }

        return jsonify({'return_code': 1, 'message': 'OK', 'data': data}), 200

appbuilder.add_api(KnowledgeApi)
