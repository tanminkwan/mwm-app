"""동적 SelectField 두 개가 WTForms 3.2 에서 렌더된다.

WTForms 3.2 는 `iter_choices()` 가 (value, label, selected, render_kw) **4-튜플**을 내야 한다
(3.1 까지는 3-튜플도 받았다). 3-튜플이면 폼을 그릴 때 `ValueError: not enough values to unpack` —
Dependabot 묶음 갱신에서 `/utkmgroupmodelview/add` 가 깨져 드러났다.
FAB 의 자체 필드(`flask_appbuilder/fields.py`)도 4-튜플을 쓴다.
"""
from types import SimpleNamespace

import pytest
from flask import g
from flask_wtf import FlaskForm


@pytest.fixture
def form_ctx(app):
    with app.test_request_context():
        g.user = SimpleNamespace(roles=[SimpleNamespace(name='Admin')], username='pytest')
        yield


def _render(field_cls):
    class F(FlaskForm):
        class Meta:
            csrf = False
        f = field_cls('f')
    field = F().f
    choices = list(field.iter_choices())
    return choices, field()


@pytest.mark.parametrize('path', ['app.views.common.GroupSelectField', 'app.views.knowledge.RoleSelectField'])
def test_dynamic_select_fields_render(form_ctx, path):
    mod, name = path.rsplit('.', 1)
    field_cls = getattr(__import__(mod, fromlist=[name]), name)
    choices, html = _render(field_cls)
    assert choices and all(len(c) == 4 for c in choices)
    assert html.startswith('<select')


@pytest.mark.parametrize('path', ['app.views.common.GroupSelectField', 'app.views.knowledge.RoleSelectField'])
def test_the_error_fallback_also_renders(form_ctx, monkeypatch, path):
    # 역할 조회가 실패하면 '(없음)' 하나로 대신한다 — 그 경로도 4-튜플이어야 한다
    import flask_appbuilder.security.sqla.models as m
    monkeypatch.setattr(m, 'Role', None)
    monkeypatch.setattr('app.views.common.get_groups', lambda: (_ for _ in ()).throw(RuntimeError('x')))
    mod, name = path.rsplit('.', 1)
    field_cls = getattr(__import__(mod, fromlist=[name]), name)
    choices, html = _render(field_cls)
    assert choices == [('', '(없음)', True, {})]
    assert '(없음)' in html
