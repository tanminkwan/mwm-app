from app import appbuilder
from flask import jsonify, send_file, request, current_app, g
from flask_appbuilder import has_access
from flask_appbuilder.api import BaseApi, expose
from app.file_manager.s3.filemanager import S3FileManager
from app.file_manager.s3.s3 import S3Client
from io import BytesIO
from app.mail_sender import send_mail, convert_md_to_html

class CommonApi(BaseApi):

    route_base = '/common'

    @expose('/health', methods=['GET'])
    def health(self):
        return jsonify(status="healthy"), 200

    @expose('/download/<filename>', methods=['GET'])
    @has_access
    def download_file(self, filename):
        file_manager = S3FileManager()
        file_data = file_manager.get_file(filename)

        real_filename = filename if "_sep_" not in filename else filename.split("_sep_", 1)[1]
        return send_file(BytesIO(file_data), download_name=real_filename, as_attachment=True)

    @expose('/get_url_to_download/<filename>', methods=['GET'])
    @has_access
    def get_url_to_download(self, filename):
        file_manager = S3Client()
        download_url = file_manager.generate_presigned_url(filename, expiration=300)
        return {"download_url":download_url}

    @expose('/generate_long_term_token', methods=['GET'])
    @has_access
    def generate_long_term_token(self):
        """현재 로그인한 사용자의 1년(365일) 유효 개인 인증 토큰 발급"""
        from flask_jwt_extended import create_access_token
        from datetime import timedelta
        
        if not g.user or g.user.is_anonymous:
            return jsonify({"error": "Authentication required"}), 401
            
        # 365일 (1년) 유효한 토큰 생성 (Identity는 보통 user_id 또는 username 사용)
        token = create_access_token(identity=g.user.id, expires_delta=timedelta(days=365))
        return jsonify(token=token), 200

from flask_appbuilder.api import BaseApi, expose, protect
from app.api.errors import internal_error

class EmailApi(BaseApi):
    resource_name = 'email'

    @expose('/send', methods=['POST'])
    @protect()
    def send(self):
        """이메일 발송 API
        ---
        post:
          summary: 이메일 발송
          description: SMTP를 통해 HTML 이메일을 발송합니다. (인증 필요 - JWT/Session)
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    sender_name:
                      type: string
                      description: 발신인 표시 이름
                      example: "미들웨어관리소 시스템"
                    receivers:
                      type: string
                      description: 수신인 이메일 주소 (여러 명일 경우 콤마로 구분)
                      example: "user1@example.com, user2@example.com"
                    subject:
                      type: string
                      description: 메일 제목
                      example: "[알림] 시스템 정기 점검 안내"
                    content:
                      type: string
                      description: 메일 본문 (HTML 지원)
                      example: "<h1>공지</h1><p>내용입니다.</p>"
          responses:
            200:
              description: 발송 성공
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      message:
                        type: string
                        example: "Email sent successfully"
            400:
              description: 필수 파라미터 누락
            500:
              description: 메일 발송 오류
        """
        data = request.json or {}
        sender_name = data.get('sender_name')
        receivers = data.get('receivers')
        subject = data.get('subject')
        content = data.get('content')

        if not all([sender_name, receivers, subject, content]):
            return jsonify({"error": "Missing required parameters"}), 400

        if isinstance(receivers, str):
            receivers = [r.strip() for r in receivers.split(',')]

        success, message = send_mail(
            host=current_app.config['SMTP_HOST'],
            port=current_app.config['SMTP_PORT'],
            sender='admin@leebalso.org',
            sender_name=sender_name,
            receivers=receivers,
            subject=subject,
            content=content,
            use_tls=current_app.config.get('SMTP_USE_TLS', False),
            username=current_app.config.get('SMTP_USERNAME'),
            password=current_app.config.get('SMTP_PASSWORD')
        )

        if success:
            return jsonify({"message": "Email sent successfully"}), 200
        else:
            return internal_error('Email send failed', key='error', detail=message)

    @expose('/send_markdown', methods=['POST'])
    @protect()
    def send_markdown(self):
        """Markdown 이메일 발송 API
        ---
        post:
          summary: Markdown 이메일 발송
          description: Markdown 콘텐츠를 HTML로 변환(Mermaid, S3 이미지 포함)하여 SMTP로 발송합니다. (인증 필요 - JWT/Session)
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    sender_name:
                      type: string
                      description: 발신인 표시 이름
                      example: "미들웨어관리소 시스템"
                    receivers:
                      type: string
                      description: 수신인 이메일 주소 (여러 명일 경우 콤마로 구분)
                      example: "user1@example.com, user2@example.com"
                    subject:
                      type: string
                      description: 메일 제목
                      example: "[알림] 시스템 점검 결과 보고"
                    content:
                      type: string
                      description: 메일 본문 (Markdown 형식)
                      example: "# 점검 결과\n\n- 엔진 상태: **정상**\n\n```mermaid\ngraph TD; A-->B;\n```"
          responses:
            200:
              description: 발송 성공
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      message:
                        type: string
                        example: "Email sent successfully"
            400:
              description: 필수 파라미터 누락
            500:
              description: 메일 발송 오류
        """
        data = request.json or {}
        sender_name = data.get('sender_name')
        receivers = data.get('receivers')
        subject = data.get('subject')
        content_md = data.get('content')

        if not all([sender_name, receivers, subject, content_md]):
            return jsonify({"error": "Missing required parameters"}), 400

        if isinstance(receivers, str):
            receivers = [r.strip() for r in receivers.split(',')]

        kroki_url = current_app.config.get('KROKI_URL', 'http://mwm-kroki:8000').rstrip('/')
        inlined_html, inline_images = convert_md_to_html(content_md, kroki_url)

        success, message = send_mail(
            host=current_app.config['SMTP_HOST'],
            port=current_app.config['SMTP_PORT'],
            sender=current_app.config.get('SMTP_SENDER', 'admin@leebalso.org'),
            sender_name=sender_name,
            receivers=receivers,
            subject=subject,
            content=inlined_html,
            use_tls=current_app.config.get('SMTP_USE_TLS', False),
            username=current_app.config.get('SMTP_USERNAME'),
            password=current_app.config.get('SMTP_PASSWORD'),
            inline_images=inline_images
        )

        if success:
            return jsonify({"message": "Email sent successfully"}), 200
        else:
            return internal_error('Email send failed', key='error', detail=message)

class MarkdownApi(BaseApi):
    resource_name = 'markdown'

    @expose('/to_html', methods=['POST'])
    @protect()
    def to_html(self):
        """Markdown을 HTML로 변환하는 API
        ---
        post:
          summary: Markdown을 HTML로 변환
          description: Markdown 콘텐츠를 HTML로 변환(Mermaid, S3 이미지 포함)하여 반환합니다. (인증 필요 - JWT/Session)
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    content:
                      type: string
                      description: 변환할 Markdown 본문
                      example: "# 제목\n\n- 내용\n\n```mermaid\ngraph TD; A-->B;\n```"
          responses:
            200:
              description: 변환 성공
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      html:
                        type: string
                        description: 변환된 HTML
                        example: "<h1>제목</h1><p>내용</p>"
            400:
              description: 필수 파라미터 누락
            500:
              description: 변환 오류
        """
        data = request.json or {}
        content_md = data.get('content')

        if not content_md:
            return jsonify({"error": "Missing required parameter: content"}), 400

        try:
            kroki_url = current_app.config.get('KROKI_URL', 'http://mwm-kroki:8000').rstrip('/')
            inlined_html, _ = convert_md_to_html(content_md, kroki_url)
            return jsonify({"html": inlined_html}), 200
        except Exception:
            return internal_error('Markdown to_html failed', key='error')

appbuilder.add_api(CommonApi)
appbuilder.add_api(EmailApi)
appbuilder.add_api(MarkdownApi)
