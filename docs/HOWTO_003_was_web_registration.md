# WAS 및 Web 서버 등록 매커니즘 가이드 (HOWTO_003)

이 문서는 미들웨어관리소(MWM) 시스템에서 WAS(JEUS) 및 Web(WebToB) 서버가 등록되는 방식과 양쪽의 연결(Relationship)이 어떻게 형성되는지 설명합니다.

---

## 1. 등록 매커니즘 개요

WAS와 Web 서버 정보는 주로 **에이전트(Agent)**가 수집한 설정 파일(`domain.xml`, `http.m` 등)을 분석하여 자동으로 등록됩니다.

### 1-1. 데이터 수집 및 전송 (Agent)
1.  **명령 하달**: 사용자가 UI(Command Master 등)를 통해 에이전트에게 데이터 수집 명령(예: `get_http_m`)을 내립니다.
2.  **파일 수집**: 에이전트는 해당 서버의 특정 경로에서 설정 데이터를 읽어옵니다.
3.  **API 호출**: 에이전트는 수집된 텍스트 데이터를 미들웨어관리소 서버의 API(`MWConfigurationApi`)로 전송합니다.
    -   `POST /api/v1/config/httpm`: WebToB 설정 데이터 전송
    -   `POST /api/v1/config/jeusdomain`: JEUS 설정 데이터 전송

### 1-2. 데이터 분석 및 저장 (Server-side DML)
1.  **Autorun 로직**: API를 통해 들어온 데이터는 `AutorunResult` 기능을 통해 분석 프로세스로 넘겨집니다.
2.  **Parsing**: 수집된 텍스트 데이터를 딕셔너리 형태의 구조화된 데이터로 변환합니다.
3.  **Upsert**: 변환된 데이터를 바탕으로 `MwWas`, `MwWeb`, `MwWebServer` 등의 테이블에 정보를 저장(Update or Insert)합니다.

---

## 2. 관계 형성(Relationship Formation) 로직

미들웨어관리소는 WAS와 Web의 관계를 **두 가지 레벨**에서 관리합니다.

### 2-1. 부모 WAS - 내장 Web 논리적 연결 (`mw_was_web`)
이 연결은 "어떤 Web 서버가 어떤 WAS에 속해 있는가"를 정의하며, 주로 JEUS 내장 WebToB 구조에서 사용됩니다.

-   **매칭 키**: Web 서버의 `Host ID`와 `Web Home`(설치 경로)을 확인합니다.
-   **동작 시점**: Web 등록 또는 텍스트 기반 재등록 시 실시간으로 수행됩니다.
-   **데이터 보관**: `mw_was_web` (Association Table)

### 2-2. WAS 커넥터 - Web 서버 물리적 연결 (`mw_webtobconn_webserver`)
WAS 프로세스(JEUS MS)와 Web 프로세스(WebToB SVR) 간의 실제 소켓 통신 경로를 정의합니다.

-   **매칭 키**: 커넥터 설정과 서버 설정의 다음 항목들을 비교합니다.
    -   **Domain Socket**: 동일 호스트 내에서 `web_home` 경로가 일치하는지 확인
    -   **TCP Socket**: `jsv_port` 번호가 일치하는지 확인
    -   **SVR 매칭**: `svr_id`와 `jsv_id`가 일치하는지 확인
-   **동작 시점**:
    -   **배치 작업**: `Batch` 메뉴의 `createWebtobConn` 기능을 통해 일괄 갱신
    -   **실시간**: Web 등록 또는 텍스트 기반 재등록 시 해당 Web과 관련된 모든 커넥터 정보를 즉시 갱신
-   **데이터 보관**: `mw_webtobconn_webserver` (Association Table)

---

## 3. 사용자가 수행해야 할 작업

자동 등록 및 관계 형성이 원활하게 이루어지기 위해 사용자는 다음 단계를 수행해야 합니다.

### 단계 1: 서버 및 호스트 등록
-   **메뉴**: `서버 관리` -> `서버`
-   **작업**: 대상 서버의 `Host ID`를 등록합니다. (에이전트로부터 올라오는 `host_id`와 반드시 일치해야 함)

### 단계 2: 에이전트 설치 및 승인
-   **메뉴**: `관리` -> `에이전트 목록`
-   **작업**: 설치된 에이전트를 `승인(Approved)` 상태로 변경합니다.

### 단계 3: 데이터 수집 명령 실행
-   **방법 A (신규 등록)**: `명령 관리` -> `Command Master`에서 `수집 관련 명령`을 실행합니다.
-   **방법 B (수동 재등록)**: WAS 또는 Web 상세 화면 상단의 `텍스트 기반 재등록` 버튼을 클릭하여 설정 텍스트를 직접 입력하거나 수정하여 반영할 수 있습니다.

---

## 4. 관계 시각화 (Diagram)
등록 및 관계 형성이 완료된 데이터는 `구성도(Diagram)` 메뉴를 통해 시각적으로 확인할 수 있습니다. 
만약 관계선이 보이지 않는다면 다음을 확인하십시오.
1.  WAS와 Web 양쪽 호스트의 `Host ID` 일치 여부
2.  사용자가 `createWebtobConn` 배치를 실행했거나, Web을 재등록했는지 여부
3.  커넥터 설정(`http.m`)의 `svr_id` 및 `port` 정보의 정확성
