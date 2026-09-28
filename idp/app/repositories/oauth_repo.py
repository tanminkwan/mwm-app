"""OAuth2 데이터 접근 계층. SOLID-SRP: OAuth2 관련 DB 조작만 담당."""
import secrets
import time

from app.models import db, OAuth2Client, OAuth2AuthorizationCode, OAuth2Token


class OAuthRepository:
    """OAuth2 Client, Code, Token 테이블에 대한 CRUD 연산"""

    # ── Client ──
    def get_client_by_id(self, client_id):
        return OAuth2Client.query.filter_by(client_id=client_id).first()

    def get_all_clients(self):
        return OAuth2Client.query.all()

    def get_client_by_pk(self, client_id_pk):
        return db.session.get(OAuth2Client, client_id_pk)

    def create_client(self, client_id, client_secret, client_name, redirect_uris,
                    grant_types="authorization_code refresh_token",
                    scope="openid profile email",
                    policy_mapping=None):
        client = OAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            client_name=client_name,
            redirect_uris=redirect_uris,
            grant_types=grant_types,
            scope=scope,
            policy_mapping=policy_mapping or {}
        )
        db.session.add(client)
        db.session.flush()
        return client

    def delete_client(self, client_obj):
        db.session.delete(client_obj)
        db.session.flush()

    # ── Authorization Code ──
    def create_authorization_code(self, client_id, redirect_uri, scope, user_id,
                                  nonce=None, code_lifetime=300):
        code = OAuth2AuthorizationCode(
            code=secrets.token_urlsafe(32),
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            user_id=user_id,
            nonce=nonce,
            expires_at=int(time.time()) + code_lifetime,
        )
        db.session.add(code)
        db.session.flush()
        return code

    def get_authorization_code(self, code):
        return OAuth2AuthorizationCode.query.filter_by(code=code).first()

    def delete_authorization_code(self, code_obj):
        db.session.delete(code_obj)
        db.session.flush()

    # ── Token ──
    def create_token(self, user_id, client_id, scope, expires_in):
        token = OAuth2Token(
            access_token=secrets.token_urlsafe(32),
            refresh_token=secrets.token_urlsafe(32),
            token_type="Bearer",
            scope=scope,
            expires_in=expires_in,
            expires_at=int(time.time()) + expires_in,
            user_id=user_id,
            client_id=client_id,
        )
        db.session.add(token)
        db.session.flush()
        return token

    def get_token_by_access(self, access_token):
        return OAuth2Token.query.filter_by(access_token=access_token).first()

    def get_token_by_refresh(self, refresh_token):
        return OAuth2Token.query.filter_by(refresh_token=refresh_token).first()

    def revoke_token(self, token_obj):
        db.session.delete(token_obj)
        db.session.flush()

    def commit(self):
        db.session.commit()

    def rollback(self):
        db.session.rollback()
