# 元数据存储微服务（meta-service）开发 Prompt

> **服务端口：9093** ｜ 技术栈与工程规范严格对齐 `mservice-fastapi-user`（user-service）

---

## 前置事实（user-service 已实现，直接对接）

- user-service 已具备：JWT RS256 非对称签名 + JWKS 多 kid 自动轮换；JWT payload 携带 `role` 声明（`sub / user_id / service_name / role / type`）；部署时按 `.env` 配置自动创建 `role=superuser` 的超级用户。
- 本服务作为其**兄弟微服务**，**不签发令牌**，只消费其 JWT 做认证与权限判定。

## 定位说明

本服务**不存储文件/对象二进制本体**，只存储**结构化元数据**：业务方（forum / shop / game 等，对齐 user-service 的 `service_name` 维度）登记一种"元数据类型"（Metadata Type），然后对该类型下的实体写入/查询描述性元数据（JSON、标签、版本）。目标是可复用的通用元数据存储底座，供多个业务微服务共享。

## 一、技术栈（与参照项目现状保持一致）

- **FastAPI**（异步 Web 框架）
- **SQLAlchemy 2.0 (Async) + aiosqlite**（元数据持久化，SQLite）
- **Pydantic v2 + pydantic-settings**（数据验证 + 全局配置，从 `.env` 加载）
- **python-jose + cryptography**（JWT 校验，消费 user-service 令牌）
- **Log Proxy**（复用参照项目 `app/proxy/log_proxy.py`，Repository 层包裹自动脱敏）
- **RotatingFileHandler 轮转日志**（复用参照项目 `app/utils/logger.py` 风格）
- **pytest + pytest-asyncio + httpx**（测试）
- 依赖拆分：`requirements.txt`（生产）与 `requirements-dev.txt`（测试/热重载）；**不含 alembic**（建表走 `init_db` 自动 `create_all`，对齐参照项目现状）
- Dockerfile 使用**中科大 pip 源** `https://mirrors.ustc.edu.cn/pypi/simple/`（清华源在当前网络返回 403）

## 二、目录结构（与参照项目对齐）

```
meta-service/
├── app/
│   ├── main.py                    # 应用入口（lifespan 初始化数据库）
│   ├── core/
│   │   ├── config.py              # Settings（含 USER_SERVICE_URL / 元数据限额 / superuser 白名单）
│   │   ├── database.py            # SQLite 异步连接 + get_db/init_db
│   │   ├── security.py            # JWKS 获取/缓存 + JWT 校验
│   │   └── dependencies.py        # 认证依赖（get_current_user / require_superuser）
│   ├── models/
│   │   ├── metadata_type.py       # 元数据类型定义表
│   │   └── metadata_entry.py      # 元数据实体表（含版本）
│   ├── schemas/
│   │   ├── type.py                # 类型请求/响应
│   │   └── entry.py               # 实体元数据请求/响应
│   ├── repositories/
│   │   ├── type_repository.py     # 类型 CRUD
│   │   └── entry_repository.py    # 实体元数据 CRUD + 版本
│   ├── services/
│   │   ├── type_service.py        # 类型管理 + schema 动态校验
│   │   └── entry_service.py       # 元数据写读查/版本/回滚
│   ├── api/v1/routes/
│   │   ├── types.py               # 元数据类型路由（管理接口，仅 superuser）
│   │   └── entries.py             # 元数据实体路由（登录用户）
│   ├── proxy/
│   │   └── log_proxy.py           # 直接复用参照项目实现
│   └── utils/
│       └── logger.py              # 复用参照项目实现
├── tests/
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
└── docker-compose.yml
```

## 三、核心功能需求

1. **元数据类型管理（Metadata Type）**
   - 创建类型：`type_name`（按 service_name 唯一）、描述、**字段 schema**（JSON：字段名 → 类型/必填/可索引/默认值）
   - 列出 / 获取 / 删除类型（软删除；已有实体数据的类型禁止硬删）
   - 更新类型 schema：仅允许新增字段（向后兼容），移除或改字段类型需拒绝（422）
   - **写入时按 schema 动态校验**：运行时用 Pydantic 构造模型校验 JSON 元数据
   - ⚠️ **类型管理（POST/PUT/DELETE /types）为平台级管理操作，仅 superuser 可调用**

2. **实体元数据 CRUD（Metadata Entry）**
   - 创建：`(type_name, entity_key)` 唯一，写入 `data`（JSON）、`tags`、归属
   - 获取：按 `type_name + entity_key`，支持 `?version=` 读历史版本，默认最新
   - 更新：部分更新（deep merge），版本自增，保留历史版本（可配置上限）
   - 删除：软删除（`is_deleted`/`deleted_at`），可恢复或提供永久删除
   - 版本历史 + 回滚到指定版本

3. **查询与检索**
   - 按类型 + 字段值等于/范围/存在性过滤、tags 交集、创建时间范围
   - 分页返回 `{"total": ..., "items": [...]}`（对齐参照项目）
   - 排序；仅返回当前用户可见数据（service_name / owner 隔离）

## 四、数据模型设计方向

**MetadataType 表**：`id`、`type_name`（String(100)，索引）、`service_name`（String(50)，索引）、`description`、`schema_json`（JSON）、`created_at`/`updated_at`/`deleted_at`/`is_deleted`；唯一约束 `(type_name, service_name, is_deleted)`。

**MetadataEntry 表**：`id`、`type_id`（FK）、`entity_key`（String(255)，索引）、`data`（JSON）、`tags`（JSON 数组）、`version`（Integer 默认 1）、`service_name`（索引）、`owner_user_id`（索引）、`created_at`/`updated_at`/`deleted_at`/`is_deleted`；软删除下保证 `(type_id, entity_key)` 唯一。

**MetadataVersion 表**：`id`、`entry_id`（FK）、`version`、`data`（JSON）、`tags`（JSON）、`created_at`、`created_by_user_id`。

## 五、API 设计（前缀 `/api/v1`，服务端口 9093，全部需认证）

| 方法 | 端点 | 功能 | 权限 |
|------|------|------|------|
| POST | `/types` | 创建元数据类型 | **仅 superuser** |
| GET | `/types` | 类型列表（service_name 筛选、分页） | 登录用户 |
| GET | `/types/{type_name}` | 获取类型详情（含 schema） | 登录用户 |
| PUT | `/types/{type_name}` | 更新类型 schema | **仅 superuser** |
| DELETE | `/types/{type_name}` | 软删除类型 | **仅 superuser** |
| POST | `/entries` | 创建实体元数据 | 登录用户 |
| GET | `/entries/{type_name}/{entity_key}` | 获取元数据（支持 `?version=`） | 登录用户 |
| PUT | `/entries/{type_name}/{entity_key}` | 更新元数据（版本自增） | 登录用户 |
| DELETE | `/entries/{type_name}/{entity_key}` | 软删除元数据 | 登录用户 |
| GET | `/entries` | 查询（字段过滤 + tags + 分页 + 排序） | 登录用户 |
| GET | `/entries/{type_name}/{entity_key}/versions` | 版本历史列表 | 登录用户 |
| POST | `/entries/{type_name}/{entity_key}/rollback` | 回滚到指定版本 | 登录用户 |
| GET | `/health`、`/` | 健康检查与服务信息 | 公开 |

## 六、认证与权限（核心：对接 user-service 的 role）

- **JWT 校验**：复用参照项目 README"其他服务校验"做法——读 JWT Header `kid` → 本地 JWKS 缓存命中则验证，未命中则从 `http://user-service:8000/.well-known/jwks.json` 强制刷新后再验证（RS256），兼容密钥轮换；JWKS 缓存带 TTL（`JWKS_CACHE_TTL_SECONDS`）。
- **superuser 判定（管理接口）**：
  - **主路径**：从 JWT payload 读取 `role` 声明，`role == "superuser"` 放行 `/types` 写操作（user-service 部署时自动创建的 superuser 登录后，其 token 天然携带 `role=superuser`）；
  - **兜底路径**：JWT 无 `role` 声明时，用 `sub`/`user_id` 比对配置白名单 `SUPERUSER_USERNAMES` / `SUPERUSER_USER_IDS`（JSON 数组，从 `.env` 加载），命中视为 superuser；
  - 普通业务 token 只读 `/types`、可写 `/entries`；非 superuser 访问 `/types` 写操作统一返回 **403**。
- **资源隔离**：写入时从 JWT 提取 `user_id` 与 `service_name` 作为归属；非 owner 且非同 service_name 越权 403，列表仅返回可见数据。

## 七、安全要求

- `data` 按类型 schema 用 Pydantic 动态校验：未知字段/类型错误/超长返回 422；拒绝嵌套过深（防 ReDoS/深递归）
- `type_name`/`entity_key` 限制字符集与长度；tags 数量与单 tag 长度上限（配置可调）
- 软删除与唯一性：删除后同名 `entity_key` 可重建；查询统一过滤 `is_deleted=False`
- 日志脱敏：Repository 层统一 LogProxy 包裹，`data` 中敏感 key（password/secret/token 等，复用参照项目 SENSITIVE_FIELDS）自动脱敏
- 越权统一 403；管理接口二次鉴权（require_superuser 依赖）

## 八、工程化要求

- **配置**（`.env.example` 逐项注释）：`USER_SERVICE_URL`、`JWKS_CACHE_TTL_SECONDS`、`SUPERUSER_USERNAMES`、`SUPERUSER_USER_IDS`、`MAX_ENTRY_DATA_KEYS`、`MAX_ENTRY_DATA_DEPTH`、`MAX_TAGS_PER_ENTRY`、`MAX_TAG_LENGTH`、`MAX_VERSION_KEPT`、`ENTRY_KEY_MAX_LENGTH`
- **Docker**：`Dockerfile`（中科大 pip 源、仅生产依赖、无 gcc）+ `docker-compose.yml`（命名 `meta-service`、**端口 `9093:9093`**、`./data:/app/data` 卷持久化、healthcheck 探测 `/health`）
- **建表**：`init_db` 自动 `create_all`（无 alembic）
- **测试**：类型 CRUD 与 schema 变更规则、元数据 CRUD、schema 校验 422、版本与回滚、tags 过滤、分页、越权 403、**superuser 权限（普通 token 写 /types 403、superuser token 可管理）**、无 token/伪造 token 拒绝
- **README.md**：技术栈、目录结构、快速开始、API 端点表（含权限列）、模型字段表、配置项说明、Docker 部署、测试、与 user-service 的 JWT/role 对接说明

## 九、代码风格与质量要求

- 与参照项目逐行对齐：类型注解齐全（Mapped/Annotated）、Service 持有 `LogProxy(Repository(db))`、`datetime.now(timezone.utc)`、中文 docstring、`HTTPException` + `status.HTTP_*`、中文 detail
- Repository 只做数据访问，Service 做业务/schema 校验，Route 只做参数解析与响应组装
- `data` 校验基于类型定义运行时构造 Pydantic 模型，禁止硬编码业务字段

## 十、验收标准

1. `uvicorn app.main:app --reload --port 9093` 可启动，`/health` 正常
2. 用 user-service 签发的普通 token：读 `/types` 正常、写 `/types` 返回 **403**、`/entries` 全流程可用
3. 用 superuser token（user-service 部署自动创建的 superuser 登录）：可创建/更新/删除类型
4. schema 校验、tags 过滤查询、分页、版本历史与回滚端到端可用
5. `pytest tests/ -v` 全部通过
6. `docker-compose up -d --build` 可构建启动，重启数据不丢失

---

# 附：使用示例（含类型创建）

> 以下示例以**论坛（forum）**业务为例，演示"建类型 → 写元数据 → 查询 → 更新/版本 → 回滚"完整链路。
> 认证方式：`Authorization: Bearer <token>`（user-service 签发）。

## 示例 1：创建元数据类型（POST /api/v1/types）—— 仅 superuser

业务方在接入前，先用 **superuser token** 声明"论坛帖子元数据"长什么样（即先建表）。

**请求**

```
POST http://localhost:9093/api/v1/types
Authorization: Bearer <superuser_token>
Content-Type: application/json
```

```json
{
  "type_name": "forum_post",
  "service_name": "forum",
  "description": "论坛帖子元数据",
  "schema_json": {
    "fields": {
      "title":     { "type": "string",  "required": true,  "indexed": true  },
      "board":     { "type": "string",  "required": true,  "indexed": true  },
      "likes":     { "type": "integer", "required": false, "indexed": true  },
      "is_pinned": { "type": "boolean", "required": false, "indexed": false },
      "pinned_until": { "type": "string", "required": false, "indexed": false }
    }
  }
}
```

**成功响应（201 Created）**

```json
{
  "id": 1,
  "type_name": "forum_post",
  "service_name": "forum",
  "description": "论坛帖子元数据",
  "schema_json": {
    "fields": {
      "title":     { "type": "string",  "required": true,  "indexed": true  },
      "board":     { "type": "string",  "required": true,  "indexed": true  },
      "likes":     { "type": "integer", "required": false, "indexed": true  },
      "is_pinned": { "type": "boolean", "required": false, "indexed": false },
      "pinned_until": { "type": "string", "required": false, "indexed": false }
    }
  },
  "created_at": "2026-09-01T10:00:00",
  "updated_at": null
}
```

**越权响应（403 Forbidden）—— 普通用户 token 调用同一接口**

```json
{
  "detail": "仅超级用户可执行此操作"
}
```

## 示例 2：按类型写入实体元数据（POST /api/v1/entries）—— 登录用户

类型建好后，业务方（登录用户）即可写入具体帖子的元数据。

**请求**

```
POST http://localhost:9093/api/v1/entries
Authorization: Bearer <normal_user_token>
Content-Type: application/json
```

```json
{
  "type_name": "forum_post",
  "entity_key": "post-1001",
  "data": {
    "title": "如何配置 JWT 密钥轮换",
    "board": "技术",
    "likes": 128,
    "is_pinned": true,
    "pinned_until": "2026-09-15T00:00:00"
  },
  "tags": ["fastapi", "jwt", "教程"]
}
```

> 若 `data` 中缺必填字段（如 `title`）或字段类型错误（如 `likes: "128"`），服务端按 schema 动态校验并返回 **422**。

**成功响应（201 Created）**

```json
{
  "id": 10,
  "type_name": "forum_post",
  "entity_key": "post-1001",
  "data": {
    "title": "如何配置 JWT 密钥轮换",
    "board": "技术",
    "likes": 128,
    "is_pinned": true,
    "pinned_until": "2026-09-15T00:00:00"
  },
  "tags": ["fastapi", "jwt", "教程"],
  "version": 1,
  "owner_user_id": 3,
  "service_name": "forum",
  "created_at": "2026-09-01T10:05:00",
  "updated_at": null
}
```

## 示例 3：查询元数据（GET /api/v1/entries）—— 登录用户

按类型 + 字段过滤 + tags + 分页。

**请求**

```
GET http://localhost:9093/api/v1/entries?type_name=forum_post&board=%E6%8A%80%E6%9C%AF&tags=fastapi&page=1&page_size=20
Authorization: Bearer <normal_user_token>
```

**成功响应（200 OK）**

```json
{
  "total": 1,
  "items": [
    {
      "id": 10,
      "type_name": "forum_post",
      "entity_key": "post-1001",
      "data": {
        "title": "如何配置 JWT 密钥轮换",
        "board": "技术",
        "likes": 128,
        "is_pinned": true
      },
      "tags": ["fastapi", "jwt", "教程"],
      "version": 1,
      "owner_user_id": 3,
      "service_name": "forum",
      "created_at": "2026-09-01T10:05:00",
      "updated_at": null
    }
  ]
}
```

## 示例 4：更新、版本历史与回滚（PUT / POST）—— 登录用户

**更新元数据（版本自增 1 → 2）**

```
PUT http://localhost:9093/api/v1/entries/forum_post/post-1001
Authorization: Bearer <normal_user_token>
Content-Type: application/json
```

```json
{
  "data": { "likes": 256, "is_pinned": false },
  "tags": ["fastapi", "jwt", "教程", "热门"]
}
```

**成功响应（200 OK）**

```json
{
  "id": 10,
  "type_name": "forum_post",
  "entity_key": "post-1001",
  "data": {
    "title": "如何配置 JWT 密钥轮换",
    "board": "技术",
    "likes": 256,
    "is_pinned": false,
    "pinned_until": "2026-09-15T00:00:00"
  },
  "tags": ["fastapi", "jwt", "教程", "热门"],
  "version": 2,
  "owner_user_id": 3,
  "service_name": "forum",
  "created_at": "2026-09-01T10:05:00",
  "updated_at": "2026-09-01T10:10:00"
}
```

**查看版本历史**

```
GET http://localhost:9093/api/v1/entries/forum_post/post-1001/versions
Authorization: Bearer <normal_user_token>
```

```json
{
  "total": 2,
  "items": [
    { "version": 2, "data": { "...": "最新数据" }, "created_at": "2026-09-01T10:10:00" },
    { "version": 1, "data": { "...": "原始数据" }, "created_at": "2026-09-01T10:05:00" }
  ]
}
```

**回滚到指定版本（生成新版本，数据取回滚目标）**

```
POST http://localhost:9093/api/v1/entries/forum_post/post-1001/rollback
Authorization: Bearer <normal_user_token>
Content-Type: application/json
```

```json
{ "version": 1 }
```

## 快速自测清单

1. superuser 登录 user-service → 拿 token → `POST /types` 创建类型 → **201**
2. 普通用户登录 → 拿 token → `POST /types` → **403**；`GET /types` → **200**
3. 普通用户 `POST /entries` 写入元数据 → **201**（含 `version: 1`）
4. `PUT /entries/...` 更新 → `version: 2`
5. 传非法字段（`likes: "abc"`）→ **422**
6. 无 token / 伪造 token → **401**
