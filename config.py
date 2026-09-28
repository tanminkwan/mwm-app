import os
import sys
import redis
from flask_appbuilder.security.manager import (
    AUTH_OID,
    AUTH_REMOTE_USER,
    AUTH_DB,
    AUTH_LDAP,
    AUTH_OAUTH,
)
from dotenv import load_dotenv
import logging

# 기본 로깅 설정
LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# 환경변수에서 로깅 레벨 가져오기
# 기본 INFO — DEBUG 는 요청 내용까지 남기므로 개발 때만 켠다 (WS-1-7)
log_level = os.getenv('LOGGING_LEVEL', 'INFO').upper()

# 로깅 레벨 문자열을 로깅 모듈의 레벨 상수로 변환
log_levels = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}
LOGGING_LEVEL = log_levels.get(log_level, logging.INFO)  # 모르는 값도 INFO

# .env 파일 로드
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


def get_required_secret(name, min_bytes=32):
    """비밀 값은 기본값을 두지 않는다. 없거나 짧으면 이유를 남기고 기동을 멈춘다."""
    val = os.getenv(name, '')
    if len(val.encode('utf-8')) < min_bytes:
        reason = 'is MISSING' if not val else f'is shorter than {min_bytes} bytes'
        sys.stderr.write(
            f"\n{'!'*60}\n[CRITICAL CONFIG ERROR] Required environment variable '{name}' {reason}.\n"
            f"Set it in '.env' (see .env.example). Server cannot start without it.\n{'!'*60}\n")
        sys.stderr.flush()
        sys.exit(1)
    return val


# Flask 세션 서명 + JWT 서명(JWT_SECRET_KEY 미설정 시 이 값을 쓴다). HS256 이므로 32바이트 이상
SECRET_KEY = get_required_secret('MWM_SECRET_KEY')

# The SQLAlchemy connection string.
# SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(basedir, "app.db")
# SQLALCHEMY_DATABASE_URI = 'mysql://myapp@localhost/myapp'
# SQLALCHEMY_DATABASE_URI = 'postgresql://root:password@localhost/myapp'
# 계정·비밀번호를 담으므로 기본값을 두지 않는다
SQLALCHEMY_DATABASE_URI = get_required_secret('MWM_DATABASE_URI', min_bytes=1)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Redis
# 환경 변수에서 Redis URL 가져오기
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

SESSION_TYPE = 'redis'
#SESSION_PERMANENT = False
SESSION_PERMANENT = True # 서버 재기동 후에도 token 유효하도록
SESSION_USE_SIGNER = True
SESSION_REDIS = redis.from_url(redis_url)

# PlantUML
PLANTUML_URL = os.getenv('PLANTUML_URL', 'https://plantuml.example.com:20443')

# S3
AWS_URL = os.getenv('AWS_URL', 'http://localhost:9000')
# 선택 연동의 비밀은 빈 값이 기본이다. 없으면 해당 기능만 실패한다
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')
BUCKET_NAME = os.getenv('BUCKET_NAME', 'mwm-contents')

NOTIFICATION_URL = os.getenv('NOTIFICATION_URL', 'https://monitor.example.com:20443/notification')
BUCKET_PREFIX = '/uploads/'

# Flask-WTF flag for CSRF
CSRF_ENABLED = True

# ------------------------------
# GLOBALS FOR APP Builder
# ------------------------------
# Uncomment to setup Your App name
APP_NAME = "미들웨어관리소(VER:20260928.001)"
PREFERRED_URL_SCHEME = 'https'

# Uncomment to setup Setup an App icon
# APP_ICON = "static/img/logo.jpg"

# ----------------------------------------------------
# AUTHENTICATION CONFIG
# ----------------------------------------------------
# The authentication type
# AUTH_OID : Is for OpenID
# AUTH_DB : Is for database (username/password()
# AUTH_LDAP : Is for LDAP
# AUTH_REMOTE_USER : Is for using REMOTE_USER from web server
AUTH_TYPE = AUTH_DB
# Uncomment to setup Full admin role name
# AUTH_ROLE_ADMIN = 'Admin'

# Uncomment to setup Public role name, no authentication needed
# AUTH_ROLE_PUBLIC = 'Public'

# Will allow user self registration
# AUTH_USER_REGISTRATION = True

# The default user self registration role
# AUTH_USER_REGISTRATION_ROLE = "Public"

# When using LDAP Auth, setup the ldap server
# AUTH_LDAP_SERVER = "ldap://ldapserver.new"

# Uncomment to setup OpenID providers example for OpenID authentication
# OPENID_PROVIDERS = [
#    { 'name': 'Yahoo', 'url': 'https://me.yahoo.com' },
#    { 'name': 'AOL', 'url': 'http://openid.aol.com/<username>' },
#    { 'name': 'Flickr', 'url': 'http://www.flickr.com/<username>' },
#    { 'name': 'MyOpenID', 'url': 'https://www.myopenid.com' }]
# ---------------------------------------------------
# Babel config for translations
# ---------------------------------------------------
# Setup default language
BABEL_DEFAULT_LOCALE = "ko"
# Your application default translation path
BABEL_DEFAULT_FOLDER = "translations"
# The allowed translation for you app
LANGUAGES = {
    "en": {"flag": "gb", "name": "English"},
    "pt": {"flag": "pt", "name": "Portuguese"},
    "pt_BR": {"flag": "br", "name": "Pt Brazil"},
    "es": {"flag": "es", "name": "Spanish"},
    "de": {"flag": "de", "name": "German"},
    "zh": {"flag": "cn", "name": "Chinese"},
    "ru": {"flag": "ru", "name": "Russian"},
    "pl": {"flag": "pl", "name": "Polish"},
    "ko": {"flag": "ko", "name": "Coree"},
}
# ---------------------------------------------------
# Image and file configuration
# ---------------------------------------------------
# The file upload folder, when using models with files
UPLOAD_FOLDER = basedir + "/app/static/uploads/"

# The image upload folder, when using models with images
IMG_UPLOAD_FOLDER = basedir + "/app/static/uploads/"

# The image upload url, when using models with images
IMG_UPLOAD_URL = "/static/uploads/"
# Setup image size default is (300, 200, True)
# IMG_SIZE = (300, 200, True)

FAB_API_SWAGGER_UI = True
# API 오류 응답에 스택트레이스를 싣지 않는다. 개발 때만 켠다 (WS-1-7)
FAB_API_SHOW_STACKTRACE = os.getenv('FAB_API_SHOW_STACKTRACE', 'False').lower() in ('true', '1', 'yes')

# Theme configuration
# these are located on static/appbuilder/css/themes
# you can create your own and easily use them placing them on the same dir structure to override
# APP_THEME = "bootstrap-theme.css"  # default bootstrap
# APP_THEME = "cerulean.css"
# APP_THEME = "amelia.css"
# APP_THEME = "cosmo.css"
# APP_THEME = "cyborg.css"
# APP_THEME = "flatly.css"
# APP_THEME = "journal.css"
# APP_THEME = "readable.css"
# APP_THEME = "simplex.css"
# APP_THEME = "slate.css"
APP_THEME = "spacelab.css"
# APP_THEME = "united.css"
# APP_THEME = "yeti.css"

# ---------------------------------------------------
# Constant Values (moved from app/__init__.py con_val)
# ---------------------------------------------------
TAG_EMAILS    = '이메일-'
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USE_TLS  = os.getenv('SMTP_USE_TLS', 'True').lower() in ('true', '1', 'yes')
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_SENDER   = os.getenv('SMTP_SENDER', '')
KROKI_URL     = os.getenv('KROKI_URL', 'http://mwm-kroki:8000')

#Added by mwm

# JWT: sub 클레임 타입 검증 비활성화
#   PyJWT 2.10+ 는 RFC 7519 를 엄격히 적용해 sub 가 문자열이 아니면 거부한다
#   ("Subject must be a string"). 그런데 Flask-AppBuilder 의
#   /api/v1/security/login 이 identity=user.id (정수) 로 토큰을 만들고,
#   이 앱도 4곳에서 같은 방식을 쓴다. FAB 쪽은 우리가 고칠 수 없다.
#   서명 검증은 그대로이며 타입 검사만 끄는 것이다.
#   FAB 5.2.3 업그레이드(WS-2-3) 때 FAB 가 str 로 바꿨는지 재확인하고 제거를 검토한다.
JWT_VERIFY_SUB = False
SCHEDULER_API_ENABLED = True
AGENT_OFFLINE_MINUTES = 5

# IDP Configuration
IDP_INTERNAL_SERVER_URL = os.getenv('IDP_INTERNAL_SERVER_URL', 'http://mwm-idp:5000')
IDP_EXTERNAL_SERVER_URL = os.getenv('IDP_EXTERNAL_SERVER_URL', 'http://localhost:5000')
IDP_CLIENT_ID = os.getenv('IDP_CLIENT_ID', 'mwm-client')
IDP_CLIENT_SECRET = os.getenv('IDP_CLIENT_SECRET', '')

# ---------------------------------------------------
# MQTT (실시간 Command 발송)
# ---------------------------------------------------
# 브로커: eclipse-mosquitto:2.0 (별도 compose 프로젝트 'mqtt')
# 컨테이너 내부에서는 localhost 가 아니라 docker 게이트웨이(=호스트)를 거쳐야 한다.
# docker-compose.yml 이 extra_hosts 로 mqtt-broker.local:host-gateway 를 매핑하므로
# 컨테이너에서는 MQTT_BROKER_HOST=mqtt-broker.local 이 기본값이다.
# host-gateway 는 docker 가 런타임에 실제 게이트웨이로 치환한다 - IP 를 박지 않는다.
#
# MQTT 사용여부 스위치. 기본 False(opt-in).
# False 이면 MQTT 관련 활성화를 일절 하지 않는다 —
#   paho import 안 함 / 클라이언트 생성 안 함 / 백그라운드 스레드 안 뜸 /
#   접속·재시도 안 함 / 발행 시도 안 함.
# 전 구간이 기존 REST 폴링으로만 동작한다.
MQTT_ENABLED = os.getenv('MQTT_ENABLED', 'False').lower() in ('true', '1', 'yes')
MQTT_BROKER_HOST = os.getenv('MQTT_BROKER_HOST', 'localhost')
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', '1883'))
MQTT_USERNAME = os.getenv('MQTT_USERNAME', 'central')
# 비밀번호는 코드에 두지 않는다. .env 또는 컨테이너 환경변수로만 주입한다.
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')
# client_id 는 f"{MQTT_CLIENT_ID_PREFIX}-{socket.gethostname()}-{os.getpid()}" 로 조립한다.
# pid 로 같은 서버의 프로세스 간 충돌을 막는다(중복 시 브로커가 기존 접속을 끊는다).
MQTT_CLIENT_ID_PREFIX = os.getenv('MQTT_CLIENT_ID_PREFIX', 'controller')
MQTT_KEEPALIVE = int(os.getenv('MQTT_KEEPALIVE', '60'))
# 재접속 재시도 주기(초, 고정). paho reconnect_delay_set(min=max=이 값) 으로 지정한다.
# 브로커가 죽어 있어도 앱 기동은 막지 않고 이 주기로 무한 재시도한다.
MQTT_RECONNECT_DELAY = int(os.getenv('MQTT_RECONNECT_DELAY', '60'))
# 연결성 로그 억제 창(초). 재시도가 60초마다 돌아도 사건 종류별 1시간에 1건만 남긴다.
MQTT_LOG_THROTTLE_SECONDS = int(os.getenv('MQTT_LOG_THROTTLE_SECONDS', '3600'))
# central 계정 ACL: topic write cmd/#  (발행 전용, 구독 시 메시지 미전달)
MQTT_CMD_TOPIC = os.getenv('MQTT_CMD_TOPIC', 'cmd/{agent_id}/req')
MQTT_BROADCAST_TOPIC = os.getenv('MQTT_BROADCAST_TOPIC', 'cmd/broadcast/req')
MQTT_QOS = int(os.getenv('MQTT_QOS', '1'))
# 명령 유효시간(초). 브로커가 이 시간이 지난 큐 메시지를 스스로 폐기한다.
MQTT_MESSAGE_EXPIRY = int(os.getenv('MQTT_MESSAGE_EXPIRY', '3600'))
MQTT_PUBLISH_TIMEOUT = float(os.getenv('MQTT_PUBLISH_TIMEOUT', '5'))
