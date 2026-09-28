# SPEC_007: Generic Table Viewer 리팩토링 및 UI 개선 (gridView)

## 1. 개요
- 기존 `/monitor/test`라는 불분명한 뷰 이름을 기능을 직관적으로 나타내는 `/monitor/gridView`로 리팩토링한다.
- 조회 화면의 UI를 현대적인 디자인(Glassmorphism, Grid Layout)으로 개편하여 사용자 경험을 향상시킨다.
- 특히 동적으로 생성되는 조회 조건 영역의 시인성과 레이아웃을 개선한다.

## 2. 변경 내용
### 2.1 Backend 리팩토링 (`app/views/monitor.py`)
- 함수명 변경: `test` -> `gridView`
- 경로 변경: `@expose('/test')`, `@expose('/test/<param>')` -> `@expose('/gridView')`, `@expose('/gridView/<param>')`
- 메뉴 링크 업데이트: `TABLE.INFO` 링크의 `href`를 `/monitor/gridView`로 수정.

### 2.2 UI/UX 개선 (`app/templates/list_jqgrid.html`)
- **디자인 컨셉**: 모던한 컬러 팔레트와 부드러운 그림자(Soft Shadows), Glassmorphism 효과(Backdrop Blur) 적용.
- **레이아웃**: 
    - 조회 구분 선택기: 둥근 모서리의 캡슐 형태로 개선.
    - 검색 조건 영역: Flexbox와 Grid를 활용하여 항목들이 정해진 규칙에 따라 배치되도록 수정.
    - 버튼: 세련된 파란색 테마와 호버 효과 추가.
- **컴포넌트**: 기본 브라우저 스타일 대신 커스텀 스타일이 가미된 input, select 적용.
- **로딩 효과**: 애니메이션이 포함된 현대적인 스피너로 교체.

## 3. 수정 파일 목록
- `app/views/monitor.py`
- `app/templates/list_jqgrid.html`
- `config.py` (버전 업데이트)

## 4. 운영 절차 (Apply Changes)
1. `config.py`의 `APP_NAME` 버전 업데이트. (20260317.004)
2. `docker compose stop mwm-app && docker compose rm -f mwm-app`
3. `docker build --no-cache -t mwm-app -f Dockerfile.app .`
4. `docker compose up -d mwm-app`
