#!/bin/sh
# 새 설치에서 키·인증서를 만든다 (TASK 1-1). ./certs/ 는 git 으로 배포하지 않는다 (.gitignore).
#   certs/idp/idp_private.pem   IDP 의 ID Token 서명 키 (RS256)
#   certs/nginx/mwm_local.key   nginx TLS 개인키
#   certs/nginx/mwm_local.crt   자체 서명 인증서 (*.mwm.local). 설정은 nginx/certs/openssl.conf
#
# 이미 있는 파일은 건드리지 않는다. 키를 바꾸면 발급된 ID Token 검증과 브라우저의 인증서 신뢰가 깨진다.
set -eu
cd "$(dirname "$0")"
umask 077
mkdir -p certs/idp certs/nginx

if [ -e certs/idp/idp_private.pem ]; then
    echo "skip: certs/idp/idp_private.pem (exists)"
else
    openssl genpkey -quiet -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out certs/idp/idp_private.pem
    echo "created: certs/idp/idp_private.pem"
fi

if [ -e certs/nginx/mwm_local.key ] || [ -e certs/nginx/mwm_local.crt ]; then
    echo "skip: certs/nginx/mwm_local.{key,crt} (exists)"
else
    openssl req -x509 -nodes -days 825 -newkey rsa:2048 -config nginx/certs/openssl.conf \
        -keyout certs/nginx/mwm_local.key -out certs/nginx/mwm_local.crt 2>/dev/null
    chmod 644 certs/nginx/mwm_local.crt
    echo "created: certs/nginx/mwm_local.{key,crt}"
fi
