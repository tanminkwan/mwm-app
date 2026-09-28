# HOWTO 007 - MWM-IDP (인증 서버) 설치 및 운영 가이드

본 문서는 `mwm-idp` (OIDC/OAuth2 인증 서버)를 설치하고 운영 환경에 배포하기 위한 상세 절차를 기술합니다.

---

## 1. 개요 (Description)

`mwm-idp`는 `mwm-app`의 사용자 정보를 통합 관리하고, OAuth2/OIDC 표준을 통해 외부 시스템(MinIO, Kroki 등)에 Single Sign-On(SSO) 기능을 제공하는 독립 인증 서비스입니다.

---

## 2. 사전 요구 사항 (Prerequisites)

- **Docker & Docker Compose**: 컨테이너 환경에서 실행됩니다.
- **PostgreSQL**: `mwm-db` 내에 `idp` 전용 데이터베이스가 필요합니다.
- **SSL 인증서**: OIDC 통신은 HTTPS를 강력히 권고합니다. ([HOWTO 005](./HOWTO_005_generate_ssl_certificates.md) 참고)

---

## 3. Step 1: 데이터베이스 초기화 (Database Setup)

`mwm-idp`는 독립적인 DB(`idp`)를 사용합니다. 호스트에서 다음 명령을 통해 DB를 생성합니다.

```bash
# PostgreSQL 컨테이너에 접속하여 DB 생성 및 권한 부여
docker exec -it mwm-db psql -U postgres -c "CREATE DATABASE idp;"
docker exec -it mwm-db psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE idp TO mwm;"
docker exec -it mwm-db psql -U postgres -d idp -c "ALTER SCHEMA public OWNER TO mwm;"
```

---

## 4. Step 2: RS256 서명용 개인키 생성 (RSA Key Generation)

OIDC ID Token의 서명을 위해 2048비트 RSA 개인키가 필요합니다. 이 키는 **호스트의 특정 디렉토리에 파일로 저장**되어 컨테이너에 마운트되어야 합니다.

```bash
# 간단한 방법: 저장소 루트에서 ./init_certs.sh → certs/idp/idp_private.pem (이미 있으면 건너뛴다. git 으로 배포하지 않는다 — TASK 1-1)
# 수동으로 만들 때도 compose 가 마운트하는 certs/idp/ 에 둔다

# 1. 저장용 디렉토리 생성
mkdir -p idp/certs

# 2. 2048비트 RSA 개인키 생성
openssl genrsa -out idp/certs/idp_private.pem 2048

# 3. 권한 설정 (생략 가능하나 보안상 권장)
chmod 600 idp/certs/idp_private.pem
```

> [!IMPORTANT]
> 생성된 `idp_private.pem` 파일은 절대 외부에 노출되어서는 안 됩니다. 이제 이 파일은 `docker-compose.yml`의 볼륨 기능을 통해 컨테이너 내부로 전달됩니다.

---

## 5. Step 3: 환경 변수 구성 (Full Configuration Guide)

`mwm-idp`의 모든 거동은 환경변수를 통해 제어됩니다. 운영 환경에서 실수하기 쉬운 핵심 설정들을 아래와 같이 `docker-compose.yml`에 상세히 정의해야 합니다.

### 5-1. 환경변수 상세 정의 (Environment Variables)

| 카테고리 | 환경변수명 | 설명 | 비고 |
|:--- |:--- |:--- |:--- |
| **DB** | `IDP_DATABASE_URI` | IDP 전용 DB 접속 URI | `postgresql://.../idp` |
| **보안** | `IDP_SECRET_KEY` | Flask 세션 및 CSRF 보안용 비밀키 | 복잡한 문자열 권장 |
| | `IDP_PASSWORD_MIN_LENGTH` | 사용자 암호 최소 길이 (기본: 8) | |
| **OAuth2** | `OAUTH2_TOKEN_EXPIRES_IN` | Access Token 유효 기간 (초) | 기본: 3600 (1시간) |
| | `OAUTH2_REFRESH_TOKEN_EXPIRES_IN` | Refresh Token 유효 기간 (초) | 기본: 86400 (24시간) |
| **OIDC** | `OIDC_ISSUER` | 토큰 내 발행자 식별 URL | 브라우저 접근 주소와 일치 필수 |
| | `IDP_RSA_PRIVATE_KEY` | RS256 서명용 RSA 개인키 **파일 경로** | 컨테이너 내부 경로 (예: `/etc/idp/certs/idp_private.pem`) |
| **클라이언트**| `IDP_MWM_CLIENT_ID` | 기본 클라이언트(`mwm-app`) ID | |
| | `IDP_MWM_CLIENT_SECRET` | 기본 클라이언트 비밀번호 | |
| | `IDP_MWM_REDIRECT_URI` | 인증 후 돌아갈 주소 (Callback) | |
| **운영** | `IDP_EXTERNAL_SERVER_URL` | 외부 접근용 Base URL | `https://idp.mwm.local...` |
| | `IDP_APP_TITLE` | 화면에 표시될 서비스 명칭 | |
| | `IDP_LOG_LEVEL` | 로그 상세도 (INFO, DEBUG 등) | |
| **동기화** | `SYNC_MWM_DB_URI` | `mwm-app` 사용자를 가져올 DB 주소 | |

### 5-2. `docker-compose.yml` 전체 예시

아래 내용을 복사하여 운영 환경에 맞게 수정하십시오.

```yaml
  mwm-idp:
    container_name: mwm-idp
    image: mwm-idp
    build:
      context: ./idp
      dockerfile: Dockerfile.idp
    ports:
      - "5000:5000"
    environment:
      # [필수] 로컬 타임존 설정
      - TZ=Asia/Seoul
      
      # [필수] 데이터베이스 접속 정보
      - IDP_DATABASE_URI=postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@mwm-db:5432/idp
      - SYNC_MWM_DB_URI=postgresql://${MWM_DB_USER}:${MWM_DB_PASSWORD}@mwm-db:5432/mw
      
      # [중요] 보안 및 세션 설정
      - IDP_SECRET_KEY=${IDP_SECRET_KEY}
      - IDP_APP_TITLE=MWM Identity Provider (PROD)
      
      # [중요] OIDC 발행자 정보 (브라우저가 접근하는 주소와 동일해야 함)
      - OIDC_ISSUER=https://idp.mwm.local:20443
      - IDP_EXTERNAL_SERVER_URL=https://idp.mwm.local:20443
      
      # [필수] RS256 서명용 개인키 파일 경로
      # 주의: PEM 파일 '내용'을 넣는 것이 아니라, 마운트된 '파일 경로'를 지정합니다.
      - IDP_RSA_PRIVATE_KEY=/etc/idp/certs/idp_private.pem
      
      - IDP_MWM_CLIENT_ID=mwm-client
      - IDP_MWM_CLIENT_SECRET=${IDP_CLIENT_SECRET}
      - IDP_MWM_REDIRECT_URI=https://app.mwm.local:20443/idp/callback
    volumes:
      # [필수] 호스트의 PEM 파일을 컨테이너 내부로 마운트 (Read-only)
      - ./idp/certs:/etc/idp/certs:ro
```

### 5-3. RSA 개인키 상세 가이드 (Usage & Generation)

`IDP_RSA_PRIVATE_KEY`는 OIDC의 핵심 보안 요소로, 다음과 같은 용도와 절차로 관리됩니다.

#### ① 용도 (Why is this needed?)
- **ID Token 서명**: 사용자가 로그인할 때 발행되는 **ID Token(JWT)**이 변조되지 않았음을 보장하기 위해 **RS256(RSA Signature with SHA-256)** 알고리즘으로 서명할 때 사용합니다.
- **공개키 노출**: IDP 서버는 이 개인키에서 추출한 공개키를 `/.well-known/jwks.json` 경로에 노출하며, 클라이언트(MinIO 등)는 이를 가져와 토큰의 정당성을 검증합니다.

#### ② 작동 방식 (How it works)
IDP 서버는 **기동 시점(Startup)**에 설정된 경로에서 PEM 파일을 한 번만 읽어 메모리에 적재합니다.

- **성능**: 매 인증 요청마다 디스크 I/O가 발생하지 않으므로 빠르고 안정적입니다.
- **Fail-fast**: 기동 시 키 파일이 없거나 유효하지 않으면 서버가 즉시 종료되어 보안 구멍을 사전에 차단합니다.
- **결합도 분리**: 소스 코드나 환경 변수가 아닌 파일 시스템 수준에서 보안 자산을 관리합니다.

#### ③ 키 로테이션 (Key Rotation)
키를 교체해야 하는 경우 호스트의 PEM 파일을 덮어쓴 후, `mwm-idp` 컨테이너를 **재기동**하십시오. 재기동 시 새 키가 메모리에 다시 적재됩니다.

---

---

## 6. Step 4: 빌드 및 기동 (Build & Run)

README 의 '이미지 빌드' 절차대로 다시 빌드하고 컨테이너를 교체합니다.

```bash
# 1. 기존 컨테이너 중지 및 삭제
docker compose stop mwm-idp && docker compose rm -f mwm-idp

# 2. 이미지 빌드 (캐시 미사용)
docker build --no-cache -t mwm-idp -f idp/Dockerfile.idp idp

# 3. 컨테이너 기동
docker compose up -d mwm-idp
```

---

## 7. Step 5: 초기 사용자 동기화 (Initial Sync)

서비스 기동 시 자동으로 수행되지만, 운영 중에 명시적으로 `mwm-app`의 사용자(`ab_user`)를 다시 가져오려면 관리자 전용 API를 호출합니다.

### 7-1. API 사용 제약 (Constraints)
- **인증 방식**: `Authorization: Bearer <API_KEY>` 헤더가 필수입니다.
- **권한 요구**: API Key를 발급받은 사용자가 **`Admin`** 또는 **`PowerUser`** 역할을 보유해야 합니다.
- **예외**: 서버 기동 시 `init_idp()`에 의해 수행되는 최초 동기화는 내부 프로세스이므로 별도의 인증 없이 자동 실행됩니다.

### 7-2. 동기화 API 호출 예시
```bash
# 관리자 API Key를 사용하여 mwm-app 사용자 동기화
curl -X POST https://idp.mwm.local:20443/api/sync/mwm_app \
     -H "Authorization: Bearer <IDP_ADMIN_API_KEY>" \
     -H "Content-Type: application/json"
```

성공 시 `{ "created": n, "updated": m, ... }` 형태의 JSON 결과가 반환됩니다. 로그를 통해서도 상세 내역 확인이 가능합니다.
`docker compose logs -f mwm-idp`

---

## 8. Step 6: 관리자 API Key 발급 (Admin Security)

IDP 관리용 API를 안전하게 사용하기 위해 관리자 계정의 API Key를 발급합니다.

1. **로그인**: `idp.mwm.local` UI에 `Admin` 권한 계정으로 로그인합니다.
2. **콘솔 이동**: `관리자 콘솔` 메뉴 또는 `/admin/settings`로 이동합니다.
3. **Key 생성**: `관리자 전용 API Key` 섹션에서 `새 키 발급/갱신 (Rotate Key)`을 누릅니다.
4. **확인**: 발급된 `mwm_sk_...` 키를 안전하게 보관합니다.

---

## 9. 트러블슈팅 (Troubleshooting)

### 9-1. "Database connection error" 발생 시
- `SYNC_MWM_DB_URI` 환경변수의 DB 접속 정보가 정확한지, `mwm-db` 컨테이너가 정상 기동 중인지 확인합니다.

### 9-2. ID Token 서명 검증 실패 (`RS256`) 또는 기동 에러
- `IDP_RSA_PRIVATE_KEY`에 지정된 경로에 실제 PEM 파일이 존재하는지, `docker-compose.yml`의 `volumes` 마운트가 정확한지 확인합니다.
- 로그(`docker logs mwm-idp`)에서 `OIDC RSA Private Key successfully loaded into memory.` 메시지가 있는지 확인합니다.
- 파일 내용이 손상되었거나 RSA 형식이 아닐 경우 서버 기동이 중지됩니다.

### 9-3. redirect_uri 불일치 에러
- IDP 어드민 콘솔에서 등록한 클라이언트의 `Redirect URI`와 실제 호출하는 주소가 스키마(http/https)까지 정확히 일치하는지 점검합니다.

---

## 10. 관련 문서
- [HOWTO 005 - SSL 인증서 생성](./HOWTO_005_generate_ssl_certificates.md)
- [HOWTO 006 - MinIO OIDC 연동 가이드](./HOWTO_006_minio_oidc_integration_guide.md)
- [SPEC 012 - OAuth2 IDP 설계서](./SPEC_012_oauth2_idp_server.md)
