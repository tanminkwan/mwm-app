"""수동 점검 스크립트 공용 헬퍼.

pytest 테스트가 아니다. 살아있는 서버를 상대로 사람이 실행한다.
"""
import json
import os

import requests

BASE_URL = os.getenv('MWM_URL', 'http://127.0.0.1:8000')
USER     = os.getenv('MWM_USER', 'admin')
PASSWORD = os.getenv('MWM_PASSWORD', '')


def login(base_url: str = None) -> str:
    """로그인해서 access token 을 받는다.

    `MWM_TOKEN` 이 설정되어 있으면 그 값을 그대로 쓴다.
    비밀번호는 코드에 두지 않는다 - `MWM_PASSWORD` 로만 주입한다.
    """
    token = os.getenv('MWM_TOKEN')
    if token:
        return token

    if not PASSWORD:
        raise RuntimeError(
            'MWM_PASSWORD 또는 MWM_TOKEN 환경변수가 필요합니다.')

    resp = requests.post(
        (base_url or BASE_URL) + '/api/v1/security/login',
        data=json.dumps(dict(username=USER, password=PASSWORD,
                             provider='db', refresh='true')),
        headers={'Content-Type': 'application/json;charset=utf-8'},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['access_token']
