# Docker 이미지 이전 가이드 (Migration Guide)

## 1. 개요
개발 환경에서 빌드된 Docker 이미지를 외부 전송용으로 분할(Split)하고, 폐쇄망(On-premise) 환경에서 다시 병합하여 로드하는 절차를 설명함.

## 2. 이미지 추출 및 분할 (개발 환경)

### 2.1. Docker 이미지 저장 및 압축
```bash
# 1. 이미지 저장
docker save -o mwm-base.tar mwm-base:latest

# 2. Gzip 압축
gzip mwm-base.tar
```

### 2.2. 파일 분할 및 확장자 변경
```bash
# 3. 3개 파일로 분할 (숫자 접미사, 3자리)
split -n 3 -d -a 3 mwm-base.tar.gz mwm-base.tar.gz.
split -n 2 -d -a 3 mwm-app-ref_1st.zip.gz mwm-app-ref_1st.zip.gz.

# 4. 전송용 확장자(.gsd) 추가
for f in mwm-base.tar.gz.*; do mv "$f" "${f%.*}.gsd"; done
```
*   생성 결과 예시: `mwm-base.tar.gz.000.gsd`, `mwm-base.tar.gz.001.gsd`, `mwm-base.tar.gz.002.gsd`

## 3. 이미지 복구 및 로드 (온프레미스 환경)

### 3.1. 파일 병합 및 압축 해제
```bash
# 1. 분할된 파일(.gsd) 병합
cat mwm-base.tar.gz.*.gsd > mwm-base.tar.gz

# 2. 압축 해제
gunzip mwm-base.tar.gz
```

### 3.2. Docker 이미지 로드
```bash
# 3. 이미지 로드
docker load -i mwm-base.tar
```

### 3.3. 확인
```bash
docker images | grep mwm-base
```
