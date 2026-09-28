# HOWTO 018 — 테스트 작성 가이드

프로젝트의 TDD 규칙이 **언제** 테스트를 쓰는지를 정한다.
이 문서는 **어떻게** 쓰는지를 다룬다.

여기 적힌 함정은 전부 이 프로젝트에서 **실제로 밟은 것**이다. 가정이 아니다.

---

## 1. 먼저 알아둘 것

### 1.1 실행은 `mwm-test` 이미지에서

`pytest` 는 운영 이미지에 없다. 테스트 도구는 `requirements-dev.txt` 에 있고
`Dockerfile.test` 가 `mwm-app` 위에 얹는다.

```bash
docker build -t mwm-test -f Dockerfile.test .

docker run --rm --network host \
  -v "$PWD/tests:/app/tests" \
  -v "$PWD/pytest.ini:/app/pytest.ini:ro" \
  -e MWM_DATABASE_URI="postgresql://<user>:<password>@localhost:<port>/mw" \
  mwm-test pytest -q
```

**호스트에 venv 를 만들지 않는다.** 프로젝트 전체 규칙이다.

### 1.2 테스트는 `mw_test` 에서 돈다

`MWM_DATABASE_URI` 를 `/mw` 로 주더라도 `conftest.py` 가 **`/mw_test` 로 바꾼다.**
바뀌지 않으면 실행을 중단한다.

이 안전장치는 사고가 있어서 생겼다 — 예전 구조는 운영 DB 에 사용자를 만들었다.


### 1.3 빠른 되먹임은 `-m unit`

```bash
... mwm-test pytest -q -m unit      # 91개, 0.34초
... mwm-test pytest -q              # 127개, 약 70초
```

단위 테스트만 돌리면 1초 안에 끝난다. 파서를 고치는 중이라면 이것만 돌린다.

---

## 2. 파일과 marker

### 2.1 이름이 곧 분류다

| 접두사 | 뜻 | 예 |
| :--- | :--- | :--- |
| `test_unit_*` | 외부 의존 없는 순수 로직 | `test_unit_webtob_httpm.py` |
| `test_char_*` | 특성화 — HTTP 계약·화면 가용성 | `test_char_routes.py` |
| `test_api_*` | API 단위 동작 | `test_api_markdown.py` |

`tests/manual/` 은 **사람이 살아있는 서버를 상대로** 돌리는 스크립트다.
`pytest` 가 import 하면 실제 HTTP 호출이 나가므로 `norecursedirs` 로 수집에서 뺐다.

### 2.2 marker 는 등록해야 쓸 수 있다

```python
pytestmark = pytest.mark.unit        # 파일 전체에 적용
```

`pytest.ini` 의 `markers` 에 없는 이름을 쓰면 **에러**다(`strict = True`).
새 marker 가 필요하면 `pytest.ini` 에 설명과 함께 추가한다.

---

## 3. 특성화 테스트 쓰는 법

이 코드베이스에는 명세 문서가 거의 없다. 그래서 대부분의 테스트가
**"옳은 동작"이 아니라 "현재 동작"을 고정**하는 특성화 테스트다.

### 3.1 단언문은 반드시 **관찰한 뒤** 쓴다

코드를 읽고 "이럴 것이다"로 쓰지 않는다. 먼저 실행해서 출력을 본다.

```bash
docker run --rm --network host -v "$PWD:/probe" -w /app -e PYTHONPATH=/app \
  -e MWM_DATABASE_URI="..." mwm-test python /probe/probe.py
```

이 방식으로 도메인 파서 테스트를 쓰면서
`-Xms2g` 가 2 로 저장되는 결함을 찾았다. **코드를 읽어서는 보이지 않았다** —
`opt[4:][:-1]` 이 `m` 접미사에서만 우연히 맞는다는 것은 값을 넣어 보고 나서야 드러났다.

### 3.2 결함도 일단 고정하고 표시한다

```python
def test_jvm_heap_without_a_unit_loses_its_last_digit():
    """**결함**: 단위가 없으면 마지막 숫자가 잘린다.  ...
    """
    assert get_jvm_options(None, '-Xms512')[0] == 51
```

고칠 때 **무엇이 바뀌는지** 이 테스트가 보여준다. 실제로 5-7b 에서 그렇게 썼다.

### 3.3 판단이 끝난 것은 결함 표시를 지운다

조사 결과 문제가 아니면 docstring 에서 `결함` 을 빼고 **판단 근거와 결론**을 적는다.
`test_first_line_quoted_value_loses_internal_spaces` 가 그 예다 —
"같은 논거로 다시 제안하지 말 것"까지 적어 둔다.

---

## 4. 의존을 끊는 방법

### 4.1 `self` 를 안 쓰는 메서드는 인스턴스 없이 부른다

```python
from app.sqls.jeus_dml import JeusDomain

get_jvm_options = JeusDomain._getJvmOptions      # ABC 라 인스턴스화 불가
get_jvm_options(None, '-Xms2g')                  # self 자리에 None
```

### 4.2 DB 호출은 `monkeypatch` 로 바꾼다

모듈 속성을 갈아 끼운다. import 한 이름이 아니라 **모듈 객체**를 대상으로 해야 한다.

```python
from app.sqls import relationship

def test_ip_is_looked_up(monkeypatch):
    monkeypatch.setattr(relationship, 'get_host_id', lambda ip: f'resolved-{ip}')
    assert relationship.get_real_web_host_id('10.0.0.5', 'h1') == 'resolved-10.0.0.5'
```

호출되면 안 되는 경로는 `pytest.fail` 을 심어 둔다.

```python
monkeypatch.setattr(relationship, 'get_host_id',
                    lambda ip: pytest.fail('조회가 일어나면 안 된다'))
```

### 4.3 시계에 의존하지 않는다

시간을 인자로 받는 함수라면 **고정된 값을 넣는다.**

```python
MONDAY_0915 = datetime(2026, 9, 28, 9, 15)
assert _is_now_in_any_cron_range('0 9 * * 1-5:30', MONDAY_0915) is True
```

`datetime.now()` 를 쓰는 테스트는 언젠가 반드시 깨진다.

---

## 5. 밟았던 함정

| 함정 | 무슨 일이 났나 | 방지 |
| :--- | :--- | :--- |
| **엔진이 import 시점에 바인딩된다** | 테스트가 **운영 DB** 에 사용자를 만들었다 | `conftest.py` 가 `app` import **전에** 환경변수를 바꾸고, `db.engine.url` 을 검사한다. **import 순서를 바꾸지 말 것** |
| **app context 누수** | `app` fixture 가 context 를 세션 내내 열어둬 `g` 가 요청 사이에 남았다. **로그인 안 한 클라이언트가 인증된 것처럼** 동작 | fixture 는 context 를 **닫은 상태로** `yield` 한다 |
| **parametrize ID 충돌** | `'15843.0'`(문자열)과 `15843.0`(float)이 같은 ID 를 만들어 수집이 거부됐다 | `ids=['str-with-.0', 'float', ...]` 를 명시한다 |
| **`addopts` 의 CLI 플래그 무시** | `addopts = --strict-markers` 가 pytest 9 에서 **아무 효과가 없었다** | 엄격 옵션은 **ini 옵션**으로 쓴다 (`strict = True`) |
| **`field.data` 가 항상 기대한 타입은 아니다** | 검색 필터 위젯이 문자열을 넘겨 list 뷰 7개가 500 이 됐다 | 타입을 단정하지 말고 `hasattr` 로 분기한다 |

---

## 6. 통과해야 하는 것들

task 를 끝내려면 아래가 전부 초록이어야 한다. CI 가 같은 것을 본다.

| 관문 | 실패 조건 | 근거 |
| :--- | :--- | :--- |
| `pytest` | 실패·에러 1건이라도 | |
| **새 `DeprecationWarning`** | 유예 목록에 없는 것이 나오면 | 업그레이드 조기 경보 |
| **미등록 marker** | `pytest.ini` 에 없는 marker | 5-3 |
| **flake8 차단 검사** | `E9`/`F63`/`F7`/`F82` 1건이라도 | 5-3 |
| **flake8 스타일 래칫** | 총계가 `.flake8-baseline` 초과 | 5-3 |
| **커버리지 게이트** | `.coverage-baseline` 미달 | `.coverage-baseline` |

기준선을 **낮추는 방향**(린트) 또는 **높이는 방향**(커버리지)으로 개선했다면
해당 파일의 숫자도 같이 갱신해 커밋한다. CI 가 `::notice::` 로 값을 알려준다.

---

## 7. 커버리지를 읽는 법

```bash
... -v "$PWD/.coveragerc:/app/.coveragerc:ro" mwm-test pytest --cov
```

**라인 커버리지를 그대로 믿지 않는다.** 테스트를 하나도 돌리지 않고
import 만 해도 **38%** 가 나온다 — `class`·`def`·컬럼 선언이 전부 "실행된 구문"이다.

**분기 커버리지를 본다.** 함수 본문 안의 갈림길을 세므로 import 로 부풀릴 수 없다.
게이트도 두 지표를 함께 본다.

> CI 수치는 실행마다 0.18%p 가량 흔들린다(구문 18개). 로컬은 안정적이다.
> 기준선에 여유가 있는 이유다.

---

## 8. 무엇을 테스트하지 않나

- **FAB 가 하는 일** — list 뷰 렌더링은 FAB 의 제네릭 `ModelView.list()` 가 한다.
  우리 뷰 클래스는 대부분 선언이라 58개 화면을 전부 렌더링해도
  `app/views/was.py` 는 616 구문 중 2개만 늘었다. 특성화 테스트는
  **커버리지가 아니라 HTTP 계약**을 지키는 장치다.
- **외부에 실제 영향을 주는 것** — 메일 발송 등은 `@pytest.mark.integration` 을 달고
  기본 실행에서 빠진다. 돌리려면 `pytest -m integration`.
- **DB 에 깊이 묶인 함수** — 지금 구조로는 단위 테스트가 닿지 않는다.
  억지로 붙이지 말고, 세션 주입이 가능하도록 **구조를 바꾼 뒤** 붙인다
  (리팩터링이므로 계획서 8.1.1 상 **기존 동작 고정 테스트가 선행**돼야 한다).
