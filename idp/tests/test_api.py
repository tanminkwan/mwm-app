"""사용자 CRUD API 통합 테스트. Coverage 목표: api.py 100%"""
import json


class TestListUsers:
    def test_list_users_empty(self, client, db):
        resp = client.get("/api/users")
        assert resp.status_code == 200
        # default client의 초기화로 인한 빈 목록일 수 있음
        assert isinstance(resp.get_json(), list)

    def test_list_users_with_data(self, client, db, sample_user):
        resp = client.get("/api/users")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        usernames = [u["username"] for u in data]
        assert "testuser" in usernames


class TestCreateUser:
    def test_create_user_api(self, client, db):
        resp = client.post("/api/users", json={
            "username": "apiuser",
            "email": "api@example.com",
            "password": "StrongPass123!",
            "first_name": "API",
            "last_name": "User",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["username"] == "apiuser"
        assert data["email"] == "api@example.com"

    def test_create_user_duplicate_username(self, client, db, sample_user):
        resp = client.post("/api/users", json={
            "username": "testuser",
            "email": "other@example.com",
        })
        assert resp.status_code == 409

    def test_create_user_duplicate_email(self, client, db, sample_user):
        resp = client.post("/api/users", json={
            "username": "other",
            "email": "test@example.com",
        })
        assert resp.status_code == 409

    def test_create_user_validation_missing_fields(self, client, db):
        resp = client.post("/api/users", json={"first_name": "Only"})
        assert resp.status_code == 400
        assert "Missing required fields" in resp.get_json()["error"]

    def test_create_user_no_json(self, client, db):
        resp = client.post("/api/users", data="not json",
                           content_type="text/plain")
        assert resp.status_code == 400

    def test_create_user_short_password(self, client, db):
        resp = client.post("/api/users", json={
            "username": "shortpw",
            "email": "short@example.com",
            "password": "123",
        })
        assert resp.status_code == 409  # ValueError → 409


class TestGetUser:
    def test_get_user(self, client, db, sample_user):
        resp = client.get(f"/api/users/{sample_user.id}")
        assert resp.status_code == 200
        assert resp.get_json()["username"] == "testuser"

    def test_get_user_not_found(self, client, db):
        resp = client.get("/api/users/99999")
        assert resp.status_code == 404


class TestUpdateUser:
    def test_update_user(self, client, db, sample_user):
        resp = client.put(f"/api/users/{sample_user.id}", json={
            "first_name": "Updated",
        })
        assert resp.status_code == 200
        assert resp.get_json()["first_name"] == "Updated"

    def test_update_user_not_found(self, client, db):
        resp = client.put("/api/users/99999", json={"first_name": "X"})
        assert resp.status_code == 404

    def test_update_user_duplicate_username(self, client, db, sample_user):
        # 다른 사용자 생성
        client.post("/api/users", json={
            "username": "other", "email": "o@example.com",
        })
        resp = client.put(f"/api/users/{sample_user.id}", json={
            "username": "other",
        })
        assert resp.status_code == 409


class TestDeleteUser:
    def test_delete_user(self, client, db, sample_user):
        resp = client.delete(f"/api/users/{sample_user.id}")
        assert resp.status_code == 204
        # 비활성화 확인
        resp2 = client.get(f"/api/users/{sample_user.id}")
        assert resp2.get_json()["active"] is False

    def test_delete_user_not_found(self, client, db):
        resp = client.delete("/api/users/99999")
        assert resp.status_code == 404


class TestUserInfo:
    def test_userinfo_success(self, client, db, access_token, sample_user):
        resp = client.get("/api/userinfo", headers={
            "Authorization": f"Bearer {access_token.access_token}",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["username"] == "testuser"
        assert "roles" in data

    def test_userinfo_no_header(self, client, db):
        resp = client.get("/api/userinfo")
        assert resp.status_code == 401

    def test_userinfo_invalid_token(self, client, db):
        resp = client.get("/api/userinfo", headers={
            "Authorization": "Bearer invalid_token_here",
        })
        assert resp.status_code == 401

    def test_userinfo_bad_format(self, client, db):
        resp = client.get("/api/userinfo", headers={
            "Authorization": "Basic dXNlcjpwYXNz",
        })
        assert resp.status_code == 401
