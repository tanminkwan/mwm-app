# HOWTO_020: SBOM 과 third-party 라이선스 목록

> 작성 2026-09-29 (VER 20260929.003). 조직의 보안·법무 심사에 내는 자료를 만들고 다시 만드는 방법, 그리고 첫 점검 결과.

---

## 1. 무엇이 어디 있나

| 파일 | 내용 | 만드는 법 |
| :--- | :--- | :--- |
| `sbom/mwm-app.cdx.json` | 본 앱 SBOM (CycloneDX 1.6) — 운영 이미지의 Python 패키지 + `app/static` 의 vendored JS/CSS | `sbom/generate.sh` |
| `sbom/mwm-idp.cdx.json` | IdP SBOM (CycloneDX 1.6) — IdP 이미지의 Python 패키지 | `sbom/generate.sh` |
| `THIRD_PARTY_LICENSES.md` | 위 전부의 라이선스 표 + **검토 필요** 항목 | `sbom/generate.sh` |
| `sbom/static-assets.json` | `app/static` 에 넣어 둔 외부 JS/CSS 목록 (이름·버전·라이선스·파일) | **손으로** 관리 |
| `sbom/build.py` | 원자료 → SBOM·라이선스 문서. `--check` 는 목록 검사만 | — |

프로젝트 자체 라이선스는 MIT(`LICENSE`)다.

### 왜 두 갈래인가

- **Python 패키지**는 운영 이미지에 실제 설치된 것을 그대로 뽑는다(`cyclonedx-py environment`). 간접 의존성, pip·setuptools 까지 들어간다
- **`app/static` 의 JS/CSS**는 npm 을 거치지 않고 파일째 저장소에 들어 있다. pip·Dependabot·pip-audit·CodeQL 의존성 분석 **어느 것도 모른다**.
  그래서 목록을 손으로 적고, 버전을 확인하지 못한 것은 추측하지 않고 `unknown` 으로 둔다
- 여러 라이브러리가 **안에 묶어 넣은** 라이브러리(DOMPurify)는 따로 교체할 수 없지만, 스캐너가 보도록 별도 컴포넌트로 적었다

OS 패키지(Debian `python:3.12.14-slim-bookworm` 베이스)는 이 SBOM 에 없다. 필요하면 이미지 스캐너(`trivy image mwm-app`)로 따로 본다.

---

## 2. 다시 만들기

`requirements*.txt`·`idp/requirements.txt` 가 바뀌거나 `app/static` 을 바꾸면 다시 만들어 결과를 함께 커밋한다.

```bash
docker build -t mwm-base -f Dockerfile.base . && docker build -t mwm-app -f Dockerfile.app .
docker build -t mwm-idp  -f idp/Dockerfile.idp idp
sbom/generate.sh        # 인터넷 필요 (개발 PC). 도구는 컨테이너 안 별도 venv 에 설치 — 이미지 패키지 목록에 섞이지 않는다
```

끝에 **검토 필요** 목록을 출력한다. 새 항목이 생겼으면 §4 에 판단을 적는다.

`app/static` 에 파일을 추가·교체했다면 먼저 `sbom/static-assets.json` 을 고친다.
CI `lint` job 이 `python3 sbom/build.py --check` 로 **목록에 없는 `app/static` 파일이 있으면 실패**시킨다.

검증 (CycloneDX 공식 도구):

```bash
docker run --rm -v "$PWD/sbom:/s:ro" cyclonedx/cyclonedx-cli validate \
    --input-file /s/mwm-app.cdx.json --input-version v1_6 --fail-on-errors
```

---

## 3. 심사에 낼 때

- SBOM 두 파일과 `THIRD_PARTY_LICENSES.md` 를 낸다. 조직이 SPDX 를 요구하면 `cyclonedx-cli convert --output-format spdxjson` 으로 바꾼다
- 조직 스캐너(Dependency-Track 등)에 SBOM 을 넣으면 새 CVE 가 나올 때 영향 여부를 바로 본다
- ⚠ **스캐너 하나만 믿지 않는다.** 이번 점검에서 Trivy 는 SBOM 의 Moment 2.29.1·SheetJS 0.15.6 취약점을 **잡지 못했고**,
  retire.js 는 SheetJS·SimpleMDE·Summernote 를 알아보지 못했다 (§5). 결과를 합쳐서 본다

---

## 4. 라이선스 검토 (2026-09-29)

| 구성요소 | 라이선스 | 판단 |
| :--- | :--- | :--- |
| ~~Guriddo jqGrid JS 4.7.1~~ → **free jqGrid 4.15.5** (`app/static/js/jquery.jqgrid*`) | MIT OR GPL-2.0 → MIT 를 고른다 | **교체 완료 (2026-09-30).** Guriddo 는 상용 라이선스 계열이라 뺐다. 쓰는 화면은 2개 — Monitor > Table 정보 조회(`/monitor/gridView`)·System > Table 상세 조회(`/monitor/viewTableSpecs`). ⚠ free jqGrid 는 id 없는 로컬 데이터의 행 id 를 `1..n` 이 아니라 `jqg1..` 로 붙인다 — 상세 조회의 행 색칠을 `getDataIDs()` 로 고쳤다. 헤드리스 Chrome 으로 두 화면(조회·필터 툴바·행 색·더블클릭 하위 그리드) 확인, 콘솔 오류 0. OSV 알려진 취약점 없음 |
| `psycopg2-binary` 2.9.13 (본 앱·IdP) | LGPL | 수정 없이 import 해서 쓴다 — 보통 문제없다. 조직 규정 확인 |
| `cssutils` 2.15.0 · `encutils` 1.0.0 (`premailer` 가 씀) | LGPL-3.0-or-later | 위와 같다 |
| ~~JSZip 3.5.0~~ | MIT OR GPL-3.0 | 삭제했다 (쓰지 않음, §5) |
| DOMPurify (내장) | MPL-2.0 OR Apache-2.0 | Apache-2.0 을 고른다 |
| `certifi` | MPL-2.0 | 파일 단위 약한 copyleft, 수정 없이 사용 — 보통 문제없다 |

**`html2text`(GPL-3.0-or-later) 는 뺐다.** `requirements.txt` 에만 있고 코드·설치된 다른 패키지 어디서도 import 하지 않는다
(TASK 2-7 에서 "메일 경로에서 간접 사용 가능성"으로 남겨 뒀던 것 — 이미지 site-packages 전체와 `Requires-Dist` 로 확인). 테스트 283 통과.

---

## 5. vendored JS 취약점 (2026-09-29)

pip-audit·Dependabot·CodeQL 이 보지 못하던 부분이다. **수정은 별도 task** 로 한다 (라이브러리를 올리면 화면 확인이 필요하다).

| 구성요소 | 쓰는 곳 | 취약점 | 고친 버전 | 찾은 도구 |
| :--- | :--- | :--- | :--- | :--- |
| ~~DOMPurify 2.3.3~~ → **3.4.16 (2026-09-30 완료)** (TOAST UI Editor 3.2.2 내장) | 마크다운 편집·보기 (`*_md2.html` — 지식관리 MD 문서) | **high 포함 다수** — CVE-2024-45801·47875·48910, CVE-2025-26791 등 (새니타이저 우회 → XSS) | TOAST UI Editor 는 3.2.2 가 마지막이라 올릴 수 없다 → 번들 안의 DOMPurify 모듈(webpack 368)만 바꿨다. 다시 만들 때 `vendor/toastui-editor/patch_dompurify.sh` (Docker node, 인터넷 필요, 멱등). 확인: 실제 문서 3개 렌더링이 교체 전후 같음(속성 순서 제외), XSS 문자열 6종 결과 동일, retire.js 검출 0 | retire.js, Trivy |
| ~~SheetJS 0.15.6~~ → **0.20.3 (2026-09-30 완료)** (`xlsx.full.min.js`) | 엑셀 내보내기만 — Monitor > Table 정보 조회의 "EXCEL 내보내기" (`list_jqgrid.html`). 읽기는 쓰지 않는다 | CVE-2023-30533 (조작된 파일로 프로토타입 오염, high), CVE-2024-22363 (ReDoS) | 0.20.2+ (npm 이 아니라 cdn.sheetjs.com 배포) — 0.20.3 으로 교체. 헤드리스 Chrome 으로 내보낸 파일(헤더·데이터 행) 확인 | **수동 확인** — 두 스캐너 모두 놓침 |
| ~~Moment.js 2.29.1~~ → **2.31.0 (2026-09-30 완료)** | 엑셀 내보내기 파일 이름의 날짜 (`list_jqgrid.html`). `listWithJson.html` 도 불러오지만 쓰는 함수(`get3MinBefore`)를 부르는 곳이 없다 | CVE-2022-31129 (RFC2822 파싱 ReDoS, high), CVE-2022-24785 (Node 전용, 브라우저 무관) | 2.29.4+ — npm 최신 2.31.0 으로 교체. 헤드리스 Chrome 으로 파일 이름·목록 화면 확인 | retire.js |
| ~~JSZip 3.5.0~~ → **삭제 (2026-09-30)** | 쓰는 곳 없음 — 어떤 템플릿도 불러오지 않는다 (git 히스토리 전체에서도). 엑셀 내보내기는 SheetJS 가 자체 zip 으로 한다 | CVE-2021-23413 (프로토타입 오염), CVE-2022-48285 (경로 조작) — medium | 파일 삭제 | retire.js, Trivy |
| ~~SimpleMDE 1.11.2~~ → **삭제 (2026-09-30)** | 쓰는 곳 없음 — 불러오던 `add_md.html`·`edit_md.html`·`show_md.html` 을 어떤 뷰도 쓰지 않는다 (지금은 TOAST UI 의 `*_md2.html`). 템플릿과 함께 뺐다 | CVE-2018-19057 (XSS) — 관리 중단, 수정판 없음 | 파일 삭제 | Trivy |
| ~~Summernote 0.8.20~~ → **0.9.1 (2026-09-30 완료)** | HTML 편집 (`*_summer.html` — 지식관리 HTML 문서) | CVE-2024-37629 (코드 보기 XSS) — medium. **더 큰 문제는 앱 쪽이었다**: 저장된 HTML 을 보기 화면(`show_raw.html` 의 `\|safe`)·목록 HTML 보기(`listWithJson.html` 의 jQuery `.html()`)·편집 화면(편집 영역에 넣는 순간)이 거르지 않고 넣어 저장형 XSS 가 됐다 | 0.9.1 로 교체(코드 보기 필터 기본 켜짐) + 세 곳 모두 단독 DOMPurify 3.4.16 으로 거른 뒤 넣는다 (`target` 속성만 추가 허용). 헤드리스 Chrome: 교체 전 XSS 문자열 실행 2~3회 → 교체 후 0, 제목·표·색·링크 유지 | Trivy (앱 쪽 XSS 는 CodeQL 도 못 봄 — 수동 확인) |
| ~~mermaid 10.9.5 (DOMPurify 3.2.4 내장)~~ → **mermaid 11.17.2 (DOMPurify 3.4.12) (2026-09-30 완료)** | 마크다운 문서의 다이어그램 (`*_md2.html`, 플러그인 `toastui-editor-plugin-mermaid.js`) | mermaid 10.9.5: CSS 주입·프로토타입 오염·DoS 7건. 내장 DOMPurify 3.2.4: low·medium 19건 | 11.17.2 는 mermaid 알려진 취약점 0, 내장 DOMPurify 3.4.12 는 IN_PLACE 모드 1건(mermaid 는 쓰지 않음). 10.9.8 은 내장 DOMPurify 가 10건 남아, 12.0.0 은 5.5MB 라 고르지 않았다. 문서 다이어그램 노드 수 동일·스크린샷 확인 | retire.js |

버전을 모르는 구성요소(diff2html, jsdiff, Prism, jquery.flowchart, jquery.json-viewer, mermaid 본체)는 스캐너가 판단할 수 없다.
교체할 때 버전이 박힌 파일로 바꾼다.

도구 실행:

```bash
docker run --rm -v "$PWD/app/static:/s:ro" node:22-slim npx -y retire@5 --path /s          # 파일 내용으로 버전·취약점 추정
docker run --rm -v "$PWD/sbom:/s:ro" aquasec/trivy sbom /s/mwm-app.cdx.json                  # SBOM 기준
```

---

## 6. 앱 코드 취약점 — 스캐너가 못 본 것 (2026-09-30)

CodeQL 은 소스 정적 분석(SAST)이라 아래를 잡지 못했다. 회사 점검의 동적 점검(DAST)에 걸릴 종류다.

| 문제 | 영향 | 조치 |
| :--- | :--- | :--- |
| **Flask-APScheduler REST API 가 켜져 있었다** (`SCHEDULER_API_ENABLED = True`) — `/scheduler/jobs` 등 | **인증 없는 원격 코드 실행.** 로그인 없이 작업을 조회·추가·즉시 실행할 수 있고, 추가할 때 실행할 함수를 `module:function` 문자열로 받는다 (ZAP 점검 중 발견, 2026-09-30) | 항상 끈다. "정기 JOB 목록" 화면은 로그인이 필요한 읽기 전용 `/monitor/jobs.json` 으로 옮기고, 화면 권한이 있는 역할에 새 권한을 주는 `docs/sql/20260930_grant_job_list_json.sql` (DB 스크립트 12). 테스트 `tests/test_char_scheduler_api.py`. 로컬 확인 때 이미 들어온 작업은 없었다(4개 모두 앱 함수) |
| 저장된 HTML 을 거르지 않고 출력 — `show_raw.html` 의 `\|safe`, `listWithJson.html` 의 jQuery `.html()`, Summernote 편집 영역 | 저장형 XSS: 문서를 저장할 수 있는 사람이 읽는 모든 사람의 브라우저에서 스크립트 실행 | 세 곳 모두 DOMPurify 로 거른 뒤 넣는다 (§5 Summernote 행) |
| `/json/htmlviewer/<table>/<column>/<title>/<id>`, `/api/v1/model/column_all\|column_distinct/<table>.<column>` 이 테이블·컬럼 이름을 주소에서 그대로 받음 | 로그인한 누구나 아무 테이블의 아무 컬럼을 읽는다 (예: `ab_user.password` 해시, `ag_agent.refresh_token`). `column_all` 의 `condition` 으로 다른 컬럼 값을 한 글자씩 맞혀 볼 수도 있었다. htmlviewer 는 문서 목록의 그룹 필터도 건너뛰었다 | 화면이 쓰는 조합만 허용 (`HTML_VIEWER_FIELDS`·`COLUMN_LOOKUPS`, 그 밖은 404). `condition` 은 조회하는 컬럼 자신에만 (그 밖은 400). htmlviewer 는 목록과 같은 그룹 기준(`visible_to_current_user`). 테스트 `tests/test_api_data_exposure.py` |
| mermaid 를 `securityLevel: 'loose'` 로 초기화 + 오류 문구를 `innerHTML` 로 넣음 (`toastui-editor-plugin-mermaid.js`) | 문서의 다이어그램으로 `click ... "javascript:..."` 링크를 만들고, 문법 오류 문구에 넣은 HTML 이 실행됐다 (헤드리스 Chrome 에서 재현) | `'strict'`(mermaid 기본값)로 바꾸고 오류는 `textContent` 로 넣는다 (2026-09-30). 라벨의 이벤트 속성·javascript: 링크·오류 경로 실행 모두 0 |
| 지식 문서를 id 로 여는 경로 — `/ut/htmlcontent/<id>`·`/ut/mdcontent/<id>`·`/ut/mdcontent.download/<content_id>`·두 `send_email` | 목록의 그룹 필터를 건너뛰어, id 를 바꾸면 다른 그룹 문서를 보고·내려받고·메일로 보낼 수 있었다 | 다섯 곳 모두 `visible_to_current_user` 로 거르고 안 보이면 404 (2026-09-30). 테스트 `tests/test_api_doc_group_visibility.py`. 남은 것: 첨부 `/common/download/<파일명>` 은 그룹을 보지 않는다 — 파일명에 UUID 가 붙어 추측은 어렵다 |
| 보안 헤더 없음 (nginx 도 안 붙임) · 세션 쿠키 SameSite 없음 · IdP 장애 시 `/idp/login` 500 · 콜백이 예외 문구를 화면에 냄 (ZAP baseline) | clickjacking·MIME 추측·정보 노출 | 앱이 `X-Frame-Options`·`X-Content-Type-Options`·`Referrer-Policy`·`Permissions-Policy`·CSP(`frame-ancestors`·`object-src`·`base-uri` 만) 를 붙인다. 쿠키 `SameSite=Lax`·`HttpOnly`, `Secure` 는 `MWM_SESSION_COOKIE_SECURE=true` 로 켠다(모든 접속이 https 일 때). IdP 오류는 로그에만 남기고 로그인 화면으로 (2026-09-30). 테스트 `tests/test_char_security_headers.py` |
| **남은 것** — CSP `script-src` 없음 · Flask-AppBuilder 내장 Bootstrap 3.4.1 (CVE-2024-6485·CVE-2025-1647) | 인라인 스크립트가 많아 `script-src` 를 넣으면 화면이 깨진다. Bootstrap 은 FAB 가 들고 온다 | CSP 는 Report-Only 로 먼저 모아 보는 별도 task. Bootstrap 은 FAB 가 올리기 전까지 수용 — 두 CVE 는 `data-loading-text`·툴팁/팝오버 sanitize 우회로, 앱은 공격자 입력을 그 속성에 넣지 않는다 |
| ZAP 로그인 full scan (1216 URL, FAIL 0, active 에서 SQLi·XSS 없음) 뒤 정리 — Swagger UI 번들의 DOMPurify 3.0.6 (High) · DB 재기동 뒤 끊긴 연결로 500 · `showWithJson.html` 의 `eval` | 오래된 라이브러리 노출 · 가용성 · 화면 글자를 코드로 실행하는 구조 | Swagger UI 기본 끔 — 필요할 때 `MWM_SWAGGER_UI=true` 로 재기동 (켜도 Admin 만). `pool_pre_ping`. 위젯이 dict 를 JSON 으로 그리고 화면은 `JSON.parse` (2026-09-30). 테스트 `tests/test_char_hardening.py` |
| CSRF 전역 보호 없음 — 토큰 없는 FAB 삭제 POST 가 실제로 지웠다 (DB 사본에서 확인) | 로그인한 사용자를 속여 데이터를 바꾸거나 지운다 (`SameSite=Lax` 로 교차 사이트는 이미 완화) | `CSRFProtect` 를 AppBuilder 보다 먼저 켠다 (FAB 가 API 를 뺀다). API 중 **로그인 쿠키로 인증된 조회 아닌 요청**은 앱이 따로 확인 — JWT(Agent)·쿠키 없는 `/api/v1/security/login` 은 그대로. 공통 레이아웃 `mwm_base.html` 이 토큰 meta 와 `mwm_csrf.js`(같은 출처 jQuery AJAX·fetch 에 `X-CSRFToken`)를 넣는다. 토큰은 세션 동안 유효(`WTF_CSRF_TIME_LIMIT=None`). https 에서는 Referer 도 확인한다 (2026-09-30). 테스트 `tests/test_char_csrf.py`, 헤드리스 Chrome 으로 nginx(https) 경유 추가·삭제·AJAX·fetch 확인 |
| 수용 · 오탐 | 사설 IP 노출(서버 인벤토리 화면이 원래 보여 주는 값) · "Source Code Disclosure - SQL"(WAS 설정 안의 `select 1 from dual`) · 타임스탬프 | 조치 없음 |

---

## 7. 웹 점검(ZAP) 다시 돌리기

CodeQL 은 소스만 본다. 사이트를 띄워 요청을 보내는 점검(DAST)은 ZAP 으로 한다. 이미지는 `ghcr.io/zaproxy/zaproxy:stable` (2.17.0, CI 는 digest 고정).

### 7.1 baseline — CI 관문 (자동)

`.github/scripts/zap_baseline.sh` 가 배포 이미지를 띄우고 로그인 없이 보이는 화면을 **수동 점검**한다 (헤더·쿠키·정보 노출 등).
받아들인 경고는 `.zap/rules.tsv` 에 **이유와 함께** 적는다. 그 밖의 경고가 하나라도 나오면 CI 가 실패한다.
로컬에서도 같다 (compose 네트워크, DB 는 사본을 쓴다):

```bash
NET=mw_app_default REDIS_URL=redis://mwm-redis:6379/5 \
  MWM_DATABASE_URI=postgresql://<계정>:<비번>@mwm-db:5432/<사본 DB> .github/scripts/zap_baseline.sh
```

### 7.2 로그인 상태 full scan — 로컬에서 수동 (공격 요청을 보낸다)

**데이터를 바꾼다** (FAB 추가·삭제 폼에 값을 넣어 보낸다). 개발 DB 를 쓰지 말고 사본에 붙인 전용 컨테이너로 한다. 2026-09-30 에 한 방식:

1. DB 사본 — `createdb -O <앱 계정> mw_zap && pg_dump mw | psql mw_zap`
2. 전용 앱 컨테이너 `mwm-app-zap` — compose 의 앱 환경변수를 쓰되 `MWM_DATABASE_URI` 는 `mw_zap`, SMTP·MQTT·알림·S3 는 `*.invalid` 주소로 막는다.
   **호스트 포트를 열지 않는다** (ZAP 은 같은 docker 네트워크에서 붙는다)
3. 전용 관리자 — `docker exec mwm-app-zap flask fab create-admin --username zap_tmp ...` 로 만들고, 로그인해 `session` 쿠키를 얻는다
4. 점검 — 쿠키를 모든 요청에 붙이고 로그아웃은 뺀다:
   ```bash
   docker run --rm --network mw_app_default -v <작업 디렉터리>:/zap/wrk:rw ghcr.io/zaproxy/zaproxy:stable \
     zap-full-scan.py -t http://mwm-app-zap:8000/ -m 10 -J full_auth.json -r full_auth.html -I -z "\
       -config replacer.full_list(0).description=auth -config replacer.full_list(0).enabled=true \
       -config replacer.full_list(0).matchtype=REQ_HEADER -config replacer.full_list(0).matchstr=Cookie \
       -config replacer.full_list(0).regex=false -config replacer.full_list(0).replacement=session=<쿠키> \
       -config globalexcludeurl.url_list.url(0).regex=.*/logout.* -config globalexcludeurl.url_list.url(0).enabled=true \
       -config scanner.maxScanDurationInMins=40"
   ```
   1216 URL 에 약 50분 (spider 10분 + active 40분).
5. 끝나면 컨테이너·`mw_zap` 을 지운다

2026-09-30 결과와 조치는 §6 에 있다 (FAIL 0, active 에서 SQL 주입·XSS 없음).
