# AskFlow 项目状态与开发计划

> 最后更新：2026-03-28

## 1. 总体状态

| 模块 | 状态 | 完成度 |
|------|------|--------|
| 后端核心 | 基本完成 | ~85% |
| Agent 管线 | 基本完成 | ~80% |
| RAG 管线 | 基本完成 | ~85% |
| 工单系统 | 基本完成 | ~80% |
| 嵌入/文档处理 | 基本完成 | ~85% |
| 前端 (React) | 主要页面可用 | ~70% |
| 测试 | 单元测试扩展中 | ~35% |
| 基础设施/DevOps | 基础就绪 | ~40% |
| 数据库迁移 | 已初始化 | ~80% |

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
- 会话管理接口：列表、消息历史、重命名、归档、删除 (`chat/router.py`)

**管理后台** — 完整可用
- 文档列表/删除、意图 CRUD、工单列表、统计看板
- 所有端点带角色守卫

**脚本工具** — 完整可用
- `seed_data.py`：创建 admin/user1 + 6 个意图配置
- `create_user.py`：CLI 用户创建

### 2.2 后端待完善

| 编号 | 问题 | 优先级 | 说明 |
|------|------|--------|------|
| B-2 | `search_order` 是硬编码模拟 | P1 | tools.py 返回静态数据，无真实业务系统对接 |
| B-3 | 删除会话存在“先提交 DB、后清理 Redis”风险 | P1 | `chat/router.py` 先 `db.commit()` 再 `session_store.clear()`，Redis 失败时会出现“接口 500 但数据已删除”的不一致 |
| B-4 | 无用户管理接口 | P2 | 无法列出/禁用/角色变更用户 |
| B-5 | 无文档详情/预览/下载接口 | P2 | MinIO 上传了文件，但没有下载 API |
| B-6 | Prompt 模板管理未实现 | P2 | PRD 要求版本化 Prompt 管理，当前 prompt_builder 硬编码 |
| B-7 | Redis Streams 异步任务未使用 | P2 | PRD 选型了 Redis Streams，实际使用同步调用 |
| B-8 | 敏感数据脱敏未实现 | P2 | PRD 要求手机号/身份证脱敏存储 |
| B-9 | 邮件通知未实现 | P2 | PRD 要求工单变更"可选邮件通知" |
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
| 智能问答 | `/app/chat/:id` | 完成（三栏布局、组件拆分、流式、来源、意图、创建工单弹窗） |
| 工单列表 | `/app/tickets` | 完成 |
| 工单详情 | `/app/tickets/:id` | 完成 |
| 管理看板 | `/admin/dashboard` | 完成（四指标卡片+图表） |
| 文档管理 | `/admin/documents` | 完成 |
| 意图配置 | `/admin/intents` | 完成 |

**全局模块**
- WebSocket Hook (`hooks/useWebSocket.ts`)
- AppLayout 带角色感知导航
- Service 层：auth, chat, ticket, document, admin
- Chat 组件：ConversationList、MessageList、MessageBubble、ChatComposer、InfoPanel、CreateTicketDialog

### 3.2 前端待完善

| 编号 | 问题 | 优先级 | 说明 |
|------|------|--------|------|
| F-3 | PAGE_PLAN 部分"已知边界"已过时 | P1 | 文档说"没有 GET /users/me"和"没有意图删除接口"，但后端已补充 |
| F-4 | WebSocket 未就绪时消息可能静默丢失 | P1 | `useWebSocket.sendMessage()` 在连接未 `OPEN` 时直接返回，`ChatPage` 仍会先把用户消息写入本地列表 |
| F-5 | 普通用户缺少“关闭自己工单”的前端入口 | P1 | 后端允许普通用户关闭自己的工单，但 `TicketDetailPage` 仅 agent/admin 可改状态 |
| F-6 | CreateTicketDialog 编辑中会被新消息重置 | P1 | 弹窗 `useEffect` 依赖 `messages`，流式消息进入时会覆盖用户正在填写的表单 |
| F-7 | 无 Toast/Notification 系统 | P2 | 注册成功/失败等场景缺少 Toast 反馈 |
| F-8 | 无虚拟滚动 | P2 | 长会话消息列表无虚拟化，性能可能有问题 |
| F-9 | 前端测试为零 | P2 | 无 Vitest/Jest 配置，无组件/Hook 测试 |
| F-10 | 无 PWA / 离线支持 | P3 | 可选优化 |
| F-11 | 无 i18n | P3 | 当前 UI 中文硬编码 |

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
| `test_agent_service.py` | AgentService.process | 3 | 好，覆盖 RAG / Graph / 降级分支 |
| `test_agent_graph.py` | AgentGraph.run | 3 | 好，覆盖主要路由链路 |
| `test_agent_nodes.py` | Agent 节点函数 | 5 | 好，覆盖 ticket / handoff / tool / clarify |
| `test_rag_service.py` | RAGService | 4 | 好，覆盖普通查询与流式查询 |
| `test_retriever.py` | HybridRetriever / RRF | 3 | 好，覆盖混合召回主流程 |
| `test_ticket_service.py` | TicketService | 5 | 好，覆盖权限与去重逻辑 |
| `test_chat_router.py` | 会话 REST 接口 | 4 | 好，覆盖重命名 / 归档 / 删除 |
| `test_conversation_repo.py` | ConversationRepo | 2 | 基础覆盖，验证删除清理逻辑 |

### 4.2 测试缺口（按优先级）

| 编号 | 未覆盖模块 | 优先级 | 类型 |
|------|-----------|--------|------|
| T-1 | `chat/router.py` (WebSocket 端点) | P1 | 集成 |
| T-2 | `admin/router.py` (全部管理端点) | P1 | 集成 |
| T-3 | 全部 repository 类 | P1 | 集成 |
| T-4 | `embedding/service.py` (EmbeddingService) | P1 | 单元 |
| T-5 | `rag/llm_client.py` (LLMClient) | P2 | 单元 |
| T-6 | `chat/manager.py` (ConnectionManager) | P2 | 单元 |
| T-7 | `chat/session.py` (SessionStore) | P2 | 单元 |
| T-8 | 集成测试（空目录） | P1 | 集成 |
| T-9 | E2E 测试（空目录） | P2 | E2E |
| T-10 | `web/src/hooks/useWebSocket.ts` | P1 | 前端单元 |
| T-11 | `web/src/components/chat/CreateTicketDialog.tsx` | P1 | 前端单元 |
| T-12 | `web/src/pages/App/TicketDetailPage.tsx` | P1 | 前端单元 |

**当前覆盖率估算**：~25-35%（后端核心业务单元测试已有补齐，但前端仍无测试，路由集成与 E2E 仍明显不足）

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
| I-2 | 无 CI/CD 配置 | P1 | 无 `.github/workflows/`，无自动化测试/构建/部署 |
| I-4 | Dockerfile 未复制 .env | P2 | 生产环境需通过环境变量/secret 注入 |
| I-5 | 无 docker-compose.prod.yml | P2 | 无生产级编排（应用容器 + 基础设施 + 网络） |
| I-6 | 无 Kubernetes manifests | P3 | PRD 提到 K8s 部署拓扑，当前无 YAML |
| I-7 | 无 Grafana 看板 | P2 | 有 Prometheus 指标但无预置看板 |

---

## 6. PRD 对比差距分析

对照 PRD 功能需求，以下是尚未完成的部分：

| PRD 需求 | 当前状态 | 差距 |
|----------|----------|------|
| 知识检索问答端到端 | **已实现** | — |
| 6 类意图识别 | **已实现** | — |
| 5 条路由链路 | **已实现** | — |
| WebSocket 流式 + 取消 + 心跳 | **已实现** | 前端仍有“连接未就绪时消息可能静默丢失”的交互缺口 |
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

### Phase 1：生产就绪（P0，已基本完成）

> 目标：让系统能在生产环境稳定运行

1. [x] **创建 Alembic 初始迁移** — 已存在 `alembic/versions/20260327_01_initial_schema.py`
2. [x] **修复 seed_data 中 order_query 路由目标** — 已改为 `tool`
3. [x] **LLMClient lifespan 接入** — `main.py` 已在 lifespan 中调用 `llm_client.close()`
4. [ ] **补充核心业务测试** — 已覆盖 AgentService、AgentGraph、AgentNodes、RAGService、HybridRetriever、TicketService；仍缺集成层
5. [x] **Dockerfile 安全加固** — 已使用非 root 用户并补充 `.dockerignore`

### Phase 2：体验完善（P1）

> 目标：前后端功能闭环，用户体验完整

6. [x] **添加会话管理接口** — 已实现重命名、删除、归档
7. [x] **ChatPage 组件拆分** — 已拆为独立聊天组件
8. [x] **添加工单创建弹窗** — 已在聊天页 InfoPanel 中接入 CreateTicketDialog
9. **修复聊天/工单页已知交互问题** — WebSocket 未连接发送保护、普通用户关闭工单入口、CreateTicketDialog 表单状态保持
10. **更新 PAGE_PLAN 已知边界** — 移除已解决的条目（auth/me、意图删除等）
11. **CI/CD Pipeline** — GitHub Actions：lint + test + build
12. **补充集成测试** — 路由端点、Repository 层
13. **补充前端测试** — `useWebSocket`、CreateTicketDialog、TicketDetailPage 权限分支
14. **修复 order_query 工具** — 对接真实业务接口或提供更完整的模拟

### Phase 3：能力增强（P2）

> 目标：PRD 剩余功能 + 运维能力

15. **Prompt 模板管理** — DB 存储、版本化、后台 CRUD
16. **文档详情/预览/下载** — MinIO 预签名 URL
17. **用户管理接口** — 列表、禁用、角色变更
18. **RAG 元数据过滤** — 按来源/标签/时间过滤检索结果
19. **BM25 索引持久化** — 启动时从 DB 加载
20. **Redis Streams 异步任务** — 文档索引异步化
21. **Grafana 预置看板** — 基于现有 Prometheus 指标
22. **前端 Toast 系统** — 操作反馈通知
23. **E2E 测试** — 关键用户流程

### Phase 4：运营优化（P3）

24. **敏感数据脱敏**
25. **邮件通知（工单变更）**
26. **审计日志存储与查询**
27. **Kubernetes manifests**
28. **前端 i18n**
29. **消息虚拟滚动**

---

## 8. 技术债务

| 项目 | 影响 | 建议 |
|------|------|------|
| LangGraph 依赖未使用 | 包体积 | 从 pyproject.toml 移除，或替换自建 AgentGraph |
| `search_order` 硬编码模拟 | 功能不完整 | 抽象为 Tool Protocol，注册真实实现 |
| 会话删除先提交数据库再清理 Redis | 状态不一致 | 将 Redis 清理纳入更可控的失败处理，避免“已删成功但接口报错” |
| WebSocket 发送未做排队/未连接保护 | 用户体验回退 | 在前端增加连接状态保护、重试或消息队列 |
| `re` 内联 import (tools.py:71) | 代码规范 | 移到文件顶部 |
| PRD 写 Vue 3 前端，实际用 React | 文档偏差 | 更新 PRD 前端选型章节 |
| 模块级单例 (`llm_client`, `bm25_index`) | 测试困难 | 改为依赖注入 |
