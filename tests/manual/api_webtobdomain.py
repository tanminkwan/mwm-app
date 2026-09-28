"""WebToB 설정 등록 API 수동 점검 스크립트.

살아있는 서버를 상대로 실행한다. pytest 테스트가 아니다.

    export MWM_URL=http://127.0.0.1:8000
    export MWM_USER=<계정>  MWM_PASSWORD=<비밀번호>
    export WEBTOB_HTTPM=/path/to/http.m
    python tests/manual/api_webtobdomain.py
"""
import json
import os
import sys

import requests

URL         = os.getenv('MWM_URL', 'http://127.0.0.1:8000')
USER        = os.getenv('MWM_USER', 'admin')
PASSWORD    = os.getenv('MWM_PASSWORD', '')
HTTPM_PATH  = os.getenv('WEBTOB_HTTPM', '')
HOST_ID     = os.getenv('WEBTOB_HOST_ID', 'example-host-01')
SYSTEM_USER = os.getenv('WEBTOB_SYSTEM_USER', 'webtob')


def login() -> str:
    resp = requests.post(
        URL + '/api/v1/security/login',
        data=json.dumps(dict(username=USER, password=PASSWORD,
                             provider='db', refresh='true')),
        headers={'Content-Type': 'application/json;charset=utf-8'},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['access_token']


def main() -> int:
    if not PASSWORD:
        print('MWM_PASSWORD 가 필요합니다.')
        return 2
    if not HTTPM_PATH or not os.path.exists(HTTPM_PATH):
        print(f'WEBTOB_HTTPM 경로가 필요합니다: {HTTPM_PATH!r}')
        return 2

    try:
        token = login()
    except Exception as e:
        print(f'Login failed: {e}')
        return 1

    with open(HTTPM_PATH, encoding='utf-8') as fd:
        content = fd.read()

    resp = requests.post(
        URL + '/api/v1/config/httpm',
        data=json.dumps(dict(content=content, host_id=HOST_ID,
                             system_user=SYSTEM_USER)),
        headers={'Content-Type': 'application/json;charset=utf-8',
                 'Authorization': 'Bearer ' + token},
        timeout=30,
    )
    print(f'Status Code: {resp.status_code}')
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False)
          if resp.status_code == 201 else resp.text)
    return 0 if resp.status_code == 201 else 1


if __name__ == '__main__':
    sys.exit(main())
