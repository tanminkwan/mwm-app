# DB Migration 가이드 (Flask-Migrate / Alembic)

> **환경**: Docker Compose (`mwm-app`, `mwm-db`)  
> **DB**: PostgreSQL 15 · 사용자: `mwm` (`.env` 의 `MWM_DB_USER`, 기본 `mwm`) · 데이터베이스: `mw`  
> **프레임워크**: Flask-AppBuilder + Flask-Migrate (Alembic)

---

## 1. 기본 마이그레이션 절차

### 1-1. mwm-app 컨테이너 shell 접속
```bash
docker exec -it mwm-app sh
```

### 1-2. gunicorn 프로세스 중지
> Flask CLI(`flask db`)가 정상 동작하려면 gunicorn이 점유 중인 포트/리소스를 해제해야 합니다.
```bash
pkill gunicorn
```

### 1-3. 마이그레이션 파일 생성 (autogenerate)
> 모델(`app/models/*.py`)과 현재 DB 스키마를 비교하여 변경사항을 자동 감지합니다.
```bash
flask db migrate -m "변경 내용 요약"
```
- 생성된 파일: `migrations/versions/<revision_id>_<slug>.py`
- **반드시 생성된 파일을 열어 내용을 검토**하세요. 자동 감지가 완벽하지 않을 수 있습니다.

### 1-4. 마이그레이션 적용 (upgrade)
```bash
flask db upgrade
```

### 1-5. gunicorn 재시작 또는 컨테이너 재시작
```bash
# 방법 1: 컨테이너 내부에서 gunicorn 재시작
gunicorn -c gunicorn_config.py run:app &

# 방법 2: 컨테이너 외부에서 재시작 (호스트에서 실행)
docker compose restart mwm-app
```

---

## 2. 자주 사용하는 명령어

| 명령어 | 설명 |
|--------|------|
| `flask db current` | 현재 DB가 가리키는 마이그레이션 버전 확인 |
| `flask db history` | 전체 마이그레이션 히스토리 조회 |
| `flask db heads` | 최신 마이그레이션 버전(head) 확인 |
| `flask db upgrade` | head까지 마이그레이션 적용 |
| `flask db upgrade <revision>` | 특정 버전까지 마이그레이션 적용 |
| `flask db downgrade -1` | 바로 이전 버전으로 롤백 |
| `flask db downgrade <revision>` | 특정 버전으로 롤백 |
| `flask db stamp head` | 실제 DDL 실행 없이 현재 DB를 head로 마킹 |
| `flask db show <revision>` | 특정 마이그레이션 파일의 상세 내용 조회 |

---

## 3. 마이그레이션 없이 수동으로 스키마를 변경한 경우

모델을 수정하고 DB에 직접 `ALTER TABLE`을 실행한 경우, Alembic이 인식하는 버전과 실제 DB 스키마가 불일치합니다.  
이때는 **stamp** 명령으로 현재 상태를 head로 마킹합니다.

```bash
# 1. 컨테이너 접속
docker exec -it mwm-app sh

# 2. gunicorn 중지
pkill gunicorn

# 3. 빈 마이그레이션 생성 시도 (변경사항 없음 확인)
flask db migrate -m "sync after manual ALTER"
# → "No changes in schema detected." 가 나오면 정상

# 4. 현재 DB를 최신 버전으로 마킹
flask db stamp head

# 5. 확인
flask db current
# → (head) 표시되면 성공
```

---

## 4. DB 스키마 직접 확인 (호스트에서 실행)

```bash
# 테이블 구조 확인
docker exec mwm-db psql -U postgres -d mw -c "\d+ <테이블명>"

# 예시
docker exec mwm-db psql -U postgres -d mw -c "\d+ it_was"
docker exec mwm-db psql -U postgres -d mw -c "\d+ it_web"
docker exec mwm-db psql -U postgres -d mw -c "\d+ mw_was"

# 전체 테이블 목록
docker exec mwm-db psql -U postgres -d mw -c "\dt"
```

---

## 5. 권한 부여

테이블을 `postgres` 사용자로 생성한 경우 앱 사용자(`mwm`)에게 권한을 부여해야 합니다.

```bash
docker exec mwm-db psql -U postgres -d mw -c "
GRANT ALL PRIVILEGES ON TABLE <테이블명> TO mwm;
"
```

---

## 6. 주의사항

1. **모델 수정 후 반드시 `flask db migrate` 실행**  
   - 모델 파일만 수정해도 DB 스키마는 자동으로 변경되지 않습니다.

2. **마이그레이션 파일은 Git에 커밋**  
   - `migrations/versions/*.py` 파일은 반드시 Git에 포함시켜야 다른 환경에서도 동일한 스키마를 유지할 수 있습니다.

3. **Enum 타입 변경 시 주의**  
   - PostgreSQL의 Enum 타입은 `ALTER TYPE ... ADD VALUE`로만 값을 추가할 수 있습니다. Alembic 자동 감지가 안 될 수 있으므로 수동 편집이 필요합니다.

4. **on-premise 배포 시**  
   - 컨테이너 접속 → `pkill gunicorn` → `flask db upgrade` → gunicorn 재시작 순서로 진행합니다.
   - 또는 `tmp/backup_update_report_20260212.md`에 포함된 SQL 스크립트를 직접 실행할 수 있습니다.

---

## 7. 마이그레이션 히스토리 (현재까지)

| Revision | 날짜 | 주요 변경 내용 |
|----------|------|---------------|
| `1f22dabe20a9` | 초기 | 최초 마이그레이션 |
| `8929a1afeddb` | - | 스키마 변경 |
| `e5639b1cfd99` | 2024-08-08 | `ag_command_master.interval_type` Enum 변환, `mw_was.was_text` comment 변경, `mw_web.web_text` / `mw_web_change_history.old_web_text` 컬럼 추가 |
| `8e5111323215` | 2026-02-26 | ITAM 대사 결과 테이블 4개 추가 (`it_itam_was_compare`, `it_itam_web_compare`, `it_leebalso_was_compare`, `it_leebalso_web_compare`) |
| `cc8f86f77bff` | 2026-03-05 | 새 컨테이너 초기화 후 재생성. `it_was`/`it_web` comment 추가, `mw_was.blackout_info` comment, `mw_was_httplistener.ssl_yn` VARCHAR→Enum 변환 |

---

## 8. 트러블슈팅

### 8-1. `Path doesn't exist: '/app/migrations'` 오류

컨테이너 내부에 `migrations` 폴더가 없는 경우 발생. 코드 동기화(빌드/볼륨마운트) 후 `flask db init`으로 초기화 필요.

```bash
flask db init
```

### 8-2. `Can't locate revision identified by 'xxxx'` 오류

DB의 `alembic_version` 테이블에 기록된 revision이 `migrations/versions/` 폴더에 없는 경우 발생. `flask db init`으로 새로 초기화한 경우 자주 발생.

```bash
# alembic_version 초기화 후 다시 migrate
docker exec mwm-db psql -U postgres -d mw -c "DELETE FROM alembic_version;"
flask db migrate -m "변경 내용"
flask db upgrade
```

> **`flask db upgrade` 실패 시**: 아래 8-6, 8-7을 참고하세요. autogenerate가 이미 반영된 변경을 잘못 감지하거나 타입 캐스팅 문제가 발생할 수 있습니다. 이 경우 수동 수정 후 `flask db stamp head`로 우회합니다.

### 8-3. `InsufficientPrivilege: must be owner of relation` 오류

`flask db migrate`가 기존 테이블(예: `it_was`, `it_web`)의 COMMENT 변경 등을 감지했으나, 해당 테이블의 owner가 앱 사용자(`mwm`)가 아닌 `postgres`인 경우 발생.

**해결 방법 1**: 테이블 owner를 `mwm`로 변경
```bash
docker exec mwm-db psql -U postgres -d mw -c "
ALTER TABLE it_was OWNER TO mwm;
ALTER TABLE it_web OWNER TO mwm;
"
```

**해결 방법 2**: 마이그레이션 없이 직접 SQL로 테이블 생성 후 `stamp head`
```bash
# postgres 사용자로 직접 테이블 생성
docker exec mwm-db psql -U postgres -d mw -c "CREATE TABLE ... ;"

# 권한 부여
docker exec mwm-db psql -U postgres -d mw -c "GRANT ALL PRIVILEGES ON TABLE <테이블명> TO mwm;"

# alembic 버전 마킹 (컨테이너 내부)
flask db stamp head
```

### 8-4. `flask db upgrade` 실행 중 멈춤 (Hang)

다른 프로세스(gunicorn 등)가 참조 테이블에 트랜잭션을 잡고 있어 FK 생성 시 락 대기 상태가 되는 경우 발생.

```bash
# 1. gunicorn 중지 (컨테이너 내부에서)
pkill -9 gunicorn

# 2. DB의 모든 블로킹 세션 강제 종료 (호스트에서)
docker exec mwm-db psql -U postgres -d mw -c "
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'mw' AND pid != pg_backend_pid();
"

# 3. 다시 upgrade 시도
flask db upgrade
```

### 8-5. 테이블 owner 확인

```bash
docker exec mwm-db psql -U postgres -d mw -c "
SELECT tablename, tableowner FROM pg_tables 
WHERE schemaname = 'public' ORDER BY tableowner, tablename;
"
```

### 8-6. 새 컨테이너에서 `migrations/versions/`가 비어 있는 경우

새로 빌드한 컨테이너에 migration 파일이 없고, DB의 `alembic_version`도 비어 있는(또는 위치 못 찾는) 경우. DB 테이블은 이미 존재하지만 Alembic 이력이 없는 상태.

```bash
# 1. 호스트에서: alembic_version 초기화 (이미 비어 있으면 생략 가능)
docker exec mwm-db psql -U postgres -d mw -c "DELETE FROM alembic_version;"

# 2. 컨테이너 접속
docker exec -it mwm-app sh

# 3. gunicorn 중지 (실행 중인 경우)
pkill gunicorn

# 4. 마이그레이션 생성 — 주로 comment 변경, 타입 변경만 감지됨
flask db migrate -m "init after new container"

# 5-a. upgrade 시도
flask db upgrade
# → 성공하면 완료

# 5-b. upgrade 실패 시 (타입 캐스팅 에러 등)
#    → 수동으로 필요한 DDL만 실행 후 stamp head (아래 8-7 참고)
docker exec mwm-db psql -U postgres -d mw -c "DELETE FROM alembic_version;"
# (수동 DDL 실행)
flask db stamp head

# 6. 확인
flask db current
# → (head) 표시되면 성공

# 7. 컨테이너 재시작 (호스트에서)
docker compose restart mwm-app
```

### 8-7. `DatatypeMismatch: column cannot be cast automatically to type` 오류

`flask db upgrade` 시 VARCHAR→Enum 변환에서 자동 캐스팅이 안 되는 경우 발생.
예: `mw_was_httplistener.ssl_yn`을 `VARCHAR(10)`에서 `ynenum`으로 변경 시.

```
sqlalchemy.exc.ProgrammingError: column "ssl_yn" cannot be cast automatically to type ynenum
HINT: You might need to specify "USING ssl_yn::ynenum".
```

**해결 방법**: 수동으로 USING 절을 사용하여 변환 후 `stamp head`

```bash
# 1. 호스트에서: alembic_version 초기화
docker exec mwm-db psql -U postgres -d mw -c "DELETE FROM alembic_version;"

# 2. 수동 타입 변환 (USING 절 사용)
docker exec mwm-db psql -U postgres -d mw -c "
ALTER TABLE mw_was_httplistener ALTER COLUMN ssl_yn TYPE ynenum USING ssl_yn::ynenum;
"

# 3. 컨테이너 내부에서 stamp head
flask db stamp head

# 4. 확인
flask db current
```

---

## 9. ITAM 대사 테이블 생성 SQL (수동 생성 시 사용)

> 2026-02-26 추가. `flask db migrate/upgrade` 대신 직접 생성할 때 사용.

```sql
CREATE TABLE it_itam_was_compare (
    id SERIAL PRIMARY KEY,
    config_id VARCHAR(50) NOT NULL REFERENCES it_was(config_id) ON DELETE CASCADE,
    error_type VARCHAR(100) NOT NULL,
    error_content TEXT,
    action_yn VARCHAR(3) DEFAULT 'NO',
    user_id VARCHAR(50) NOT NULL,
    create_on TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE it_itam_web_compare (
    id SERIAL PRIMARY KEY,
    config_id VARCHAR(50) NOT NULL REFERENCES it_web(config_id) ON DELETE CASCADE,
    error_type VARCHAR(100) NOT NULL,
    error_content TEXT,
    action_yn VARCHAR(3) DEFAULT 'NO',
    user_id VARCHAR(50) NOT NULL,
    create_on TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE it_leebalso_was_compare (
    id SERIAL PRIMARY KEY,
    leebalso_id INTEGER NOT NULL REFERENCES mw_was(id) ON DELETE CASCADE,
    error_type VARCHAR(100) NOT NULL,
    error_content TEXT,
    action_yn VARCHAR(3) DEFAULT 'NO',
    user_id VARCHAR(50) NOT NULL,
    create_on TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE it_leebalso_web_compare (
    id SERIAL PRIMARY KEY,
    leebalso_id INTEGER NOT NULL REFERENCES mw_web(id) ON DELETE CASCADE,
    error_type VARCHAR(100) NOT NULL,
    error_content TEXT,
    action_yn VARCHAR(3) DEFAULT 'NO',
    user_id VARCHAR(50) NOT NULL,
    create_on TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 권한 부여
GRANT ALL PRIVILEGES ON TABLE it_itam_was_compare TO mwm;
GRANT ALL PRIVILEGES ON TABLE it_itam_web_compare TO mwm;
GRANT ALL PRIVILEGES ON TABLE it_leebalso_was_compare TO mwm;
GRANT ALL PRIVILEGES ON TABLE it_leebalso_web_compare TO mwm;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mwm;
```

---

## 10. 지식관리 그룹 테이블 생성 SQL (수동 생성 시 사용)

> 2026-03-05 추가. `ut_km_group` 및 association 테이블.

```sql
CREATE TABLE ut_km_group (
    id SERIAL PRIMARY KEY,
    group_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE ut_kmgroup_htmlcontent (
    id SERIAL PRIMARY KEY,
    id_of_group INTEGER NOT NULL REFERENCES ut_km_group(id) ON DELETE CASCADE,
    id_of_htmlcontent INTEGER NOT NULL REFERENCES ut_html_content(id) ON DELETE CASCADE
);

CREATE TABLE ut_kmgroup_mdcontent (
    id SERIAL PRIMARY KEY,
    id_of_group INTEGER NOT NULL REFERENCES ut_km_group(id) ON DELETE CASCADE,
    id_of_mdcontent INTEGER NOT NULL REFERENCES ut_md_content(id) ON DELETE CASCADE
);

-- 권한 부여
GRANT ALL PRIVILEGES ON TABLE ut_km_group TO mwm;
GRANT ALL PRIVILEGES ON TABLE ut_kmgroup_htmlcontent TO mwm;
GRANT ALL PRIVILEGES ON TABLE ut_kmgroup_mdcontent TO mwm;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mwm;
```

---

## 11. IDP DB (`idp`) 컬럼 추가 SQL

> 2026-10-07 추가. IDP(`mwm-idp`)는 Alembic 을 쓰지 않는다 — 기동 시 `db.create_all()` 이 **없는 테이블만** 만들고
> 기존 테이블의 컬럼은 추가하지 않는다. 그래서 컬럼이 늘면 아래 SQL 을 **새 이미지보다 먼저** 적용한다.
> 대상 DB 는 `mw` 가 아니라 **`idp`** 이다 (`-d idp`).

### 11-1. 로그인 잠금 (`idp_user`)

연속 로그인 실패 횟수와 잠금 해제 시각. 기본 5회 실패 → 15분 잠금 (`IDP_LOGIN_MAX_ATTEMPTS`, `IDP_LOGIN_LOCK_MINUTES`).

```sql
ALTER TABLE idp_user
    ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until       TIMESTAMP WITHOUT TIME ZONE;
```

- 적용·되돌리기 파일: `docs/sql/20261007_add_idp_login_lockout.sql`, `docs/sql/20261007_add_idp_login_lockout_rollback.sql` (확인 쿼리와 순서 설명 포함)
- 순서: **SQL 먼저 → 새 mwm-idp.** 구 앱은 새 컬럼을 몰라도 동작하지만, 새 앱을 SQL 없이 띄우면 `idp_user` 조회가 모두 실패해 로그인이 막힌다.
- 적용 (호스트에서):
  ```bash
  docker exec -i mwm-db psql -U <DB 사용자> -d idp \
      -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20261007_add_idp_login_lockout.sql
  ```
- 잠긴 계정을 바로 풀기:
  ```sql
  UPDATE idp_user SET locked_until = NULL, failed_login_count = 0 WHERE username = '<계정>';
  ```
