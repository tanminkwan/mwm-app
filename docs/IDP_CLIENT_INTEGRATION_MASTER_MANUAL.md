# [Master Manual] MWM IDP Client Integration Guide

본 문서는 `mwm-idp`를 인증 공급자(OIDC Provider)로 사용하는 모든 클라이언트 애플리케이션(RP, Relying Party)을 위한 **최종 통합 연동 매뉴얼**입니다. 이 가이드를 준수하여 연동할 경우 보안성과 표준 호환성을 보장받을 수 있습니다.

---

## 1. 연동 준비 (Base Information)

연동 시 필요한 엔드포인트 정보는 **Discovery URL**을 통해 자동 획득하는 것을 원칙으로 합니다.

*   **Discovery URL**: `https://idp.mwm.local:20443/.well-known/openid-configuration`
*   **Issuer**: `https://idp.mwm.local:20443`
*   **Signature Algorithm**: `RS256` (RSA Signature with SHA-256)

---

## 2. [Step 1] 클라이언트 등록 (Registration)

인증을 시작하기 전, IDP 관리자 콘솔(`https://idp.mwm.local:20443/admin/settings`)에서 다음 정보를 등록하고 발급받아야 합니다.

1.  **Client ID**: 애플리케이션 고유 식별자 (예: `my-web-app`)
2.  **Client Secret**: 클라이언트 비밀키 (Token 교환 시 사용, 외부 노출 금지)
3.  **Redirect URIs**: 인증 성공 후 `code`를 전달받을 주소 (포트번호 포함 정확히 일치 필수)
4.  **Scopes**: 반드시 `openid`, `profile`, `email`을 포함해야 하며, 권한 활용 시 `groups` 추가 필수.
5.  **Policy Mapping**: (선택) IDP의 Role을 클라이언트용 Policy 값으로 변환할 매핑 규칙(JSON).

---

## 3. [Step 2] 로그인 구현 (Authentication Flow)

`Authorization Code Flow`를 사용합니다.

### 3-1. 인증 요청 (Authorization Request)
브라우저를 통해 사용자를 아래 주소로 보냅니다.
```http
GET https://idp.mwm.local:20443/oauth/authorize?
    response_type=code&
    client_id={YOUR_CLIENT_ID}&
    redirect_uri={YOUR_REGISTERED_REDIRECT_URI}&
    scope=openid profile email groups&
    state={CSRF_TOKEN}&
    nonce={RANDOM_NONCE}
```

### 3-2. 토큰 교환 (Token Request)
전달받은 `code`를 사용하여 서버 간 통신으로 토큰을 발급받습니다.
```http
POST https://idp.mwm.local:20443/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code={RECEIVED_CODE}&
redirect_uri={YOUR_REGISTERED_REDIRECT_URI}&
client_id={YOUR_CLIENT_ID}&
client_secret={YOUR_CLIENT_SECRET}
```

---

## 4. [Step 3] ID Token 검증 및 권한 활용

응답으로 받은 `id_token`은 JWT 포맷이며, 다음 과정을 거쳐 검증하고 사용합니다.

### 4-1. 서명 검증 (Signature Verification)
1.  `id_token` 헤더의 `kid` 확인.
2.  `https://idp.mwm.local:20443/oauth/jwks`에서 공개키 획득.
3.  RS256 알고리즘으로 서명 및 유효기간(`exp`) 검증.

### 4-2. 주요 클레임 (Claims Table)
| 클레임 | 설명 | 예시 |
| :--- | :--- | :--- |
| `sub` | 사용자 고유 식별자 | `alice` |
| `preferred_username` | 사용자 ID | `alice` |
| `email` | 사용자 이메일 | `alice@example.com` |
| `groups` | **통합 권한 그룹** | `["Admin", "PowerUser", "MinioAdmin"]` |
| `given_name` | 이름 | `Gildong` |
| `family_name` | 성 | `Hong` |

> **중요**: `groups` 클레임에는 IDP 내부 Role뿐만 아니라 클라이언트별로 정의된 Policy Mapping 결과가 합쳐져서 전달됩니다.

---

## 5. [Step 4] 로그아웃 구현 (RP-Initiated Logout)

로그아웃 시에는 자체 세션만 파기하지 말고, 반드시 IDP 세션도 함께 종료시켜야 합니다.

### 로그아웃 요청 (Logout Request)
브라우저를 아래 엔드포인트로 리다이렉트합니다.
```http
GET https://idp.mwm.local:20443/logout?
    id_token_hint={ID_TOKEN_ISSUED_EARLIER}&
    post_logout_redirect_uri={YOUR_REGISTERED_REDIRECT_URI}&
    state={STATE}
```

*   **`id_token_hint`**: 로그인 시 발급받았던 `id_token` 원본.
*   **`post_logout_redirect_uri`**: 로그아웃 후 복귀할 주소 (반드시 사전 등록된 Redirect URI여야 함).

---

## 6. 보안 체크리스트 (Security Checklist)

- [ ] 모든 엔드포인트는 `https`를 사용하는가?
- [ ] `state` 파라미터를 생성하고 복귀 시 검증하는가? (CSRF 방어)
- [ ] `nonce` 파라미터를 사용하여 리플레이 공격을 방어하는가?
- [ ] `id_token` 서명 검증을 건너뛰지 않았는가?
- [ ] `client_secret`이 클라이언트 사이드(JS 소스 등)에 노출되지 않았는가?

---

## 7. 트러블슈팅 (Troubleshooting)

| 현상 | 원인 | 해결책 |
| :--- | :--- | :--- |
| `redirect_uri_mismatch` | 요청한 URI가 등록된 값과 다름 | 포트번호, 슬래시(/) 하나까지 정확히 일치시키십시오. |
| `invalid_token` | 서명 검증 실패 | JWKS에서 가져온 공개키가 유효한지, `iss` 값이 일치하는지 확인하십시오. |
| 로그아웃 후 복귀 안 됨 | `post_logout_redirect_uri` 미등록 | 해당 주소를 클라이언트 관리 화면에 추가하십시오. |

---

## 8. 문의처
IDP 관리자 (Admin: admin@mwm.local)
