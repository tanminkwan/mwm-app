import os

from _common import login

import requests
import json
import sys

# 미들웨어관리소 API 서버 주소 (Container 외부에서 실행 시 적절한 호스트명/포트 수정 필요)
BASE_URL = os.getenv("MWM_URL", "http://127.0.0.1:8000")

def main():
    """
    /api/v1/email/send_markdown API를 호출하여
    Mermaid, Table 등이 포함된 Markdown 본문을 발송하는 수동 테스트 스크립트입니다.
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
현재 모든 엔진 및 데이터베이스 상태는 안정적이나, **Redis 캐시**의 메모리 사용량에 주의가 필요합니다.

| 분류 | 상태 | 상세 내용 |
| :--- | :---: | :--- |
| **API Server** | ✅ 정상 | 평균 응답속도 45ms 유지 |
| **Database**   | ✅ 정상 | 액티브 세션 25개 미만 |
| **Redis**      | ⚠️ 주의 | 메모리 사용량 82% (증설 검토) |

## 3. 서비스 구성도 (Mermaid)
```mermaid
graph LR;
    Client((User)) --> WAF[Web Firewall];
    WAF --> LB[Load Balancer];
    LB --> App1[WAS Node 1];
    LB --> App2[WAS Node 2];
    App1 & App2 --> DB[(PostgreSQL)];
    App1 & App2 --> Redis[(Redis Cluster)];
```

## 4. 권장 조치 사항
*   **인프라**: Redis 메모리 2GB -> 4GB 증설 권고
*   **배포**: 2026/04/10 정기 점검 시 패치 적용 예정
*   **모니터링**: [통합 관제 시스템](https://monitor.example.com) 참조

---
*본 메일은 시스템 자동 발송 메일이므로, 회신을 받지 않습니다.*
"""

    payload = {
        "sender_name": "미들웨어관리소 테스트 (Markdown)",
        "receivers": os.getenv("MWM_TEST_RECEIVERS", "someone@example.com"),
        "subject": "[테스트] 시스템 점검 결과 보고 (Markdown/Mermaid)",
        "content": markdown_content
    }

    print(f"\n🚀 Sending Markdown email to {payload['receivers']}...")
    print(f"URL: {BASE_URL}/api/v1/email/send_markdown")

    try:
        # FAB API는 기본적으로 /api/v1 접두사를 사용합니다.
        res = requests.post(
            f"{BASE_URL}/api/v1/email/send_markdown",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"Status Code: {res.status_code}")
        
        try:
            print("Response Response:")
            print(json.dumps(res.json(), indent=2, ensure_ascii=False))
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
