"""Redis 客户端管理：全局单例连接池，供验证码与 Token 服务端管控使用。

使用方式：
- 生产：lifespan 启动时调用 get_redis_client()（惰性创建并连接），关闭时调用 close_redis_client()；
- 测试：直接替换本模块的 redis_client 为 mock 实现（如 FakeRedis），服务层经 get_redis_client() 获取。
"""

from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

# 全局 Redis 客户端（惰性创建）；测试中可整体替换为 FakeRedis
redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """获取全局 Redis 客户端，未初始化时按配置创建（惰性）。"""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            encoding="utf-8",
        )
    return redis_client


async def close_redis_client() -> None:
    """关闭并释放 Redis 连接池。"""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


__all__ = ["get_redis_client", "close_redis_client", "redis_client"]
