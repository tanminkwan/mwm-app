# 수동 점검 스크립트

**pytest 테스트가 아니다.** 살아있는 서버를 상대로 사람이 직접 실행하는 스크립트다.

`test_` 접두사를 떼고 이 디렉터리로 분리했다 — pytest 가 수집하면 살아있는 서버로 실제 HTTP 호출이 일어나기 때문이다.
을 참고한다. 요약하면 — 이 파일들이 `tests/` 에 `test_*.py` 이름으로 있으면 pytest 가
import 하면서 실제 HTTP 호출을 일으키고, 그중 일부는 `exit(1)` 로 **pytest 프로세스를
통째로 죽였다.**

## 실행 방법

비밀값은 코드에 두지 않는다. 환경변수로 주입한다.

```bash
export MWM_URL=http://127.0.0.1:8000
export MWM_USER=<계정>
export MWM_PASSWORD=<비밀번호>        # 또는 MWM_TOKEN 으로 토큰 직접 지정

python tests/manual/<스크립트>.py
```

## 환경변수

| 변수 | 기본값 | 용도 |
| :--- | :--- | :--- |
| `MWM_URL` | `http://127.0.0.1:8000` | 대상 서버 |
| `MWM_USER` | `admin` | 로그인 계정 |
| `MWM_PASSWORD` | (없음) | 로그인 비밀번호. **필수** |
| `MWM_TOKEN` | (없음) | 토큰 직접 지정. 있으면 로그인을 건너뛴다 |
| `MWM_TEST_RECEIVERS` | `someone@example.com` | 메일 발송 스크립트의 수신자 |
| `MWM_TARGET_HOST` | `example-host-01` | `api_mwserver.py` 대상 호스트 |
| `JEUS_DOMAIN_XML` | (없음) | `api_jeusdomain.py` 입력 XML 경로. **필수** |
| `JEUS_HOST_ID` / `JEUS_DOMAIN_ID` / `JEUS_SYSTEM_USER` | 예시값 | JEUS 등록 파라메터 |
| `WEBTOB_HTTPM` | (없음) | `api_webtobdomain.py` 입력 `http.m` 경로. **필수** |
| `WEBTOB_HOST_ID` / `WEBTOB_SYSTEM_USER` | 예시값 | WebToB 등록 파라메터 |

## 스크립트

| 파일 | 대상 API |
| :--- | :--- |
| `api_jeusdomain.py` | `POST /api/v1/config/jeusdomain` |
| `api_webtobdomain.py` | `POST /api/v1/config/httpm` |
| `api_mwserver.py` | `/api/v1/mwserver/*` 조회·등록·수정 |
| `api_email.py` | `POST /api/v1/email/send` |
| `api_email_markdown.py` | `POST /api/v1/email/send_markdown` |
| `api_markdown.py` | `POST /api/v1/markdown/to_html` |
| `_common.py` | 공용 로그인 헬퍼 |

## 규칙

- **비밀값·개인정보를 파일에 적지 않는다.** 과거 이 스크립트들에는 1년짜리 JWT 토큰과
  운영 계정 비밀번호, 개인 이메일 주소가 하드코딩되어 있었다.
- 고객사 호스트명·도메인을 쓰지 않는다. 예시값은 `example.com`, `example-host-01`.
- `exit()` 대신 `main()` 이 반환값을 주고 `sys.exit(main())` 으로 끝낸다.
