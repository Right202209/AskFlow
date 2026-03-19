# AskFlow

基于 RAG（检索增强生成）和 Agent 架构的智能客服系统。

AskFlow 将私有知识库检索、意图识别、流程路由和工单管理串联为自动化闭环，减少人工重复劳动，同时保证私有知识安全可控、不外泄。

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                  客户端（Web 聊天界面）                   │
└──────────────────────────┬──────────────────────────────┘
                           │ WebSocket / HTTPS
┌──────────────────────────▼──────────────────────────────┐
│                    FastAPI 网关层                        │
│          认证 (JWT) · 限流 · 跨域 · 链路追踪              │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                        服务层                            │
│                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐         │
│  │  Chat      │  │    RAG     │  │   Agent    │         │
│  │  WebSocket │  │  检索 & 生成│  │  意图 &    │         │
│  │  流式输出   │  │           │  │  路由      │          │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘         │
│        │               │               │                │
│  ┌─────┴──────┐  ┌─────┴──────┐  ┌─────┴──────┐         │
│  │  工单服务   │  │  嵌入服务   │  │  管理服务   │        │
│  └────────────┘  └────────────┘  └────────────┘         │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                       数据层                             │
│    PostgreSQL · Redis · ChromaDB · MinIO                │
└─────────────────────────────────────────────────────────┘
```

## 核心功能

- **RAG 问答** — BM25 + 向量混合检索，倒数排序融合（RRF），可选交叉编码器重排序，LLM 生成回答并附带来源引用
- **Agent 系统** — 规则 + LLM 双重意图识别，配置驱动路由至 RAG / 工单 / 转人工 / 澄清追问
- **流式聊天** — 基于 WebSocket 的实时逐字输出，支持心跳检测、取消生成、断线自动重连
- **工单管理** — 自动创建工单，24 小时去重，状态跟踪，WebSocket 实时通知
- **可配置嵌入** — 基于 Protocol 的设计，支持本地（fastembed，CPU ONNX）和 API（OpenAI 兼容）两种嵌入方式
- **文档处理** — 支持 PDF、DOCX、Markdown、HTML 解析，可配置分块大小和重叠
- **优雅降级** — LLM 不可用时返回原文片段；向量库不可用时降级为 BM25；Agent 异常时回退到 RAG
- **可观测性** — 结构化 JSON 日志（含 trace_id），Prometheus 指标（请求数/延迟、RAG 查询、LLM Token、意图分布）
- **管理后台** — 知识文档/意图配置/Prompt 模板管理，数据统计看板
- **认证安全** — JWT 认证，RBAC 权限控制（user/agent/admin），Redis 滑动窗口限流（60 次/分钟）

## 技术选型

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI（异步） |
| 关系数据库 | PostgreSQL 16 + SQLAlchemy 2.0（异步） |
| 向量数据库 | ChromaDB |
| 缓存 | Redis 7 |
| 对象存储 | MinIO（S3 兼容） |
| 大模型 | OpenAI 兼容 API（Ollama、vLLM 等） |
| 嵌入模型 | fastembed（本地，CPU ONNX）/ OpenAI 兼容 API |
| 搜索 | BM25（rank_bm25 + jieba 分词）+ 向量检索 |
| 认证 | JWT（PyJWT）+ bcrypt |
| 日志 | structlog（JSON 格式） |
| 指标 | prometheus-client |
| 数据库迁移 | Alembic |
| 聊天界面 | 原生 HTML / JS / CSS |

## 项目结构

```
AskFlow/
├── pyproject.toml              # 依赖与构建配置
├── docker-compose.yml          # PostgreSQL, Redis, ChromaDB, MinIO
├── Dockerfile
├── Makefile                    # 开发命令
├── alembic.ini
├── .env.example
├── alembic/                    # 数据库迁移
│   ├── env.py
│   └── versions/
├── static/                     # 聊天界面
│   ├── index.html
│   ├── chat.js
│   └── style.css
├── scripts/
│   ├── seed_data.py            # 初始数据填充
│   └── create_user.py          # 用户创建工具
├── tests/
│   ├── conftest.py
│   ├── unit/                   # 单元测试
│   ├── integration/            # 集成测试
│   └── e2e/                    # 端到端测试
└── src/askflow/
    ├── main.py                 # 应用工厂 + 生命周期
    ├── config.py               # Pydantic Settings 配置
    ├── dependencies.py         # 依赖注入
    ├── core/                   # 共享基础设施
    │   ├── database.py         # SQLAlchemy 异步引擎 + 会话
    │   ├── redis.py            # Redis 连接池
    │   ├── minio_client.py     # MinIO 封装
    │   ├── security.py         # JWT + 密码哈希
    │   ├── auth.py             # 当前用户获取、角色校验
    │   ├── rate_limiter.py     # Redis 滑动窗口限流
    │   ├── logging.py          # structlog JSON + trace_id
    │   ├── trace.py            # contextvars 链路追踪 ID
    │   ├── exceptions.py       # 自定义异常 + 处理器
    │   ├── middleware.py       # CORS、链路追踪、日志中间件
    │   └── metrics.py          # Prometheus 计数器/直方图
    ├── models/                 # SQLAlchemy ORM 模型
    │   ├── base.py             # Base、UUID Mixin、时间戳 Mixin
    │   ├── user.py             # 用户
    │   ├── conversation.py     # 会话
    │   ├── message.py          # 消息
    │   ├── ticket.py           # 工单
    │   ├── document.py         # 知识文档
    │   └── intent_config.py    # 意图配置
    ├── schemas/                # Pydantic 请求/响应模型
    │   ├── common.py           # APIResponse, PaginatedResponse
    │   ├── auth.py
    │   ├── conversation.py
    │   ├── message.py
    │   ├── ticket.py
    │   ├── document.py
    │   ├── intent.py
    │   └── admin.py
    ├── repositories/           # 数据访问层
    │   ├── user_repo.py
    │   ├── conversation_repo.py
    │   ├── message_repo.py
    │   ├── ticket_repo.py
    │   ├── document_repo.py
    │   └── intent_config_repo.py
    ├── chat/                   # WebSocket + 会话管理
    │   ├── protocol.py         # 消息类型与序列化
    │   ├── manager.py          # 连接管理器
    │   ├── session.py          # Redis 会话存储
    │   └── router.py           # WS 端点 + REST 端点
    ├── rag/                    # 检索增强生成
    │   ├── llm_client.py       # OpenAI 兼容流式客户端
    │   ├── vector_store.py     # ChromaDB 封装
    │   ├── bm25.py             # BM25 索引（jieba 分词）
    │   ├── retriever.py        # 混合检索 + RRF 融合
    │   ├── reranker.py         # 可选交叉编码器重排序
    │   ├── prompt_builder.py   # System Prompt + 上下文模板
    │   ├── service.py          # RAG 查询编排
    │   └── router.py
    ├── agent/                  # 意图识别 + 路由
    │   ├── intent_classifier.py # 规则 + LLM 双重分类
    │   ├── state.py            # Agent 状态
    │   ├── graph.py            # Agent 图（分类 → 路由）
    │   ├── nodes.py            # RAG、工单、转人工、澄清节点
    │   ├── tools.py            # 业务工具（订单查询等）
    │   ├── service.py          # Agent 编排服务
    │   └── router.py
    ├── ticket/                 # 工单生命周期
    │   ├── service.py          # CRUD + 状态流转
    │   ├── dedup.py            # 24 小时去重
    │   ├── notifier.py         # WebSocket 通知
    │   └── router.py
    ├── embedding/              # 文档处理 + 向量化
    │   ├── embedder.py         # Embedder 协议 + 实现
    │   ├── parser.py           # PDF、DOCX、HTML、MD 解析器
    │   ├── chunker.py          # 文本分块（支持重叠）
    │   ├── service.py          # 索引编排
    │   ├── router.py
    │   └── index_worker.py
    └── admin/                  # 管理 + 统计
        ├── service.py          # 文档/意图管理
        ├── analytics.py        # 聚合统计
        └── router.py           # 认证 + 管理端点
```

## 快速开始

### 前置条件

- Python 3.11+
- Docker & Docker Compose
- OpenAI 兼容的 LLM 服务（如 Ollama 运行 `qwen2.5:7b`）

### 1. 克隆与配置

```bash
git clone <repo-url> AskFlow
cd AskFlow
cp .env.example .env
# 编辑 .env，配置 LLM 端点、密钥等
```

### 2. 启动基础设施

```bash
make docker-up
# 启动 PostgreSQL、Redis、ChromaDB、MinIO
```

### 3. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
make install
```

### 4. 数据库迁移与初始数据

```bash
make migrate
make seed
# 创建管理员用户（admin / admin123）和默认意图配置
```

### 5. 启动服务

```bash
make dev
# 服务运行在 http://localhost:8000
```

### 6. 打开聊天界面

浏览器访问 `http://localhost:8000/static/index.html`，使用 `admin / admin123` 登录后即可开始对话。

## API 接口

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/admin/auth/register` | 注册新用户 |
| POST | `/api/v1/admin/auth/login` | 登录，获取 JWT Token |

### 聊天

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/chat/conversations` | 创建会话 |
| GET | `/api/v1/chat/conversations/{id}/messages` | 获取消息历史 |
| WS | `/api/v1/chat/ws/{token}` | WebSocket 聊天端点 |

### RAG 问答

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/rag/query` | 知识库查询 |

### Agent

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/agent/classify` | 意图分类 |

### 工单

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tickets` | 创建工单 |
| GET | `/api/v1/tickets/{id}` | 查询工单 |
| PUT | `/api/v1/tickets/{id}` | 更新工单 |
| GET | `/api/v1/tickets` | 工单列表 |

### 文档嵌入

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/embedding/documents` | 上传并索引文档 |
| POST | `/api/v1/embedding/documents/{id}/reindex` | 重建文档索引 |

### 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/documents` | 文档列表 |
| DELETE | `/api/v1/admin/documents/{id}` | 删除文档 |
| GET | `/api/v1/admin/intents` | 意图配置列表 |
| POST | `/api/v1/admin/intents` | 创建意图配置 |
| PUT | `/api/v1/admin/intents/{id}` | 更新意图配置 |
| GET | `/api/v1/admin/analytics` | 统计看板 |

### 可观测性

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |

## WebSocket 协议

**客户端 -> 服务端：**

```json
{
  "type": "message | cancel | ping",
  "conversation_id": "uuid",
  "content": "用户输入文本",
  "timestamp": 1710000000
}
```

**服务端 -> 客户端：**

```json
{
  "type": "token | message_end | error | intent | source | ticket | pong",
  "conversation_id": "uuid",
  "data": {
    "content": "逐字内容或完整消息",
    "sources": [{"title": "...", "chunk": "...", "score": 0.92}],
    "label": "faq",
    "confidence": 0.95,
    "ticket_id": "uuid"
  },
  "timestamp": 1710000000
}
```

## 降级策略

| 故障场景 | 降级方案 |
|----------|----------|
| LLM 服务不可用 | 返回检索原文片段 + 提示信息 |
| 向量数据库不可用 | 降级为 BM25 关键词检索 |
| Agent 路由异常 | 默认走 RAG 问答链路 |
| WebSocket 断连 | 客户端自动重连，服务端恢复会话上下文 |

## 开发命令

```bash
make dev         # 启动开发服务器（热重载）
make test        # 运行测试（含覆盖率）
make lint        # 代码检查
make format      # 代码格式化
make clean       # 清理构建产物
make docker-up   # 启动基础设施
make docker-down # 停止基础设施
make seed        # 填充初始数据
make migrate     # 运行数据库迁移
```

## 环境变量

查看 [.env.example](.env.example) 了解所有可配置项：

- `LLM_BASE_URL` / `LLM_MODEL` — 大模型端点配置
- `EMBEDDING_PROVIDER` — `api`（OpenAI 兼容，默认）或 `local`（fastembed，CPU ONNX）
- `DATABASE_URL` — PostgreSQL 连接串
- `REDIS_URL` — Redis 连接串
- `CHROMA_HOST` / `CHROMA_PORT` — ChromaDB 连接配置
- `SECRET_KEY` — JWT 签名密钥（生产环境务必修改！）
- `RATE_LIMIT_PER_MINUTE` — 单用户限流（默认 60 次/分钟）

## 许可证

MIT
