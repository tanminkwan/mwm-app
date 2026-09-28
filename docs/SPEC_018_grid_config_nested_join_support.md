# SPEC_018: Grid Config Nested Join Support

## 1. 배경
- `/monitor/gridView`에서 특정 테이블(예: `mw_web_domain`)을 조회할 때, 직접적인 관계가 없는 상위 오브젝트(예: `mw_web.use_yn`)의 값으로 필터링하거나 기본 검색 조건을 설정하고자 함.
- 기존 시스템은 1단계 관계(Direct Relationship)만 조인하여 필터링할 수 있었으나, 복잡한 데이터 모델(Domain -> Vhost -> Web) 대응을 위해 중첩된(Nested) 관계 조인을 지원할 필요가 있음.

## 2. 변경 내용
- **`app/sqls/monitor.py`**:
    - `select_rows2` 함수에서 `join_conditions`의 키값에 점(`.`)이 포함된 경우(예: `mw_web_vhost.mw_web`) 이를 순차적으로 조인하도록 로직 개선.
    - `aliased`와 `inspection`을 사용하여 안전하게 중첩된 모델을 탐색하고 필터링함.
- **`app/api/grid_api.py`**:
    - `GridApi.table_view_2`에서 `column` 명에 포함된 점(`.`) 개수 제한(기존 1개)을 해제하고, 마지막 항목을 제외한 나머지를 `join_path`로 처리하도록 수정.
- **`app/views/monitor.py`**:
    - `gridView` 함수에서 **조회조건항목**([`.`] 포함된 중첩 경로)의 데이터 타입(Enum 등)을 올바르게 가져오도록 개선하여 UI 레이아웃 및 검색 연산자 최적화.
- **`app/templates/list_jqgrid.html`**:
    - 조회 조건(`condition`)이 없는 테이블에서도 '조회 실행' 버튼이 항상 표시되도록 템플릿 로직 수정.
- **`config.py`**:
    - `APP_NAME` 버전을 `미들웨어관리소(VER:20260406.003)`로 업데이트.

## 3. 사용법 (UI 설정)
- `/mogridconfigmodelview` (Table 목록 조회 설정) 메뉴에서 해당 `grid_key`의 **기본조건(`default_condition`)** 필드에 다음과 같이 입력:
    ```json
    {"column":"mw_web_vhost.mw_web.use_yn", "operator":"eql", "value":"YES"}
    ```
- 만약 이미 검색 조건이 있는 경우 쉼표로 구분하여 추가:
    ```json
    {"column":"column1","operator":"eql","value":"val1"}, {"column":"mw_web_vhost.mw_web.use_yn", "operator":"eql", "value":"YES"}
    ```

## 4. 수정 파일 목록
- `/app/api/grid_api.py`
- `/app/sqls/monitor.py`
- `/app/templates/list_jqgrid.html`
- `/config.py`
