"""Markdown → HTML 변환 API (`/api/v1/markdown/to_html`) 테스트."""
import json
import re

MARKDOWN_URL = '/api/v1/markdown/to_html'


def test_convert_markdown_to_html(client, auth_headers):
    payload = {
        'content': '# Markdown 테스트\n\n- 항목 1\n- 항목 2\n',
    }

    response = client.post(
        MARKDOWN_URL,
        data=json.dumps(payload),
        headers=auth_headers,
        content_type='application/json',
    )

    assert response.status_code == 200
    assert 'html' in response.json

    html = response.json['html']
    # premailer 가 스타일을 인라인하므로 태그에 속성이 붙는다.
    # 문자열 그대로 비교하지 않고 태그와 내용으로 확인한다.
    assert re.search(r'<h1[^>]*>Markdown 테스트</h1>', html)
    assert re.search(r'<li[^>]*>항목 1</li>', html)
    assert re.search(r'<li[^>]*>항목 2</li>', html)


def test_convert_markdown_requires_auth(client):
    response = client.post(MARKDOWN_URL, json={'content': '# x'})
    assert response.status_code == 401
