"""메일 발송 API 테스트.

**실제로 메일을 보낸다.** SMTP 설정이 유효해야 하고, 수신자에게 메일이 도착한다.
기본 실행에서는 제외되며 명시적으로 켜야 한다.

    pytest -m integration
"""
import json
import os

import pytest

RECEIVERS = os.getenv('MWM_TEST_RECEIVERS', 'someone@example.com')


@pytest.mark.integration
def test_send_email(client, auth_headers):
    payload = {
        'sender_name': 'MW App 테스트(Pytest)',
        'receivers': RECEIVERS,
        'subject': '[테스트] 메일 발송 API',
        'content': '<h1>메일 발송 테스트</h1><p>Pytest 로 발송된 메일입니다.</p>',
    }

    response = client.post(
        '/api/v1/email/send',
        data=json.dumps(payload),
        headers=auth_headers,
        content_type='application/json',
    )

    assert response.status_code == 200
    assert response.json['message'] == 'Email sent successfully'
