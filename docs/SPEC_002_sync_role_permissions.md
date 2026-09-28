# Role/Permission 자동 동기화 (sync_role_permissions)

> **날짜**: 2026-03-16  
> **버전**: `미들웨어관리소(VER:20260316.003)`  
> **변경 요약**: BaseApi 상속 클래스 네이밍 규칙 정립 (CommonView -> CommonApi 등) 및 Role 자동 생성 로직 개선.

---

## 1. 변경 배경

기존에는 Role과 Permission을 관리자가 FAB Security UI에서 수동으로 매핑해야 했음.  
메뉴 구성이 변경되거나 뷰가 추가될 때마다 수동 관리가 필요하여 유지보수 부담이 컸음.  
최상위 메뉴 카테고리 단위로 Role을 자동 정의하고, 권한을 일괄 동기화하는 기능을 추가.

---

## 2. 수정된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `app/sqls/batch.py` | `sync_role_permissions` batch 함수 + `MENU_CATEGORY_TO_ROLE`, `API_CLASSES_FOR_ROLE` 매핑 추가 |
| `config.py` | `APP_NAME` 버전 업데이트 → `미들웨어관리소(VER:20260312.010)` |

---

## 3. 실행 방법

### 3-1. Command 유형 등록 (최초 1회)

`Agent&Command > Command 유형` 메뉴에서 Add:

| 필드 | 값 |
|------|-----|
| Command Type ID | `SYNC.ROLE_PERMISSIONS` |
| Command Type Name | `Role/Permission 자동 동기화` |
| Command Class | `[서버내부기능]` |
| Target File Name | `sync_role_permissions` |

### 3-2. Command 실행

`Agent&Command > Command 목록` 에서 Add:

| 필드 | 값 |
|------|-----|
| Command Type | `SYNC.ROLE_PERMISSIONS` 선택 |
| 실행 구분 | `ONETIME` |
| 최초실행일시 | (현재시각 이후) |

→ 스케줄러가 해당 시각에 `sync_role_permissions` 함수를 자동 실행.

### 3-3. Batch API 호출 (대안)

```bash
curl -X POST http://localhost:8000/api/v1/batch/run/sync_role_permissions \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"command_id": "MANUAL"}'
```

---

## 4. Role 생성 기준

### 4-1. 명명 규칙

- Role 이름은 `{카테고리}_rgroup` 형식
- 예: `Server` 메뉴 → `server_rgroup`

### 4-2. 메뉴 카테고리 → Role 매핑 (MENU_CATEGORY_TO_ROLE)

| 메뉴 카테고리 | Role 이름 | 포함 메뉴 예시 |
|---|---|---|
| `Server` | `server_rgroup` | 서버 목록, DB Master, App Master |
| `Was` | `mw_rgroup` | WAS 목록, JEUS MS 목록, Was Http Listener 등 |
| `Web` | `mw_rgroup` | WEB 목록, Web Server 목록, SSL FILE 등 |
| `Agent&Command` | `agent_rgroup` | Agent, Agent 그룹, Command 유형/목록/상세 등 |
| `Monitor` | `monitor_rgroup` | 모니터링 관련 메뉴 |
| `System` | `system_rgroup` | 시스템 관리 메뉴 |
| `지식관리` | `knowledge_rgroup` | 지식 관리 관련 메뉴 |
| `ITAM 대사` | `itam_rgroup` | ITAM 대사 관련 메뉴 |
| `Tools` | `tools_rgroup` | Git 등 도구 메뉴 |

> **Was + Web 통합**: 두 카테고리 모두 `mw_rgroup` 하나로 매핑됨.  
> `mw_rgroup` Role을 가진 사용자는 WAS와 WEB 메뉴 모두 접근 가능.

### 4-3. API 통합 Role (api_rgroup)

시스템 내 등록된 모든 API 클래스를 동적으로 수집하여 하나의 Role로 관리.

- **수집 대상**: `flask_appbuilder.api.BaseApi`를 상속받은 모든 클래스
- **수집 방법**: `appbuilder.baseviews`를 순회하며 `BaseApi` 인스턴스를 찾아 해당 클래스명의 모든 PVM 할당

### 4-4. 공통 Role (common_rgroup)

모든 사용자가 로그인 후 기본적으로 가져야 하는 가시성 및 프로필 관리 권한을 통합 관리.

| View | 설명 |
|---|---|
| `MyIndexView` | 메인 대시보드 접근 |
| `UserDBModelView` | 내 정보 조회/수정 |
| `ResetPasswordView` | 비밀번호 재설정 |
| `UserInfoEditView` | 사용자 정보 편집 |
| `CommonApi` | 공통 파일 다운로드 등 (BaseApi) |
| `Main` (Menu) | 기본 메뉴 구조 접근 |
| `UtKmGroup` (Menu) | 지식관리 그룹 관리 (가시성 필터용) |

### 4-5. Role 세분화 (Variant Roles)

기본 생성되는 각 `{카테고리}_rgroup`에 대해 접근 수준에 따른 변형 Role을 자동 생성함.

| Role 접미사 | 설명 | 제외되는 권한 (Filter) |
|---|---|---|
| `_rgroup` | 기본 (Full) | (모든 권한 포함) |
| `_read_rgroup` | 읽기 전용 | `can_add`, `can_edit`, `can_delete`, `muldelete` |
| `_edit_rgroup` | 수정 가능 | `can_delete`, `muldelete` |

- 예: `server_rgroup` 기반으로 `server_read_rgroup`, `server_edit_rgroup`이 자동 생성/업데이트됨.
- `api_rgroup` 및 `common_rgroup` 에 대해서도 동일한 규칙으로 변형 Role이 생성됨.

---

## 5. 동작 로직 상세

### 5-1. 처리 흐름

```
sync_role_permissions 실행
  │
  ├─ (1) 메뉴 카테고리 순회
  │     │
  │     ├─ appbuilder.menu.menu 에서 최상위 메뉴 아이템 순회
  │     ├─ MENU_CATEGORY_TO_ROLE 에서 role_name 결정
  │     ├─ 카테고리 메뉴 자체 → ('menu_access', 카테고리명) 수집
  │     └─ 하위 child 메뉴 각각:
  │           ├─ ('menu_access', child.name) 수집
  │           └─ FAB DB에서 해당 view의 모든 permission 조회
  │               ├─ (permission_name, view_menu_name) 수집
  │               └─ 연결된 **related_views**가 있을 경우 해당 권한도 함께 수집
  │
  ├─ (2) API 클래스 처리
  │     │
  │     └─ API_CLASSES_FOR_ROLE 의 각 class명으로
  │         FAB DB에서 permission 조회 → api_rgroup 에 수집
  │
  └─ (3) Role 생성/업데이트
        │
        ├─ sm.find_role(role_name) 으로 존재 여부 확인
        ├─ 없으면 → sm.add_role(role_name) 으로 새 Role 생성
        ├─ 있으면 → 기존 Role 사용
        ├─ role.permissions = [] 으로 기존 권한 초기화
        ├─ 수집된 각 (perm_name, view_name) 에 대해:
        │     sm.find_permission_view_menu() → sm.add_permission_role()
        └─ db.session.commit()
```

### 5-2. 권한 수집 항목

하나의 메뉴 아이템(예: `WAS 목록`)에 대해 수집되는 권한 예시:

| Permission | View Menu | 설명 |
|---|---|---|
| `menu_access` | `Was` | 최상위 카테고리 메뉴 접근 |
| `menu_access` | `WAS 목록` | 하위 메뉴 접근 |
| `can_list` | `WAS 목록` | 목록 조회 |
| `can_show` | `WAS 목록` | 상세 조회 |
| `can_add` | `WAS 목록` | 추가 |
| `can_edit` | `WAS 목록` | 수정 |
| `can_delete` | `WAS 목록` | 삭제 |

> **참고**: 뷰에 `base_permissions`가 정의되어 있으면 해당 permission만 존재.  
> 예: `base_permissions = ['can_list', 'can_show']` 인 뷰는 `can_add`, `can_edit`, `can_delete`가 없음.

### 5-3. Role 업데이트 방식

- **신규 Role**: `sm.add_role()` → 생성 후 권한 할당
- **기존 Role**: `role.permissions = []` 으로 **기존 권한 초기화** 후 최신 권한으로 **재할당**
- 이 방식으로 뷰가 추가/삭제되어도 다시 실행하면 최신 상태로 동기화됨

### 5-4. 기존 기능 영향

- **Admin Role**: `_rgroup` 이름이 아니므로 이 함수가 건드리지 않음
- **기타 수동 생성 Role**: `_rgroup` 이름이 아니면 영향 없음
- **기존 Permission/View Menu**: 읽기만 하고 수정하지 않음
- `@batch_function` 데코레이터가 자동으로 `finish_commands()` 호출 + `db.session.commit()` 수행

---

## 6. 코드 위치

### 6-1. 매핑 정의

```python
# app/sqls/batch.py

MENU_CATEGORY_TO_ROLE = {
    'Server':        'server_rgroup',
    'Was':           'mw_rgroup',
    'Web':           'mw_rgroup',
    'Agent&Command': 'agent_rgroup',
    'Monitor':       'monitor_rgroup',
    'System':        'system_rgroup',
    '지식관리':       'knowledge_rgroup',
    'ITAM 대사':     'itam_rgroup',
    'Tools':         'tools_rgroup',
}

API_CLASSES_FOR_ROLE = [
    'CommandApi', 'AgentApi', 'MwServerApi', 'MWConfigurationApi', 'MwDiffApi',
    'BatchApi', 'GridApi', 'ModelSpecApi', 'ItamCompareApi', 'CommonApi',
    'ExampleApi', 'DailyReportApi', 'ShortQueries', 'JsonView', 'MonitorApi',
    'GitView', 'UtApi',
]
```

### 6-2. Batch 함수

```python
@batch_function
def sync_role_permissions():
    """메뉴 기반 Role(_rgroup) 자동 생성 및 권한 할당"""
    sm = appbuilder.sm
    # ... (상세 로직은 5-1 참조)
```

---

## 7. 확장 방법

### 7-1. 새 메뉴 카테고리 추가 시

`MENU_CATEGORY_TO_ROLE` 딕셔너리에 항목 추가:

```python
MENU_CATEGORY_TO_ROLE = {
    ...
    '새카테고리': 'new_rgroup',
}
```

### 7-2. 새 API 클래스 추가 시

`API_CLASSES_FOR_ROLE` 리스트에 클래스명 추가:

```python
API_CLASSES_FOR_ROLE = [
    ...
    'NewApiClassName',
]
```

### 7-3. 여러 카테고리를 하나의 Role로 통합

`MENU_CATEGORY_TO_ROLE`에서 같은 role_name을 지정하면 됨:

```python
'Was': 'mw_rgroup',   # 이 두 카테고리가
'Web': 'mw_rgroup',   # mw_rgroup 하나로 통합됨
```

---

## 8. 실행 결과 예시

실행 성공 시 return 메시지:

```
Created role: server_rgroup; Created role: mw_rgroup; Created role: agent_rgroup; 
Created role: monitor_rgroup; Created role: system_rgroup; Created role: knowledge_rgroup; 
Created role: itam_rgroup; Created role: tools_rgroup; Created role: api_rgroup
```

재실행 시 (role이 이미 존재):

```
Updated role: server_rgroup; Updated role: mw_rgroup; Updated role: agent_rgroup; ...
```

---

## 9. 주의사항

- FAB가 초기화된 후 메뉴/뷰/API가 **모두 등록된 상태**에서 실행해야 정확한 permission 수집 가능
- 새로운 메뉴/뷰가 추가되면 **다시 실행**하여 권한 갱신 필요
- Admin Role은 이 기능의 대상이 아님 (Admin은 전체 권한 보유)
- `_rgroup` Role에 수동으로 추가한 권한은 **재실행 시 초기화**됨 (자동 관리 대상이므로)
