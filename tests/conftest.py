"""pytest 공용 fixture.

테스트는 **별도 데이터베이스**(`mw_test`)를 쓴다.

## 왜 `app` 을 import 하기 전에 환경변수를 바꾸는가

`app/__init__.py` 는 **import 시점에** `SQLA(app)` 와 `AppBuilder(...)` 를 실행하며,
그때 `config.py` 가 읽은 `SQLALCHEMY_DATABASE_URI` 로 **엔진이 바인딩된다.**
import 후에 `app.config` 를 고쳐도 엔진은 바뀌지 않는다.

실제로 이 구조 때문에 **테스트가 운영 DB(`mw`)에 사용자를 만든 적이 있다.**
기존 conftest 는 운영 DB 에 이미 있는 계정명을 재사용해서 증상이 드러나지 않았을 뿐이다.

그래서 **import 보다 먼저** `MWM_DATABASE_URI` 를 `mw_test` 로 바꾼다.
아래 import 순서를 바꾸면 안 된다.

## `mw_test` 준비

앱 계정에 `CREATEDB` 권한이 없어 테스트가 스스로 만들 수 없다.

- 신규 설치: `create_db.sql` 이 초기화 시 함께 만든다
- 기존 환경: 한 번 만든다 — `docker exec mwm-db psql -U postgres -c "CREATE DATABASE mw_test OWNER <DB 계정>;"`
"""
import os


def _to_test_uri(uri: str) -> str:
    uri = uri.rstrip('/')
    return uri[:-3] + '/mw_test' if uri.endswith('/mw') else uri


# --- app import 이전에 실행되어야 한다 -----------------------------------
if not os.getenv('MWM_DATABASE_URI'):
    raise RuntimeError(
        'MWM_DATABASE_URI 가 없습니다. 운영 DB 와 같은 서버의 /mw 접속 문자열을 주면 '
        '/mw_test 로 바꿔 접속합니다 (예: postgresql://mwm:<비밀번호>@localhost:5433/mw).')
_TEST_DB_URI = _to_test_uri(os.environ['MWM_DATABASE_URI'])
if not _TEST_DB_URI.endswith('/mw_test'):
    raise RuntimeError(
        f'테스트 DB URI 가 mw_test 가 아닙니다: {_TEST_DB_URI}\n'
        'MWM_DATABASE_URI 는 /mw 로 끝나야 합니다.')
os.environ['MWM_DATABASE_URI'] = _TEST_DB_URI

# config.py 는 MWM_SECRET_KEY 가 없으면 기동하지 않는다 (TASK 1-10). 테스트 전용 값을 넣는다
os.environ.setdefault('MWM_SECRET_KEY', 'pytest-only-secret-key-not-for-production-use')
# ------------------------------------------------------------------------

import pytest  # noqa: E402
from flask_appbuilder.security.sqla.models import PermissionView, User  # noqa: E402
from flask_jwt_extended import create_access_token  # noqa: E402

from app import app as flask_app, appbuilder, db  # noqa: E402

# 테스트 전용 계정. 운영 자격증명과 분리한다.
TEST_USERNAME = os.getenv('MWM_TEST_USERNAME', 'pytest-admin')
TEST_PASSWORD = os.getenv('MWM_TEST_PASSWORD', 'pytest-only-not-a-secret')
TEST_EMAIL    = os.getenv('MWM_TEST_EMAIL', 'pytest-admin@example.com')

@pytest.fixture(scope='session')
def app():
    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
    })

    # 준비 작업만 app context 안에서 한다.
    #
    # context 를 테스트 전체에 걸쳐 열어두면 안 된다. Flask 는 요청마다 새 app
    # context 를 밀어 넣는데, 이미 열려 있으면 그것을 재사용해 `g` 가 요청 사이에
    # 남는다. 그러면 Flask-Login 이 `g` 에 캐시한 사용자가 이어져
    # **로그인하지 않은 클라이언트도 인증된 것처럼 동작한다.**
    with flask_app.app_context():
        engine_url = str(db.engine.url)
        if not engine_url.endswith('/mw_test'):
            pytest.exit(
                f'테스트가 운영 DB 에 연결되어 있습니다: {engine_url}\n'
                'conftest.py 의 환경변수 설정이 app import 보다 먼저 실행되어야 합니다.',
                returncode=1)

        try:
            db.create_all()
        except Exception as e:
            pytest.exit(
                f'테스트 DB 에 접속할 수 없습니다: {e}\n'
                'mw_test 가 없다면: docker exec mwm-db psql -U postgres -c \"CREATE DATABASE mw_test OWNER <DB 계정>;\"',
                returncode=1)

        for role_name in ('Admin', 'User', 'Public'):
            appbuilder.sm.add_role(role_name)

        if not appbuilder.sm.find_user(username=TEST_USERNAME):
            appbuilder.sm.add_user(
                username=TEST_USERNAME,
                first_name='Pytest',
                last_name='Admin',
                email=TEST_EMAIL,
                role=appbuilder.sm.find_role('Admin'),
                password=TEST_PASSWORD,
            )

    # context 를 닫은 상태로 넘긴다.
    yield flask_app

    with flask_app.app_context():
        db.session.remove()


@pytest.fixture(scope='session')
def client(app):
    """로그인된 상태를 공유하는 클라이언트 (세션 스코프)."""
    c = app.test_client()
    c.post('/login/', data={'username': TEST_USERNAME,
                            'password': TEST_PASSWORD},
           follow_redirects=False)
    return c


@pytest.fixture
def anon_client(app):
    """매 테스트마다 새로 만드는, 로그인하지 않은 클라이언트."""
    return app.test_client()


@pytest.fixture(scope='session')
def json_header():
    return {'Content-Type': 'application/json;charset=utf-8'}


@pytest.fixture(scope='session')
def test_user(app):
    with app.app_context():
        user = db.session.query(User).filter_by(username=TEST_USERNAME).first()
        assert user is not None, 'app fixture 가 테스트 계정을 만들지 못했습니다.'

        permission = db.session.query(PermissionView).filter_by(
            permission=appbuilder.sm.find_permission('can_httpm_config'),
            view_menu=appbuilder.sm.find_view_menu('MWConfigurationApi'),
        ).first()
        if permission and user.roles and permission not in user.roles[0].permissions:
            user.roles[0].permissions.append(permission)
            db.session.commit()

        return user.id


@pytest.fixture
def auth_headers(app, test_user):
    with app.app_context():
        token = create_access_token(identity=test_user)
    return {'Authorization': f'Bearer {token}'}
