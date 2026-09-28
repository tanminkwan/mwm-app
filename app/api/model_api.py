from app import appbuilder
from flask import jsonify, request
from flask_appbuilder.api import BaseApi, expose, protect
from app.sqls.monitor import select_rows2, get_model_info, get_all_tables
import json

class ModelSpecApi(BaseApi):

    resource_name = 'model'

    @expose('/column_all/<table_column>', methods=['GET'])
    @protect(allow_browser_login=True)
    def col_values_all(self, table_column):

        table_name, column_name = table_column.split('.')

        if request.args:
            tmp = request.args.get('condition')
            condition = [json.loads(tmp)]
        else:
            condition = None

        col_recs, _ = select_rows2(table_name, column_name, condition=condition, distinct=False)

        col_list = []
        if col_recs:
            [ col_list.append({'pk':r[1],'value':r[0]}) for r in col_recs ]        

        return jsonify({'list':col_list})

    @expose('/column_distinct/<table_column>', methods=['GET'])
    @protect(allow_browser_login=True)
    def col_values_distinct(self, table_column):

        table_name, column_name = table_column.split('.')

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
