import os

from _common import login

import requests
import json
import sys

# 미들웨어관리소 API 서버 주소 (Container 내부에서 실행 시 127.0.0.1:8000)
BASE_URL = os.getenv("MWM_URL", "http://127.0.0.1:8000")

def main():
    """
    /api/v1/markdown/to_html API를 호출하여
    Markdown 본문을 HTML로 변환하는 기능을 테스트하는 스크립트입니다.
    """

    # 토큰은 환경변수로 주입한다. 없으면 로그인해서 발급받는다.
    token = os.getenv('MWM_TOKEN') or login()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    markdown_content = """# 📊 시스템 점검 종합 분석 보고서

## 1. 개요
본 보고서는 미들웨어관리소 시스템의 **정기 점검** 결과를 기반으로 작성되었습니다.

## 2. 서비스 운영 지표
| 분류 | 상태 | 상세 내용 |
| :--- | :---: | :--- |
| **API Server** | ✅ 정상 | 평균 응답속도 45ms 유지 |

## 3. 서비스 구성도 (Mermaid)
```mermaid
graph LR;
    Client((User)) --> WAF[Web Firewall];
    WAF --> LB[Load Balancer];
```
"""

    payload = {
        "content": markdown_content
    }

    print(f"\n🚀 Sending Markdown to HTML conversion request...")
    print(f"URL: {BASE_URL}/api/v1/markdown/to_html")

    try:
        res = requests.post(
            f"{BASE_URL}/api/v1/markdown/to_html",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"Status Code: {res.status_code}")
        
        try:
            res_json = res.json()
            print("Response Response:")
            if "html" in res_json:
                print("HTML content preview (first 500 chars):")
                print(res_json["html"][:500] + "...")
            else:
                print(json.dumps(res_json, indent=2, ensure_ascii=False))
        except Exception:
            print("Response Content (Not JSON):")
            print(res.text[:1000])

        if res.status_code == 200:
            print("\n✅ Test Result: SUCCESS")
        else:
            print(f"\n❌ Test Result: FAILED (Code: {res.status_code})")
            sys.exit(1)

    except requests.exceptions.ConnectionError:
        print(f"\n❌ Error: Cannot connect to {BASE_URL}. Ensure the service is running.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
