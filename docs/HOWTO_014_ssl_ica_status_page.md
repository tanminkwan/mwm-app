# HOWTO: Monitor 메뉴 하단에 'SSL인증서 만료 현황' 페이지 신규 추가 및 ICA 현황 반영

본 문서는 Dashboard(my_index)에 있는 기존 `[SSL 인증서 만료 현황]`을 대체/확장하기 위해, `Monitor` 메뉴 하단에 별도의 **'SSL인증서 만료 현황'** 페이지를 만들고, 기존 LEAF 인증서 현황과 더불어 중간 인증서(ICA) 현황까지 함께 집계하여 보여주기 위한 개발 가이드라인입니다. 코딩을 진행하기 전 단계별 작업 지시서로 활용됩니다.

## 목차
1. [개요](#1-개요)
2. [백엔드 (SQL 로직 추가)](#2-백엔드-sql-로직-추가)
3. [컨트롤러 및 REST API 엔드포인트 추가](#3-컨트롤러-및-rest-api-엔드포인트-추가)
4. [프론트엔드 (신규 HTML 템플릿 작성)](#4-프론트엔드-신규-html-템플릿-작성)
5. [기존 Dashboard (my_index.html) 수정](#5-기존-dashboard-my_indexhtml-수정)
6. [변경 및 신규 파일 목록](#6-변경-및-신규-파일-목록)

---

## 1. 개요
* **목표 1**: `Monitor` 메뉴 내 신규 페이지(`SSL인증서 만료 현황`) 생성.
* **목표 2**: 신규 페이지에서 기존 대시보드의 테이블을 `[LEAF인증서 만료 현황]`으로 이름 변경하여 배치.
* **목표 3**: 동일한 형태의 테이블로 중간(CA) 인증서 만료일을 집계하는 `[ICA인증서 만료 현황]` 테이블 추가 구현.
* **DB 배경**: 중간(CA) 인증서 관련 컬럼은 `mw_web_domain` 및 `mw_etc_ssl_domain` 테이블에 `notafter_ca`, `subject_ca` 등의 형태로 기 존재함. (ICA의 집계 키는 `notafter_ca`를 사용)

---

## 2. 백엔드 (SQL 로직 추가)
**수정 파일: `app/sqls/monitor.py`**

기존 LEAF 인증서를 집계하는 함수(`get_cert_expiry_stat`, `get_cert_expiry_stat_jeus`)를 참고하여, ICA 전용 집계 함수를 새롭게 생성해야 합니다.

1. **`get_ica_cert_expiry_stat()` 함수 신규 작성 (webtob용)**
   - 기존 `get_cert_expiry_stat` 복사.
   - `status_case` 로직에서 `MwWebDomain.notafter`를 `MwWebDomain.notafter_ca`로 변경합니다.
   
2. **`get_ica_cert_expiry_stat_jeus()` 함수 신규 작성 (jeus용)**
   - 기존 `get_cert_expiry_stat_jeus` 복사.
   - `status_case` 로직에서 `MwEtcSslDomain.notafter`를 `MwEtcSslDomain.notafter_ca`로 변경합니다.

*(참고: ICA 만료일 정보가 없는 경우에도 LEAF의 방식처럼 `미확인`으로 정상 집계되도록 처리해야 합니다.)*

---

## 3. 컨트롤러 및 REST API 엔드포인트 추가

### 3.1. REST API 엔드포인트 구현 (신규)
**신규 파일: `app/api/monitor_api.py`**

외부 연동 확장성 및 API Key(Bearer token 등) 인증을 고려하여, 신규 데이터는 REST API 규격(`flask_appbuilder.api.BaseApi`)으로 구현합니다.

```python
from flask_appbuilder.api import BaseApi, expose, protect
from app import appbuilder
# get_cert_expiry_stat, get_cert_expiry_stat_jeus, get_ica_cert_expiry_stat 등 관련 모듈 임포트

class MonitorRestApi(BaseApi):
    resource_name = 'monitor'
    
    # ------------------ 기존 LEAF 인증서용 (REST 마이그레이션) ------------------
    @expose('/cert_expiry_stat', methods=['GET'])
    @protect()
    def get_cert_expiry_stat(self):
        result = get_cert_expiry_stat()
        return self.response(200, cert_expiry_stat=result)

    @expose('/cert_expiry_stat_jeus', methods=['GET'])
    @protect()
    def get_cert_expiry_stat_jeus(self):
        result = get_cert_expiry_stat_jeus()
        return self.response(200, cert_expiry_stat_jeus=result)

    # ------------------ 신규 ICA 인증서용 ------------------
    @expose('/ica_cert_expiry_stat', methods=['GET'])
    @protect() # API Key 또는 JWT/Session 방식 모두 지원 가능
    def get_ica_cert_expiry_stat(self):
        result = get_ica_cert_expiry_stat()
        return self.response(200, ica_cert_expiry_stat=result)

    @expose('/ica_cert_expiry_stat_jeus', methods=['GET'])
    @protect()
    def get_ica_cert_expiry_stat_jeus(self):
        result = get_ica_cert_expiry_stat_jeus()
        return self.response(200, ica_cert_expiry_stat_jeus=result)

appbuilder.add_api(MonitorRestApi)
```
프론트엔드에서의 AJAX 호출 경로는 `/api/v1/monitor/cert_expiry_stat` 및 `/api/v1/monitor/ica_cert_expiry_stat` 등과 같이 구성됩니다. 기존 `app/views/monitor.py`에 있던 `@expose('/cert_expiry_stat')`는 제거하거나 Deprecated 처리합니다.

### 3.2. 신규 화면(View) 및 메뉴 등록
**수정 파일: `app/views/monitor.py`**

템플릿 화면을 렌더링하기 위해 뷰 클래스를 만들고, 하단에서 메뉴에 등록합니다.

```python
from flask_appbuilder import BaseView, expose
from app import appbuilder

class SslCertStatusView(BaseView):
    default_view = 'index'

    @expose('/')
    def index(self):
        # ssl_cert_status.html 템플릿 렌더링
        return self.render_template('ssl_cert_status.html')

# 파일 최하단 Flask-AppBuilder에 뷰 및 메뉴 등록 부분
appbuilder.add_view(
    SslCertStatusView,
    "SSL인증서 만료 현황",
    category="Monitor",
    category_icon="fa-desktop" # 기존 Monitor 아이콘과 동일하게 맞춤
)
```

---

## 4. 프론트엔드 (신규 HTML 템플릿 작성)
**신규 파일: `app/templates/ssl_cert_status.html`**

기존 `my_index.html`의 스타일과 스크립트를 베이스로 가져오되, 대시보드의 다른 요소들은 제외하고 인증서 만료 현황 카드만 배치합니다.

### 4.1. 화면 구조 (HTML)
화면을 두 개의 카드로 구성합니다.

1. **Card 1: `[LEAF인증서 만료 현황]`**
   - 1) webtob 집계 (`<table id="certStat">`)
   - 2) jeus https 집계 (`<table id="certStatJeus">`)
   
2. **Card 2: `[ICA인증서 만료 현황]`**
   - 1) webtob 집계 (`<table id="icaCertStat">`)
   - 2) jeus https 집계 (`<table id="icaCertStatJeus">`)

### 4.2. Javascript 구성 (AJAX 및 렌더링)
- 기존 `renderExpiryTable` 및 `gotoSSLList` 함수를 복사해 옵니다.
- 총 4개의 AJAX 호출을 구현합니다.
  1. `/api/v1/monitor/cert_expiry_stat` -> `certStat` 렌더링 (기존 LEAF용 REST API)
  2. `/api/v1/monitor/cert_expiry_stat_jeus` -> `certStatJeus` 렌더링 (기존 LEAF용 REST API)
  3. `/api/v1/monitor/ica_cert_expiry_stat` -> `icaCertStat` 렌더링 (신규 ICA용 REST API)
  4. `/api/v1/monitor/ica_cert_expiry_stat_jeus` -> `icaCertStatJeus` 렌더링 (신규 ICA용 REST API)
- *주의*: 상세 화면 이동(`gotoSSLList`) 시, ICA의 경우 필터링하는 파라미터가 `notafter`가 아닌 `notafter_ca`가 되어야 하므로, 클릭 이벤트를 분기하거나 `gotoSSLList` 함수에 `is_ica` 인자를 추가하여 파라미터 컬럼명 분기(`col_name`)를 수정해야 합니다.

---

## 5. 기존 Dashboard (my_index.html) 수정
**수정 파일: `app/templates/my_index.html`**

- **링크 및 안내 문구 추가**: 대시보드의 기존 `[SSL 인증서 만료 현황]` 카드 상단이나 하단에 신규로 생성한 'SSL인증서 만료 현황' 전체 페이지로 이동할 수 있는 링크(버튼 등)와 안내 문구를 추가합니다.
- **JEUS 테이블 제거**: 대시보드 화면 간소화를 위해 기존에 노출되던 "2) JEUS HTTPS 집계" 테이블 및 관련 AJAX 호출 코드를 대시보드에서 제거합니다. (해당 데이터는 신규 화면에서만 조회 가능하게 됩니다.)
- **AJAX 호출 URL 변경**: 기존에 호출하던 `/monitor/cert_expiry_stat` (webtob) 요청을 새로운 REST API인 `/api/v1/monitor/cert_expiry_stat` 로 수정합니다.

---

## 6. 변경 및 신규 파일 목록

- **`app/sqls/monitor.py` (수정)**: ICA 인증서 집계용 SQL 함수 2개 추가 (`get_ica_cert_expiry_stat`, `get_ica_cert_expiry_stat_jeus`)
- **`app/api/monitor_api.py` (신규)**: `flask_appbuilder.api.BaseApi` 기반의 모니터링 전용 REST API 작성 (신규 ICA API 및 기존 LEAF API 마이그레이션)
- **`app/views/monitor.py` (수정)**: 신규 화면 렌더링용 `SslCertStatusView(BaseView)` 정의 및 메뉴 링크 등록, 기존 non-REST API(`cert_expiry_stat` 등) 제거/정리
- **`app/templates/ssl_cert_status.html` (신규)**: 'SSL인증서 만료 현황' 화면 UI (LEAF 및 ICA 카드 2개 포함, REST API 호출)
- **`app/templates/my_index.html` (수정)**: 기존 대시보드 내 JEUS 테이블 제거, 신규 화면 링크 추가, LEAF 인증서 조회 AJAX URL을 REST API로 변경
