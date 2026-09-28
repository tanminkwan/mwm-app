# SPEC 020: Command Result 자동실행을 통한 지식정보(Markdown) 자동 생성

## 1. 개요
Agent의 Command 실행 결과를 파싱하여 Markdown 형식으로 변환 후, 시스템 내 지식정보 게시판(`ut_md_content`)에 자동 등록(저장)하기 위한 Autorun(자동실행) 기능을 추가합니다.

## 2. 요구사항
- Command 처리 결과로 수신되는 JSON/JSONL 형식의 데이터를 Markdown으로 자동 변환해야 합니다.
- 변환된 Markdown 텍스트는 `ut_md_content` (지식정보-Markdown 형식) 테이블에 새로운 항목으로 자동 Insert 되어야 합니다.
- 자동 실행을 위해 맵핑할 신규 함수명은 `log_2_knowledge`로 지정합니다.

## 3. 상세 구현 방안

### 3.1. Markdown 변환 (사전 준비 완료)
- `app/common.py`에 추가된 `jsonl_to_markdown` 함수를 재사용하여 데이터를 파싱 및 포매팅합니다.

### 3.2. Autorun 함수 개발
- **대상 파일**: `app/sqls/agent_dml.py`
- **클래스**: `AutorunResult`
- **추가 함수**: `log_2_knowledge(self)`
- **동작 로직**:
  1. `self.result` 객체로부터 `result_text` (결과 데이터 원문) 추출
  2. 데이터 파싱 및 본문 구성
     * `jsonl_to_markdown` 함수를 호출하여 본문 마크다운 텍스트 생성
     * `host_id`와 `최하위_디렉터리명`(was_instance_id)을 이용하여 `mw_was_instance` 테이블을 먼저 조회하고(여러 건이 반환될 경우 **첫 번째 row만 취함**), 이를 통해 상위 `mw_was`까지 추적하여 정보를 추출 (DB 조회 실패 시 에러 처리 없이 해당 값만 공란으로 둠)
     * 최종 `content_md` 형태:
       ```markdown
       ## Log 추출 기준
       - WAS 이름: {mw_was.was_name} 
       - WAS Domain id : {mw_was.was_id}
       - WAS 설치 서버 : {mw_was.located_host_id}
       - WAS instance id : {mw_was_instance.was_instance_id}
       - WAS instance 실행 서버 : {mw_was_instance.host_id}
       - Log 파일 : {additional_params 의 'file' 값}
       - 발생 기간 : {additional_params 의 시작 일시(targetDate+startTime 또는 start) 값} ~ {additional_params 의 종료 일시(targetDate+endTime 또는 end) 값}
       - 추출 문자열 : {additional_params 의 'keywords' 값}
       ## Log 추출 내용
       {jsonl_to_markdown 변환 결과값}
       ```
     * (참고: `Log 파일`, `발생 기간`, `추출 문자열`은 `self.result.ag_command_detail.additional_params`를 JSON으로 파싱하여 값을 가져옵니다.)
  3. `content_name` (제목) 구성 
     * 형식: `Log Extracted - {host_id} - {최하위_디렉터리명} - {시작시간(yyyy.mm.dd hh:mi)}`
     * (참고: 파일 위치 경로(`key_value2`)에서 가장 안쪽 디렉터리명을 추출하고, 로그의 첫 항목 등에서 시작시간을 추출하여 사용)
  4. `app.sqls.monitor.insert_row` 유틸리티 함수(혹은 `db.session.add` 방식 등)를 이용하여 `ut_md_content` 테이블에 데이터 인서트
     * **추가 로직**: DB의 `ut_tag` 테이블을 조회하여 `tag == '지식유형-LOG추출'` 레코드가 존재하면 해당 레코드를 새로 생성되는 지식정보에 매핑(연결)하고, 없으면 무시합니다.
  5. 성공 여부에 따라 `(1, 'OK')` 또는 `(-1, 에러메시지)` 리턴

### 3.3. DB 테이블 정보 (참고용)
- **테이블명**: `ut_md_content` (`UtMdContent` 모델)
- **인서트 대상 컬럼**:
  - `content_name`: 생성된 식별용 제목
  - `content_md`: 변환된 Markdown 텍스트
  - `search_tags`: `command_id=실제_command_id_값` 형태의 데이터 저장
  - `content_id`: 모델에서 `get_uuid()`로 자동 부여
  - `update_on`, `create_on`: 모델 기본값 또는 `insert_row` 함수 내에서 자동 부여
  - `user_id`: 자동실행 주체이므로 `scheduler` 셋팅 (기본 처리됨)

## 4. UI 설정 가이드 (향후 적용 시)
웹 관리자 UI의 **Agent&Command > Command 처리결과 자동 반영 설정(Result 자동실행 목록)**에서 룰 등록:
- **자동실행 Type**: `FILENAME`
- **대상 파일 이름**: 처리할 로그 파일명의 정규식 패턴 (예: `.*\.log$`)
- **자동실행 기능(autorun_func)**: `log_2_knowledge` 입력
