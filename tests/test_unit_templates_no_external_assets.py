"""템플릿은 외부(CDN) 스크립트·스타일을 싣지 않는다 (CodeQL js/functionality-from-untrusted-source).

운영은 폐쇄망이라 외부 주소는 닿지 않는다. 닿는 환경에서는 무결성 검증 없이 남의 코드를 실행하게 된다.
필요한 라이브러리는 app/static 에 두거나 FAB 기본 레이아웃이 싣는 것을 쓴다.
"""
import os
import re

import pytest

pytestmark = pytest.mark.unit

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'templates')
EXTERNAL = re.compile(r'<(?:script|link)\b[^>]*\b(?:src|href)\s*=\s*["\']?(?:https?:)?//', re.IGNORECASE)


def _templates():
    for root, _, files in os.walk(TEMPLATES):
        for f in files:
            if f.endswith('.html'):
                yield os.path.join(root, f)


def test_templates_exist():
    assert len(list(_templates())) > 10


def test_no_template_loads_external_scripts_or_styles():
    found = []
    for path in _templates():
        for n, line in enumerate(open(path, encoding='utf-8', errors='replace'), 1):
            if EXTERNAL.search(line):
                found.append(f'{os.path.relpath(path, TEMPLATES)}:{n}: {line.strip()[:100]}')
    assert found == []
