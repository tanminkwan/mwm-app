import os

from _common import login

import requests
import json
import sys

BASE_URL = os.getenv("MWM_URL", "http://127.0.0.1:8000")

def main():

    # 토큰은 환경변수로 주입한다. 없으면 로그인해서 발급받는다.
    token = os.getenv('MWM_TOKEN') or login()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "sender_name": "Antigravity Test (Auth API)",
        "receivers": os.getenv("MWM_TEST_RECEIVERS", "someone@example.com"),
        "subject": "[Leebalso] Email Auth API Test",
        "content": "<h1>성공</h1><p>보안 설정 및 토큰 인증 발송 테스트 결과입니다.</p>"
    }

    print("\nExecuting email send request (With Authentication Token)...")
    # EmailApi has resource_name = 'email'
    res = requests.post(f"{BASE_URL}/api/v1/email/send", headers=headers, json=payload, timeout=15)
    
    print(f"Status: {res.status_code}")
    try:
        print(json.dumps(res.json(), indent=2, ensure_ascii=False))
    except Exception:
        print("Response is not JSON:")
        print(res.text[:500])

    if res.status_code == 200:
        print("\nTest PASSED.")
    else:
        print("\nTest FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    main()
