"""명령의 결과 받는 곳(result_receiver)은 SERVER 만 쓴다.

Agent 는 결과를 REST(`POST /api/v1/command/result`)로만 보낸다. MQTT 는 명령을 내려보내는 채널
(command_sender)일 뿐이라, 예전 Agent 는 result_receiver=MQTT 명령의 결과를 어디로도 보내지 않았다.
두 필드가 같은 enum 을 써서 화면에서 MQTT 를 고를 수 있었다.
"""
from types import SimpleNamespace

import pytest

from app.models.common import TargetToSendEnum
from app.views.agent import CommandMasterModelView, _force_result_receiver_server


pytestmark = pytest.mark.unit


def test_add_form_has_no_result_receiver():
    assert 'result_receiver' not in CommandMasterModelView.add_columns
    assert 'result_receiver' not in CommandMasterModelView.edit_columns


@pytest.mark.parametrize('given', [TargetToSendEnum.MQTT, TargetToSendEnum.SERVER, None])
def test_result_receiver_is_forced_to_server(given):
    target = SimpleNamespace(result_receiver=given)
    _force_result_receiver_server(target)
    assert target.result_receiver == TargetToSendEnum.SERVER
