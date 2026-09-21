"""邮箱验证码服务：基于 Redis 的生成、存储、限流与校验，及网易 SMTP 邮件发送。"""

import logging
import secrets
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from hmac import compare_digest

import aiosmtplib
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# 支持的验证码场景
_SCENES = ("register", "login", "reset_password", "change_email")


def _code_key(scene: str, email: str) -> str:
    return f"verify:code:{scene}:{email}"


def _cooldown_key(scene: str, email: str) -> str:
    return f"verify:cooldown:{scene}:{email}"


def _count_key(scene: str, email: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"verify:count:{scene}:{email}:{today}"


def _attempts_key(scene: str, email: str) -> str:
    return f"verify:attempts:{scene}:{email}"


def _seconds_until_midnight() -> int:
    now = datetime.now()
    midnight = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return max(1, int((midnight - now).total_seconds()) + 1)


def _mask_email(email: str) -> str:
    """邮箱脱敏：abc***@example.com。"""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[0] if local else ''}***@{domain}"
    return f"{local[:2]}***@{domain}"


class EmailService:
    """邮箱验证码业务逻辑层。"""

    def __init__(self, redis=None) -> None:
        self.redis = redis if redis is not None else get_redis_client()

    async def send_verification_code(self, email: str, scene: str = "register") -> dict[str, str]:
        """发送邮箱验证码（含冷却与每日限额控制）。"""
        if scene not in _SCENES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的验证码场景",
            )

        # SMTP 未配置时直接返回明确错误，避免底层发信报错（不消耗验证码/冷却/当日次数）
        if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="邮件服务未配置（SMTP_USER / SMTP_PASSWORD），请联系管理员",
            )

        email_norm = email.strip().lower()
        if await self.redis.exists(_cooldown_key(scene, email_norm)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"发送过于频繁，请 {settings.VERIFY_CODE_COOLDOWN_SECONDS} 秒后再试",
            )

        count = int(await self.redis.get(_count_key(scene, email_norm)) or 0)
        if count >= settings.VERIFY_CODE_DAILY_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日发送次数已达上限",
            )

        code = f"{secrets.randbelow(10 ** settings.VERIFY_CODE_LENGTH):0{settings.VERIFY_CODE_LENGTH}d}"
        code_key = _code_key(scene, email_norm)
        await self.redis.set(code_key, code, ex=settings.VERIFY_CODE_EXPIRE_SECONDS)

        try:
            await self._deliver_email(email_norm, code)
        except Exception:
            logger.exception("邮件发送失败 email=%s", _mask_email(email_norm))
            # 发送失败回滚验证码，用户可立即重试（不消耗冷却与当日次数）
            await self.redis.delete(code_key)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="邮件发送失败，请稍后重试",
            )

        # 发送成功：累加当日次数（首次设置当日 TTL）并写入冷却标记
        new_count = await self.redis.incr(_count_key(scene, email_norm))
        if new_count == 1:
            await self.redis.expire(_count_key(scene, email_norm), _seconds_until_midnight())
        await self.redis.set(
            _cooldown_key(scene, email_norm),
            "1",
            ex=settings.VERIFY_CODE_COOLDOWN_SECONDS,
        )
        logger.info("验证码已发送 email=%s scene=%s", _mask_email(email_norm), scene)
        return {"message": "验证码已发送，请查收邮箱"}

    async def verify_code(self, email: str, scene: str, code: str) -> dict[str, bool | str]:
        """校验邮箱验证码；校验成功后立即作废（一次性使用）。"""
        if scene not in _SCENES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的验证码场景",
            )

        email_norm = email.strip().lower()
        code_key = _code_key(scene, email_norm)
        attempts_key = _attempts_key(scene, email_norm)

        saved = await self.redis.get(code_key)
        if saved is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码不存在或已过期，请重新获取",
            )

        if not compare_digest(saved, code.strip()):
            attempts = int(await self.redis.get(attempts_key) or 0) + 1
            await self.redis.set(attempts_key, attempts, ex=settings.VERIFY_CODE_EXPIRE_SECONDS)
            if attempts >= settings.VERIFY_CODE_MAX_ATTEMPTS:
                await self.redis.delete(code_key)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="验证码错误次数过多，请重新获取",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"验证码错误（剩余 {settings.VERIFY_CODE_MAX_ATTEMPTS - attempts} 次机会）",
            )

        # 校验成功：一次性作废
        await self.redis.delete(code_key, attempts_key)
        logger.info("验证码校验通过 email=%s scene=%s", _mask_email(email_norm), scene)
        return {"verified": True, "message": "验证码校验通过"}

    async def _deliver_email(self, to: str, code: str) -> None:
        """通过网易 SMTP 发送验证码邮件（测试中可替换该方法以拦截真实发信）。"""
        # 双保险：防止 SMTP_USER 为空时 formataddr 生成 "名称 <>" 非法地址
        if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            raise RuntimeError("SMTP 未配置：SMTP_USER / SMTP_PASSWORD 为空")

        subject = f"[{settings.APP_NAME}] 邮箱验证码"
        expire_minutes = settings.VERIFY_CODE_EXPIRE_SECONDS // 60
        text = (
            f"您的邮箱验证码为：{code}，{expire_minutes} 分钟内有效。"
            "请勿将验证码告知他人。如非本人操作，请忽略本邮件。"
        )
        html = (
            f'<div style="font-family:sans-serif;max-width:480px;margin:0 auto;'
            f'padding:24px;border:1px solid #e5e7eb;border-radius:8px;">'
            f'<h2 style="margin:0 0 16px;color:#111827;">{settings.APP_NAME}</h2>'
            f'<p style="color:#374151;">您的邮箱验证码为：</p>'
            f'<p style="font-size:28px;font-weight:700;letter-spacing:4px;color:#2563eb;">{code}</p>'
            f'<p style="color:#6b7280;font-size:13px;">{expire_minutes} 分钟内有效，请勿泄露给他人。</p>'
            f"</div>"
        )

        message = EmailMessage()
        message["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_USER))
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_USE_TLS,
            timeout=settings.SMTP_TIMEOUT,
        )


__all__ = ["EmailService"]
