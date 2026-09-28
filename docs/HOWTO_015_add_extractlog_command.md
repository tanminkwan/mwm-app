# HOWTO_015: 신규 Command Type (ExtractLog) 추가 가이드

## 1. 개요
에이전트(Agent)에서 수행하는 새로운 `ExtractLog` (로그 추출) 기능을 서버(`mw_app`)에서 관리하고 전송할 수 있도록 `CommandClassEnum`을 확장하고, 관련 데이터베이스를 업데이트하는 방법입니다. 결과에 대한 자동실행(Autorun)은 생략된 기본 연동 과정만 설명합니다.

## 2. Model Enum 추가
`app/models/common.py`에 새 커맨드 분류(`CommandClassEnum`) 항목을 추가합니다.

```python
class CommandClassEnum(enum.Enum):
    # ... 기존 내용 ...
    GetRefreshToken= 'Update인증Token'
    ExtractLog     = 'Log Extractor'
```
*참고: 이 단계는 이미 이번 패치에서 `app/models/common.py` 파일 내에 반영되었습니다.*

## 3. Database 마이그레이션
PostgreSQL의 Native Enum 타입으로 지정된 `commandclassenum`을 변경하려면 Alembic 마이그레이션이 필요합니다.

### 3.1. Alembic 마이그레이션 수행
`migrations/versions/a1b2c3d4e5f6_.py` 파일로 `ALTER TYPE commandclassenum ADD VALUE IF NOT EXISTS 'ExtractLog'` 명령이 생성되었습니다. 서버 환경에서 아래 명령어를 실행하여 적용할 수 있습니다.

```bash
flask db upgrade
```

### 3.2. (참고) 수동 SQL 적용
만약 툴을 사용하지 않고 직접 DB 콘솔에서 수행하려면 다음 쿼리를 활용합니다.
```sql
ALTER TYPE commandclassenum ADD VALUE IF NOT EXISTS 'ExtractLog';
```

## 4. UI에서 새 Command Type 템플릿 생성
코드 상에 `ExtractLog`가 반영되었으므로, 구동 후 브라우저 UI에서 다음을 수행합니다.

1. 관리자 시스템 UI 접속
2. **Agent&Command > Command Type 등록** 메뉴 이동
3. 신규 Type 추가 (등록 폼 오픈)
4. `Command Class` 콤보박스에서 **Log Extractor** 선택
5. ID 및 Target File Name, Parameters 등 필요한 커맨드 기본 양식 입력 후 저장

위 과정이 마무리되면, 등록된 Command Type을 이용해 Agent에 신규 로그 추출 명령(Command)을 정상적으로 전달할 수 있습니다.
