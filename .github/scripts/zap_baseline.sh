#!/bin/sh
# ZAP baseline(수동 점검) 을 mwm-app 이미지에 돌린다 — CI 관문이자 로컬 점검 (HOWTO_020 §6).
#
#   MWM_DATABASE_URI=... .github/scripts/zap_baseline.sh            # CI: 러너의 host 네트워크
#   NET=mw_app_default MWM_DATABASE_URI=... .github/scripts/zap_baseline.sh   # 로컬: compose 네트워크
#
# 앱은 로그인 없이 보이는 화면만 점검한다. 외부 연동(SMTP·MQTT·알림·S3)은 존재하지 않는 주소로 막는다.
# 받아들이기로 한 경고는 .zap/rules.tsv 에서 IGNORE/OUTOFSCOPE 로 뺀다 — 새 경고가 하나라도 나오면 실패한다.
set -eu
cd "$(dirname "$0")/../.."
: "${MWM_DATABASE_URI:?set MWM_DATABASE_URI}"
NET=${NET:-host}
REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}
ZAP_IMAGE=ghcr.io/zaproxy/zaproxy@sha256:781a2bdaea47324e7bab583e2263f21d257b0aee61ed51521a5be45f5f5081ef  # 2.17.0
NAME=mwm-app-zapci
if [ "$NET" = host ]; then TARGET=http://localhost:8000; else TARGET=http://$NAME:8000; fi

WRK=$(mktemp -d)
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WRK"; }
trap cleanup EXIT
chmod 777 "$WRK"
cp .zap/rules.tsv "$WRK/rules.tsv" 2>/dev/null || : > "$WRK/rules.tsv"

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --network "$NET" \
    -e MWM_DATABASE_URI="$MWM_DATABASE_URI" -e REDIS_URL="$REDIS_URL" \
    -e MWM_SECRET_KEY="zap-baseline-only-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')" \
    -e MQTT_ENABLED=false -e SMTP_HOST=smtp.invalid -e SMTP_PORT=25 \
    -e NOTIFICATION_URL=https://notification.invalid/notification -e AWS_URL=http://s3.invalid:9000 \
    mwm-app >/dev/null

# 앱이 뜰 때까지 (최대 3분)
i=0
until docker run --rm --network "$NET" "$ZAP_IMAGE" curl -s -o /dev/null -w '%{http_code}' "$TARGET/login/" 2>/dev/null | grep -q 200; do
    i=$((i + 1))
    if [ $i -gt 60 ]; then echo "앱이 뜨지 않았다"; docker logs --tail 50 "$NAME"; exit 1; fi
    sleep 3
done

set +e
docker run --rm --network "$NET" -v "$WRK:/zap/wrk:rw" "$ZAP_IMAGE" \
    zap-baseline.py -t "$TARGET/" -m 3 -c rules.tsv -J report.json ${ZAP_EXTRA:-}
rc=$?
set -e
[ -n "${ZAP_REPORT_DIR:-}" ] && cp "$WRK/report.json" "$ZAP_REPORT_DIR/" 2>/dev/null || true
# 0=통과, 1=FAIL, 2=WARN, 3=점검 오류 — 모두 0 이 아니면 관문 실패
if [ $rc -ne 0 ]; then echo "ZAP baseline: 새 경고가 있다 (exit $rc). 받아들일 것이면 .zap/rules.tsv 에 이유와 함께 적는다"; fi
exit $rc
