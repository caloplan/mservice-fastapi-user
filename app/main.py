import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.bootstrap import init_superuser
from app.core.config import settings
from app.core.database import init_db
from app.core.redis_client import close_redis_client, get_redis_client
from app.core.security import get_jwks, key_manager
from app.utils.logger import setup_logger


async def _rotation_loop(logger) -> None:
    """后台任务：定期检查并执行 JWT 密钥轮换 / 旧公钥清理。"""
    interval_seconds = settings.JWT_ROTATION_CHECK_HOURS * 3600
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            if key_manager.check_rotation():
                logger.info("JWT 密钥已轮换，当前 kid=%s", key_manager.current_kid)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("JWT 密钥轮换检查失败")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库并启动密钥轮换任务，关闭时清理资源。"""
    logger = setup_logger()
    logger.info("正在启动 %s v%s (env=%s)", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)
    logger.info("JWT 当前签名 kid=%s，活跃公钥=%s", key_manager.current_kid, key_manager.get_active_kids())
    await init_db()
    logger.info("数据库初始化完成")

    if await init_superuser():
        logger.info("超级用户初始化完成（已自动创建）")
    else:
        logger.info("超级用户初始化：跳过（未配置 / 已存在 / 密码强度不足）")

    rotation_task = asyncio.create_task(_rotation_loop(logger))
    logger.info(
        "JWT 密钥轮换后台任务已启动（每 %s 小时检查一次）",
        settings.JWT_ROTATION_CHECK_HOURS,
    )

    # Redis：验证码与 Token 服务端管控的存储后端
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        logger.info("Redis 连接成功（%s）", settings.REDIS_URL)
    except Exception:
        logger.warning("Redis 连接失败（%s），验证码与 Token 服务端管控功能将不可用", settings.REDIS_URL)

    try:
        yield
    finally:
        rotation_task.cancel()
        await close_redis_client()
        logger.info("应用已关闭")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="基于 FastAPI 的用户微服务，提供完整的认证、授权和用户管理功能。",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 路由
    app.include_router(api_router)

    # 健康检查
    @app.get("/health", tags=["系统"], summary="健康检查")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "service": settings.APP_NAME, "version": settings.APP_VERSION}

    @app.get("/", tags=["系统"], summary="服务信息")
    async def root() -> dict[str, str]:
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/health",
            "jwks": "/.well-known/jwks.json",
        }

    # JWT 公钥（JWKS），供其他服务获取公钥验证本服务签发的令牌（可能包含多个 kid）
    @app.get("/.well-known/jwks.json", tags=["系统"], summary="JWT 公钥（JWKS）")
    async def jwks() -> dict:
        return get_jwks()

    return app


app = create_app()
