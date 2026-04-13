# AskFlow

AskFlow 是一个围绕 FastAPI、RAG 和意图路由 Agent 构建的智能客服系统。本仓库同时包含 `src/askflow/` 下的后端应用和 `web/` 下的 React 前端。

## 当前概况

- 后端：按聊天、RAG、Agent 路由、工单、嵌入、管理端拆分的 FastAPI 应用
- 前端：React 19 + Vite 应用，已实现登录注册、聊天、工单、看板、文档管理、意图管理
- 基础设施：Docker Compose 启动 PostgreSQL、Redis、ChromaDB、MinIO
- 文档：项目级文档放在 `docs/`，前端专项文档放在 `web/docs/`

当前实现状态和缺口见 [docs/status/PROJECT_STATUS.md](docs/status/PROJECT_STATUS.md)。

## 架构概览

```
React Web UI
    |
    | HTTPS / WebSocket
    v
FastAPI API
    |
    +-- chat
    +-- rag
    +-- agent
    +-- tickets
    +-- embedding
    +-- admin
    |
    +-- PostgreSQL
    +-- Redis
    +-- ChromaDB
    +-- MinIO
```

## 已实现能力

- JWT 登录认证，以及前后端基于角色的访问控制
- WebSocket 聊天，支持流式 token、心跳、取消、断线重连
- BM25 与 Chroma 向量检索结合的混合召回
- `rag`、`ticket`、`handoff`、`tool`、`clarify` 五类路由执行
- 工单创建、更新、用户视角列表，以及 admin/agent 视角管理
- 文档上传、索引、重建索引、删除，以及 MinIO 原文件存储
- 管理看板、文档管理、意图配置接口
- `/health` 与 `/metrics` 运维接口

## 当前缺口

- Prompt 模板 CRUD 与版本化尚未实现
- 检索结果按来源/时间/标签过滤尚未实现
- `order_query` 仍然使用模拟工具实现
- 还没有用户管理 API
- 集成测试、E2E 测试和前端自动化测试仍为空白

## 仓库结构

| 路径 | 用途 |
|------|------|
| `src/askflow/` | 后端源码 |
| `web/src/` | React 前端源码 |
| `alembic/` | 数据库迁移 |
| `tests/` | 后端测试 |
| `scripts/` | 初始化与本地辅助脚本 |
| `docs/` | 项目文档、状态、审计 |
| `web/docs/` | 前端规划与实现文档 |

更完整的目录说明见 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)。

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 20+
- Docker（支持 Compose）
- 可用的 OpenAI 兼容 LLM 接口，用于聊天与可选嵌入

### 1. 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

```bash
make install
make install-web
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

`.env.example` 已包含完整默认值。通常需要关注的变量有：

- `DATABASE_URL`
- `REDIS_URL`
- `CHROMA_HOST` / `CHROMA_PORT`
- `MINIO_*`
- `LLM_*`
- `EMBEDDING_*`
- `CORS_ORIGINS`

### 4. 启动本地基础设施

```bash
make docker-up
```

默认会启动：

- PostgreSQL：`localhost:5432`
- Redis：`localhost:6379`
- ChromaDB：`localhost:8100`
- MinIO API：`localhost:9000`
- MinIO Console：`localhost:9001`

### 5. 执行迁移并填充数据

```bash
make migrate
make seed
```

默认种子账号：

- `admin / admin123`
- `user1 / user123`

### 6. 启动后端

```bash
make dev
```

后端地址：

- API：`http://localhost:8000`
- OpenAPI 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`
- 指标：`http://localhost:8000/metrics`

### 7. 启动前端

```bash
make dev-web
```

前端地址：

- 应用：`http://localhost:5173`

## 常用命令

| 命令 | 说明 |
|------|------|
| `make install` | 以 editable 模式安装后端依赖 |
| `make install-web` | 安装前端依赖 |
| `make docker-up` | 启动 PostgreSQL、Redis、ChromaDB、MinIO |
| `make docker-down` | 停止本地基础设施 |
| `make migrate` | 执行 Alembic 迁移 |
| `make migrate-create msg="..."` | 创建新迁移 |
| `make seed` | 填充默认用户和意图配置 |
| `make dev` | 启动 FastAPI 开发服务 |
| `make dev-web` | 启动 Vite 开发服务 |
| `make test` | 运行后端测试 |
| `make lint` | 执行 Ruff 检查 |
| `make format` | 使用 Ruff 格式化后端代码 |
| `make build-web` | 构建前端生产包 |

## API 分组

后端挂载的主要路由前缀如下：

| 模块 | 前缀 |
|------|------|
| RAG | `/api/v1/rag` |
| Embedding | `/api/v1/embedding` |
| Chat | `/api/v1/chat` |
| Agent | `/api/v1/agent` |
| Tickets | `/api/v1/tickets` |
| Admin | `/api/v1/admin` |

代表性接口：

- `POST /api/v1/admin/auth/login`
- `GET /api/v1/chat/conversations`
- `WS /api/v1/chat/ws/{token}`
- `POST /api/v1/rag/query`
- `POST /api/v1/tickets`
- `GET /api/v1/admin/analytics`
- `POST /api/v1/embedding/documents`

完整接口定义请查看 `/docs`。

## 校验说明

- 截至 2026-04-06，`web/` 下 `npm run build` 可通过
- `make test` 依赖当前 shell 的 Python 环境已安装项目依赖；请先激活 `.venv` 或执行 `make install`
- 使用仓库 `.venv` 直接运行 `pytest` 时已暴露后端失败用例，因此当前后端测试集不能视为全绿

## 文档索引

- [docs/README.md](docs/README.md) - 项目文档入口
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) - 仓库结构与放置规则
- [docs/status/PROJECT_STATUS.md](docs/status/PROJECT_STATUS.md) - 当前实现状态
- [docs/audits/PRD_AUDIT.md](docs/audits/PRD_AUDIT.md) - PRD 对照审计
- [web/docs/README.md](web/docs/README.md) - 前端文档入口
- [PRD.md](PRD.md) - 产品需求文档

## 许可证

MIT
