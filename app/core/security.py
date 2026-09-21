from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.key_manager import KeyManager

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.PASSWORD_BCRYPT_ROUNDS,
)

# RS256 非对称 + 自动轮换：私钥仅用于签发（保留在 user-service），公钥可对外分发校验。
# 旧 PEM（JWT_PRIVATE_KEY / JWT_PUBLIC_KEY）作为首次启动的迁移导入来源。
key_manager = KeyManager(
    key_dir=settings.JWT_KEY_DIR,
    rotation_interval_days=settings.JWT_ROTATION_INTERVAL_DAYS,
    retire_days=settings.JWT_RETIRE_DAYS,
    legacy_private=settings.JWT_PRIVATE_KEY,
    legacy_public=settings.JWT_PUBLIC_KEY,
)


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希值是否匹配。"""
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str,
    user_id: int,
    service_name: str,
    role: str,
    expires_delta: timedelta,
    token_type: str,
    jti: str | None = None,
) -> str:
    """使用当前签名密钥生成 JWT 令牌（Header 携带 kid，payload 携带 jti）。"""
    expire = datetime.now(timezone.utc) + expires_delta
    payload: dict[str, Any] = {
        "sub": subject,
        "user_id": user_id,
        "service_name": service_name,
        "role": role,
        "type": token_type,
        "jti": jti or uuid4().hex,
        "exp": expire,
    }
    kid, private_key = key_manager.get_signing_key()
    return jwt.encode(
        payload,
        private_key,
        algorithm=settings.ALGORITHM,
        headers={"kid": kid},
    )


def create_access_token(
    subject: str,
    user_id: int,
    service_name: str,
    role: str,
    jti: str | None = None,
) -> str:
    """生成访问令牌（默认 30 分钟）。"""
    return _create_token(
        subject=subject,
        user_id=user_id,
        service_name=service_name,
        role=role,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
        jti=jti,
    )


def create_refresh_token(
    subject: str,
    user_id: int,
    service_name: str,
    role: str,
    jti: str | None = None,
) -> str:
    """生成刷新令牌（默认 7 天）。"""
    return _create_token(
        subject=subject,
        user_id=user_id,
        service_name=service_name,
        role=role,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
        jti=jti,
    )


def _kid_from_token(token: str) -> str | None:
    """读取 JWT Header 中的 kid；解析失败返回 None。"""
    try:
        return jwt.get_unverified_header(token).get("kid")
    except Exception:
        return None


def decode_token(token: str) -> dict[str, Any]:
    """使用对应 kid 的公钥解码并校验 JWT，失败抛出 JWTError。"""
    kid = _kid_from_token(token)
    if kid is not None:
        public_key = key_manager.get_public_key(kid)
        if public_key is None:
            raise JWTError(f"未知的 kid: {kid}")
    else:
        # 兼容旧的无 kid 令牌：用当前签名公钥校验
        public_key = key_manager.get_public_key(key_manager.current_kid)
    return jwt.decode(token, public_key, algorithms=[settings.ALGORITHM])


def get_jwks() -> dict[str, Any]:
    """返回 JWKS：包含当前与未过期的旧公钥（多 kid），供其他服务按 kid 验证。"""
    return key_manager.get_jwks(algorithm=settings.ALGORITHM)


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_jwks",
    "key_manager",
    "JWTError",
]
