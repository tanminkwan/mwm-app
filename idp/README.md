# MWM IDP (Identity Provider)

이 폴더는 **MWM OAuth2 & OIDC Identity Provider (IDP)** 서버의 독립적인 소스 코드 및 설정을 포함합니다.  
본 서비스는 `mwm-app`(시스템 관리 도구) 및 `mwm-minio`를 포함한 여러 클라이언트 애플리케이션에 고도화된 Single Sign-On(SSO) 환경을 제공합니다.

## 🚀 주요 기능 (Features)

- **OIDC (OpenID Connect) 지원**: RS256 서명 기반 ID Token 발급, Discovery 엔드포인트 및 JWKS 지원.
- **REST API 보안 (API Key)**: `mwm_sk_...` 기반의 **IDP 관리용** API 보안 레이어 제공.
- **OAuth2 Authorization Server**: `authorization_code` 및 `refresh_token` Grant Type 지원 (Authlib 기반).
- **사용자 데이터 동기화 (Sync)**: `mwm-app` DB의 최신 정보를 수동/자동으로 가져오는 Pull 기반 동기화 서비스.
- **Session-Based SSO**: `Flask-Login`과 세션 관리를 통해 멀티 클라이언트 로그인 시 재로그인 불필요.

## 🔐 시스템 인증 체계 가이드

미들웨어관리소(MWM) 시스템은 용도에 따라 두 가지 인증 방식을 제공합니다.

| 구분 | 인증 방식 | 용도 | 발급 위치 |
| :--- | :--- | :--- | :--- |
| **IDP 관리용** | API Key (`mwm_sk_...`) | IDP 설정 관리, 사용자 동기화 제어 | IDP Admin Console |
| **서비스 연동용** | **개인 API Token (JWT)** | Email 발송 API 등 공통 서비스 연동 | `mwm-app` > 나의 정보 |

> [!IMPORTANT]
> 외부 어플리케이션(스크립트 등)에서 **Email 발송 API** 등을 사용하려면 `mwm-app`의 **'개인 인증 토큰 발급'** 메뉴를 통해 1년(365일) 유효 토큰을 발급받아야 합니다.

## 📁 프로젝트 구조 (Architecture)

```text
idp/
├── app/                  # Flask 애플리케이션 소스 코드 (Core)
│   ├── __init__.py      # App Factory & Blueprint 등록
│   ├── config.py         # 설정 (DB, OIDC, SyncSources 등)
│   ├── models.py         # DB 모델 (IdpUser, OAuth2Client, OAuth2Token)
│   ├── routes.py         # OAuth2/OIDC/Admin UI 핸들러
│   ├── api.py            # REST API (Userinfo, Sync, API Key 보안)
│   ├── run.py            # 서버 진입점 및 초기화 로직
│   ├── repositories/     # 데이터 접근 계층 (SOLID: DIP)
│   ├── services/         # 비즈니스 로직 및 동기화 전략 (SOLID: SRP/OCP)
│   └── templates/        # UI 템플릿 (Admin Console 포함)
├── tests/                # pytest 기반 단위/통합 테스트 (이미지에 넣지 않고 마운트)
├── Dockerfile.idp        # IDP 운영 이미지 (mwm-idp)
├── Dockerfile.test       # mwm-idp + 테스트 도구 (mwm-idp-test, CI·개발 전용)
├── create_idp_db.sql     # IDP 전용 PostgreSQL 초기화 SQL
├── requirements.txt      # 운영 의존성 (Authlib, Flask-Login 등) — 전부 버전 고정
└── requirements-dev.txt  # 테스트 도구 (운영 이미지에 싣지 않는다)
```

## 🛠️ 관리 포인트 (Admin Operations)

### 1. 어드민 콘솔 (Admin Console)
- **주소**: [https://idp.mwm.local:20443/admin/settings](https://idp.mwm.local:20443/admin/settings)
- **대상**: `Admin` 또는 `PowerUser` 역할(Role)을 가진 사용자만 접근 가능.
- **기능**:
  - OAuth2 클라이언트 등록 및 MinIO OIDC 정책 매핑 (Policy Mapping).
  - 전체 사용자 목록 및 역할 정보 (Read-only) 모니터링.

### 2. IDP 관리 API 보안 (Internal API Key)
관리자 전용 IDP 내부 API 호출 시 헤더에 `mwm_sk_...` 형태의 키를 포함해야 합니다.
```bash
curl -k -X GET https://idp.mwm.local:20443/api/userinfo \
     -H "Authorization: Bearer <mwm_sk_your_key_here>"
```

### 3. 사용자 동기화 (Sync)
`mwm-app`에서 변경된 사용자/권한 정보를 즉시 반영하려면 어드민 콘솔의 **[Sync Now]** 버튼을 통해 동기화를 수행하십시오.

## 🧪 로컬 개발 환경 (Local Dev)

1. **환경 변수 설정**: `IDP_DATABASE_URI`, `SYNC_MWM_DB_URI`, `IDP_RSA_PRIVATE_KEY` 등을 설정합니다.
2. **패키지 설치**: `pip install -r requirements.txt`
3. **서버 실행**: `export PYTHONPATH=. && python app/run.py`
4. **테스트 수행**: 아래 [테스트](#-테스트) 참고 (Docker)

## 🧪 테스트

테스트 러너는 운영 이미지(`mwm-idp`)에 없다. `mwm-idp-test` 에서 `tests/` 를 마운트해 돌린다.
필수 환경변수는 더미 값이면 되고, RSA 키는 일회용으로 만들어 `/tmp/dummy.pem` 에 마운트한다
(`app/config.py` 의 `TestConfig`). 저장소 루트에서:

```bash
docker build -t mwm-idp      -f idp/Dockerfile.idp  idp
docker build -t mwm-idp-test -f idp/Dockerfile.test idp
openssl genrsa -out /tmp/idp-test.pem 2048 && chmod 644 /tmp/idp-test.pem
docker run --rm \
  -v "$PWD/idp/tests:/workspace/tests:ro" -v /tmp/idp-test.pem:/tmp/dummy.pem:ro \
  -e IDP_DATABASE_URI=sqlite:///:memory: -e IDP_SECRET_KEY=dev \
  -e IDP_MWM_CLIENT_ID=dev -e IDP_MWM_CLIENT_SECRET=dev \
  -e IDP_MWM_REDIRECT_URI=http://localhost/callback -e OIDC_ISSUER=http://localhost \
  -e IDP_RSA_PRIVATE_KEY=/tmp/dummy.pem -e SYNC_MWM_DB_URI=sqlite:///:memory: \
  mwm-idp-test python -m pytest -q -p no:cacheprovider tests
```

- CI(`idp-test` job)는 **전부 통과해야** 한다.
- 관리 API(`/api/users`·`/api/clients`·`/api/sync`)를 부르는 테스트는 `api_headers` fixture 를 쓴다
  (API 키 + Admin 역할). 인증 자체는 `tests/test_api_auth.py` 가 본다.
- 의존성 취약점은 CI `audit` job 이 `pip-audit` 로 본 앱과 함께 검사한다.

## 🐳 Docker 배포 가이드
전체 시스템(`mw_app`)의 루트 디렉터리에서 `docker-compose.yml`을 통해 관리됩니다. 소스 변경 시 반드시 재빌드 및 재시작이 필요합니다.
compose 는 이미지를 빌드하지 않으므로 먼저 `docker build` 로 만든다.
```bash
docker build -t mwm-idp -f idp/Dockerfile.idp idp
docker compose up -d --force-recreate mwm-idp
```

---
*본 문서는 2026-04-03 최종 업데이트 되었습니다.*
