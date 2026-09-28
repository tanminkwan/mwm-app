import jwt
import datetime
import time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from flask import current_app

class OIDCService:
    """OIDC (OpenID Connect) 핵심 로직. ID Token 생성 및 JWKS 추출 담당."""

    _private_key = None
    _public_key = None
    _jwks = None

    def __init__(self):
        pass

    def _get_private_key(self):
        if OIDCService._private_key is None:
            key_source = current_app.config.get("IDP_RSA_PRIVATE_KEY")
            if not key_source:
                raise ValueError("IDP_RSA_PRIVATE_KEY is not configured")
            
            # If it's a file path, read the file
            import os
            if os.path.isfile(key_source):
                try:
                    with open(key_source, 'r') as f:
                        key_pem = f.read()
                except Exception as e:
                    current_app.logger.error(f"Failed to read RSA private key from file {key_source}: {str(e)}")
                    raise ValueError(f"Could not read RSA private key file: {str(e)}")
            else:
                # Assume it's the PEM content directly
                key_pem = key_source

            try:
                # Handle escaped newlines if coming from env var
                if "-----BEGIN" not in key_pem:
                    key_pem = key_pem.replace("\\n", "\n")
                
                OIDCService._private_key = serialization.load_pem_private_key(
                    key_pem.encode("utf-8"),
                    password=None,
                    backend=default_backend()
                )
            except Exception as e:
                current_app.logger.error(f"Failed to load RSA private key: {str(e)}")
                raise ValueError(f"Invalid RSA private key format: {str(e)}")
        
        return OIDCService._private_key

    def get_public_key(self):
        if OIDCService._public_key is None:
            priv_key = self._get_private_key()
            OIDCService._public_key = priv_key.public_key()
        return OIDCService._public_key

    def get_jwks(self):
        """JWKS (JSON Web Key Set) 생성"""
        if OIDCService._jwks is None:
            pub_key = self.get_public_key()
            numbers = pub_key.public_numbers()
            
            # RSA n, e 값을 Base64URL 인코딩 (OIDC 스펙 준수)
            import base64
            def b64_encode(value):
                # 정수를 바이트로 변환 후 base64url 인코딩
                byte_len = (value.bit_length() + 7) // 8
                b = value.to_bytes(byte_len, 'big')
                return base64.urlsafe_b64encode(b).decode('utf-8').rstrip('=')

            OIDCService._jwks = {
                "keys": [
                    {
                        "kty": "RSA",
                        "alg": "RS256",
                        "use": "sig",
                        "kid": "mwm-idp-key-1", # 임의의 Key ID
                        "n": b64_encode(numbers.n),
                        "e": b64_encode(numbers.e)
                    }
                ]
            }
        return OIDCService._jwks

    def create_id_token(self, user, client_id, nonce=None, policy_mapping=None):
        """ID Token (JWT) 생성"""
        now = int(time.time())
        issuer = current_app.config.get("OIDC_ISSUER", "http://localhost:5000")
        expires_in = current_app.config.get("OAUTH2_TOKEN_EXPIRES_IN", 3600)

        payload = {
            "iss": issuer,
            "sub": user.username, # Subject: 고유 사용자 식별자
            "aud": client_id,
            "exp": now + expires_in,
            "iat": now,
            "auth_time": now,
            "preferred_username": user.username,
            "email": user.email,
            "given_name": user.first_name,
            "family_name": user.last_name,
            "roles": user.roles or [],
            "groups": list(dict.fromkeys(
                (user.roles or []) +
                [ (policy_mapping or {}).get(r, r) for r in (user.roles or []) ]
            )),
            "policy": list(dict.fromkeys(
                (user.roles or []) +
                [ (policy_mapping or {}).get(r, r) for r in (user.roles or []) ]
            ))
        }

        if nonce:
            payload["nonce"] = nonce

        # RS256 서명 수행 (Private Key 사용)
        headers = {
            "kid": "mwm-idp-key-1"
        }
        
        token = jwt.encode(
            payload, 
            self._get_private_key(), 
            algorithm="RS256", 
            headers=headers
        )
        return token
