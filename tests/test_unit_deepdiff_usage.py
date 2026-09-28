"""DeepDiff 사용 방식의 특성화 테스트 (의존성 업그레이드 안전망).

`agent_dml` 은 설정(JEUS domain, WebtoB http.m)을 다시 받을 때 옛 파싱 결과와 비교해
- 다르지 않으면(`not diff`) 이력을 남기지 않고
- 다르면 `diff.to_json()` 을 변경 이력에 저장한다.
메이저 버전이 바뀌어도 이 두 동작이 같아야 한다.
"""
import json

import pytest
from deepdiff import DeepDiff

pytestmark = pytest.mark.unit

OLD = {'NODE': [{'NAME': 'n1', 'PORT': '80', 'HOSTNAME': ['a.example.com', 'b.example.com']}],
       'VHOST': [{'NAME': 'v1', 'PORT': '8080'}]}


def test_same_content_in_other_order_is_not_a_change():
    reordered = {'VHOST': [{'PORT': '8080', 'NAME': 'v1'}],
                 'NODE': [{'HOSTNAME': ['b.example.com', 'a.example.com'], 'PORT': '80', 'NAME': 'n1'}]}

    assert not DeepDiff(OLD, reordered, ignore_order=True)


def test_changed_value_is_reported_as_json():
    new = json.loads(json.dumps(OLD))
    new['NODE'][0]['PORT'] = '81'

    diff = DeepDiff(OLD, new, ignore_order=True)
    body = json.loads(diff.to_json())

    assert diff
    assert body == {'values_changed': {"root['NODE'][0]['PORT']": {'new_value': '81', 'old_value': '80'}}}


def test_added_item_is_reported_as_json():
    new = json.loads(json.dumps(OLD))
    new['VHOST'].append({'NAME': 'v2', 'PORT': '8443'})

    body = json.loads(DeepDiff(OLD, new, ignore_order=True).to_json())

    assert list(body) == ['iterable_item_added']
    assert list(body['iterable_item_added'].values()) == [{'NAME': 'v2', 'PORT': '8443'}]
