-- IDP DB. create_db.sh 가 create_db.sql 다음에 실행한다 — psql 변수 app_user 를 받는다 (TASK 4-13).
CREATE DATABASE idp;
GRANT ALL PRIVILEGES ON DATABASE idp TO :"app_user";
ALTER DATABASE idp OWNER TO :"app_user";
