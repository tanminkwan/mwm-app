"""MQTT 실시간 Command 발송 패키지.

이 모듈은 **paho 를 import 하지 않는다.** `MQTT_ENABLED=False` 인 환경에서
paho-mqtt 가 설치되어 있지 않아도 앱이 정상 기동해야 하기 때문이다.
실제 클라이언트 구현(`mqtt_publisher`)은 `init_publisher()` 안에서 지연 import 된다.
"""
import logging

# 프로세스 단위 싱글턴. init_publisher() 로만 설정한다.
_publisher = None


def get_publisher():
    """현재 publisher 를 반환한다. MQTT 미사용/초기화 실패 시 None.

    `from app.mqtt import _publisher` 처럼 값을 직접 import 하면 import 시점의
    None 이 고정되므로(기존 kafka_producer 의 문제) 반드시 이 함수로 접근한다.
    """
    return _publisher


def init_publisher(config):
    """설정에 따라 publisher 를 생성한다.

    MQTT_ENABLED 가 False 면 paho import 를 포함해 **아무 작업도 하지 않는다.**
    어떤 실패도 예외로 전파하지 않는다. app/__init__.py 는 팩토리 없는 모듈 레벨
    스크립트라서, 여기서 예외가 나가면 앱 전체가 기동하지 못한다.
    """
    global _publisher

    if not config.get('MQTT_ENABLED'):
        logging.info('MQTT 비활성화 (MQTT_ENABLED=False) - REST 폴링만 사용')
        return None

    if not config.get('MQTT_PASSWORD'):
        logging.warning('MQTT_ENABLED=True 이지만 MQTT_PASSWORD 가 비어 있음 - MQTT 비활성화')
        return None

    try:
        from .mqtt_publisher import Publisher4Mqtt  # 지연 import

        _publisher = Publisher4Mqtt(
            host=config['MQTT_BROKER_HOST'],
            port=config['MQTT_BROKER_PORT'],
            username=config['MQTT_USERNAME'],
            password=config['MQTT_PASSWORD'],
            client_id_prefix=config.get('MQTT_CLIENT_ID_PREFIX', 'controller'),
            keepalive=config.get('MQTT_KEEPALIVE', 60),
            reconnect_delay=config.get('MQTT_RECONNECT_DELAY', 60),
            log_throttle=config.get('MQTT_LOG_THROTTLE_SECONDS', 3600),
            qos=config.get('MQTT_QOS', 1),
            message_expiry=config.get('MQTT_MESSAGE_EXPIRY', 3600),
            publish_timeout=config.get('MQTT_PUBLISH_TIMEOUT', 5),
        )
    except ImportError:
        logging.error('paho-mqtt 미설치 - MQTT 비활성화하고 REST 폴링으로 계속 '
                      '(requirements.txt 반영 후 mwm-base 재빌드 필요)')
    except Exception:
        logging.exception('MQTT publisher 초기화 실패 - REST 폴링으로 계속')

    return _publisher
