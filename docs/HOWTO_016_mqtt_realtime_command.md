# HOWTO_016: MQTT 실시간 Command 발송 구현 가이드

> 상태: **구현 완료**. 실제 Agent 로 full loop 검증 완료 (발행 → MQTT push → 실행 2초 → 결과 수신 → COMPLITED).
> 관련 문서: [agent_command_system.md](agent_command_system.md), [HOWTO_012](HOWTO_012_command_master_api.md), [SPEC_022](SPEC_022_command_result_api.md)

## 1. 개요

현재 Command 전달은 **Agent 폴링(REST)** 방식이다. Agent 가 주기적으로
`GET /api/v1/command/<agent_id>/...` 를 호출해 `CREATE` 상태 Command 를 가져간다
(`app/sqls/agent.py:739` `send_commands`). 따라서 명령 생성 → 실제 수행까지
**폴링 주기만큼 지연**된다.

본 작업은 MQTT 브로커를 통해 서버가 Agent 에게 명령을 **push** 하여 지연을 제거한다.

핵심 설계 원칙 3가지:

1. **폴링을 대체하지 않고 보완한다.** MQTT 발행 실패 시 기존 REST 폴링으로 자동 fallback.
2. **결과 보고는 계속 REST 를 쓴다.** 브로커 ACL 이 Agent 에게 write 권한을 주지 않으므로
   (§3.2) MQTT 는 **하향(서버→Agent) 단방향 전용**이다.
3. **기존 Kafka 발송 경로를 그대로 답습한다.** 이미 `command_sender = KAFKA` 분기가
   존재하므로(`app/sqls/agent.py:490`) 구조를 새로 만들 필요가 없다.

---

## 2. 브로커 현황 (검증 완료)

`mqtt-broker` 컨테이너는 **이 repo 의 `docker-compose.yml` 이 아니라 별도 compose
프로젝트**에서 기동된다.

| 항목 | 값 |
|---|---|
| 이미지 | `eclipse-mosquitto:2.0` |
| 컨테이너 | `mqtt-broker` |
| compose 파일 | `~/projects/mqtt/docker-compose.yml` (project: `mqtt`) |
| 설정 파일 | `~/projects/mqtt/broker/config/{mosquitto.conf,acl,passwd}` |
| 리스너 | `1883/tcp` (호스트 전체 바인딩, TLS 없음) |
| 프로토콜 | MQTT 5 지원 확인 (`p5` 로 접속 로그 기록됨) |

브로커 측 주요 설정(`mosquitto.conf`):

```
allow_anonymous false
persistence true                      # 세션/오프라인 큐 영속화
persistent_client_expiration 7d       # 오프라인 Agent 세션 보존
max_queued_messages 100               # 세션당 큐 상한
max_inflight_messages 20
```

→ **오프라인 Agent 도 재접속 시 큐에 쌓인 명령을 받는다.** 이것이 폴링 대비 가장 큰 이점이다.

---

## 3. 인증 / 권한 (검증 완료)

### 3.1 컨트롤러(서버) 계정

```
id : central
pw : (git 에 두지 않는다 — 호스트 `.env` 의 MQTT_PASSWORD 참조, §6)
```

ACL: `topic write cmd/#` — **발행 전용, 읽기 권한 없음.**

브로커 계정 정보의 원본은 `~/projects/mqtt/broker/config/passwd` 이고,
서버가 쓰는 값은 추적되지 않는 `.env` 에만 둔다.

### 3.2 Agent 계정 패턴

`acl` 파일의 pattern 규칙:

```
pattern read  cmd/%u/req          # %u = 접속 username
pattern read  cmd/broadcast/req
```

여기서 도출되는 **가장 중요한 사실 2가지**:

1. **Agent 의 MQTT username == `ag_agent.agent_id`** 이다.
   `passwd` 파일에 등록된 사용자 중 `devhost01_ops_J` 는 DB `ag_agent.agent_id`
   값과 정확히 일치한다. 따라서 토픽은 `cmd/{ag_agent.agent_id}/req`.
   (Kafka 경로도 이미 `'t_' + ag.agent_id` 를 쓴다 — `app/sqls/agent.py:492`)
2. **Agent 는 어떤 토픽에도 write 권한이 없다.** `resp` 성격의 토픽은 ACL 에 아예
   없다. 따라서 결과 보고를 MQTT 로 옮기려면 **브로커 ACL/passwd 변경이 선행**되어야
   한다. 본 계획의 범위 밖이며, 결과는 기존 `POST /api/v1/command/result` 를 유지한다.

또한 `cmd/broadcast/req` 가 이미 정의되어 있어, **브로드캐스트 명령을 N건 발행 대신
1건 발행으로 처리**할 수 있다.

### 3.3 등록된 계정

| username | 용도 |
|---|---|
| `central` | 컨트롤러 (발행 전용) |
| `ops` | `$SYS/#` 읽기 (운영자 CLI) |
| `health` | `$SYS/broker/uptime` 읽기 (compose healthcheck) |
| `agent-001`, `agent-002` | 테스트 Agent |
| `devhost01_ops_J` | 실제 Agent (DB `ag_agent` 등록됨) |

---

## 4. 접속 테스트 결과

**검증 환경: `mwm-base` 컨테이너 내부** (`--network mw_app_default`,
python 3.12.4 / paho-mqtt 2.1.0, MQTT 5, `clean_start=True`).
이 프로젝트는 호스트가 아니라 Docker 에서 test/실행한다(§Step 0).

재현 명령:

```bash
docker run --rm --network mw_app_default \
  -e MQTT_BROKER_HOST=172.26.0.1 -e MQTT_USERNAME=central \
  -e MQTT_PASSWORD="$(grep '^MQTT_PASSWORD=' .env | cut -d= -f2-)" \
  -v "$(pwd)/config.py":/app/config.py:ro \
  mwm-base python3 -c '...'
```

| 테스트 | 결과 |
|---|---|
| `central` 접속 | **CONNACK Success** (server props: `ReceiveMaximum=20`, `TopicAliasMaximum=10`) |
| `cmd/{agentId}/req` 발행 (QoS 0/1) | **성공** |
| `cmd/broadcast/req` 발행 (QoS 1) | **성공** |
| MQTT5 속성 동반 발행 (`MessageExpiryInterval`, `ContentType`, `CorrelationData`) | **성공** |
| `other/topic` 발행 | **PUBACK `Not authorized`** — ACL 정상 동작 |
| `cmd/#` 구독 | **SUBACK 은 `Granted QoS 1`** 이지만 **메시지 전달 0건** |

### 4.1 주의: SUBACK 을 권한 판정에 쓰면 안 된다

Mosquitto 는 read 권한이 없어도 SUBACK 을 `Granted` 로 응답하고, **전달 시점에
필터링**한다. 즉 "구독 거부"는 SUBACK 이 아니라 무전달로 나타난다.
→ 서버 구현에서 구독은 아예 시도하지 않는다.

### 4.2 PUBACK reason code 를 배달 신호로 활용할 수 있다

QoS 1 발행 시 reason code 가 유용하게 갈린다.

| 발행 토픽 | PUBACK reason code | 의미 |
|---|---|---|
| `cmd/devhost01_ops_J/req` | `Success` | 해당 Agent 의 **세션이 브로커에 존재** (접속 중 or 오프라인 큐에 적재됨) |
| `cmd/agent-001/req` | `Success` | 동일 |
| `cmd/broadcast/req` | `Success` | 동일 |
| `cmd/nobody/req` | `No matching subscribers` | 구독자·세션 없음 → **명령이 버려짐** |

`Success` 가 돌아온다는 것은 이미 영속 세션(durable subscription)이 브로커에
존재한다는 뜻이며, 실제로 `persistence` 파일(`broker/data/mosquitto.db`)이 존재한다.
→ **`No matching subscribers` 를 "MQTT 로 전달 불가"로 판정하고 REST fallback 처리**하면
명령 유실을 막을 수 있다. (설계 결정 D4, §7)

### 4.3 Agent 측 payload 계약 (실제 Agent 검증으로 확인)

살아있는 Agent(`devhost01_ops_J`)로 full loop 을 검증하며 확인한 사항이다.
**REST 폴링 payload 를 그대로 보내면 동작하지 않는다.**

#### (1) `cmdId` 가 필요하다

Agent 는 MQTT 수신 시 `cmdId` 로 중복 실행을 걸러낸다(같은 값을 다시 받으면 무시).
REST 폴링 응답에는 없는 필드이므로 MQTT 경로에서만 추가한다.
값은 `{command_id}_{repetition_seq}` — 발행 key 와 같다.

#### (2) 문자열 필드에 JSON `null` 을 보내면 명령이 조용히 사라진다

Agent(Java)의 `ReadPlainFile.getFileFullName()` 은 null 체크 없이
`commandVo.getAdditionalParams().length()` 를 호출한다.

```java
String file_name = commandVo.getTargetFileName();
if (commandVo.getAdditionalParams().length() > 0) {   // additional_params 가 null 이면 NPE
    file_name += "." + commandVo.getAdditionalParams();
}
```

`AgCommandMaster.additional_params` 는 nullable 이고, `None` 은 `json.dumps` 에서
`null` 로 직렬화된다. 그러면 Agent 는 `NullPointerException` 을 내고,
**`ReadFile.execute()` 가 예외를 내부에서 삼킨 뒤 결과를 채우지 않고 반환**한다.
즉 결과 보고(`sendResult`)조차 호출되지 않아 **아무 로그도 남지 않고 명령만 사라진다.**
(브로커·토픽·QoS 는 모두 정상이었고 Agent 의 dispatch 까지 들어갔다)

→ 발행 측에서 `additional_params` / `target_object` 의 `None` 을 `''` 로 보정한다.
이 보정 하나로 full loop 이 통과했다(발행 → Agent 실행 2초 → 결과 수신 → `COMPLITED`).

`additional_params` 가 null 일 때 터지는 곳은 `ReadPlainFile` 뿐이 아니다.

| Agent 클래스 | 위치 | 증상 |
|---|---|---|
| `ReadPlainFile` | `:24`, `:36` | `.length()` 직접 호출 → NPE (2곳) |
| `ExtractLog` | `:35-38` | `JSONParser().parse(null)` → NPE |
| `ReadFullPathFile` | `:40` | null 안전 (경로 검증에서 거부) |
| `ExeText` / `ExeScript` / `ExeShell` | — | null 안전 (조건 분기 또는 예외 포착) |

#### `target_file_path` / `target_file_name` 은 보정하지 않는다

이 둘은 NPE 를 내지 않지만 **더 조용히 망가진다.** Java 의 문자열 연결은 `null` 을
`"null"` 문자열로 바꾸므로, `ReadPlainFile.java:28` 의
`getTargetFilePath() + file_name` 이 `"nulldomain.xml"` 같은 경로를 만들어
`FileNotFoundException` 으로 빠진다. (`ExeShell:47-48`, `ExeScript:49-50`,
`DownloadFile:74,87` 도 같은 성격)

그럼에도 **보정하지 않는 이유**: 이 두 필드는 `null` 이 "미지정"의 의미를 갖는
command_class 가 있고, `''` 로 바꾸면 `"/some/path/" + ""` 가 되어 디렉터리를
파일로 읽으려 하는 등 다른 오동작을 만든다. 보정은 `additional_params` /
`target_object` 두 필드로 좁게 유지한다.

> ⚠️ **REST 폴링 경로도 같은 위험을 갖는다.** `send_commands`
> (`app/sqls/agent.py`)는 DB 값을 그대로 내려주므로 `additional_params` 가 NULL 인
> 명령은 REST 로도 NPE 를 유발한다. UI 로 만든 명령은 빈 문자열 `''` 이 들어가
> 지금까지 드러나지 않았을 뿐이다. 근본 수정은 Agent 쪽 null 체크이며
> **mwagent 저장소 담당의 판단이 필요하다**(§11-8).

#### (3) `command_class` 화이트리스트는 없다

Agent 의 MQTT 핸들러는 `command_class` 값으로 `mwagent.order.{command_class}` 를
동적 로딩한다. 별도 허용 목록이 없으므로 해당 클래스가 Agent 에 존재하면 동작한다.
`ag_command_type` 등록 여부와 Agent 의 동적 로딩은 무관하다.

---

---

## 5. 네트워크 제약 — 반드시 먼저 해결해야 함

브로커와 앱이 **서로 다른 docker 네트워크**에 있다.

| 컨테이너 | 네트워크 | IP |
|---|---|---|
| `mqtt-broker` | `mqtt_default` | 192.168.96.2 |
| `mwm-app` | `mw_app_default` | 172.26.0.6 |

`mwm-app` 컨테이너 안에서 확인한 도달성:

| 대상 | 결과 |
|---|---|
| `mqtt-broker` (DNS) | 이름 해석 실패 |
| `192.168.96.2:1883` (브로커 직접 IP) | timeout |
| **`172.26.0.1:1883`** (mw_app_default 게이트웨이) | **접속 성공** |
| `172.17.0.1:1883` (docker0) | 접속 성공 |

브로커가 `1883:1883` 으로 호스트에 포트를 노출하고 있으므로 **게이트웨이 IP 경유로
접근**된다. 이 repo 의 `docker-compose.yml` 은 이미 `extra_hosts` 에 `172.26.0.1` 을
쓰는 관례가 있다(`docker-compose.yml:39-43`).

### 권장 조치 (택 1)

- **(A) 게이트웨이 경유 — 권장, 변경 최소.**
  `mwm-app` 서비스 environment 에 `MQTT_BROKER_HOST: 172.26.0.1` 추가.
- **(B) 네트워크 연결.** `mqtt_default` 를 external network 로 `mwm-app` 에 붙이고
  호스트명 `mqtt-broker` 사용. 더 깔끔하지만 두 compose 프로젝트 간 결합이 생긴다.

> 운영 환경에서는 평문 1883 이 호스트 전체에 열려 있는 점도 별도 검토 대상이다
> (TLS 8883 + `mTLS_based_auth.md` 참고).

---

## 6. 저장된 설정 (이미 반영됨)

### `config.py` (파일 끝에 추가됨)

```python
MQTT_ENABLED          = os.getenv('MQTT_ENABLED', 'True') ...
MQTT_BROKER_HOST      = os.getenv('MQTT_BROKER_HOST', 'localhost')
MQTT_BROKER_PORT      = int(os.getenv('MQTT_BROKER_PORT', '1883'))
MQTT_USERNAME         = os.getenv('MQTT_USERNAME', 'central')
MQTT_PASSWORD         = os.getenv('MQTT_PASSWORD', '')   # 코드에 비밀번호 두지 않음
MQTT_CLIENT_ID_PREFIX = os.getenv('MQTT_CLIENT_ID_PREFIX', 'controller')
MQTT_KEEPALIVE        = int(os.getenv('MQTT_KEEPALIVE', '60'))
MQTT_RECONNECT_DELAY      = int(os.getenv('MQTT_RECONNECT_DELAY', '60'))       # 재시도 주기(고정)
MQTT_LOG_THROTTLE_SECONDS = int(os.getenv('MQTT_LOG_THROTTLE_SECONDS', '3600')) # 로그 억제 창
MQTT_CMD_TOPIC        = os.getenv('MQTT_CMD_TOPIC', 'cmd/{agent_id}/req')
MQTT_BROADCAST_TOPIC  = os.getenv('MQTT_BROADCAST_TOPIC', 'cmd/broadcast/req')
MQTT_QOS              = int(os.getenv('MQTT_QOS', '1'))
MQTT_MESSAGE_EXPIRY   = int(os.getenv('MQTT_MESSAGE_EXPIRY', '3600'))
MQTT_PUBLISH_TIMEOUT  = float(os.getenv('MQTT_PUBLISH_TIMEOUT', '5'))
```

### `.env` (신규, git 추적 제외 — `.gitignore:115`)

실제 비밀번호는 여기에만 둔다. 템플릿은 `.env.example` (추적 대상, 비밀번호 공란).

```
MQTT_ENABLED=True
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_USERNAME=central
MQTT_PASSWORD=<실제 비밀번호>          # git 에 커밋하지 않는다
```

#### `.env` 값이 컨테이너까지 전달되는 경로 (검증 완료)

`.env` 는 **이미지에 들어가지 않는다.** `Dockerfile.app` 은 `app/`, `config.py`,
`run.py`, `gunicorn_config.py` 만 COPY 한다(컨테이너 내 `/app/.env` 부재 확인).
따라서 컨테이너 안의 `load_dotenv()` 는 아무것도 읽지 못한다.

전달은 **`docker compose` 의 변수 치환**으로 이뤄진다. compose 는 프로젝트 디렉터리의
`./.env` 를 자동으로 읽어 `${VAR}` 를 치환한다 — `docker compose config` 로
실제 비밀번호가 치환되는 것을 확인했다.

```
.env (호스트, git 제외)
   └─ docker compose 가 ${MQTT_PASSWORD} 치환
        └─ docker-compose.yml 의 mwm-app: environment:
             └─ 컨테이너 환경변수
                  └─ config.py 의 os.getenv()
```

즉 `.env` 는 **compose 변수 공급원**이고, 컨테이너 안에서 파일로 읽히는 게 아니다.
따라서 Step 9 의 compose `environment:` 블록이 **필수**다. 빠뜨리면 컨테이너에서
`MQTT_PASSWORD` 가 비어 publisher 가 생성되지 않고 조용히 REST 폴링만 동작한다.

> `MQTT_BROKER_HOST` 기본값이 `localhost` 인 이유: 호스트 쪽 도구(`mosquitto_pub` 등)
> 에서 바로 쓰이게 하고, 컨테이너는 compose environment 로 `172.26.0.1` 로 덮어쓴다(§5-A).
>
> ⚠️ `config.py` 는 이미지에 baked-in 이다(`mwm-app` 에 bind mount 없음).
> 반영에는 이미지 재빌드가 필요하다(§Step 0).

### 6.1 MQTT 사용여부 스위치 `MQTT_ENABLED` (검증 완료)

```python
# config.py — 기본 False (opt-in)
MQTT_ENABLED = os.getenv('MQTT_ENABLED', 'False').lower() in ('true', '1', 'yes')
```

기본값을 **False** 로 둔다. 이유:

- 브로커가 이 프로젝트 compose 밖에 있고 기본 네트워크로는 닿지 않는다(§5).
  기본 True 면 기존 배포가 전부 접속 실패 재시도를 돌게 된다.
- MQTT 는 폴링을 보완하는 선택 기능이다. 켜는 쪽이 명시적이어야 한다.

허용 값은 `true` / `1` / `yes` (대소문자 무관). 그 외 전부 False.

#### 비활성 시 보장 사항

`MQTT_ENABLED=False` 이면 **MQTT 관련 활성화를 일절 하지 않는다.**

| 항목 | 비활성 시 |
|---|---|
| `paho` import | **안 함** (지연 import 이므로 `sys.modules` 에도 안 올라옴) |
| 클라이언트 객체 생성 | 안 함 (`mqtt_publisher is None`) |
| 백그라운드 네트워크 스레드 | **안 뜸** (`loop_start()` 미호출) |
| 브로커 접속 / 60초 재시도 | 안 함 |
| 발행 시도 | 안 함 — `command_sender=MQTT` 명령이 있어도 Step 5 분기가 `and mqtt_publisher` 에서 차단 |
| 연결성 로그 | 기동 시 INFO 1건뿐 |
| `paho-mqtt` 의존성 | **불필요** — 미설치 이미지에서도 정상 기동 |

마지막 항목이 중요하다. 지연 import 덕분에 **MQTT 를 끄면 paho 가 없는 이미지에서도
앱이 그대로 뜬다.** 의존성 추가와 기능 활성화를 분리할 수 있다.

`command_sender=MQTT` 로 만들어진 명령은 비활성 상태에서 status `CREATE` 로 남아
**기존 REST 폴링으로 정상 수행된다**(D4). 즉 스위치를 끄는 것만으로 기능 장애가 되지 않는다.

#### 검증 결과 (컨테이너 실측)

| # | 조건 | 이미지 | 결과 |
|---|---|---|---|
| A | `MQTT_ENABLED` 미설정 | `mwm-app` (paho 없음) | `False` 로 해석, paho import 안 함, 스레드 1→1, 발행 시도 0 — **전 항목 PASS** |
| B | `MQTT_ENABLED=True`, paho 없음, 가드 미보강 | `mwm-app` | **`ModuleNotFoundError` 로 기동 실패** ← Step 2 에서 `ImportError` 처리 필요 |
| B′ | 위와 동일, 가드 보강 후 | `mwm-app` | ERROR 로그 1건 + `publisher=None`, **기동 계속** |
| C | `MQTT_ENABLED=True`, paho 있음 | `mwm-base` | publisher 정상 생성 |
| D | `MQTT_ENABLED=True`, `MQTT_PASSWORD` 공란 | `mwm-base` | WARNING 1건 + `publisher=None`, 기동 계속 |

#### 운영 설정

`docker-compose.yml` 에서는 켜는 것을 명시한다(Step 9).

```yaml
      MQTT_ENABLED: ${MQTT_ENABLED:-False}
```

끄고 싶으면 `.env` 에서 `MQTT_ENABLED=False` 로 두거나 항목을 지우면 된다.
**재빌드 없이 컨테이너 재기동만으로 전환된다**(환경변수이므로).

---

---

## 7. 설계 결정

| # | 결정 | 근거 |
|---|---|---|
| **D1** | 전송 방식 선택은 신규 컬럼이 아니라 **기존 `AgCommandMaster.command_sender`** 에 `MQTT` / `SERVER_N_MQTT` 를 추가한다 | Kafka 와 동일 구조. UI/폼 로직 재사용(`app/views/agent.py:307`) |
| **D2** | `AgCommandDetail.command_status` 에 `MQTT` / `MQTT_FAILED` 추가 | `KAFKA`/`KAFKA_FAILED` 쌍과 대칭 |
| **D3** | 발행 성공 → status `MQTT`. `send_commands` 는 `CREATE` 만 조회하므로 **폴링으로 중복 전달되지 않는다** | `app/sqls/agent.py:745` |
| **D4** | 발행 실패 또는 PUBACK `No matching subscribers` → status 를 **`CREATE` 로 남겨 REST 폴링 fallback** | 명령 유실 방지. `MQTT_FAILED` 는 "fallback 도 불가"인 경우에만 |
| **D5** | `SERVER_N_MQTT` 는 기본 제공하지 않거나 문서에 위험을 명시 | status 를 `CREATE` 로 두고 발행까지 하면 Agent 가 push + poll 로 **2회 실행**한다. Agent 측 `(command_id, repetition_seq)` 멱등 처리가 전제 |
| **D6** | 발행은 **DB commit 이후**에 수행한다 | commit 전에 발행하면 Agent 가 결과를 먼저 POST 해 `AgCommandDetail` 부재로 FK 위반/누락이 발생. 현재 Kafka 코드는 insert 전에 발행하는 구조라 이 순서를 그대로 베끼면 안 된다 |
| **D7** | 브로드캐스트는 1차 구현에서 **Agent 별 개별 발행**으로 한다 | `AgCommandDetail` 이 Agent 별로 필요하고 `repetition_seq`·`result_hash` 가 Agent 별로 다름. `cmd/broadcast/req` 최적화는 payload 규격 변경이 필요해 2차 과제 |
| **D8** | MQTT payload 는 REST 폴링 응답과 **동일한 dict 구조**를 쓰되 **두 가지를 보정**한다 — `cmdId` 추가, `additional_params`/`target_object` 의 `None` 을 `''` 로 변환 | Agent 파서 재사용이 기본. 다만 Agent 의 MQTT 경로는 `cmdId` 로 중복 실행을 걸러내고, Java 측이 null 체크 없이 `.length()` 를 호출해 JSON null 이면 NPE 로 명령이 조용히 버려진다 (§4.3) |
| **D9** | 결과 수신은 REST 유지 | §3.2 ACL 제약 |
| **D10** | `MQTT_ENABLED` 기본값은 **False**(opt-in). 비활성 시 paho import 조차 하지 않는 지연 import 구조 | 브로커가 기본 네트워크에서 안 닿으므로(§5) 기본 True 면 기존 배포가 전부 재시도를 돌게 된다. 지연 import 로 **의존성 추가와 기능 활성화를 분리**한다 (§6.1) |
| **D11** | `command_sender` 가 `MQTT` 면 `periodic_type` 을 **무조건 `IMMEDIATE`(즉시작업)로 강제**한다 | MQTT 의 목적은 폴링 지연 제거다. `ONETIME`/`PERIODIC` 은 APScheduler 가 나중에 상세를 만들므로 "실시간 push" 가 성립하지 않는다. 또 `IMMEDIATE` 만이 `create_command_detail()` 을 동기 호출하는 경로다 (§Step 3.1) |

### 7.1 상태 전이

```
                       ┌─ 발행 성공 ──→ MQTT ──(POST result)──→ COMPLITED / FAILED
create_command_detail ─┤
                       └─ 발행 실패 ──→ CREATE ──(REST polling)──→ SENDED ──→ COMPLITED / FAILED
```

---

## 8. 구현 계획

### Step 0. 의존성 및 이미지 빌드

`requirements.txt` 에 추가 **(반영 완료)**:

```
paho-mqtt==2.1.0
```

이 프로젝트는 **build / test / 실행을 모두 Docker 로 한다.** 호스트에 venv 를 만들지
않는다. 빌드는 2단계이며 `requirements.txt` 는 **base 이미지**에서 설치된다
(`Dockerfile.base`), `Dockerfile.app` 은 소스코드만 COPY 한다.
따라서 **의존성을 추가하면 base 부터 다시 빌드해야 한다.**

```bash
docker build -t mwm-base -f Dockerfile.base .   # requirements.txt 설치
docker build -t mwm-app  -f Dockerfile.app  .   # 소스코드 COPY (코딩 완료 후)
docker compose up -d mwm-app
```

`docker-compose.yml` 의 `build` 는 `Dockerfile.app` 만 가리키므로
(`docker build -t mwm-app -f Dockerfile.app .` 은 base 를 갱신하지 않는다) base 재빌드는 수동이다.
절차 상세는 [HOWTO_001](HOWTO_001_create_docker_image.md).

**진행 상태**

| 항목 | 상태 |
|---|---|
| `requirements.txt` 에 `paho-mqtt==2.1.0` 추가 | 완료 |
| `mwm-base` 재빌드 | **완료** (paho 2.1.0 / python 3.12.4 확인) |
| `mwm-app` 재빌드 | 보류 — Step 1~9 코딩 완료 후 |

base 에 paho 가 들어갔으므로 **소스 코딩 전에도 `mwm-base` 컨테이너로 연동 검증이
가능하다.** `config.py` 만 마운트하면 실제 실행 환경(python 3.12 / 앱 네트워크)에서
확인된다.

```bash
docker run --rm --network mw_app_default \
  -e MQTT_BROKER_HOST=172.26.0.1 -e MQTT_BROKER_PORT=1883 \
  -e MQTT_USERNAME=central \
  -e MQTT_PASSWORD="$(grep '^MQTT_PASSWORD=' .env | cut -d= -f2-)" \
  -v "$(pwd)/config.py":/app/config.py:ro \
  mwm-base python3 /path/to/verify.py
```

이 방식으로 확인된 항목: `config.py` 의 `MQTT_*` 로딩, `/app/.env` 부재,
`MQTT_PASSWORD` 환경변수 주입, `172.26.0.1:1883` TCP 도달, CONNACK Success,
허용 토픽 발행 + PUBACK, 비허용 토픽 `Not authorized`, 미접속 `rc=4` 및
`is_published()` RuntimeError — **전 항목 PASS**.

### Step 1. Publisher 클래스 — `app/mqtt/mqtt_publisher.py` (신규)

`app/kafka/kafka_producer.py` 와 **동일한 계약**(`send_message(topic, message, key) -> 1 | -1`)을
유지해 호출부 수정을 최소화한다.

```python
class Publisher4Mqtt:
    def __init__(self, host, port, username, password, client_id_prefix, keepalive): ...
    def send_message(self, topic, message, key='', expiry=None) -> int: ...
    def close(self): ...
```

구현 요점:

- `mqtt.Client(CallbackAPIVersion.VERSION2, protocol=MQTTProtocolVersion.MQTTv5)`
- **`client_id` 는 `controller-{hostname}-{pid}`** 형식으로 조립한다.

  ```python
  import os, socket
  client_id = f"{client_id_prefix}-{socket.gethostname()}-{os.getpid()}"
  # 예) controller-b94d0b491e2c-42
  ```

  - 목적은 **같은 서버의 프로세스 간 충돌 방지**다. 같은 client_id 로 두 번 접속하면
    브로커가 먼저 붙어 있던 쪽을 끊어버리므로(MQTT 스펙) 조용한 장애가 된다.
  - **Docker 환경에서는 두 성분이 모두 필요하다.** `mwm-app` 컨테이너 실측:

    ```
    PID  PPID  COMMAND          hostname = b94d0b491e2c
      1     0  supervisord
      8     1  gunicorn (master)
     11     8  gunicorn (worker)   -> controller-b94d0b491e2c-11
    ```

    - `pid` : 컨테이너 **안**의 프로세스들(gunicorn master/worker, APScheduler,
      일회성 스크립트)을 구분한다.
    - `hostname` : **PID 네임스페이스가 컨테이너별로 분리**되어 있어 같은 호스트의
      다른 컨테이너도 pid 1·8·11 을 그대로 갖는다. 즉 pid 만으로는 같은 서버에서
      충돌할 수 있고, 컨테이너 ID 인 hostname 이 이를 막는다.
      (검증용 일회성 컨테이너에서 `pid=1` 로 접속되는 것을 실제로 확인)
  - **생성 시점은 `Publisher4Mqtt.__init__` 안**이어야 한다. config 모듈 레벨에서
    `os.getpid()` 를 평가하면 fork 기반 배포(`preload_app=1`)에서 모든 워커가
    부모 프로세스에서 계산된 같은 문자열을 물려받아 충돌한다.
- **접속은 `connect_async()` + `loop_start()`** (§Step 1.1)
- `clean_start=True` (컨트롤러는 세션 보존 불필요)
- 발행 시 MQTT5 properties: `MessageExpiryInterval = MQTT_MESSAGE_EXPIRY`,
  `ContentType='application/json'`, `CorrelationData = key.encode()`
- **QoS 1 + `wait_for_publish(timeout=MQTT_PUBLISH_TIMEOUT)`** 로 PUBACK 확인.
  `on_publish` 콜백에서 reason code 를 보관해 `No matching subscribers` 를 구분
- 미접속/타임아웃/예외는 **모두 `-1` 반환하고 로그만 남긴다.** 명령 생성 트랜잭션을
  깨뜨리지 않는 것이 우선 (D4 fallback 이 받아준다)
- ⚠️ `app/kafka/kafka_producer.py` 의 `send_message` 를 호출부에서 `sendMessage` 로
  잘못 쓴 버그(`app/sqls/agent.py:506`)가 있다. **이 오타를 복사하지 말 것.**

---

### Step 1.1 접속 재시도 정책 (검증 완료)

요구사항 3가지 — ① 기동 시 브로커 없어도 무한 재시도 ② 운행 중 단절돼도 무한 재시도
③ 재시도 로그 폭주 금지(60초 try, 1시간 단위 로그) — 를 아래 조합으로 만족시킨다.

```python
client.reconnect_delay_set(min_delay=MQTT_RECONNECT_DELAY,
                           max_delay=MQTT_RECONNECT_DELAY)   # 60초 고정
client.connect_async(host, port, keepalive=MQTT_KEEPALIVE, clean_start=True)
client.loop_start()
```

#### 핵심: `connect()` 가 아니라 `connect_async()` 를 써야 한다

| | `connect()` | `connect_async()` |
|---|---|---|
| 브로커 다운 시 | **예외 발생** → 앱 기동 실패/지연 | 즉시 반환, 예외 없음 |
| 재시도 | 직접 구현 필요 | `loop_start()` 스레드가 자동 |

실측 결과:

- `connect_async()` 는 브로커가 없어도 **예외를 던지지 않는다** → `app/__init__.py`
  import 가 막히지 않으므로 요구사항 ①이 코드 없이 충족된다.
- **최초 접속이 한 번도 성공하지 못한 상태에서도 재시도가 계속 돈다.**
  (죽은 포트 대상 13초간 7회 시도, 간격 정확히 `min_delay`)
- `min_delay == max_delay` 로 두면 backoff 없이 **정확히 60초 고정 주기**가 된다.
  (기본값은 1→2→4→…→120초 지수 backoff 이므로 반드시 명시할 것)
- 운행 중 단절 → 복구 시나리오(실제 브로커 대상, TCP 프록시 차단으로 재현):
  단절 감지 → 60초 주기 재시도 → 브로커 복귀 시 자동 재접속 → **발행 재개 확인**.
  요구사항 ②도 별도 코드 없이 충족된다.

#### 폭주 원인: `on_disconnect` 가 재시도마다 호출된다

단절 1회에 콜백 1회가 아니다. **재접속 시도가 실패할 때마다 `on_disconnect` 가 다시
호출된다**(실측: 단절 구간에서 2초 간격 재시도 시 DISCONNECT 콜백 2회 연속 관측).
60초 주기면 **시간당 60건**, 하루 1440건이 쌓인다. 콜백에 그냥 `logging.error` 를
넣으면 요구사항 ③이 깨진다.

#### 스로틀: 사건 종류별 1시간 1건 + 억제 건수 요약

```python
class _ThrottledLog:
    """연결성 로그를 사건 종류(key)별로 throttle 창에 1건으로 제한.
    각 key 의 최초 발생은 즉시 통과시켜 장애 인지가 늦어지지 않게 한다."""
    def __init__(self, throttle):
        self.throttle = throttle
        self._last, self._suppressed = {}, {}

    def should_log(self, key):
        now = time.monotonic()
        last = self._last.get(key)
        if last is None or now - last >= self.throttle:
            n = self._suppressed.pop(key, 0)
            self._last[key] = now
            return True, n          # (기록할지, 지난 창에서 억제된 건수)
        self._suppressed[key] = self._suppressed.get(key, 0) + 1
        return False, 0
```

사용:

```python
ok, suppressed = self._log.should_log('connect_fail')
if ok:
    logging.error('MQTT 접속 실패 [%s:%s] rc=%s (직전 1시간 동안 동일 실패 %d건 억제)',
                  host, port, rc, suppressed)
```

사건 key 는 3개로 나눈다.

| key | 기록 위치 | 내용 |
|---|---|---|
| `connect_fail` | `on_connect`(rc≠0) / `on_disconnect` | 접속·재접속 실패 |
| `reconnected` | `on_connect`(rc=0), 단 직전 상태가 단절일 때 | 복구. 단절 지속시간·실패 횟수 동반 |
| `publish_no_conn` | `send_message` 에서 `rc == MQTT_ERR_NO_CONN` | 미접속으로 발행 못 함 → REST fallback |

시뮬레이션으로 확인한 로그 건수:

| 시나리오 | 이벤트 | 로그 |
|---|---|---|
| 브로커 24시간 연속 다운 | 1,440건 | **24건** (시간당 1건, 각 "59건 억제" 표기) |
| 60초 주기 플래핑 12시간 | 720건 | **24건** (실패·복구 각 시간당 1건) |
| 다운 중 명령 1,000건 발행 시도 | 1,000건 | **1건** |

→ **시간당 최대 3건**(사건 종류 수)으로 상한이 걸린다. 억제 건수를 함께 남기므로
정보는 잃지 않는다.

#### 그 외 주의

- **`client.enable_logger()` 를 호출하지 말 것.** paho 는 기본적으로 자체 로그를
  남기지 않는다(실패 7회 동안 출력 0건 확인). 이걸 켜면 재시도마다 DEBUG 가 쏟아져
  스로틀이 무의미해진다. 디버깅 시에만 임시로 켠다.
- ⚠️ **미접속 상태에서 `info.is_published()` / `info.wait_for_publish()` 는
  `RuntimeError` 를 던진다.** (`RuntimeError: Message publish failed: The client is
  not currently connected.`) 반드시 `rc` 를 먼저 확인한다.

  ```python
  info = client.publish(topic, payload, qos=1, properties=props)
  if info.rc != mqtt.MQTT_ERR_SUCCESS:      # MQTT_ERR_NO_CONN == 4
      # 여기서 is_published()/wait_for_publish() 호출하면 예외
      return -1                              # -> D4 REST fallback
  info.wait_for_publish(timeout=MQTT_PUBLISH_TIMEOUT)
  ```
- `MQTT_ENABLED=False` 이거나 `MQTT_PASSWORD` 가 비어 있으면 클라이언트를 아예 만들지
  않는다. 이때 `mqtt_publisher` 는 `None` 이고 전 구간이 REST 폴링으로만 동작한다.
- 브로커가 장기 다운이어도 `command_sender=MQTT` 명령은 D4 에 따라 status `CREATE` 로
  남아 폴링으로 수행된다. **즉 브로커 장애가 기능 장애가 되지 않는다.**

### Step 2. 싱글턴 초기화 — `app/__init__.py`

`kafka_producer` 자리(`app/__init__.py:44-48`) 옆에 배치하고,
`scheduler.start()` 직전(`:127`)에 생성한다.

```python
mqtt_publisher = None

if not app.config.get('MQTT_ENABLED'):
    logging.info('MQTT 비활성화 (MQTT_ENABLED=False) — REST 폴링만 사용')
elif not app.config.get('MQTT_PASSWORD'):
    logging.warning('MQTT_ENABLED=True 이지만 MQTT_PASSWORD 가 비어 있음 — MQTT 비활성화')
else:
    try:
        from .mqtt.mqtt_publisher import Publisher4Mqtt   # 지연 import (§6.1)
        mqtt_publisher = Publisher4Mqtt(
            host=app.config['MQTT_BROKER_HOST'],
            port=app.config['MQTT_BROKER_PORT'],
            username=app.config['MQTT_USERNAME'],
            password=app.config['MQTT_PASSWORD'],
            client_id_prefix=app.config['MQTT_CLIENT_ID_PREFIX'],
            keepalive=app.config['MQTT_KEEPALIVE'],
        )
    except ImportError:
        logging.error('paho-mqtt 미설치 — MQTT 비활성화하고 REST 폴링으로 계속 '
                      '(requirements.txt 반영 후 mwm-base 재빌드 필요)')
    except Exception:
        logging.exception('MQTT publisher 초기화 실패 — REST 폴링으로 계속')
```

⚠️ **`ImportError` 를 반드시 따로 잡아야 한다.** `app/__init__.py` 는 팩토리 없는
모듈 레벨 스크립트라서, 여기서 예외가 나가면 **앱 전체가 기동하지 못한다.**
paho 가 없는 이미지에서 `MQTT_ENABLED=True` 로 띄우면 `ModuleNotFoundError` 로
죽는 것을 실제로 확인했다(§6.1 검증표 B). `except Exception` 만으로도 잡히지만,
원인별 안내 메시지가 달라야 하므로 분리한다.

⚠️ **early-binding 함정**: `app/sqls/agent.py:2` 의 `from app import kafka_producer` 는
import 시점의 `None` 을 그대로 고정한다. MQTT 는 이 패턴을 쓰지 말고
**`import app` 후 `app.mqtt_publisher` 로 접근**하거나 `get_mqtt_publisher()` accessor 를 둔다.

> gunicorn 은 현재 `workers=1, threads=2, preload_app=0`
> (`gunicorn_config.py:13,14,17`) 이라 프로세스당 1 커넥션이면 충분하다.
> `GUNICORN_WORKERS` 를 올리면 APScheduler 와 함께 MQTT 커넥션도 중복 생성되므로,
> 그때는 `post_fork` 훅으로 소유권을 정리해야 한다.

### Step 3. Enum 확장 — `app/models/common.py`

```python
class CommandStatusEnum(enum.Enum):   # :111-117
    ...
    MQTT        = 'MQTT로 전달'
    MQTT_FAILED = 'MQTT 전달 실패'

class TargetToSendEnum(enum.Enum):    # :119-122
    ...
    MQTT         = 'MQTT'
    SERVER_N_MQTT = 'Server and MQTT'   # D5 위험 확인 후 도입
```

`colored_command_status` 색상 매핑에도 추가 (`app/models/common.py:222`):
`'MQTT':'brown', 'MQTT_FAILED':'red'`.

### Step 3.1 `command_sender=MQTT` → `periodic_type=IMMEDIATE` 강제

`command_sender` 가 `MQTT` 로 선택되면 **실행구분(`periodic_type`)은 무조건
`IMMEDIATE`(즉시작업)** 로 설정한다.

근거: `IMMEDIATE` 만이 `after_insert` 훅에서 `create_command_detail()` 을
**동기 호출**하는 경로다(`app/views/agent.py:54-57`). `ONETIME`/`PERIODIC` 은
`job_ag_create_job()` 으로 APScheduler 에 넘겨져 나중에 상세가 생성되므로,
"실시간 push" 라는 MQTT 도입 목적 자체가 성립하지 않는다.

#### (1) 강제 지점 — `before_insert` 훅 (권위 있는 계층)

`app/views/agent.py` 의 기존 `set_interval_type`(`:73-78`) 과 같은 패턴으로 추가한다.

```python
@db.event.listens_for(AgCommandMaster, 'before_insert')
def force_immediate_for_mqtt(mapper, connection, target):
    if target.command_sender and target.command_sender.name in ('MQTT', 'SERVER_N_MQTT'):
        if target.periodic_type != PeriodicTypeEnum.IMMEDIATE:
            logging.info('command_sender=%s -> periodic_type 을 IMMEDIATE 로 강제 (요청값=%s)',
                         target.command_sender.name, target.periodic_type)
        target.periodic_type = PeriodicTypeEnum.IMMEDIATE
        # 스케줄 관련 필드는 의미가 없어지므로 함께 비운다 (훅 등록 순서와 무관하게)
        target.time_to_exe  = None
        target.time_to_stop = None
        target.cycle_to_exe = None
        target.interval_type = None
```

- **`before_insert` 여야 한다.** `after_insert` 에 두면 이미
  `create_command_detail1`(`:49-57`) 이 원래 `periodic_type` 을 보고 분기해버린다.
- **스케줄 필드를 같은 훅에서 직접 비운다.** 기존 `set_interval_type` 이
  `interval_type` 을 비워주지만, SQLAlchemy 리스너는 **등록 순서**로 실행되므로
  두 훅의 순서에 의존하면 깨지기 쉽다. 자체적으로 정리해 순서 무관하게 만든다.
- `edit` 경로도 막으려면 `before_update` 에 같은 처리를 추가한다.

#### (2) UI 반영 — 사용자가 놀라지 않게

강제만 하면 사용자가 `주기작업`을 골랐는데 조용히 `즉시작업`이 되어 혼란스럽다.
게다가 **FAB validator 가 훅보다 먼저 돈다**:

```python
# app/views/agent.py:321-322
'cycle_to_exe': [RequiredOnContidion('periodic_type', 'PERIODIC', ...)]
'time_to_exe' : [RequiredOnContidion('periodic_type', 'ONETIME', ...)]
```

즉 `MQTT + 주기작업`을 고르면 **버려질 `cycle_to_exe` 를 입력하라고 요구**받는다.
따라서 UI 에서 조합 자체를 막아야 한다.

이미 `app/templates/agent/command_master_add.html` / `command_master_edit.html` 에
동일한 "지능형 UI 제어" 패턴이 구현되어 있다(broadcast_callback 선택 시 대상 Agent·
그룹을 `disabled` 처리). 이를 그대로 확장한다.

```javascript
function handleSenderChange() {
    var isMqtt = ['MQTT', 'SERVER_N_MQTT'].indexOf($('#command_sender').val()) >= 0;
    var periodic = $('#periodic_type');
    if (isMqtt) {
        periodic.val('IMMEDIATE').trigger('change');
        periodic.prop('disabled', true);
        $('#time_to_exe, #time_to_stop, #cycle_to_exe, #interval_type')
            .val(null).prop('disabled', true);
    } else {
        periodic.prop('disabled', false);
        $('#time_to_exe, #time_to_stop, #cycle_to_exe, #interval_type')
            .prop('disabled', false);
    }
}
$('#command_sender').on('change', handleSenderChange);
handleSenderChange();
```

> `disabled` 필드는 폼 전송에서 제외되므로 서버단 훅이 최종 방어선 역할을 그대로 한다.

#### (3) 우회 경로 확인 — ORM 이벤트가 안 도는 곳

`before_insert` 는 **ORM 매핑 인스턴스의 flush 에만** 발동한다.
Core `insert()` 문은 훅을 타지 않는다. master 생성 경로 전수 조사 결과:

| 경로 | 방식 | `periodic_type` | 훅 발동 |
|---|---|---|---|
| UI ModelView (`app/views/agent.py:306,310`) | ORM | 사용자 선택 | **O** ← 주 대상 |
| `POST /api/v1/command_master/create` (`app/api/agent_api.py:370-373`) | ORM | `IMMEDIATE` 하드코딩 | O (이미 충족) |
| `POST /api/v1/command_master/extract_log` (`app/api/agent_api.py:572-575`) | ORM | `IMMEDIATE` 하드코딩 | O (이미 충족) |
| `app/sqls/agent.py:584` (`insert(AgCommandMaster)`) | **Core** | `IMMEDIATE`(`:565`) | **X** |
| `app/sqls/agent.py:638` (`insert(AgCommandMaster)`) | **Core** | `IMMEDIATE`(`:634`) | **X** |

→ Core insert 두 곳은 훅을 타지 않지만 **이미 `IMMEDIATE` 를 명시**하고 있어
현재는 충돌이 없다. 다만 향후 이 경로에 `command_sender=MQTT` 를 추가한다면
훅이 돌지 않으므로 **호출부에서 직접 `IMMEDIATE` 를 넣어야 한다.**

#### (4) 후속 동작

`IMMEDIATE` + `publish_yn='YES'` 조합은 `finish_commands_by_scheduler`
(`app/sqls/agent.py:383-395`, 1분 주기)가 다음 실행에서 `finished_yn='YES'` 로
정리한다. 기존 `IMMEDIATE` 와 동일한 동작이므로 추가 작업은 없다.

### Step 4. Alembic 마이그레이션

PostgreSQL native enum 이므로 `ALTER TYPE` 이 필요하다
(HOWTO_015 §3 과 동일한 절차).

```sql
ALTER TYPE commandstatusenum ADD VALUE IF NOT EXISTS 'MQTT';
ALTER TYPE commandstatusenum ADD VALUE IF NOT EXISTS 'MQTT_FAILED';
ALTER TYPE targettosendenum  ADD VALUE IF NOT EXISTS 'MQTT';
```

> `SERVER_N_MQTT` 는 도입하지 않았으므로 추가하지 않는다
> (`app/models/common.py` 참고 - push/polling 이중 실행 위험).

> PG 12+ 는 트랜잭션 블록 안에서 `ALTER TYPE ... ADD VALUE` 를 허용한다
> (추가한 값을 **같은 트랜잭션에서 사용**하는 것만 금지). DB 는 PostgreSQL 15.2 이고
> 기존 `a1b2c3d4e5f6` 마이그레이션도 같은 방식이므로 `op.execute` 로 충분하다.

> ⚠️ **이 환경의 alembic 체인은 이미 끊겨 있다.** DB `alembic_version` 이
> `cc8f86f77bff` 인데 이 revision 이 `migrations/versions/` 와 git 이력 어디에도
> 없어서 `flask db upgrade` 가 실패한다. 본 작업에서는 HOWTO_015 §3.2 의
> 수동 SQL 방식으로 db 컨테이너에 직접 적용했다.
> 마이그레이션 파일(`b7c1d9e4f2a8`)은 체인이 정상인 다른 환경용으로 남겨둔다.

### Step 5. 발송 분기 — `app/sqls/agent.py:490-511`

Kafka 블록의 형제로 MQTT 분기를 추가한다. 메시지 dict(`:494-504`)는 그대로 재사용.

```python
# MQTT (실시간 push)
elif command_rec.command_sender.name in ('MQTT', 'SERVER_N_MQTT') and mqtt_publisher:
    topic = app.config['MQTT_CMD_TOPIC'].format(agent_id=ag.agent_id)
    key   = f"{command_rec.command_id}_{repetition_seq + i}"
    message = dict(... 기존 Kafka message dict 와 동일 ...)
    pending_publishes.append((topic, key, message))   # D6: commit 이후 발행
```

**D6 을 지키기 위한 구조 변경**이 이 Step 의 핵심이다. 현재 `create_command_detail` 은
발행 → insert 순서다. MQTT 는:

1. `AgCommandDetail` 을 status `CREATE` 로 insert
2. 발행 대상을 `pending_publishes` 에 모은다
3. 호출부에서 **commit**
4. commit 성공 후 발행 → 성공 건만 status 를 `MQTT` 로 update → 다시 commit

호출부가 두 군데이므로 양쪽 모두 손대야 한다:

- `app/views/agent.py:49-57` `create_command_detail1` (`after_insert` 훅, IMMEDIATE)
  — **`after_insert` 훅 안에서는 commit 할 수 없다.** SQLAlchemy `after_commit`
  이벤트로 발행을 미루거나, `create_command_detail` 이 발행 목록을 반환하고
  훅이 이를 세션에 stash → `after_commit` 에서 flush 하는 방식을 쓴다.
- `app/sqls/agent.py:534-549` `create_command_detail_by_sch` (APScheduler, ONETIME/PERIODIC)
  — 자체 commit 이 있어 그 직후에 발행하면 된다.

### Step 6. 중복 전달 가드 수정 — `app/sqls/agent.py:457-463`

```python
.filter(..., AgCommandDetail.command_status=='CREATE').first()
```

이 "이미 미수행 명령이 있으면 skip" 가드는 **`CREATE` 만 인식**한다. status 가
`MQTT` 인 미완료 명령을 못 보므로, PERIODIC 재실행 시 중복 상세가 생길 수 있다.
(`KAFKA` 도 같은 허점을 갖고 있다.)

→ `command_status.in_(['CREATE', 'MQTT', 'KAFKA'])` 로 확장한다.

### Step 7. Agent 부팅 핸드셰이크 — `app/api/agent_api.py:88-92`

`command_v4` 는 `agent_status == 'BOOT'` 일 때 이미 `kafka_broker_address` 를
내려준다. 여기에 MQTT 접속 정보를 추가해 Agent 가 하드코딩 없이 브로커를 찾게 한다.

```python
{'command_class': 'BOOT',
 'mqtt_broker_host': ..., 'mqtt_broker_port': ...,
 'mqtt_topic': f'cmd/{agent_id}/req',
 'mqtt_broadcast_topic': 'cmd/broadcast/req'}
```

> **비밀번호는 내려주지 않는다.** Agent 의 MQTT 계정은 브로커 `passwd`/`acl` 에
> 별도 프로비저닝되어야 하며(§9), 그 배포 경로는 본 계획 범위 밖이다.

### Step 7.1 REST API 로 MQTT Command 전달 (검증 완료)

외부 시스템이 MQTT 로 명령을 보내려면 `POST /api/v1/command_master/create` 에
`command_sender` 를 주면 된다. **기본값은 `SERVER`** 이므로 기존 호출은 그대로 동작한다.

```bash
# 1) 로그인
curl -s -X POST http://mwm-app:8000/api/v1/security/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<user>","password":"<pw>","provider":"db","refresh":true}'

# 2) MQTT 로 즉시 전달
curl -s -X POST http://mwm-app:8000/api/v1/command_master/create \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"command_type_id":"Read.domain.xml",
       "target_agent_id":"devhost01_ops_J",
       "parameters":"",
       "command_sender":"MQTT"}'
# -> 201 {"return_code":1,"message":"OK","command_id":"fce4f4d142cb"}

# 3) 결과 조회
curl -s "http://mwm-app:8000/api/v1/command_master/result?command_id=fce4f4d142cb" \
  -H "Authorization: Bearer $TOKEN"
```

- `command_sender` 미지정 → `SERVER` (기존 동작, REST 폴링으로 전달)
- 잘못된 값 → `400` + 허용 목록 안내
  (`Invalid command_sender: BOGUS. Use one of ['SERVER', 'KAFKA', 'SERVER_N_KAFKA', 'MQTT']`)
- 이 API 는 `periodic_type=IMMEDIATE` 를 이미 하드코딩하므로 D11 강제와 충돌하지 않는다
- `parameters` 는 미지정 시 `''` 가 들어가므로 §4.3 의 JSON null 문제도 발생하지 않는다

#### 실측 대조 — 같은 명령을 두 방식으로 생성

| command_id | command_sender | 결과 |
|---|---|---|
| `fce4f4d142cb` | **MQTT** | **2초 후 `COMPLITED`** (Agent 가 push 로 수신·실행) |
| `27ea71353212` | `SERVER` | 동시점에 여전히 `CREATE` (다음 폴링 주기 대기) |

폴링 지연 제거라는 도입 목적이 그대로 확인된다.

### Step 8. 폴링 부기(bookkeeping) 보완

`send_commands` 는 명령 전달과 동시에 `AgAgent.last_checked_date` /
`agent_version` / `agent_type` 를 갱신한다(`app/sqls/agent.py:769-777`).
이 값이 UI 의 OnLine/OffLine 배지를 결정한다(`app/models/agent.py:68-89`).

MQTT push 는 이 경로를 타지 않으므로, **Agent 가 MQTT 로만 명령을 받고 폴링 주기를
늘리면 온라인 판정이 깨진다.** 대응:

- Agent 는 MQTT 도입 후에도 **하트비트 목적의 저빈도 폴링을 유지**한다 (권장, 변경 없음)
- 또는 `AGENT_OFFLINE_MINUTES`(`config.py:188`) 를 폴링 주기에 맞춰 조정

### Step 9. `docker-compose.yml`

```yaml
  mwm-app:
    environment:
      MQTT_ENABLED: ${MQTT_ENABLED:-False}   # 기본 끔. 켤 때만 .env 에서 True (§6.1)
      MQTT_BROKER_HOST: 172.26.0.1           # §5-A (컨테이너는 게이트웨이 경유)
      MQTT_BROKER_PORT: "1883"
      MQTT_USERNAME: central
      MQTT_PASSWORD: ${MQTT_PASSWORD}        # 호스트 .env 에서 치환 (§6)
```

`MQTT_ENABLED` / `MQTT_PASSWORD` 는 환경변수이므로 **값 변경에 이미지 재빌드가
필요하지 않다.** `docker compose up -d mwm-app` 재기동만으로 켜고 끌 수 있다.
(이미지 재빌드가 필요한 건 `config.py` 자체를 고칠 때다 — §6)

---

## 9. Agent 측 요구사항 (별도 repo)

서버만 구현해도 동작하지 않는다. Agent 가 아래를 만족해야 한다.

1. `username = <agent_id>`, 해당 비밀번호로 브로커 접속. 브로커 `passwd`/`acl` 에
   Agent 계정 프로비저닝 필요 (현재 `agent-001`, `agent-002`,
   `devhost01_ops_J` 만 등록됨)
2. `cmd/{agent_id}/req` 와 `cmd/broadcast/req` 구독, **QoS 1**
3. **`clean_start=False` + `SessionExpiryInterval` 설정** — 이것이 없으면 오프라인
   중 발행된 명령이 유실된다. §4.2 의 `Success` reason code 도 영속 세션이 있을 때만
   나온다
4. `(command_id, repetition_seq)` 기준 **멱등 처리** — MQTT push 와 REST 폴링이
   같은 명령을 중복 전달할 수 있는 경로(D5)에 대한 방어
5. 결과는 기존과 동일하게 `POST /api/v1/command/result` (JWT)
6. `max_queued_messages 100` 상한 — Agent 가 장기 오프라인이면 초과분은 버려진다.
   `MessageExpiryInterval` 1시간과 함께 "오래된 명령은 실행하지 않는다"는 정책으로 간주

---

## 10. 테스트 계획

| 단계 | 방법 | 기대 |
|---|---|---|
| 접속 | `central` 로 CONNACK 확인 | Success (§4 완료) |
| ACL | 비허용 토픽 발행 | `Not authorized` (§4 완료) |
| 단건 push | `command_sender=MQTT` 로 IMMEDIATE 명령 생성 | 폴링 대기 없이 Agent 수행, detail status `MQTT` |
| fallback | 브로커 중단 후 명령 생성 | status `CREATE` 유지 → 폴링으로 수행 (명령 유실 0) |
| 오프라인 큐 | Agent 종료 → 명령 발행 → Agent 재접속 | 재접속 직후 수신 (Agent `clean_start=False` 전제) |
| 미등록 Agent | 브로커 계정 없는 agent_id 로 발행 | PUBACK `No matching subscribers` → `CREATE` fallback |
| 중복 실행 | PERIODIC + MQTT 로 반복 | `repetition_seq` 증가, 동일 seq 2회 실행 없음 |
| 결과 수신 | `GET /api/v1/command_master/result` | `MQTT` 로 보낸 명령도 결과 정상 조회 (SPEC_022) |
| 기동 시 브로커 다운 | 브로커 중단 후 `mwm-app` 기동 | 기동 성공(차단·예외 없음), 60초 주기 재시도 |
| 운행 중 단절/복구 | 기동 후 브로커 중단 → 재기동 | 자동 재접속, 발행 재개 |
| 로그 폭주 | 브로커 장기 다운 상태 유지 | 연결성 로그 시간당 최대 3건, 억제 건수 표기 |
| 스위치 OFF | `MQTT_ENABLED=False` 로 기동 | paho import·스레드·접속 전부 없음, `command_sender=MQTT` 명령도 REST 폴링으로 수행 |
| 실행구분 강제 | UI 에서 `command_sender=MQTT` + `주기작업` 저장 시도 | `periodic_type=IMMEDIATE` 로 저장되고 스케줄 필드는 NULL |
| 실행구분 UI | UI 에서 `command_sender=MQTT` 선택 | 실행구분이 `즉시작업`으로 자동 설정 + 비활성화, 스케줄 필드 비활성화 |
| APScheduler 미등록 | 위 명령 저장 후 job 목록 확인 | `CreDetail_<command_id>` job 이 생성되지 않음 |
| 스위치 OFF→ON | `.env` 수정 후 컨테이너 재기동 | 재빌드 없이 전환, publisher 생성 |
| 의존성 누락 | paho 없는 이미지 + `MQTT_ENABLED=True` | ERROR 로그 1건, **기동은 성공**하고 REST 폴링 |

모든 테스트는 **Docker 안에서** 수행한다. 호스트에 venv 를 만들지 않는다.

### 수동 발행 스니펫 (디버깅용)

컨테이너에서 (브로커 호스트는 게이트웨이 IP):

```bash
docker run --rm --network mw_app_default eclipse-mosquitto:2.0 \
  mosquitto_pub -h 172.26.0.1 -p 1883 -V 5 \
  -u central -P "$MQTT_PASSWORD" \
  -t 'cmd/<agent_id>/req' -q 1 \
  -m '{"command_id":"...","repetition_seq":1,"command_class":"ExeShell", ...}'
```

앱 컨테이너에서 직접 확인할 때는 `docker exec mwm-app python3 -c '...'` 를 쓴다
(`mwm-app` 재빌드 후부터 paho 사용 가능).

> ⚠️ 실제 운영 Agent 의 토픽으로 임의 payload 를 발행하면 **영속 세션 큐에 적재되어
> Agent 재접속 시 그대로 배달**된다. 테스트는 `cmd/nobody/req` 처럼 세션 없는
> agent_id 를 쓰거나 전용 테스트 Agent 계정을 사용한다.

---

## 11. 미해결 과제 / 후속

1. **TLS 미적용.** 1883 평문 + 비밀번호 인증. 운영 적용 시 8883/TLS 또는 mTLS
   (`docs/mTLS_based_auth.md`) 검토
2. **브로커가 이 repo 의 compose 밖에 있다.** 배포·백업·기동 순서가 분리되어 있어
   `mwm-app` 이 브로커보다 먼저 떠도 조용히 REST 로만 동작한다. 의도된 동작이지만
   모니터링 지표가 필요
3. **브로커 단일 장애점.** `restart: unless-stopped` 만 있고 클러스터 구성 없음.
   REST fallback 이 안전망
4. **브로드캐스트 1건 발행 최적화** (D7 2차 과제)
5. **결과 상향 MQTT 전환** — ACL 에 Agent write 권한 추가가 선행 조건 (§3.2)
6. **`agent_id` 토픽 안전성.** `agent_id` 는 사용자/호스트 유래 자유 문자열이고
   코드에 sanitize 가 없다. `+`, `#`, `/` 가 포함되면 토픽이 깨지므로
   Agent 등록 시점(`app/sqls/agent.py:781`) 검증 추가 권장
7. **Agent 의 null 체크 누락 (mwagent 저장소).**
   `ReadPlainFile.getFileFullName()` 이 `getAdditionalParams()` 에 null 체크 없이
   `.length()` 를 호출해 NPE 가 난다. 더 나쁜 점은 `ReadFile.execute()` 가 예외를
   삼켜 **결과 보고 없이 명령이 사라진다**는 것이다. 서버측은 `''` 보정으로 우회했지만
   (§4.3) 근본 수정은 Agent 쪽이며, 예외 시 실패 결과라도 보고하게 해야 진단이 가능하다.
8. **결과 POST 의 FK 위반이 HTTP 500 으로 응답된다.**
   서버가 만들지 않은 `command_id` 로 결과를 보내면(예: 토픽에 직접 발행한 명령)
   `ag_result` FK 위반으로 500 이 난다. 의도된 무결성 제약이므로 4xx + 명확한 메시지가 맞다.
9. **Kafka 경로 정리.** `KAFKA_BROKERS = []` 로 사실상 사장된 코드에
   `sendMessage` 오타 버그까지 있다. MQTT 도입 후 Kafka 분기 제거 여부 결정
