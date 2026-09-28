# SPEC_016: MinIO Boot Dependency and OIDC Initialization Resolution

## 1. 개요 (Background)
MinIO Console은 OIDC 인증을 활성화하기 위해 부팅 시점에 고정된 `MINIO_IDENTITY_OPENID_CONFIG_URL`에서 구성 정보를 가져오려 시도합니다. 만약 이 시점에 해당 URL(IDP 서버 또는 이를 중계하는 Nginx)에 접근할 수 없으면, MinIO는 OIDC 초기화에 실패하고 로그인 화면에서 IDP 인증 버튼이 나타나지 않게 됩니다.

## 2. 문제 분석 (Problem Analysis)
기존 `docker-compose.yml` 설정에서는 다음과 같은 의존성 순환(또는 지연) 문제가 발생했습니다:
1.  `mwm-nginx`는 `mwm-minio`가 준비될 때까지 시작하지 않음 (`depends_on`).
2.  `mwm-minio`는 시작하며 `idp.mwm.local:20443` 접속을 시도함.
3.  `idp.mwm.local:20443`은 `mwm-nginx`가 포트를 열어야만 접근 가능함.
4.  결과적으로 MinIO는 Nginx가 뜨기를 기다릴 수 없어 OIDC 초기화에 실패함.

## 3. 해결 설계 (Solution Design)
의존성 순서를 반대로 조정하여, **외부 관문(Gateway) 역할을 하는 Nginx가 먼저 기동된 후 MinIO가 시작**되도록 보강합니다.

### 3.1 의존성 변경 사항 (Dependency Changes)
- **`mwm-nginx`**: `depends_on` 목록에서 `mwm-minio`를 제거하여 MinIO 없이도 먼저 실행될 수 있도록 함.
- **`mwm-app`**: `depends_on` 목록에서 `mwm-minio`를 제거하여 MinIO 기동 지연에 영향을 받지 않도록 함. (App은 런타임에 S3 연결을 시도함)
- **`mwm-minio`**: `depends_on` 목록에 `mwm-nginx`를 추가하여, 관문이 준비된 후에 OIDC Discovery를 시도하도록 강제함.

## 4. 적용 세부 사항 (Implementation Details)

### 4.1 docker-compose.yml
```yaml
  mwm-minio:
    ...
    depends_on:
      - mwm-nginx
    ...

  mwm-app:
    ...
    depends_on:
      - mwm-db
      - mwm-redis
      - mwm-kroki
    # - mwm-minio 제거
    ...

  mwm-nginx:
    ...
    depends_on:
      - mwm-app
      - mwm-idp
    # - mwm-minio 제거
    ...
```

### 4.2 minio_config.env 보강
기존 `docker-compose.yml`에 흩어져 있던 OIDC 설정값을 `minio_config.env`로 통합하고 명시적인 표시 이름을 추가함.
```bash
MINIO_IDENTITY_OPENID_DISPLAY_NAME="MWM IDP"
```

## 5. 제약 사항 및 운영 가이드 (Constraints & Operation)
- **중요**: MinIO 부팅 시점에 반드시 IDP 서버와 Nginx 프록시가 모두 응답 가능한 상태여야 합니다. 
- 시스템 전체 재기동 후 버튼이 나타나지 않는다면, Nginx가 완전히 준비된 후 `docker compose restart mwm-minio`를 수행하여 재초기화를 유도할 수 있습니다. 
- 이 변경은 Docker 내부 DNS가 캐시를 활용하여 Hostname 해석 실패를 방지하도록 설계되었습니다.
