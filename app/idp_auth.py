import os
from flask import Blueprint, redirect, url_for, session, current_app, request, flash
from authlib.integrations.flask_client import OAuth
from flask_appbuilder.security.sqla.models import User
from flask_login import login_user

idp_auth_bp = Blueprint('idp_auth', __name__)
oauth = OAuth()

def init_oauth(app):
    oauth.init_app(app)
    
    internal_url = app.config.get('IDP_INTERNAL_SERVER_URL')
    external_url = app.config.get('IDP_EXTERNAL_SERVER_URL')
    if not internal_url or not external_url:
        return
        
    app.logger.info(f"OAUTH REGISTER: name=mwm_idp, client_id={app.config.get('IDP_CLIENT_ID')}")
    oauth.register(
        name='mwm_idp',
        client_id=app.config.get('IDP_CLIENT_ID'),
        client_secret=app.config.get('IDP_CLIENT_SECRET'),
        server_metadata_url=f"{internal_url}/.well-known/openid-configuration",
        access_token_url=f"{internal_url}/oauth/token",
        access_token_params=None,
        authorize_url=f"{external_url}/oauth/authorize",
        authorize_params=None,
        api_base_url=f"{internal_url}/api/",
        client_kwargs={'scope': 'openid profile email', 'verify': False},
    )

@idp_auth_bp.route('/login')
def login():
    if not current_app.config.get('IDP_EXTERNAL_SERVER_URL'):
        flash("IDP Login is not configured.", "warning")
        return redirect(url_for("AuthDBView.login"))
        
    # Build redirect URI: e.g., http://localhost:8000/idp/callback
    redirect_uri = url_for('idp_auth.auth_callback', _external=True)
    current_app.logger.info(f"OAUTH LOGIN: redirect_uri={redirect_uri}")
    return oauth.mwm_idp.authorize_redirect(redirect_uri)

@idp_auth_bp.route('/callback')
def auth_callback():
    from app import appbuilder
    if not current_app.config.get('IDP_INTERNAL_SERVER_URL'):
        return redirect(url_for("AuthDBView.login"))
        
    try:
        token = oauth.mwm_idp.authorize_access_token()
        # Fetch user info using the access token
        resp = oauth.mwm_idp.get('userinfo', token=token)
        resp.raise_for_status()
        user_info = resp.json()
        
        username = user_info.get('username')
        
        # Look up user in FAB SecurityManager
        user = appbuilder.sm.find_user(username=username)
        if not user or not user.active:
            flash(f"User {username} not found or inactive in the local system.", "danger")
            return redirect(url_for("AuthDBView.login"))
            
        login_user(user, remember=False)
        return redirect(appbuilder.get_url_for_index)
        
    except Exception as e:
        flash(f"IDP Login failed: {str(e)}", "danger")
        return redirect(url_for("AuthDBView.login"))
