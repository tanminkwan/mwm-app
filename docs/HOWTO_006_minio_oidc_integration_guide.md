# HOWTO 006 - MinIO OIDC (SSO) 연동 가이드

본 문서는 `mwm-idp`를 인증 서버로 사용하여 `mwm-minio` Console에 Single Sign-On(SSO)을 구현하는 상세 절차를 기술합니다. **MinIO의 코드 수정 없이 설정 및 UI 등록만으로 가능합니다.**

---

## 1. 전제 조건 (Prerequisites)
- [HOWTO 005](./HOWTO_005_generate_ssl_certificates.md)를 통해 SSL 설정이 완료되어야 합니다.
- `mwm-idp`가 HTTPS(`https://idp.mwm.local:20443`)로 정상 구동 중이어야 합니다.

---

## 2. Step 1: IDP 관리자 콘솔 접속 및 클라이언트 설정 (UI)

모든 관리 작업은 **IDP 전용 어드민 기능**을 통해 수행됩니다. 

1. **IDP 관리자 콘솔 접속**:  
   [https://idp.mwm.local:20443/admin/settings](https://idp.mwm.local:20443/admin/settings) 에 접속하여 `Admin` 권한 계정으로 로그인합니다.
2. **클라이언트 관리 진입**:  
   `OAuth2 Client 앱 관리` 섹션에서 `클라이언트 리스트 관리`를 클릭하여 `minio-client`를 등록/수정합니다.
3. **상세 설정**:
    - **Scope**: `openid profile email groups`
    - **Policy Mapping (JSON)**:  
      예: `{"Admin": "consoleAdmin", "User": "readwrite"}`  
      *(주의: IDP의 역할(Role) 이름을 MinIO의 정책(Policy) 이름으로 변환해주는 설정입니다.)*

---

## 3. Step 2: MinIO 환경 변수 및 인증서 설정 (Configuration)

MinIO 서버가 자체 서명 인증서(Self-signed)를 사용하는 IDP를 신뢰할 수 있도록 인증서를 마운트하고 환경 변수를 설정합니다.

### 3.1 방법 1: `docker-compose.yml` 직접 설정 (빠른 테스트용)
설정의 가시성이 좋아 초기 연동 테스트에 유리합니다.


```yaml
services:
  mwm-minio:
    # ... 기존 설정 ...
    environment:
      - MINIO_IDENTITY_OPENID_CONFIG_URL=https://idp.mwm.local:20443/.well-known/openid-configuration
      - MINIO_IDENTITY_OPENID_CLIENT_ID=minio-client
      - MINIO_IDENTITY_OPENID_CLIENT_SECRET=${MINIO_OIDC_CLIENT_SECRET}
      - MINIO_IDENTITY_OPENID_SCOPES=openid,profile,email,groups
      - MINIO_IDENTITY_OPENID_REDIRECT_URI=https://minio.mwm.local:20443/oauth_callback
      - MINIO_IDENTITY_OPENID_CLAIM_NAME=policy
      - MINIO_IDENTITY_OPENID_DISPLAY_NAME="MWM IDP"
    volumes:
      - ${MWM_MINIO_DATA_DIR:-./volumes/minio}:/mnt/data
      - ./minio_config.env:/etc/config.env
      - ./nginx/certs/mwm_local.crt:/root/.minio/certs/CAs/mwm_local.crt:ro
```
### 3.2 방법 2: 외부 설정 파일(`.env`) 사용 (운영/실무 권장)
설정 항목이 많아질 경우 관리 효율성을 위해 별도의 파일을 사용합니다.

1. **`minio_config.env` 파일 생성**:
   ```env
   MINIO_IDENTITY_OPENID_CONFIG_URL=https://idp.mwm.local:20443/.well-known/openid-configuration
   MINIO_IDENTITY_OPENID_CLIENT_ID=minio-client
   MINIO_IDENTITY_OPENID_CLIENT_SECRET=${MINIO_OIDC_CLIENT_SECRET}
   MINIO_IDENTITY_OPENID_SCOPES=openid,profile,email,groups
   MINIO_IDENTITY_OPENID_REDIRECT_URI=https://minio.mwm.local:20443/oauth_callback
   MINIO_IDENTITY_OPENID_CLAIM_NAME=policy
   MINIO_IDENTITY_OPENID_DISPLAY_NAME="MWM IDP"
   ```

2. **`docker-compose.yml` 마운트 설정**:
   마운트한 파일을 컨테이너 내부의 `/etc/config.env` 경로에 둡니다.
   ```yaml
   services:
     mwm-minio:
       volumes:
         - ./minio_config.env:/etc/config.env
   ```

### 3.3 SSL 인증서 신뢰 설정 (Trust Store)
자체 서명 인증서(Self-signed) 환경에서 MinIO가 IDP의 SSL을 신뢰할 수 있도록 인증서를 시스템 보관소에 주입합니다.

- **마운트 경로**: `/root/.minio/certs/CAs/` 디렉토리에 인증서(`.crt`)를 마운트합니다.
- **신뢰 범위**: 단일 인증서뿐만 아니라 **Root CA** 혹은 **중간 인증서(Intermediate)**를 마운트하여 복합적인 인증서 체인(Chain Trust)을 지원합니다.
- **번들 파일 지원**: 여러 개의 인증서(Root + Intermediate)를 하나의 `.crt` 파일에 합쳐서(Bundled) 마운트해도 정상 동작합니다.
- **파일명**: 파일명은 자유로우나 확장자는 반드시 **`.crt`**여야 합니다.

> **왜 인증서를 마운트하나요?**  
> 최근 MinIO 버전은 보안을 위해 `SKIP_VERIFY` 같은 우회 환경 변수를 허용하지 않는 경우가 많습니다. 대신 전용 디렉토리에 인증서를 넣어두면 MinIO가 기동될 때 자동으로 이를 신뢰 목록에 추가하여 안전하게 통신합니다.

---

## 4. Step 3: 권한 매핑 (Claims & Policies)

연동이 완료된 후 사용자가 로그인했을 때의 권한은 IDP 클라이언트 설정의 **`Policy Mapping (JSON)`**을 통해 결정됩니다.

1. **매핑 원리**:  
   IdP가 발행하는 토큰의 `policy` 클레임에 사용자의 역할을 변환하여 담습니다.
2. **설정 예시**:  
   - IDP 역할이 `Admin`인 사용자에게 MinIO 관리자 권한을 주려면: `{"Admin": "consoleAdmin"}`
   - IDP 역할이 `User`인 사용자에게 읽기/쓰기 권한을 주려면: `{"User": "readwrite"}`
3. **확인**:  
   MinIO 사이드바의 `Administrator > Policies`에 해당 정책(예: `consoleAdmin`)이 존재해야 합니다. (기본 제공됨)

---

## 5. 접속 및 확인

1. **MinIO 접속**: [https://minio.mwm.local:20443](https://minio.mwm.local:20443) 에 접속합니다.
2. **SSO 버튼 확인**: 로그인 화면 하단에 `Login with OpenID` 버튼이 활성화됩니다.
3. **인증 수행**: 버튼 클릭 시 `idp.mwm.local` 로그인 화면으로 이동하며, 로그인을 마치면 다시 MinIO로 돌아와 자동으로 서비스에 진입합니다.

---

- **Invalid redirect_uri**: IdP UI에 등록한 Redirect URI와 `docker-compose.yml`의 설정값이 일치하는지 확인하십시오.
- **JWKS Error**: IdP의 `/.well-known/openid-configuration` 주소가 MinIO 컨테이너 내부에서도 접속 가능한지(`extra_hosts` 확인) 점검하십시오.

---

## 7. REST API 보안 및 관리자 관리

IDP는 관리 주체의 보안을 위해 **API Key** 기동 및 **수동 동기화** 기능을 제공합니다.

### 7.1 관리자 API Key 발급 및 사용
1. **발급**: 어드민 콘솔 하단의 `관리자 전용 API Key` 섹션에서 `새 키 발급/갱신 (Rotate Key)`을 클릭합니다.
2. **조회/복사**: 발급된 키(`mwm_sk_...`)를 복사하여 안전한 곳에 보관합니다.
3. **API 호출 예시 (curl)**:
   ```bash
   curl -k -X GET https://idp.mwm.local:20443/api/userinfo \
        -H "Authorization: Bearer <여러분의_API_KEY>"
   ```

### 7.2 사용자 정보 최신화 (Sync)
- `mwm-app`에서 사용자 권한이나 계정을 수정한 후, IDP에 즉시 반영하려면 **[지금 동기화 실행 (Sync Now)]** 버튼을 누르십시오. 
- 이 작업은 IDP 서버가 `mwm-app`의 데이터베이스에 직접 접속하여 최신 정보를 가져옵니다.

---

## 8. 보안 권장 사항
- **API Key 수명**: 현재 발급된 API Key는 수동 갱신(Rotate) 전까지 유효합니다. 보안을 위해 정기적인 갱신을 권장합니다.
- **권한 관리**: IDP 관리자 콘솔은 `Admin` 또는 `PowerUser` 전용입니다. 일반 사용자에게는 노출되지 않도록 계정 관리에 유의하십시오.
