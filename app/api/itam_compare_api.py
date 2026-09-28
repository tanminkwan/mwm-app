"""
ITAM 대사(Compare) API 엔드포인트
"""
from app import appbuilder, db
from flask import jsonify, request
from flask_appbuilder.api import BaseApi, expose
from flask_appbuilder import has_access
import logging

from app.sqls.itam_compare import (
    run_all_compare,
    compare_single_itam_was,
    compare_single_itam_web,
    compare_single_leebalso_was,
    compare_single_leebalso_web
)
from app.models.itam import (
    ItItamWasCompare, ItItamWebCompare,
    ItLeebalsoWasCompare, ItLeebalsoWebCompare
)

log = logging.getLogger(__name__)


class ItamCompareApi(BaseApi):
    resource_name = 'itam-compare'
    allow_browser_login = True

    @expose('/run-all', methods=['POST'])
    @has_access
    def run_all(self):
        """일괄 대사 실행"""
        try:
            summary = run_all_compare()
            return jsonify({
                'message': 'ITAM 대사 완료',
                'summary': summary
            }), 200
        except Exception as e:
            log.error(f"일괄 대사 실행 오류: {str(e)}")
            return jsonify({'message': f'대사 실행 중 오류 발생: {str(e)}'}), 500

    @expose('/itam-was/<config_id>', methods=['POST'])
    @has_access
    def compare_itam_was_single(self, config_id):
        """ITAM WAS 단건 대사"""
        try:
            count = compare_single_itam_was(config_id)
            return jsonify({
                'message': f'ITAM WAS 대사 완료 (config_id={config_id})',
                'error_count': count
            }), 200
        except Exception as e:
            return jsonify({'message': f'대사 실행 중 오류 발생: {str(e)}'}), 500

    @expose('/itam-web/<config_id>', methods=['POST'])
    @has_access
    def compare_itam_web_single(self, config_id):
        """ITAM WEB 단건 대사"""
        try:
            count = compare_single_itam_web(config_id)
            return jsonify({
                'message': f'ITAM WEB 대사 완료 (config_id={config_id})',
                'error_count': count
            }), 200
        except Exception as e:
            return jsonify({'message': f'대사 실행 중 오류 발생: {str(e)}'}), 500

    @expose('/leebalso-was/<int:id>', methods=['POST'])
    @has_access
    def compare_leebalso_was_single(self, id):
        """미들웨어관리소 WAS 단건 대사"""
        try:
            count = compare_single_leebalso_was(id)
            return jsonify({
                'message': f'미들웨어관리소 WAS 대사 완료 (id={id})',
                'error_count': count
            }), 200
        except Exception as e:
            return jsonify({'message': f'대사 실행 중 오류 발생: {str(e)}'}), 500

    @expose('/leebalso-web/<int:id>', methods=['POST'])
    @has_access
    def compare_leebalso_web_single(self, id):
        """미들웨어관리소 WEB 단건 대사"""
        try:
            count = compare_single_leebalso_web(id)
            return jsonify({
                'message': f'미들웨어관리소 WEB 대사 완료 (id={id})',
                'error_count': count
            }), 200
        except Exception as e:
            return jsonify({'message': f'대사 실행 중 오류 발생: {str(e)}'}), 500

    @expose('/results/itam-was', methods=['GET'])
    @has_access
    def results_itam_was(self):
        """ITAM WAS 대사 결과 조회"""
        results = db.session.query(ItItamWasCompare).order_by(
            ItItamWasCompare.error_type, ItItamWasCompare.config_id
        ).all()
        return jsonify([self._serialize_itam_was(r) for r in results]), 200

    @expose('/results/itam-web', methods=['GET'])
    @has_access
    def results_itam_web(self):
        """ITAM WEB 대사 결과 조회"""
        results = db.session.query(ItItamWebCompare).order_by(
            ItItamWebCompare.error_type, ItItamWebCompare.config_id
        ).all()
        return jsonify([self._serialize_itam_web(r) for r in results]), 200

    @expose('/results/leebalso-was', methods=['GET'])
    @has_access
    def results_leebalso_was(self):
        """미들웨어관리소 WAS 대사 결과 조회"""
        results = db.session.query(ItLeebalsoWasCompare).order_by(
            ItLeebalsoWasCompare.error_type, ItLeebalsoWasCompare.leebalso_id
        ).all()
        return jsonify([self._serialize_leebalso_was(r) for r in results]), 200

    @expose('/results/leebalso-web', methods=['GET'])
    @has_access
    def results_leebalso_web(self):
        """미들웨어관리소 WEB 대사 결과 조회"""
        results = db.session.query(ItLeebalsoWebCompare).order_by(
            ItLeebalsoWebCompare.error_type, ItLeebalsoWebCompare.leebalso_id
        ).all()
        return jsonify([self._serialize_leebalso_web(r) for r in results]), 200

    def _serialize_itam_was(self, r):
        w = r.it_was
        return {
            'id': r.id,
            'config_id': r.config_id,
            'host_id': w.host_id if w else None,
            'run_env': w.run_env if w else None,
            'domain_name': w.domain_name if w else None,
            'config_name': w.config_name if w else None,
            'install_user': w.install_user if w else None,
            'was_ssl_yn': w.was_ssl_yn if w else None,
            'os_type': w.os_type if w else None,
            'error_type': r.error_type,
            'error_content': r.error_content,
            'action_yn': r.action_yn.name if r.action_yn else 'NO',
            'create_on': r.create_on.strftime('%Y-%m-%d %H:%M:%S') if r.create_on else None
        }

    def _serialize_itam_web(self, r):
        w = r.it_web
        return {
            'id': r.id,
            'config_id': r.config_id,
            'host_id': w.host_id if w else None,
            'node_port': w.node_port if w else None,
            'config_name': w.config_name if w else None,
            'ssl_yn': w.ssl_yn if w else None,
            'run_env': w.run_env if w else None,
            'install_user': w.install_user if w else None,
            'os_type': w.os_type if w else None,
            'webtob_version': w.webtob_version if w else None,
            'error_type': r.error_type,
            'error_content': r.error_content,
            'action_yn': r.action_yn.name if r.action_yn else 'NO',
            'create_on': r.create_on.strftime('%Y-%m-%d %H:%M:%S') if r.create_on else None
        }

    def _serialize_leebalso_was(self, r):
        w = r.mw_was
        return {
            'id': r.id,
            'leebalso_id': r.leebalso_id,
            'located_host_id': w.located_host_id if w else None,
            'landscape': w.landscape.value if w and w.landscape else None,
            'was_id': w.was_id if w else None,
            'was_name': w.was_name if w else None,
            'sys_user': w.sys_user if w else None,
            'os_type': w.c_os_type() if w else None,
            'error_type': r.error_type,
            'error_content': r.error_content,
            'action_yn': r.action_yn.name if r.action_yn else 'NO',
            'create_on': r.create_on.strftime('%Y-%m-%d %H:%M:%S') if r.create_on else None
        }

    def _serialize_leebalso_web(self, r):
        w = r.mw_web
        return {
            'id': r.id,
            'leebalso_id': r.leebalso_id,
            'host_id': w.host_id if w else None,
            'port': w.port if w else None,
            'web_name': w.web_name if w else None,
            'ssl_yn': w.t__ssl_yn() if w else None,
            'landscape': w.landscape.value if w and w.landscape else None,
            'sys_user': w.sys_user if w else None,
            'os_type': w.mw_server.os_type.name if w and w.mw_server and w.mw_server.os_type else None,
            'version_info': w.version_info if w else None,
            'error_type': r.error_type,
            'error_content': r.error_content,
            'action_yn': r.action_yn.name if r.action_yn else 'NO',
            'create_on': r.create_on.strftime('%Y-%m-%d %H:%M:%S') if r.create_on else None
        }


appbuilder.add_api(ItamCompareApi)
