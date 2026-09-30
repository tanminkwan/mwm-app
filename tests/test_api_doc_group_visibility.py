"""지식 문서를 id 로 여는 경로가 목록 화면과 같은 그룹 기준을 쓰는지 (HOWTO_020 §6).

목록은 base_filters(FilterGroupRelation) 로 내 그룹·그룹 없음·내가 쓴 문서만 보여 주지만,
보기·다운로드·메일 발송은 id 만으로 읽어 id 를 바꾸면 다른 그룹 문서가 보였다.
"""
from datetime import datetime

import pytest

from app import db
from app.models.knowledge import UtHtmlContent, UtMdContent, UtKmGroup

GROUP = 'pytest-docgroup-other'


@pytest.fixture
def docs(app, monkeypatch):
    """모델마다 공개 문서 하나와 다른 그룹 문서 하나. 현재 사용자는 다른 그룹에 속한다."""
    with app.app_context():
        group = UtKmGroup(group_name=GROUP)
        db.session.add(group)
        made = {}
        for model, body in ((UtHtmlContent, 'content_html'), (UtMdContent, 'content_md')):
            for kind in ('public', 'private'):
                doc = model(content_name=f'{kind} doc', user_id='someone-else', group_id='',
                            update_on=datetime.now(), create_on=datetime.now(), **{body: f'{kind} body'})
                if kind == 'private':
                    doc.ut_kmgroup = [group]
                db.session.add(doc)
                db.session.flush()
                made[(model.__name__, kind)] = (doc.id, doc.content_id)
        db.session.commit()

    monkeypatch.setattr('app.views.common.get_group_list', lambda: ['pytest-docgroup-mine'])

    def _no_real_mail(*args, **kwargs):
        pytest.fail('테스트가 실제 SMTP 로 메일을 보내려 했다')
    monkeypatch.setattr('app.views.knowledge.send_mail', _no_real_mail)
    yield made

    with app.app_context():
        for model in (UtHtmlContent, UtMdContent):
            for kind in ('public', 'private'):
                doc = db.session.get(model, made[(model.__name__, kind)][0])
                if doc:
                    doc.ut_kmgroup = []
                    db.session.delete(doc)
        db.session.query(UtKmGroup).filter_by(group_name=GROUP).delete()
        db.session.commit()


@pytest.mark.parametrize('model, url', [
    ('UtHtmlContent', '/ut/htmlcontent/{id}'),
    ('UtMdContent', '/ut/mdcontent/{id}'),
    ('UtMdContent', '/ut/mdcontent.download/{content_id}'),
])
def test_other_group_documents_are_hidden(client, docs, model, url):
    doc_id, content_id = docs[(model, 'private')]
    response = client.get(url.format(id=doc_id, content_id=content_id))
    assert response.status_code == 404
    assert b'private body' not in response.data


@pytest.mark.parametrize('model, url', [
    ('UtHtmlContent', '/ut/htmlcontent/{id}'),
    ('UtMdContent', '/ut/mdcontent/{id}'),
    ('UtMdContent', '/ut/mdcontent.download/{content_id}'),
])
def test_public_documents_stay_visible(client, docs, model, url):
    doc_id, content_id = docs[(model, 'public')]
    response = client.get(url.format(id=doc_id, content_id=content_id))
    assert response.status_code == 200
    assert b'public body' in response.data


@pytest.mark.parametrize('model, url', [
    ('UtHtmlContent', '/ut/htmlcontent/{id}/send_email'),
    ('UtMdContent', '/ut/mdcontent/{id}/send_email'),
])
def test_other_group_documents_cannot_be_mailed(client, docs, model, url):
    doc_id, _ = docs[(model, 'private')]
    response = client.post(url.format(id=doc_id), json={'manual_emails': 'a@example.invalid'})
    assert response.status_code == 404


@pytest.mark.parametrize('model, url', [
    ('UtHtmlContent', '/ut/htmlcontent/{id}/send_email'),
    ('UtMdContent', '/ut/mdcontent/{id}/send_email'),
])
def test_public_documents_reach_the_mail_step(client, docs, model, url):
    """보이는 문서는 수신자 검사까지 간다 (수신자가 없으니 400 — 실제로 보내지 않는다)."""
    doc_id, _ = docs[(model, 'public')]
    response = client.post(url.format(id=doc_id), json={'tag_names': [], 'manual_emails': ''})
    assert response.status_code == 400
