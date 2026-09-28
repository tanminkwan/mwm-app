# SPEC 021: 로그 추출(EXTRACT.LOG) 명령 등록 API 추가

## 1. 개요
외부 시스템이나 UI 호출을 통해 특정 서버와 WAS 인스턴스의 조건에 맞는 로그를 추출하는 Command(명령)를 등록하기 위한 전용 API를 신규 개발합니다.

## 2. API 명세
- **Endpoint**: `/api/v1/command_master/extract_log` (또는 등록된 Blueprint 경로 기준)
- **Method**: `POST`
- **인증**: API Key 방식 또는 Web Session (`@protect(allow_browser_login=True)`)
- **입력 파라미터 (JSON Body)**:
  - `host_id` (필수): 대상 서버 ID
  - `was_instance_id` (필수): WAS 인스턴스 ID
  - `date` (필수): 조회 날짜 (형식: `yyyymmdd`, 예: `20260825`)
  - `time_from` (필수): 조회 시작 시간 (형식: `hhmmss`, 예: `140439`)
  - `time_to` (필수): 조회 종료 시간 (형식: `hhmmss`)
  - `file_name` (선택, 또는 `file` 필드로 대체 가능): 대상 로그 파일명
  - `keywords` (선택): 검색할 키워드 배열 (입력되지 않은 경우 기본값: `["Exception", "Fail"]`)

## 3. 세부 처리 로직

### 3.1. 대상 파일명 지정 (file_name)
`file_name` 파라미터가 명시적으로 전달되지 않은 경우, 요청받은 `date` 값과 **시스템 당일 날짜**의 일치 여부에 따라 파일 경로를 자동 완성합니다.
- `date`가 오늘 날짜와 **같을 경우**: `/log/jeus/{was_instance_id}/JeusServer.log`
- `date`가 오늘 날짜와 **다를 경우**: `/log/jeus/{was_instance_id}/JeusServer_{date}.log`

### 3.2. 조회 기간 설정 (targetDate, startTime, endTime)
전달받은 `date`와 `time_from`, `time_to` 파라미터 값을 변환 없이 그대로 사용합니다.
- **targetDate**: 전달받은 `date` 값 (예: `20260825`)
- **startTime**: 전달받은 `time_from` 값 (예: `140439`)
- **endTime**: 전달받은 `time_to` 값 (예: `140443`)

### 3.3. 로그 포맷 정규식 (dateRegex) 추출 로직
`dateRegex` 파라미터는 `ut_tag` 테이블을 조회하여 동적으로 리스트를 구성합니다.
- **조회 조건**: `tag` 값이 `MS-{해당 was_id 의 맨 앞한자리를 뺀 값}-{해당 was_instance_id 의 '_'가 나타나기 전 값}`과 일치하는 데이터 조회
- **추출 대상**: 위 조건으로 조회했을 때 상위 태그(parent tag) 중에서, `tag` 값이 `log.format`으로 시작하는 데이터들의 `value1` 값을 리스트 형태로 추출합니다. (조건을 만족하는 상위 태그가 여러 개일 수 있으므로 배열 형태로 구성)
- **추출된 value1 예시**:
  ```json
  {
    "regex": "\\[(\\d{4}\\.\\d{2}\\.\\d{2}) \\[[\\w-]+\\] (\\d{2}:\\d{2}:\\d{2})\\]",
    "dateFormat": "yyyy.MM.dd",
    "timeFormat": "HH:mm:ss"
  }
  ```

### 3.4. 대상 Agent 자동 선정
명령을 수행할 에이전트는 해당 `host_id`를 기반으로 다음 우선순위에 따라 승인된(Approved) 에이전트를 검색하여 매핑합니다.
1. 1순위: `{host_id}_jeus_J`
2. 2순위: `{host_id}_webtob_J`
3. 3순위: `{host_id}_*_J` (위 조건에 맞는 에이전트가 없을 경우, `_J`로 끝나는 해당 서버의 모든 승인된 에이전트 중 1개 할당)
- **예외 처리**: 조건을 만족하는 에이전트가 전혀 없을 경우 Error (HTTP 400) 반환.

### 3.5. Command Master 테이블 등록 설정
조합된 데이터를 바탕으로 `ag_command_master` 테이블에 새로운 레코드를 인서트합니다.
- **실행 구분 (periodic_type)**: `IMMEDIATE` (즉시 실행)
- **Command Type ID**: `EXTRACT.LOG`
- **추가 파라미터 (additional_params)**: 다음 구조의 JSON 문자열로 변환하여 저장합니다.
  ```json
  {
    "file": "{자동 생성 또는 입력받은 파일명}",
    "targetDate": "{date 파라미터 값}",
    "startTime": "{time_from 파라미터 값}",
    "endTime": "{time_to 파라미터 값}",
    "dateRegex": [
      {
        "regex": "\\[(\\d{4}\\.\\d{2}\\.\\d{2}) \\[[\\w-]+\\] (\\d{2}:\\d{2}:\\d{2})\\]",
        "dateFormat": "yyyy.MM.dd",
        "timeFormat": "HH:mm:ss"
      },
      {
        "regex": "\\[(\\d{2}:\\d{2}:\\d{2})\\]",
        "timeFormat": "HH:mm:ss"
      }
    ],
    "keywords": ["Exception", "Fail"],
    "abbreviatePrefix": "\tat "
  }
  ```
  *참고: `keywords`에는 사용자가 입력한 배열이 지정되며, 값이 없을 경우 기본값으로 `["Exception", "Fail"]`이 할당됩니다.*
