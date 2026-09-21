"""用户管理 API 集成测试。"""

import pytest


@pytest.mark.asyncio
async def test_get_me(client, register_user):
    """测试获取当前用户信息。"""
    register_resp = await register_user(
        email="test@example.com",
        full_name="Test User",
        service_name="default",
    )
    token = register_resp.json()["access_token"]
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert data["service_name"] == "default"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client):
    """测试未认证访问 /me 失败。"""
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_me(client, register_user):
    """测试更新当前用户信息。"""
    register_resp = await register_user(email="test@example.com", service_name="default")
    token = register_resp.json()["access_token"]
    response = await client.put(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "Updated Name", "service_name": "forum"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name"
    assert data["service_name"] == "forum"


@pytest.mark.asyncio
async def test_change_password(client, register_user):
    """测试修改密码。"""
    register_resp = await register_user(email="test@example.com", service_name="default")
    token = register_resp.json()["access_token"]
    response = await client.post(
        "/api/v1/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "Test@1234", "new_password": "New@12345"},
    )
    assert response.status_code == 204

    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "New@12345"},
    )
    assert login_resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_me(client, register_user):
    """测试软删除用户。"""
    register_resp = await register_user(email="test@example.com", service_name="default")
    token = register_resp.json()["access_token"]
    response = await client.delete(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "Test@1234"},
    )
    assert login_resp.status_code == 401


@pytest.mark.asyncio
async def test_get_user_by_id(client, register_user):
    """测试按 ID 获取用户。"""
    register_resp = await register_user(email="test@example.com")
    token = register_resp.json()["access_token"]
    response = await client.get(
        "/api/v1/users/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_list_users(client, register_user):
    """测试获取用户列表。"""
    for i in range(3):
        await register_user(
            username=f"user{i}",
            email=f"user{i}@example.com",
            service_name="default",
        )
    register_resp = await register_user(
        username="adminuser",
        email="admin@example.com",
        service_name="default",
    )
    token = register_resp.json()["access_token"]
    response = await client.get(
        "/api/v1/users?skip=0&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert len(data["items"]) == 4
