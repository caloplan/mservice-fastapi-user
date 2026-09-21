"""认证 API 集成测试。"""

import pytest


@pytest.mark.asyncio
async def test_register_success(client, register_user):
    """测试用户注册成功（需邮箱验证码）。"""
    response = await register_user(email="test@example.com")
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_without_code_rejected(client, register_user):
    """注册不携带验证码被拒绝（422）。"""
    register_user  # 仅占位：复用 fixture 依赖，保证 redis/邮件 mock 就绪
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Test@1234",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_with_wrong_code(client, register_user):
    """注册携带错误验证码被拒绝（400）。"""
    await client.post(
        "/api/v1/auth/email/code",
        json={"email": "test@example.com", "scene": "register"},
    )
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Test@1234",
            "code": "000000",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_duplicate_username(client, register_user):
    """测试重复用户名注册失败。"""
    await register_user(email="test@example.com")
    response = await register_user(email="test@example.com")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client, register_user):
    """测试用户登录成功。"""
    await register_user(email="test@example.com")
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "Test@1234"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client, register_user):
    """测试错误密码登录失败。"""
    await register_user(email="test@example.com")
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "Wrong@1234"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client, register_user):
    """测试刷新令牌。"""
    register_resp = await register_user(email="test@example.com")
    refresh_token = register_resp.json()["refresh_token"]
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_refresh_token_one_time_rotation(client, register_user):
    """刷新令牌一次性轮换：使用后立即失效，重复使用被拒绝。"""
    register_resp = await register_user(email="test@example.com")
    refresh_token = register_resp.json()["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()

    # 旧 refresh token 已被消费，重复使用应被拒绝
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 401
    assert "已失效或已被使用" in response.json()["detail"]


@pytest.mark.asyncio
async def test_logout_blacklists_access_token(client, register_user):
    """登出后 access token 立即失效（黑名单）。"""
    register_resp = await register_user(email="test@example.com")
    token = register_resp.json()["access_token"]

    # 登出前可正常访问受保护接口
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    # 登出
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # 登出后同一 access token 失效
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_requires_auth(client):
    """登出需要携带 access token。"""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401
