import pytest
from app import create_app
from app.models import db, OAuth2Client

from app.config import TestConfig

@pytest.fixture
def app():
    # 테스트용 설정 클래스 커스텀
    class MyTestConfig(TestConfig):
        DEFAULT_CLIENT_ID = "test-client"
        DEFAULT_CLIENT_SECRET = "test-secret"
        DEFAULT_REDIRECT_URI = "http://localhost/callback"
        APP_TITLE = "IDP TEST"

    app = create_app(MyTestConfig)
    with app.app_context():
        # db.create_all()은 factory 내에서 수행되므로 여기서는 추가 작업 불필요
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_create_client_api(client):
    """API를 통한 클라이언트 생성 테스트"""
    data = {
        "client_id": "new-api-client",
        "client_secret": "test-secret",
        "client_name": "Test Application",
        "redirect_uris": "http://localhost/callback"
    }
    response = client.post("/api/clients", json=data)
    assert response.status_code == 201
    assert response.json["client_id"] == "new-api-client"
    assert response.json["client_name"] == "Test Application"

def test_duplicate_client_id_error(client):
    """클라이언트 ID 중복 시 에러 처리 테스트"""
    data = {
        "client_id": "dup-client",
        "client_secret": "s",
        "client_name": "N",
        "redirect_uris": "http://l"
    }
    client.post("/api/clients", json=data)
    response = client.post("/api/clients", json=data)
    assert response.status_code == 409
    assert "already exists" in response.json["error"]

def test_get_client_list_api(client):
    """클라이언트 목록 조회 API 테스트"""
    client.post("/api/clients", json={
        "client_id": "c1", "client_secret": "s", "client_name": "N1", "redirect_uris": "r"
    })
    client.post("/api/clients", json={
        "client_id": "c2", "client_secret": "s", "client_name": "N2", "redirect_uris": "r"
    })
    
    response = client.get("/api/clients")
    assert response.status_code == 200
    assert len(response.json) >= 2

def test_update_client_api(client):
    """클라이언트 정보 수정 API 테스트"""
    # 생성
    res = client.post("/api/clients", json={
        "client_id": "orig", "client_secret": "s", "client_name": "Original", "redirect_uris": "r"
    })
    pk = res.json["id"]
    
    # 수정
    update_data = {"client_name": "Updated Name", "client_id": "new-id"}
    response = client.put(f"/api/clients/{pk}", json=update_data)
    assert response.status_code == 200
    assert response.json["client_name"] == "Updated Name"
    assert response.json["client_id"] == "new-id"

def test_delete_client_api(client):
    """클라이언트 삭제 API 테스트"""
    res = client.post("/api/clients", json={
        "client_id": "del-me", "client_secret": "s", "client_name": "D", "redirect_uris": "r"
    })
    pk = res.json["id"]
    
    # 삭제
    response = client.delete(f"/api/clients/{pk}")
    assert response.status_code == 204
    
    # 확인
    response = client.get(f"/api/clients/{pk}")
    assert response.status_code == 404
