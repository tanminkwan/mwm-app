# HOWTO: CommandMasterApi 사용 가이드

## 1. 개요
이 문서는 `CommandMasterApi`를 사용하여 외부 시스템 등에서 REST API로 즉시 실행 가능한 명령어(`CommandMaster`) 데이터를 생성하고, 그 **실행 결과를 조회**하는 방법을 안내합니다.

## 2. 엔드포인트 정보

| 경로 | 메서드 | 용도 |
|---|---|---|
| `/api/v1/command_master/create` | `POST` | 즉시 실행 명령 생성 |
| `/api/v1/command_master/extract_log` | `POST` | WAS 에러 로그 추출 명령 생성 ([SPEC 021](SPEC_021_extract_log_api.md)) |
| `/api/v1/command_master/result` | `GET` | 명령 실행 결과 조회 ([SPEC 022](SPEC_022_command_result_api.md)) |

* **인증 방식**: Session 및 API Key (Bearer 토큰 지원)

이 문서의 4~7장은 `create`를, 8장은 `result`를 다룹니다.

## 3. API Key 인증 방법
API 호출 시 HTTP Header의 `Authorization` 필드에 Bearer 토큰(API Key)을 포함하여 전달해야 합니다.
```bash
curl -X POST "http://<SERVER_IP>:<PORT>/api/v1/command_master/create" \
     -H "Authorization: Bearer <YOUR_API_KEY>" \
     -H "Content-Type: application/json" \
     -d '{...}'
```

## 4. Request Body 파라미터 (JSON)

### 필수 항목
* `command_type_id` (String): 실행할 명령어 타입 ID
* **대상(Target) 지정 (아래 세 가지 중 최소 하나는 반드시 포함)**:
  * `broadcast_callback` (String): 브로드캐스트용 콜백 함수명
  * `target_agent_id` (String 또는 List[String]): 대상 에이전트 ID
  * `target_agent_group_id` (String 또는 List[String]): 대상 에이전트 그룹 ID

### 선택 항목
* `parameters` (String/JSON 객체): 명령어 실행 시 추가적으로 필요한 설정 값
* `command_sender` (String): 명령 전달 방식. 기본값 `SERVER`
  | 값 | 동작 |
  |---|---|
  | `SERVER` (기본) | 에이전트가 REST 폴링으로 가져감. 폴링 주기만큼 지연 발생 |
  | `MQTT` | 생성 직후 MQTT 브로커로 즉시 push. 폴링 지연 없음 (실측 2초 내 수행 완료) |

  * 값을 주지 않으면 기존과 동일하게 동작하므로 **기존 호출을 수정할 필요가 없습니다.**
  * `MQTT` 지정 시 발행이 실패하면(브로커 장애, 에이전트 세션 없음 등) 명령이 `CREATE`
    상태로 남아 **기존 REST 폴링으로 자동 fallback** 됩니다. 명령이 유실되지 않습니다.
  * 서버에서 MQTT 가 비활성(`MQTT_ENABLED=False`)이면 `MQTT` 를 지정해도 폴링으로 전달됩니다.
  * 허용되지 않는 값은 HTTP 400 으로 거부되며 응답에 허용 목록이 포함됩니다.
  * 상세: [HOWTO_016](HOWTO_016_mqtt_realtime_command.md)

## 5. 요청 예시

### 5.1. 단일/다중 에이전트에 명령어 전달
`target_agent_id`에 문자열 또는 문자열 배열을 전달할 수 있습니다.
```json
{
  "command_type_id": "CMD_UPDATE_CONFIG",
  "target_agent_id": ["AGENT_001", "AGENT_002"],
  "parameters": {
    "module": "nginx",
    "restart": true
  }
}
```

### 5.2. 브로드캐스트(서버 전체)로 콜백 함수 실행
```json
{
  "command_type_id": "CMD_SYNC_STATUS",
  "broadcast_callback": "sync_all_agents",
  "parameters": "{\"force_sync\": true}"
}
```

### 5.3. MQTT 로 즉시 전달
`command_sender`에 `MQTT`를 지정하면 폴링을 기다리지 않고 바로 에이전트에 도달합니다.
```json
{
  "command_type_id": "COMMON.READFILE",
  "target_agent_id": ["devhost01_ops_J"],
  "parameters": "/srv/mqtt/DESIGN.md",
  "command_sender": "MQTT"
}
```

실패 응답 예시 (허용되지 않는 값):
```json
{
  "return_code": -2,
  "message": "Invalid command_sender: BOGUS. Use one of ['SERVER', 'MQTT']"
}
```

## 6. Response (응답)

### 6.1. 성공 응답 (HTTP 201)
정상적으로 데이터가 생성된 경우 서버에서 자동 발급한 `command_id`를 반환합니다.
```json
{
  "return_code": 1,
  "message": "OK",
  "command_id": "8b3f2991-c239-45ce-98ea-f03320c4a5da"
}
```

### 6.2. 실패 응답 (HTTP 400 등)
필수 파라미터가 누락된 경우 등에 반환됩니다.
```json
{
  "return_code": -2,
  "message": "Target must be specified (broadcast_callback, target_agent_id, or target_agent_group_id)"
}
```

## 7. 시스템 자동 처리 내역 (DB)
API를 통해 요청된 데이터는 `AgCommandMaster` 테이블에 기록되며, 즉시 실행을 위해 다음 값들이 자동 설정됩니다.
* `periodic_type`: `IMMEDIATE`
* `publish_yn`: `YES`
* `cancel_yn` / `finished_yn`: `NO`
* `result_receiver`: `SERVER`
* `command_sender`: 요청의 `command_sender` 값 (미지정 시 `SERVER`)
* 파라미터로 지정된 대상에 따라 `ag_agent` 및 `ag_agent_group` 연결 매핑 자동 생성 (SQLAlchemy).

`command_sender=MQTT` 인 경우 `AgCommandDetail.command_status` 가 다음과 같이 전이합니다.

| 상황 | status 흐름 |
|---|---|
| 정상 | `MQTT` → (결과 수신) `COMPLITED` / `FAILED` |
| 발행 실패·구독자 없음 | `CREATE` 유지 → (REST 폴링) `SENDED` → `COMPLITED` / `FAILED` |

> `periodic_type` 은 이 API 가 항상 `IMMEDIATE` 로 설정합니다. `command_sender=MQTT` 는
> 실시간 push 전용이므로 실행 구분이 `IMMEDIATE` 여야 하며, UI 등 다른 경로로 생성할 때도
> 서버가 자동으로 `IMMEDIATE` 로 강제합니다.

## 8. 명령 실행 결과 조회 (`GET /result`)
에이전트가 명령을 수행하고 보고한 결과(`ag_result`)를 조회합니다.

### 8.1. 요청
`command_id` / `agent_id` / `host_id` 중 **최소 하나**를 Query String으로 전달합니다.
조건이 하나도 없으면 HTTP 400을 반환합니다.

```bash
# 명령 ID로 조회
curl -X GET "http://<SERVER_IP>:<PORT>/api/v1/command_master/result?command_id=956065ee17ab" \
     -H "Authorization: Bearer <YOUR_API_KEY>"

# 에이전트의 가장 최근 결과 조회
curl -X GET "http://<SERVER_IP>:<PORT>/api/v1/command_master/result?agent_id=devhost01_ops_J" \
     -H "Authorization: Bearer <YOUR_API_KEY>"
```

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `command_id` | 선택 | 명령어 ID (`create` 응답으로 받은 값) |
| `agent_id` | 선택 | 에이전트 ID |
| `host_id` | 선택 | HOST 이름 |

여러 조건을 함께 주면 AND로 결합됩니다.
**조건에 맞는 결과가 여러 건이면 `create_on` 기준 가장 최근 1건만** 반환합니다.

### 8.2. 응답 (HTTP 200)
`ag_result`의 결과 정보와 함께, `ag_command_detail`에서 조인한
`command_type_id` / `command_class` / `additional_params`를 반환합니다.

```json
{
  "return_code": 1,
  "message": "OK",
  "data": {
    "id": 395,
    "command_id": "03c3fb4eac3b",
    "agent_id": "devhost01_ops_J",
    "host_id": "devhost01",
    "repetition_seq": 1,
    "result_status": "COMPLITED",
    "result_text": {"domain": "www.example.com", "certs": []},
    "result_message": "Inserted into mw_etc_ssl_domain",
    "create_on": "2026-08-07 10:58:26",
    "complited_date": "2026-08-07 10:58:26",
    "command_type_id": "CALL.GET_SSL_CERTI",
    "command_class": "ExeAgentFunc",
    "additional_params": {"domain_name": "www.example.com", "port": "443"}
  }
}
```

조회된 결과가 없으면 에러가 아니라 `data: null`로 응답합니다.
```json
{ "return_code": 0, "message": "No result found", "data": null }
```

조회 조건을 하나도 주지 않으면 HTTP 400입니다.
```json
{ "return_code": -2, "message": "At least one of command_id, agent_id, host_id is required" }
```

### 8.3. `result_text` / `additional_params` 의 자료형
두 항목은 DB에 Text로 저장되며 JSON과 일반 문자열이 섞여 들어옵니다.
**저장된 값이 JSON(object/array)이면 파싱된 JSON으로, 그 외에는 문자열 그대로** 반환합니다.
호출하는 쪽에서 다시 `json.loads`를 할 필요가 없습니다.

```json
// JSON 으로 저장된 경우 -> object
"additional_params": {"domain_name": "www.example.com", "port": "443"}

// 일반 문자열로 저장된 경우 -> string
"additional_params": "/srv/mqtt/DESIGN.md"
```

자료형이 고정되지 않으므로 클라이언트는 두 경우를 모두 처리해야 합니다.
```python
params = data['additional_params']
if isinstance(params, dict):
    file_path = params.get('file')
else:
    file_path = params            # 평문 문자열
```

백슬래시 이스케이프가 깨진 JSON(예: `{"a":"ttt\iii"}`)도 보정해서 파싱합니다.
다만 `\t`, `\n`처럼 JSON이 정의한 이스케이프는 규격대로 해석되므로,
Windows 경로는 `C:\\temp\\log`와 같이 이스케이프해서 저장해야 합니다.
자세한 규칙은 [SPEC 022](SPEC_022_command_result_api.md)를 참고하세요.

### 8.4. 사용 예시: 명령 등록 후 결과 확인
```bash
# 1) 파일 읽기 명령 등록
CID=$(curl -s -X POST "http://<SERVER_IP>:<PORT>/api/v1/command_master/create" \
  -H "Authorization: Bearer <YOUR_API_KEY>" -H "Content-Type: application/json" \
  -d '{"command_type_id":"COMMON.READFILE",
       "target_agent_id":["devhost01_ops_J"],
       "parameters":"/srv/mqtt/DESIGN.md"}' | jq -r .command_id)

# 2) 에이전트가 수행을 마칠 때까지 대기 후 결과 조회
curl -s "http://<SERVER_IP>:<PORT>/api/v1/command_master/result?command_id=$CID" \
  -H "Authorization: Bearer <YOUR_API_KEY>" | jq .data.result_text
```
명령 등록 직후에는 에이전트가 아직 결과를 보고하지 않아 `return_code: 0`이 반환될 수 있습니다.
결과가 생길 때까지 폴링하거나, 에이전트의 명령 수신 주기를 감안해 조회하시기 바랍니다.
