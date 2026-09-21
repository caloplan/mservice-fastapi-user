"""超级用户自动创建（部署引导）测试。"""

import pytest
from sqlalchemy import func, select

from app.core.bootstrap import ensure_superuser
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models.user import User


def _set_superuser_config(monkeypatch, password: str = "S@fePass2026!"):
    """统一注入 superuser 配置。"""
    monkeypatch.setattr(settings, "SUPERUSER_USERNAME", "superuser")
    monkeypatch.setattr(settings, "SUPERUSER_PASSWORD", password)
    monkeypatch.setattr(settings, "SUPERUSER_EMAIL", "superuser@local.local")
    monkeypatch.setattr(settings, "SUPERUSER_FULL_NAME", "Super User")
    monkeypatch.setattr(settings, "SUPERUSER_SERVICE_NAME", "default")


@pytest.mark.asyncio
async def test_create_superuser_with_strong_password(monkeypatch):
    """配置强密码时自动创建 role=superuser 的用户，密码以哈希存储。"""
    _set_superuser_config(monkeypatch)

    async with AsyncSessionLocal() as session:
        created = await ensure_superuser(session)
        await session.commit()
    assert created is True

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == "superuser"))
        ).scalars().first()
    assert user is not None
    assert user.role == "superuser"
    assert user.service_name == "default"
    assert user.hashed_password != "S@fePass2026!"


@pytest.mark.asyncio
async def test_superuser_creation_is_idempotent(monkeypatch):
    """重复调用不重复创建。"""
    _set_superuser_config(monkeypatch)

    async with AsyncSessionLocal() as session:
        first = await ensure_superuser(session)
        await session.commit()
        second = await ensure_superuser(session)
        await session.commit()
    assert first is True
    assert second is False

    async with AsyncSessionLocal() as session:
        total = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar_one()
    assert total == 1


@pytest.mark.asyncio
async def test_skip_when_password_empty(monkeypatch):
    """SUPERUSER_PASSWORD 为空时不创建。"""
    _set_superuser_config(monkeypatch, password="")

    async with AsyncSessionLocal() as session:
        created = await ensure_superuser(session)
        await session.commit()
    assert created is False

    async with AsyncSessionLocal() as session:
        total = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar_one()
    assert total == 0


@pytest.mark.asyncio
async def test_skip_when_password_weak(monkeypatch):
    """弱口令（常见密码 / 与用户名相同）拒绝创建。"""
    _set_superuser_config(monkeypatch, password="password")
    async with AsyncSessionLocal() as session:
        assert await ensure_superuser(session) is False
        await session.commit()

    _set_superuser_config(monkeypatch, password="superuser")
    async with AsyncSessionLocal() as session:
        assert await ensure_superuser(session) is False
        await session.commit()

    async with AsyncSessionLocal() as session:
        total = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar_one()
    assert total == 0


@pytest.mark.asyncio
async def test_skip_when_username_exists(monkeypatch):
    """已存在同名用户时不重置密码、不修改角色。"""
    _set_superuser_config(monkeypatch)

    async with AsyncSessionLocal() as session:
        from app.core.security import hash_password

        existing = User(
            username="superuser",
            email="someone@example.com",
            hashed_password=hash_password("Origin@123"),
            role="user",
        )
        session.add(existing)
        await session.commit()

        created = await ensure_superuser(session)
        await session.commit()
    assert created is False

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == "superuser"))
        ).scalars().first()
    assert user is not None
    assert user.role == "user"  # 角色未被修改


@pytest.mark.asyncio
async def test_jwt_contains_role(client, monkeypatch, register_user):
    """普通用户注册 token 携带 role=user；superuser 登录 token 携带 role=superuser。"""
    register_resp = await register_user(
        username="normaluser",
        email="normal@example.com",
        full_name="Normal User",
    )
    assert register_resp.status_code == 201
    normal_payload = decode_token(register_resp.json()["access_token"])
    assert normal_payload["role"] == "user"

    _set_superuser_config(monkeypatch)
    async with AsyncSessionLocal() as session:
        await ensure_superuser(session)
        await session.commit()

    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "superuser", "password": "S@fePass2026!"},
    )
    assert login_resp.status_code == 200
    super_payload = decode_token(login_resp.json()["access_token"])
    assert super_payload["role"] == "superuser"
