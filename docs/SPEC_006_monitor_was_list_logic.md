# SPEC_006: WAS 점검 대상 로직 변경 (get_not_running_was_list)

## 1. 개요
- `/monitor/get_not_running_was_list` API에서 점검 대상을 결정하는 기준을 기존 `MoWasStatusTemplate` 기반에서 `MwWas` 및 `MwWasInstance` 테이블의 `use_yn` 및 `landscape` 컬럼 기반으로 변경한다.
- 이는 보고서 관점의 고정된 템플릿 대신, 실제 등록된 데이터의 상태를 동적으로 반영하기 위함이다.

## 2. 변경 내용
### 2.1 Backend (`app/sqls/monitor.py`)
- `get_not_running_was_list` 함수 내부의 점검 대상 조회 쿼리 수정.
- **기존**: `MoWasStatusTemplate` 테이블의 모든 레코드를 조회하여 해당되는 인스턴스들을 점검.
- **변경**: 
    1. `MwWas` 테이블에서 `landscape = 'PROD'` 이고 `use_yn = 'YES'` 인 레코드 조회.
    2. 위 `MwWas`에 속한 `MwWasInstance` 중 `use_yn = 'YES'` 인 레코드를 최종 점검 대상으로 확정.
- `was_instance_group` 정보는 `MwWasInstance` 테이블에 직접적으로 존재하지 않으므로, 기존 로직과의 호환성을 위해 기본값(예: 'Instance') 또는 특정 규칙에 따른 값을 할당하도록 처리.

## 3. 수정 파일 목록
- `app/sqls/monitor.py`
- `config.py` (버전 업데이트)

## 4. 운영 절차 (Apply Changes)
1. `config.py`의 `APP_NAME` 버전 업데이트. (20260317.003)
2. `docker compose stop mwm-app && docker compose rm -f mwm-app`
3. `docker build --no-cache -t mwm-app -f Dockerfile.app .`
4. `docker compose up -d mwm-app`
