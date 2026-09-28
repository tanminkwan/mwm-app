"""배치 함수 목록 조회·실행 API 수동 점검 스크립트.

살아있는 서버를 상대로 실행한다. pytest 테스트가 아니다.

    export MWM_URL=http://127.0.0.1:8000
    export MWM_USER=<계정>  MWM_PASSWORD=<비밀번호>
    python tests/manual/api_batch.py
"""
import json
import os
import sys

import requests

from _common import BASE_URL, login

BATCH_FUNC = os.getenv('MWM_BATCH_FUNC', 'createWebtobConn')
BATCH_PARAM = os.getenv('MWM_BATCH_PARAM', 'EXAMPLE_Domain')


def main() -> int:
    try:
        token = login()
    except Exception as e:
        print(f'Login failed: {e}')
        return 1

    headers = {'Authorization': f'Bearer {token}',
               'Content-Type': 'application/json'}

    print('--- Listing Batch Functions ---')
    res = requests.get(f'{BASE_URL}/api/v1/batch/list', headers=headers, timeout=15)
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))

    print(f'\n--- Running {BATCH_FUNC} ---')
    res = requests.post(
        f'{BASE_URL}/api/v1/batch/run/{BATCH_FUNC}',
        headers=headers, json={'params': [BATCH_PARAM]}, timeout=60,
    )
    print(f'Status: {res.status_code}')
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))
    return 0 if res.status_code < 400 else 1


if __name__ == '__main__':
    sys.exit(main())
