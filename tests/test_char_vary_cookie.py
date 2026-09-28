"""세션을 쓰는 응답에 `Vary: Cookie` 를 붙인다 (Flask PYSEC-2026-2151 완화).

Flask 3.1.2 이하는 session 을 읽기만 한 응답에 `Vary: Cookie` 를 빠뜨려, 앞단 캐시가
사용자별 응답을 다른 사용자에게 줄 수 있다. 고친 Flask(3.1.3)는 FAB 4.x 가 허용하지 않으므로
앱에서 헤더를 붙인다.
"""


def test_login_page_varies_on_cookie(client):
    response = client.get('/login/')

    assert 'Cookie' in response.headers.get('Vary', '')


def test_api_response_varies_on_cookie(client):
    response = client.get('/common/health')

    assert 'Cookie' in response.headers.get('Vary', '')
