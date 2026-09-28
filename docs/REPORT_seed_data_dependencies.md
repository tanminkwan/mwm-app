# REPORT: DB 선입력 데이터에 의존하는 코드 분석

**작성일**: 2026-09-18
**분석 기준**: `main` @ `fd48845`, 실행 중인 `mwm-db` / `mw` DB 스냅샷

## 0. 요약

코드가 "DB에 이 행이 이미 있다"고 가정하는 지점을 전수 조사했다. 대표적으로 알려진
token 갱신, `extract_log` 의 command type 의존 외에 **5개 범주**가 확인됐다.

위험도는 "시드가 없을 때 어떻게 실패하는가"로 갈린다. 예외로 죽는 것보다
**조용히 아무 일도 하지 않는 것**이 더 위험하다. 실제로 가장 심각한 건
C/D 범주의 무고지 실패다.

| 범주 | 대상 테이블 | 시드 누락 시 | 현재 정합성 |
|---|---|---|---|
| A. Command Type 레지스트리 | `ag_command_type` | FK 위반 예외 | ❌ 참조 11건 중 7건 누락 |
| B. 문자열 → 코드 심볼 디스패치 | `ag_command_type`, `ag_autorun_result`, `ag_command_master` | 조용한 no-op / 영구 미완료 | ⚠️ 정합하나 `set_properties` 누락 |
| C. 태그 시드 | `ut_tag` | 조용히 빈 값으로 진행 | ❌ 1건 누락, 1건 테스트 잔재 |
| D. 매핑 헬퍼 | `ag_command_helper` | 에이전트 조용히 건너뜀 | ❌ 0행 |
| E. 운영 데이터 하드코딩 | (코드 측) | `KeyError` / 오분류 | ⚠️ 개발 PC 경로 잔존 |
| F. 시드 스크립트 커버리지 | — | 재구축 시 기능 소실 | ❌ 필요 시드 중 1건만 스크립트화 |

## A. `ag_command_type` 레지스트리 — 코드에 command_type_id 하드코딩

코드가 특정 `command_type_id` 문자열을 박아놓고 그 행이 DB에 있다고 가정한다.
`ag_command_master.command_type_id` 에는 **FK 제약**이 있어(`app/models/agent.py:157`)
행이 없으면 INSERT 시점에 `IntegrityError` 가 발생한다.

| 위치 | command_type_id | 현재 DB |
|---|---|---|
| `app/api/agent_api.py:569` | `EXTRACT.LOG` | 존재 |
| ~~`app/sqls/agent.py:157-159`~~ | ~~`RUN.CONNECT.SSL.WIN` / `RUN.CONNECT.SSL`~~ | **해소** — 호출 코드를 TASK 3-11 에서 제거 |
| ~~`app/sqls/agent.py:288-290`~~ | ~~`RUN.FILE.SSL.WIN` / `RUN.FILE.SSL`~~ | **해소** — 호출 코드를 TASK 3-12 에서 제거 |
| `app/views/monitor.py:316-324` | `NOAGENT.JMX.MONITOR` / `ASIS.P.JMX.MONITOR` / `NEWGEN.jmx.monitor` | **없음** — **존치 결정 (2026-09-27)**. TASK 3-13 §6 |
| `app/sqls/agent.py:711` | `GetRefreshToken` (자체 INSERT) | `updateToken` 이 대행 |
| (2026-09-18 등록) | `CALL.SET_PROPERTIES` | 존재 |

하드코딩 참조 11건 중 **7건이 현재 DB에 없다.** 즉 다음 기능은 현 형상에서 실패한다.

* SSL 인증서 수집 — `app/views/was.py:732`, `app/views/was.py:902` (예외 그대로 전파)
* WAS 상태 재확인 — `app/views/monitor.py:295` `recheckStatus` (`try/except` 로 화면 에러 표시)

`EXTRACT.LOG` 만 유일하게 **존재 검증 후 HTTP 400 을 반환**한다
(`app/api/agent_api.py:570-572`). 나머지는 검증 없이 바로 INSERT 한다.

### A-1. 예외: 자체 복구형 2건

**token 갱신** — `get_closeto_token_expiry_bysch()` (`app/sqls/agent.py:706-719`) 는
`command_class=='GetRefreshToken'` 으로 조회해 **없으면 직접 INSERT** 한다.
시드 의존이 없는 유일한 설계다. 단 조회 키가 `command_type_id` 가 아니라
`command_class` 라서, 현재 DB 의 `updateToken` 행이 그 역할을 하고 있다 —
`command_type_id` 이름은 무엇이든 무관하다.

또한 이 자동 INSERT 는 `target_file_path` 를 채우지 않아 NULL 로 들어간다.
이 경로는 `AgCommandDetail` 을 직접 만들어(`app/sqls/agent.py:742-755`)
`create_command_detail()` 을 우회하므로 지금은 문제가 없지만,
`create_command_detail()` 은 `target_file_path` 에 널 체크 없이
`rexp.match()` 를 호출한다(`app/sqls/agent.py:477`). 이 command type 이
다른 경로로 쓰이면 `TypeError` 가 된다.

**스텁** — `get_or_insert_command_type()` (`app/sqls/agent.py:649`) 은 이름과 달리
`return 0, ''` 스텁이다. `send_command_immediately()` (`app/sqls/agent.py:645`) 도 동일.
이를 쓰는 `restartMWAgent()` (`app/sqls/agent_dml.py:911`) 는 `command_type_id` 에
튜플 `(0, '')` 을 받아 넘기는 **완전한 no-op** 이다.

## B. DB 문자열 → 코드 심볼 동적 디스패치

DB 컬럼 값이 **함수/메소드 이름 문자열**이고, 코드가 그 이름으로 심볼을 찾는다.
컴파일 타임 검증이 전혀 없어 함수명을 리팩터링하면 DB 행이 조용히 끊긴다.

| 메커니즘 | 위치 | DB 컬럼 | 해석 방식 |
|---|---|---|---|
| ServerFunc 배치 | `app/sqls/batch.py:56` | `ag_command_type.target_file_name` | `globals()[function_name]` |
| Autorun 후처리 | `app/sqls/agent_dml.py:65` | `ag_autorun_result.autorun_func` | `getattr(self, autorunFunc)` |
| Broadcast 콜백 | `app/sqls/agent.py:499` | `ag_command_master.broadcast_callback` | 데코레이터 레지스트리 조회 |
| Agent 기능 | (Java Agent 측) | `ag_command_type.target_file_name` | Agent 가 함수명으로 해석 |

현재 DB 상태는 전부 정합하다.

* ServerFunc: `sync_role_permissions` (`app/sqls/batch.py:402`),
  `re_register_all_was_from_text` (`app/sqls/batch.py:286`) 존재 확인
* Autorun 3행: `update_jeus_domain`, `update_connect_ssl_by_api`,
  `update_gc_parsed_log` 모두 `AutorunResult` 메소드로 존재
* Broadcast: DB 의 `get_all_agents(PROD)`, `get_was_agents_newgen`,
  `get_all_agents` 모두 레지스트리에 등록됨

주의할 점 두 가지.

* `ag_command_master.broadcast_callback` 에 **빈 문자열 행**이 있다.
  `create_command_detail` 이 `if command_rec.broadcast_callback:` 로 걸러내므로
  무해하지만, 미등록 이름이 들어가면
  `return 0, "Broadcast callback 'X' not found."` 로 명령 전체가 취소된다.
* `ag_autorun_result.target_file_name` 은 **정규식으로도 매칭**된다
  (`app/sqls/agent.py:135-145`). `domain.*\.xml` 같은 행이 있어, 새 기능의
  함수명이 기존 정규식에 우연히 걸리면 엉뚱한 후처리가 실행된다.

### B-1. 실제 사고: `set_properties` 결과가 영구 미완료로 남는다

2026-09-18 에 Agent 측에 추가된 `set_properties` 기능이 정확히 이 함정에 빠져 있다.
`ag_autorun_result` 에 해당 행이 없으므로:

1. `call_autorun_func()` → `(0, 'No Autorun')` (`app/sqls/agent_dml.py:57-58`)
2. `app/api/agent_api.py:169-173` → `rtn2 > 0` 이 아니므로 **`db.session.rollback()`** + ERROR 로그
3. `ag_result.result_status` 는 `CREATE`, `complited_date` 는 `NULL` 로 **영구히 남는다**

실측(command_id `a106be54246b`)에서 `result_text` 는 정상 수신됐으나
`result_status: "CREATE"`, `complited_date: null` 이었다. `add_result` 가 먼저
커밋되므로 데이터 자체는 살아 있지만 상태값은 절대 `COMPLITED` 가 되지 않는다.
**후처리가 필요 없는 명령까지 실패로 취급하는 구조**다.

`app/jobs.py` 의 "Remove Finished Commands" 잡이 `finished_yn` 기준으로 정리하므로,
이런 미완료 결과의 누적 여부도 확인이 필요하다.

## C. `ut_tag` 태그 시드 의존 — 조용한 실패

| 위치 | 필요한 태그 | 현재 DB | 없을 때 |
|---|---|---|---|
| `app/api/agent_api.py:583-590` | `MS-{was_id}-{host}` + 상위 `log.format*` (`value1` = 정규식 JSON) | `MS-` 5행 / `log.format.test1`, `log.format.test2` | `date_regex_list=[]` 로 **빈 배열 전송** → Agent 로그 파싱 실패 |
| `app/sqls/agent_dml.py:1086` | `지식유형-LOG추출` | **없음** | `if target_tag:` 가드 → **태그 없는 지식 문서가 조용히 생성** |
| `app/sqls/monitor.py:655` | `담당자-업무-박훈` | — | 특정 담당자 이름이 코드에 하드코딩 |
| `app/views/knowledge.py:499` | `tag_prefix` 로 시작하는 태그군 | — | 목록이 빈 상태로 렌더링 |

`extract_log` 의 태그 의존이 특히 다층적이다.

```
MwWasInstance → was_id → MS-{was_id}-{host} 태그 → 상위 log.format* 태그 → value1 JSON
```

**4단 체인 중 어디가 끊겨도 HTTP 400 이 아니라 "정규식 없는 명령"이
정상 응답(201)으로 하달된다.** 현재 `log.format` 태그가 `test1`/`test2` 뿐인 것도
운영 데이터가 아니라 테스트 잔재로 보인다.

## D. `ag_command_helper` 매핑 의존 — 현재 0행

`<<<...>>>` 플레이스홀더 치환과 에이전트별 경로 매핑에 쓰이는 테이블인데
**현재 0행**이다.

* `app/sqls/agent.py:531-540` — `target_file_path` 에 `<<<KEY>>>` 가 있으면 매핑 조회.
  없으면 `logging.error` 후 **해당 에이전트를 `continue` 로 건너뛴다.**
  명령은 `publish_yn=YES` 로 마킹되지만 실제로 아무 에이전트에도 가지 않는다.
* `app/views/monitor.py:320` — `mapping_key='ASIS_JMX_PARAMS'` 조회.
  0행이므로 항상 `NEWGEN.jmx.monitor`(A 범주에서 누락 확인된 타입) 분기로 간다.
* `app/views/was.py:436`, `app/sqls/agent_dml.py:870` — `mapping_key='DOMAIN_HOME'`.
  이쪽은 **기본값 `/sw/jeus/bin/` 폴백이 있어** 유일하게 안전하다.

### D-1. 플레이스홀더 문법 불일치

정규식은 `(<<<)(.*?)(>>>)` 로 **3중** 괄호인데(`app/sqls/agent.py:476`),
시드된 `sslcertifile.download` 행의 `target_file_path` 는 `<<WEBTOBDIR>>/ssl/` 로
**2중**이다. 매칭이 되지 않아 치환 없이 리터럴 `<<WEBTOBDIR>>` 이 Agent 로 전달된다.

## E. 특정 운영 데이터가 코드에 하드코딩

시드 의존과 방향은 반대지만 같은 뿌리의 문제다.

* `app/sqls/agent_dml.py:512` — `if host_id == 'uok01a' and 'usropt01/jeus60/jeusok' in file_path:`
  → `domain_id = 'jeusok2_dev'` (주석에 "예외로직"이라 명시)
* `app/sqls/agent_dml.py:895-901` — `agent_sub_type` → 재기동 스크립트명 5종 dict.
  DB enum 에 새 값이 추가되면 `KeyError`
* `app/api/agent_api.py:547-550` — `/log/jeus/{was_instance_id}/JeusServer.log` 경로 규칙
* `app/api/agent_api.py:554-557` — agent_id 후보 `{host_id}_jeus_J` / `{host_id}_webtob_J` 명명 규약
* 현재 DB 의 `Read.domain.xml` 행은 `target_file_path` 가
  `/home/<user>/GitHub/mw/test/domains/...` — 개발 PC 절대경로가 DB 에 남아 있다

## F. 시드 스크립트가 실태를 따라가지 못함

| 파일 | 줄수 | 내용 |
|---|---|---|
| `create_db.sql` | 7 | DB/유저 생성만 |
| `insert_ct.py` | 16 | `EXTRACT.LOG` 만 |
| `insert_data.py` | 84 | `EXTRACT.LOG` + `uok01a` 테스트 서버/WAS |
| `insert_data2.py` | 46 | 추가 테스트 데이터 |

**A~D 에서 필요한 시드 중 `EXTRACT.LOG` 하나만 스크립트화되어 있다.**
나머지 — `updateToken`, `SYNC.ROLE_PERMISSIONS`, `WAS.REBUILD`,
`CALL.GET_SSL_CERTI`, `ag_autorun_result` 3행, 그리고
2026-09-18 에 등록한 `CALL.SET_PROPERTIES` — 는 **운영 DB 에만 존재**한다.
새 환경을 구축하면 이 기능들은 전부 동작하지 않고, 어느 것이 빠졌는지
알 방법도 없다.

## G. 개선 우선순위

| # | 항목 | 근거 |
|---|---|---|
| 1 | `No Autorun` 시 rollback 하지 않고 `COMPLITED` 처리 (`app/api/agent_api.py:169`) | 후처리 불필요한 명령이 영구 미완료로 남음. `set_properties` 가 현재 이 상태 (B-1) |
| 2 | 시드 스크립트 정비 — 현 DB 의 `ag_command_type` / `ag_autorun_result` 전량을 멱등 스크립트로 추출 | 재구축 시 조용히 깨지는 기능 다수. `CALL.SET_PROPERTIES` 포함 필요 (F) |
| 3 | 기동 시 하드코딩 `command_type_id` 존재 검증 로그 | 7건 누락을 아무도 모르는 상태. 실행 시점이 아니라 기동 시점에 드러나야 함 (A) |
| 4 | `extract_log` 의 `log.format` 태그 누락 시 경고 또는 400 | 빈 정규식으로 201 응답 후 Agent 에서 실패 — 원인 추적 곤란 (C) |
| 5 | `<<...>>` 와 `<<<...>>>` 문법 통일 | 시드와 정규식 불일치 (D-1) |
| 6 | `get_or_insert_command_type` / `send_command_immediately` 스텁 제거 또는 구현 | `restartMWAgent()` 가 조용한 no-op (A-1) |

## H. 관련 문서

* [HOWTO_012](HOWTO_012_command_master_api.md) — CommandMasterApi 사용 가이드
* [HOWTO_015](HOWTO_015_add_extractlog_command.md) — ExtractLog command 추가
* [SPEC_001](SPEC_001_broadcast_callback.md) — Broadcast callback
* [SPEC_002](SPEC_002_sync_role_permissions.md) — Role 권한 동기화
* [SPEC_021](SPEC_021_extract_log_api.md) — Extract Log API
* [agent_command_system.md](agent_command_system.md) — Agent 명령 체계 개요
