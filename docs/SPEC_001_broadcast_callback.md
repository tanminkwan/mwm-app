# broadcast_callback 기능 변경

> **날짜**: 2026-03-12  
> **버전**: `미들웨어관리소(VER:20260312.005)`  
> **변경 요약**: `ag_command_master.broadcast_yn` (YES/NO Enum) → `broadcast_callback` (String) 으로 변경.  
> callback 함수명을 text로 등록하여 범용적인 broadcast 기능으로 개선.

---

## 1. 변경 배경

기존 `broadcast_yn`은 YES/NO 2가지 선택만 가능하여, YES인 경우 무조건 전체 approved agent에게 broadcast하는 방식이었음.  
이를 callback 함수명을 등록하는 방식으로 변경하여, 다양한 agent 선택 로직을 유연하게 적용할 수 있도록 개선.

---

## 2. DB Migration SQL

```sql
-- broadcast_callback 컬럼 추가
ALTER TABLE ag_command_master ADD COLUMN IF NOT EXISTS broadcast_callback VARCHAR(100);

-- 기존 broadcast_yn='YES' 데이터를 get_all_agents로 마이그레이션
UPDATE ag_command_master SET broadcast_callback = 'get_all_agents' WHERE broadcast_yn = 'YES';

-- 기존 broadcast_yn 컬럼 삭제
ALTER TABLE ag_command_master DROP COLUMN IF EXISTS broadcast_yn;

-- 컬럼 comment 추가
COMMENT ON COLUMN ag_command_master.broadcast_callback IS 'Broadcast Callback 함수명';
```

---

## 3. 수정된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `app/models/agent.py` | `broadcast_yn` (Enum YnEnum) → `broadcast_callback` (String(100)) 컬럼 변경 |
| `app/sqls/agent.py` | callback registry + 3개 기본 callback 함수 추가 + `create_command_detail` 로직 수정 |
| `app/views/agent.py` | list/add/edit 컬럼명, label, validator 수정. `extra_args`로 callback 목록을 템플릿에 전달 |
| `app/templates/agent/command_master_add.html` | broadcast_callback 입력 UI + 사용 가능 callback 목록 및 안내 문구 표시 |
| `app/templates/agent/command_master_edit.html` | broadcast_callback 입력 UI + 사용 가능 callback 목록 및 안내 문구 표시 |
| `config.py` | `APP_NAME` 버전 업데이트 → `미들웨어관리소(VER:20260312.005)` |

---

## 4. Broadcast Callback Registry 구조

`app/sqls/agent.py`에 `broadcast_callback_registry` 딕셔너리와 `@register_broadcast_callback` decorator를 추가.

```python
broadcast_callback_registry = {}

def register_broadcast_callback(name):
    def decorator(func):
        broadcast_callback_registry[name] = func
        return func
    return decorator
```

### 4-1. 기본 제공 callback 함수

| 함수명 | 설명 |
|--------|------|
| `get_all_agents` | Approved 된 **전체** agent 목록 return |
| `get_was_agents` | `MwWas(use_yn=YES)`를 등록한 approved agent 목록 return |
| `get_web_agents` | `MwWeb(use_yn=YES)`를 등록한 approved agent 목록 return |

- 모든 callback 함수는 **입력 파라미터 없이** 내부 로직으로 agent 목록(`list`)을 return.
- `MwWas.agent_id`, `MwWeb.agent_id` 컬럼을 기준으로 `AgAgent` 테이블과 매핑.

### 4-2. 새 callback 함수 추가 방법

`app/sqls/agent.py`에 아래 패턴으로 추가:

```python
@register_broadcast_callback('새_함수명')
def 새_함수명():
    """설명"""
    agents = db.session.query(AgAgent)\
        .filter(조건들).all()
    return agents if agents else []
```

---

## 5. create_command_detail 로직 변경

기존:
```python
if command_rec.broadcast_yn.name == 'YES':
    ags = db.session.query(AgAgent).filter(AgAgent.approved_yn == 'YES').all()
else:
    for agg in command_rec.ag_agent_group:
        for ag in agg.ag_agent:
            ags.append(ag)
    ags += command_rec.ag_agent
```

변경 후:
```python
if command_rec.broadcast_callback:
    callback_func = broadcast_callback_registry.get(command_rec.broadcast_callback)
    if callback_func:
        ags = callback_func()

# callback + agent_group + agent 모두 합산
for agg in command_rec.ag_agent_group:
    for ag in agg.ag_agent:
        ags.append(ag)
ags += command_rec.ag_agent

# set()으로 중복 제거 후 command_detail 생성
for ag in set(ags):
    ...
```

- **callback, agent, agent_group 3개 모두 합산** 후 `set()`으로 distinct 처리.
- callback만 사용해도 되고, 혼합 사용도 가능.

---

## 6. Validation 로직

**3개 중 최소 1개 필수 선택**:
- `broadcast_callback` (callback 함수명) 입력
- `ag_agent` (개별 agent) 선택
- `ag_agent_group` (agent 그룹) 선택

callback 함수명이 입력되면 UI에서 agent/agent_group 필드가 disabled 됨.

---

## 7. UI 동작 변경

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| 필드 타입 | YES/NO Select (Enum) | Text Input (String) |
| 필드명 | `broadcast_yn` | `broadcast_callback` |
| Label | `전체 대상(Broadcast)` | `Broadcast Callback` |
| 입력 예시 | `YES` / `NO` | `get_all_agents`, `get_was_agents`, `get_web_agents` |
| 연동 동작 | YES 선택 시 agent/group disabled | callback 입력 시 agent/group disabled |

### 7-1. 안내 문구 표시 방식

- `views/agent.py`에서 `extra_args`로 callback 목록 리스트를 템플릿에 전달:
  ```python
  extra_args = {'broadcast_callbacks': list(broadcast_callback_registry.keys())}
  ```
- 템플릿(`command_master_add.html`, `command_master_edit.html`)에서 Jinja2로 직접 렌더링:
  ```html
  <p class="help-block"><b>사용 가능:</b> {{ broadcast_callbacks | join(", ") }}</p>
  <p class="help-block">※ Broadcast Callback, 대상 Agent, 대상 Agent 그룹 중 적어도 하나는 선택해야 합니다.</p>
  ```
- 별도 AJAX 호출 없이 페이지 로드 시 서버 사이드 렌더링으로 표시됨.
