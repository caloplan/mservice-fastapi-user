"""邮箱验证码 API 集成测试（mock 邮件发送，不真实发信）。"""

from datetime import datetime

import pytest

from app.core.config import settings
from app.services.email_service import EmailService


async def _fake_deliver(self, to: str, code: str) -> None:
    """拦截真实 SMTP 发信。"""
    return None


def _count_key(email: str) -> str:
    return f"verify:count:register:{email}:{datetime.now().strftime('%Y-%m-%d')}"


@pytest.mark.asyncio
async def test_send_code_success(client, monkeypatch, setup_redis):
    """发送验证码成功，并写入 Redis。"""
    monkeypatch.setattr(EmailService, "_deliver_email", _fake_deliver)
    response = await client.post(
        "/api/v1/auth/email/code",
        json={"email": "test@example.com", "scene": "register"},
    )
    assert response.status_code == 200
    assert "验证码已发送" in response.json()["message"]
    code = await setup_redis.get("verify:code:register:test@example.com")
    assert code is not None and len(code) == 6 and code.isdigit()


@pytest.mark.asyncio
async def test_send_code_cooldown(client, monkeypatch):
    """冷却期内重复发送被拒绝。"""
    monkeypatch.setattr(EmailService, "_deliver_email", _fake_deliver)
    await client.post("/api/v1/auth/email/code", json={"email": "test@example.com"})
    response = await client.post("/api/v1/auth/email/code", json={"email": "test@example.com"})
    assert response.status_code == 429
    assert "频繁" in response.json()["detail"]


@pytest.mark.asyncio
async def test_send_code_daily_limit(client, monkeypatch, setup_redis):
    """当日发送次数达到上限后被拒绝。"""
    monkeypatch.setattr(EmailService, "_deliver_email", _fake_deliver)
    await setup_redis.set(_count_key("test@example.com"), "10")
    response = await client.post(
        "/api/v1/auth/email/code",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 429
    assert "上限" in response.json()["detail"]


@pytest.mark.asyncio
async def test_verify_code_success_and_one_time(client, monkeypatch, setup_redis):
    """验证码校验成功且一次性作废。"""
    monkeypatch.setattr(EmailService, "_deliver_email", _fake_deliver)
    await client.post("/api/v1/auth/email/code", json={"email": "test@example.com"})
    code = await setup_redis.get("verify:code:register:test@example.com")

    response = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "test@example.com", "code": code},
    )
    assert response.status_code == 200
    assert response.json()["verified"] is True

    # 同一验证码再次校验应失败（已作废）
    response = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "test@example.com", "code": code},
    )
    assert response.status_code == 400
    assert "不存在或已过期" in response.json()["detail"]


@pytest.mark.asyncio
async def test_verify_code_wrong_and_lock(client, monkeypatch, setup_redis):
    """错误验证码累计失败次数，超限后锁定并作废。"""
    monkeypatch.setattr(EmailService, "_deliver_email", _fake_deliver)
    await client.post("/api/v1/auth/email/code", json={"email": "test@example.com"})

    for _ in range(4):
        response = await client.post(
            "/api/v1/auth/email/verify",
            json={"email": "test@example.com", "code": "000000"},
        )
        assert response.status_code == 400
        assert "验证码错误" in response.json()["detail"]

    # 第 5 次错误 → 次数超限并作废
    response = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "test@example.com", "code": "000000"},
    )
    assert response.status_code == 400
    assert "次数过多" in response.json()["detail"]


@pytest.mark.asyncio
async def test_verify_code_not_exists(client):
    """未发送过验证码时校验被拒绝。"""
    response = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "test@example.com", "code": "123456"},
    )
    assert response.status_code == 400
    assert "不存在或已过期" in response.json()["detail"]


@pytest.mark.asyncio
async def test_send_code_invalid_scene(client, monkeypatch):
    """不支持的验证码场景被拒绝。"""
    monkeypatch.setattr(EmailService, "_deliver_email", _fake_deliver)
    response = await client.post(
        "/api/v1/auth/email/code",
        json={"email": "test@example.com", "scene": "unknown"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_send_code_smtp_not_configured(client, monkeypatch, setup_redis):
    """SMTP_USER / SMTP_PASSWORD 未配置时返回 503 明确配置错误（而非底层发信 502）。"""
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    response = await client.post(
        "/api/v1/auth/email/code",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 503
    assert "邮件服务未配置" in response.json()["detail"]
    # 未消耗任何 Redis 状态（不写验证码、不写冷却）
    assert await setup_redis.get("verify:code:register:test@example.com") is None
    assert await setup_redis.exists("verify:cooldown:register:test@example.com") == 0
