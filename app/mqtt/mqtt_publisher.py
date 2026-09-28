"""MQTT Command 발행 클라이언트.

`app/kafka/kafka_producer.py` 의 `Producer4Kafka` 와 같은 계약을 유지한다
(`send_message(topic, message, key) -> int`). 호출부 구조를 바꾸지 않기 위함이다.

반환값만 3단계로 확장했다.
    1  : 발행 성공. 브로커에 해당 Agent 세션이 있어 전달/큐잉됨
    0  : 발행은 됐지만 구독자·세션이 없어 전달 불가 (No matching subscribers)
   -1  : 발행 실패 (미접속 / 타임아웃 / ACL 거부 / 예외)
호출부는 `rtn > 0` 일 때만 MQTT 전달로 간주하고, 그 외에는 REST 폴링으로 fallback 한다.
"""
import json
import logging
import os
import socket
import threading
import time

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

# MQTT 5 reason code
RC_SUCCESS = 0
RC_NO_MATCHING_SUBSCRIBERS = 16


class ThrottledLog:
    """연결성 로그를 사건 종류(key)별로 throttle 창에 1건으로 제한한다.

    `on_disconnect` 는 단절 1회당 1회가 아니라 **재접속 시도가 실패할 때마다**
    호출된다. 재시도 주기가 60초면 시간당 60건, 하루 1440건이 쌓인다.
    각 key 의 최초 발생은 즉시 통과시켜 장애 인지가 늦어지지 않게 하고,
    이후에는 창당 1건으로 줄이면서 억제된 건수를 함께 남긴다.
    """

    def __init__(self, throttle_seconds):
        self.throttle = throttle_seconds
        self._last = {}
        self._suppressed = {}
        self._lock = threading.Lock()

    def should_log(self, key):
        """(기록할지, 지난 창에서 억제된 건수) 를 반환한다."""
        now = time.monotonic()
        with self._lock:
            last = self._last.get(key)
            if last is None or now - last >= self.throttle:
                suppressed = self._suppressed.pop(key, 0)
                self._last[key] = now
                return True, suppressed
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return False, 0


class Publisher4Mqtt:

    def __init__(self, host, port, username, password, client_id_prefix='controller',
                 keepalive=60, reconnect_delay=60, log_throttle=3600,
                 qos=1, message_expiry=3600, publish_timeout=5):

        self.host = host
        self.port = int(port)
        self.qos = int(qos)
        self.message_expiry = int(message_expiry)
        self.publish_timeout = float(publish_timeout)
        self.reconnect_delay = int(reconnect_delay)

        self._log = ThrottledLog(log_throttle)
        self._connected = False
        self._ever_connected = False
        self._down_since = None
        self._reasons = {}
        self._reasons_lock = threading.Lock()

        # client_id 는 같은 서버의 프로세스 간 충돌을 막아야 한다.
        # 컨테이너에서는 PID 네임스페이스가 분리되어 pid 만으로는 부족하므로
        # hostname(컨테이너 ID)을 함께 쓴다. 생성은 여기(인스턴스 생성 시점)에서
        # 해야 한다 - config 모듈 레벨에서 평가하면 preload 기반 fork 배포에서
        # 모든 워커가 부모의 같은 문자열을 물려받아 충돌한다.
        self.client_id = f'{client_id_prefix}-{socket.gethostname()}-{os.getpid()}'

        self._client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            protocol=MQTTProtocolVersion.MQTTv5,
        )
        self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_publish = self._on_publish

        # min == max 로 두어야 고정 주기가 된다.
        # 기본값은 1->2->4->...->120초 지수 backoff 이다.
        self._client.reconnect_delay_set(min_delay=self.reconnect_delay,
                                         max_delay=self.reconnect_delay)

        # connect() 가 아니라 connect_async() 를 쓴다. connect() 는 브로커가
        # 죽어 있으면 예외를 던져 앱 기동을 막지만, connect_async() 는 즉시
        # 반환하고 loop_start() 스레드가 무한 재시도한다. 최초 접속이 한 번도
        # 성공하지 못한 상태에서도 재시도는 계속 돈다.
        self._client.connect_async(self.host, self.port,
                                   keepalive=int(keepalive), clean_start=True)
        self._client.loop_start()

        logging.info('MQTT publisher 기동: %s@%s:%s client_id=%s '
                     '(재시도 %d초 주기, 로그 억제 %d초)',
                     username, self.host, self.port, self.client_id,
                     self.reconnect_delay, log_throttle)

    # ------------------------------------------------------------------ 콜백

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):

        if reason_code.value != RC_SUCCESS:
            # 인증 실패(135) 등. 재시도해도 같은 결과이므로 로그를 억제해야 한다.
            ok, suppressed = self._log.should_log('connect_fail')
            if ok:
                logging.error('MQTT 접속 거부 [%s:%s] %s (직전 %d초 동안 동일 실패 %d건 억제)',
                              self.host, self.port, reason_code,
                              self._log.throttle, suppressed)
            return

        self._connected = True
        down_since, self._down_since = self._down_since, None

        if not self._ever_connected:
            self._ever_connected = True
            logging.info('MQTT 접속 성공 [%s:%s]', self.host, self.port)
            return

        ok, suppressed = self._log.should_log('reconnected')
        if ok:
            downtime = f'{time.monotonic() - down_since:.0f}초' if down_since else '알 수 없음'
            logging.info('MQTT 재접속 성공 [%s:%s] 단절 지속 %s '
                         '(직전 %d초 동안 동일 복구 %d건 억제)',
                         self.host, self.port, downtime, self._log.throttle, suppressed)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):

        self._connected = False
        if self._down_since is None:
            self._down_since = time.monotonic()

        ok, suppressed = self._log.should_log('connect_fail')
        if ok:
            logging.warning('MQTT 접속 단절 [%s:%s] %s - %d초 주기로 재시도 중 '
                            '(직전 %d초 동안 동일 실패 %d건 억제)',
                            self.host, self.port, reason_code, self.reconnect_delay,
                            self._log.throttle, suppressed)

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        with self._reasons_lock:
            self._reasons[mid] = reason_code

    def _take_reason(self, mid):
        with self._reasons_lock:
            return self._reasons.pop(mid, None)

    # ------------------------------------------------------------------- API

    @property
    def is_connected(self):
        return self._connected

    def send_message(self, topic, message, key=''):
        """Command 를 발행한다. 예외를 던지지 않고 1 / 0 / -1 을 반환한다.

        명령 생성 트랜잭션을 깨뜨리지 않는 것이 최우선이다. 실패는 호출부에서
        REST 폴링 fallback 으로 흡수된다.
        """
        if isinstance(message, (str, bytes)):
            payload = message
        else:
            payload = json.dumps(message, ensure_ascii=False, default=str)

        props = Properties(PacketTypes.PUBLISH)
        # 브로커가 이 시간이 지난 큐 메시지를 스스로 폐기한다.
        # 오래된 명령이 뒤늦게 실행되는 것을 막는다.
        props.MessageExpiryInterval = self.message_expiry
        props.ContentType = 'application/json'
        if key:
            props.CorrelationData = str(key).encode()

        try:
            info = self._client.publish(topic, payload, qos=self.qos, properties=props)
        except Exception:
            ok, suppressed = self._log.should_log('publish_error')
            if ok:
                logging.exception('MQTT 발행 예외 [%s] (직전 %d초 동안 동일 예외 %d건 억제)',
                                  topic, self._log.throttle, suppressed)
            return -1

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            # 미접속 등. 이 상태에서 is_published()/wait_for_publish() 를 호출하면
            # RuntimeError 가 발생하므로 절대 호출하지 않는다.
            ok, suppressed = self._log.should_log('publish_no_conn')
            if ok:
                logging.warning('MQTT 미접속으로 발행 실패 [%s] %s - REST 폴링으로 fallback '
                                '(직전 %d초 동안 동일 실패 %d건 억제)',
                                topic, mqtt.error_string(info.rc),
                                self._log.throttle, suppressed)
            return -1

        if self.qos == 0:
            return 1

        try:
            info.wait_for_publish(timeout=self.publish_timeout)
        except (RuntimeError, ValueError) as e:
            self._take_reason(info.mid)
            ok, suppressed = self._log.should_log('publish_no_conn')
            if ok:
                logging.warning('MQTT 발행 확인 실패 [%s] %s - REST 폴링으로 fallback '
                                '(직전 %d초 동안 동일 실패 %d건 억제)',
                                topic, e, self._log.throttle, suppressed)
            return -1

        reason = self._take_reason(info.mid)

        if reason is None:
            return 1

        if reason.value == RC_SUCCESS:
            return 1

        if reason.value == RC_NO_MATCHING_SUBSCRIBERS:
            # Agent 세션이 브로커에 없다. 발행해도 명령이 버려지므로 전달로 보지 않는다.
            logging.info('MQTT 구독자 없음 [%s] - REST 폴링으로 fallback', topic)
            return 0

        # ACL 거부(Not authorized) 등. 설정 문제이므로 재시도해도 같다.
        ok, suppressed = self._log.should_log('publish_refused')
        if ok:
            logging.error('MQTT 발행 거부 [%s] %s (직전 %d초 동안 동일 거부 %d건 억제)',
                          topic, reason, self._log.throttle, suppressed)
        return -1

    def close(self):
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            logging.exception('MQTT publisher 종료 중 예외')
