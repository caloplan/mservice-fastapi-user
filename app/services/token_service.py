"""Token 服务端管控：refresh 白名单（一次性轮换）与 access 登出黑名单，均存储于 Redis。"""

import logging

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def _refresh_key(jti: str) -> str:
    return f"token:refresh:{jti}"


def _blacklist_key(jti: str) -> str:
    return f"token:blacklist:{jti}"


class TokenService:
    """Token 生命周期管理（Redis 存储）。

    - refresh token：签发时写入白名单，刷新时一次性消费（删除），实现轮换；
    - access token：登出时写入黑名单，TTL 为其剩余有效期，实现登出即失效。
    """

    def __init__(self, redis=None) -> None:
        self.redis = redis if redis is not None else get_redis_client()

    async def store_refresh_token(self, jti: str, user_id: int, ttl_seconds: int) -> None:
        """签发 refresh token 后登记白名单。"""
        await self.redis.set(_refresh_key(jti), user_id, ex=ttl_seconds)

    async def consume_refresh_token(self, jti: str) -> bool:
        """一次性消费 refresh token；存在则删除并返回 True，已被使用/不存在返回 False。"""
        deleted = await self.redis.delete(_refresh_key(jti))
        return deleted > 0

    async def blacklist_access_token(self, jti: str, ttl_seconds: int) -> None:
        """登出：将 access token 加入黑名单，TTL 为 token 剩余有效期。"""
        if ttl_seconds <= 0:
            return
        await self.redis.set(_blacklist_key(jti), "1", ex=ttl_seconds)

    async def is_access_blacklisted(self, jti: str) -> bool:
        """判断 access token 是否已被登出（黑名单）。"""
        return await self.redis.exists(_blacklist_key(jti)) > 0


__all__ = ["TokenService"]
