# 비상대응 가이드

> **환경**: Docker Compose (`mwm-app`, `mwm-db`, `mwm-redis`, `mwm-minio`, `mwm-kroki`, `mwm-kroki-mermaid`)

---

## 1. DB 세션 강제 종료

DB 락, 세션 꼬임, `RuntimeError: number of values in row` 등 DB 관련 오류 발생 시.

```bash
# mw 데이터베이스의 모든 세션 강제 종료 (현재 세션 제외)
docker exec mwm-db psql -U postgres -d mw -c "
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'mw' AND pid != pg_backend_pid();
"
```

### 현재 활성 세션 확인
```bash
docker exec mwm-db psql -U postgres -d mw -c "
SELECT pid, usename, application_name, state, query_start, query
FROM pg_stat_activity 
WHERE datname = 'mw';
"
```

---

## 2. 컨테이너 관리

### 컨테이너 상태 확인
```bash
docker ps -a --filter "name=mwm" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```

### mwm-app 재시작
```bash
docker compose restart mwm-app
```

### mwm-app 강제 재생성 (코드 변경 반영)
```bash
docker build -t mwm-app -f Dockerfile.app .   # compose 는 빌드하지 않는다
docker compose up -d --force-recreate mwm-app
```

### 전체 컨테이너 재시작
```bash
docker compose down && docker compose up -d
```

### 특정 컨테이너 로그 확인
```bash
docker logs mwm-app --tail 100 -f
```

---

## 3. gunicorn 관련

### 컨테이너 내부에서 gunicorn 중지
```bash
docker exec mwm-app sh -c "pkill gunicorn"
# 강제 종료
docker exec mwm-app sh -c "pkill -9 gunicorn"
```

### gunicorn 프로세스 확인
```bash
docker exec mwm-app ps aux | grep gunicorn
```

---

## 4. Kroki (Mermaid 다이어그램) 서비스

### Kroki 컨테이너 시작
```bash
docker compose up -d mwm-kroki mwm-kroki-mermaid
```

### Kroki 연결 테스트
```bash
docker exec mwm-app sh -c "wget -qO- http://mwm-kroki:8000/health || echo 'FAILED'"
```

---

## 5. Redis 관련

### Redis 연결 테스트
```bash
docker exec mwm-redis redis-cli ping
# → PONG 이면 정상
```

### Redis 데이터 초기화 (주의!)
```bash
docker exec mwm-redis redis-cli FLUSHALL
```

---

## 6. DB 테이블 owner 일괄 변경

`InsufficientPrivilege` 오류 시 모든 테이블의 owner를 `mwm`로 변경.

```bash
docker exec mwm-db psql -U postgres -d mw -c "
SELECT 'ALTER TABLE ' || tablename || ' OWNER TO mwm;'
FROM pg_tables 
WHERE schemaname = 'public' AND tableowner = 'postgres';
"
# 위 출력 결과를 복사하여 실행
```

---

## 7. 빠른 진단 체크리스트

| 순서 | 확인 항목 | 명령어 |
|------|----------|--------|
| 1 | 컨테이너 상태 | `docker ps -a --filter "name=mwm"` |
| 2 | 앱 로그 | `docker logs mwm-app --tail 50` |
| 3 | DB 연결 | `docker exec mwm-db psql -U postgres -d mw -c "SELECT 1;"` |
| 4 | DB 세션 | 위 §1의 활성 세션 확인 명령 |
| 5 | Redis 연결 | `docker exec mwm-redis redis-cli ping` |
| 6 | 테이블 owner | `docker exec mwm-db psql -U postgres -d mw -c \"SELECT tablename, tableowner FROM pg_tables WHERE schemaname='public' AND tableowner!='mwm';\"` |

---

## 8. 스케줄러(APScheduler)와 멀티 프로세스 구조

현재 시스템은 **DB 기반(SQLAlchemyJobStore)** APScheduler를 사용하여 정합성과 가용성을 보장합니다.

### ✅ 주요 설계 (Architecture)
1.  **DB 공유 저장소 (`SQLAlchemyJobStore`)**: 
    *   스케줄 작업(Job) 목록을 메모리가 아닌 PostgreSQL(`apscheduler_jobs` 테이블)에 저장합니다.
    *   서버 재기동 후에도 작업 목록이 유지되며, 여러 워커가 하나의 장부를 공유합니다.
2.  **멀티 워커 지원 (`Multi-Worker`)**:
    *   Gunicorn 워커가 여러 개(`workers > 1`)여도 DB 락(Lock) 기능을 통해 **오직 한 명의 워커만** 특정 작업을 수행합니다. (중복 실행 방지)
3.  **마스터-워커 분리 (`preload_app = 0`)**:
    *   Gunicorn Master는 앱을 로드하지 않고 관리만 하며, 실제 작업을 수행하는 **Worker에서만 스케줄러가 기동**되도록 설정되어 있습니다.
4.  **실행 보정 로직 (5s Normalization)**:
    *   등록 시점과 실행 예정 시점의 오차(ms 단위)로 인해 알람을 놓치는 `Race Condition`을 방지하기 위해, 시작 시간이 지났거나 임박한 작업은 **현재 시각 + 5초** 뒤에 즉시 실행되도록 보정합니다.

### ⚠️ 운영 및 트러블슈팅
*   **작업 미실행 시**: 
    *   로그에서 `Setting start_date for ... to 5s from now` 메시지가 있는지 확인하십시오. 
    *   `misfire_grace_time`은 300초(5분)로 설정되어 있어, 일시적인 부하로 인한 지연 실행을 허용합니다.
*   **DB 세션 이슈**: 
    *   백그라운드 작업 시작 시 `db.session.remove()`를 호출하여 항상 최신 DB 데이터를 참조하도록 보장합니다.
*   **작업 수동 확인**:
    *   DB 접속 후 `SELECT * FROM apscheduler_jobs;` 명령으로 현재 예약된 모든 작업의 상태와 다음 실행 시각을 확인할 수 있습니다.

### 🚀 배포 가이드
*   코드 변경 후에는 반드시 `docker build -t mwm-app -f Dockerfile.app .` 후 `docker compose up -d --force-recreate mwm-app`을 수행하여 마스터/워커 프로세스의 스케줄러가 새로운 로직으로 갱신되도록 하십시오.

