"""JEUS domain 설정 등록 API 수동 점검 스크립트.

살아있는 서버를 상대로 실행한다. pytest 테스트가 아니다.

    export MWM_URL=http://127.0.0.1:8000
    export MWM_USER=<계정>  MWM_PASSWORD=<비밀번호>
    export JEUS_DOMAIN_XML=/path/to/domain.xml
    python tests/manual/api_jeusdomain.py
"""
import json
import os
import sys

import requests

URL       = os.getenv('MWM_URL', 'http://127.0.0.1:8000')
USER      = os.getenv('MWM_USER', 'admin')
PASSWORD  = os.getenv('MWM_PASSWORD', '')
XML_PATH  = os.getenv('JEUS_DOMAIN_XML', '')
HOST_ID   = os.getenv('JEUS_HOST_ID', 'example-host-01')
DOMAIN_ID = os.getenv('JEUS_DOMAIN_ID', 'EXAMPLE_Domain')
SYSTEM_USER = os.getenv('JEUS_SYSTEM_USER', 'jeus')


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
    if not XML_PATH or not os.path.exists(XML_PATH):
        print(f'JEUS_DOMAIN_XML 경로가 필요합니다: {XML_PATH!r}')
        return 2

    try:
        token = login()
    except Exception as e:
        print(f'Login failed: {e}')
        return 1

    with open(XML_PATH, encoding='utf-8') as fd:
        content = fd.read()

    resp = requests.post(
        URL + '/api/v1/config/jeusdomain',
        data=json.dumps(dict(content=content, host_id=HOST_ID,
                             domain_id=DOMAIN_ID, system_user=SYSTEM_USER)),
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
