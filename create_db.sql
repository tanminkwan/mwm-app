-- 초기 DB 구성. postgres 컨테이너가 최초 기동(빈 볼륨)할 때 1회 실행된다.
--   docker-compose.yml: create_db.sh 가 이 파일을 실행한다
--
-- 계정 이름·비밀번호는 여기에 두지 않는다. psql 변수 app_user / app_password 로 받는다 (TASK 1-3a, 4-13).
--   compose : create_db.sh 가 POSTGRES_APP_PASSWORD 를 넘긴다
--   직접 실행: psql -v ON_ERROR_STOP=1 -v app_user=mwm -v app_password='<비밀번호>' -f create_db.sql

CREATE USER :"app_user" WITH PASSWORD :'app_password';

-- 애플리케이션 DB
CREATE DATABASE mw;
GRANT ALL PRIVILEGES ON DATABASE mw TO :"app_user";
ALTER DATABASE mw OWNER TO :"app_user";

-- 테스트 DB. pytest 의 conftest 가 /mw -> /mw_test 로 바꿔 접속한다.
-- 앱 계정에 CREATEDB 권한이 없으므로 여기서 미리 만들어 둔다.
CREATE DATABASE mw_test;
GRANT ALL PRIVILEGES ON DATABASE mw_test TO :"app_user";
ALTER DATABASE mw_test OWNER TO :"app_user";
