#!/bin/sh
# postgres 컨테이너 최초 초기화(빈 볼륨) 때 1회 실행된다 (docker-entrypoint-initdb.d).
# .sql 은 환경변수를 읽지 못하므로, 앱 계정 이름·비밀번호를 psql 변수로 넘겨 실행한다 (TASK 1-3a, 4-13).
set -eu
: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD is required}"
APP_USER=${POSTGRES_APP_USER:-mwm}
for f in /opt/mwm-init/create_db.sql /opt/mwm-init/create_idp_db.sql; do
    psql -v ON_ERROR_STOP=1 -v app_user="$APP_USER" -v app_password="$POSTGRES_APP_PASSWORD" \
         --username "$POSTGRES_USER" --dbname postgres -f "$f"
done
