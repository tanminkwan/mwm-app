# SPEC_010: WAS-WEB Relationship Refactoring (Association Table)

## 1. Background (변경 배경)
- 현재 `mw_web` 테이블은 `dependent_was_id`라는 문자열 컬럼을 사용하여 제우스 내장 WebToB와 WAS 간의 관계를 관리하고 있음.
- **문제점**:
  - 데이터 무결성 보장이 어려움 (WAS 삭제 시 관계 유지 등).
  - 등록 시점의 순서에 따라 관계 형성이 복잡해짐 (문자열 정규화 로직 의존).
  - 프로젝트 내 다른 관계(Tag, Application 등)와 일관성이 없음.
- **해결책**:
  - `dependent_was_id` 컬럼을 제거하고, `mw_was_web`이라는 **Association Table**을 도입하여 M:N 관계(실제로는 1:N 이 많음)를 지원함.
  - 문자열 ID 매칭 대신, **실제 물리적 설정값(JSV Port 또는 Web Home 경로)**을 기반으로 관계를 식별함.

## 2. Migration & Sync Strategy (이관 및 동기화 전략)
- **기존 방식 폐기**: `dependent_was_id` 문자열 기반의 SQL Migration을 수행하지 않음.
- **서버 내부 기능 (`update_was_web_relation`) 도입**:
    - 모든 `MwWeb` 레코드를 루프 돌며, 해당 WEB을 바라보고 있는 `MwWasWebtobConnector` 정보를 조회함.
    - 물리적 설정값이 일치하는 경우 `mw_was_web` 테이블에 모든 매칭되는 WAS 관계 정보를 일괄 생성/갱신함.
- **실행 방식**: 
    - **WEB 등록/재등록 시**: 자동으로 해당 WEB에 대한 관계 및 상태(BuiltType, NextGen)를 갱신함.
    - **WAS 등록 시**: 성능 및 복잡도 관리를 위해 자동 관계 업데이트를 수행하지 않음 (WEB 등록 시에만 수행).
    - **일괄 동기화**: UI의 `Command Master` (서버내부기능)에서 `sync_was_web_relationship`을 통해 호출 가능.
- **최종 정리**: 동기화 완료 및 검증 후 `mw_web.dependent_was_id` 컬럼을 삭제함.

## 3. Modified Files (수정 파일 목록)
- `app/models/was.py`: 
    - `mw_was_web` 테이블 정의.
    - `MwWeb.newgeneration_yn` 컬럼 정의 (차세대 여부).
    - `MwWeb.linked_was` 속성 추가 (목록 표시용).
- `app/sqls/relationship.py`:
    - 공통 동기화 함수 `update_was_web_relation(web_id=None, was_id=None)` 구현.
    - `webtobconnector`와 `mw_web_server` 매칭 로직(`get_web_servers`) 고도화.
- `app/sqls/webtob_dml.py`:
    - WEB 등록(`upsertWebtobHttpm`) 시, `update_was_web_relation`을 호출하여 관계 및 상태 갱신.
- `app/sqls/jeus_dml.py`:
    - WAS 등록 시에는 관계 업데이트를 호출하지 않도록 정립.
- `app/sqls/batch.py`:
    - `sync_was_web_relationship` 배치 함수 추가.

## 4. Technical Spec (기술 사양)
### 1) 내장 WEB 식별 및 매칭 로직 (Multi-Node / HA 대응)
1. **내장형(Internal) 판단 기준**:
   - `web_home` 경로에 `webserver` 문자열이 포함되어 있음.
   - **OR** `mw_was_web`에 연결된 WAS 중 `was_id`가 `jeus`로 시작하는 것이 존재함.
   - **예외**: 사용자가 명시적으로 `분리(Isolated)` 타입을 선택한 경우, 위 기준에 부합하더라도 업데이트하지 않음.
2. **차세대(NextGen) 판단 기준**:
   - `mw_was_web`에 연결된 WAS 중 `was_id`가 `jeus`로 시작하는 것이 존재하면 **NO**.
   - 존재하지 않으면 **YES**.

### 2) 서비스 매칭 상세 로직 (`get_web_servers`)
1. **기본 원칙**: 별도의 식별자 없이 순수하게 물리적 설정값(Port/Path)을 기반으로 `webtobconnector`와 `mw_web_server`를 연결함.
2. **단계별 매칭 기준**:
   - **호스트**: 커넥터의 `web_host_id` (localhost 등 치환 포함) == `MwWeb.host_id`.
   - **서비스 식별**:
      - **도메인 소켓 또는 파이프 방식** (`disable_pipe`=NO): `svr_id` AND `web_home` 경로 일치 여부로 매칭.
      - **그 외 일반 방식**: `svr_id` AND `jsv_port` 번호 일치 여부로 매칭.
3. **결과 반영**: 위 매칭이 성립된 모든 부모 WAS를 `mw_was_web` 테이블에 등록함. (이전 방식의 순환 참조 문제 해결)

## 5. Potential Impacts (기타 영향 파악)

### 1) UI/View 영향 (`app/views/was.py`)
- `WebCommonView`의 `list_columns` 및 `label_columns`에서 `dependent_was_id` 참조를 제거하고, 관계형 필드(예: `mw_was`)로 대체해야 함.
- 대체하지 않을 경우 WEB 목록 화면 조회 시 컬럼 부재로 인한 Runtime Error 발생 가능.

### 2) ITAM 데이터 비교 로직 (`app/sqls/itam_compare.py`)
- **가장 큰 영향**: ITAM 데이터와 로컬 데이터를 비교할 때 `dependent_was_id`를 Key로 사용하고 있음.
- 해당 파일 내의 모든 `MwWeb.dependent_was_id` 참조를 새로운 관계형 조인 또는 `httpm_object` 내의 힌트 정보 사용으로 로직 전면 수정 필요.

### 3) 엑셀 다운로드 기능
- `WebModelView`의 `Excel Download` 액션 등에서 `select *`를 사용하는 경우 컬럼 구조 변화가 결과물에 반영됨.

### 4) 데이터 마이그레이션 리스크
- 컬럼 삭제 전 반드시 `mw_was_web` 테이블로의 데이터 이관이 선행되어야 함. (Migration SQL 시퀀스 준수 필수)

## 6. Usage & Operation (사용 및 운영)
- **관계 동기화**: `Command Master` (서버내부기능)에서 `sync_was_web_relationship` 기능을 실행함.
- **검증**: `MwWas` 상세 정보 또는 구성도에서 관계가 정상인지 확인함.
- **후처리**: 모든 검증이 완료된 후, DB에서 `dependent_was_id` 컬럼을 수동 삭제(Drop)함 (또는 코드를 최종 수정하여 배포함).
