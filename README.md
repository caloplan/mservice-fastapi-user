# User Service - 用户微服务

基于 FastAPI 的用户微服务，提供完整的认证、授权和用户管理功能。JWT 采用 RS256 非对称签名并支持自动密钥轮换，公钥通过 JWKS 端点公开供其他微服务验证。
## 相关项目（CaloPlan 全家桶）

CaloPlan 全栈项目统一托管在 GitHub Organization [caloplan](https://github.com/caloplan)：

| 类型 | 项目 | 与本项目关系 |
| --- | --- | --- |
| 前端 | [coloplan-v2](https://github.com/caloplan/coloplan-v2) | 客户端（登录 / Account 页） |
| SDK | [caloplan-core](https://github.com/caloplan/caloplan-core) | 业务核心（兄弟模块） |
| SDK | [caloplan-user](https://github.com/caloplan/caloplan-user) | 用户模块 SDK（对接本服务） |
| SDK | [caloplan-chat](https://github.com/caloplan/caloplan-chat) | AI 对话 SDK（Token 来源） |
| SDK | [caloplan-cache](https://github.com/caloplan/caloplan-cache) | 通用缓存（Token 持久化） |
| 服务 | [fastapi-chat-service](https://github.com/caloplan/fastapi-chat-service) | AI 对话微服务（消费本服务 JWT） |
| 服务 | [fastapi-file-service](https://github.com/caloplan/fastapi-file-service) | 图片上传微服务（消费本服务 JWT） |
| 服务 | [mservice-fastapi-metastorage](https://github.com/caloplan/mservice-fastapi-metastorage) | 元数据微服务（消费本服务 JWT） |
| 服务（本仓库） | [mservice-fastapi-user](https://github.com/caloplan/mservice-fastapi-user) | 认证 / 用户微服务 |

本服务是全家桶的认证底座：签发 RS256 JWT 并通过 JWKS 公开公钥，所有兄弟微服务（chat / file / metastorage）均消费本服务令牌。

## 技术栈

- **FastAPI** - 异步 Web 框架
- **SQLAlchemy 2.0 (Async)** - 异步 ORM
- **SQLite (aiosqlite)** - 数据库
- **Pydantic v2** - 数据验证
- **JWT (python-jose)** - 令牌认证（RS256 + 自动密钥轮换）
- **Passlib (bcrypt)** - 密码哈希
- **Log Proxy** - 操作日志代理模式

## 项目结构

```
app/
├── main.py                          # 应用入口（lifespan 启动密钥轮换后台任务）
├── core/
│   ├── config.py                    # 配置管理（含 REGISTERED_SERVICES 可注册业务列表）
│   ├── database.py                  # SQLite 异步连接
│   ├── security.py                  # JWT + 密码加密
│   ├── key_manager.py               # JWT 密钥管理（kid 生成、轮换、多 key JWKS）
│   └── dependencies.py              # 认证依赖
├── models/
│   └── user.py                      # User 主表模型
├── schemas/                         # Pydantic 模型
│   ├── user.py                      # 用户请求/响应
│   └── token.py                     # Token 模型
├── repositories/
│   └── user_repository.py           # 主表 CRUD
├── services/
│   ├── user_service.py              # 用户业务逻辑
│   └── auth_service.py              # 认证业务逻辑
├── api/v1/routes/
│   ├── auth.py                      # 认证路由
│   └── users.py                     # 用户路由
├── proxy/
│   └── log_proxy.py                 # Log Proxy 日志代理
└── utils/
    └── logger.py                    # 日志配置
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements-dev.txt   # 开发：含热重载与测试依赖
# 生产部署仅需：pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，配置 JWT_PRIVATE_KEY / JWT_PUBLIC_KEY（密钥路径或 PEM 字符串）等
```

### 3. 生成 JWT 密钥（RS256 非对称）

```bash
python scripts/generate_jwt_keys.py
```

生成：
- `keys/jwt_private.pem`：**私钥**，仅保留在 user-service，严禁提交仓库（已加入 `.gitignore`）；
- `keys/jwt_public.pem`：**公钥**，可分发给任何需要校验 JWT 的兄弟服务。

> 首次启动时会自动导入该密钥并分配 kid，后续轮换由后台任务完成。

### 4. 运行服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 访问 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 端点

### 认证 (`/api/v1/auth`)

| 方法 | 端点 | 功能 | 认证 |
|------|------|------|------|
| POST | `/register` | 用户注册 | 否 |
| POST | `/login` | 用户登录（返回 JWT） | 否 |
| POST | `/refresh` | 刷新令牌 | 否 |
| POST | `/logout` | 用户登出 | 是 |

### 用户管理 (`/api/v1/users`)

| 方法 | 端点 | 功能 | 认证 |
|------|------|------|------|
| GET | `/me` | 获取当前用户 | 是 |
| PUT | `/me` | 更新当前用户 | 是 |
| POST | `/me/change-password` | 修改密码 | 是 |
| DELETE | `/me` | 软删除用户 | 是 |
| GET | `/{user_id}` | 获取指定用户 | 是 |
| GET | `/` | 用户列表（支持按 `service_name` 筛选） | 是 |

### 系统

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/` | 服务信息 |
| GET | `/.well-known/jwks.json` | JWT 公钥（JWKS，多 kid） |

## 用户模型

### 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer | 主键，自增 |
| `username` | String(50) | 用户名，唯一 |
| `email` | String(100) | 邮箱，唯一 |
| `hashed_password` | String(255) | bcrypt 密码哈希 |
| `full_name` | String(100) | 全名，可空 |
| `service_name` | String(50) | 业务服务标识，默认 `default` |
| `role` | String(20) | 用户角色，默认 `user`；超级用户为 `superuser` |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |
| `deleted_at` | DateTime | 删除时间（软删除） |
| `is_deleted` | Boolean | 是否软删除 |

### 注册请求示例

```json
{
  "username": "demo_user",
  "email": "demo@example.com",
  "password": "Test@1234",
  "full_name": "Demo User",
  "service_name": "default"
}
```

### 响应示例

```json
{
  "id": 1,
  "username": "demo_user",
  "email": "demo@example.com",
  "full_name": "Demo User",
  "service_name": "default",
  "role": "user",
  "created_at": "2026-09-01T00:00:00",
  "updated_at": null
}
```

## 超级用户自动创建（部署引导）

服务启动时（lifespan）会根据 `.env` 配置自动创建超级用户，用于平台级管理操作（如后续兄弟微服务的管理接口鉴权）。

### 配置项

```
SUPERUSER_USERNAME=superuser
SUPERUSER_PASSWORD=          # 为空则不创建；生产环境必须显式注入强密码
SUPERUSER_EMAIL=superuser@local.local
SUPERUSER_FULL_NAME=Super User
SUPERUSER_SERVICE_NAME=default
```

### 行为规则

- `SUPERUSER_PASSWORD` 为空 → 跳过创建（未启用该能力）；
- 密码强度不足（长度 < 8 / 常见弱口令 / 与用户名相同）→ 拒绝创建，避免默认弱口令风险；
- 用户名或邮箱已存在（含软删除）→ 跳过，不重置密码、不修改角色；
- 创建的用户 `role=superuser`，登录后签发的 JWT 携带 `role` 声明（`TokenPayload.role` 已预留），供其他兄弟微服务做权限判定。

### Docker 部署注入密码

```bash
SUPERUSER_PASSWORD='your-strong-password' docker-compose up -d --build
```

> 密码通过宿主机环境变量注入（`docker-compose.yml` 中 `${SUPERUSER_PASSWORD:-}`），请勿硬编码进仓库。

## 可注册业务列表

`user.service_name` 用于标识用户所属业务。项目预留了 `REGISTERED_SERVICES` 配置项（`.env`），专供给未来可选业务使用：

```
REGISTERED_SERVICES=["forum","shop","game"]
```

- 当前版本不实现具体业务的扩展表或专属响应格式，所有用户统一返回 `UserResponse`。
- 未来接入可选业务时，可在此列表中登记业务名，并在 `service_name` 字段中引用。
- `service_name` 字段保留在用户主表中，支持按业务筛选用户列表。

## 数据库建表

开发环境在服务启动时（lifespan）通过 `init_db` 自动建表（`Base.metadata.create_all`），无需手动迁移。若后续引入 Alembic 迁移，可在此补充。

## Docker 部署

### 1. 先在本机生成 JWT 密钥

```bash
python scripts/generate_jwt_keys.py
# 生成 keys/jwt_private.pem（私钥）与 keys/jwt_public.pem（公钥）
```

> `keys/` 目录已被 `.dockerignore` 排除，**不会烘焙进镜像**；运行时通过 `./keys:/app/keys` 卷注入。
> **务必先在宿主机生成好密钥再启动容器**。密钥目录需要**可写**，因为密钥轮换会在运行期写入新密钥和 `jwt_state.json`。

### 2. 构建并启动

```bash
docker-compose up -d --build
```

- JWT 密钥：`./keys:/app/keys` 读写挂载（轮换需写入新密钥）
- SQLite 数据库：`./data:/app/data` 卷持久化
- 日志：`./logs:/app/logs` 挂载
- 生产环境建议：私钥放入密钥管理服务（KMS / Vault / 云 Secret），通过 Secret 挂载覆盖 `JWT_PRIVATE_KEY`，公钥可分发给各兄弟服务校验

## 运行测试

```bash
pytest tests/ -v
```

测试覆盖：
- 认证 API（注册、登录、刷新、重复注册、错误密码）
- 用户管理 API（CRUD、密码修改、软删除、列表、按 service_name 筛选）
- JWT 密钥轮换（kid 生成、空目录自生成、旧 PEM 迁移、超龄轮换、旧 token 保留期可验证、到期清理、重启 kid 稳定）

## JWT 认证（RS256 非对称加密 + 自动密钥轮换）

本服务使用 **RS256 非对称算法**签发与校验 JWT，并支持**密钥自动轮换**：

- **kid**：每套 RSA 公私钥对应唯一 `kid`（RFC 7638 JWK thumbprint），JWT Header 携带 `kid`，其他服务据此选取公钥验证。
- **签发**：登录 / 注册时用**当前私钥**签名，私钥只存在于 user-service，绝不外发。
- **自动轮换**：后台定时任务（默认每 24h 检查）检查当前密钥年龄，超过 `JWT_ROTATION_INTERVAL_DAYS`（默认 30 天）自动生成新密钥并设为当前签名密钥；**旧公钥保留** `JWT_RETIRE_DAYS`（默认 8 天，≥ 最长 JWT 有效期）后自动删除。
- **JWKS 多 kid**：`GET /.well-known/jwks.json` 同时返回当前与未过期的旧公钥，验证方按 `kid` 匹配即可在轮换期间无缝过渡。
- **状态持久化**：密钥与状态仅存本地文件，无数据库依赖。

### 密钥目录结构

```
keys/
├── jwt_state.json              # 状态：当前签名 kid、各密钥创建/退役时间
├── jwt_private_<kid>.pem       # 私钥（每个 kid 一份，仅本服务持有）
├── jwt_public_<kid>.pem        # 公钥（可分发）
├── jwt_private.pem / jwt_public.pem   # 旧命名初始密钥（首次启动自动导入并分配 kid）
```

### 配置项（`.env`）

```
JWT_PRIVATE_KEY=keys/jwt_private.pem    # 首次启动迁移导入的旧 PEM（路径或 PEM 字符串）
JWT_PUBLIC_KEY=keys/jwt_public.pem
ALGORITHM=RS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_KEY_DIR=keys                         # 密钥目录
JWT_ROTATION_INTERVAL_DAYS=30            # 密钥轮换周期
JWT_RETIRE_DAYS=8                        # 旧公钥保留天数（>= 最长 JWT 有效期）
JWT_ROTATION_CHECK_HOURS=24              # 后台检查间隔（小时）
REGISTERED_SERVICES=["forum","shop","game"]  # 可注册业务列表（预留）
```

### 其他服务校验（推荐：按 kid 校验 + 未知 kid 强制刷新缓存）

```python
from jose import jwt

# 1) 从 token Header 读取 kid
kid = jwt.get_unverified_header(token)["kid"]

# 2) 本地缓存命中且包含该 kid -> 直接验证
if cached_jwks and any(k["kid"] == kid for k in cached_jwks["keys"]):
    payload = jwt.decode(token, cached_jwks["keys"], algorithms=["RS256"])
else:
    # 3) 未知 kid -> 强制刷新 JWKS 缓存后再验证（应对密钥轮换）
    cached_jwks = requests.get("http://user-service:8000/.well-known/jwks.json").json()
    payload = jwt.decode(token, cached_jwks["keys"], algorithms=["RS256"])
```

> 轮换期间 JWKS 会同时包含新旧公钥，旧 token 在保留期内仍可验证；`kid` 不在缓存中时强制刷新一次即可，无需其他协调。

## 安全特性

- 密码 bcrypt 哈希存储（12 轮）
- JWT RS256 非对称签名 + 自动密钥轮换：私钥签发、公钥校验（访问令牌 30 分钟 + 刷新令牌 7 天），JWKS 多 kid 公开供其他服务验证
- 敏感信息日志自动脱敏（password、email 等）
- CORS 来源限制
- SQL 注入防护（ORM 参数化查询）
- 输入数据验证（Pydantic）
- 软删除保留数据
- 操作日志审计（Log Proxy 模式，自动记录 Repository 层所有操作）
