# SPEC_015: IDP RSA Private Key 파일 관리 및 보안 강화

> **날짜**: 2026-03-30  
> **버전**: `IDP_KEY_FILE(VER:20260330.001)`  
> **변경 요약**: OIDC ID Token 서명에 사용되는 RSA Private Key를 환경 변수나 코드 내 하드코딩 방식에서 외부 PEM 파일 로드 방식으로 전환하여 보안성과 운영 편의성을 강화한다.

---

## 1. 개요

기존 `mwm-idp`는 OIDC 구동을 위한 RSA Private Key를 `config.py` 내부에 하드코딩하거나 환경 변수로 직접 전달받는 방식을 사용하였다. 이는 보안상 취약할 뿐만 아니라, 키 교체 시 컨테이너 환경 변수를 매번 수정해야 하는 번거로움이 있었다. 이를 개선하기 위해 **호스트 시스템의 PEM 파일을 볼륨 마운트하여 동적으로 로드**하는 구조로 개편한다.

---

## 2. 주요 변경 사항

### 2-1. 설정 방식 변경 (`idp/app/config.py`)
- `IDP_RSA_PRIVATE_KEY` 환경 변수의 역할을 '키 값'에서 **'PEM 파일의 컨테이너 내부 경로'**로 변경한다.
- 기본값: `/etc/idp/certs/idp_private.pem`

### 2-2. 키 로드 로직 고도화 (`idp/app/services/oidc_service.py`)
- `_get_private_key()` 메서드에서 설정된 값이 파일 경로인지 확인하는 로직을 추가한다.
- 파일 경로일 경우 해당 파일을 읽어 PEM 데이터를 추출하고, 파일이 아닐 경우(하위 호환성) 기존처럼 문자열로 처리한다.
- `jwt.encode` 시 매번 설정을 참조하는 대신, 로드된 `cryptography` 키 객체를 직접 사용하여 성능과 안정성을 높인다.

### 2-3. Docker 컨테이너 구성 (`docker-compose.yml`)
- 호스트의 `./idp/certs` 디렉토리를 컨테이너의 `/etc/idp/certs` 경로로 읽기 전용(`:ro`) 마운트한다.
- `IDP_RSA_PRIVATE_KEY` 환경 변수를 마운트된 파일 경로로 지정한다.

---

## 3. 적용 방법 (Surefire Rebuild)

본 변경 사항은 Docker 구성(Volume, Env)의 변화를 포함하므로, 프로젝트 그라운드 룰에 따라 다음 단계를 거쳐 적용해야 한다.

```bash
# 1. 기존 컨테이너 중지 및 제거
docker compose stop mwm-idp && docker compose rm -f mwm-idp

# 2. 노캐시 빌드
docker build --no-cache -t mwm-idp -f idp/Dockerfile.idp idp

# 3. 컨테이너 가동
docker compose up -d mwm-idp
```

---

## 4. 파일 구조

- **호스트 경로**: `./idp/certs/idp_private.pem`
- **컨테이너 경로**: `/etc/idp/certs/idp_private.pem` (Read-only)

> [!IMPORTANT]
> 운영 환경에서는 반드시 암호화된 볼륨 또는 보안이 강화된 디렉토리에 PEM 파일을 위치시켜야 하며, 파일 권한(예: 600) 관리에 유의해야 한다.

---

## 5. 기대 효과
- **보안성**: 소스 코드나 환경 변수 노출 없이 파일 시스템 보안 정책에 따라 키 관리 가능.
- **운영 효율**: 컨테이너 재시작 없이(혹은 최소한의 재시작으로) 호스트의 파일 교체만으로 키 로테이션 준비 가능.
- **안정성**: 파일 부재 시 명확한 에러 로그를 남기도록 개선되어 트러블슈팅 용이.
