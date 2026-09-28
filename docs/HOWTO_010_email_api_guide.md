# 📧 미들웨어관리소 Email API 연동 가이드

본 문서는 미들웨어관리소 시스템의 **Email 발송 API**를 외부 어플리케이션이나 스크립트에서 연동하려는 개발자를 위한 상세 가이드입니다.

---

## 1. 사전 준비: 인증 토큰 발급

미들웨어관리소 API는 보안을 위해 모든 호출에 **인증 토큰(JWT)**을 요구합니다.

1.  **미들웨어관리소 웹 접속**: 브라우저에서 미들웨어관리소 시스템에 로그인합니다.
2.  **토큰 발급 메뉴 이동**: 상단 메뉴의 **`나의 정보` > `개인 인증 토큰 발급`**을 클릭합니다.
3.  **토큰 생성**: `신규 토큰 생성하기` 버튼을 누르면 긴 문자열(Token)이 나타납니다.
4.  **복사 및 보관**: 이 토큰은 **1년(365일)** 동안 유효하며, 보안상 한 번만 확인할 수 있으므로 안전한 곳에 저장해 두세요.

---

## 2. 공통 호출 규격

*   **Host**: `http://<서버-IP>:8000` (또는 실제 운영 도메인)
*   **Header**: 모든 요청에 반드시 아래 헤더가 포함되어야 합니다.
    *   `Content-Type: application/json`
    *   `Authorization: Bearer <나의-인증-토큰>`

---

## 3. 일반 HTML 메일 발송 API

표준 HTML 형식의 본문을 발송할 때 사용합니다.

### 엔드포인트
*   **URL**: `/api/v1/email/send`
*   **Method**: `POST`

### Request Body (JSON)
| 파라미터 | 타입 | 설명 | 예시 |
| :--- | :--- | :--- | :--- |
| `sender_name` | String | 발신자명 (이메일 닉네임) | `미들웨어관리소 알림봇` |
| `receivers` | String | 수신자명 (쉼표로 구분 가능) | `test@example.com, dev@example.com` |
| `subject` | String | 메일 제목 | `[알림] 시스템 점검 안내` |
| `content` | String | HTML 형식의 본문 내용 | `<h1>긴급</h1><p>내용...</p>` |

---

## 4. Markdown 메일 발송 API (권장)

문서 작성이 간편하며, **Mermaid 차트** 및 **S3 이미지**를 자동으로 처리해 줍니다.

### 엔드포인트
*   **URL**: `/api/v1/email/send_markdown`
*   **Method**: `POST`

### 주요 고급 기능
1.  **Mermaid 차트**: ` ```mermaid ` 블록을 사용하면 메일에 이미지로 자동 변환되어 포함됩니다.
2.  **S3 이미지 인라인**: 본문에 `/common/download/<파일명>` 형태의 링크를 사용하면, 수신자가 이미지를 따로 다운로드하지 않아도 보이도록 **내장 이미지(CID)**로 자동 변환합니다.

### Request Body (JSON)
| 파라미터 | 타입 | 설명 | 예시 |
| :--- | :--- | :--- | :--- |
| `sender_name` | String | 발신자명 | `보고서 자동발송` |
| `receivers` | String | 수신자명 | `user1@example.com` |
| `subject` | String | 메일 제목 | `[분석보고서] 자동 생성 결과` |
| `content` | String | Markdown 형식의 본문 내용 | `# 제목\n\n* 리스트\n\n![](/common/download/img.png)` |

---

## 5. 연동 예제 (Python)

```python
import requests
import json

def send_markdown_email():
    # 1. 설정 정보
    BASE_URL = "http://127.0.0.1:8000"
    MY_TOKEN = "나의_1년_인증_토큰"
    
    url = f"{BASE_URL}/api/v1/email/send_markdown"
    
    # 2. 헤더 설정 (인증 토큰 포함)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MY_TOKEN}"
    }
    
    # 3. 발송 내용 구성 (Markdown)
    markdown_text = """
    # 🚀 일일 운영 현황 보고
    
    ## 1. 지표 요약
    | 항목 | 수치 | 상태 |
    | :--- | :--- | :--- |
    | 서버 부하 | 15% | ✅ 안정 |
    
    ## 2. 인프라 구조
    ```mermaid
    graph LR;
    Client --> API_Server --> DB;
    ```
    """
    
    payload = {
        "sender_name": "미들웨어관리소 로봇",
        "receivers": "user@example.com",
        "subject": "오늘의 인프라 현황입니다",
        "content": markdown_text
    }
    
    # 4. API 호출
    response = requests.post(url, headers=headers, json=payload)
    
    # 5. 결과 확인
    if response.status_code == 200:
        print("메일 발송 성공!")
    else:
        print(f"발송 실패: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    send_markdown_email()
```

---

## 6. 오류 응답 (Troubleshooting)

*   **401 Unauthorized**: 토큰이 없거나 만료되었습니다. 헤더의 `Bearer` 형식을 확인하세요.
*   **404 Not Found**: URL 주소가 틀렸습니다. `/api/v1/` 접두사를 확인하세요.
*   **500 Internal Server Error**: SMTP 설정 오류이거나 서버측 로직 오류입니다. 관리자에게 문의하세요.
