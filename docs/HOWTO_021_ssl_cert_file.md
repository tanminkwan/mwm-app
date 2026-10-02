# HOWTO_021: SSL 인증서 파일 등록·적용 현황

> 상태: **구현 완료** (2026-10-01) — 브랜치 `mwm-app-20261001-ssl-cert-file`. 테스트 56건(TDD), 전체 389 passed. 실제 앱 화면 확인 전
> 관련: [HOWTO_014](HOWTO_014_ssl_ica_status_page.md) (SSL인증서 만료 현황), [SPEC_017](SPEC_017_etc_ssl_domain.md) (기타 SSL Domain)

---

## 1. 개요

새로 받은 SSL 인증서 파일을 등록하고, 그 인증서를 어느 도메인에 적용해야 하는지(또는 적용됐는지) 본다.

| 화면 | 하는 일 |
| :--- | :--- |
| **SSL 인증서 파일** (`/sslcertfilemodelview/list`) | `ag_file` 에서 파일을 골라 등록 → 서버가 인증서 정보 추출·저장. 보기/수정(이름만)/삭제 |
| **SSL 인증서 적용 현황** (`/sslcertapplyview/`) | 인증서 하나를 고르면 적용 대상 도메인 목록 |

| 할 일 | 위치 |
| :--- | :--- |
| 모델 `MwSslCertFile` (신규 테이블 `mw_ssl_cert_file`), `SslCertTypeEnum` | `app/models/was.py`, `app/models/common.py` |
| 인증서 파싱 | `app/sqls/ssl_cert.py` (신규) |
| 적용 대상 조회 | `app/sqls/ssl_cert.py` |
| 화면 2개 + 메뉴 | `app/views/ssl_cert.py` (신규), `app/templates/ssl_cert_apply.html` (신규) |
| REST | `/api/v1/monitor/ssl_cert_apply/<id>` — `app/api/monitor_api.py` |
| DB | 테이블 1개 추가 — 운영은 SQL 파일 (§7) |

기존 화면·API 계약은 바꾸지 않는다. `AgFile` 에 `__repr__` 만 추가한다(§3.2).

---

## 2. 테이블 `mw_ssl_cert_file`

인증서 파일 1건 = 1행. 화면과 1:1.

| 컬럼 | 타입 | 제약 | 입력 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 자동 | |
| `cert_name` | String(30) | NOT NULL, UNIQUE | 화면 | 이름 (예: `2026.11-EV-bank`). **UTF-8 30byte 이내** |
| `ag_file_id` | Integer | FK `ag_file.id` ON DELETE SET NULL | 화면 | 원본 파일 |
| `file_name` | String(50) | NOT NULL | 자동 | 등록 시점의 `ag_file.file_name` 복사 (파일이 지워져도 남는다) |
| `received_date` | Date | NOT NULL | 화면 | 접수일 `yyyy-mm-dd` |
| `receiver_name` | String(50) | NOT NULL | 화면 | 접수자 이름 |
| `cert_type` | Enum(SslCertTypeEnum) | NOT NULL | 추출 | `LEAF` / `CA` (중간 CA) |
| `subject` | String(300) | | 추출 | |
| `cn` | String(200) | | 추출 | subject 의 CN 값 (`CN=` 뺀 값). 적용 대상 매칭 키 |
| `serial` | String(100) | | 추출 | |
| `issuer` | String(300) | | 추출 | |
| `notbefore` | DateTime | | 추출 | 유효기간 시작 |
| `notafter` | DateTime | | 추출 | 유효기간 만료 |
| `user_id` | String(50) | NOT NULL | 자동 | `get_user` |
| `create_on` | DateTime | NOT NULL | 자동 | |

`subject`·`serial`·`issuer`·`notbefore`·`notafter` 는 `MwWebDomain` 과 같은 이름·타입·형식으로 둔다.
값 형식도 맞춘다 — 적용 현황에서 나란히 보이고, `cn` 은 `MwWebDomain.t__cn()` 과 비교한다.

```python
class SslCertTypeEnum(enum.Enum):   # app/models/common.py
    LEAF = 'Leaf'
    CA   = '중간 CA'
```

---

## 3. 화면 1 — SSL 인증서 파일

### 3.1 컬럼

| 동작 | 컬럼 |
| :--- | :--- |
| add | `ag_file`, `cert_name`, `received_date`, `receiver_name` |
| edit | `cert_name` **만** |
| list | `cert_name`, `cert_type`, `cn`, `notafter`, `file_name`, `received_date`, `receiver_name` |
| show | 전 컬럼 |

`base_permissions = ['can_list', 'can_show', 'can_add', 'can_edit', 'can_delete']`.
목록 정렬 기본값은 `received_date` 내림차순.

### 3.2 파일 선택

`ag_file` 은 relationship select(`QuerySelectField`)로 고른다. 지금 `AgFile` 에 `__repr__` 이 없어서
선택지가 `<AgFile 3>` 으로 보인다 → `AgFile.__repr__` 을 `f'{file_name} ({file_version})'` 로 추가한다.
다른 화면에서 `AgFile` 을 문자열로 쓰는 곳이 없음을 구현 시 확인한다.

### 3.3 저장 흐름

```
[저장] → 폼 검증 (cert_name 30byte, 날짜 형식, 필수값)
       → pre_add: ag_file 의 파일을 S3FileManager.get_file() 로 읽음
       → parse_certificate(bytes)  — 실패하면 ValueError
       → cert_type/subject/cn/serial/issuer/notbefore/notafter/file_name 채움 → INSERT
```

- 이름 길이: `len(cert_name.encode('utf-8')) <= 30` 검증기를 단다. String(30) 은 PostgreSQL 에서 **글자 수** 제한이라
  한글이 섞이면 30byte 를 넘어도 들어간다. 요구가 byte 이므로 검증기가 기준이다.
- 추출은 `SslCertFileModelView.pre_add()` 에서 한다. FAB `BaseCRUDView._add()` 는 `pre_add` 예외를 잡아
  `flash(str(e), "danger")` 로 보이고 **INSERT 하지 않는다** (설치된 FAB 소스로 확인).
  `before_insert` 리스너(`AgFile` 의 `set_file_name` 방식)는 쓰지 않는다 — 거기서 난 `ValueError` 는
  `SQLAInterface.add()` 가 `SQLAlchemyError` 만 롤백하므로 세션이 롤백되지 않은 채 남는다.
- 수정은 `cert_name` 만 바뀌므로 재추출하지 않는다.

### 3.4 인증서 파싱 — `parse_certificate(data: bytes) -> dict`

요구사항의 "openssl 등" → **`cryptography` 패키지**(이미 `requirements.txt` 에 있음)로 한다.
`openssl` 바이너리를 subprocess 로 부르지 않는다 — 이미지에 openssl CLI 가 있다는 보장이 없고, 쉘 호출을 늘리지 않는다.

| 단계 | 처리 |
| :--- | :--- |
| 형식 | PEM(`-----BEGIN CERTIFICATE-----`) → `x509.load_pem_x509_certificates`. 아니면 DER → `load_der_x509_certificate` |
| 인증서 개수 | **정확히 1개**. 0개 → 오류. 2개 이상(체인 묶음) → 오류 "인증서 1개짜리 파일만 등록" |
| 개인키 | 파일에 `PRIVATE KEY` 블록이 있으면 오류 (키 파일 업로드 방지) |
| leaf/CA | `BasicConstraints.ca == True` → `CA`, 그 외(확장 없음 포함) → `LEAF` |
| 루트 CA | subject == issuer 인 CA(자체서명 루트) → 오류 "루트 인증서는 대상 아님" |
| subject/issuer | `rfc4514_string()` — 쉼표 구분. `t__cn()` 이 `/` 와 `,` 를 모두 처리하므로 그대로 비교 가능 |
| cn | subject 의 `NameOID.COMMON_NAME` 첫 값. 없으면 `None` (leaf 인데 CN 없으면 오류) |
| serial | 대문자 16진수 문자열 (`format(serial_number, 'X')`). 보기용 — 식별에는 쓰지 않는다 (§4.4) |
| 날짜 | `not_valid_before_utc` / `not_valid_after_utc` + 9h → **KST naive datetime, 마이크로초 0**. Agent 수집값(`_get_ssl_datetime`)과 같은 규칙 — 적용 여부 식별 키라 반드시 맞춘다 |

오류 메시지는 사용자에게 그대로 보이므로 파일 내용·경로를 넣지 않는다.

---

## 4. 화면 2 — SSL 인증서 적용 현황

### 4.1 전체 대상 (모수)

| 출처 | 조건 |
| :--- | :--- |
| `mw_web_domain` | `ssl_yn = YES` **and** `mw_web.use_yn = YES` (vhost → web 조인) |
| `mw_etc_ssl_domain` | `use_yn = YES` |

**WEB 쪽은 `/api/v1/monitor/cert_expiry_stat` 의 `전체.total` 과 같다** (같은 조인·필터, `get_cert_expiry_stat()` `app/sqls/monitor.py:668`).

> ⚠ ETC 쪽은 기존 API 와 모수가 다르다. `/cert_expiry_stat` 은 WEB 만 센다.
> JEUS 쪽 `/cert_expiry_stat_jeus` 는 `mw_etc_ssl_domain` 이 아니라 **`mw_was_http_listener`(ssl_yn=YES)** 를 센다
> (도메인이 없는 리스너도 '미확인'으로 포함). 요구사항대로 **`mw_etc_ssl_domain(use_yn=YES)` 를 쓴다** —
> 이 경우 "모수가 cert_expiry_stat 과 같다"는 WEB 부분에만 성립한다. (§8-1 확정)

### 4.2 특정 인증서의 적용 대상

| 인증서 | 대상 | 보여 줄 인증서 정보 |
| :--- | :--- | :--- |
| `LEAF` | 모수 중 **현재 leaf CN == 이 인증서 CN** | `subject`, `notafter` |
| `CA` | 모수 **전체** (필터 없음) | `subject_ca`, `notafter_ca` |

- CN 비교: `CN=` 을 뗀 값끼리 **대소문자 무시**로 비교한다. 모수 행의 CN 은 §4.3 방식으로 얻는다.
- **bulk 인증서는 CN 이 와일드카드다** (예: `CN=*.com.kr`). CN **문자열끼리** 비교하므로 bulk 파일은
  현재 subject 의 CN 도 `*.com.kr` 인 행과 매칭된다. `*` 를 와일드카드로 풀어 `domain_name` 과 맞추지 않는다.
  `*` 는 SQL `LIKE` 특수문자가 아니라 이스케이프 대상이 아니다. SAN 은 보지 않는다.
- `subject` 가 `No Valid Certificate.` / `Connection Failed` 처럼 `CN=` 이 없는 행은 매칭되지 않는다.
  (`MwWebDomain.t__cn()` 은 `CN=` 이 없으면 subject 전체를 돌려주므로 그대로 쓰지 말고 `CN=` 유무를 먼저 본다.)
- CA 는 대상이 모수 전체라 `대상 수 == 모수` 다.

### 4.3 `mw_web_domain`·`mw_etc_ssl_domain` 에 `cn` 컬럼을 추가할지

**추가하지 않는다** (결정 2026-10-01). 조회할 때마다 `subject` 에서 CN 을 동적으로 파싱한다.

LEAF 매칭은 두 단계로 한다 — 모수 전체를 파싱하지 않는다:

1. SQL 로 후보만 가져온다: `subject ILIKE '%' || :cn || '%'` (`:cn` 의 `\`·`%`·`_` 는 이스케이프).
   `CN=` 을 붙이지 않는다 — `CN = a.co.kr` 처럼 `=` 앞뒤에 공백이 있는 subject 도 후보에 넣기 위해서다
2. 후보만 파이썬에서 CN 을 꺼내 **정확히** 비교한다 (대소문자 무시) — `CN=www.bank.com.kr` 같은 부분 일치를 버린다

CA 는 필터가 없으므로 이 단계가 없다.

| | 추가 안 함 (기본안) | 추가 |
| :--- | :--- | :--- |
| 매칭 | SQL `ILIKE` 로 후보 → 파이썬에서 CN 정확 비교 | SQL `lower(cn) = lower(:cn)` |
| 성능 | 후보 수 건만 파싱 — 문제 없음 | 인덱스 가능 |
| 바꿀 곳 | 없음 | `subject` 를 쓰는 저장 경로 전부에 `cn` 같이 저장 — `app/sqls/agent_dml.py` 223·310·334·390·399·438 행 부근(파일 기준·접속 기준·etc fallback·실패 처리) |
| DB | 없음 | 두 테이블 ALTER + 기존 행 backfill SQL (`subject` 에서 CN 추출) |
| 정합성 | `subject` 하나가 원본 | `subject` 와 `cn` 이 어긋날 수 있음 (경로 하나 빠뜨리면) |

추가가 필요해지는 경우: 모수가 수만 건 이상으로 늘거나, 다른 화면에서도 CN 으로 조회·필터할 때. 그때는 별도 과제로 한다.

### 4.4 행마다 "적용 여부" — 만료일로 식별

대상 행의 현재 인증서가 이 파일과 같은지 **만료일(`notafter`)** 로 판단한다. serial 은 쓰지 않는다.

| 인증서 | 같다의 기준 |
| :--- | :--- |
| `LEAF` | 행의 `notafter` == 파일 `notafter` |
| `CA` | 행의 `notafter_ca` == 파일 `notafter` |

- 비교는 **초 단위**. 행의 값은 Agent 가 `GMT + 9h` 로 바꾼 KST naive datetime 이다(`_get_ssl_datetime`, `app/sqls/agent_dml.py:238`).
  파일 쪽도 §3.4 대로 KST naive 로 저장하고 마이크로초를 버리므로 그대로 `==` 비교한다.
- 표시: `적용` / `미적용` / `미확인`(행의 만료일이 NULL). 상단 요약: `적용 a · 미적용 b · 미확인 c / 대상 N`. **이 인증서가 적용돼야 할 대상이 모수다** — 전체 모수(§4.1)는 보여 주지 않는다 (2026-10-01 결정).

### 4.5 화면

```
SSL 인증서 적용 현황
[인증서 선택 ▼ 2026.11-EV-bank (LEAF, CN=www.bank.com, ~2027-11-30 08:59:59)]

적용 9 · 미적용 2 · 미확인 1 / 대상 12

구분 | Landscape | Host  | Domain:Port       | 현재 Subject(CN) | 현재 만료일          | 적용여부
WEB  | PROD      | web01 | www.bank.com:443  | CN=www.bank.com  | 2026-11-30 08:59:59 | 미적용
ETC  | PROD      | was03 | www.bank.com:8443 | CN=www.bank.com  | 2027-11-30 08:59:59 | 적용
```

- Landscape: WEB 은 `mw_web.landscape`, ETC 는 `mw_server.landscape` (`host_id` 조인).
- 인증서 선택은 `/sslcertapplyview/?cert_id=<id>` 쿼리로도 들어올 수 있게 한다. 화면 1 의 목록에서 `적용 현황` 링크로 연결.
- 정렬: 적용여부(미적용 → 미확인 → 적용), Landscape(PROD → TEST → DEV), Domain.

### 4.6 REST

```
GET /api/v1/monitor/ssl_cert_apply/<cert_id>      @protect()
200 {
  "cert":    {"id", "cert_name", "cert_type", "cn", "notafter"},
  "summary": {"target": 12, "applied": 9, "not_applied": 2, "unknown": 1},
  "rows":    [{"source": "WEB"|"ETC", "landscape", "host_id", "domain", "subject", "notafter", "status"}]
}
404 — cert_id 없음
```

화면은 `HOWTO_014` 의 `ssl_cert_status.html` 처럼 이 API 를 AJAX 로 불러 그린다.
`MonitorRestApi` 에 붙이므로 기존 `monitor` 권한 체계를 따른다.

---

## 5. 메뉴·권한

`Monitor` 카테고리, `SSL인증서 만료 현황` 아래:

| 메뉴 | View |
| :--- | :--- |
| SSL 인증서 파일 | `SslCertFileModelView` |
| SSL 인증서 적용 현황 | `SslCertApplyView` (`BaseView`) |

새 권한(`can_list on SslCertFileModelView` 등)은 FAB 가 기동 시 만든다. 역할에 붙이는 건
[SPEC_002](SPEC_002_sync_role_permissions.md) 의 동기화 절차를 따른다.

> 지금은 **Admin 만** 두 화면을 쓴다 (FAB 가 새 권한을 Admin 에만 자동 부여). 다른 역할에 열지는 정하지 않았다 —
> 열게 되면 `20260930_grant_job_list_json.sql` 방식의 권한 SQL 을 따로 낸다.

---

## 6. 테스트

`test_unit_ssl_cert_parse.py`(파싱) · `test_ssl_cert_file_views.py`(화면 1) · `test_ssl_cert_apply.py`(화면 2·API).

인증서는 테스트 안에서 `cryptography` 로 만든다 (파일 커밋 안 함). S3 는 `S3FileManager.get_file` 을 monkeypatch.

| 대상 | 경우 |
| :--- | :--- |
| `parse_certificate` | PEM leaf / DER leaf / 중간 CA / 체인 2개 → 오류 / 루트 → 오류 / 개인키 포함 → 오류 / 쓰레기 바이트 → 오류 / 날짜 KST 변환 |
| 등록 | 정상 → 행 생성·추출값 저장 / 추출 실패 → flash 오류·행 없음 / 이름 31byte(한글) → 검증 오류 / 이름 중복 → 오류 |
| 수정 | `cert_name` 만 폼에 있음, 다른 값 안 바뀜 |
| 모수 | WEB 모수 == `get_cert_expiry_stat()[-1]['total']` / ETC 는 `use_yn=NO` 제외 |
| 적용 대상 | LEAF: bulk `CN=*.com.kr` 파일 ↔ `CN=*.com.kr` 행 매칭(`CN=www.a.com.kr` 행은 제외)·CN 대소문자 무시 매칭·부분 일치(`CN=a.com.kr`) 제외·`CN=` 없는 subject 제외·CN 에 `%`/`_` 포함 시 이스케이프 / CA: 모수 전체 |
| 적용 여부 | 만료일 초 단위 일치 → 적용 / 다르면 미적용 / NULL → 미확인. LEAF 는 `notafter`, CA 는 `notafter_ca` 와 비교 |
| API | 200 형식 / 404 / 미인증 401 |

---

## 7. DB 변경 — 운영은 SQL 파일

HOWTO_019 §6 과 같은 방식. 폐쇄망이라 `flask db upgrade` 를 안 쓴다.
`docs/sql/20261001_add_mw_ssl_cert_file.sql` (적용), `..._rollback.sql` (되돌리기). Alembic 리비전 `d2f7b3a91c6e` 도 같은 내용이다(`c4e8a2f19d3b` 다음).

SQL 은 테스트 DB 의 `create_all` 결과와 `pg_dump -s` 로 비교해 **스키마가 같음**을 확인했다. 적용·되돌리기 모두 두 번 실행해도 된다.

```sql
-- 적용 — 다시 실행해도 된다
BEGIN;
DO $$ BEGIN
    CREATE TYPE sslcerttypeenum AS ENUM ('LEAF', 'CA');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS mw_ssl_cert_file (
    id            SERIAL PRIMARY KEY,
    cert_name     VARCHAR(30)  NOT NULL UNIQUE,
    ag_file_id    INTEGER REFERENCES ag_file(id) ON DELETE SET NULL,
    file_name     VARCHAR(50)  NOT NULL,
    received_date DATE         NOT NULL,
    receiver_name VARCHAR(50)  NOT NULL,
    cert_type     sslcerttypeenum NOT NULL,
    subject       VARCHAR(300),
    cn            VARCHAR(200),
    serial        VARCHAR(100),
    issuer        VARCHAR(300),
    notbefore     TIMESTAMP WITHOUT TIME ZONE,
    notafter      TIMESTAMP WITHOUT TIME ZONE,
    user_id       VARCHAR(50)  NOT NULL,
    create_on     TIMESTAMP WITHOUT TIME ZONE NOT NULL
);
COMMENT ON TABLE mw_ssl_cert_file IS 'SSL 인증서 파일 (HOWTO_021)';
COMMIT;

-- 되돌리기
BEGIN;
DROP TABLE IF EXISTS mw_ssl_cert_file;
DROP TYPE IF EXISTS sslcerttypeenum;
COMMIT;
```

---

## 8. 결정 사항 (2026-10-01 확정)

| # | 내용 | 결정 |
| :--- | :--- | :--- |
| 1 | ETC 모수: `mw_etc_ssl_domain(use_yn=YES)` 로 하면 JEUS 통계(`cert_expiry_stat_jeus`, 리스너 기준)와 수가 다르다 | `mw_etc_ssl_domain(use_yn=YES)` |
| 2 | 체인 파일(leaf+중간 CA 한 파일) | 거부. 인증서 1개 파일만 |
| 3 | `ag_file` 삭제 시 | 인증서 행은 남기고 `ag_file_id` 만 NULL (`file_name` 은 남음) |
| 4 | 같은 인증서 중복 등록 | 허용 (이름만 유일) |
| 5 | `cn` 컬럼 추가 | 추가 안 함, 동적 파싱 (§4.3) |

---

## 9. 변경·신규 파일

| 파일 | 변경 |
| :--- | :--- |
| `app/models/common.py` | `SslCertTypeEnum` |
| `app/models/was.py` | `MwSslCertFile` |
| `app/models/agent.py` | `AgFile.__repr__` |
| `app/sqls/ssl_cert.py` | 신규 — `parse_certificate`, `cn_of`, `get_ssl_cert_apply` |
| `app/views/ssl_cert.py` | 신규 — `SslCertFileModelView`(`pre_add` 에서 추출), `SslCertApplyView`, 메뉴 |
| `app/__init__.py:134` | `from app.views import ... ssl_cert` 추가 |
| `tests/_certs.py` | 신규 — 테스트용 인증서 생성 (root → 중간 CA → leaf) |
| `app/api/monitor_api.py` | `/ssl_cert_apply/<cert_id>` |
| `app/templates/ssl_cert_apply.html` | 신규 |
| `migrations/versions/<rev>_.py` | 신규 |
| `docs/sql/20261001_add_mw_ssl_cert_file{,_rollback}.sql` | 신규 |
| `tests/test_unit_ssl_cert_parse.py`, `tests/test_ssl_cert_file_views.py`, `tests/test_ssl_cert_apply.py` | 신규 |
| `README.md` | 문서 목록에 이 HOWTO 추가 |

---

## 10. 만료 주의 메일 — [서버내부기능] `notify_ssl_cert_expiry`

Command Type 을 `[서버내부기능]` 으로 등록할 때 쓰는 함수. 주기 작업(예: 매일 08:00)으로 돌린다.

| 항목 | 내용 |
| :--- | :--- |
| 함수 이름 (`target_file_name`) | `notify_ssl_cert_expiry` |
| 파라미터 (`additional_params`) | JSON — `{"dday": [60, 30, 14, 7], "last_dday": 3}` (정수 배열, 정수) |
| 대상 | `mw_ssl_cert_file` 중 **남은 일수가 `dday` 중 하나와 같거나 `last_dday` 보다 작은** 인증서 |
| 남은 일수 | `notafter 날짜 − 오늘` (일 단위) |
| 제외 | **만료된 인증서** — 만료 시각이 실행 시각보다 이전이면 뺀다 (오늘 만료라도 시각이 지났으면 제외). 2026-10-01 결정 |
| 대상 없음 | 아무것도 하지 않는다 (지식·메일 없음) |
| 수신자 | `ut_tag.tag = '이메일-MW'` 의 `value1` (`,` 구분, 앞뒤 공백 제거) |
| 발송 방식 | ① Markdown **지식(`ut_md_content`)으로 등록** → ② 지식 메일 발송 기능(`send_md_content_email`, 화면의 [메일 발송]과 같은 함수)으로 보낸다 |

메일(=지식) 내용 — 남은 일수 적은 순:

```
# SSL 인증서 만료 주의 (2026-10-01)

| 인증서 | 구분 | CN | 만료일 | 남은 일수 | 적용 | 미적용 | 미확인 | 대상 |
| 2026.12-bulk | Leaf | *.com.kr | 2026-10-03 | 2 | 5 | 3 | 1 | 9 |
```

적용/미적용/미확인/대상 수는 적용 현황 화면(§4)과 같은 `get_ssl_cert_apply()` 로 센다.

| 결과 | `ag_command` 결과 (rtn, msg) |
| :--- | :--- |
| 보냄 | `1`, `N건, M명에게 발송 (지식 <content_id>)` |
| 대상 없음 | `1`, `만료 주의 대상 인증서가 없습니다.` |
| 파라미터 오류 | `0`, 형식 안내 |
| 수신자 없음 | `0` — 지식도 만들지 않는다 |
| 메일 실패 | `0` — **지식은 남긴다** (지식관리 화면에서 다시 보낼 수 있다) |

테스트: `tests/test_ssl_cert_notify.py` (21건).
