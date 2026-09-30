from app import appbuilder
from flask import jsonify, request, abort
from flask_appbuilder.api import BaseApi, expose, protect
from app.sqls.monitor import select_rows2, get_model_info, get_all_tables
import json

# column_all · column_distinct 가 읽을 수 있는 컬럼 — 화면의 선택 목록(listWithJson.html)과 맞춘다.
# 주소의 테이블·컬럼 이름을 그대로 쓰면 아무 테이블이나 읽힌다 (예: ab_user.password).
COLUMN_LOOKUPS = {
    'ag_agent.agent_id',
    'mw_app_master.app_id',
    'mw_biz_category.biz_category',
    'ut_tag.tag',
}


def _lookup_target(table_column):
    if table_column not in COLUMN_LOOKUPS:
        abort(404)
    return table_column.split('.')


class ModelSpecApi(BaseApi):

    resource_name = 'model'

    @expose('/column_all/<table_column>', methods=['GET'])
    @protect(allow_browser_login=True)
    def col_values_all(self, table_column):

        table_name, column_name = _lookup_target(table_column)

        condition = None
        tmp = request.args.get('condition')
        if tmp:
            try:
                condition = [json.loads(tmp)]
            except ValueError:
                abort(400)
            # 다른 컬럼 조건은 그 컬럼 값을 한 글자씩 맞혀 보는 통로가 된다 (예: ag_agent.refresh_token)
            if not isinstance(condition[0], dict) or condition[0].get('column') != column_name:
                abort(400)

        col_recs, _ = select_rows2(table_name, column_name, condition=condition, distinct=False)

        col_list = []
        if col_recs:
            [ col_list.append({'pk':r[1],'value':r[0]}) for r in col_recs ]        

        return jsonify({'list':col_list})

    @expose('/column_distinct/<table_column>', methods=['GET'])
    @protect(allow_browser_login=True)
    def col_values_distinct(self, table_column):

        table_name, column_name = _lookup_target(table_column)

        col_recs, _ = select_rows2(table_name, column_name, distinct=True)

        col_list = []
        if col_recs:
            [ col_list.append({'pk':r[0],'value':r[0]}) for r in col_recs ]        

        return jsonify({'list':col_list})

    @expose('/modelinfo/<table>', methods=['GET'])
    @protect(allow_browser_login=True)
    def model_info(self, table):

        dic = get_model_info(table)

        return jsonify({'dict':dic})

    @expose('/tables', methods=['GET'])
    @protect(allow_browser_login=True)
    def tables(self):

        tables = get_all_tables()

        print(tables)

        return jsonify({'list':tables})

appbuilder.add_api(ModelSpecApi)
