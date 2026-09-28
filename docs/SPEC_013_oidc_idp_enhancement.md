# SPEC_013: OpenID Connect (OIDC) 고도화 및 외부 시스템(MinIO 등) 연계

> **날짜**: 2026-03-28  
> **버전**: `OIDC_ENHANCE(VER:20260328.001)`  
> **변경 요약**: 기존 OAuth2 IDP 서버를 OIDC(OpenID Connect) 표준으로 완전 계층화하여, MinIO 등 외부 상용/오픈소스 솔루션이 연동 가능한 표준 IDP로 고도화한다.

---

## 1. 배경 및 필요성

- 현재 mwm-idp는 OAuth2 기반의 Authorization Code Flow를 지원하나, **OpenID Connect(OIDC)**의 핵심 표준 요소들이 미비함.
- **문제점**:
  - **ID Token(JWT) 미발급**: 인증 응답에 서명된 ID Token이 포함되지 않아 클라이언트가 독자적으로 사용자 신원을 검증할 수 없음.
  - **Discovery 미지원**: `.well-known/openid-configuration` 엔드포인트가 없어 외부 솔루션(MinIO, GitLab, ArgoCD 등)이 자동 설정을 수행하지 못함.
  - **JWKS 미지원**: 서명 검증을 위한 공개키(Public Key) 제공 표준 수단이 부재함.
- **목표**:
  - MinIO가 요구하는 표준 OIDC 스펙을 충족하여 사내 통합 인증 체계를 구축한다.
  - 범용적인 JWT Claims(특히 `groups` 등)를 지원하여 Role 기반 접근 제어(RBAC) 연계가 가능케 한다.

---

## 2. OIDC 아키텍처 및 표준 구현 상세

### 2-1. OIDC Discovery 엔드포인트 (`GET /.well-known/openid-configuration`)

외부 서비스가 IDP 정보를 자동으로 파싱할 수 있도록 아래 메타데이터를 제공한다.

| 필드 | 설명 | 값(예시) |
|------|------|----------|
| `issuer` | IDP 서버 고유 식별자 | `http://localhost:5000` |
| `authorization_endpoint` | 인증 요청 URL | `/oauth/authorize` |
| `token_endpoint` | 토큰 교환 URL | `/oauth/token` |
| `userinfo_endpoint` | 사용자 정보 조회 URL | `/api/userinfo` |
| `jwks_uri` | 공개키 목록 URL | `/oauth/jwks` |
| `end_session_endpoint` | 로그아웃 URL | `/logout` |
| `response_types_supported` | 지원 응답 타입 | `["code"]` |
| `subject_types_supported` | 지원 서브젝트 타입 | `["public"]` |
| `id_token_signing_alg_values_supported` | 서명 알고리즘 | `["RS256"]` |
| `scopes_supported` | 지원 스코프 | `["openid", "profile", "email", "groups"]` |

### 2-2. JWKS (JSON Web Key Set) 엔드포인트 (`GET /oauth/jwks`)

ID Token의 서명을 검증하기 위해 RSA 공개키를 JSON 포맷으로 노출한다.

```json
{
  "keys": [
    {
      "kty": "RSA",
      "alg": "RS256",
      "use": "sig",
      "kid": "mwm-idp-key-1",
      "n": "...",
      "e": "AQAB"
    }
  ]
}
```

### 2-3. ID Token (JWT) 설계

- **Signing Algorithm**: RS256 (RSA Signature with SHA-256)
- **Header**: `{"alg": "RS256", "typ": "JWT", "kid": "mwm-idp-key-1"}`
- **Payload (Claims)**:

| Claim | 설명 | 매핑 데이터 |
|-------|------|-----------|
| `iss` | Issuer (발행자) | `config.OIDC_ISSUER` |
| `sub` | Subject (사용자 식별자) | `idp_user.username` (또는 UUID) |
| `aud` | Audience (수신자) | `client_id` |
| `exp` | Expiration Time | 토큰 만료 시각 |
| `iat` | Issued At | 발행 시각 |
| `nonce` | Nonce | Replay 공격 방지용 string |
| `preferred_username` | 사용자 ID | `idp_user.username` |
| `email` | 이메일 | `idp_user.email` |
| `groups` | 그룹(Role) 목록 | `idp_user.roles` (리스트 형태) |

> **MinIO 참고**: MinIO는 Claim 중 `groups` 필드를 읽어 Policy 매핑에 사용하므로, IDP의 `roles` 정보를 `groups` 클레임으로 전달하는 것이 중요함.

---

## 3. 구현 요구사항 (Technical Requirements)

### 3-1. RSA 키 관리 (Key Management)

- **개발 환경**: `config.py`에 내장된 고정 RSA 키(Private Key) 사용.
- **운영 환경**: 환경변수(`IDP_RSA_PRIVATE_KEY`)를 통해 PEM 포맷의 개인키 주입.
- **공개키 추출**: 개인키에서 실시간으로 공개키(`n`, `e`)를 추출하여 JWKS에 반영.

### 3-2. OAuth2/OIDC 서비스 및 엔드포인트 확장

1. **`OAuthService` 확장**:
   - `create_id_token(user, client_id, nonce)` 메서드 추가.
   - PyJWT 또는 Authlib을 사용하여 JWT 생성 및 서명.
2. **`routes.py` 확장**:
   - `/.well-known/openid-configuration` 라우트 추가.
   - `/oauth/jwks` 라우트 추가.
   - `/oauth/token` 응답 본문에 `id_token` 필드 포함.
3. **`UserRepository` 확장**:
   - OIDC 정보를 위한 `get_user_claims` 메서드 (비즈니스 로직 분리).

### 3-3. MinIO 연동 설정 (Configuration Guide)

MinIO 측에서 IDP를 연동하기 위한 환경변수 설정 예시:

```bash
MINIO_IDENTITY_OPENID_DISPLAY_NAME="MWM Login"
MINIO_IDENTITY_OPENID_CONFIG_URL="http://mwm-idp:5000/.well-known/openid-configuration"
MINIO_IDENTITY_OPENID_CLIENT_ID="minio-client"
MINIO_IDENTITY_OPENID_CLIENT_SECRET=${MINIO_OIDC_CLIENT_SECRET}
MINIO_IDENTITY_OPENID_SCOPES="openid,profile,email,groups"
MINIO_IDENTITY_OPENID_REDIRECT_URI="http://MINIO_HOST:9000/oauth_callback"
# Policy Claim 매핑 (IDP의 groups 클레임을 MinIO의 policy로 사용)
MINIO_IDENTITY_OPENID_CLAIM_NAME="groups"
```

---

## 4. DB 모델 변경 (선택 사항)

- **`oauth2_client` 테이블**: `jwks_uri` 또는 특정 클라이언트 전용 클레임 설정을 위한 컬럼 추가 필요성 검토 (현재는 기본값으로 진행).

---

## 5. 구현 단계 (Milestones)

### Step 1: RSA 키 유틸리티 및 JWT 서명 구현
- `cryptography` 라이브러리를 사용하여 PEM 키 로드 및 JWKS용 공개키 추출 로직 구현.
- `PyJWT`를 이용한 ID Token 생성 모듈 개발.

### Step 2: Discovery 및 JWKS 엔드포인트 추가
- `routes.py`에 OIDC 표준 메타데이터 제공 엔드포인트 구현.
- 클라이언트(MinIO 등)가 이 엔드포인트를 통해 정상적으로 IDP 정보를 수신하는지 검증.

### Step 3: Token Response에 ID Token 통합
- `access_token` 발급 시 `openid` 스코프가 포함되어 있다면 `id_token`을 생성하여 함께 반환하도록 `oauth_service.py` 수정.

### Step 4: MinIO 연동 테스트 및 Claims 튜닝
- 실제 MinIO 컨테이너를 구동하여 로그인이 정상적으로 수행되는지 확인.
- `groups` 클레임이 MinIO의 IAM Policy와 연계되는지 최종 검증.

---

## 6. 주의 사항

- **TLS/SSL**: OIDC는 보안상 HTTPS 사용을 강력히 권고함. 로컬 테스트 외 운영 환경에서는 반드시 SSL 터미네이션(Nginx 등) 뒤에 위치해야 함.
- **Issuer 일치**: `issuer` 정보는 Discovery URI의 Base URL과 정확히 일치해야 함.
- **Time Sync**: JWT 서명 검증 시 서버 간 시간 오차가 발생하면 `exp` 검증이 실패하므로 NTP 동기화가 필수적임.
