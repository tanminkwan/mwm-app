from app import appbuilder
from flask import jsonify, request
from flask_appbuilder import Model
from flask_appbuilder.api import BaseApi, expose, protect
from app.sqls.monitor import get_grid_config, select_rows2
import enum
import sys
from datetime import time
import json
import re
import logging

class GridApi(BaseApi):

    #route_base = '/grid'
    resource_name = 'grid'

    def get_last_values(self, orig_v, seperator=',', condition=None):

        str_v = ''

        if isinstance (orig_v, enum.Enum):
            str_v = self.__meet_condition(orig_v.value, condition)
        elif isinstance(orig_v, Model):
            str_v = self.__meet_condition(str(orig_v), condition)
        elif isinstance (orig_v, time):
            str_v = orig_v.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(orig_v, list):
            tmp = [ self.__meet_condition(str(v), condition) for v in orig_v]
            str_v = seperator.join(tmp) if tmp else ''
        elif orig_v:
            str_v = self.__meet_condition(str(orig_v), condition)

        return str_v

    def __meet_condition(self, value, condition):

        if condition:
            operator, operand = condition

            condition_map = {
                            'like':operand in value
                            , 'nlike':operand not in value
                            , 'eql':operand==value
                            , 'neql':operand!=value
                            }

            return value if condition_map[operator] else ''
        else:
            return value

    # 컴파일된 정규식으로 성능 향상
    _RE_BRACKET = re.compile(r'\([^)]*\)')
    _RE_CONDITION = re.compile(r'\(([^)]+)')

    def __get_col_name(self, text):
        return self._RE_BRACKET.sub('', text)

    def __get_condition(self, text):
        match = self._RE_CONDITION.search(text)
        if match:
            # 'op__val' 형식을 분리
            parts = match.group(1).split('__')
            return (parts[0], parts[1]) if len(parts) == 2 else None
        return None

    def get_col_values(self, rec, col_path, seperator=','):
        """
        개선된 get_col_values (Iterative BFS 방식):
        - 재귀를 제거하여 성능 최적화 및 중간 필터링 지원
        - 컬렉션(One-to-Many) 관계 자동 확장 탐색
        - 최종 결과에 대해서만 set/sort를 수행하여 효율성 극대화
        """
        current_objs = [rec]
        nodes = col_path.split('.')

        for i, node in enumerate(nodes):
            is_last = (i == len(nodes) - 1)
            prop_name = self.__get_col_name(node)
            condition = self.__get_condition(node)
            new_objs = []

            for obj in current_objs:
                if obj is None:
                    continue
                
                try:
                    val = getattr(obj, prop_name)
                except AttributeError:
                    continue
                
                if val is None:
                    continue

                # 리스트/객체 관계를 동일하게 처리하기 위해 리스트화
                items = val if isinstance(val, (list, tuple, set)) else [val]
                
                for item in items:
                    if is_last:
                        # 마지막 노드: 실제 값 추출 및 필터 적용
                        res_str = self.get_last_values(item, seperator=seperator, condition=condition)
                        if res_str:
                            # 이미 구분자가 포함된 경우 개별 항목으로 분리하여 추가
                            new_objs.extend([v.strip() for v in res_str.split(seperator) if v.strip()])
                    else:
                        # 중간 단계: 필터 조건이 있다면 객체의 문자열 표현(str) 기준으로 필터링
                        if condition and not self.__meet_condition(str(item), condition):
                            continue
                        new_objs.append(item)
            
            current_objs = new_objs
            if not current_objs:
                break

        # 중복 제거 및 정렬 후 최종 병합
        unique_results = sorted(list(set(str(v) for v in current_objs)))
        return seperator.join(unique_results)

    @expose('/gridlist', methods=['GET'])
    @protect(allow_browser_login=True)
    def grid_list(self):

        recs = get_grid_config()

        list = []
        if recs:
            [ list.append({'pk':r.grid_key,'value':r.title+'('+ r.grid_key +')'}) for r in recs ]

        return jsonify({'list':list})

    @expose('/table/<param>', methods=['GET'])
    @protect(allow_browser_login=True)
    def table_view_2(self, param):

        cmd = request.args.get('cmd')

        rec = get_grid_config(param)

        if not rec:
            return jsonify({'msg':'Param is not found'}), 404    

        table_name = rec.table_name
        columns    = rec.columns.split(',')
        header     = rec.headers.split(',') if rec.headers else ''
        widths     = rec.widths.split(',') if rec.widths else ''
        tmp        = rec.default_condition if rec.default_condition else ''
        tmp        = '{"conditions":[' + tmp + ']}'
        conditions = json.loads(tmp)
        seperator  = rec.seperator if rec.seperator else ','
        
        title      = rec.title
        file_name  = rec.file_name
        page_dblclick = rec.page_dblclick if rec.rows_per_page else ''
        rows_per_page = rec.rows_per_page if rec.rows_per_page else 25

        if cmd == 'nodata':
            return jsonify({'list':[], 'columns':columns, 'labels':header, 'widths':widths, 'title':title, 'file_name':file_name, 'rows_per_page':rows_per_page, 'page_dblclick':page_dblclick}), 200

        try:

            condition = []
            join_table_name = ''
            nm_column_name = ''
            join_conditions = {}

            for cond in conditions['conditions']:

                if '.' in cond['column']:

                    val2 = cond['column'].split('.')

                    # join_path is all but the last element (the column name)
                    join_path = '.'.join(val2[:-1])
                    v_dict = dict(
                             operator = cond['operator']
                            ,column   = val2[-1]
                            ,value    = cond['value']
                            ) 
                    if join_conditions.get(join_path):
                        join_conditions[join_path].append(v_dict)
                    else:
                        join_conditions[join_path] = [v_dict]

                else:
                    condition.append(cond)

            for arg in request.args:

                val = arg.split('__')

                if len(val)<2:
                    continue

                if '.' in val[1]:
                    val2 = val[1].split('.')

                    # join_path is all but the last element (the column name)
                    join_path = '.'.join(val2[:-1])
                    v_dict = dict(
                             operator = val[0]
                            ,column   = val2[-1]
                            ,value    = request.args[arg]
                            ) 
                    if join_conditions.get(join_path):
                        join_conditions[join_path].append(v_dict)
                    else:
                        join_conditions[join_path] = [v_dict]
                else:
                    condition.append(
                        dict(
                        operator = val[0]
                        ,column   = val[1]
                        ,value    = request.args[arg])
                    )

            recs, _ = select_rows2(table_name, condition=condition, join_conditions=join_conditions)

        except KeyError as e:
            return jsonify({'msg':'Table:'+table_name+' dose not exist'}), 500

        grid_list = []
        
        try:

            if recs:
                for r in recs:
                
                    grid_row = {}

                    for col in columns:

                        if col.startswith('t__') and callable(getattr(r, col)):
                            grid_row[col] = getattr(r, col)()
                        else:
                            grid_row[col] = self.get_col_values(r, col, seperator)

                    grid_row['id'] = r.id
                    grid_list.append(grid_row)

        except AttributeError as e:
            excType, excValue, traceback = sys.exc_info()
            logging.error(f"AttributeError Error : {excType}, {excValue}, {traceback}")
                
            return jsonify({'msg':rec.columns+' is not valid.'}), 500

        return jsonify({'list':grid_list, 'columns':columns, 'labels':header, 'widths':widths, 'title':title, 'file_name':file_name, 'rows_per_page':rows_per_page, 'page_dblclick':page_dblclick}), 200

appbuilder.add_api(GridApi)
