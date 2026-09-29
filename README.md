# 🛠️ MWM (Middleware Management System) - 미들웨어관리소

[![CI](https://github.com/tanminkwan/mwm-app/actions/workflows/python-app.yml/badge.svg)](https://github.com/tanminkwan/mwm-app/actions/workflows/python-app.yml)
[![CodeQL](https://github.com/tanminkwan/mwm-app/actions/workflows/codeql.yml/badge.svg)](https://github.com/tanminkwan/mwm-app/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)

## 📋 프로젝트 개요
**미들웨어관리소(MWM)**는 미들웨어(WAS, WEB) 및 IT 자산의 상태를 모니터링하고, 변경 사항을 대사(Compare)하며, Kroki 기반의 Mermaid 다이어그램을 포함한 고급 이메일 리포트를 생성하는 통합 관리 솔루션입니다.

## ✨ 주요 기능 및 특징

### 🔍 미들웨어 관리 & 자동화
- **실시간 모니터링**: JEUS, WebToB 인스턴스 상태 추적 및 장애 탐지.
- **유연한 데이터 수집(Agent DML)**: 
  - 정규표현식(Regex) 기반 파일 매칭 지원 (`domain.*\.xml` 등).
  - 설치 경로 분석을 통한 도메인 ID 자동 추출 및 PK 매칭.
  - 설정 파일 변경분 대사(DeepDiff) 및 히스토리 관리.
- **가시성 최적화**: WAS/WEB 간의 복잡한 연결 관계를 시각화한 Relationship Diagram 제공.
- **실시간 명령 전달(MQTT)**: 명령 생성 즉시 MQTT 브로커로 push 하여 에이전트 폴링 주기만큼의
  지연을 제거 (실측 2초 내 수행 완료). 발행 실패 시 기존 REST 폴링으로 자동 fallback 되므로
  브로커 장애가 기능 장애로 번지지 않음. 기본 비활성(`MQTT_ENABLED`)으로 opt-in.

### 🛡️ 데이터 정합성 & 보안 강화
- **통합 인증 체계**: OIDC/OAuth2 기반의 SSO 및 **개인 인증 토큰(JWT)** 발급 시스템 구축.
- **API 보안**: 외부 툴 연동을 위한 1년(365일) 유효 장기 토큰 관리 기능 (`나의 정보` 메뉴).
- **Host ID 표준화**: 시스템 전반의 `host_id`를 소문자로 강제 통일하여 장애 원천 차단.
- **지식정보 그룹 권한**: Role 기반 접근제어(UtKmGroup)를 통한 콘텐츠 보안 강화.

### 📧 고급 리포팅 & API 연동
- **Smart Email API (Markdown/HTML)**:
  - **Mermaid 다이어그램**: 본문에 포함된 Mermaid 코드를 이미지로 자동 렌더링하여 삽입.
  - **S3 이미지 인라인**: 오브젝트 스토리지(MinIO) 링크를 감지하여 본문 내장(CID) 이미지로 자동 변환.
- **협업 최적화**: Select2 기반의 유연한 수신자 선택 및 Markdown 기반 지식베이스 구축.

## 🏗️ 시스템 아키텍처

- **Backend**: Python 3.12, Flask 3.1, Flask-AppBuilder 5
- **Persistent Scheduler**: 
  - **SQLAlchemyJobStore** 도입으로 스케줄 정보 DB 영구 저장.
  - Multi-Worker(Gunicorn) 환경에서도 안전한 단일 스케줄러 인스턴스 보장.
- **Storage/Cache**: PostgreSQL 15, Redis 7+ (Session & Cache)
- **Messaging**: Eclipse Mosquitto 2.0 (MQTT 5) — 에이전트 실시간 명령 전달 채널.
  발행 전용 ACL(`topic write cmd/#`)로 컨트롤러 권한을 최소화하고, 브로커 영속 세션으로
  오프라인 에이전트에도 명령을 큐잉.
- **Engine 연동**: Kroki (Mermaid 렌더링), MinIO/S3 (오브젝트 스토리지)

## 📂 주요 가이드 (Documentation)
- **[테스트 작성 가이드](docs/HOWTO_018_writing_tests.md)**: 실행 방법, 특성화 테스트 패턴, 밟았던 함정, CI 관문.
- **[Email API 연동 가이드 (초보용)](docs/HOWTO_010_email_api_guide.md)**: 토큰 발급부터 Python 연동 샘플까지 포함.
- **[비상 대응 가이드 (Emergency Response)](docs/emergency_response.md)**: DB 세션 정리 및 컨테이너 복구 절차.
- **[OAuth2 & OIDC 연동 가이드](idp/README.md)**: IDP 서버 구성 및 SSO 설정.
- **[에이전트 명령 시스템](docs/agent_command_system.md)**: 명령 생성·배포·결과 수집의 전체 구조.
- **[CommandMaster API 가이드](docs/HOWTO_012_command_master_api.md)**: REST 로 명령 생성 및 결과 조회.
- **[MQTT 실시간 명령 전달](docs/HOWTO_016_mqtt_realtime_command.md)**: 브로커 구성, ACL, 재접속 정책, 구현 상세.

## 🚀 시작하기

**빌드·테스트·실행을 모두 Docker 안에서 합니다.** 호스트에 venv 를 만들지 않습니다.

### 이미지 빌드

이미지는 5개이며, `mwm-test`·`mwm-idp-test` 는 CI·개발 전용입니다.

```bash
docker build -t mwm-base -f Dockerfile.base .              # requirements.txt 설치 — 바뀔 때만
docker build -t mwm-app  -f Dockerfile.app  .              # 소스 코드만 COPY
docker build -t mwm-idp  -f idp/Dockerfile.idp idp         # IDP 서버
docker build -t mwm-test -f Dockerfile.test .              # mwm-app + 테스트 도구 (CI·개발 전용)
docker build -t mwm-idp-test -f idp/Dockerfile.test idp    # mwm-idp + 테스트 도구 (CI·개발 전용)
```

> **`docker compose` 는 이미지를 빌드하지 않습니다.** 빌드는 위 명령으로만 하고, compose 는 만들어진 이미지를
> 실행만 합니다. 이미지가 없으면 compose 는 Docker Hub 에서 받지 않고 `No such image` 로 멈춥니다.
> `requirements.txt` 를 바꿨다면 `mwm-base` 부터 다시 빌드해야 반영됩니다.

### 실행

```bash
cp .env.example .env                                  # '필수' 칸을 채운다
./init_certs.sh                                       # 키·인증서 생성 (certs/, git 으로 배포하지 않는다)
docker compose up -d                                  # DB 초기화가 끝나면 IDP·앱이 뜬다
docker exec -it mwm-app flask fab create-admin        # 최초 1회 — 관리자 계정 생성
docker compose restart mwm-idp                        # 만든 계정을 IDP 로 동기화 (IDP 는 기동 때 동기화한다)
docker exec -i mwm-db psql -U mwm -d mw -f /dev/stdin < seed_data.sql   # 최초 1회 — 기본 명령 유형 등 (MWM_DB_USER 를 바꿨다면 그 이름)
```

### 접속

nginx 가 도메인별로 나눠 줍니다(자체 서명 인증서라 브라우저 경고가 뜹니다). 먼저 hosts 에 도메인을 등록합니다.

```
127.0.0.1  app.mwm.local idp.mwm.local minio.mwm.local s3.mwm.local     # /etc/hosts
```

| 서비스 | 주소 |
| :--- | :--- |
| 앱 | https://app.mwm.local:20443 (직접: http://localhost:8000) |
| IDP (SSO) | https://idp.mwm.local:20443 |
| MinIO 콘솔 | https://minio.mwm.local:20443 |

### 테스트

테스트 러너는 운영 이미지에 없습니다(`requirements-dev.txt`). `mwm-test` 에서 돌립니다.

```bash
docker run --rm --network host \
  -v "$PWD/tests:/app/tests" \
  -v "$PWD/pytest.ini:/app/pytest.ini:ro" \
  -e MWM_DATABASE_URI="postgresql://<user>:<password>@localhost:<port>/mw" \
  mwm-test pytest -q
```

- **운영 DB 를 건드리지 않습니다.** `tests/conftest.py` 가 URI 끝의 `/mw` 를 `/mw_test` 로
  바꾸고, 그렇지 않으면 실행을 중단합니다.
- 신규 설치라면 `create_db.sql` 이 `mw_test` 도 함께 만듭니다. 기존 DB 에 없다면 한 번 만듭니다
  (앱 계정에는 `CREATEDB` 권한이 없습니다):
  `docker exec mwm-db psql -U postgres -c "CREATE DATABASE mw_test OWNER <DB 계정>;"`
- **새로 생기는 `DeprecationWarning` 은 테스트를 실패시킵니다.** 라이브러리 업그레이드의
  조기 경보이기 때문입니다. 지금 나는 것만 `pytest.ini` 의 `filterwarnings` 에
  이유와 함께 유예해 두었습니다.
- 등록하지 않은 marker 를 쓰면 에러입니다(`strict = True`). marker 는 `pytest.ini` 에 추가하세요.

커버리지를 함께 재려면 `.coveragerc` 를 마운트하고 `--cov` 를 붙입니다
(계측이 실행 시간을 약 2배로 늘리므로 기본 실행에는 넣지 않았습니다).

```bash
docker run --rm --network host \
  -v "$PWD/tests:/app/tests" \
  -v "$PWD/pytest.ini:/app/pytest.ini:ro" \
  -v "$PWD/.coveragerc:/app/.coveragerc:ro" \
  -e MWM_DATABASE_URI="postgresql://<user>:<password>@localhost:<port>/mw" \
  mwm-test pytest --cov
```

커버리지 하한은 `.coverage-baseline` 에 있고 CI 가 강제합니다 — [테스트 작성 가이드](docs/HOWTO_018_writing_tests.md) 참고.

### 린트

설정은 `.flake8` 에 있습니다. 정책은 2단계입니다.

1. **차단 검사** — 문법 오류·미정의 이름(`E9`, `F63`, `F7`, `F82`). 현재 0건이며 0건을 유지합니다.
2. **스타일 래칫** — 나머지 전부. 총계가 `.flake8-baseline` 을 넘으면 CI 가 실패합니다.
   기존 위반은 용인하되 **새 위반은 막습니다.**

```bash
docker run --rm -v "$PWD:/src" -w /src python:3.12.14-slim-bookworm sh -euc '
  pip install -q -r requirements-dev.txt
  flake8 . --count --select=E9,F63,F7,F82 --show-source   # 1) 차단 검사
  flake8 . --count --exit-zero --statistics -q -q          # 2) 총계 (기준선과 비교)
'
```

위반을 줄였다면 `.flake8-baseline` 의 숫자도 함께 낮춰 커밋하세요 — 그래야 래칫이 조여집니다.
CI(`.github/workflows/python-app.yml`)가 같은 명령을 돌립니다.

### MQTT 실시간 명령 전달 활성화 (선택)
기본값은 비활성이며, 켜지 않아도 기존 REST 폴링으로 정상 동작합니다.

1. `.env` 에 브로커 설정을 넣습니다 (`.env.example` 을 다시 복사하면 채운 값이 지워집니다).
   ```bash
   MQTT_ENABLED=True
   MQTT_PASSWORD=<발급받은 값>
   ```
2. 컨테이너를 재기동합니다. **환경변수이므로 이미지 재빌드는 필요하지 않습니다.**
   ```bash
   docker compose up -d --force-recreate mwm-app
   ```
3. 명령 생성 시 `command_sender: "MQTT"` 를 지정하면 즉시 push 됩니다
   (미지정 시 기본값 `SERVER` = 기존 폴링 방식).

> 의존성(`paho-mqtt`)을 추가·갱신했다면 **base 이미지부터** 다시 빌드해야 합니다
> (위 [이미지 빌드](#이미지-빌드) 참고).
> 자세한 내용은 [HOWTO_016](docs/HOWTO_016_mqtt_realtime_command.md) 참고.

## 🛠️ 유지보수 및 진단
- **로그 모니터링**: 
  ```bash
  docker logs -f mwm-app
  ```

## 📄 라이선스

[MIT](LICENSE)
