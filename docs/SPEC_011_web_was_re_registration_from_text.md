# SPEC_011: Web/WAS Re-registration from Raw Text

## 1. Background (변경 배경)
- 에이전트를 통해 수집된 WebToB 설정 원본(`web_text`) 및 JEUS 설정 원본(`was_text`)은 DB에 저장되어 있으나, 파싱 로직 변경이나 데이터 유실 시 이를 다시 반영하기 위해서는 에이전트의 재수집을 기다려야 함.
- 사용자(운영자)가 원할 때 언제든지 DB에 저장된 원본 텍스트를 기반으로 하위 정보(VHost, URI, SSL, Domain, DataSource, Application 등)를 재생성할 수 있는 수동 보정 도구가 필요함.

## 2. Technical Spec (기술 사양)
### WebToB 재등록
- `MwWeb` 테이블의 `web_text` 컬럼에 저장된 `http.m` 원본 데이터를 읽어옴.
- `httpmToDict` 함수를 사용하여 텍스트를 구조화된 JSON(Dict)으로 변환.
- **업데이트 로직**: `newgeneration_yn` (차세대 여부)에 따라 `NewHttpm` 또는 `OldHttpm` 객체를 생성하여 정보를 동기화(Upsert).
- **관계 동기화**: `upsertWebtobHttpm` 내부에서 `update_was_web_relation`을 호출하여 해당 웹 서버와 연계된 WAS 정보를 즉시 갱신하고, 내장/외장(`BuiltType`) 구분을 자동 업데이트함.

### WAS(JEUS) 재등록
- `MwWas` 테이블의 `was_text` 컬럼에 저장된 `domain.xml` 또는 `JEUSMain.xml` 원본 데이터를 읽어옴.
- `app.sqls.agent_dml.AutorunResult.update_domain(domain_info, skip_check=True)` 메서드를 호출.
- **업데이트 정책**: WEB 재등록 로직과의 일관성을 위해, 기존 설정 정보와 차이가 없더라도('Not changed') 무조건 업데이트를 수행하도록 `skip_check=True` 옵션을 적용함. (기본 에이전트 자동 수집 로직에서는 효율성을 위해 여전히 체크를 수행함)
- 내부적으로 `xmltodict`를 사용하여 파싱하고, `NewJeusDomain` 또는 `OldJeusDomain` 객체를 생성하여 정보를 동기화(Upsert).

### 전체 관계 일괄 동기화 (Batch Sync)
- 개별 재등록 외에, DB 전체의 WAS-WEB 관계 및 서버 속성을 일괄 갱신하기 위한 `sync_was_web_relationship` 배치 함수를 제공함.
- **수행 범위**: 
    1. 전역 `webtob_connector` 정보 기반 JSV 연결 갱신.
    2. 모든 Web 서버(`mw_web`)의 연결된 WAS 목록(`mw_was_web` 매핑) 전체 재산출.
    3. 모든 Web 서버의 `BuiltType`(Internal/External) 및 `NewGenerationYN` 플래그 일괄 보정.

## 3. Modified Files (수정 파일 목록)
- `app/views/was.py`:
    - `WebModelView` 및 `WasModelView`에 `re_register` 액션 추가.
- `app/sqls/batch.py`:
    - `re_register_web_from_text(web_id)` 서비스 함수 구현.
    - `re_register_was_from_text(was_id)` 서비스 함수 구현.
    - `re_register_all_was_from_text()` 서비스 함수 구현 (전체 WAS 대상 일괄 재등록).
    - `re_register_all_web_from_text()` 서비스 함수 구현 (전체 Web 대상 일괄 재등록).
    - `sync_was_web_relationship()` 배치 함수 구현 (전체 동기화용).
- `app/sqls/agent_dml.py`:
    - `AutorunResult.update_domain`에 `skip_check` 파라미터 추가하여 조건부 무조건 업데이트 지원.

## 4. Usage & Operation (사용 및 운영)
- WebToB 또는 WAS 목록 화면에서 하나 이상의 레코드를 선택 후 상단 액션 메뉴에서 `재등록 (... Text 기반)` 클릭.
- 만약 전체적인 관계 데이터나 서버 유형 플래그가 맞지 않는 것으로 판단될 경우, `Batch Sync` 기능을 호출하여 전수 조사를 수행함.
- 작업 완료 후 상세 정보 및 하위 목록(URI, VHost, DataSource 등)이 갱신되었는지 확인.
