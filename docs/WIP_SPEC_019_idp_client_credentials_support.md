# WIP_SPEC_019: IDP OAuth2 Client Credentials Grant Type 지원

> **날짜**: 2026-04-14 (수정)
> **버전**: `CLIENT_CREDS(VER:20260414.003)`  
> **상태**: **WIP (Work In Progress) - App 측 API 인증 레이어 설계 보강 중**
> **변경 요약**: IDP의 기존 사용자(`idp_user`) 모델과 `api_key` 메커니즘을 활용하여 OAuth 2.0 `client_credentials`를 지원하되, App 측에서 API 호출 시 이를 검증할 수 있는 Security Manager 커스텀 설계를 추가한다.

---

## 1. 배경 및 필요성

- 현재 IDP는 `authorization_code` + `refresh_token` Grant Type만 지원하며, 모든 토큰 발급에 **사용자(User)의 브라우저 로그인**이 필수임.
- **문제점**:
  - 스케줄러, 백엔드 데몬, 외부 시스템 등 **UI 없이 API를 호출**해야 하는 시나리오를 지원할 수 없음.
  - App의 API들은 현재 세션 기반(브라우저) 또는 자체 JWT 기반 인증만 처리하고 있어, IDP가 발행한 토큰을 인식하지 못함.
- **해결책**:
  - 기존 `idp_user`의 `username`을 `client_id`로, `api_key`를 `client_secret`으로 활용하여 `client_credentials` 방식을 구현한다.
  - **App에 커스텀 Security Manager를 도입**하여 IDP 토큰을 Bearer 헤더로 받아들일 수 있도록 보완한다.

---

## 2. 핵심 설계 원리 (IDP 측)

### 2.1. 기존 자원 재활용 매핑

| OAuth2 개념 | 매핑 대상 | 비고 |
|------------|----------|------|
| `client_id` | `idp_user.username` | 기존 필드 |
| `client_secret` | `idp_user.api_key` | 기존 필드 (`mwm_sk_` 접두사) |
| 토큰 저장 | `oauth2_token` 테이블 | 기존 테이블 (`user_id` 활용) |
| 권한 | `idp_user.roles` → App의 Shadow User Role | 기존 동기화 체계 활용 |

---

## 3. 사용자 유형 가이드 (User Type Guide)

*(중략 - 기존 SPEC 내용과 동일)*

---

## 4. 상세 설계 (IDP 측)

*(중략 - 기존 SPEC 내용과 동일)*

---

## 5. Application 측 연동 (보강된 설계)

### 5.1. 현재 상황 분석 (Technical Gap)

조사 결과, 현재 App(`mwm-app`)의 API 서버는 다음과 같은 상태임:
1. **OIDC 로그인**: `/idp/callback`을 통해 IDP 토큰을 받아 세션을 생성하는 로직은 존재함 (`app/idp_auth.py`).
2. **API 보호**: `@protect()` 데코레이터를 사용 중이나, 이는 오직 **브라우저 세션** 또는 **앱 자체 발행 JWT**만 검증함.
3. **결론**: 서비스 계정(`svc_collector` 등)이 IDP에서 발급받은 토큰을 들고 앱 API를 호출하면, 앱은 이 토큰의 유효성을 IDP에 물어보는 레이어가 없어 **401 Unauthorized**를 반환하게 됨.

### 5.2. 기술적 해결 방안: Custom Security Manager

App 단에 **Custom Security Manager**를 구현하여 `Authorization: Bearer` 토큰이 들어올 경우 IDP의 `/userinfo` 엔드포인트를 호출하여 인증하도록 보강한다.

#### 구현 로직 (Pseudo-code):
```python
# app/security.py (신규 생성 예정)
from flask_appbuilder.security.manager import AUTH_DB
from flask_appbuilder.security.sqla.manager import SecurityManager

class MwmSecurityManager(SecurityManager):
    def check_authorization(self, roles, path, method):
        # 1. 헤더에서 Bearer 토큰 추출
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # 2. IDP의 /userinfo 호출 (캐싱 적용 권장)
            # oauth.mwm_idp.get('userinfo', token=token) 등을 활용
            # ...
            # 3. Shadow User 찾기 및 컨텍스트 설정
            # user = self.find_user(username=info['username'])
            # if user: g.user = user; return True
            pass
        
        # 4. 실패 시 기존 FAB 인증 로직 수행
        return super().check_authorization(roles, path, method)
```

---

## 13. [CRITICAL] 미구현 보완 사항 상세 (Implementation TODOs)

현재 "App 코드 변경 불필요"라는 기존 전제는 틀린 것으로 판명됨. 실제 연동을 위해서는 다음과 같은 **App 측 보완 작업이 필수적**임.

### 13.1. App Security Manager 커스텀 작업
- **파일**: `app/security.py` 신규 생성
- **내용**: 
    - `flask_appbuilder.security.sqla.manager.SecurityManager` 상속
    - `check_authorization` 또는 `before_request` 오버라이드하여 `Authorization` 헤더 처리 로직 추가
    - IDP 토큰 검증 결과(`username`)를 바탕으로 FAB의 `g.user`를 Shadow User로 강제 할당하는 로직 구현

### 13.2. App 설정 변경
- **파일**: `config.py`
- **내용**: 
    ```python
    from app.security import MwmSecurityManager
    CUSTOM_SECURITY_MANAGER = MwmSecurityManager
    ```

### 13.3. 성능 최적화 (Token Caching)
- API 요청마다 IDP에 물어보는 것은 부하가 크므로, 발급받은 토큰의 유효성을 Redis 등에 짧게(예: 1~5분) 캐싱하는 로직이 필요함.

### 13.4. 에러 핸들링 보강
- IDP가 다운되었거나 잘못된 토큰일 경우, 앱 API가 적절한 OAuth2 호환 에러 메시지(`invalid_token`)를 반환하도록 예외 처리 추가.

---

## 14. 수정된 전체 운영 절차 (Updated End-to-End)

1. **[App]**: Shadow User 생성 및 권한 부여.
2. **[IDP]**: 위 계정에 대해 `api_key` 발급 (Client Secret).
3. **[Client]**: IDP의 `/oauth/token`에 `client_credentials` 요청 → Access Token 획득.
4. **[Client]**: App API 호출 (Header에 Token 포함).
5. **[App_New]**: **Custom Security Manager**가 헤더 감지 → IDP에 검증 요청 → Shadow User 권한 확인 → API 응답 성공.

---

> **비고**: 이 문서는 실구현 과정에서 발견된 Technical Gap을 반영하여 수정되었으며, 향후 App 측의 Security Manager 구현이 완료될 때까지 `WIP_` 상태를 유지한다.
