# SPEC_005: WAS 인스턴스 미사용(use_yn=NO) 시 다이어그램 스타일 적용

## 1. 개요
- 사용자가 `mw_was_instance.use_yn = 'NO'`로 설정한 인스턴스를 관계도(Relationship Diagram)에서 제외하는 대신, 시각적으로 비활성화된 상태임을 알 수 있도록 스타일을 적용한다.
- 라이브러리(`jquery.flowchart.js`)의 원본 코드를 수정하지 않고 스타일을 반영해야 한다.

## 2. 변경 내용
### 2.1 Backend (`app/sqls/relationship.py`)
- `get_was_relationship` 함수에서 `use_yn='YES'` 필터를 제거하여 모든 인스턴스를 조회하도록 변경.
- `use_yn == 'NO'`인 경우 라벨에 유니코드 조합 취소선(U+0336)을 적용하는 `strike()` 함수 도입.
- 프론트엔드에서 특정 라벨을 식별하여 색상을 변경할 수 있도록 라벨 끝에 투명 마커(`\u200D`, Zero Width Joiner) 추가.

### 2.2 Frontend (`app/templates/listWithJson.html`)
- `drawDiagram` 함수 내에 추가 로직 구현.
- `flowchart('setData', jdata)` 실행 후, `\u200D` 마커가 포함된 라벨 엘리먼트를 찾아 CSS `color: gray` 처리.

## 3. 수정 파일 목록
- `app/sqls/relationship.py`
- `app/templates/listWithJson.html`
- `config.py` (버전 업데이트)

## 4. 운영 절차 (Apply Changes)
1. `config.py`의 `APP_NAME` 버전 업데이트.
2. `docker compose stop mwm-app && docker compose rm -f mwm-app`
3. `docker build --no-cache -t mwm-app -f Dockerfile.app .`
4. `docker compose up -d mwm-app`
