# 에이전트 명령(Command) 시스템 가이드

이 문서는 MWM(Middleware Management) 시스템의 핵심 기능인 에이전트 명령 생성, 배포 및 결과 처리 시스템에 대해 설명합니다.

---

## 1. 개요 (Overview)
중앙 서버에서 수천 대의 원격 서버(에이전트)에 특정 작업(스크립트 실행, 설정 변경, 파일 전송 등)을 지시하고, 그 결과를 실시간으로 수집하여 관리하는 시스템입니다.

명령 전달 방식은 두 가지이며, `AgCommandMaster.command_sender` 로 선택합니다.

| 방식 | 값 | 특징 |
|---|---|---|
| **폴링 (기본)** | `SERVER` | 에이전트가 주기적으로 REST 로 조회. 폴링 주기만큼 지연 |
| **실시간 push** | `MQTT` | 서버가 MQTT 브로커로 즉시 발행. 지연 없음 (실측 2초 내 수행 완료) |

MQTT 는 폴링을 **대체하지 않고 보완**합니다. 발행이 실패하면 명령이 `CREATE` 상태로 남아
기존 폴링이 그대로 가져가므로, 브로커 장애가 기능 장애로 이어지지 않습니다.
상세는 [HOWTO 016](HOWTO_016_mqtt_realtime_command.md) 참고.

---

## 2. 데이터 모델 및 구조 (Data Model)

시스템은 **Master-Detail-Result**의 3단계 구조로 이루어져 있습니다.

### 2.1 AgCommandType (명령 정의)
- 수행할 작업의 '정의'입니다.
- 실행할 파일 경로, 파일명, 명령 클래스(`CommandClass`) 등을 미리 정의합니다.

### 2.2 AgCommandMaster (명령 마스터)
- 누구에게(Target), 언제(Schedule), 무엇을(Type) 시킬지 결정하는 레코드입니다.
- **실행 구분**: `IMMEDIATE`(즉시), `ONETIME`(1회 예약), `PERIODIC`(주기적 반복).
- **대상 지정**: 개별 에이전트, 에이전트 그룹, 또는 **전체 대상(Broadcast)**.

### 2.3 AgCommandDetail (명령 상세)
- 마스터가 생성될 때, 각 에이전트별로 생성되는 실제 수행권입니다.
- `AgResult` 생성을 위한 부모(Parent) 역할을 하며, 데이터 무결성을 보장합니다.
- 상태 변화 (폴링): `CREATE` → `SENDED` → `COMPLITED` / `FAILED`.
- 상태 변화 (MQTT): `MQTT` → `COMPLITED` / `FAILED`.
  발행 실패 시에는 `CREATE` 로 남아 폴링 경로를 타므로 `SENDED` 를 거칩니다.

### 2.4 AgResult (실행 결과)
- 에이전트가 명령을 수행한 후 서버로 보내온 결과 데이터입니다.
- 상세 명령(`AgCommandDetail`)과 외래키(FK)로 연결되어 있어, 추적이 가능합니다.

---

## 3. 명령 대상 지정 방식 (Command Targeting)

MWM 시스템은 유연한 대상 지정을 지원하기 위해 세 가지 방식을 제공합니다.

### 3.1 개별 에이전트 (Individual Agents)
- 하나 이상의 특정 에이전트를 직접 선택합니다.
- 특정 장비에만 패치를 적용하거나 개별 상태를 확인해야 할 때 사용합니다.

### 3.2 에이전트 그룹 (Agent Groups)
- 미리 정의된 에이전트 그룹(`AgAgentGroup`)을 선택합니다.
- 운영 장비군, 개발 장비군, 또는 특정 서비스 모듈 단위로 대량의 장비에 동일한 명령을 내릴 때 효율적입니다.

### 3.3 전체 대상 (Broadcast) - [신규]
- 시스템에 승인된 모든 에이전트를 대상으로 합니다.
- **UI**: `전체 대상(Broadcast)`을 `YES`로 선택하면 자동 적용됩니다.
- **지능형 UI 제어**: `YES` 선택 시 '대상 Agent' 및 '그룹' 선택 필드가 자동으로 비활성화(Gray out)되어 중복 선택이나 사용자 실수를 방지합니다.
- **로직**: 명령 저장 또는 스케줄러 실행 시점에 활성 상태인 모든 에이전트를 쿼리하여 개별 실행권을 자동 생성합니다.

---

## 4. 실행 프로세스 (Execution Flow)

```mermaid
sequenceDiagram
    participant U as User (UI)
    participant S as MWM Server (Flask)
    participant DB as Database (Postgres)
    participant B as MQTT Broker (Mosquitto)
    participant A as Agent

    U->>S: 명령 마스터 생성 (AgCommandMaster)
    S->>DB: 마스터 레코드 저장
    
    rect rgb(240, 240, 240)
    Note over S,DB: 즉시 실행 또는 스케줄러 트리거
    S->>DB: 대상 에이전트별 상세 레코드 생성 (AgCommandDetail, CREATE)
    end

    alt command_sender = MQTT (실시간 push)
        Note over S,B: 발행은 반드시 commit 이후에 한다
        S->>B: cmd/{agentId}/req 발행 (QoS 1)
        B-->>S: PUBACK
        S->>DB: 상세 레코드 상태 변경 (MQTT)
        B->>A: 명령 데이터 전달 (JSON)
    else command_sender = SERVER (폴링) 또는 MQTT 발행 실패
        loop 주기적 하트비트 (Polling)
            A->>S: 명령 조회 요청 (GET /api/v1/command/...)
            S->>DB: CREATE 상태인 상세 명령 조회
            DB-->>S: 명령 데이터
            S->>DB: 상세 레코드 상태 변경 (SENDED)
            S-->>A: 명령 데이터 전달 (JSON)
        end
    end

    Note over A: 로직 수행 (스크립트 실행 등)

    A->>S: 실행 결과 보고 (POST /api/v1/command/result)
    S->>DB: 결과 레코드 저장 (AgResult)
    S->>DB: 상세 레코드 상태 완료 변경 (COMPLITED)
    S-->>A: 수신 완료 응답
```

1.  **명령 생성 (Server Side)**:
    - 사용자가 UI를 통해 명령 마스터를 생성합니다.
    - 즉시 실행인 경우 `after_insert` 서버 이벤트가 발생하여 상세 레코드를 생성합니다.
    - 주기성 실행인 경우 `APScheduler`가 정해진 시간에 상세 레코드를 생성합니다.

2.  **명령 전달 (MQTT Push)** — `command_sender=MQTT` 인 경우:
    - 상세 레코드를 만든 뒤 **DB commit 이 끝난 다음에** 브로커로 발행합니다.
      commit 전에 발행하면 에이전트가 결과를 먼저 보고해 상세 레코드가 없는 상태가 되어
      결과가 유실됩니다.
    - 발행 성공 시 상세 레코드는 `MQTT` 상태가 되고, 폴링 조회 대상(`CREATE`)에서 빠지므로
      **중복 전달되지 않습니다.**
    - 발행 실패 또는 구독자 없음(`No matching subscribers`)이면 `CREATE` 를 유지해
      폴링으로 넘깁니다.

3.  **명령 수신 (Agent Polling)**:
    - 에이전트는 주기적으로 하트비트(REST API)를 서버로 보냅니다.
    - 서버는 해당 에이전트용 `AgCommandDetail` 중 `CREATE` 상태인 항목을 응답으로 내려줍니다.
    - 응답과 동시에 해당 상세 레코드는 `SENDED` 상태로 변경됩니다.

4.  **결과 보고 (Result Submission)**:
    - 에이전트가 작업을 마치면 결과 API(`POST /api/v1/command/result`)를 호출합니다.
    - 서버는 `AgResult`를 생성하고, 연결된 `AgCommandDetail`의 상태를 `COMPLITED` 또는 `FAILED`로 업데이트합니다.

5.  **결과 조회 (Result Retrieval)**:
    - 외부 시스템이나 UI는 조회 API(`GET /api/v1/command_master/result`)로 실행 결과를 확인합니다.
    - `command_id` / `agent_id` / `host_id` 중 최소 하나를 조건으로 하며, 여러 건이면 `create_on` 기준 최근 1건을 반환합니다.
    - 상세 명세는 [SPEC 022](SPEC_022_command_result_api.md) 및 [HOWTO 012](HOWTO_012_command_master_api.md) 참고.

---

## 5. 기술적 특징 및 주의사항

- **무결성 제약**: `AgResult`는 반드시 서버에 미리 생성된 `AgCommandDetail`이 있어야만 저장이 가능합니다. (Foreign Key 제약)
- **주기성 작업**: `PERIODIC` 옵션 사용 시, 매 실행 주기마다 새로운 실행 회차(`repetition_seq`)를 가진 상세 레코드가 생성됩니다.
- **확장성**: 브로드캐스트 기능을 통해 수천 대의 장비에 동시에 자동 업데이트나 환경 설정을 배포할 수 있습니다.
- **MQTT 실행 구분 제약**: `command_sender=MQTT` 인 명령은 실행 구분이 **`IMMEDIATE` 로 강제**됩니다.
  `ONETIME`/`PERIODIC` 은 스케줄러가 나중에 상세를 생성하므로 '실시간 push' 가 성립하지 않습니다.
  UI 에서는 MQTT 선택 시 실행 구분이 자동으로 '즉시작업'으로 고정되고 스케줄 입력란이 비활성화됩니다.
- **MQTT 결과 경로**: 브로커 ACL 이 에이전트에게 발행(write) 권한을 주지 않으므로 MQTT 는
  **하향(서버→에이전트) 단방향 전용**입니다. 결과 보고는 방식과 무관하게 항상 REST 를 사용합니다.
- **오프라인 에이전트**: 브로커가 영속 세션에 명령을 큐잉하므로, 오프라인 에이전트도 재접속 시
  누락된 명령을 받습니다. 단 에이전트가 `clean_start=False` 로 접속해야 하며, 명령은 1시간 후
  브로커에서 자동 폐기됩니다(오래된 명령이 뒤늦게 실행되는 것을 방지).
