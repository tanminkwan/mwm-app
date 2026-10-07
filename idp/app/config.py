import os
import sys

def get_required_env(name):
    """
    필수 환경변수를 가져옴. 없으면 명확한 가이드와 함께 에러 로그를 남기고 즉시 종료.
    """
    val = os.getenv(name)
    if not val:
        error_msg = f"\n{'!'*60}\n[CRITICAL CONFIG ERROR] Required environment variable '{name}' is MISSING.\n"
        error_msg += f"Please check your 'docker-compose.yml' or '.env' file.\n"
        error_msg += f"Server cannot start without this constant.\n{'!'*60}\n"
        sys.stderr.write(error_msg)
        sys.stderr.flush()
        # 프로세스 자체를 즉시 종료하여 불필요한 스택 트레이스 없이 명확히 알림
        sys.exit(1)
    return val

class Config:
    """IDP 서버 기본 설정. 모든 설정값은 환경변수 필수, 누락 시 기동 불가."""

    # ── DB (필수) ──
    SQLALCHEMY_DATABASE_URI = get_required_env("IDP_DATABASE_URI")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_NAME = "mwm_idp_session"

    # ── Security (필수) ──
    SECRET_KEY = get_required_env("IDP_SECRET_KEY")
    PREFERRED_URL_SCHEME = 'https'
    PASSWORD_HASH_METHOD = "bcrypt"
    PASSWORD_MIN_LENGTH = int(os.getenv("IDP_PASSWORD_MIN_LENGTH", "8"))
    # 로그인 연속 실패 N회면 M분 잠금 (brute force 방어). N <= 0 이면 잠금 끔
    LOGIN_MAX_ATTEMPTS = int(os.getenv("IDP_LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCK_MINUTES = int(os.getenv("IDP_LOGIN_LOCK_MINUTES", "15"))

    # ── OAuth2 ──
    OAUTH2_TOKEN_EXPIRES_IN = int(os.getenv("OAUTH2_TOKEN_EXPIRES_IN", "3600"))
    OAUTH2_REFRESH_TOKEN_EXPIRES_IN = int(
        os.getenv("OAUTH2_REFRESH_TOKEN_EXPIRES_IN", "86400")
    )

    # ── Default Client (필수) ──
    DEFAULT_CLIENT_ID = get_required_env("IDP_MWM_CLIENT_ID")
    DEFAULT_CLIENT_SECRET = get_required_env("IDP_MWM_CLIENT_SECRET")
    DEFAULT_REDIRECT_URI = get_required_env("IDP_MWM_REDIRECT_URI")

    # ── UI ──
    APP_TITLE = os.getenv("IDP_APP_TITLE", "MWM Identity Provider")

    # ── OIDC (필수) ──
    OIDC_ISSUER = get_required_env("OIDC_ISSUER")
    IDP_RSA_PRIVATE_KEY = get_required_env("IDP_RSA_PRIVATE_KEY")


    # ── Logging ──
    LOG_LEVEL = os.getenv("IDP_LOG_LEVEL", "INFO")

    # ── Sync (필수 DB URI 포함) ──
    SYNC_SOURCES = {
        "mwm_app": {
            "description": "미들웨어관리소(mwm-app) 사용자",
            "db_uri": get_required_env("SYNC_MWM_DB_URI"),
            "table": "ab_user",
            "id_column": "id",
            "column_mapping": {
                "username": "username",
                "email": "email",
                "first_name": "first_name",
                "last_name": "last_name",
                "password_hash": "password",
                "active": "active",
            },
            "role_source": {
                "type": "join",
                "join_table": "ab_user_role",
                "join_user_column": "user_id",
                "join_role_column": "role_id",
                "role_table": "ab_role",
                "role_id_column": "id",
                "role_name_column": "name",
            },
            "filter": "active = true",
            "sync_password": True,
            "auto_sync_interval_minutes": 0,
        }
    }


class TestConfig(Config):
    """테스트 전용 설정 (필수값 임석/모킹)"""
    TESTING = True
    # 필수값 체크 우회용 더미 설정
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key"
    DEFAULT_CLIENT_ID = "test-client"
    DEFAULT_CLIENT_SECRET = "test-secret"
    DEFAULT_REDIRECT_URI = "http://localhost/callback"
    OIDC_ISSUER = "http://localhost"
    IDP_RSA_PRIVATE_KEY = "/tmp/dummy.pem"
    
    WTF_CSRF_ENABLED = False
    SYNC_SOURCES = {}

