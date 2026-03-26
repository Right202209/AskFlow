# AskFlow 项目状态与开发计划

> 最后更新：2026-03-27

## 1. 总体状态

| 模块 | 状态 | 完成度 |
|------|------|--------|
| 后端核心 | 基本完成 | ~85% |
| Agent 管线 | 基本完成 | ~80% |
| RAG 管线 | 基本完成 | ~85% |
| 工单系统 | 基本完成 | ~80% |
| 嵌入/文档处理 | 基本完成 | ~85% |
| 前端 (React) | 页面骨架完成 | ~60% |
| 测试 | 仅单元测试 | ~25% |
| 基础设施/DevOps | 基础就绪 | ~40% |
| 数据库迁移 | 未开始 | 0% |

---

## 2. 后端详细状态

### 2.1 已完成（功能可用）

**核心基础设施** — 全部实现
- 异步 SQLAlchemy 引擎 + 会话工厂 (`core/database.py`)
- Redis 连接池 + 滑动窗口限流 (`core/redis.py`, `core/rate_limiter.py`)
- JWT 认证 + bcrypt 密码哈希 (`core/security.py`)
- RBAC 鉴权守卫 (`core/auth.py`, `require_role`)
- 结构化 JSON 日志 + trace_id (`core/logging.py`, `core/trace.py`)
- Prometheus 指标 + 路径归一化 (`core/metrics.py`, `core/middleware.py`)
- 统一异常处理 (`core/exceptions.py`)
- CORS 可配置 (`config.py` cors_origins)

**Agent 管线** — 核心链路完成
- 规则 + LLM 双重意图分类 (`agent/intent_classifier.py`)
- DB 驱动的意图路由配置 + 硬编码回退 (`agent/nodes.py`, `agent/service.py`)
- 5 条路由：rag / ticket / handoff / tool / clarify
- AgentGraph 执行 (`agent/graph.py`)
- 业务工具注册表 (`agent/tools.py`) — 目前仅 `search_order` 硬编码模拟数据
- 路由缓存 + 失效机制 (`agent/service.py`)

**RAG 管线** — 完整可用
- BM25 索引 (jieba 分词) + ChromaDB 向量检索
- RRF 融合排序 (`rag/retriever.py`)
- 可选 Reranker (`rag/reranker.py`)
- OpenAI 兼容 LLM 客户端（流式/非流式） (`rag/llm_client.py`)
- Prompt 构建 + 降级响应 (`rag/prompt_builder.py`)
- RAGService 编排 (`rag/service.py`)
- 优雅降级：LLM 不可用→原文片段；向量库不可用→BM25

**嵌入/文档处理** — 完整可用
- Protocol-based Embedder（API + Local 两种实现）
- 多格式解析器：PDF(pymupdf)、DOCX、Markdown、HTML
- 可配置分块策略 (`embedding/chunker.py`)
- 索引写入 + 删除 (`embedding/service.py`)
- 异步索引 Worker (`embedding/index_worker.py`)

**工单系统** — 完整可用
- CRUD + 状态流转 (`ticket/service.py`)
- 24h 去重 (`ticket/dedup.py`)
- WebSocket 通知 (`ticket/notifier.py`)
- 权限控制：普通用户只能关闭自己工单，staff 可修改优先级/指派

**聊天系统** — 完整可用
- WebSocket 端点（token 认证）
- 流式 token 推送 + 取消 + 心跳
- Redis 会话上下文存储
- 连接管理器
- 完整协议定义

**管理后台** — 完整可用
- 文档列表/删除、意图 CRUD、工单列表、统计看板
- 所有端点带角色守卫

**脚本工具** — 完整可用
- `seed_data.py`：创建 admin/user1 + 6 个意图配置
- `create_user.py`：CLI 用户创建

### 2.2 后端待完善

| 编号 | 问题 | 优先级 | 说明 |
|------|------|--------|------|
| B-1 | 无数据库迁移文件 | **P0** | `alembic/versions/` 为空，当前依赖 `create_all` 建表 |
| B-2 | `search_order` 是硬编码模拟 | P1 | tools.py 返回静态数据，无真实业务系统对接 |
| B-3 | 无会话管理接口 | P1 | 缺少重命名、删除、归档会话的 API |
| B-4 | 无用户管理接口 | P2 | 无法列出/禁用/角色变更用户 |
| B-5 | 无文档详情/预览/下载接口 | P2 | MinIO 上传了文件，但没有下载 API |
| B-6 | Prompt 模板管理未实现 | P2 | PRD 要求版本化 Prompt 管理，当前 prompt_builder 硬编码 |
| B-7 | Redis Streams 异步任务未使用 | P2 | PRD 选型了 Redis Streams，实际使用同步调用 |
| B-8 | 敏感数据脱敏未实现 | P2 | PRD 要求手机号/身份证脱敏存储 |
| B-9 | 邮件通知未实现 | P2 | PRD 要求工单变更"可选邮件通知" |
| B-10 | `order_query` seed 路由目标配置为 `rag` | P1 | seed_data 中 order_query.route_target="rag"，但 _FALLBACK_ROUTES 将其映射为 "tool"，DB 配置与预期不一致 |
| B-11 | LLMClient 无 close 集成 | P1 | `llm_client` 是模块级单例，`close()` 未接入 lifespan |
| B-12 | BM25 索引不持久化 | P2 | 内存中的 BM25 索引重启后清空，需要重新加载 |

---

## 3. 前端详细状态

### 3.1 已完成

**基础架构** — 全部就绪
- React 19 + Vite + TypeScript
- React Router v7 路由 + 守卫 (`RequireAuth`, `RequireRole`)
- Zustand stores: authStore, chatStore, ticketStore, adminStore
- API client + JWT 解析 + Bearer 注入 (`services/api.ts`, `services/jwt.ts`)
- shadcn/ui 集成 + Tailwind CSS

**已实现页面**（全部有实际 UI，非占位）

| 页面 | 路由 | 状态 |
|------|------|------|
| 登录页 | `/login` | 完成 |
| 注册页 | `/register` | 完成 |
| 智能问答 | `/app/chat/:id` | 完成（三栏布局、消息流、流式、来源、意图） |
| 工单列表 | `/app/tickets` | 完成 |
| 工单详情 | `/app/tickets/:id` | 完成 |
| 管理看板 | `/admin/dashboard` | 完成（四指标卡片+图表） |
| 文档管理 | `/admin/documents` | 完成 |
| 意图配置 | `/admin/intents` | 完成 |

**全局模块**
- WebSocket Hook (`hooks/useWebSocket.ts`)
- AppLayout 带角色感知导航
- Service 层：auth, chat, ticket, document, admin

### 3.2 前端待完善

| 编号 | 问题 | 优先级 | 说明 |
|------|------|--------|------|
| F-1 | 组件未拆分 | P1 | ChatPage 把 ConversationList/MessageBubble/SourceCard 全写在一个文件（278行），PAGE_PLAN 建议拆为 7 个组件 |
| F-2 | 无工单创建弹窗 | P1 | 聊天页 InfoPanel 缺少"创建工单"按钮和 CreateTicketDialog |
| F-3 | PAGE_PLAN 部分"已知边界"已过时 | P1 | 文档说"没有 GET /users/me"和"没有意图删除接口"，但后端已补充 |
| F-4 | 无 Toast/Notification 系统 | P2 | 注册成功/失败等场景缺少 Toast 反馈 |
| F-5 | 无虚拟滚动 | P2 | 长会话消息列表无虚拟化，性能可能有问题 |
| F-6 | 前端测试为零 | P2 | 无 Vitest/Jest 配置，无组件/Hook 测试 |
| F-7 | 无 PWA / 离线支持 | P3 | 可选优化 |
| F-8 | 无 i18n | P3 | 当前 UI 中文硬编码 |

---

## 4. 测试状态

### 4.1 现有测试

| 测试文件 | 覆盖模块 | 测试数量 | 质量 |
|----------|----------|----------|------|
| `test_intent.py` | 规则分类 + 路由决策 | 11 | 好，覆盖主要分支 |
| `test_auth.py` | Bearer token 提取 | 4 | 好，含边界用例 |
| `test_schemas.py` | APIResponse, Ticket, Auth schemas | 7 | 好，含验证错误 |
| `test_embedder.py` | APIEmbedder 多种 payload 格式 | 2 | 好 |
| `test_protocol.py` | 聊天协议 | ? | 存在 |
| `test_security.py` | JWT + 密码 | ? | 存在 |
| `test_config.py` | 配置加载 | ? | 存在 |
| `test_trace.py` | trace_id 生成 | ? | 存在 |
| `test_exceptions.py` | 异常类 | ? | 存在 |
| `test_chunker.py` | 文本分块 | ? | 存在 |
| `test_parser.py` | 文档解析 | ? | 存在 |
| `test_prompt_builder.py` | Prompt 构建 | ? | 存在 |
| `test_embedding_router.py` | 嵌入路由 | ? | 存在 |

### 4.2 测试缺口（按优先级）

| 编号 | 未覆盖模块 | 优先级 | 类型 |
|------|-----------|--------|------|
| T-1 | `agent/service.py` (AgentService.process) | **P0** | 单元 |
| T-2 | `agent/graph.py` (AgentGraph.run) | **P0** | 单元 |
| T-3 | `agent/nodes.py` (rag_node, ticket_node, handoff_node, tool_node) | **P0** | 单元 |
| T-4 | `rag/service.py` (RAGService.query, query_stream) | **P0** | 单元 |
| T-5 | `rag/retriever.py` (HybridRetriever.retrieve, RRF fusion) | **P0** | 单元 |
| T-6 | `ticket/service.py` (TicketService 全量方法) | P1 | 单元 |
| T-7 | `chat/router.py` (WebSocket 端点) | P1 | 集成 |
| T-8 | `admin/router.py` (全部管理端点) | P1 | 集成 |
| T-9 | 全部 repository 类 | P1 | 集成 |
| T-10 | `embedding/service.py` (EmbeddingService) | P1 | 单元 |
| T-11 | `rag/llm_client.py` (LLMClient) | P2 | 单元 |
| T-12 | `chat/manager.py` (ConnectionManager) | P2 | 单元 |
| T-13 | `chat/session.py` (SessionStore) | P2 | 单元 |
| T-14 | 集成测试（空目录） | P1 | 集成 |
| T-15 | E2E 测试（空目录） | P2 | E2E |

**当前覆盖率估算**：~15-20%（仅 core 工具类和 schemas 有测试，业务逻辑层几乎未测试）

---

## 5. 基础设施状态

### 5.1 已就绪

- `docker-compose.yml`：PostgreSQL 16、Redis 7、ChromaDB、MinIO（含健康检查）
- `Dockerfile`：多阶段构建，可用
- `Makefile`：完整的开发命令集
- `.env.example`：覆盖所有配置项
- `pyproject.toml`：依赖完整，dev 依赖分离

### 5.2 待完善

| 编号 | 问题 | 优先级 | 说明 |
|------|------|--------|------|
| I-1 | 无 Alembic 迁移文件 | **P0** | `alembic/versions/` 为空，生产部署无法用 `create_all` |
| I-2 | 无 CI/CD 配置 | P1 | 无 `.github/workflows/`，无自动化测试/构建/部署 |
| I-3 | Dockerfile 缺少非 root 用户 | P1 | 容器以 root 运行，安全风险 |
| I-4 | Dockerfile 未复制 .env | P2 | 生产环境需通过环境变量/secret 注入 |
| I-5 | 无 docker-compose.prod.yml | P2 | 无生产级编排（应用容器 + 基础设施 + 网络） |
| I-6 | 无 Kubernetes manifests | P3 | PRD 提到 K8s 部署拓扑，当前无 YAML |
| I-7 | 无 Grafana 看板 | P2 | 有 Prometheus 指标但无预置看板 |
| I-8 | 无 .dockerignore | P2 | 构建镜像可能包含不必要的文件 |

---

## 6. PRD 对比差距分析

对照 PRD 功能需求，以下是尚未完成的部分：

| PRD 需求 | 当前状态 | 差距 |
|----------|----------|------|
| 知识检索问答端到端 | **已实现** | — |
| 6 类意图识别 | **已实现** | — |
| 5 条路由链路 | **已实现** | — |
| WebSocket 流式 + 取消 + 心跳 | **已实现** | 缺少客户端断线重连（后端支持，前端 useWebSocket 需验证） |
| 工单自动创建 + 去重 + 状态跟踪 | **已实现** | — |
| 按文档来源/时间/标签过滤 | **未实现** | RAG 检索不支持元数据过滤 |
| Prompt 模板版本化管理 | **未实现** | prompt_builder 硬编码 |
| Redis Streams 异步任务 | **未实现** | 使用同步调用 |
| 敏感数据脱敏 | **未实现** | — |
| 邮件通知 | **未实现** | 工单变更仅 WebSocket 推送 |
| 日志审计追踪 | **部分实现** | 有 trace_id，无审计日志存储/查询 |
| Grafana 看板 | **未实现** | 有 Prometheus 指标 |
| LangGraph 编排 | **未使用** | pyproject.toml 有依赖但实际用自建 AgentGraph |

---

## 7. 开发计划

### Phase 1：生产就绪（P0）

> 目标：让系统能在生产环境稳定运行

1. **创建 Alembic 初始迁移** — 从现有模型生成 `alembic revision --autogenerate`
2. **修复 seed_data 中 order_query 路由目标** — 改为 `tool`
3. **LLMClient lifespan 接入** — 在 app lifespan 中调用 `llm_client.close()`
4. **补充核心业务测试** — AgentService, RAGService, HybridRetriever, TicketService
5. **Dockerfile 安全加固** — 非 root 用户 + .dockerignore

### Phase 2：体验完善（P1）

> 目标：前后端功能闭环，用户体验完整

6. **添加会话管理接口** — 重命名、删除、归档
7. **ChatPage 组件拆分** — 按 PAGE_PLAN 拆为独立组件
8. **添加工单创建弹窗** — 聊天页 InfoPanel 中的 CreateTicketDialog
9. **更新 PAGE_PLAN 已知边界** — 移除已解决的条目（auth/me、意图删除等）
10. **CI/CD Pipeline** — GitHub Actions：lint + test + build
11. **补充集成测试** — 路由端点、Repository 层
12. **修复 order_query 工具** — 对接真实业务接口或提供更完整的模拟

### Phase 3：能力增强（P2）

> 目标：PRD 剩余功能 + 运维能力

13. **Prompt 模板管理** — DB 存储、版本化、后台 CRUD
14. **文档详情/预览/下载** — MinIO 预签名 URL
15. **用户管理接口** — 列表、禁用、角色变更
16. **RAG 元数据过滤** — 按来源/标签/时间过滤检索结果
17. **BM25 索引持久化** — 启动时从 DB 加载
18. **Redis Streams 异步任务** — 文档索引异步化
19. **Grafana 预置看板** — 基于现有 Prometheus 指标
20. **前端 Toast 系统** — 操作反馈通知
21. **E2E 测试** — 关键用户流程

### Phase 4：运营优化（P3）

22. **敏感数据脱敏**
23. **邮件通知（工单变更）**
24. **审计日志存储与查询**
25. **Kubernetes manifests**
26. **前端 i18n**
27. **消息虚拟滚动**
28. **前端单元测试**

---

## 8. 技术债务

| 项目 | 影响 | 建议 |
|------|------|------|
| LangGraph 依赖未使用 | 包体积 | 从 pyproject.toml 移除，或替换自建 AgentGraph |
| `search_order` 硬编码模拟 | 功能不完整 | 抽象为 Tool Protocol，注册真实实现 |
| `re` 内联 import (tools.py:71) | 代码规范 | 移到文件顶部 |
| PRD 写 Vue 3 前端，实际用 React | 文档偏差 | 更新 PRD 前端选型章节 |
| 模块级单例 (`llm_client`, `bm25_index`) | 测试困难 | 改为依赖注入 |
