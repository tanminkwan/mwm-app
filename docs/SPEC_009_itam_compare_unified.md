# ITAM 데이터 대사(Comparison) 정의서

> **최종 수정일**: 2026-03-17  
> **버전**: `미들웨어관리소(VER:20260317.010)`  
> **통합 정보**: `itam_compare_requirement.md`, `itam_compare_flow.md`, `itam_compare_implementation_plan.md`를 현행화하여 통합함.

---

## 1. 개요 및 목적

ITAM(IT 자산관리 시스템)의 구성 데이터와 본 시스템(미들웨어관리소)에 등록된 실시간 미들웨어(WAS/WEB) 데이터를 비교하여 정합성을 검증한다. 상호 누락되거나 설정이 불일치하는 항목을 찾아내어 데이터의 신뢰성을 확보하는 것을 목적으로 한다.

---

## 2. 주요 대사 유형 (6가지)

| 구분 | 기준 데이터 | 비교 대상 데이터 | 목적 |
|------|------------|----------------|------|
| **1-1** | ITAM WAS (`it_was`) | 미들웨어관리소 WAS (`mw_was`) | ITAM에 등록된 WAS가 미들웨어관리소에 정상 등록/연결되었는지 확인 |
| **1-2** | ITAM 내장WEB (`it_was`) | 미들웨어관리소 WEB (`mw_web`) | WAS 내장 웹 서버의 등록 및 설정 일치 여부 확인 |
| **1-3** | ITAM 외장WEB (`it_web`) | 미들웨어관리소 WEB (`mw_web`) | ITAM에 등록된 외장 웹 서버의 미들웨어관리소 등록 여부 확인 |
| **2-1** | 미들웨어관리소 WAS (`mw_was`) | ITAM WAS (`it_was`) | 미들웨어관리소에서 관리 중인 WAS가 ITAM에 누락(또는 불용)되었는지 확인 |
| **2-2** | 미들웨어관리소 내장WEB (`mw_web`) | ITAM WAS (`it_was`) | 미들웨어관리소 내장 웹이 ITAM에 누락(또는 불용)되었는지 확인 |
| **2-3** | 미들웨어관리소 외장WEB (`mw_web`) | ITAM 외장WEB (`it_web`) | 미들웨어관리소 외장 웹이 ITAM에 누락(또는 불용)되었는지 확인 |

---

## 3. 핵심 규칙 및 로직 (Refined)

### 3-1. WAS ID 정규화 (Suffix Handling)
미들웨어관리소의 `was_id`는 환경에 따라 접미사가 붙을 수 있으나, ITAM의 `domain_name`과 비교 시에는 이를 제거하여 매핑율을 높인다.
- **제거 대상 접미사**: `_dev`, `_test`, `_A`, `_L`, `_N`
- **처리 함수**: `_get_cleaned_was_id(was_id)`

### 3-2. ITAM 불용 데이터 처리
ITAM 테이블(`it_was`, `it_web`)에 데이터가 존재하더라도 `config_status = '불용'`인 레코드는 미들웨어관리소 기준 대사 시 **'ITAM 미등록'**으로 간주하여 색출한다.

### 3-3. 호스트 및 매핑 규칙
- **WAS/WEB 공통**: 기본적으로 `host_id`와 `domain_name`(또는 `was_id`)을 조합하여 비교한다.
- **내장 WEB**: 포트 번호(`embed_web_port`)가 ITAM에 누락된 경우가 많고, WAS당 내장 웹은 최대 1개이므로 **포트 비교를 제외**하고 `host_id`와 정규화된 `domain_name`만으로 매핑한다.

---

## 4. 대사 상세 로직

### 4-1. ITAM WAS 기준 (1-1)
- **필터**: `status != '불용'`, `run_env` 운영/이관/개발, 특정 키워드(`(S)`, `tmax`) 제외
- **오류 항목**:
  - `hostname 미등록`: `host_id`가 미들웨어관리소 서버 마스터(`mw_server`)에 없음
  - `WAS 미등록`: `domain_name` + `run_env` 매핑 데이터가 미들웨어관리소에 없음
  - `설치 서버 불일치`: `host_id`가 미들웨어관리소 등록 서버와 다름
  - `WAS SSL 불일치`: 미들웨어관리소 리스너의 SSL 설정과 ITAM의 `was_ssl_yn`이 다름
  - `Agent 없음/비활성화`: 미들웨어관리소에 Agent가 없거나 통신이 5분 이상 단절됨

### 4-2. ITAM 내장WEB 기준 (1-2)
- **필터**: `it_was.embed_web_yn = 'Y'`
- **오류 항목**:
  - `내장 WEB 미등록`: `host_id` 기준 매핑되는 내장 웹 서버가 미들웨어관리소에 없음
  - `SSL 여부 불일치`: ITAM(`embed_web_ssl_yn`) ↔ 미들웨어관리소(`t__ssl_yn`) 불일치
  - `WAS Domain 이상`: ITAM(`domain_name`) ↔ 미들웨어관리소(`dependent_was_id`) 불일치
  - `구분 이상`: 미들웨어관리소에 '내장' 타입으로 등록되지 않음

### 4-3. 미들웨어관리소 WAS/WEB 기준 (2-1~3)
- **필터**: `use_yn = 'YES'`
- **오류 항목**:
  - `ITAM 미등록`: 미들웨어관리소의 데이터를 ITAM에서 찾을 수 없거나, 찾았더라도 `config_status = '불용'`인 경우
  - **비교 키**: `host_id` + `cleaned_was_id` (WAS/내장웹), `host_id` + `port` (외장웹)

---

## 5. 시스템 아키텍처 및 구현 파일

### 5-1. 호출 흐름 (Flow)
1. **[UI]** 사용자가 '일괄 대사 실행' 클릭
2. **[API]** `itam_compare_api.py` → `run_all()` 호출
3. **[SQL]** `itam_compare.py` → 기존 결과 DELETE 후 6개 대사 함수 실행
4. **[Result]** 대사 결과 테이블 4개(`it_itam_was_compare` 등)에 결과 저장

### 5-2. 주요 파일 목록
| 파일 경로 | 역할 |
|-----------|------|
| `app/models/itam.py` | ITAM 원본 및 대사 결과 테이블 모델 정의 |
| `app/sqls/itam_compare.py` | **핵심 대사 로직** 및 데이터 변환 함수 |
| `app/views/itam.py` | 대사 결과 조회 및 조치 관리 화면 |
| `app/templates/itam_compare.html` | 대사 실행 UI 및 결과 탭 구성 |

---

## 6. 데이터 변환 매핑 테이블

| 미들웨어관리소 (Landscape) | ITAM (run_env) |
|-------------------|----------------|
| `PROD` | 운영 |
| `TEST` | 이관 |
| `DEV` | 개발 |
| `DR` | DR |

| 미들웨어관리소 (ssl_yn) | ITAM (ssl_yn) |
|----------------|--------------|
| `YES` | `Y` |
| `NO` | `N` |
