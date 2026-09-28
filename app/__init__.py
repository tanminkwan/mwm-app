import logging
import os
import sys
from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_appbuilder import AppBuilder, SQLA, IndexView

from flask_apscheduler import APScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

class MyIndexView(IndexView):
    index_template = 'my_index.html'

from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)


@app.after_request
def _vary_on_cookie(response):
    """세션을 쓰는 응답이 앞단 캐시에 공유되지 않게 한다 (Flask PYSEC-2026-2151 완화).

    고친 Flask(3.1.3)는 FAB 4.x 가 허용하지 않는다. 대부분 응답이 사용자별이라 모든 응답에 붙인다.
    """
    response.vary.add('Cookie')
    return response


app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config.from_object("config")
app.config['SCHEDULER_JOBSTORES'] = {
    'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
}
app.config['SCHEDULER_API_ENABLED'] = True

"""
 Logging configuration
"""
logging.basicConfig(
    level=app.config['LOGGING_LEVEL'],
    format=app.config['LOGGING_FORMAT'],
    stream=sys.stdout
)
#logging.getLogger('werkzeug').setLevel(app.config['LOGGING_LEVEL'])

db = SQLA(app)
migrate = Migrate(app, db)


# FAB 의 datetime 위젯은 시분초를 입력할 수 없다. 네이티브 입력으로 교체한다.
# AppBuilder 생성 전에 호출해야 한다. 자세한 배경은 app/fieldwidgets.py 참조.
from app.fieldwidgets import install as _install_datetime_widget
_install_datetime_widget()

appbuilder = AppBuilder(app, db.session, indexview=MyIndexView)
#Current WAS Status
WAS_STATUS = dict()

#Constant Values (loaded from config.py)
con_val = dict(
    TAG_EMAILS     = app.config['TAG_EMAILS']
   ,SMTP_HOST      = app.config['SMTP_HOST']
   ,SMTP_PORT      = app.config['SMTP_PORT']
   ,SMTP_USE_TLS   = app.config['SMTP_USE_TLS']
   ,SMTP_USERNAME  = app.config['SMTP_USERNAME']
   ,SMTP_PASSWORD  = app.config['SMTP_PASSWORD']
   ,SMTP_SENDER    = app.config['SMTP_SENDER']
   ,KROKI_URL      = app.config['KROKI_URL']
)

PLANTUML_URL = app.config.get('PLANTUML_URL')

#scheduler = BlockingScheduler(timezone='Asia/Seoul')
#os.environ['TZ']='Asia/Seoul'
scheduler = APScheduler()

"""
from sqlalchemy.engine import Engine
from sqlalchemy import event

#Only include this for SQLLite constraints
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Will force sqllite contraint foreign keys
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
"""
from . import models
from app.views import was, agent, monitor, knowledge, itam
from app.views.common import TokenView
from app.sqls import was, agent, monitor, knowledge, batch, server, itam_compare
from app.api import was_api, agent_api, common_api, model_api, grid_api, batch_api, itam_compare_api, monitor_api, knowledge_api
from . import jobs

# Add API Documentation (Swagger) to Security menu
appbuilder.add_link("API Documentation", href="/swagger/v1", category="Security", category_icon="fa-lock")

# Add API Token Management to '나의 정보' (My Info) menu, visible to general users
# Use add_view with category to ensure sync_role_permissions can collect all PVMs correctly
appbuilder.add_view(TokenView(), "개인 인증 토큰 발급", icon="fa-user", category="나의 정보")

# MQTT 실시간 Command 발송 (MQTT_ENABLED=False 면 아무 작업도 하지 않는다)
from .mqtt import init_publisher as init_mqtt_publisher
init_mqtt_publisher(app.config)

scheduler.init_app(app)
scheduler.start()

from app.idp_auth import idp_auth_bp, init_oauth
init_oauth(app)
app.register_blueprint(idp_auth_bp, url_prefix='/idp')

# with app.app_context():
#     db.create_all()