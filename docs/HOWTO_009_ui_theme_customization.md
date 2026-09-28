# HOWTO_009_ui_theme_customization.md

## 1. 개요
Flask-AppBuilder에서 제공하는 기본 UI 테마(Bootswatch)들은 기본적으로 고정된 최대 너비(1170px)를 가지고 있으며, 외부 Google Fonts를 참조하도록 설정되어 있습니다. 이 가이드는 와이드스크린 지원과 폐쇄망 환경을 위해 테마 파일을 일괄적으로 커스터마이징하는 방법을 설명합니다.

---

## 2. 주요 수정 사항

### 2.1 UI 너비 확장 (Widescreen 지원)
기본 Bootstrap 3 사양인 1170px 컨테이너 너비를 1470px로 확장하여 고해상도 모니터 활용도를 높입니다.
- **기존**: `min-width: 1200px` -> `width: 1170px`
- **변경**: `min-width: 1500px` -> `width: 1470px`

### 2.2 외부 폰트(Google Fonts) 호출 차단
폐쇄망 환경에서 외부 인터넷 연결 지연이나 차단으로 인한 로딩 지연을 방지하기 위해 Google Fonts 호출을 주석 처리합니다.

### 2.3 내부 폰트 경로 수정
일부 테마에서 폰트 파일 참조 경로가 상위 디렉토리를 잘못 가리키는 경우(`../fonts` -> `../../fonts`) 이를 바로잡아 로컬 폰트가 정상적으로 로드되도록 합니다.

---

## 3. 적용 방법 (Dockerfile.app 수정 가이드)

`Dockerfile.app` 빌드 시점에 `sed` 명령어를 활용하여 테마 파일을 패치하는 방법입니다. 특정 테마(`amelia.css`)를 제외한 모든 테마에 일괄 적용하는 로직은 다음과 같습니다.

```dockerfile
# FAB_HOME 및 경로 변수 설정 (사용자 환경에 맞게 조정)
ENV FAB_HOME=/usr/local/lib/python3.12/site-packages/flask_appbuilder
ENV FAB_STATIC_DIR=${FAB_HOME}/static/appbuilder

# UI thema 파일의 일괄 수정 (amelia.css 제외)
RUN for f in ${FAB_STATIC_DIR}/css/themes/*.css; do \
    if [ "$(basename $f)" != "amelia.css" ]; then \
        # 1. UI 너비 확장
        sed -i 's/media (min-width:1200px){.container{width:1170px}}/media (min-width:1500px){.container{width:1470px}}/g' "$f"; \
        # 2. 외부 폰트 호출 차단 (정규표현식 활용)
        sed -i 's#@import url("https://fonts.googleapis.com/css?family=[^"]*");#/* @import url(...) */#g' "$f"; \
        # 3. 내부 폰트 경로 수정
        sed -i 's|../fonts|../../fonts|g' "$f"; \
    fi; \
done
```

---

## 4. 관련 파일
- **수정 대상**: `${FAB_STATIC_DIR}/css/themes/*.css`
- **배포 파일**: `Dockerfile.app`

---

## 5. 운영 절차 (Surefire Rebuild)
테마 설정이 변경된 후에는 반드시 다음 절차를 따라 컨테이너를 재빌드해야 안정적으로 반영됩니다.

1. `config.py`의 `APP_NAME` 버전 업데이트
2. `docker compose stop mwm-app && docker compose rm -f mwm-app`
3. `docker build --no-cache -t mwm-app -f Dockerfile.app .`
4. `docker compose up -d mwm-app`
