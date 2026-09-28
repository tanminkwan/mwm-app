"""정규식 ReDoS 제거 (CodeQL py/polynomial-redos) — 동작은 그대로, 시간만 선형으로.

| 위치 | 예전 식 | 느려지는 입력 |
| :--- | :--- | :--- |
| `mail_sender.convert_md_to_html` 이미지 | `(!\\[[^\\]]*\\]\\()/common/download/...` | `![` 반복 |
| 같은 함수 mermaid 블록 | `(?m)^\\s*```mermaid\\s*\\n(.*?)\\n\\s*```` | ```` ```mermaid ```` 뒤 `\\n ` 반복 |
| `JeusDomain._getAppID` | `(\\d+)(?!.*\\d)` | 숫자 반복 |

앞 둘은 사용자가 쓴 지식관리 본문(메일 발송)이 입력이다.
특성화 테스트로 현재 동작을 먼저 고정하고, 병적 입력이 빨리 끝나는지 본다.
"""
import base64
import time
import zlib
from types import SimpleNamespace

import pytest

from app.sqls.jeus_dml import JeusDomain

pytestmark = pytest.mark.unit

# 예전 식으로는 이 크기에서 수 초~수십 초 걸린다. 선형이면 수 ms 다
N = 20000
LIMIT = 1.0


def _elapsed(fn, *args):
    t = time.perf_counter()
    fn(*args)
    return time.perf_counter() - t


# --- _getAppID ---------------------------------------------------------------

def _app_id(was_instance_id, domain_id='D1'):
    return JeusDomain._getAppID(SimpleNamespace(domain_id=domain_id), was_instance_id)


@pytest.mark.parametrize('inst, expected', [
    ('mwAppMSA01', 'D1.mwAppMSA'),      # 마지막 숫자 묶음 제거. 밑줄이 없어 _MS[A-Z] 치환은 안 탄다
    ('app_MSB12', 'D1.app_MS'),         # 12 제거 → _MSB → _MS
    ('ab12cd345', 'D1.ab12cd'),         # 마지막 묶음만
    ('noDigits', 'D1.noDigits'),
    ('adminServer', 'NOAPP'),
])
def test_get_app_id(inst, expected):
    assert _app_id(inst) == expected


def test_get_app_id_is_linear():
    assert _elapsed(_app_id, '9' * N + 'x1') < LIMIT


# --- convert_md_to_html 의 두 식 -------------------------------------------------

@pytest.fixture
def kroki(monkeypatch):
    """requests.get 을 가로채 kroki 로 보낸 mermaid 코드를 돌려준다."""
    import requests
    sent = []

    def fake_get(url, timeout=None):
        encoded = url.rsplit('/', 1)[1]
        sent.append(zlib.decompress(base64.urlsafe_b64decode(encoded)).decode())
        return SimpleNamespace(status_code=200, content=b'PNG')
    monkeypatch.setattr(requests, 'get', fake_get)
    return sent


@pytest.fixture
def s3(monkeypatch):
    import app.file_manager.s3.filemanager as fm
    got = []

    class FakeS3:
        def get_file(self, path):
            got.append(path)
            return b'IMG'
    monkeypatch.setattr(fm, 'S3FileManager', FakeS3)
    return got


def _html(md):
    from app.mail_sender import convert_md_to_html
    return convert_md_to_html(md, 'http://kroki')


@pytest.mark.parametrize('md', [
    '```mermaid\ngraph TD\nA-->B\n```',
    '  ```mermaid  \ngraph TD\nA-->B\n  ```',        # 들여쓰기·뒤 공백
    '```mermaid\n\ngraph TD\nA-->B\n\n```',          # 앞뒤 빈 줄
    'text\n```mermaid\ngraph TD\nA-->B\n```\nmore',
], ids=['plain', 'indented', 'blank-lines', 'surrounded'])
def test_mermaid_block_is_sent_to_kroki(kroki, md):
    _html(md)
    assert kroki == ['graph TD\nA-->B']


def test_two_mermaid_blocks_are_separate(kroki):
    _html('```mermaid\nA\n```\nx\n```mermaid\nB\n```')
    assert kroki == ['A', 'B']


def test_a_non_mermaid_fence_is_left_alone(kroki):
    _html('```python\nprint(1)\n```')
    assert kroki == []


@pytest.mark.parametrize('md, path', [
    ('![alt](/common/download/a/b.png)', 'a/b.png'),
    ('![](/common/download/x.png)', 'x.png'),
    ('see ![a b](/common/download/p/q.jpg) here', 'p/q.jpg'),
])
def test_markdown_image_is_inlined_from_s3(s3, md, path):
    html, images = _html(md)
    assert s3 == [path]
    assert 'src="cid:s3img_1.' in html
    assert images[0][1] == b'IMG'


def test_an_image_outside_download_is_left_alone(s3):
    _html('![alt](https://example.com/a.png)')
    assert s3 == []


def test_patterns_are_linear():
    from app.mail_sender import MD_IMAGE_RE, MERMAID_RE
    assert _elapsed(MD_IMAGE_RE.sub, '', '![' * N) < LIMIT
    assert _elapsed(MERMAID_RE.sub, '', '```mermaid\n' + '\n ' * N) < LIMIT
    assert _elapsed(MERMAID_RE.sub, '', '```mermaid\n\n' + '\n' * N) < LIMIT
