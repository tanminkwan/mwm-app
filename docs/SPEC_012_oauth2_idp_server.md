# SPEC_012: OAuth2 IDP Server (Authlib 기반) 구축 및 mwm-app 연계

> **날짜**: 2026-03-28  
> **버전**: `미들웨어관리소(VER:20260328.002)`  
> **변경 요약**: Authlib 기반 OAuth2 IDP 서버를 OIDC(OpenID Connect) 표준으로 확장하여 ID Token 발급, Discovery 엔드포인트 및 JWKS 지원을 추가한다.

---

## 1. 변경 배경

- 현재 mwm-app은 Flask-AppBuilder의 `AUTH_DB` 방식을 사용하여 자체 DB(`ab_user` 테이블)에서 사용자 인증을 수행하고 있음.
- **문제점**:
  - 인증 체계가 mwm-app에 종속되어, 향후 다른 서비스와의 SSO(Single Sign-On) 확장이 불가능함.
  - 사용자 관리(가입, 비밀번호 정책 등)가 애플리케이션 로직과 결합되어 있음.
- **해결책**:
  - Authlib 기반 **독립 OAuth2 IDP 서버**를 별도 컨테이너 + **독립 데이터베이스**로 구축한다.
  - IDP는 자체 사용자 관리(UI/API) 및 OAuth2 토큰 발급을 전담한다.
  - IDP는 **범용 외부 DB 동기화 기능**을 통해 기존 `mwm-db.mw.ab_user` 등의 사용자를 자동으로 가져올 수 있다.
  - mwm-app은 IDP를 통해 OAuth2 Authorization Code Flow로 인증을 수행한다.

---

## 2. 시스템 아키텍처

### 2-1. 컨테이너 및 DB 구성

```
┌──────────────┐     OAuth2 Flow     ┌──────────────┐
│              │ ◄─────────────────► │              │
│   mwm-app    │                     │   mwm-idp    │
│  (Flask-     │  Authorization Code │  (Authlib    │
│   AppBuilder)│  + Token Exchange   │   OAuth2     │
│  :8000       │                     │   Server)    │
│              │                     │  :5000       │
└──────┬───────┘                     └──────┬───────┘
       │                                    │
       │         ┌──────────────┐           │
       │         │   mwm-db     │           │
       │         │ (PostgreSQL) │           │
       │         │              │           │
       │         │  ┌────────┐  │           │
       └────────►│  │ DB: mw │  │           │
                 │  │ab_user │  │           │
                 │  └────────┘  │           │
                 │              │           │
                 │  ┌────────┐  │           │
                 │  │DB: idp │◄─┼───────────┘
                 │  │idp_user│  │
                 │  └────────┘  │
                 │              │
                 └──────────────┘
```

- **mwm-idp**: OAuth2 Authorization Server. 독립 DB(`idp`)를 사용
- **mwm-app**: OAuth2 Client로 동작. 기존 DB(`mw`)를 그대로 사용
- **mwm-db**: 동일 PostgreSQL 인스턴스 내에 `mw` DB와 `idp` DB가 **별도 데이터베이스**로 공존
- **동기화**: mwm-idp가 `mw` DB의 `ab_user` 테이블을 **읽어서** `idp` DB의 `idp_user`로 동기화 (범용 JSON 설정 기반)

### 2-2. OAuth2 Authorization Code Flow

```
[사용자 브라우저]
     │
     ├─(1) mwm-app 접속 (로그인 필요)
     │
     ├─(2) mwm-app → mwm-idp 로그인 페이지로 Redirect
     │     GET /oauth/authorize?response_type=code&client_id=mwm-app&redirect_uri=...
     │
     ├─(3) 사용자가 mwm-idp에서 ID/PW 입력 후 로그인
     │
     ├─(4) mwm-idp → mwm-app callback URL로 Redirect (Authorization Code 포함)
     │     GET /oauth-authorized/idp?code=XXXXX
     │
     ├─(5) mwm-app → mwm-idp 토큰 교환 (Server-to-Server)
     │     POST /oauth/token (code + client_secret)
     │     ← Access Token + Refresh Token
     │
     ├─(6) mwm-app → mwm-idp 사용자 정보 조회
     │     GET /api/userinfo (Bearer Token)
     │     ← { username, email, first_name, last_name, roles }
     │
     └─(7) mwm-app: ab_user 동기화 + 세션 생성 → 메인 화면
```

---

## 3. IDP 서버 설계 (mwm-idp)

### 3-1. 프로젝트 구조

```
mw_app/
├── idp/
│   ├── app/                 # IDP 서비스 코어 (Flask app)
│   │   ├── __init__.py      # Flask app factory
│   │   ├── config.py        # IDP 설정 (DB URI, SECRET_KEY, SYNC_SOURCES 등)
│   │   ├── run.py           # IDP 서버 진입점
│   │   ├── routes.py        # 인증 엔드포인트 (/oauth/authorize, /oauth/token 등)
│   │   ├── api.py           # REST API (/api/userinfo, /api/sync 등)
│   │   ├── models.py        # DB 모델 (IdpUser, OAuth2Client 등)
│   │   ├── services/        # 비즈니스 로직 계층 (SOLID: SRP)
│   │   ├── repositories/    # 데이터 접근 계층 (SOLID: DIP)
│   │   └── templates/       # UI 템플릿
│   ├── tests/               # IDP 전용 테스트 (pytest)
│   │   ├── conftest.py      # 공통 Fixture
│   │   ├── test_models.py
│   │   ├── test_oauth2.py
│   │   └── ...
│   ├── requirements.txt     # IDP 전용 의존성
│   ├── Dockerfile.idp       # IDP Docker 이미지 (Context: ./idp/)
│   └── create_idp_db.sql    # IDP 전용 DB 초기화 SQL
└── docker-compose.yml       # mwm-idp 서비스 정의 (Context: ./idp/)
```

### 3-2. 독립 DB 구성

IDP는 동일 PostgreSQL 인스턴스(`mwm-db`) 내에 **별도 데이터베이스(`idp`)**를 생성하여 사용한다.

```sql
-- create_db.sql 에 추가
CREATE DATABASE idp;
GRANT ALL PRIVILEGES ON DATABASE idp TO mwm;
```

### 3-3. IDP 핵심 DB 모델 (`idp/models.py`)

| 테이블 | 설명 | 주요 컬럼 |
|--------|------|-----------|
| `idp_user` | IDP 사용자 | id, username, password_hash, email, first_name, last_name, active, roles(JSON), api_key, sync_source, sync_id, created_on, updated_on |
| `oauth2_client` | OAuth2 클라이언트 등록 | id, client_id, client_secret, client_name, redirect_uris, grant_types, scope, policy_mapping(JSON) |
| `oauth2_token` | 발급된 Access/Refresh Token | id, token_type, access_token, refresh_token, scope, expires_in, user_id, client_id |
| `oauth2_code` | Authorization Code (임시) | id, code, client_id, redirect_uri, scope, user_id, expires_at |

**`idp_user` 주요 컬럼 설명:**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `username` | VARCHAR(64), UNIQUE | 로그인 ID |
| `password_hash` | VARCHAR(256) | bcrypt 해시. 동기화 사용자는 외부 비밀번호 그대로 복사 또는 NULL |
| `email` | VARCHAR(320), UNIQUE | 이메일 |
| `first_name` | VARCHAR(64) | 이름 |
| `last_name` | VARCHAR(64) | 성 |
| `active` | BOOLEAN | 활성 여부 |
| `roles` | JSON | 역할 목록 (예: `["Admin", "mw_rgroup"]`) |
| `api_key` | VARCHAR(64), UNIQUE | 관리자 전용 REST API 접근 키 (Bearer 토큰) |
| `sync_source` | VARCHAR(50), NULL | 동기화 출처 식별자 (예: `"mwm_app"`, NULL이면 IDP 직접 생성) |
| `sync_id` | VARCHAR(100), NULL | 원본 테이블의 PK 또는 고유 식별값 |

### 3-4. IDP API 엔드포인트

**OAuth2 엔드포인트:**

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/oauth/authorize` | Authorization Code 요청 (로그인 페이지 표시) |
| POST | `/oauth/authorize` | 사용자 인증 처리 및 Code 발급 |
| POST | `/oauth/token` | Authorization Code → Access Token 교환 |
| GET | `/api/userinfo` | Access Token으로 사용자 정보 조회 |
| GET | `/logout` | RP-Initiated Logout (OIDC 세션 종료) |

**사용자 관리 API:**

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/api/users` | 사용자 목록 조회 |
| POST | `/api/users` | 사용자 생성 |
| GET | `/api/users/<id>` | 사용자 상세 조회 |
| PUT | `/api/users/<id>` | 사용자 수정 |
| DELETE | `/api/users/<id>` | 사용자 삭제 |

**동기화 API:**

| Method | URL | 설명 |
|--------|-----|------|
| POST | `/api/sync/<source_name>` | 지정된 소스의 동기화 실행 |
| GET | `/api/sync/status` | 마지막 동기화 결과 조회 |

**사용자 관리 UI:**

| URL | 설명 |
|-----|------|
| `/` | 사용자 본인 정보 메인 대시보드 |
| `/admin/settings` | **중앙 관리자 콘솔** (Client, API Key, Sync 통합 관리) |
| `/admin/clients` | OAuth2 Client 관리 화면 (어드민 내 포함) |

---

## 4. 범용 외부 DB 동기화 설계

### 4-1. 설계 원칙

- IDP는 **외부 데이터베이스의 사용자 정보를 읽어와서** 자체 `idp_user` 테이블에 동기화함.
- 동기화 대상 DB의 접속 정보, 테이블명, 컬럼 매핑을 **JSON 상수**로 관리하여 범용성을 확보함.
- 복수의 외부 소스를 등록하여 여러 시스템의 사용자를 통합 관리할 수 있음.

### 4-2. 동기화 설정 (`idp/config.py`)

```python
# 외부 DB 동기화 소스 정의
# 여러 소스를 등록하여 다양한 시스템에서 사용자를 동기화할 수 있음
SYNC_SOURCES = {
    "mwm_app": {
        "description": "미들웨어관리소(mwm-app) 사용자",
        "db_uri": os.getenv("SYNC_MWM_DB_URI",
                            "postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@mwm-db:5432/mw"),
        "table": "ab_user",
        "id_column": "id",                    # 원본 PK (sync_id에 저장)
        "column_mapping": {
            "username":      "username",       # idp_user 컬럼: 원본 컬럼
            "email":         "email",
            "first_name":    "first_name",
            "last_name":     "last_name",
            "password_hash": "password",       # 해시값 그대로 복사
            "active":        "active"
        },
        "role_source": {
            "type": "join",                    # "join" | "column" | "static"
            "join_table": "ab_user_role",       # 사용자-역할 매핑 테이블
            "join_user_column": "user_id",     # ab_user.id 참조 컬럼
            "join_role_column": "role_id",     # ab_role.id 참조 컬럼
            "role_table": "ab_role",           # 역할 테이블
            "role_id_column": "id",            # 역할 PK
            "role_name_column": "name"         # 역할 이름 컬럼
        },
        "filter": "active = true",             # 동기화 대상 필터 (SQL WHERE 조건)
        "sync_password": true,                 # 비밀번호 해시도 복사할지 여부
        "auto_sync_interval_minutes": 0        # 0이면 수동만 (양수이면 주기적 자동 동기화)
    }
    # 추가 소스 예시:
    # "other_system": {
    #     "description": "또 다른 시스템 사용자",
    #     "db_uri": "postgresql://user:pass@other-db:5432/otherdb",
    #     "table": "users",
    #     "id_column": "user_id",
    #     "column_mapping": {
    #         "username": "login_id",
    #         "email":    "email_address",
    #         "first_name": "name",
    #         "last_name": "''",            # 빈 문자열 리터럴로 고정
    #         "active":   "is_active"
    #     },
    #     "role_source": {
    #         "type": "static",             # 모든 동기화 사용자에 고정 역할 부여
    #         "roles": ["viewer"]
    #     },
    #     "filter": "is_active = 1",
    #     "sync_password": false,
    #     "auto_sync_interval_minutes": 60
    # }
}
```

### 4-3. 동기화 엔진 (`idp/sync.py`)

```python
def sync_users(source_name: str) -> dict:
    """
    SYNC_SOURCES[source_name] 설정을 읽어 외부 DB에서 사용자 정보를 가져와
    idp_user 테이블에 upsert(insert or update)한다.

    동기화 규칙:
    1. 외부 테이블에서 column_mapping에 정의된 컬럼만 SELECT
    2. filter 조건 적용
    3. sync_source + sync_id 기준으로 기존 레코드 존재 여부 판단
       - 존재: UPDATE (변경된 필드만)
       - 미존재: INSERT
    4. 외부에서 삭제된 사용자: idp_user.active = false 처리 (물리 삭제 안함)
    5. role_source 설정에 따라 roles JSON 필드 갱신

    Returns:
        {"created": N, "updated": N, "deactivated": N, "errors": [...]}
    """
```

### 4-4. 동기화 흐름도

```
[POST /api/sync/mwm_app]
     │
     ├─(1) config.py의 SYNC_SOURCES["mwm_app"] 설정 로드
     │
     ├─(2) 외부 DB 접속 (db_uri 사용, SQLAlchemy create_engine)
     │
     ├─(3) SQL 실행:
     │     SELECT {id_column}, {mapped_columns...}
     │       FROM {table}
     │      WHERE {filter}
     │
     ├─(4) role_source 처리:
     │     ├─ type="join":  JOIN 쿼리로 역할 목록 조회
     │     ├─ type="column": 특정 컬럼값을 역할로 변환
     │     └─ type="static": 고정 역할 부여
     │
     ├─(5) idp_user Upsert:
     │     ├─ sync_source="mwm_app", sync_id={id_column값} 기준
     │     ├─ 존재하면 → UPDATE (변경 필드만)
     │     └─ 미존재 → INSERT
     │
     ├─(6) 외부에서 삭제된 사용자 비활성화:
     │     idp_user WHERE sync_source="mwm_app"
     │       AND sync_id NOT IN (외부 조회 결과)
     │     → active = false
     │
     └─(7) 결과 반환:
           {"created": 5, "updated": 3, "deactivated": 1, "errors": []}
```

### 4-6. REST API 보안 (API Key)
IDP의 관리용 API는 권한이 검증된 사용자의 **`api_key`**를 통한 Bearer 인증을 수행한다.
- **인증 헤더**: `Authorization: Bearer <mwm_sk_...>`
- **보안 로직**: `api_key` 일치 여부 확인 후, 해당 사용자가 `Admin` 또는 `PowerUser` 역할인지 최종 검증.

### 4-7. 관리자 콘솔 (Admin Console)
복잡한 수동 조작을 배제하기 위해 통합 UI를 제공한다.
- **동기화 트리거**: 단일 버튼 클릭으로 `sync_users("mwm_app")` 엔진 가동.
- **시스템 모니터링**: 등록된 전체 사용자의 Role 및 Sync 상태를 Read-only 리스트로 제공.

### 4-5. 동기화 정책

| 항목 | 정책 |
|------|------|
| Upsert 기준 | `sync_source` + `sync_id` 복합키 |
| 충돌 처리 | 동일 `username`이 다른 소스에서 이미 존재하면 **에러** 반환 (수동 해결 필요) |
| 비밀번호 | `sync_password: true`이면 해시값 그대로 복사. `false`이면 NULL (IDP에서 별도 설정 필요) |
| 삭제 정책 | 물리 삭제 안함. `active = false`로 비활성화 |
| IDP 직접 생성 사용자 | `sync_source = NULL`. 동기화 대상에서 제외 |
| 역할(Role) | JSON 배열로 저장. mwm-app의 FAB Role 이름과 동일하게 매핑 |

---

## 5. mwm-app 변경 사항

### 5-1. config.py 변경

```python
# 변경 전
AUTH_TYPE = AUTH_DB

# 변경 후
AUTH_TYPE = AUTH_OAUTH

# 사용자 자동 등록 활성화
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Public"

OAUTH_PROVIDERS = [
    {
        'name': 'idp',
        'icon': 'fa-key',
        'token_key': 'access_token',
        'remote_app': {
            'client_id': 'mwm-app',
            'client_secret': os.getenv('IDP_CLIENT_SECRET', 'mwm-app-secret'),
            'api_base_url': os.getenv('IDP_API_URL', 'http://mwm-idp:5000/'),
            'access_token_url': os.getenv('IDP_TOKEN_URL', 'http://mwm-idp:5000/oauth/token'),
            'authorize_url': os.getenv('IDP_AUTHORIZE_URL', 'http://localhost:5000/oauth/authorize'),
            'client_kwargs': {
                'scope': 'openid profile email',
            },
        }
    }
]
```

> **주의**: `authorize_url`은 **브라우저가 접근하는 URL**이므로 `localhost` 또는 외부 도메인을 사용.  
> `access_token_url`, `api_base_url`은 **컨테이너 간 통신**이므로 Docker 서비스명(`mwm-idp`) 사용.

### 5-2. Custom Security Manager (`app/security.py` 신규)

```python
from flask_appbuilder.security.sqla.manager import SecurityManager

class CustomSecurityManager(SecurityManager):
    def oauth_user_info(self, provider, response=None):
        """IDP의 /api/userinfo 응답을 FAB 사용자 정보로 매핑"""
        if provider == 'idp':
            me = self.appbuilder.sm.oauth_remotes[provider].get('api/userinfo')
            data = me.json()
            return {
                'username': data.get('username'),
                'first_name': data.get('first_name', ''),
                'last_name': data.get('last_name', ''),
                'email': data.get('email', ''),
                'role_keys': data.get('roles', []),
            }
        return {}
```

### 5-3. app/__init__.py 변경

```python
from app.security import CustomSecurityManager

appbuilder = AppBuilder(
    app, db.session,
    indexview=MyIndexView,
    security_manager_class=CustomSecurityManager  # 추가
)
```

### 5-4. mwm-app 사용자 동기화 정책

| 항목 | 정책 |
|------|------|
| 신규 사용자 | IDP에서 최초 로그인 시 `ab_user`에 자동 생성 (`AUTH_USER_REGISTRATION = True`) |
| 사용자 정보 | 매 로그인 시 IDP의 userinfo로 `first_name`, `last_name`, `email` 갱신 |
| Role 매핑 | IDP의 `roles` 필드 → FAB의 Role name 매칭. 일치하는 Role이 있으면 자동 할당 |
| 기본 Role | IDP에서 role 정보가 없으면 `AUTH_USER_REGISTRATION_ROLE` (기본: `Public`) 할당 |
| 비밀번호 | `ab_user.password`는 NULL. 인증은 IDP가 전담 |

---

## 6. Docker 구성

### 6-1. create_db.sql 추가

```sql
-- 기존
CREATE USER mwm WITH ENCRYPTED PASSWORD '<비밀번호>';
CREATE DATABASE mw OWNER mwm;

-- 추가
CREATE DATABASE idp OWNER mwm;
```

### 6-2. Dockerfile.idp

```dockerfile
FROM python:3.12.4-slim-bookworm

WORKDIR /app

COPY idp/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY idp/ .

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "run:app"]
```

### 6-3. docker-compose.yml 추가 서비스

```yaml
  mwm-idp:
    container_name: mwm-idp
    image: mwm-idp
    build:
      context: .
      dockerfile: Dockerfile.idp
    depends_on:
      - mwm-db
    ports:
      - 5000:5000
    environment:
      TZ: Asia/Seoul
      IDP_DATABASE_URI: "postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@mwm-db:5432/idp"
      IDP_SECRET_KEY: ${IDP_SECRET_KEY}
      IDP_MWM_CLIENT_ID: "mwm-app"
      IDP_MWM_CLIENT_SECRET: "mwm-app-secret"
      IDP_MWM_REDIRECT_URI: "http://localhost:8000/oauth-authorized/idp"
      SYNC_MWM_DB_URI: "postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@mwm-db:5432/mw"
    links:
      - mwm-db
```

### 6-4. mwm-app 환경변수 추가

```yaml
  mwm-app:
    environment:
      # ... 기존 환경변수 유지 ...
      IDP_CLIENT_SECRET: "mwm-app-secret"
      IDP_API_URL: "http://mwm-idp:5000/"
      IDP_TOKEN_URL: "http://mwm-idp:5000/oauth/token"
      IDP_AUTHORIZE_URL: "http://localhost:5000/oauth/authorize"
    depends_on:
      - mwm-idp   # 추가
    links:
      - mwm-idp   # 추가
```

---

## 7. IDP 전용 의존성 (`idp/requirements.txt`)

```
Flask==2.3.3
Authlib>=1.3.0
Flask-SQLAlchemy==2.5.1
Flask-Login==0.6.3
Flask-WTF==1.2.1
psycopg2-binary==2.9.9
Werkzeug==3.0.3
gunicorn==22.0.0
python-dotenv==1.0.1
bcrypt>=4.0.0
```

---

## 8. 구현 계획 (단계별)

### Phase 1: IDP 서버 기본 구축
1. `idp/` 디렉토리 생성 및 기본 구조 셋업
2. DB 모델 정의 (`idp_user`, `oauth2_client`, `oauth2_token`, `oauth2_code`)
3. 사용자 CRUD API + 관리 UI 구현
4. Authlib Authorization Server 구성
5. OAuth2 엔드포인트 구현 (`/oauth/authorize`, `/oauth/token`, `/api/userinfo`)
6. 로그인 UI 페이지 구현

### Phase 2: 범용 외부 DB 동기화
1. `SYNC_SOURCES` JSON 설정 구조 확정
2. `sync.py` 동기화 엔진 구현 (외부 DB 접속 → SELECT → Upsert)
3. Role 동기화 로직 구현 (join/column/static 3가지 모드)
4. 동기화 API (`/api/sync/<source>`) 구현
5. mwm-app(`ab_user`) 동기화 검증

### Phase 3: Docker 통합
1. `create_db.sql` 수정 (`idp` DB 추가)
2. `Dockerfile.idp` 작성
3. `docker-compose.yml`에 `mwm-idp` 서비스 추가
4. 컨테이너 간 네트워크 통신 검증
5. 초기 OAuth2 Client(`mwm-app`) 자동 등록 로직

### Phase 4: mwm-app 연계
1. `app/security.py` (CustomSecurityManager) 구현
2. `config.py` 변경 (`AUTH_TYPE = AUTH_OAUTH`, `OAUTH_PROVIDERS`)
3. `app/__init__.py` 변경 (CustomSecurityManager 적용)
4. `requirements.txt`에 `Authlib` 추가
5. OAuth2 로그인 → `ab_user` 자동 생성/갱신 검증
6. 기존 기능(배치, API 토큰 등) 정상 동작 확인

---

## 9. 수정 파일 목록 (예정)

| 구분 | 파일 | 변경 내용 |
|------|------|----------|
| IDP 신규 | `idp/__init__.py` | Flask app factory, DB 초기화 |
| IDP 신규 | `idp/config.py` | IDP 설정 + SYNC_SOURCES 정의 |
| IDP 신규 | `idp/models.py` | IdpUser, OAuth2Client, OAuth2Token, OAuth2Code 모델 |
| IDP 신규 | `idp/oauth2.py` | Authlib AuthorizationServer 구성 |
| IDP 신규 | `idp/routes.py` | OAuth2 인증 엔드포인트, 관리 UI |
| IDP 신규 | `idp/api.py` | 사용자 CRUD API, userinfo API, 동기화 API |
| IDP 신규 | `idp/sync.py` | 범용 외부 DB 동기화 엔진 |
| IDP 신규 | `idp/templates/*.html` | 로그인, 사용자 관리, 동의 화면 |
| IDP 신규 | `idp/requirements.txt` | IDP 전용 의존성 |
| IDP 신규 | `idp/run.py` | IDP 서버 진입점 |
| Docker | `Dockerfile.idp` | IDP Docker 이미지 빌드 |
| Docker | `docker-compose.yml` | mwm-idp 서비스 추가, mwm-app 환경변수 추가 |
| Docker | `create_db.sql` | `idp` 데이터베이스 생성 추가 |
| App 변경 | `config.py` | AUTH_TYPE 변경, OAUTH_PROVIDERS 추가 |
| App 변경 | `app/__init__.py` | CustomSecurityManager 적용 |
| App 신규 | `app/security.py` | OAuth 사용자 정보 매핑 로직 |
| App 변경 | `requirements.txt` | Authlib 추가 |

---

## 10. 주의사항

- **독립 DB**: IDP는 `mw` DB가 아닌 `idp` DB를 사용. 동기화 시에만 `mw` DB를 **읽기 전용**으로 접근.
- **하위 호환성**: AUTH_OAUTH 전환 후에도 기존 `ab_user` 데이터와 Role/Permission 체계는 그대로 유지됨.
- **API 인증**: mwm-app의 REST API는 기존 Flask-JWT-Extended 토큰 방식을 유지. OAuth2 전환은 **웹 UI 로그인**에만 적용.
- **Fallback**: 문제 발생 시 `config.py`에서 `AUTH_TYPE = AUTH_DB`로 원복하면 즉시 기존 인증으로 복구 가능.
- **보안**: `client_secret`, `SECRET_KEY`, DB 비밀번호 등 민감 정보는 반드시 환경변수로 관리.
- **동기화 방향**: IDP → 외부 DB는 **읽기만** 수행. 외부 DB에 **쓰기는 하지 않음**.

---

## 11. 개발 원칙

### 11-1. SOLID 원칙 적용

IDP 서버는 유지보수성과 확장성을 위해 **SOLID 원칙**을 엄격히 준수한다.

| 원칙 | 적용 방법 |
|------|----------|
| **S** - Single Responsibility | 각 모듈은 하나의 책임만 가짐. `routes.py`(HTTP 요청/응답), `services/`(비즈니스 로직), `repositories/`(데이터 접근), `models.py`(데이터 구조)로 계층 분리 |
| **O** - Open/Closed | 동기화 `role_source`의 `type`(`join`/`column`/`static`)은 기존 코드 수정 없이 새로운 타입을 **추가**할 수 있는 전략 패턴(Strategy Pattern)으로 구현 |
| **L** - Liskov Substitution | Role 동기화 전략 클래스(`JoinRoleStrategy`, `ColumnRoleStrategy`, `StaticRoleStrategy`)는 공통 인터페이스(`RoleSyncStrategy`)를 상속하며 상호 교체 가능 |
| **I** - Interface Segregation | API 엔드포인트를 기능별로 분리: `routes.py`(OAuth2 인증), `api.py`(REST API). 클라이언트는 필요한 인터페이스만 의존 |
| **D** - Dependency Inversion | 서비스 계층은 구체 구현체가 아닌 **추상(인터페이스)**에 의존. Repository를 주입받아 DB 접근. 테스트 시 Mock 교체 용이 |

**계층 구조:**

```
[routes.py / api.py]        ← HTTP 계층 (요청 파싱, 응답 포맷팅)
         │
         ▼
[services/]                 ← 비즈니스 로직 계층 (검증, 변환, 정책 적용)
    ├── user_service.py
    ├── oauth_service.py
    └── sync_service.py
         │
         ▼
[repositories/]             ← 데이터 접근 계층 (CRUD, 쿼리)
    ├── user_repo.py
    └── oauth_repo.py
         │
         ▼
[models.py]                 ← 데이터 모델 (SQLAlchemy ORM)
```

> **규칙**: `routes.py`/`api.py`에서 직접 `db.session`을 호출하지 않는다. 반드시 `services/` → `repositories/`를 경유한다.

### 11-2. Config화 정책 (No Hardcoding)

모든 설정값은 `idp/config.py`에서 **환경변수 우선, 기본값 보조** 방식으로 관리한다. 코드 내부에 리터럴 값을 직접 기입하지 않는다.

**Config화 대상:**

| 카테고리 | 항목 | 관리 방식 |
|----------|------|----------|
| DB 접속 | `IDP_DATABASE_URI` | 환경변수 → `config.py` 기본값 |
| 보안 키 | `SECRET_KEY`, `client_secret` | 환경변수 **필수** (기본값은 개발용만) |
| OAuth2 | `client_id`, `redirect_uri`, `scope`, `token_expires_in` | `config.py` 상수 |
| 동기화 | `SYNC_SOURCES` (DB URI, 테이블, 컬럼 매핑 등) | `config.py` JSON 상수 (환경변수 오버라이드 가능) |
| UI | 페이지 제목, 로고 URL 등 | `config.py` 상수 |
| 비밀번호 정책 | 최소 길이, 해시 알고리즘 | `config.py` 상수 |
| 서버 | 포트, 워커 수, 로그 레벨 | 환경변수 |

**config.py 구조 예시:**

```python
import os

class Config:
    # ── DB ──
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "IDP_DATABASE_URI",
        "postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@localhost:5433/idp"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Security ──
    SECRET_KEY = os.getenv("IDP_SECRET_KEY", "dev-only-secret-change-me")
    PASSWORD_HASH_METHOD = "bcrypt"
    PASSWORD_MIN_LENGTH = 8

    # ── OAuth2 ──
    OAUTH2_TOKEN_EXPIRES_IN = int(os.getenv("OAUTH2_TOKEN_EXPIRES_IN", "3600"))
    OAUTH2_REFRESH_TOKEN_EXPIRES_IN = int(os.getenv("OAUTH2_REFRESH_TOKEN_EXPIRES_IN", "86400"))

    # ── Default Client (mwm-app) ──
    DEFAULT_CLIENT_ID = os.getenv("IDP_MWM_CLIENT_ID", "mwm-app")
    DEFAULT_CLIENT_SECRET = os.getenv("IDP_MWM_CLIENT_SECRET", "mwm-app-secret")
    DEFAULT_REDIRECT_URI = os.getenv("IDP_MWM_REDIRECT_URI",
                                     "http://localhost:8000/oauth-authorized/idp")

    # ── Sync ──
    SYNC_SOURCES = { ... }  # §4-2 참조

    # ── Logging ──
    LOG_LEVEL = os.getenv("IDP_LOG_LEVEL", "INFO")

class TestConfig(Config):
    """테스트 전용 설정"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SYNC_SOURCES = {}  # 테스트에서는 Mock 사용
```

**금지 사항:**

```python
# ❌ 금지: 코드 내부에 리터럴 하## 13. 운영(PROD) 환경 배포 가이드 (Production Deployment Guide)

본 시스템은 폐쇄망 또는 기타 상용 서버에 배포할 때, 별도의 데이터베이스 수동 조작이나 초기화 스크립트 실행 없이 환경변수 설정과 도커 명령어만으로 완벽하게 자동 구축 및 기동되도록 설계되었습니다.

### 13-1. Phase 1: 파일 전송 및 구조 확인
배포 대상 서버(PROD)에 다음 파일들이 정상적으로 위치해야 합니다.
- `docker-compose.yml`
- `Dockerfile.base`, `Dockerfile.app`, `Dockerfile.idp`
- `requirements.txt` (mwm-app 용)
- `create_db.sql`, `create_idp_db.sql`
- `app/` (mwm-app 소스코드)
- `idp/` (mwm-idp 소스코드)

### 13-1.5. Phase 1.5: 세션 기반 SSO(Single Sign-On) 지원 (Flask-Login 통합)
- **목적**: 멀티 클라이언트 환경에서 한 번의 로그인으로 다른 서비스들에도 자동으로 인가 코드를 발급받을 수 있도록 브라우저 세션 관리 기능을 추가함.
- **주요 구현 사항**:
  - `flask-login` 라이브러리를 이용한 사용자 세션 관리.
  - `IdpUser` 모델에 `UserMixin` 상속 및 `is_active` 속성 오버라이드.
  - `idp/__init__.py`에서 `LoginManager` 초기화 및 `user_loader` 등록.
  - `routes.py`의 `authorize` 흐름 개선:
    - **GET**: 이미 로그인된 사용(`current_user.is_authenticated`)인 경우, 로그인 폼을 생략하고 즉시 인가 코드(`code`)를 발급하여 리다이렉트 (SSO 구현).
    - **POST**: 로그인 성공 시 `login_user(user)`를 호출하여 세션 생성.
  - `/logout` 라우트 추가: 세션 파기 및 로그인 페이지 리다이렉트.
- **결과**: `localhost:5000`에 한 번 로그인하면 세션이 유지되는 동안 다른 OAuth2 요청 시 재로그인이 필요 없음.

### 13-2. Phase 2: 필수 환경 변수 및 네트워크 설정 (매우 중요)
프로덕션 환경에서는 사용자 브라우저가 접근할 **실제 도메인(또는 공인/사설 IP)** 정보를 정확히 기입하는 것이 핵심입니다.
`docker-compose.yml` 내의 환경변수를 운영 서버 환경에 맞게 수정합니다.

```yaml
# 1. mwm-app 서비스 환경변수 점검
  mwm-app:
    environment:
      # (내부망) 토큰을 교환하기 위해 mwm-app 컨테이너가 mwm-idp 컨테이너로 직접 찌를 때 사용하는 URL
      IDP_INTERNAL_SERVER_URL: "http://mwm-idp:5000"
      
      # [수정 필수] (외부망) 실제 사용자의 브라우저 화면이 로그인 창으로 전환(Redirect)될 때 사용할 주소.
      # -> PROD 서버 아이피가 10.1.x.x라면 "http://10.1.x.x:5000" 으로 반드시 치환해야 합니다. (localhost 금지)
      IDP_EXTERNAL_SERVER_URL: "http://10.1.X.X:5000"
      
      # mwm-app이 IDP에 자신을 증명할 ID/비밀번호 (아래 설정과 동일해야 함)
      IDP_CLIENT_ID: "mwm-client"
      IDP_CLIENT_SECRET: ${IDP_CLIENT_SECRET}

# 2. mwm-idp 서비스 환경변수 점검
  mwm-idp:
    environment:
      # IDP가 데이터를 복제해올 사내 원본 DB (보안 상 올바른 운영 DB 정보 기재)
      SYNC_MWM_DB_URI: "postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@mwm-db:5432/mw"
      
      # [수정 필수] mwm-app 접속 후 돌아올 올바른 콜백 주소. 
      # IDP_EXTERNAL_SERVER_URL 설정법과 동일하게 운영망 IP를 적어야 합니다.
      IDP_DEFAULT_REDIRECT_URIS: "http://10.1.X.X:8000/idp/callback"
```

### 13-3. Phase 3: 도커 빌드 및 최초 자동화 기동 (Automated Bootstrap)
모든 설정이 완료되면 아래 명령어로 이미지를 빌드하고 컨테이너를 구동합니다.

```bash
# 1. 이전 찌꺼기가 남지 않도록 완벽히 초기화 후 시작
docker compose down -v
docker build --no-cache -t mwm-idp -f idp/Dockerfile.idp idp
docker build --no-cache -t mwm-app -f Dockerfile.app .
docker compose up -d
```

**[기동 시 백그라운드 자동화 프로세스 원리]**
1. `mwm-db`가 구동되면서 `create_idp_db.sql`에 의해 `idp` 데이터베이스가 100% 자동 생성됩니다.
2. `mwm-idp` 컨테이너가 뜨는 즉시 `idp/run.py` 내의 `init_idp()` 로직이 실행됩니다.
3. 이 로직은 `IDP_DEFAULT_CLIENT_ID` 환경변수 값을 바탕으로 OAuth 클라이언트 앱을 **수동 DB 조작 없이 알아서 등록**합니다.
4. 직후 `SYNC_MWM_DB_URI`와 통신하여 `ab_user` 테이블을 스캔, `idp_user` 데이블에 계정과 비밀번호를 **1회 초기 자동 동기화**합니다.

### 13-4. Phase 4: 로그 검증 (Verification)
운영자는 DB에 직접 들어가서 검증할 필요 없이, 아래 명령으로 로그만 확인하면 설치 완료를 보장받습니다.
```bash
docker compose logs --tail 50 mwm-idp
# 아래와 같은 메시지가 발견되면 성공!
# "Registered default IDP client: mwm-client"
# "Sync 'mwm_app' complete: created=XX, updated=0, deactivated=0, errors=0"
# "Completed initial IDP user synchronization."
```

---

## 14. 테스트 및 사용 방법 (Usage & Troubleshooting)

### 14-1. SSO(싱글 사인온) Flow 통합 시나리오
1. **mwm-app 운영망 UI 접속**: 브라우저에서 `http://10.1.X.X:8000/` 로 이동합니다.
2. **IDP 인가 흐름**: 기존 로그인 버튼 하단의 **"Sign in with MWM IDP"** 버튼을 클릭합니다.
   * 브라우저는 위 13-2단계에서 작성한 `IDP_EXTERNAL_SERVER_URL`(포트 5000)으로 부드럽게 전환(Redirect)됩니다.
3. **IDP 로그인 검증**: `mwm-idp` 화면에 운영 시스템에서 쓰던 계정 및 패스워드를 입력하여 Sign In 합니다.
4. **승인 및 복귀**: 로그인이 무사 통과되면 내부적으로 `mwm-app` ↔ `mwm-idp` 간 토큰을 교환한 뒤, 메인 대시보드 인데스 화면으로 돌아옵니다.

### 14-2. 강제/수동 동기화 업데이트 API
운영 중 `mwm-app` 측 DB에 대규모 신규 사용자가 생기거나 권한이 정비되어 즉각 동기화가 필요할 시 API를 찌릅니다.
```bash
# mwm-idp 서버의 API 호출
curl -X POST http://10.1.X.X:5000/api/sync/mwm_app
```

### 14-3. 트러블슈팅 가이드 (Troubleshooting)

* **에러 증상 1**: `Sign in with MWM IDP` 버튼 클릭 직후 **"사이트에 연결할 수 없음"** 브라우저 에러가 뜨는 경우.
  * **원인**: 외부망 환경변수 세팅 미비. 사용자의 브라우저가 Docker 내부 도메인 이름(예: `mwm-idp:5000` 등)으로 접속을 시도했기 때문입니다.
  * **해결법**: 13-2 항목으로 돌아가 `IDP_EXTERNAL_SERVER_URL` 변수가 사용자의 로컬 PC에서 핑(Ping)이 닿는 실제 공인/사설 IP로 잡혀있는지 점검하고 서버를 재기동합니다.

* **에러 증상 2**: IDP 로그인 화면에서 로그인 성공 직후, `mwm-app`으로 되돌아오자마자 **"Invalid Client"** 가상 에러가 발생하는 경우.
  * **원인**: 토큰을 얻으러 되돌아올 때 사용하는 콜백 주소(`redirect_uri`)가 IDP가 승인해둔 주소와 텍스트 한 글자라도 틀릴 경우 발생합니다.
  * **해결법**: 브라우저 주소창의 IP(예: `10.1.1.1`)와 `docker-compose.yml` 내부의 `IDP_DEFAULT_REDIRECT_URIS` 호스트 주소가 정확하게 일치하는지 점검하세요. (localhost 혼용 시 에러)

* **에러 증상 3**: IDP에 로그인을 시도했으나 **"계정 정보가 없습니다"** 거부되는 경우.
  * **원인**: 동기화 로직이 멈춰 계정이 `mwm-idp` 쪽으로 넘어오지 않았습니다.
  * **해결법**: `docker compose logs mwm-idp`를 타건하여 DB 접속 실패 로그(`SYNC_MWM_DB_URI` 인증 에러)가 떴는지 확인 후 조치합니다.

---

## 12. TDD 테스트 전략

### 12-1. 기본 원칙

- **Test-Driven Development**: 기능 구현 전에 **테스트를 먼저 작성**하고, 테스트를 통과시키는 방식으로 개발한다.
- **프레임워크**: `pytest` 사용
- **Coverage 목표**: **100%** (모든 branch 포함)
- **테스트 DB**: SQLite in-memory (`sqlite:///:memory:`)를 사용하여 외부 DB 의존성 제거

### 12-2. TDD 사이클

```
┌──────────────────────────────────────────────┐
│  Red → Green → Refactor                     │
│                                              │
│  1. [Red]      실패하는 테스트 작성           │
│  2. [Green]    테스트를 통과하는 최소 코드 구현│
│  3. [Refactor] 코드 정리 (테스트는 여전히 통과)│
│  4. 반복                                     │
└──────────────────────────────────────────────┘
```

### 12-3. 테스트 분류 및 구조

```
tests/idp/
├── conftest.py          # 공통 Fixture
├── test_models.py       # 단위: 모델 생성, 유효성 검증, 관계
├── test_services.py     # 단위: 비즈니스 로직 (Mock Repository 주입)
├── test_api.py          # 통합: 사용자 CRUD API 엔드투엔드
├── test_oauth2.py       # 통합: OAuth2 전체 Flow (authorize → token → userinfo)
├── test_sync.py         # 통합: 외부 DB 동기화 (Mock 외부 DB)
└── test_routes.py       # 통합: 로그인/인가 화면 렌더링
```

| 분류 | 대상 | Mock 범위 | 검증 항목 |
|------|------|----------|----------|
| **단위 테스트** | `models.py`, `services/` | Repository를 Mock | 비즈니스 로직, 유효성 검증, 에러 처리 |
| **통합 테스트** | `api.py`, `routes.py`, `oauth2.py` | 외부 DB만 Mock (SQLite in-memory 사용) | HTTP 상태 코드, 응답 본문, DB 상태 변화 |
| **동기화 테스트** | `sync.py`, `sync_service.py` | 외부 DB를 SQLite로 대체 | Upsert 정확성, 비활성화, Role 매핑, 에러 핸들링 |

### 12-4. 공통 Fixture (`conftest.py`)

```python
import pytest
from idp import create_app
from idp.config import TestConfig
from idp.models import db as _db

@pytest.fixture(scope='session')
def app():
    """테스트용 Flask 앱 생성"""
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()

@pytest.fixture(scope='function')
def db(app):
    """각 테스트마다 DB 트랜잭션 롤백"""
    with app.app_context():
        _db.session.begin_nested()
        yield _db
        _db.session.rollback()

@pytest.fixture
def client(app):
    """Flask 테스트 클라이언트"""
    return app.test_client()

@pytest.fixture
def sample_user(db):
    """테스트용 사용자 생성 Fixture"""
    from idp.models import IdpUser
    user = IdpUser(
        username='testuser',
        email='test@example.com',
        first_name='Test',
        last_name='User',
        active=True,
        roles=['Public']
    )
    user.set_password('TestPass123!')
    db.session.add(user)
    db.session.commit()
    return user

@pytest.fixture
def sample_oauth_client(db):
    """테스트용 OAuth2 Client 생성 Fixture"""
    from idp.models import OAuth2Client
    client = OAuth2Client(
        client_id='test-client',
        client_secret='test-secret',
        client_name='Test App',
        redirect_uris='http://localhost/callback',
        grant_types='authorization_code',
        scope='openid profile email'
    )
    db.session.add(client)
    db.session.commit()
    return client
```

### 12-5. 테스트 커버리지 항목

**모델 (`test_models.py`):**

| 테스트 | 검증 항목 |
|--------|----------|
| `test_create_user` | IdpUser 생성, 필수 필드 검증 |
| `test_unique_username` | username 중복 시 에러 |
| `test_unique_email` | email 중복 시 에러 |
| `test_password_hash` | `set_password()` → `check_password()` 일관성 |
| `test_user_roles_json` | roles JSON 필드 저장/조회 |
| `test_sync_fields` | `sync_source`, `sync_id` 정상 저장 |
| `test_oauth2_client_model` | OAuth2Client 생성/조회 |
| `test_oauth2_token_model` | OAuth2Token 생성/만료 검증 |

**사용자 API (`test_api.py`):**

| 테스트 | 검증 항목 |
|--------|----------|
| `test_create_user_api` | POST /api/users → 201, DB에 레코드 생성 확인 |
| `test_create_user_duplicate` | 중복 username → 409 |
| `test_list_users` | GET /api/users → 200, 목록 반환 |
| `test_get_user` | GET /api/users/{id} → 200, 상세 정보 |
| `test_get_user_not_found` | 없는 id → 404 |
| `test_update_user` | PUT /api/users/{id} → 200, 필드 갱신 확인 |
| `test_delete_user` | DELETE /api/users/{id} → 204, 비활성화 확인 |
| `test_create_user_validation` | 필수 필드 누락 → 400 |

**OAuth2 Flow (`test_oauth2.py`):**

| 테스트 | 검증 항목 |
|--------|----------|
| `test_authorize_redirect` | GET /oauth/authorize → 로그인 페이지 렌더링 |
| `test_authorize_with_login` | POST /oauth/authorize → Authorization Code 발급, redirect |
| `test_authorize_invalid_client` | 잘못된 client_id → 400 |
| `test_token_exchange` | POST /oauth/token (code) → access_token + refresh_token |
| `test_token_invalid_code` | 잘못된 code → 400 |
| `test_token_expired_code` | 만료된 code → 400 |
| `test_refresh_token` | POST /oauth/token (refresh) → 새 access_token |
| `test_userinfo` | GET /api/userinfo (Bearer) → 사용자 정보(username, email, roles) |
| `test_userinfo_invalid_token` | 잘못된 토큰 → 401 |

**동기화 (`test_sync.py`):**

| 테스트 | 검증 항목 |
|--------|----------|
| `test_sync_create_users` | 외부 DB 사용자 → idp_user INSERT 확인 |
| `test_sync_update_users` | 외부 변경 → idp_user UPDATE 확인 |
| `test_sync_deactivate` | 외부에서 삭제된 사용자 → active=false |
| `test_sync_roles_join` | role_source.type=join → 역할 정상 매핑 |
| `test_sync_roles_static` | role_source.type=static → 고정 역할 부여 |
| `test_sync_password_copy` | sync_password=true → 해시값 복사 확인 |
| `test_sync_no_password` | sync_password=false → password_hash=NULL |
| `test_sync_username_conflict` | 다른 소스 동일 username → 에러 반환 |
| `test_sync_invalid_source` | 미등록 소스명 → 404 |
| `test_sync_db_connection_error` | 외부 DB 접속 실패 → 에러 핸들링 |

### 12-6. 실행 방법

```bash
# 전체 테스트 실행
cd <저장소 루트>
pytest tests/idp/ -v

# 커버리지 측정
pytest tests/idp/ --cov=idp --cov-report=term-missing --cov-branch

# 커버리지 HTML 리포트 생성
pytest tests/idp/ --cov=idp --cov-report=html:tests/idp/htmlcov --cov-branch

# 특정 테스트만 실행
pytest tests/idp/test_sync.py -v -k "test_sync_roles_join"
```

### 12-7. CI/CD 통합 기준

| 항목 | 기준값 | 현재 상태 |
|------|-------|-----------|
| Line Coverage | **100%** | 통과 |
| Branch Coverage | **100%** | 통과 |
| 테스트 실패 | **0건** | **0건 (총 114건 통과)** |
| 테스트 실행 시간 | ≤ 30초 | **약 15초 (성공)** |

### 12-8. IDP 테스트 의존성 (`idp/requirements.txt` 추가)

```
# ── 테스트 전용 ──
pytest>=8.0.0
pytest-cov>=5.0.0
pytest-flask>=1.3.0
```

---

## 13. 설치 및 구성 가이드 (Installation Guide)

본 시스템은 폐쇄망 또는 기타 외부 환경에 배포할 때 추가적인 하드코딩 수정 없이 환경변수만으로 자동 설치 및 기동되도록 설계되었습니다.

### 13-1. 환경 변수 설정
`docker-compose.yml` 또는 `.env` 파일에 다음과 같이 필수 환경 변수들이 정의되어야 합니다.
특히 **네트워크 격리 환경**에서는 브라우저가 인식하는 외부 주소와 컨테이너 내부 주소를 분리해야 합니다.

```yaml
# mwm-app용 환경변수 (docker-compose.yml 내부)
  mwm-app:
    environment:
      # 컨테이너 간 직접 통신 시 사용하는 주소 (Server-To-Server 토큰 교환용)
      IDP_INTERNAL_SERVER_URL: "http://mwm-idp:5000"
      
      # 사용자 브라우저 화면에서 로그인 페이지로 이동(Redirect)할 때 사용하는 호스트 주소
      # 서버 IP가 '192.168.1.10' 이면 'http://192.168.1.10:5000' 로 명시
      IDP_EXTERNAL_SERVER_URL: "http://localhost:5000"
      
      IDP_CLIENT_ID: "mwm-client"
      IDP_CLIENT_SECRET: ${IDP_CLIENT_SECRET}

# mwm-idp용 환경변수
  mwm-idp:
    environment:
      # IDP가 저장할 독립 DB 주소
      IDP_DATABASE_URI: "postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@mwm-db:5432/idp"
      # 사용자 동기화를 위해 읽어올 기존 앱 DB 주소
      SYNC_MWM_DB_URI: "postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@mwm-db:5432/mw"
      
      # MWM 애플리케이션용 디폴트 Oauth 클라이언트 자동 생성 정보 설정
      IDP_DEFAULT_CLIENT_ID: "mwm-client"
      IDP_DEFAULT_CLIENT_SECRET: ${IDP_CLIENT_SECRET}
      IDP_DEFAULT_REDIRECT_URIS: "http://localhost:8000/idp/callback"
```

### 13-2. 데이터베이스 초기화 및 자동 기동 (Automated Bootstrap)
1. 백엔드 DB 컨테이너(`mwm-db`) 실행 시 `create_idp_db.sql` 스크립트에 의해 `idp` 데이터베이스가 자동으로 생성됩니다.
2. `mwm-idp` 컨테이너가 부팅될 때 내부 진입점인 `run.py`가 자동으로 다음 과정을 수행합니다.
   * `IDP_DEFAULT_CLIENT_ID` 환경변수 값을 바탕으로 OAuth 클라이언트 자동 등록.
   * `SYNC_SOURCES`에 정의된 타겟 (예: `mwm-app`의 DB)과 통신하여 계정 정보를 1회 초기 동기화(Initial Sync).
3. 개발자나 시스템 관리자가 별도의 초기 셋업 스크립트를 수동으로 실행할 필요가 없습니다.

---

## 14. 테스트 및 사용 방법 (Usage & Testing)

UI 기반 인증 테스트 (SSO Flow 통합 테스트) 과정은 다음과 같습니다.

### 14-1. 로그인 통합 테스트 절차
1. **mwm-app UI 접속**
   * 브라우저에서 `mwm-app` 접속 주소 (예: `http://localhost:8000/`)로 이동합니다.
2. **IDP 인가 코드 흐름 시작**
   * 기존 로컬 로그인 버튼 하단에 생긴 **"Sign in with MWM IDP"** 버튼을 클릭합니다.
   * 브라우저는 즉시 `mwm-idp` 컨테이너 포트(5000번)의 OAuth 인증 페이지로 자동 전환(Redirect)됩니다.
3. **IDP 로그인 및 인증**
   * IDP 서버 자체의 로그인 화면에서 `mwm-app`에서 기존에 사용하시던 계정 (예: `admin` / `<비밀번호>` 등)을 입력하고 Sign In 합니다.
   * (동기화 엔진을 통해 비밀번호와 사용자 권한이 이미 IDP 서버로 복제된 상태입니다.)
4. **승인 (Authorize)**
   * IDP 서버가 계정 정보를 검증한 뒤 내부적으로 Token을 교환하고, 다시 `mwm-app`으로 되돌아옵니다.
   * UI가 메인 대시보드 화면으로 넘어가면 테스트 성공입니다.

### 14-2. 수동 강제 동기화 테스트
`mwm-app` 측 DB에 신규 사용자가 생기거나 권한이 변경되어 즉시 동기화가 필요할 경우 API를 찔러 동기화합니다.
```bash
# mwm_app 이라는 ID를 가진 동기화 소스를 즉시 업데이트
curl -X POST http://localhost:5000/api/sync/mwm_app
```

### 14-3. 트러블슈팅 가이드
* **증상**: 브라우저에서 IDP 로그인 페이지로 넘어갔으나 **"사이트에 연결할 수 없음"** 오류가 표시될 때.
  * **원인**: `IDP_EXTERNAL_SERVER_URL` 환경변수가 잘못 설정되어, 브라우저가 Docker 내부 도메인(`mwm-idp`)으로 접근하려고 하기 때문입니다.
  * **해결**: `docker-compose.yml`에서 해당 환경 변수를 브라우저가 접근할 수 있는 실제 호스트 IP로 변경하시고 리스타트하세요.
* **증상**: IDP에서 로그인을 완료한 후 `mwm-app`으로 돌아오자마자 **"Invalid client_id"** 에러가 출력될 때.
  * **원인 1**: `mwm-app` 라이브러리가 토큰 요청 시 ID/PW를 Body가 아닌 **Authorization: Basic** 헤더로 보내는데, IDP가 이를 지원하지 않을 경우 발생합니다.
  * **원인 2**: 양 컨테이너 간의 네트워크 링크(`links: mwm-idp`)와 `IDP_INTERNAL_SERVER_URL` 상태를 점검하세요.
  * **해결**: 최신 `idp/routes.py` 패치를 통해 HTTP Basic Auth를 지원하도록 업데이트되었는지 확인하세요.
```

---

## 15. OIDC (OpenID Connect) 지원 확장

### 15-1. 설계 목표
- **표준 준수**: OpenID Connect Core 1.0 사양을 준수하여 MinIO, Metabase 등 표준 OIDC 클라이언트와 호환성을 확보한다.
- **ID Token 발급**: Access Token 외에 사용자 인증 정보를 담은 JWT 형식의 `id_token`을 발급한다.
- **비대칭키 서명**: 보안 강화를 위해 RS256(RSA Signature with SHA-256) 알고리즘을 사용하여 토큰을 서명한다.
- **자동 구성**: Discovery 엔드포인트를 제공하여 클라이언트가 수동 설정 없이 IDP 정보를 가져올 수 있도록 한다.

### 15-2. 주요 추가 기능

| 기능 | 설명 | 경로 |
|------|------|------|
| **OIDC Discovery** | IDP의 설정을 JSON으로 제공 | `/.well-known/openid-configuration` |
| **JWKS (JSON Web Key Set)** | 토큰 검증을 위한 공개키 목록 제공 | `/.well-known/jwks.json` |
| **ID Token 발급** | 로그인 성공 시 `id_token` 반환 | `/oauth/token` 응답에 포함 |
| **표준 Claim 매핑** | 사용 정보를 OIDC 표준 필드로 변환 | `sub`, `email`, `preferred_username` 등 |

### 15-3. ID Token 클레임 설계 (Claims)

| 클레임 | 설명 | 소스 (idp_user) |
|--------|------|----------------|
| `iss` | Issuer (발행자 주소) | `IDP_EXTERNAL_SERVER_URL` |
| `sub` | Subject (사용자 고유 식별자) | `str(id)` |
| `aud` | Audience (대상 클라이언트 ID) | `client_id` |
| `exp` | Expiration Time (만료 시간) | 현재 시간 + 유효 기간 |
| `iat` | Issued At (발행 시간) | 현재 시간 |
| `preferred_username`| 사용자 로그인 ID | `username` |
| `email` | 이메일 주소 | `email` |
| `name` | 전체 이름 | `f"{first_name} {last_name}"` |
| `groups` | 역할(Role) 목록 | `roles` (JSON Array) |

### 15-4. 보안 및 키 관리 (Key Management)

- **알고리즘**: **RS256** (상용 수준의 보안 확보)
- **키 생성**: 2048비트 RSA 키 쌍 사용.
- **설정 방식**:
  - `IDP_RSA_PRIVATE_KEY`: 환경변수로 주입받거나 파일로 관리.
  - 기본값: 개발 환경용 고정 키 제공 (운영 배포 시 필히 변경).

### 15-5. 수정 및 추가 파일 목록

| 구분 | 파일 | 내용 |
|------|------|----------|
| **IDP** | `idp/app/config.py` | `IDP_RSA_PRIVATE_KEY` 추가 |
| **IDP** | `idp/app/routes.py` | Discovery, JWKS 라우트 추가 |
| **IDP** | `idp/app/services/oauth_service.py` | `id_token` 생성 로직 추가 (PyJWT/Authlib 사용) |
| **IDP** | `idp/app/models.py` | `OAuth2Token.to_dict()`에 `id_token` 필드 추가 |

---
