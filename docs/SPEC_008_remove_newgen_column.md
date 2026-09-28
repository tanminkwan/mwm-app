# SPEC_008: JEUS 목록 '차세대' 컬럼 제거

## 1. 개요
- JEUS 목록 및 WAS Instance 목록에서 더 이상 필요하지 않은 '차세대'(`newgeneration_yn`) 컬럼을 제거하여 화면을 간소화한다.

## 2. 변경 내용
### 2.1 UI 개편 (`app/views/was.py`)
- `WasCommonView` (JEUS 목록의 부모 뷰)의 `list_columns`에서 `newgeneration_yn` 제거.
- `WasInstanceModelView` (WAS Instance 목록)의 `list_columns`에서 `newgeneration_yn` 제거.

## 3. 수정 파일 목록
- `app/views/was.py`
- `config.py` (버전 업데이트)

## 4. 운영 절차 (Apply Changes)
1. `config.py`의 `APP_NAME` 버전 업데이트. (20260317.006)
2. `docker compose stop mwm-app && docker compose rm -f mwm-app`
3. `docker build --no-cache -t mwm-app -f Dockerfile.app .`
4. `docker compose up -d mwm-app`
