# HOWTO: gc_parsed.csv 결과 자동 저장 및 중복 방지 구현

## 1. 개요
에이전트로부터 수집된 명령 결과 중 파일명이 `gc_parsed.csv`인 데이터에 대하여, 결과를 파싱하고 전용 테이블에 자동으로 저장하는 기능을 구현하는 가이드입니다. 
데이터 저장 시 지정된 복합 키(Composite Key)가 이미 존재할 경우 삽입을 스킵(Skip)하여 중복 저장을 방지합니다.

## 2. 테이블 설계 (Model)

`app/models/monitor.py` 파일에 데이터를 저장할 새 모델을 추가합니다.

### 2.1. 테이블 명세
- **테이블명**: `mo_gc_parsed_log` (가칭)
- **Primary Key**: `id`
- **Unique Key (복합키 3개)**: 
  - `host_id`
  - `was_instance_id`
  - `start_date`
- **기타 컬럼**: 
  - `duration`
  - `end_date`
  - `create_on`

### 2.2. 모델 정의 예시
```python
from sqlalchemy import Column, Integer, String, DateTime, Float, UniqueConstraint
from datetime import datetime
from flask_appbuilder import Model

class MoGcParsedLog(Model):
    __tablename__ = "mo_gc_parsed_log"

    id               = Column(Integer, primary_key=True, nullable=False)
    host_id          = Column(String(30), nullable=False)
    was_instance_id  = Column(String(30), nullable=False)
    start_date       = Column(DateTime(), nullable=False)
    duration         = Column(Float)
    end_date         = Column(DateTime())
    create_on        = Column(DateTime(), default=datetime.now, nullable=False)

    # 중복 저장을 방지하기 위한 유니크 제약 조건 설정
    __table_args__ = (
        UniqueConstraint('host_id', 'was_instance_id', 'start_date', name='uq_gc_parsed_log'),
    )
```

## 3. 자동 실행 (Result Autorun) 연결

명령 결과를 수신할 때 자동으로 실행되는 `AutorunResult` 기능을 활용하여 로직을 구성합니다. 

### 3.1. Result 자동실행 목록 화면에서 매핑 등록
웹 브라우저의 관리자 UI에서 **Agent&Command > Command 처리결과 자동 반영 설정** (Result 자동실행 목록 화면) 메뉴로 이동하여 새 설정을 추가합니다. `gc_parsed.csv` 파일 수신 시 특정 함수가 실행되도록 다음 값을 입력합니다.

- **자동실행 JOB ID (autorun_id)**: `GC_LOG_PARSER` (임의의 고유 ID)
- **자동실행 Type (autorun_type)**: `FILENAME` 선택
- **대상파일/기능 (target_file_name)**: `gc_parsed.csv`
- **자동실행 기능 (autorun_func)**: `update_gc_parsed_log` (실행될 메소드 이름 지정)

### 3.2. AutorunResult 클래스 함수 구현
`app/sqls/agent_dml.py` 파일 내의 `AutorunResult` 클래스에 `update_gc_parsed_log` 메소드를 추가하여, 수신된 결과(`self.result`)를 파싱하고 DB에 저장하도록 합니다. 

- PostgreSQL의 `ON CONFLICT DO NOTHING` (SQLAlchemy의 `on_conflict_do_nothing`) 기능을 활용하여 중복된 복합 키 삽입을 스킵합니다.

```python
import csv
from io import StringIO
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime

# app/sqls/agent_dml.py 내 AutorunResult 클래스에 아래 함수 추가
class AutorunResult:
    # ... (기존 코드) ...

    def update_gc_parsed_log(self):
        result = self.result
        
        # 수신된 결과값 (CSV 내용)과 Key 정보 추출
        content = result.result_text
        host_id = result.host_id.lower()
        
        if not content:
            return 0, 'No data found'
            
        f = StringIO(content)
        reader = csv.reader(f)
        try:
            next(reader) # 헤더 스킵
        except StopIteration:
            return -1, 'Empty CSV'

        insert_data_list = []
        for row in reader:
            if len(row) < 4:
                continue
                
            was_instance_id = row[0]
            # 예: '2026-08-03T00:52:25.242' 형태의 시간 파싱
            start_date = datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%f")
            duration = float(row[2])
            end_date = datetime.strptime(row[3], "%Y-%m-%dT%H:%M:%S.%f")
            
            insert_data_list.append({
                'host_id': host_id,
                'was_instance_id': was_instance_id,
                'start_date': start_date,
                'duration': duration,
                'end_date': end_date
            })
            
        if not insert_data_list:
            return 0, 'No valid data to insert'
            
        # sqlalchemy DB Session
        from app import db
        from app.models.monitor import MoGcParsedLog
        
        # ON CONFLICT DO NOTHING을 활용한 중복(Skip) 방지 처리
        stmt = insert(MoGcParsedLog).values(insert_data_list)
        do_nothing_stmt = stmt.on_conflict_do_nothing(
            index_elements=['host_id', 'was_instance_id', 'start_date']
        )
        
        db.session.execute(do_nothing_stmt)
        # db.session.commit() 은 call_autorun_func 밖에서 처리될 수 있으므로 호출 구조에 맞게 적용
        
        return 1, 'OK'
```

### 3.3. 수동 실행 (Update Config Action) 구조 개선(리팩토링)
현재 `app/views/agent.py` 내의 `update_config` 액션은 DB의 자동실행 매핑(`AgAutorunResult`)을 참조하지 않고 하드코딩된 `if-elif` 분기를 타고 있습니다. 
하드코딩된 과거 분기들을 과감하게 모두 삭제하고, 수동 실행 시에도 **오직 DB 매핑을 통해서만 확인하도록 전면 리팩토링**합니다.

`app/views/agent.py` 내 `ResultModelView`의 `update_config` 메서드를 다음과 같이 수정하여, 앞으로 모든 기능들이 하드코딩 없이 DB 매핑으로만 동작하게 만듭니다.

```python
# app/views/agent.py
class ResultModelView(ModelView):
    # ...
    @action("update_config","Update Config","진짜로?","fa-rocket",single=False)
    def update_config(self, items):
        for result in items:
            if result.result_status.name not in ['CREATE','ERROR']:
                continue

            file_name = result.key_value1
            ar = AutorunResult(result=result)

            # [리팩토링 적용] 동적 매핑(DB 테이블) 기반 함수 호출만 시도
            rtn, msg = ar.call_autorun_func()
            
            # 동적 매핑을 찾지 못한 경우 명시적 에러 처리
            if rtn == 0 and msg == 'No Autorun':
                ar.update_result_status('ERROR', 'Autorun mapping not found for: ' + file_name)
                
            db.session.commit()
```

## 4. 적용 프로세스 

1. **DB 마이그레이션**: `app/models/monitor.py`에 새 모델 추가 후 Alembic(`alembic revision --autogenerate`, `alembic upgrade head`)을 활용하여 DB 테이블 생성.
2. **Autorun 매핑 등록**: 브라우저 UI의 **Agent&Command > Command 처리결과 자동 반영 설정**에서 새 규칙 추가.
3. **로직 작성**: `app/sqls/agent_dml.py` 내의 `AutorunResult` 클래스에 함수 추가 후 Surefire Rebuild 진행.
