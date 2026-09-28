# SPEC_017 : 기타 SSL Domain 관리

## 1. 변경 배경

현재 `update_connect_ssl_by_api()` 함수는 Agent가 수집한 SSL 인증서 정보를 `mw_web_domain` 테이블에 업데이트한다.  
그러나 해당 `(host_id, domain_name, port)` 조합이 `mw_web_domain`에 존재하지 않는 경우 — **`mw_web`(WEBTOB) 자체가 등록되지 않은 서버이거나, WEBTOB는 있지만 해당 domain이 VHOST에 등록되지 않은 경우** — `update_rows()`가 `-1`을 반환하며 **정보가 유실**된다.

이 SPEC은 `mw_web_domain`에 매칭되지 않는 SSL 정보를 **별도 테이블 `mw_etc_ssl_domain`에 기록**하고, 이를 관리할 CRUD UI를 추가하는 것을 목적으로 한다.

---

## 2. 신규 테이블 설계

### 2.1. `mw_etc_ssl_domain`

| 컬럼명 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `id` | Integer | PK, NOT NULL | Primary Key |
| `host_id` | String(30) | FK(`mw_server.host_id`), NOT NULL | HOST ID |
| `domain_name` | String(100) | NOT NULL | Domain 이름 |
| `port` | String(10) | NOT NULL | 서비스 port |
| `notbefore` | DateTime | | 유효기간 시작 |
| `notafter` | DateTime | | 유효기간 만료 |
| `subject` | String(300) | | 주제(CN 포함) |
| `serial` | String(100) | | 일련번호 |
| `issuer` | String(300) | | 발급자 |
| `notbefore_ca` | DateTime | | 유효기간 시작(CA) — 당장 미사용 |
| `notafter_ca` | DateTime | | 유효기간 만료(CA) — 당장 미사용 |
| `subject_ca` | String(300) | | 주제(CA) — 당장 미사용 |
| `serial_ca` | String(100) | | 일련번호(CA) — 당장 미사용 |
| `issuer_ca` | String(300) | | 발급자(CA) — 당장 미사용 |
| `update_dt` | DateTime | | 최종 갱신 일시 |
| `description` | String(500) | | 설명(수동 입력) |
| `use_yn` | Enum(YnEnum) | NOT NULL, default=YES | 사용 여부 |
| `managed_yn` | Enum(YnEnum) | NOT NULL, default=NO | 미들웨어 관리 대상 여부 |
| `agent_id` | String(30) | | 수집 Agent ID |
| `user_id` | String(50) | NOT NULL | 최종 수정자 |
| `create_on` | DateTime | NOT NULL | 생성일시 |

**Unique Index**: `(host_id, domain_name, port)`  
**Foreign Key**: `host_id → mw_server.host_id`

---

## 3. 수정 대상 파일 목록

| # | 파일 | 변경 내용 |
|---|---|---|
| 1 | `app/models/was.py` | `MwEtcSslDomain` 모델 클래스 추가 |
| 2 | `app/sqls/agent_dml.py` | `update_connect_ssl_by_api()` 로직 수정 (fallback → `mw_etc_ssl_domain` upsert, `agent_id` 저장) |
| 3 | `app/views/was.py` | CRUD View 2개(활성/불용) + "Call Connect SSL" 액션 + 메뉴 등록 |

### 3.1. 기존 기능 영향 최소화 원칙

- `update_connect_ssl_by_api()` 기존 `mw_web_domain` 업데이트 로직은 **그대로 유지**, `rtn < 0` 일 때만 fallback
- 기존 `WebDomainModelView`는 **수정하지 않음**
- 신규 View는 별도의 `EtcSslDomainCommonView` 계열로 분리
- ~~`create_connect_ssl()` 함수는 수정 없이 **재사용**~~ — **무효 (2026-09-27)**. 설계 단계 서술이며, 실제 구현은 `create_connect_ssl_real_ip()` 를 쓴다. `create_connect_ssl()` 은 TASK 3-11 에서 제거했다.

---

## 4. 상세 구현 계획

### 4.1. Model 추가 (`app/models/was.py`)

`MwWebDomain` 클래스 바로 아래(line 1198 부근)에 `MwEtcSslDomain` 모델을 추가한다.

```python
class MwEtcSslDomain(Model):
    __tablename__ = "mw_etc_ssl_domain"
    t__table_comment = {"comment": "기타 SSL Domain"}
    function_comments = {"t__domain": "domain name : port"}

    id            = Column(Integer, primary_key=True, nullable=False, comment='Primary Key')
    host_id       = Column(String(30), ForeignKey('mw_server.host_id'), nullable=False, comment='HOST ID')
    domain_name   = Column(String(100), nullable=False, comment='Domain 이름')
    port          = Column(String(10), nullable=False, comment='서비스 port')
    notbefore     = Column(DateTime(), comment='유효기간시작')
    notafter      = Column(DateTime(), comment='유효기간만료')
    subject       = Column(String(300), comment='주제')
    serial        = Column(String(100), comment='일련번호')
    issuer        = Column(String(300), comment='발급자')
    notbefore_ca  = Column(DateTime(), comment='유효기간시작(CA)')
    notafter_ca   = Column(DateTime(), comment='유효기간만료(CA)')
    subject_ca    = Column(String(300), comment='주제(CA)')
    serial_ca     = Column(String(100), comment='일련번호(CA)')
    issuer_ca     = Column(String(300), comment='발급자(CA)')
    update_dt     = Column(DateTime())
    agent_id      = Column(String(30), comment='수집 Agent ID')
    description   = Column(String(500), comment='설명')
    use_yn        = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("YES"), nullable=False, comment='사용여부')
    managed_yn    = Column(Enum(YnEnum), info={'enum_class':YnEnum}, server_default=("NO"), nullable=False, comment='미들웨어 관리대상여부')
    user_id       = Column(String(50), default=get_user, nullable=False)
    create_on     = Column(DateTime(), default=datetime.now, nullable=False)

    UniqueConstraint(host_id, domain_name, port)

    @validates('host_id')
    def validate_host_id(self, key, host_id):
        if host_id:
            return host_id.lower()
        return host_id

    __table_args__ = (
        t__table_comment,
    )

    mw_server = relationship('MwServer')

    def t__domain(self):
        return self.domain_name + ':' + self.port

    def t__cn(self):
        subject = self.subject
        if not subject:
            return ''
        start = subject.find('CN=')
        if start < 0:
            result = ''
        else:
            subject = subject.replace('/', ',')
            end = subject[start:].find(',')
            if end < 0:
                end = len(subject[start:])
            result = subject[start:start+end]
        return result

    def __repr__(self):
        return self.domain_name + ':' + self.port
```

---

### 4.2. `update_connect_ssl_by_api()` 수정 (`app/sqls/agent_dml.py`)

#### 4.2.1. 변경 전 (현재 로직)

```python
return update_rows('mw_web_domain', update_dict, filter_dict)
```

#### 4.2.2. 변경 후 (fallback 로직 추가)

```python
rtn, msg = update_rows('mw_web_domain', update_dict, filter_dict)

# mw_web_domain에 해당 레코드가 없으면 → mw_etc_ssl_domain에 upsert
if rtn < 0:
    etc_filter = dict(
        host_id     = host_id,
        domain_name = domain,
        port        = port
    )

    etc_rec, _ = select_row('mw_etc_ssl_domain', etc_filter)

    etc_update = dict(**update_dict, agent_id=result.agent_id)

    if etc_rec:
        # 기존 레코드가 있으면 update
        rtn, msg = update_rows('mw_etc_ssl_domain', etc_update, etc_filter)
    else:
        # 신규 insert
        insert_dict = dict(**etc_filter, **etc_update)
        rtn, msg = insert_row('mw_etc_ssl_domain', insert_dict)
        if rtn > 0:
            msg = 'Inserted into mw_etc_ssl_domain'

return rtn, msg
```

**핵심 포인트**:
- 기존 `mw_web_domain` update 로직은 **변경 없음** (1차 시도)
- `rtn < 0` (매칭 실패) 일 때만 `mw_etc_ssl_domain`으로 fallback
- `result.agent_id`를 통해 수집 Agent 정보를 함께 저장
- `mw_web` 또는 `mw_web_domain`이 없는 경우 모두 동일하게 처리됨

---

### 4.3. View & Menu 추가 (`app/views/was.py`)

#### 4.3.1. 화면 구성 (WEBTOB Domain 목록과 동일 패턴)

**참조 화면**: `WebDomainModelView` (WEBTOB Domain 목록)

| 구성 요소 | WEBTOB Domain 목록 | 기타 SSL Domain | 비고 |
|---|---|---|---|
| 상단 검색 | HOSTNAME 입력 | HOSTNAME 입력 | **동일** |
| 상단 버튼 | SSL만 조회, SSL만료 임박 | SSL만료 임박 | ssl_yn 필터 불필요(전부 SSL) |
| 액션 버튼 | Call Connect SSL, Get Connect SSL | Call Connect SSL | `agent_id`로 직접 호출 |
| 목록 컬럼 | Host ID, Web서버, URL, SSL여부, SSL Cert File, 시작일, 만료일, CN, 확인일시 | Host ID, URL, 시작일, 만료일, CN, MW관리대상, 설명, 확인일시 | Web서버/SSL여부/SSL Cert File 제외 |

#### 4.3.2. View 클래스 코드

`WebDisusedModelView` 아래에 추가:

```python
class EtcSslDomainCommonView(ModelView):

    datamodel = SQLAInterface(MwEtcSslDomain)

    def almost_expired():
        now = datetime.now()
        plus_30 = now + timedelta(days=30)
        filter_str = f'_flt_1_notafter={now.strftime("%m/%d/%Y")}&_flt_2_notafter={plus_30.strftime("%m/%d/%Y")}'
        return filter_str

    list_template = 'listWithJson.html'
    list_widget   = ListAdvanced

    list_columns = ['host_id', 't__domain', 'notbefore', 'notafter',
                    't__cn', 'managed_yn', 'description', 'update_dt']
    label_columns = {
        'host_id': 'Host ID',
        't__domain': 'URL',
        'notbefore': '시작일',
        'notafter': '만료일',
        't__cn': 'CN',
        'managed_yn': 'MW관리대상',
        'description': '설명',
        'update_dt': '확인일시',
        'use_yn': '사용여부',
        'domain_name': 'Domain',
        'port': 'Port',
    }

    edit_columns = ['host_id', 'domain_name', 'port', 'description',
                    'use_yn', 'managed_yn']
    add_columns  = ['host_id', 'domain_name', 'port', 'description',
                    'use_yn', 'managed_yn']

    search_columns = ['host_id', 'domain_name', 'notafter', 'update_dt',
                      'managed_yn']

    search_filters = {
        'notafter': [FilterIsNull, FilterGreater, FilterSmaller],
        'update_dt': [FilterIsNull, FilterGreater, FilterSmaller]
    }

    formatters_columns = {
        'update_dt': lambda x: x.strftime('%Y.%m.%d %H:%M') if x else '',
        'notafter': lambda x: x.strftime('%Y-%m-%d') if x else '',
        'notbefore': lambda x: x.strftime('%Y-%m-%d') if x else '',
    }

    extra_args = {
        'inputList': [
            {'text': 'HOSTNAME', 'id': 'host-name', 'combind': '0',
             'condition': '_flt_2_host_id=', 'size': 20}
        ],
        'buttonList': [
            {'text': 'SSL만료 임박', 'id': 'toggle_bt1', 'bt_group': '1',
             'onclick': almost_expired()}
        ],
    }

    base_order = ('host_id', 'asc')

    @action("call_connect_ssl", "Call Connect SSL", "", "fa-rocket", single=False)
    def callConnectSSL(self, items):
        for item in items:
            if not item.agent_id:
                continue

            agent_rec = get_agent(item.agent_id)

            if not agent_rec:
                continue

            insert_command_master('CALL.GET_SSL_CERTI',
                                 [agent_rec.agent_id],
                                 item.domain_name + ':' + item.port)

        db.session.commit()
        self.update_redirect()
        return redirect(self.get_redirect())


class EtcSslDomainModelView(EtcSslDomainCommonView):
    list_title = "기타 SSL Domain"
    base_filters = [['use_yn', FilterEqual, 'YES']]


class EtcSslDomainDisusedModelView(EtcSslDomainCommonView):
    list_title = "불용 기타 SSL Domain"
    base_filters = [['use_yn', FilterEqual, 'NO']]
    base_permissions = ['can_list', 'can_show', 'can_edit', 'can_delete']
```

**"Call Connect SSL" 액션 동작 원리**:

```
UI 클릭 → Command 생성 → Agent 수신 → SSL 접속 → Result 전송 → update_connect_ssl_by_api()
              ↓                                                            ↓
     'CALL.GET_SSL_CERTI'                                    mw_web_domain UPDATE
         (ExeAgentFunc)                                   (매칭 실패 시 → mw_etc_ssl_domain upsert)
```

1. 사용자가 레코드 선택 → "Call Connect SSL" 클릭
2. `insert_command_master('CALL.GET_SSL_CERTI', [agent_id], 'domain:port')` → `ag_command_master` + `ag_command_detail` 생성
3. Agent가 주기적 Polling으로 Command 수신 (`command_class=ExeAgentFunc`, `target_file_name=get_ssl_certi`)
4. Agent가 서버에서 `openssl s_client -connect domain:port` 동등 작업 수행 → SSL 인증서 정보 추출
5. Agent가 Result를 JSON으로 전송 → `ag_result` 저장
6. `ag_autorun_result` 매핑에 의해 `update_connect_ssl_by_api()` 자동 호출

**기존 View와의 차이점**:
- `WebDomainModelView.callConnectSSL`은 `item.mw_web_vhost.mw_web.agent_id`로 agent를 찾음 (WEBTOB 경유)
- `EtcSslDomainCommonView.callConnectSSL`은 `item.agent_id`를 직접 사용 (mw_web 없으므로)
- `agent_id`가 없는 레코드는 skip (수동 등록 시 agent가 없을 수 있음)

**전제조건** (이미 등록되어 있어야 하는 데이터):

1. **Command 유형** (`Agent&Command > Command 유형` 메뉴)

| 항목 | 값 |
|---|---|
| Command Type Id | `CALL.GET_SSL_CERTI` |
| Command Type 설명 | SSL 인증서 접속 조회 |
| 호출되는 기능 | `ExeAgentFunc` |
| 파일명(기능명) | `get_ssl_certi` |

2. **Result 자동실행 목록** (`Agent&Command > Command 처리결과 자동 반영 설정` 메뉴)

| 항목 | 값 |
|---|---|
| 자동실행 JOB ID | (임의 지정) |
| 자동실행 Type | `FILENAME` |
| 대상파일/기능 | `get_ssl_certi` |
| Command ID | (빈 값) |
| 자동실행 기능 | `update_connect_ssl_by_api` |
| Parameter | (빈 값) |

- 위 두 항목은 기존 WEBTOB Domain 목록의 "Call Connect SSL" 기능을 위해 **이미 등록되어 있으므로 별도 작업 불필요**


#### 4.3.3. 메뉴 등록

`"WEBTOB 불용 목록"` 메뉴 등록 코드 아래에 추가:

```python
appbuilder.add_separator("Web")
appbuilder.add_view(
    EtcSslDomainModelView,
    "기타 SSL Domain",
    icon="fa-globe",
    category="Web"
)
appbuilder.add_view(
    EtcSslDomainDisusedModelView,
    "불용 기타 SSL Domain",
    icon="fa-trash-o",
    category="Web"
)
```

**메뉴 위치**: Web > ... > WEBTOB 불용 목록 > (separator) > 기타 SSL Domain / 불용 기타 SSL Domain

---

### 4.4. Import 추가

| 파일 | 추가 import |
|---|---|
| `app/views/was.py` (line 12-15) | `MwEtcSslDomain`을 기존 model import 라인에 추가 |
| `app/sqls/agent_dml.py` | 이미 사용 중인 `select_row`, `insert_row` 확인 (추가 불필요) |

---

### 4.5. WAS Http Listener 연동 (MwWasHttpListener)

**1) 연결(Association) 테이블 추가**
`mw_was_httplistener` 와 `mw_etc_ssl_domain` 간 N:M 연결을 위한 `assoc_httplistener_etcssldomain` 테이블을 추가한다.

**2) "Call Connect SSL" 액션 추가**
- 메뉴 위치: `Web > WAS Http Listener 목록`
- 버튼 아이콘: `fa-rocket`
- **조회 및 실행 조건**:
  - `ssl_yn == 'YES'` 이고 `domain_name` 이 존재하는 경우에만 실행
  - 조건 불만족 시 알림 메세지(Flash) 출력: `"SSL 대상이 아니거나 도메인명이 설정되지 않았습니다. ({도메인명}:{포트})"`

**3) Agent 선택 및 우선순위 로직**
해당 HTTP Listener의 WAS Instance(`item.mw_was_instance`)가 위치한 `host_id` 를 기반으로 Agent를 선택한다.
- `agent_id` 가 해당 `host_id` 문자열을 **포함**하는지 검사
- 매칭되는 Agent가 여러 개일 경우 `"_jeus"` 문자열이 포함된 Agent를 우선 선택
- 그래도 일치하는 것이 여러개일 경우 알파벳 순으로 첫번째 Agent 선택
- 해당하는 Agent가 없으면 알림 메세지 출력: `"해당 서버({host_id})에 사용 가능한 Agent가 존재하지 않습니다."`

**4) 사전 데이터 및 연결 생성 로직**
Command Master 생성 전, `mw_etc_ssl_domain` 에 데이터가 기록되어 있어야 한다.
- 선택된 Host_ID, Domain, Port 기반으로 `mw_etc_ssl_domain` 조회
- 데이터가 존재하지 않으면 **신규 생성**:
  - `managed_yn = "YES"`
  - `use_yn = "YES"`
  - `agent_id = 선택된 Agent ID`
- `mw_was_httplistener`와의 연결(`append()`) 정보 저장 (이미 연결되어 있지 않은 경우)
- DB Commit 수행

**5) 명령(Command) 생성**
- 앞서의 확인 작업이 완료되면 `insert_command_master('CALL.GET_SSL_CERTI', [선택된 agent_id], domain:port)` 를 통해 명령 생성
- 이후 `ag_autorun_result`의 룰에 따라 Agent가 인증서 정보를 수집한 후 결과를 전송하면, 기존 구축된 `update_connect_ssl_by_api()`의 fallback 로직이 동작해 `mw_etc_ssl_domain`을 업데이트한다.

---

## 5. DB Migration SQL

```sql
CREATE TABLE mw_etc_ssl_domain (
    id SERIAL PRIMARY KEY,
    host_id VARCHAR(30) NOT NULL REFERENCES mw_server(host_id),
    domain_name VARCHAR(100) NOT NULL,
    port VARCHAR(10) NOT NULL,
    notbefore TIMESTAMP,
    notafter TIMESTAMP,
    subject VARCHAR(300),
    serial VARCHAR(100),
    issuer VARCHAR(300),
    notbefore_ca TIMESTAMP,
    notafter_ca TIMESTAMP,
    subject_ca VARCHAR(300),
    serial_ca VARCHAR(100),
    issuer_ca VARCHAR(300),
    update_dt TIMESTAMP,
    agent_id VARCHAR(30),
    description VARCHAR(500),
    use_yn VARCHAR(3) NOT NULL DEFAULT 'YES',
    managed_yn VARCHAR(3) NOT NULL DEFAULT 'NO',
    user_id VARCHAR(50) NOT NULL,
    create_on TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (host_id, domain_name, port)
);

COMMENT ON TABLE mw_etc_ssl_domain IS '기타 SSL Domain';
COMMENT ON COLUMN mw_etc_ssl_domain.host_id IS 'HOST ID';
COMMENT ON COLUMN mw_etc_ssl_domain.domain_name IS 'Domain 이름';
COMMENT ON COLUMN mw_etc_ssl_domain.port IS '서비스 port';
COMMENT ON COLUMN mw_etc_ssl_domain.notbefore IS '유효기간시작';
COMMENT ON COLUMN mw_etc_ssl_domain.notafter IS '유효기간만료';
COMMENT ON COLUMN mw_etc_ssl_domain.subject IS '주제';
COMMENT ON COLUMN mw_etc_ssl_domain.serial IS '일련번호';
COMMENT ON COLUMN mw_etc_ssl_domain.issuer IS '발급자';
COMMENT ON COLUMN mw_etc_ssl_domain.notbefore_ca IS '유효기간시작(CA)';
COMMENT ON COLUMN mw_etc_ssl_domain.notafter_ca IS '유효기간만료(CA)';
COMMENT ON COLUMN mw_etc_ssl_domain.subject_ca IS '주제(CA)';
COMMENT ON COLUMN mw_etc_ssl_domain.serial_ca IS '일련번호(CA)';
COMMENT ON COLUMN mw_etc_ssl_domain.issuer_ca IS '발급자(CA)';
COMMENT ON COLUMN mw_etc_ssl_domain.agent_id IS '수집 Agent ID';
COMMENT ON COLUMN mw_etc_ssl_domain.description IS '설명';
COMMENT ON COLUMN mw_etc_ssl_domain.use_yn IS '사용여부';
COMMENT ON COLUMN mw_etc_ssl_domain.managed_yn IS '미들웨어 관리대상여부';
```

---

## 6. 작업 순서

| 순서 | 작업 | 파일 |
|---|---|---|
| 1 | Model 클래스 추가 및 Association 생성 | `app/models/was.py` |
| 2 | `agent_dml.py` 로직 수정 (fallback + agent_id 저장) | `app/sqls/agent_dml.py` |
| 3 | View 및 액션 구현 (EtcSslDomain, HttpListener) | `app/views/was.py` |
| 4 | DB Migration SQL 실행 | PostgreSQL (mwm-db) |
| 5 | Docker 재빌드 & 테스트 | `docker compose` |
| 6 | 버전 업데이트 | `config.py` |

---

## 7. 검증 포인트

1. `update_connect_ssl_by_api()` 호출 시 `mw_web_domain`에 매칭되지 않는 데이터가 `mw_etc_ssl_domain`에 **insert** 되는지 확인
2. 동일 `(host_id, domain_name, port)` 데이터가 재수집될 때 **update** 되는지 확인
3. `mw_web` 자체가 없는 서버의 SSL 데이터도 정상 기록되는지 확인
4. UI에서 CRUD(생성/조회/수정/삭제)가 정상 동작하는지 확인
5. `use_yn=NO` 레코드가 "불용 기타 SSL Domain" 메뉴에서만 조회되는지 확인
6. "Call Connect SSL" 액션이 `agent_id`를 통해 정상 작동하는지 확인
7. `agent_id`가 없는 레코드(수동 등록)에서 "Call Connect SSL" 클릭 시 오류 없이 skip 되는지 확인
8. `host_id`가 `mw_server`에 존재하지 않는 값일 경우 FK 위반 에러 발생 확인
9. HOSTNAME 검색 조건으로 필터링이 정상 작동하는지 확인
10. 기존 `WebDomainModelView` (WEBTOB Domain 목록) 화면이 **변경 없이** 정상 동작하는지 확인
