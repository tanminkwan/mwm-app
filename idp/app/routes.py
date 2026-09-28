"""OAuth2 인증 라우트. SOLID-SRP: HTTP 요청/응답 처리만 담당."""
from urllib.parse import urlencode

from flask import (
    Blueprint, render_template, request, redirect, session, url_for, flash,
    current_app
)
from flask_login import current_user, login_user, logout_user, login_required

from app.models import db, OAuth2Client
from app.repositories.user_repo import UserRepository
from app.repositories.oauth_repo import OAuthRepository
from app.services.user_service import UserService
from app.services.oauth_service import OAuthService

auth_bp = Blueprint("auth", __name__)


def _get_services():
    from app.services.oidc_service import OIDCService
    from app.services.sync_service import SyncService
    user_repo = UserRepository()
    oauth_repo = OAuthRepository()
    oidc_service = OIDCService()
    user_service = UserService(user_repo)
    oauth_service = OAuthService(oauth_repo, user_repo, oidc_service)
    sync_service = SyncService(user_repo)
    return user_service, oauth_service, sync_service, oidc_service


@auth_bp.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        user=current_user,
        app_title=current_app.config.get("APP_TITLE", "MWM IDP")
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.index"))

    user_service, _, _, _ = _get_services()
    next_url = request.args.get("next") or url_for("auth.index")

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = user_service.authenticate(username, password)
        if user:
            login_user(user)
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(next_url)
        else:
            flash("Invalid username or password", "danger")

    return render_template(
        "login.html",
        app_title=current_app.config.get("APP_TITLE", "MWM IDP"),
        action_url=url_for("auth.login", next=request.args.get("next"))
    )


@auth_bp.route("/oauth/authorize", methods=["GET", "POST"])
def authorize():
    user_service, oauth_service, _, _ = _get_services()

    current_app.logger.info(f"Authorize request ({request.method}) from {request.remote_addr}")

    # 파라미터 획득 (GET과 POST 모두 지원)
    client_id = request.args.get("client_id") or request.form.get("client_id", "")
    redirect_uri = request.args.get("redirect_uri") or request.form.get("redirect_uri", "")
    response_type = request.args.get("response_type") or request.form.get("response_type", "")
    scope = request.args.get("scope") or request.form.get("scope", "openid profile email")
    state = request.args.get("state") or request.form.get("state", "")
    nonce = request.args.get("nonce") or request.form.get("nonce", "")

    if request.method == "GET":
        if current_user.is_authenticated:
            # SSO Logic: 자동 리다이렉트 전 랜딩 페이지를 거쳐 브라우저가 앱 쿠키를 저장할 시간을 줌
            try:
                oauth_service.validate_authorize_request(
                    client_id, redirect_uri, response_type
                )
                code = oauth_service.create_authorization_code(
                    client_id=client_id,
                    redirect_uri=redirect_uri,
                    scope=scope,
                    user_id=current_user.id,
                    nonce=nonce,
                )
                params = {"code": code.code}
                if state:
                    params["state"] = state
                
                target_url = f"{redirect_uri}?{urlencode(params)}"
                current_app.logger.info(f"SSO: Showing landing page for user {current_user.username}")
                
                # 원활한 이동을 위해 1초 대기 후 이동하는 랜딩 페이지 반환
                return render_template(
                    "sso_landing.html",
                    target_url=target_url,
                    username=current_user.username,
                    app_title=current_app.config["APP_TITLE"]
                )
            except ValueError as e:
                current_app.logger.warning(f"SSO Validation failed: {str(e)}")
                # Validation failed, show login form instead (fallback)
                pass

        # 로그인 페이지 표시
        try:
            oauth_service.validate_authorize_request(
                client_id, redirect_uri, response_type
            )
        except ValueError as e:
            return render_template("login.html", error=str(e),
                                   app_title=current_app.config["APP_TITLE"]), 400
        return render_template(
            "login.html",
            client_id=client_id,
            redirect_uri=redirect_uri,
            response_type=response_type,
            scope=scope,
            state=state,
            nonce=nonce,
            app_title=current_app.config.get("APP_TITLE", "MWM IDP"),
            action_url=url_for("auth.authorize", client_id=client_id, 
                               redirect_uri=redirect_uri, response_type=response_type, 
                               scope=scope, state=state, nonce=nonce)
        )

    # POST: 로그인 처리
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    user = user_service.authenticate(username, password)
    if not user:
        return render_template(
            "login.html",
            error="Invalid username or password",
            client_id=client_id,
            redirect_uri=redirect_uri,
            response_type=response_type,
            scope=scope,
            state=state,
            app_title=current_app.config["APP_TITLE"],
        ), 401

    # 로그인 세션 생성 및 Authorization Code 발급
    login_user(user)

    if not client_id:
        # OAuth 파라미터가 없으면 대시보드로 이동
        return redirect(url_for("auth.index"))

    try:
        oauth_service.validate_authorize_request(client_id, redirect_uri, response_type)
        code = oauth_service.create_authorization_code(
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            user_id=user.id,
            nonce=nonce,
        )
    except Exception as e:
        return render_template("login.html", error=str(e),
                               client_id=client_id,
                               redirect_uri=redirect_uri,
                               app_title=current_app.config.get("APP_TITLE", "MWM IDP"),
                               action_url=url_for("auth.authorize", client_id=client_id, 
                                                  redirect_uri=redirect_uri, response_type=response_type, 
                                                  scope=scope, state=state, nonce=nonce)), 500

    # Redirect (POST 성공 시에도 1초 대기 랜딩 페이지 노출)
    params = {"code": code.code}
    if state:
        params["state"] = state
    
    target_url = f"{redirect_uri}?{urlencode(params)}"
    current_app.logger.info(f"Manual Login: Showing landing page for user {user.username}")
    
    return render_template(
        "sso_landing.html",
        target_url=target_url,
        username=user.username,
        app_title=current_app.config.get("APP_TITLE", "MWM IDP")
    )


@auth_bp.route("/oauth/token", methods=["POST"])
def token():
    _, oauth_service, _, _ = _get_services()

    current_app.logger.info(f"Token request from {request.remote_addr}: form={request.form}")

    grant_type = request.form.get("grant_type", "")
    client_id = request.form.get("client_id", "")
    client_secret = request.form.get("client_secret", "")

    # Authlib may send client credentials via Basic Auth Header
    if not client_id and request.authorization:
        client_id = request.authorization.username
        client_secret = request.authorization.password

    try:
        if grant_type == "authorization_code":
            code = request.form.get("code", "")
            redirect_uri = request.form.get("redirect_uri", "")
            token_data = oauth_service.exchange_code_for_token(
                code_value=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
        elif grant_type == "refresh_token":
            refresh_token = request.form.get("refresh_token", "")
            token_data = oauth_service.refresh_access_token(
                refresh_token_value=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )
        else:
            return {"error": f"unsupported_grant_type: {grant_type}"}, 400

        return token_data, 200

    except ValueError as e:
        return {"error": str(e)}, 400


# ── Client CRUD UI ──

@auth_bp.route("/clients")
@login_required
def client_list():
    """OAuth2 클라이언트 목록 조회 화면"""
    clients = OAuth2Client.query.order_by(OAuth2Client.id.desc()).all()
    return render_template(
        "client_list.html",
        clients=clients,
        app_title=current_app.config["APP_TITLE"]
    )


@auth_bp.route("/clients/add", methods=["GET", "POST"])
@login_required
def client_add():
    """OAuth2 클라이언트 신규 등록 화면"""
    if request.method == "POST":
        try:
            import json
            mapping_str = request.form.get("policy_mapping", "{}")
            policy_mapping = json.loads(mapping_str) if mapping_str.strip() else {}
            
            client = OAuth2Client(
                client_id=request.form["client_id"],
                client_secret=request.form["client_secret"],
                client_name=request.form["client_name"],
                redirect_uris=request.form["redirect_uris"],
                grant_types=request.form.get("grant_types", "authorization_code refresh_token"),
                scope=request.form.get("scope", "openid profile email"),
                policy_mapping=policy_mapping
            )
            db.session.add(client)
            db.session.commit()
            flash(f"Client '{client.client_id}' registered successfully.", "success")
            return redirect(url_for("auth.client_list"))
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

    return render_template(
        "client_form.html",
        action="Add",
        app_title=current_app.config["APP_TITLE"]
    )


@auth_bp.route("/clients/edit/<int:id>", methods=["GET", "POST"])
@login_required
def client_edit(id):
    """OAuth2 클라이언트 정보 수정 화면"""
    client = OAuth2Client.query.get_or_404(id)
    if request.method == "POST":
        try:
            client.client_id = request.form["client_id"]
            client.client_secret = request.form["client_secret"]
            client.client_name = request.form["client_name"]
            client.redirect_uris = request.form["redirect_uris"]
            client.grant_types = request.form.get("grant_types", "authorization_code refresh_token")
            client.scope = request.form.get("scope", "openid profile email")
            
            import json
            mapping_str = request.form.get("policy_mapping", "{}")
            client.policy_mapping = json.loads(mapping_str) if mapping_str.strip() else {}
            
            db.session.commit()
            flash(f"Client '{client.client_id}' updated successfully.", "success")
            return redirect(url_for("auth.client_list"))
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

    return render_template(
        "client_form.html",
        action="Edit",
        client=client,
        app_title=current_app.config["APP_TITLE"]
    )


@auth_bp.route("/clients/delete/<int:id>", methods=["POST"])
@login_required
def client_delete(id):
    """OAuth2 클라이언트 삭제"""
    client = OAuth2Client.query.get_or_404(id)
    try:
        db.session.delete(client)
        db.session.commit()
        flash(f"Client '{client.client_id}' deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting client: {str(e)}", "danger")
    return redirect(url_for("auth.client_list"))


@auth_bp.route("/logout")
def logout():
    """
    RP-Initiated Logout (OIDC Standard) 및 일반 로그아웃 처리.
    지원 파라미터:
    - id_token_hint: (옵션) 클라이언트가 보유한 ID Token
    - post_logout_redirect_uri: (옵션) 로그아웃 후 리다이렉트할 URL
    - state: (옵션) 상태 값 유지
    """
    post_logout_redirect_uri = request.args.get("post_logout_redirect_uri")
    state = request.args.get("state")
    
    # 1. IDP 세션 종료
    logout_user()
    
    # 2. 리다이렉트 처리
    if post_logout_redirect_uri:
        # 보안을 위해 등록된 클라이언트의 redirect_uris 중 하나와 일치하는지 확인
        # (별도 필드가 없으므로 기존 redirect_uris 목록을 활용)
        from app.models import OAuth2Client
        clients = OAuth2Client.query.all()
        is_valid_uri = False
        for client in clients:
            if client.check_redirect_uri(post_logout_redirect_uri):
                is_valid_uri = True
                break
        
        if is_valid_uri:
            params = {}
            if state:
                params["state"] = state
            
            from urllib.parse import urlencode
            target_url = post_logout_redirect_uri
            if params:
                sep = "&" if "?" in target_url else "?"
                target_url += f"{sep}{urlencode(params)}"
            
            return redirect(target_url)

    flash("Successfully logged out.", "success")
    return redirect(url_for("auth.index"))


@auth_bp.route("/api-key/rotate", methods=["POST"])
@login_required
def rotate_api_key():
    """API Key 생성 및 재발급"""
    if 'Admin' not in current_user.roles and 'PowerUser' not in current_user.roles:
        flash("You do not have permission to manage API keys.", "danger")
        return redirect(url_for("auth.index"))
    
    import secrets
    # mwm_sk_ (secret key) 접두사를 붙여 식별 용이하게 함
    new_key = f"mwm_sk_{secrets.token_urlsafe(32)}"
    current_user.api_key = new_key
    db.session.commit()
    
    flash("New API Key has been generated. Please keep it secure!", "success")
    return redirect(url_for("auth.index"))


@auth_bp.route("/admin/settings")
@login_required
def admin_settings():
    """관리자 전용 설정 페이지"""
    if 'Admin' not in current_user.roles and 'PowerUser' not in current_user.roles:
        flash("관리자 권한이 필요합니다.", "danger")
        return redirect(url_for("auth.index"))
    
    user_service, _, _, _ = _get_services()
    users = user_service.user_repo.get_all()
    return render_template("admin_settings.html", user=current_user, users=users)


@auth_bp.route("/sync-users", methods=["POST"])
@login_required
def sync_users_ui():
    """UI에서 수동으로 mwm-app 사용자를 동기화"""
    if 'Admin' not in current_user.roles and 'PowerUser' not in current_user.roles:
        flash("동기화 권한이 없습니다.", "danger")
        return redirect(url_for("auth.index"))
    
    _, _, sync_service, _ = _get_services()
    try:
        result = sync_service.sync_users("mwm_app")
        flash(
            f"동기화 완료: 신규 {result['created']}명, 수정 {result['updated']}명, "
            f"비활성 {result['deactivated']}명 (오류: {len(result['errors'])}건)",
            "success"
        )
    except Exception as e:
        flash(f"동기화 중 오류 발생: {str(e)}", "danger")
        
    return redirect(url_for("auth.index"))

# ── OIDC Discovery & JWKS ──

@auth_bp.route("/.well-known/openid-configuration")
def openid_configuration():
    """OIDC Discovery 엔드포인트"""
    issuer = current_app.config.get("OIDC_ISSUER", "http://localhost:5000")
    base_url = issuer.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "userinfo_endpoint": f"{base_url}/api/userinfo",
        "jwks_uri": f"{base_url}/oauth/jwks",
        "end_session_endpoint": f"{base_url}/logout",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email", "groups"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "claims_supported": [
            "iss", "sub", "aud", "exp", "iat", "nonce", 
            "preferred_username", "email", "given_name", "family_name", "groups", "policy"
        ]
    }


@auth_bp.route("/oauth/jwks")
def jwks():
    """OIDC JWKS 엔드포인트"""
    _, _, _, oidc_service = _get_services()
    return oidc_service.get_jwks()
