from functools import wraps
from flask import Blueprint, request, jsonify
from app.models import db, IdpUser
from app.repositories.user_repo import UserRepository
from app.repositories.oauth_repo import OAuthRepository
from app.services.user_service import UserService
from app.services.oauth_service import OAuthService
from app.services.sync_service import SyncService

api_bp = Blueprint("api", __name__)


def require_api_key(f):
    """API Key 및 권한(Admin/PowerUser) 검증 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid API Key in Authorization header"}), 401
        
        api_key = auth_header[len("Bearer "):]
        if not api_key:
            return jsonify({"error": "API Key is required"}), 401
            
        user = IdpUser.query.filter_by(api_key=api_key).first()
        if not user:
            return jsonify({"error": "Invalid API Key"}), 401
            
        # 권한 체크: Admin 또는 PowerUser만 허용
        user_roles = user.roles or []
        if 'Admin' not in user_roles and 'PowerUser' not in user_roles:
            return jsonify({"error": "Forbidden: Insufficient permissions (Admin or PowerUser required)"}), 403
            
        return f(*args, **kwargs)
    return decorated_function


def _get_user_service():
    return UserService(UserRepository())


def _get_oauth_service():
    user_repo = UserRepository()
    return OAuthService(OAuthRepository(), user_repo)


def _get_sync_service():
    return SyncService(UserRepository())


# ── User CRUD ──

@api_bp.route("/users", methods=["GET"])
@require_api_key
def list_users():
    service = _get_user_service()
    users = service.list_users()
    return jsonify([u.to_dict() for u in users]), 200


@api_bp.route("/users", methods=["POST"])
@require_api_key
def create_user():
    service = _get_user_service()
    data = request.get_json(silent=True) or {}

    required = ["username", "email"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        user = service.create_user(
            username=data["username"],
            email=data["email"],
            password=data.get("password"),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            roles=data.get("roles"),
        )
        return jsonify(user.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@api_bp.route("/users/<int:user_id>", methods=["GET"])
@require_api_key
def get_user(user_id):
    service = _get_user_service()
    try:
        user = service.get_user(user_id)
        return jsonify(user.to_dict()), 200
    except ValueError:
        return jsonify({"error": "User not found"}), 404


@api_bp.route("/users/<int:user_id>", methods=["PUT"])
@require_api_key
def update_user(user_id):
    service = _get_user_service()
    data = request.get_json(silent=True) or {}

    try:
        user = service.update_user(user_id, **data)
        return jsonify(user.to_dict()), 200
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            return jsonify({"error": error_msg}), 404
        return jsonify({"error": error_msg}), 409


@api_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_api_key
def delete_user(user_id):
    service = _get_user_service()
    try:
        service.delete_user(user_id)
        return "", 204
    except ValueError:
        return jsonify({"error": "User not found"}), 404


# ── UserInfo (OAuth2 Protected) ──

@api_bp.route("/userinfo", methods=["GET"])
def userinfo():
    oauth_service = _get_oauth_service()

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid Authorization header"}), 401

    access_token = auth_header[len("Bearer "):]

    try:
        info = oauth_service.get_userinfo(access_token)
        return jsonify(info), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 401


# ── Sync ──

@api_bp.route("/sync/<source_name>", methods=["POST"])
@require_api_key
def sync(source_name):
    service = _get_sync_service()
    try:
        result = service.sync_users(source_name)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except ConnectionError as e:
        return jsonify({"error": str(e)}), 502


@api_bp.route("/sync/status", methods=["GET"])
@require_api_key
def sync_status():
    service = _get_sync_service()
    sources = service.get_sync_sources()
    return jsonify({
        "available_sources": list(sources.keys()),
        "descriptions": {k: v.get("description", "") for k, v in sources.items()},
    }), 200


# ── OAuth2 Client CRUD ──

@api_bp.route("/clients", methods=["GET"])
@require_api_key
def list_clients():
    service = _get_oauth_service()
    clients = service.list_clients()
    return jsonify([c.to_dict() for c in clients]), 200


@api_bp.route("/clients", methods=["POST"])
@require_api_key
def create_client():
    service = _get_oauth_service()
    data = request.get_json(silent=True) or {}
    
    required = ["client_id", "client_secret", "client_name", "redirect_uris"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
        
    try:
        client = service.create_client(**data)
        return jsonify(client.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@api_bp.route("/clients/<int:client_id_pk>", methods=["GET"])
@require_api_key
def get_client(client_id_pk):
    service = _get_oauth_service()
    try:
        client = service.get_client(client_id_pk)
        return jsonify(client.to_dict()), 200
    except ValueError:
        return jsonify({"error": "Client not found"}), 404


@api_bp.route("/clients/<int:client_id_pk>", methods=["PUT"])
@require_api_key
def update_client(client_id_pk):
    service = _get_oauth_service()
    data = request.get_json(silent=True) or {}
    try:
        client = service.update_client(client_id_pk, **data)
        return jsonify(client.to_dict()), 200
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            return jsonify({"error": error_msg}), 404
        return jsonify({"error": error_msg}), 409


@api_bp.route("/clients/<int:client_id_pk>", methods=["DELETE"])
@require_api_key
def delete_client(client_id_pk):
    service = _get_oauth_service()
    try:
        service.delete_client(client_id_pk)
        return "", 204
    except ValueError:
        return jsonify({"error": "Client not found"}), 404
