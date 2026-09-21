"""Pytest 共享 fixtures。"""

import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.core.redis_client as redis_module
from app.core.config import settings
from app.core.database import Base, engine
from app.main import app
from app.services.email_service import EmailService


class FakeRedis:
    """测试用内存 Redis 实现（覆盖服务层用到的 get/set/delete/exists/incr/expire）。"""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._expires: dict[str, float] = {}

    def _purge(self) -> None:
        now = time.monotonic()
        for key in [k for k, exp in self._expires.items() if exp <= now]:
            self._data.pop(key, None)
            self._expires.pop(key, None)

    async def get(self, key: str) -> str | None:
        self._purge()
        return self._data.get(key)

    async def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self._data[key] = str(value)
        if ex is not None:
            self._expires[key] = time.monotonic() + ex
        return True

    async def delete(self, *keys: str) -> int:
        self._purge()
        deleted = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                self._expires.pop(key, None)
                deleted += 1
        return deleted

    async def exists(self, *keys: str) -> int:
        self._purge()
        return sum(1 for key in keys if key in self._data)

    async def incr(self, key: str) -> int:
        self._purge()
        value = int(self._data.get(key, 0)) + 1
        self._data[key] = str(value)
        return value

    async def expire(self, key: str, ttl: int) -> bool:
        if key in self._data:
            self._expires[key] = time.monotonic() + ttl
            return True
        return False


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """每个测试前重建数据库表。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _fake_deliver(self, to: str, code: str) -> None:
    """拦截真实 SMTP 发信。"""
    return None


@pytest.fixture(autouse=True)
def _smtp_configured(monkeypatch):
    """测试环境视为 SMTP 已配置（真实发信已被 _deliver_email 拦截）。

    需验证「未配置 SMTP 返回 503」的测试可在用例内显式 monkeypatch 回空值覆盖本设置。
    """
    monkeypatch.setattr(settings, "SMTP_USER", "test@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "test-password")


@pytest_asyncio.fixture(autouse=True)
async def setup_redis():
    """每个测试前将全局 Redis 客户端替换为内存实现。"""
    fake = FakeRedis()
    redis_module.redis_client = fake
    yield fake
    redis_module.redis_client = None


@pytest_asyncio.fixture
async def register_user(client, monkeypatch, setup_redis):
    """注册辅助：mock 邮件发送 → 发送邮箱验证码 → 取码 → 调用注册接口。

    返回闭包 _register(**overrides)，overrides 可覆盖 username/email/password/code 等字段。
    """
    monkeypatch.setattr(EmailService, "_deliver_email", _fake_deliver)

    async def _register(**overrides):
        email = overrides.pop("email", "test@example.com")
        code = await setup_redis.get(f"verify:code:register:{email}")
        if code is None:
            # 验证码可能已被消费或未发送：清理冷却后重新发送（测试环境跳过真实 60s 冷却）
            await setup_redis.delete(f"verify:cooldown:register:{email}")
            resp = await client.post(
                "/api/v1/auth/email/code",
                json={"email": email, "scene": "register"},
            )
            assert resp.status_code == 200, resp.text
            code = await setup_redis.get(f"verify:code:register:{email}")
        payload = {
            "username": "testuser",
            "email": email,
            "password": "Test@1234",
            "code": code,
        }
        payload.update(overrides)
        return await client.post("/api/v1/auth/register", json=payload)

    return _register


@pytest_asyncio.fixture
async def client():
    """提供异步测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
