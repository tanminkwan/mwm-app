# SPEC 022: 명령 실행 결과(ag_result) 조회 API 추가

## 1. 개요
외부 시스템이나 UI에서 명령(Command)의 최신 실행 결과를 확인할 수 있도록 `ag_result` 조회 전용 API를 신규 개발합니다.
기존에는 명령을 등록(`/create`, `/extract_log`)할 수는 있었으나 그 결과를 REST로 확인할 방법이 없어, 결과 확인을 위해 DB를 직접 조회해야 했습니다.

## 2. API 명세
- **Endpoint**: `/api/v1/command_master/result`
- **Method**: `GET`
- **인증**: API Key 방식 또는 Web Session (`@protect(allow_browser_login=True)`)
- **입력 파라미터 (Query String)**: 아래 세 가지 중 **최소 하나는 반드시 지정**해야 합니다.
  - `command_id` (선택): 명령어 ID (`ag_command_master.command_id`)
  - `agent_id` (선택): 에이전트 ID
  - `host_id` (선택): HOST 이름
- 조건이 하나도 없으면 전체 조회를 막기 위해 HTTP 400 (`return_code: -2`)을 반환합니다.

## 3. 세부 처리 로직

### 3.1. 조회 조건 결합
입력된 파라미터만 AND로 결합합니다. 미입력 항목은 조건에서 제외되므로,
`agent_id`와 `host_id`를 함께 주면 두 조건을 모두 만족하는 결과만 조회됩니다.

### 3.2. 최근 1건 선별
조건에 해당하는 `ag_result` 레코드가 여러 건인 경우 **`create_on` 기준 가장 최근 1건만** 반환합니다.
`create_on`이 동일한 초에 여러 건 적재되는 경우를 대비해 `id` 역순을 2차 정렬 기준으로 사용합니다.

```sql
ORDER BY ag_result.create_on DESC, ag_result.id DESC LIMIT 1
```

### 3.3. Command Detail 조인
결과와 함께 명령 정의 정보를 내려주기 위해 `ag_command_detail`을 조인합니다.
- **조인 키**: `(command_id, agent_id, repetition_seq)`
- **조인 방식**: Outer Join. 결과만 있고 상세가 없는 데이터도 조회되어야 하므로, 이 경우 관련 항목은 `null`로 반환합니다.
- **추가 반환 항목**: `command_type_id`, `command_class`, `additional_params`

> 참고: `app/models/agent.py`의 `AgResult`에 선언된 `ForeignKeyConstraint`는 `__table_args__`에 등록되지 않아 실제 테이블에 적용되지 않습니다.
> 따라서 모델의 relationship 대신 명시적 조인 조건을 사용합니다.

### 3.4. JSON 텍스트 필드 파싱 (`parse_json_text`)
`result_text`와 `additional_params`는 모두 Text 컬럼이라 JSON과 일반 문자열이 섞여 저장됩니다.
호출자가 다시 `json.loads`를 하지 않도록, 값이 JSON이면 파싱해서 내려줍니다.

| 저장된 값 | 반환 형태 | 예시 |
|---|---|---|
| JSON object / array | 파싱된 JSON | `{"domain":"www.example.com","certs":[...]}` → object |
| 일반 문자열 | 문자열 그대로 | `/srv/mqtt/DESIGN.md` |
| 추출된 로그 본문 등 긴 텍스트 | 문자열 그대로 | 마크다운/로그 원문 |
| 빈 값 / `null` | 그대로 | `""`, `null` |

세부 규칙은 다음과 같습니다.

1. **스칼라는 문자열로 유지**: `json.loads`는 `'123'`, `'true'`, `'"abc"'` 같은 스칼라도 파싱에 성공하지만,
   이런 값은 원래 의미가 "문자열 값"이므로 **object/array일 때만** 파싱 결과를 채택합니다.
2. **깨진 백슬래시 이스케이프 보정**: JSON 규격에서 백슬래시 뒤에 올 수 있는 문자는 `" \ / b f n r t u` 뿐입니다.
   그 외 문자가 오면 `Invalid \escape`로 파싱이 실패하는데, 에이전트나 사용자가 Windows 경로나 정규식을
   이스케이프 없이 저장하는 사례가 잦습니다.
   값이 `{` 또는 `[`로 시작하는데 1차 파싱이 실패하면, JSON이 정의하지 않는 백슬래시만 `\\`로 보정한 뒤 재파싱합니다.
   - 예) `{"a":"ttt\iii"}` → `{"a": "ttt\\iii"}` (백슬래시를 값에 보존한 채 파싱)
   - 정상 이스케이프(`\n`, `\t`, `\\`, `\uXXXX`)는 건드리지 않습니다. 따라서 `{"path":"C:\temp"}`의 `\t`는
     JSON이 정의한 탭 문자로 해석됩니다. Windows 경로는 `C:\\temp`로 저장해야 합니다.
   - 로그 본문 같은 일반 텍스트는 `{`/`[`로 시작하지 않으므로 이 보정 경로를 타지 않습니다.

### 3.5. 기타 직렬화 규칙
- Enum 컬럼(`result_status`, `command_class`)은 JSON 직렬화가 불가하므로 `.name` 값(문자열)으로 변환합니다.
- DateTime 컬럼(`create_on`, `complited_date`)은 `YYYY-MM-DD HH:MM:SS` 형식 문자열로 변환합니다.

## 4. 응답 명세

### 4.1. 성공 (HTTP 200)
```json
{
  "return_code": 1,
  "message": "OK",
  "data": {
    "id": 395,
    "command_id": "03c3fb4eac3b",
    "agent_id": "devhost01_ops_J",
    "repetition_seq": 1,
    "host_id": "devhost01",
    "key_value1": "get_ssl_certi",
    "key_value2": "NO VALUE",
    "result_text": {"domain": "www.example.com", "certs": [{"index": "1", "isCA": false}]},
    "result_hash": null,
    "result_status": "COMPLITED",
    "result_message": "Inserted into mw_etc_ssl_domain",
    "create_on": "2026-08-07 10:58:26",
    "complited_date": "2026-08-07 10:58:26",
    "command_type_id": "CALL.GET_SSL_CERTI",
    "command_class": "ExeAgentFunc",
    "additional_params": {"domain_name": "www.example.com", "port": "443", "ip": "203.0.113.10"}
  }
}
```

### 4.2. 조회 결과 없음 (HTTP 200)
조건에 맞는 결과가 없는 것은 에러가 아니므로 200으로 응답합니다.
```json
{
  "return_code": 0,
  "message": "No result found",
  "data": null
}
```

### 4.3. 조회 조건 누락 (HTTP 400)
```json
{
  "return_code": -2,
  "message": "At least one of command_id, agent_id, host_id is required"
}
```

## 5. 반환 항목

| 항목 | 원본 | 설명 |
|---|---|---|
| `id` | `ag_result.id` | 결과 레코드 ID |
| `command_id` | `ag_result.command_id` | 명령어 ID |
| `agent_id` | `ag_result.agent_id` | 에이전트 ID |
| `repetition_seq` | `ag_result.repetition_seq` | 반복 수행 순번 |
| `host_id` | `ag_result.host_id` | HOST 이름 |
| `key_value1` / `key_value2` | `ag_result` | 결과 식별 키 |
| `result_text` | `ag_result.result_text` | 실행 결과 본문. JSON이면 파싱된 JSON |
| `result_hash` | `ag_result.result_hash` | 결과 해시 |
| `result_status` | `ag_result.result_status` | `CREATE` / `COMPLITED` / `NOCHANGE` / `FAILED` / `ERROR` 등 |
| `result_message` | `ag_result.result_message` | 후처리 메시지 |
| `create_on` | `ag_result.create_on` | 결과 생성 일시 |
| `complited_date` | `ag_result.complited_date` | 완료 일시 |
| `command_type_id` | `ag_command_detail.command_type_id` | 명령어 타입 ID |
| `command_class` | `ag_command_detail.command_class` | 명령어 수행 방식 |
| `additional_params` | `ag_command_detail.additional_params` | 추가 파라미터. JSON이면 파싱된 JSON |
