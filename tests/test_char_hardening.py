"""ZAP 전체 점검(2026-09-30) 뒤 정리 — Swagger UI 기본 끔 · DB 연결 확인 · eval 제거 (HOWTO_020 §6)."""
import json
import re
from pathlib import Path

from app import app as flask_app, db

TEMPLATES = Path(flask_app.root_path) / 'templates'


def test_swagger_ui_is_off_by_default(client):
    """Swagger UI 번들에 오래된 DOMPurify 가 들어 있다. 필요할 때만 MWM_SWAGGER_UI=true 로 켠다."""
    assert flask_app.config['FAB_API_SWAGGER_UI'] is False
    assert client.get('/swagger/v1').status_code == 404


def test_db_connections_are_checked_before_use(app):
    """DB 가 재기동된 뒤 끊긴 연결로 500 이 나지 않게 한다."""
    assert flask_app.config['SQLALCHEMY_ENGINE_OPTIONS']['pool_pre_ping'] is True
    with app.app_context():
        assert db.engine.pool._pre_ping is True


def test_show_with_json_does_not_eval():
    source = (TEMPLATES / 'showWithJson.html').read_text(encoding='utf-8')
    assert not re.search(r'\beval\s*\(', source)
    assert 'JSON.parse' in source


def test_show_widget_renders_mappings_as_json(app):
    """위젯은 dict 값을 JSON 으로 그린다 — 화면 스크립트가 JSON.parse 로 읽는다."""
    value = {'name': "it's <b>", 'none': None, 'flag': True, 'n': [1, 2]}
    with app.test_request_context():
        html = flask_app.jinja_env.get_template('widgets/showWithIds.html').render(
            include_columns=['obj', 'plain'], value_columns=[value, 'text'],
            label_columns={'obj': 'Changed Object', 'plain': 'Plain'}, formatters_columns={},
            fieldsets=None, actions={}, pk=1, modelview_name='X')
    span = re.search(r'id="Changed Object">(.*?)</span>', html, re.S).group(1)
    assert '<b>' not in span
    # 브라우저가 span 의 글자(text)로 읽는 값 — HTML 엔티티를 풀어 JSON 으로 읽힌다
    import html as html_lib
    assert json.loads(html_lib.unescape(span)) == value
