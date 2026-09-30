"""주소로 테이블·컬럼 이름을 받는 조회 엔드포인트가 정해진 조합만 읽는지 (HOWTO_020 §5).

예전에는 `/json/htmlviewer/<table>/<column>/...` 와 `/api/v1/model/column_all|column_distinct/<table>.<column>`
이 이름을 그대로 받아 로그인한 누구나 아무 테이블의 아무 컬럼(예: ab_user.password)을 읽을 수 있었다.
"""
import json

import pytest

from app import db
from app.models.knowledge import UtHtmlContent, UtKmGroup


@pytest.fixture
def html_doc(app):
    """그룹이 없는(전체 공개) 문서 하나와 다른 그룹 전용 문서 하나."""
    with app.app_context():
        group = UtKmGroup(group_name='pytest-other-group')
        public = UtHtmlContent(content_name='공개 문서', content_html='<p>public</p>',
                               user_id='someone-else', group_id='')
        private = UtHtmlContent(content_name='다른 그룹 문서', content_html='<p>private</p>',
                                user_id='someone-else', group_id='')
        private.ut_kmgroup = [group]
        db.session.add_all([group, public, private])
        db.session.commit()
        ids = {'public': public.id, 'private': private.id}
    yield ids
    with app.app_context():
        for key in ('public', 'private'):
            doc = db.session.get(UtHtmlContent, ids[key])
            if doc:
                doc.ut_kmgroup = []
                db.session.delete(doc)
        db.session.query(UtKmGroup).filter_by(group_name='pytest-other-group').delete()
        db.session.commit()


def _htmlviewer(doc_id, table='ut_html_content', column='content_html', title='content_name'):
    return f'/json/htmlviewer/{table}/{column}/{title}/{doc_id}'


# --- /json/htmlviewer --------------------------------------------------------

def test_htmlviewer_returns_listed_document(client, html_doc):
    response = client.get(_htmlviewer(html_doc['public']))
    assert response.status_code == 200
    assert response.json == {'html': '<p>public</p>', 'title': '공개 문서'}


@pytest.mark.parametrize('table, column, title', [
    ('ab_user', 'password', 'username'),              # 다른 테이블
    ('ut_html_content', 'user_id', 'content_name'),   # 같은 테이블의 다른 컬럼
    ('ut_html_content', 'content_html', 'user_id'),   # 제목 자리에 다른 컬럼
])
def test_htmlviewer_rejects_unlisted_fields(client, html_doc, table, column, title):
    response = client.get(_htmlviewer(html_doc['public'], table, column, title))
    assert response.status_code == 404


def test_htmlviewer_rejects_non_numeric_key(client):
    assert client.get(_htmlviewer('1 or 1=1')).status_code == 404


def test_htmlviewer_hides_documents_of_other_groups(client, html_doc, monkeypatch):
    """목록 화면과 같은 기준 — 내 그룹·그룹 없음·내가 쓴 문서만 보인다."""
    monkeypatch.setattr('app.views.common.get_group_list', lambda: ['pytest-my-group'])
    assert client.get(_htmlviewer(html_doc['private'])).status_code == 404
    assert client.get(_htmlviewer(html_doc['public'])).status_code == 200


# --- /api/v1/model/column_all · column_distinct --------------------------------

def test_column_all_returns_listed_column(client):
    response = client.get('/api/v1/model/column_all/ag_agent.agent_id')
    assert response.status_code == 200
    assert 'list' in response.json


@pytest.mark.parametrize('path', [
    '/api/v1/model/column_all/ab_user.password',
    '/api/v1/model/column_all/ag_agent.refresh_token',
    '/api/v1/model/column_distinct/ab_user.password',
    '/api/v1/model/column_all/no_dot',
])
def test_column_lookup_rejects_unlisted_columns(client, path):
    assert client.get(path).status_code == 404


def test_column_all_allows_condition_on_the_same_column(client):
    condition = json.dumps({'operator': 'and', 'column': 'tag', 'value': '지식유형'})
    response = client.get('/api/v1/model/column_all/ut_tag.tag', query_string={'condition': condition})
    assert response.status_code == 200


def test_column_all_rejects_condition_on_another_column(client):
    """다른 컬럼 조건은 값을 한 글자씩 맞혀 보는 통로가 된다 (예: ag_agent.refresh_token)."""
    condition = json.dumps({'operator': 'like', 'column': 'refresh_token', 'value': 'ey'})
    response = client.get('/api/v1/model/column_all/ag_agent.agent_id', query_string={'condition': condition})
    assert response.status_code == 400
