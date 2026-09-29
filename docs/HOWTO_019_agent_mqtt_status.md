# HOWTO_019: Agent MQTT 수신 상태 수집·표시

> 상태: **구현·검증 완료** (2026-09-29) — 브랜치 `mwm-app-20260929-feature`. 실제 Agent 연동 결과는 §9
> 관련: [HOWTO_016](HOWTO_016_mqtt_realtime_command.md) (MQTT 실시간 Command), [HOWTO_017](HOWTO_017_mqtt_production_deployment.md) (운영 배포)

---

## 1. 개요

Agent 는 MQTT 로 명령을 **받기만** 한다(구독 전용, HOWTO_016). 지금까지 앱은 Agent 가 브로커에
붙어 있는지 알 방법이 없었다. MQTT 로 보낸 명령이 안 가도 REST 폴링으로 fallback 되니 조용히 묻힌다.

Agent(mwagent `c28bae7`)가 명령 폴링 요청에 **`X-Mqtt-Status` 헤더**를 싣기 시작했다.
앱은 이 헤더를 받아 Agent 별 최신 상태를 저장하고, 대시보드와 Agent 목록에 보여 준다.

| 할 일 | 위치 |
| :--- | :--- |
| 헤더 파싱·저장 | 명령 폴링 API → `app/sqls/agent.py` |
| 대시보드 집계·목록 | `/monitor/mqtt_agent_stat` (신규) + `my_index.html` 카드 2개 |
| Agent 목록 구별·상태 | `/agentmodelview/list` 에 `MQTT` 컬럼 + 필터 버튼 |
| DB | `ag_agent` 컬럼 6개 추가 — **운영은 ALTER SQL = DB 스크립트 11** (§6) |

새 API 를 Agent 에 열지 않는다. 폴링 응답·계약도 바꾸지 않는다.

---

## 2. 헤더 계약 (Agent 쪽, 확정)

### 2.1 언제 오는가

| 요청 | 헤더 |
| :--- | :--- |
| `GET /api/v1/command/{agent_id}` — 명령 폴링 (`command_check_cycle` 초, 로컬 80초) | **mqtt_enabled=true 일 때만** |
| `GET /api/v1/command/{agent_id}/{version}/JAVAAGENT/BOOT` — 기동 | 없음 (MQTT 기동 전) |
| `POST /api/v1/command/result` — 결과 보고 | 없음 |

**헤더가 있다 = MQTT 수신 Agent (`mqtt_enabled=true`)** 라는 뜻이다. 헤더가 없는 이유는 셋이다:
`mqtt_enabled=false`, 이 기능이 없는 구버전 Agent, Agent 가 상태 값을 만들다 예외가 난 경우
(폴링은 계속되고 헤더만 빠진다). 앱은 셋을 구별하지 않고 **MQTT 비대상**으로 본다.

### 2.2 형식

JSON 이 아니다. `;` 로 나눈 `key=value` 이고 첫 토큰이 state 다.

```
X-Mqtt-Status: connected;since=1790660594;events=0;last_msg=1790660700
X-Mqtt-Status: unstable;since=1790664000;events=3;reason=rc=32109 Connection lost
X-Mqtt-Status: never_connected;since=1790660654;events=2;reason=rc=0 Unable to connect to server cause=Connection refused
X-Mqtt-Status: not_started;reason=mqtt_broker_address not set
```

- 파싱: `split(';')` → `[0]` = state, 나머지는 **첫 `=` 기준**으로 key/value (reason 값에 `=` 가 들어간다)
- 시각(`since`, `last_msg`)은 모두 epoch 초
- `reason` 은 Agent 가 `;`·제어문자·비ASCII 를 `_` 로 바꾸고 120자로 자른다

### 2.3 state

| state | 뜻 | 함께 오는 필드 | 판정 |
| :--- | :--- | :--- | :--- |
| `connected` | 브로커에 연결됨 | `since`(마지막 연결 시각), `events`, `last_msg`? | **정상** |
| `unstable` | 한 번 이상 붙은 뒤 끊김. Paho 가 자동 재접속 중 | `since`?(끊김 시작), `events`, `last_msg`?, `reason` | 경고 |
| `never_connected` | 기동 후 한 번도 못 붙음 (브로커 다운·주소 오류·인증 실패) | `since`?, `events`, `reason`(`unknown` 가능) | 경고 |
| `not_started` | 구독자가 안 떠 있음 | `reason` 만 — `mqtt_broker_address not set` · `start_failed` · `not_running` | 경고 |
| (그 외) | 앞으로 추가될 값 | — | `unknown` 으로 저장, 원문 보존 |

`?` 는 없을 수 있다는 뜻이다. **모든 필드를 선택값으로 파싱한다.**

- `events` 는 누적 카운터가 아니다. 연결이 60초 유지되면(복구 판정) 0 으로 리셋된다 → `connected` 인데 `events>0` 이면 막 재연결한 것
- `last_msg` 는 MQTT 로 **실제 받은** 마지막 메시지 시각이다. "연결됨"과 "실제 수신 중"을 구별한다.
  명령을 모두 REST(`command_sender=SERVER`)로 보내는 Agent 에는 원래 없다
- `unstable` 의 `since` 는 콜백 없이 끊기면 최대 60초 빠질 수 있다 (Agent 감시 주기)

### 2.4 수신 확인 (2026-09-29, 로컬)

nginx 를 거쳐 앱 컨테이너까지 헤더가 그대로 도착한다 (앱 컨테이너 네트워크에서 패킷 캡처로 확인).

```
GET /api/v1/command/devhost01_ops_J
X-Mqtt-Status: connected;since=1790660594;events=0      ← since = 14:43:14 KST, Agent 재기동 시각
```

BOOT·POST result 에는 없었다. `last_msg` 없음 — 이 Agent 의 명령은 모두 `command_sender=SERVER` 다.

---

## 3. MQTT 대상 (모수) 정의

대시보드 집계와 목록, Agent 목록의 상태 표시는 **MQTT 대상**만 다룬다.

```
MQTT 대상 =  approved_yn = 'YES'
         AND last_checked_date > now - AGENT_OFFLINE_MINUTES   (OnLine, 기본 5분)
         AND mqtt_state IS NOT NULL                            (마지막 폴링에 헤더가 있었다)
```

| 경우 | 처리 | 결과 |
| :--- | :--- | :--- |
| 헤더가 있다가 **없어짐** (MQTT 끔·구버전으로 교체·Agent 예외) | 헤더 없는 폴링이 오면 MQTT 컬럼 6개를 **NULL 로 비운다** | 다음 폴링(≤ `command_check_cycle`)부터 모수에서 빠진다 |
| Agent 가 **OffLine** (폴링이 끊김) | 값은 남겨 둔다 — 갱신할 요청이 없다 | 시각 조건으로 모수에서 빠진다. 다시 붙으면 첫 폴링에서 갱신 |
| **BOOT** 요청 | MQTT 컬럼을 **건드리지 않는다** (BOOT 에는 원래 헤더가 없다) | 재기동해도 바로 비대상이 되지 않는다. 첫 폴링에서 갱신 |
| 미승인 Agent | 저장은 하지 않는다 (`check_agent_approved` 에서 먼저 반환) | 모수 밖 |

OffLine 인 Agent 의 마지막 MQTT 상태는 믿을 수 없다(폴링이 끊긴 뒤 무슨 일이 있었는지 모른다).
그래서 "OffLine 이지만 MQTT 였던 것"을 따로 세지 않는다 — OffLine 은 기존 [Agent 상태 현황]·[미접속 Agent 목록]이 이미 보여 준다.

---

## 4. 저장 — `ag_agent` 컬럼 추가

Agent 마다 최신값 한 행이면 된다 → 별도 테이블 없이 `ag_agent` 에 붙인다. 이력은 남기지 않는다.

| 컬럼 | 타입 | 내용 |
| :--- | :--- | :--- |
| `mqtt_state` | `VARCHAR(20)` NULL | `connected`·`unstable`·`never_connected`·`not_started`·`unknown`. **NULL = MQTT 비대상** |
| `mqtt_since` | `TIMESTAMP` NULL | 현재 state 시작 시각 |
| `mqtt_events` | `INTEGER` NULL | 복구 판정 이후 끊김·에러 횟수 |
| `mqtt_last_msg` | `TIMESTAMP` NULL | 마지막 MQTT 메시지 수신 시각 |
| `mqtt_reason` | `VARCHAR(120)` NULL | 끊김·미기동 사유 |
| `mqtt_raw` | `VARCHAR(300)` NULL | 헤더 원문 (300자에서 자름). `unknown` 원문 보존·장애 분석용 |

- `mqtt_state` 는 PostgreSQL enum 이 아니라 **문자열**이다. enum 은 값을 늘릴 때마다 `ALTER TYPE` 이 필요하고
  (HOWTO_016 §Step 3), "모르는 state 는 보존"과도 맞지 않는다. 앱이 아는 값 5개로만 정규화해서 넣는다
- 수신 시각 컬럼은 따로 두지 않는다. 헤더를 저장하는 폴링이 같은 UPDATE 에서 `last_checked_date` 를 갱신한다
- 시각은 `datetime.fromtimestamp(epoch)` — 컨테이너 `TZ=Asia/Seoul` 기준 naive 로컬 시각. 기존 컬럼(`datetime.now()`)과 같다

### 4.1 파싱 규칙 (앱)

헤더는 **신뢰할 수 없는 입력**이다(인증된 Agent 가 보내지만 값 자체는 검증한다).

| 항목 | 규칙 |
| :--- | :--- |
| 전체 | 앞뒤 공백 제거. 비어 있으면 헤더 없음과 같다. 1024자 초과분은 버린다 |
| state | 소문자로 비교. 아는 4개가 아니면 `unknown` (원문은 `mqtt_raw`) |
| `since`·`last_msg` | 정수가 아니거나 음수, 또는 지금보다 1일 넘게 미래면 NULL |
| `events` | 0 이상 정수가 아니면 NULL |
| `reason` | 120자로 자른다. **화면에 낼 때 HTML 이스케이프** |
| 모르는 key | 무시 (원문에는 남는다) |
| 같은 key 두 번 | 마지막 값 |

파싱 실패로 폴링 응답이 실패하면 안 된다 — 명령 수신이 MQTT 상태보다 중요하다.
파서는 예외를 내지 않고, 저장이 실패해도 로그만 남기고 폴링은 정상 응답한다.

### 4.2 저장 지점

`command_v3` (`GET /api/v1/command/<agent_id>`) 가 `send_commands(agent_id)` 를 부른다.
`send_commands` 는 폴링마다 `last_checked_date` 를 UPDATE 한다 — 여기에 MQTT 컬럼을 함께 넣는다.

```python
# app/api/agent_api.py — command_v3
mqtt = parse_mqtt_status(request.headers.get('X-Mqtt-Status'))   # 없으면 None
rtn, data = send_commands(agent_id, mqtt_status=mqtt, update_mqtt=True)

# app/sqls/agent.py — send_commands
if update_mqtt:
    update_dict.update(mqtt_columns(mqtt))   # mqtt 가 None 이면 6개 모두 None
```

`command`·`command_v2`(옛 경로)와 `command_v4` 의 BOOT 는 `update_mqtt=False`(기본값)라 컬럼을 건드리지 않는다.

`command_v4`(`/<id>/<ver>/<type>/<status>`)는 **`status != 'BOOT'` 이면 `update_mqtt=True`** 로 부른다.
주기 폴링을 이 경로로 하는 Agent 가 있어도 "헤더가 없어지면 비운다" 규칙이 같게 적용된다.
실제 Agent(0000.0010.0001)는 BOOT 만 이 경로로, 주기 폴링은 `command_v3` 로 한다 (nginx 로그로 확인).

---

## 5. 화면

### 5.1 대시보드 (`my_index.html`) — 카드 2개

기존 카드 계약(`/monitor/agent_stat`)은 그대로 두고 새 API 를 붙인다.

**`GET /monitor/mqtt_agent_stat`** (`@has_access`)

```json
{
  "mqtt_stat": [
    {"landscape": "PROD", "total": 12, "connected": 10, "unstable": 1,
     "never_connected": 0, "not_started": 1, "unknown": 0}
  ],
  "mqtt_agents": [
    {"landscape": "PROD", "agent_id": "...", "agent_name": "...", "state": "unstable",
     "since": "2026.09.29 14:43", "events": 3, "last_msg": "2026.09.29 14:40",
     "reason": "rc=32109 Connection lost", "last_checked_date": "2026.09.29 14:52"}
  ]
}
```

- **[MQTT 수신 Agent 현황]** — `landscape` 별 대상 수와 state 별 수. 기존 [Agent 상태 현황] 카드 옆에 둔다
- **[MQTT 수신 Agent 목록]** — 대상 전부. **경고 먼저**(`unstable` → `never_connected` → `not_started` → `unknown` → `connected`), 같은 state 안에서는 `since` 오래된 순.
  `last_msg` 는 경과시간("3분 전")으로, 없으면 "수신 없음"
- MQTT 대상이 0 이면(예: `MQTT_ENABLED=False` 인 설치) 현황 카드에 "MQTT 수신 Agent 없음" 을 보이고 목록 카드는 숨긴다
- 현황 카드의 `Agent 목록` 버튼은 `/agentmodelview/list/?_flt_7_mqtt_state=-` 로 간다
- JSON 값은 원문이다. 화면에 넣을 때 `escHtml()` 로 이스케이프한다 — `title='…'` 속성에도 쓰므로 따옴표까지 바꾼다

### 5.2 Agent 목록 (`/agentmodelview/list`)

- `list_columns` 에 **`c_mqtt_status`**(라벨 `MQTT`) 추가 — `c_last_checked` 옆
  - MQTT 대상이면 state 배지: `connected` 초록, 경고 3종 주황/빨강, `unknown` 회색. 경고면 `reason` 을 툴팁으로
  - 비대상(헤더 없음·OffLine·미승인)이면 빈칸 — OffLine 여부는 옆 컬럼이 이미 보여 준다
- 필터 버튼 **`MQTT`** 추가 — `_flt_7_mqtt_state=-`. 문자열 컬럼의 7번 필터는 `FilterNotEqual`(`mqtt_state != '-'`)이고,
  SQL 에서 `NULL != '-'` 는 참이 아니므로 **헤더를 보낸 Agent 만** 남는다. OnLine 조건은 버튼에 넣지 않았다 —
  기존 `OffLine` 버튼처럼 시각을 URL 에 박으면 서버 기동 시각에 고정된다. 대신 배지가 OnLine 일 때만 나온다
  - 다른 버튼 그룹(`bt_group: '2'`)이라 `PROD`·`DEV` 등과 겹쳐 걸 수 있다
- 배지 HTML 은 `Markup(...).format(...)` 으로 만든다 → Agent 가 보낸 값(`reason` 등)이 **자동 이스케이프**된다 (CodeQL XSS, TASK 1-12)

---

## 6. DB 변경 — 운영은 ALTER SQL

운영은 폐쇄망이라 `flask db upgrade` 를 쓰지 않는다. 아래 SQL 을 파일로 제공한다 (배포 런북의 **DB 스크립트 11**):
`docs/sql/20260929_add_agent_mqtt_status.sql` (적용), `..._rollback.sql` (되돌리기).
기능이 필요로 하는 SQL 이라 공개본에도 들어가는 `docs/sql/` 에 둔다. 배포 반입물을 만들 때 운영 DB 스크립트와 같은 `sql/` 로 모은다.

Alembic 리비전 `c4e8a2f19d3b` 도 같은 컬럼으로 만들었다(`b7c1d9e4f2a8` 다음). 다만 로컬 개발 DB 의 `alembic_version` 은
저장소에 없는 리비전(`cc8f86f77bff`)이라 **개발 DB 에서도 `flask db upgrade` 는 돌지 않는다** — 개발 DB 에도 위 SQL 을 적용했다.

```sql
-- 적용 — 다시 실행해도 된다 (IF NOT EXISTS)
BEGIN;
ALTER TABLE ag_agent
    ADD COLUMN IF NOT EXISTS mqtt_state    VARCHAR(20),
    ADD COLUMN IF NOT EXISTS mqtt_since    TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS mqtt_events   INTEGER,
    ADD COLUMN IF NOT EXISTS mqtt_last_msg TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS mqtt_reason   VARCHAR(120),
    ADD COLUMN IF NOT EXISTS mqtt_raw      VARCHAR(300);
COMMENT ON COLUMN ag_agent.mqtt_state IS 'MQTT 수신 상태 (X-Mqtt-Status). NULL = MQTT 비대상';
COMMIT;

-- 되돌리기
BEGIN;
ALTER TABLE ag_agent
    DROP COLUMN IF EXISTS mqtt_state,
    DROP COLUMN IF EXISTS mqtt_since,
    DROP COLUMN IF EXISTS mqtt_events,
    DROP COLUMN IF EXISTS mqtt_last_msg,
    DROP COLUMN IF EXISTS mqtt_reason,
    DROP COLUMN IF EXISTS mqtt_raw;
COMMIT;
```

적용 명령 (기존 스크립트와 같은 방식):

```bash
docker exec -i mwm-db psql -U <DB 사용자> -d mw -v ON_ERROR_STOP=1 -f /dev/stdin \
    < docs/sql/20260929_add_agent_mqtt_status.sql
```

**순서: SQL 먼저 → 새 앱.** 컬럼은 모두 NULL 허용·기본값 없음이라
- 구 앱은 새 컬럼을 모른 채 그대로 동작한다 → **앱을 멈추지 않고** 적용할 수 있다 (잠금은 순간이다)
- 새 앱을 SQL 없이 띄우면 `ag_agent` 조회가 모두 실패한다 (없는 컬럼) — 순서를 지킨다
- 되돌릴 때는 **구 앱으로 먼저** 바꾼 뒤 rollback SQL

폐쇄망 배포 런북(공개본에는 없다)의 앱 교체 단계에 DB 스크립트 11 로, 롤백 절에 되돌리기로 넣었다.

---

## 7. 테스트 (TDD — HOWTO_018)

먼저 쓰고 실패를 본 뒤 구현한다.

| 대상 | 확인 |
| :--- | :--- |
| 파서 (단위) | §2.2 예시 4개, reason 안의 `=`, 필드 누락, 모르는 state → `unknown`+원문, 대소문자, 빈 값·공백·쓰레기 → 예외 없음, 음수·미래 시각, 긴 값 자르기 |
| 폴링 API | 헤더 있음 → 6컬럼 저장 / 있다가 없어짐 → NULL / BOOT → 안 건드림 / 미승인 → 저장 안 함 / 쓰레기 헤더여도 200 과 명령 응답 |
| 집계·목록 | 모수 = 승인 ∧ OnLine ∧ 헤더: OffLine·NULL·미승인 제외, state 별 수, 정렬 순서 |
| 화면 | `/monitor/mqtt_agent_stat` JSON, Agent 목록 배지, **`reason` 의 `<script>` 가 이스케이프됨**, 비대상은 빈칸 |
| SQL | 빈 테스트 DB 에 적용 → 두 번 적용 → rollback → 다시 적용. 적용 후 구 앱 이미지로 Agent 목록이 뜨는지 |

마지막으로 로컬 스택 + 실제 Agent 로 확인: 대시보드 카드, Agent 목록 배지, 브로커를 멈췄을 때 `unstable` 로 바뀌는지.

---

## 8. 하지 않는 것

- **상태 이력** — 최신값만 둔다. 끊김 추이가 필요해지면 별도 테이블로
- **probe (end-to-end 수신 판정)** — 앱이 주기적으로 `cmd/broadcast/req` 에 확인용 메시지를 보내 `last_msg` 로 판정하는 안.
  Agent 가 받은 메시지를 모두 명령으로 실행하므로 Agent 쪽 작업이 먼저 필요하다 (mwagent 미구현)
- **알림(메일)** — 경고 상태 알림은 이 문서 범위 밖
- 브로커 주소·구독 토픽 — Agent 가 보내지 않는다 (토픽은 고정, 주소는 BOOT 응답으로 앱이 준 값)

---

## 9. 검증 결과 (2026-09-29)

### 9.1 테스트

| 파일 | 수 | 내용 |
| :--- | ---: | :--- |
| `tests/test_unit_mqtt_status.py` | 48 | 파서·집계·정렬 (§7 첫 줄 전부) |
| `tests/test_api_agent_mqtt_status.py` | 13 | 폴링 저장·비우기·BOOT·v4·미승인·쓰레기 헤더, 대시보드 모수·정렬·로그인, Agent 목록 배지·이스케이프·필터, 대시보드 JS |

전체 283 통과 (기존 222 + 61). flake8 위반은 `main` 보다 2건 줄었다.

구현 중 테스트로 잡은 것: `'²'` 처럼 `isdigit()` 이 참인데 `int()` 가 실패하는 값, `events` 가 INTEGER 범위를 넘으면
UPDATE 가 실패해 **폴링 응답까지 깨지는** 경우 (→ 2³¹-1 초과는 NULL).

### 9.2 SQL

`mw_test` 에서 적용 → 재적용 → 되돌리기 → 다시 되돌리기 → 재적용 모두 오류 없음.
개발 DB(`mw`)에는 **구 앱이 떠 있는 채로** 적용했고, 구 앱의 로그인·Agent 폴링이 그대로 200 이었다.

### 9.3 실제 Agent (mwagent `c28bae7`, `devhost01_ops_J`, 폴링 80초)

| 시각 | 한 일 | 앱에 저장된 값 |
| :--- | :--- | :--- |
| 15:29 | 새 앱 기동 후 첫 폴링 | `connected;since=14:43:14;events=0` (last_msg 없음) |
| 15:31:24 | `command_sender=MQTT` 로 `Read.domain.xml` 1건 | 15:31:23 수행 완료 → 다음 폴링에 `last_msg=15:31:23` |
| 15:33:07 | 브로커(`mqtt-broker`) 중지 | 15:33:57 폴링: `unstable;since=15:33:06;events=1;reason=rc=32109 Connection lost` |
| 15:34:36 | 브로커 재시작 | 15:35:17: `connected;since=15:35:14;events=1` → 15:36:38: `events=0` (60초 뒤 리셋) |
| 15:39 | Agent 0000.0010.0002 로 재기동 (BOOT → 1초 뒤 폴링) | `connected;since=15:39:15;events=0` — 재기동으로 last_msg 는 비워짐 |
| 16:53:28 | Agent 를 `mqtt_enabled=false` 로 재기동 | 16:53:30 첫 폴링부터 헤더 없음 → **6컬럼 NULL**, 대시보드·Agent 목록 MQTT 필터에서 빠짐 |
| 16:56 | `mqtt_enabled=true` 로 되돌려 재기동 | 16:56:08 첫 폴링: `connected;since=16:56:08;events=0` → 다시 대상 |

`/monitor/mqtt_agent_stat`·대시보드·Agent 목록 배지(`불안정`, 툴팁에 사유)가 각 단계 값을 그대로 보였다.
