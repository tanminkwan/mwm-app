# HOWTO_005: 로컬 테스트용 자체 서명 SSL 인증서 생성 가이드

> **날짜**: 2026-03-28  
> **SEQ**: 005  
> **용도**: Nginx 프록시의 SSL Termination을 위한 와일드카드 도메인 인증서 생성 (`*.mwm.local` 지원)

---

## 1. 개요

OIDC 연동 시 보안 통신(HTTPS)을 보장하기 위해, 로컬 환경에서 신뢰할 수 있는 개발용 인증서를 생성한다. 단일 인증서로 여러 도메인을 사용할 수 있도록 **SAN(Subject Alternative Name)** 설정을 포함한다.

## 2. 인증서 생성 절차 (Linux/Mac)

서버의 적절한 위치(예: `./nginx/certs/`)에서 다음 영역을 실행한다.

### 2-1. 설정 파일 작성 (`openssl.conf`)
멀티 도메인을 지원하기 위해 아래 내용을 파일로 저장한다.
# HOWTO 005 - Wildcard SSL 인증서 생성 및 관리 (*.mwm.local)

본 문서는 `mwm.local` 하위의 모든 서브도메인을 지원하는 와일드카드 SSL 인증서 생성 절차를 기술합니다.

## 1. 와일드카드 인증서 생성 (OpenSSL)

> **간단한 방법**: 저장소 루트에서 `./init_certs.sh` 를 실행하면 `nginx/certs/openssl.conf` 로 인증서를 만든다
> (이미 있으면 건너뛴다). 키·인증서는 **`./certs/nginx/`** 에 두며 git 으로 배포하지 않는다 (TASK 1-1).
> 아래의 수동 절차로 만들 때도 결과 파일은 `certs/nginx/` 에 둔다 — compose 가 그 폴더를 마운트한다.

`nginx/certs/` 디렉토리에서 다음 명령을 실행하여 인증서를 생성합니다.

```bash
# 디렉토리 생성
mkdir -p nginx/certs
cd nginx/certs

# 와일드카드 인증서 생성 (10년 유효)
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout mwm_local.key -out mwm_local.crt \
  -subj "/C=KR/ST=Seoul/L=Seoul/O=MWM/CN=*.mwm.local" \
  -addext "subjectAltName=DNS:*.mwm.local,DNS:mwm.local"
```

## 2. Nginx 설정 반영

`nginx/nginx.conf` 내부의 각 `server` 블록에서 생성된 인증서를 참조하도록 설정합니다.

```nginx
server {
    listen 443 ssl;
    server_name idp.mwm.local;

    ssl_certificate     /etc/nginx/certs/mwm_local.crt;
    ssl_certificate_key /etc/nginx/certs/mwm_local.key;
    # ... 나머지 설정 ...
}
```


1.  **브라우저 경고**: 자체 서명 인증서이므로 브라우저 접속 시 "고급 -> 이동(안전하지 않음)" 버튼을 눌러 예외를 허용해야 한다.
2.  **OS 신뢰 등록 (선택)**: 브라우저 경고를 없애고 싶다면, `mwm_local.crt` 파일을 로컬 OS의 "신뢰할 수 있는 루트 인증 기관"으로 등록한다.
3.  **도메인 매핑**: 로컬 PC의 `/etc/hosts` 파일에 아래 내용을 추가해야 브라우저가 도메인을 인식한다.
    ```text
    127.0.0.1  app.mwm.local idp.mwm.local minio.mwm.local
    ```
