from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.proxy.log_proxy import LogProxy
from app.repositories.user_repository import UserRepository
from app.schemas.token import TokenResponse
from app.schemas.user import UserCreate
from app.services.email_service import EmailService
from app.services.token_service import TokenService
from app.services.user_service import UserService


class AuthService:
    """认证业务逻辑层。"""

    def __init__(self, db: AsyncSession, redis=None) -> None:
        self.db = db
        self.repo: UserRepository = LogProxy(UserRepository(db))  # type: ignore[assignment]
        self.user_service = UserService(db)
        self.token_service = TokenService(redis)
        self.email_service = EmailService(redis)

    async def register(self, user_data: UserCreate) -> TokenResponse:
        """用户注册：先校验邮箱验证码（一次性），成功后返回令牌。"""
        # 验证码校验通过即作废；失败抛 400，不创建用户
        await self.email_service.verify_code(user_data.email, "register", user_data.code)
        user = await self.user_service.create_user(user_data)
        return await self._issue_tokens(user)

    async def login(self, username: str, password: str) -> TokenResponse:
        """用户登录（用户名或邮箱）。"""
        user = await self.repo.get_by_username(username)
        if user is None:
            user = await self.repo.get_by_email(username)

        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户已被删除",
            )

        await self.repo.update_last_login(user)
        return await self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """使用刷新令牌换取新的访问令牌（一次性轮换）。

        刷新令牌在 Redis 白名单中登记；每次刷新都会消费旧令牌并签发新令牌对，
        旧 refresh token 一经使用即失效，重复使用会被拒绝。
        """
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="刷新令牌无效或已过期",
            )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌类型错误",
            )

        jti = payload.get("jti")
        if not jti or not await self.token_service.consume_refresh_token(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="刷新令牌已失效或已被使用，请重新登录",
            )

        user_id = payload.get("user_id")
        user = await self.repo.get_by_id(user_id)
        if user is None or user.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在",
            )
        return await self._issue_tokens(user)

    async def logout(self, access_token: str) -> None:
        """登出：将 access token 加入黑名单，直到其自然过期。"""
        try:
            payload = decode_token(access_token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="访问令牌无效或已过期",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌类型错误",
                headers={"WWW-Authenticate": "Bearer"},
            )

        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            ttl = max(0, int(exp) - int(datetime.now(timezone.utc).timestamp()))
            await self.token_service.blacklist_access_token(jti, ttl)

    async def send_email_code(self, email: str, scene: str = "register") -> dict[str, str]:
        """发送邮箱验证码。"""
        return await self.email_service.send_verification_code(email, scene)

    async def verify_email_code(self, email: str, scene: str, code: str) -> dict[str, bool | str]:
        """校验邮箱验证码。"""
        return await self.email_service.verify_code(email, scene, code)

    async def _issue_tokens(self, user: User) -> TokenResponse:
        """为用户签发访问令牌和刷新令牌，并将 refresh token 登记到 Redis 白名单。"""
        access_jti = uuid4().hex
        refresh_jti = uuid4().hex
        access_token = create_access_token(
            subject=user.username,
            user_id=user.id,
            service_name=user.service_name,
            role=user.role,
            jti=access_jti,
        )
        refresh_token = create_refresh_token(
            subject=user.username,
            user_id=user.id,
            service_name=user.service_name,
            role=user.role,
            jti=refresh_jti,
        )
        await self.token_service.store_refresh_token(
            refresh_jti,
            user.id,
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
