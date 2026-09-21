from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，从环境变量 / .env 加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "User Service"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # 服务
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 数据库 (SQLite)
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/user_service.db"
    DATABASE_ECHO: bool = False

    # Redis（邮箱验证码 / Token 服务端管控存储）
    REDIS_URL: str = "redis://localhost:6379/0"

    # SMTP（网易邮箱发件）
    SMTP_HOST: str = "smtp.163.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""                  # 发件邮箱账号
    SMTP_PASSWORD: str = ""              # 客户端授权码（非登录密码）
    SMTP_FROM_NAME: str = "User Service" # 发件人显示名
    SMTP_USE_TLS: bool = True            # True=465 隐式 TLS；False=25 普通端口
    SMTP_TIMEOUT: int = 10

    # 邮箱验证码
    VERIFY_CODE_LENGTH: int = 6                    # 验证码位数
    VERIFY_CODE_EXPIRE_SECONDS: int = 300          # 有效期（秒）
    VERIFY_CODE_COOLDOWN_SECONDS: int = 60         # 同一邮箱重发间隔（秒）
    VERIFY_CODE_DAILY_LIMIT: int = 10              # 同一邮箱每日发送上限
    VERIFY_CODE_MAX_ATTEMPTS: int = 5              # 校验失败次数上限（超出需重新获取）

    # JWT（RS256 非对称加密：私钥签发，公钥校验）
    # JWT_PRIVATE_KEY / JWT_PUBLIC_KEY 作为首次启动的旧 PEM 迁移导入来源（路径或 PEM 字符串）
    JWT_PRIVATE_KEY: str = "keys/jwt_private.pem"
    JWT_PUBLIC_KEY: str = "keys/jwt_public.pem"
    ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # JWT 密钥轮换（本地文件管理，无需数据库）
    JWT_KEY_DIR: str = "keys"          # 密钥目录：jwt_private_<kid>.pem / jwt_public_<kid>.pem / jwt_state.json
    JWT_ROTATION_INTERVAL_DAYS: int = 30   # 当前签名密钥使用多久后轮换
    JWT_RETIRE_DAYS: int = 8               # 旧公钥保留天数（需 >= 最长 JWT 有效期，默认 7 天 refresh + 余量）
    JWT_ROTATION_CHECK_HOURS: int = 24     # 后台检查轮换的间隔（小时）

    # 可注册业务列表（预留，专供给可选业务；user.service_name 建议在此列表内）
    REGISTERED_SERVICES: List[str] = ["forum", "shop", "game"]

    # 密码
    PASSWORD_BCRYPT_ROUNDS: int = 12

    # 超级用户（部署引导：服务启动时按以下配置自动创建；SUPERUSER_PASSWORD 为空则不创建）
    SUPERUSER_USERNAME: str = "superuser"
    SUPERUSER_PASSWORD: str = ""          # 生产环境必须显式注入强密码
    SUPERUSER_EMAIL: str = "superuser@example.com"
    SUPERUSER_FULL_NAME: str = "Super User"
    SUPERUSER_SERVICE_NAME: str = "default"

    # 日志
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/user_service.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # 日志操作类型
    LOG_OPERATIONS: List[str] = [
        "user_create",
        "user_update",
        "user_delete",
        "user_login",
        "user_logout",
        "password_change",
        "user_status_change",
        "role_change",
    ]

    @field_validator("ALLOWED_ORIGINS", "LOG_OPERATIONS", "REGISTERED_SERVICES", mode="before")
    @classmethod
    def _parse_list(cls, v):
        """支持从 .env 读取 JSON 数组字符串。"""
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [item.strip() for item in v.split(",") if item.strip()]
        return v


settings = Settings()
