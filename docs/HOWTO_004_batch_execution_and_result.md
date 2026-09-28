# HOWTO_004_Batch 실행 및 결과 확인 방법

본 문서는 APScheduler에 의해 실행되는 서버 측 배치 로직(ServerFunc)의 실행 구조와, 실행 결과를 로그에서 식별하는 방법에 대해 설명합니다.

## 1. 배치 실행 구조
- **스케줄러**: `app/jobs.py`에 정의된 `APScheduler`가 정해진 주기(Cron/Interval)에 따라 배치 함수를 호출합니다.
- **배치 함수**: `app/sqls/batch.py` 내의 `@batch_function` 데코레이터가 적용된 함수들입니다.
- **식별자**: 모든 배치 실행은 고유한 `command_id` (UUID)를 할당받아 실행됩니다.

## 2. 결과 확인 방법 (Log Grep)

배치 작업은 UI상의 `AgResult` 테이블에 기록되지 않으므로, 컨테이너 로그를 통해 결과를 확인해야 합니다. 모든 로그 메시지에는 `[command_id]` 형식이 포함되어 있어 쉽게 식별이 가능합니다.

### 2.1 실시간 로그 확인
특정 배치 작업이 진행 중일 때 다음과 같이 실시간으로 확인할 수 있습니다.
```bash
docker logs -f mwm-app | grep "시작" 
```

### 2.2 특정 작업의 전체 흐름 확인
DB나 스케줄러에서 확인한 `command_id`를 사용하여 해당 작업의 모든 로그를 추출할 수 있습니다.
```bash
# 예: command_id가 'a1b2c3d4e5f6'인 경우
docker logs mwm-app | grep "\[a1b2c3d4e5f6\]"
```

### 2.3 실행 성공/실패 여부 요약 확인
작업 완료 시 로그에 결과 요약이 남도록 설계되었습니다.
```bash
docker logs mwm-app | grep "작업 완료"
```
출력 예시:
`[a1b2c3d4e5f6] 작업 완료: re_register_all_was_from_text - 결과: (15, 'Total 15 WAS processed. 15 succeeded.')`

## 3. 주요 로그 패턴
- **시작**: `[ID] 시작: {함수명} - {시각}`
- **진행 상세**: `[ID] {함수명}: Processing WAS '{was_id}' ...`
- **성공**: `[ID] {함수명}: WAS '{was_id}' success.`
- **실패**: `[ID] {함수명}: WAS '{was_id}' failed: {사유}`
- **완료**: `[ID] 작업 완료: {함수명} - 결과: {요약}`
- **오류**: `[ID] 오류 발생: {함수명} - {에러내용}`

## 4. 관련 파일
- `app/sqls/batch.py`: 배치 로직 및 데코레이터 정의
- `app/jobs.py`: 스케줄러 작업 정의
- `config.py`: 로깅 레벨 설정 (`LOGGING_LEVEL`)
