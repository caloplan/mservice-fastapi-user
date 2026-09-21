from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import oauth2_scheme
from app.schemas.email import EmailCodeRequest, EmailCodeVerifyRequest
from app.schemas.token import RefreshTokenRequest, TokenResponse
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=TokenResponse, status_code=201, summary="用户注册")
async def register(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """注册新用户并返回 JWT 令牌。"""
    auth_service = AuthService(db)
    return await auth_service.register(user_data)


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """使用用户名（或邮箱）和密码登录，返回 JWT 令牌。"""
    auth_service = AuthService(db)
    return await auth_service.login(username=form_data.username, password=form_data.password)


@router.post("/refresh", response_model=TokenResponse, summary="刷新访问令牌")
async def refresh_token(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """使用刷新令牌换取新的访问令牌（旧刷新令牌一次性作废）。"""
    auth_service = AuthService(db)
    return await auth_service.refresh(data.refresh_token)


@router.post("/logout", status_code=204, summary="用户登出")
async def logout(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """登出：将当前访问令牌加入黑名单，登出后立即失效。"""
    auth_service = AuthService(db)
    await auth_service.logout(token)


@router.post("/email/code", summary="发送邮箱验证码")
async def send_email_code(
    data: EmailCodeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """向指定邮箱发送验证码（受冷却与每日限额限制）。"""
    auth_service = AuthService(db)
    return await auth_service.send_email_code(data.email, data.scene)


@router.post("/email/verify", summary="校验邮箱验证码")
async def verify_email_code(
    data: EmailCodeVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool | str]:
    """校验验证码；校验成功后验证码一次性作废。"""
    auth_service = AuthService(db)
    return await auth_service.verify_email_code(data.email, data.scene, data.code)
