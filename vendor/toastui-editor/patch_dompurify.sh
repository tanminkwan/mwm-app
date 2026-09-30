#!/bin/sh
# app/static/js/toastui-editor-all.min.js 의 DOMPurify 를 DOMPurify_VERSION 으로 바꾼다 (HOWTO_020 §5).
# 인터넷 필요 — 개발 PC 에서 돌리고 결과 파일을 커밋한다 (운영은 폐쇄망이라 파일째 옮긴다).
#
#   vendor/toastui-editor/patch_dompurify.sh
set -eu
cd "$(dirname "$0")/../.."
DOMPURIFY_VERSION=3.4.16
ACORN_VERSION=8.18.0

docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/src" -w /tmp node:22-slim sh -euc "
    npm pack --silent dompurify@$DOMPURIFY_VERSION >/dev/null
    tar xzf dompurify-$DOMPURIFY_VERSION.tgz
    npm install --silent --no-save acorn@$ACORN_VERSION >/dev/null
    cp /src/vendor/toastui-editor/patch_dompurify.mjs .
    node patch_dompurify.mjs /src/app/static/js/toastui-editor-all.min.js package/dist/purify.min.js"
