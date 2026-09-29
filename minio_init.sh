#!/bin/sh
# 번들 MinIO(개발용)에 앱용 액세스 키와 버킷을 만든다 (TASK 1-4). mwm-minio-init 이 한 번 실행한다.
# 이미 그 키로 버킷에 닿으면 아무것도 하지 않는다 — 기존 MinIO 의 사용자·정책을 건드리지 않는다.
set -eu
: "${AWS_ACCESS_KEY_ID:?}" "${AWS_SECRET_ACCESS_KEY:?}" "${BUCKET_NAME:?}"
EP=http://mwm-minio:9000
ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}

i=0
until mc alias set root "$EP" "$ROOT_USER" "$ROOT_PASSWORD" >/dev/null 2>&1; do
    i=$((i + 1)); [ "$i" -ge 60 ] && { echo "MinIO 에 root 로 접속하지 못했다"; exit 1; }
    sleep 2
done

# MinIO 는 root 로그인을 먼저 받고 사용자(IAM)는 조금 늦게 읽는다 — 앱 키 확인은 몇 번 재시도한다
i=0
while [ "$i" -lt 15 ]; do
    if mc alias set app "$EP" "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" >/dev/null 2>&1 \
       && mc ls "app/$BUCKET_NAME" >/dev/null 2>&1; then
        echo "skip: 앱 키로 버킷 '$BUCKET_NAME' 에 이미 닿는다"
        exit 0
    fi
    i=$((i + 1)); sleep 2
done

mc mb --ignore-existing "root/$BUCKET_NAME"
mc admin user add root "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY"
mc admin policy attach root readwrite --user "$AWS_ACCESS_KEY_ID" 2>/dev/null || true
echo "created: 앱 사용자와 버킷 '$BUCKET_NAME'"
