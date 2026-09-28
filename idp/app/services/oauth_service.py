"""OAuth2 비즈니스 로직. SOLID-SRP: 인가/토큰 관련 정책만 담당."""
import logging

from flask import current_app

logger = logging.getLogger(__name__)


class OAuthService:
    """OAuth2 인가 및 토큰 비즈니스 로직. Repository를 주입받아 사용 (SOLID-DIP)."""

    def __init__(self, oauth_repo, user_repo, oidc_service=None):
        self.oauth_repo = oauth_repo
        self.user_repo = user_repo
        self.oidc_service = oidc_service

    def validate_authorize_request(self, client_id, redirect_uri, response_type):
        client = self.oauth_repo.get_client_by_id(client_id)
        if not client:
            raise ValueError(f"Invalid client_id: {client_id}")
        if not client.check_redirect_uri(redirect_uri):
            raise ValueError(f"Invalid redirect_uri: {redirect_uri}")
        if response_type != "code":
            raise ValueError(f"Unsupported response_type: {response_type}")
        return client

    def create_authorization_code(self, client_id, redirect_uri, scope, user_id, nonce=None):
        code = self.oauth_repo.create_authorization_code(
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            user_id=user_id,
            nonce=nonce,
        )
        self.oauth_repo.commit()
        logger.info(f"Authorization code created for user_id={user_id}, nonce={'yes' if nonce else 'no'}")
        return code

    def exchange_code_for_token(self, code_value, client_id, client_secret,
                                redirect_uri):
        # Client 검증
        client = self.oauth_repo.get_client_by_id(client_id)
        if not client:
            raise ValueError("Invalid client_id")
        if not client.check_client_secret(client_secret):
            raise ValueError("Invalid client_secret")

        # Code 검증
        code = self.oauth_repo.get_authorization_code(code_value)
        if not code:
            raise ValueError("Invalid authorization code")
        if code.is_expired():
            self.oauth_repo.delete_authorization_code(code)
            self.oauth_repo.commit()
            raise ValueError("Authorization code expired")
        if code.client_id != client_id:
            raise ValueError("Client mismatch")
        if code.redirect_uri != redirect_uri:
            raise ValueError("Redirect URI mismatch")

        # Token 생성
        expires_in = current_app.config["OAUTH2_TOKEN_EXPIRES_IN"]
        token = self.oauth_repo.create_token(
            user_id=code.user_id,
            client_id=client_id,
            scope=code.scope,
            expires_in=expires_in,
        )

        # OIDC: ID Token 생성 (scope에 openid 포함 시)
        token_data = token.to_dict()
        if "openid" in (code.scope or "") and self.oidc_service:
            user = self.user_repo.get_by_id(code.user_id)
            if user:
                id_token = self.oidc_service.create_id_token(
                    user=user,
                    client_id=client_id,
                    nonce=code.nonce,
                    policy_mapping=client.policy_mapping
                )
                token_data["id_token"] = id_token
                logger.info(f"ID Token generated for user_id={code.user_id}")

        # Code 삭제 (1회용)
        self.oauth_repo.delete_authorization_code(code)
        self.oauth_repo.commit()

        logger.info(f"Token issued for user_id={code.user_id}")
        return token_data

    def refresh_access_token(self, refresh_token_value, client_id, client_secret):
        # Client 검증
        client = self.oauth_repo.get_client_by_id(client_id)
        if not client or not client.check_client_secret(client_secret):
            raise ValueError("Invalid client credentials")

        # Refresh Token 검증
        old_token = self.oauth_repo.get_token_by_refresh(refresh_token_value)
        if not old_token:
            raise ValueError("Invalid refresh token")
        if old_token.client_id != client_id:
            raise ValueError("Client mismatch")

        # 새 토큰 생성 + 기존 토큰 폐기
        expires_in = current_app.config["OAUTH2_TOKEN_EXPIRES_IN"]
        new_token = self.oauth_repo.create_token(
            user_id=old_token.user_id,
            client_id=client_id,
            scope=old_token.scope,
            expires_in=expires_in,
        )
        self.oauth_repo.revoke_token(old_token)
        self.oauth_repo.commit()

        logger.info(f"Token refreshed for user_id={old_token.user_id}")
        return new_token.to_dict()

    def get_userinfo(self, access_token):
        token = self.oauth_repo.get_token_by_access(access_token)
        if not token:
            raise ValueError("Invalid access token")
        if token.is_expired():
            raise ValueError("Access token expired")

        user = self.user_repo.get_by_id(token.user_id)
        if not user:
            raise ValueError("User not found")

        # 클라이언트의 policy_mapping 적용
        roles = user.roles or []
        client = self.oauth_repo.get_client_by_id(token.client_id)
        policy_mapping = client.policy_mapping if client else None
        mapped_roles = [
            (policy_mapping or {}).get(r, r) for r in roles
        ]

        return {
            "sub": user.username,
            "username": user.username,
            "preferred_username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "given_name": user.first_name,
            "family_name": user.last_name,
            "roles": roles,
            "groups": list(dict.fromkeys(roles + mapped_roles)),
            "policy": list(dict.fromkeys(roles + mapped_roles)),
        }

    # ── Client Management CRUD ──

    def list_clients(self):
        return self.oauth_repo.get_all_clients()

    def get_client(self, client_id_pk):
        client = self.oauth_repo.get_client_by_pk(client_id_pk)
        if not client:
            raise ValueError("Client not found")
        return client

    def create_client(self, client_id, client_secret, client_name, redirect_uris,
                      grant_types=None, scope=None, policy_mapping=None):
        if self.oauth_repo.get_client_by_id(client_id):
            raise ValueError(f"Client ID '{client_id}' already exists")

        client = self.oauth_repo.create_client(
            client_id=client_id,
            client_secret=client_secret,
            client_name=client_name,
            redirect_uris=redirect_uris,
            grant_types=grant_types or "authorization_code refresh_token",
            scope=scope or "openid profile email",
            policy_mapping=policy_mapping or {}
        )
        self.oauth_repo.commit()
        logger.info(f"New OAuth2 client created: {client_id}")
        return client

    def update_client(self, client_id_pk, **kwargs):
        client = self.get_client(client_id_pk)
        
        # client_id 변경 시 중복 체크
        new_client_id = kwargs.get("client_id")
        if new_client_id and new_client_id != client.client_id:
            if self.oauth_repo.get_client_by_id(new_client_id):
                raise ValueError(f"Client ID '{new_client_id}' already exists")

        for key, value in kwargs.items():
            if hasattr(client, key) and value is not None:
                setattr(client, key, value)
        
        self.oauth_repo.commit()
        logger.info(f"OAuth2 client updated: {client.client_id}")
        return client

    def delete_client(self, client_id_pk):
        client = self.get_client(client_id_pk)
        client_id = client.client_id
        self.oauth_repo.delete_client(client)
        self.oauth_repo.commit()
        logger.info(f"OAuth2 client deleted: {client_id}")
