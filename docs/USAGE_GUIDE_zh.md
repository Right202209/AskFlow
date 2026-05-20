# AskFlow 系统使用流程指南

> 最后核对：2026-05-20

本文档介绍 AskFlow 系统的端到端完整使用流程，帮助开发者、管理员和终端用户理解如何从零开始运行并使用本系统。权威细节请看：

- 工程指南：[`CLAUDE.md`](../CLAUDE.md)
- Agent 业务契约：[`AGENTS.md`](../AGENTS.md)
- 当前实现状态：[`status/STATUS.md`](status/STATUS.md)
- Harness 详解：[`AGENT_HARNESS.md`](AGENT_HARNESS.md)

## 1. 系统初始化与启动

在开始使用系统前，需要先启动相关服务并进行初始化：

1. **配置环境与拉取依赖**
   按 `README_zh.md`：`make install`（后端依赖，editable + dev extras）/ `make install-web`（前端依赖）。
2. **准备 `.env`**
   `cp .env.example .env`。模板带 `APP_ENV=development` 与占位 `SECRET_KEY`，让本地直接可用。生产部署必须把 `APP_ENV` 设为 `production` 并替换 `SECRET_KEY`，否则启动期 `_assert_production_safe_settings` 会拒绝起服务。
3. **启动基础中间件**
   `make docker-up`：PostgreSQL（5432，业务关系数据）、Redis（6379，限流 / pub/sub / 会话缓存）、ChromaDB（8100，向量索引）、MinIO（9000，文档原文件；9001 控制台）。
4. **数据库迁移与测试数据**
   - `make migrate` 执行 Alembic 迁移（当前 head：`20260519_01_ticket_open_unique`，把同用户同标题开放工单去重收敛到 DB partial unique index）。
   - `make seed` 创建默认 `admin/admin123`、`user1/user123`，并写入基础 intent_config。
   - 单独建账号：`make create-user username=... email=... password=... role=admin|agent|user`。
5. **启动前后端**
   - 后端：`make dev`（uvicorn `--factory --reload`，监听 `http://localhost:8000`）。
   - 前端：`make dev-web`（Vite，监听 `http://localhost:5173`，自动代理 `/api` + WebSocket 到后端）。

---

## 2. 知识库构建（Admin 视角）

为了让 AskFlow 的 Agent 具备回答业务问题的能力，管理员需要持续维护知识库：

1. **登录管理后台**：用 admin 账号登录 → 侧栏选择"文档管理"。
2. **上传与切分**：在"文档管理"页上传 PDF / Markdown / TXT。后端流程（`embedding/router.py` + `embedding/service.py::index_document`）：
   - `parse_file` 解析正文
   - `chunk_text` 切分为 chunk（默认 `chunk_size=500, chunk_overlap=50`）
   - `embedder.embed` 拿向量（`EMBEDDING_PROVIDER=api` 调 OpenAI 兼容接口，`local` 走 fastembed CPU ONNX）
   - 原文件 → MinIO（`put_document_bytes`）；向量 + chunk 文本 → Chroma；元数据 → Postgres `documents` 表
   - **写新 → 删旧** 顺序（per-write `generation` 毫秒时间戳）：失败也不会把旧 chunk 提前删掉造成"检索黑洞"
   - 索引完成后刷新 BM25（共享模块级 `bm25_index` 单例 + filelock pickle）
3. **Reindex**：原文件已在 MinIO，admin 触发 `POST /api/v1/embedding/documents/{doc_id}/reindex` 即可重新切分 + 重新写向量，前端 `DocumentsPage` 给了一键按钮。
4. **意图与路由配置**：在"意图管理"页配置 `intent_config`（`name` / `route_target` / 是否启用），admin 操作会触发 `invalidate_route_map_cache()` 并向 Redis `askflow:route_map:invalidate` channel 发广播，跨 worker 60s TTL 之内即刻失效。

> 旧 chunk（2026-04-17 之前写入）缺 `source` 与 `indexed_at_epoch` 字段，启用 `/api/v1/rag/query` 的 filter 时会被排除。正式启用过滤前安排一次全量 reindex 即可。

---

## 3. 智能问答与意图路由（User 视角）

普通用户进入 AskFlow 前端 `/app/chat` 后，对话请求经过以下流程：

1. **WebSocket 连接**
   前端 `useWebSocket` 走 `ws[s]://<host>/api/v1/chat/ws`，**握手成功后第一帧发送 `auth` 携带 JWT**（5 秒内未收到 auth 帧 → close 4001）。这是 2026-05-x 起的新协议，旧的 `/ws/{token}` 已在生产环境下不挂载（仅 `APP_ENV=development` 留作回归）。
2. **意图识别**（`agent/intent_classifier.py`）
   规则 + LLM 二次判断，6 类意图：`faq` / `product` / `order_query` / `fault_report` / `complaint` / `handoff`。规则给 `confidence=0.7`，与 LLM 结果比较取高者；LLM 失败兜底返回 `faq @ 0.5 + needs_clarification`。
3. **Cognitive Harness 入参拦截**（`agent/harness.py`，见 [`AGENT_HARNESS.md`](AGENT_HARNESS.md)）
   空输入 / 超 2000 字 / 命中 prompt 控制正则 → 立即停在 harness 层；历史超 12 条或单条 >1200 字会被截断；非 `user`/`assistant` 角色被丢弃。
4. **路由决策**
   `route_by_intent` 查 DB 动态路由 → 落 `_FALLBACK_ROUTES` → harness 二次校验 white-list + 置信度 → 最终 route。
5. **分支执行**
   - `rag` → 混合检索（BM25 + Chroma）→ rerank → LLM 流式作答（`wrap_stream` 限 8000 字）。sources 通过 `source` 帧推回前端，token 通过 `token` 帧逐字推。
   - `tool` → `execute_tool`：`order_query` 走 `search_order`（webhook 或 mock）；`knowledge_search`/`kb_search` 走 `search_knowledge`（RAGService top-k 拼显示）。
   - `ticket` → `TicketService.create_ticket` → `TicketRepo.create`（`INSERT ON CONFLICT DO NOTHING`，partial unique index 兜底并发去重）；通过 `ticket` 帧把 `{ticket_id, status, type, priority}` 推回前端。
   - `handoff` → 标记 `should_handoff=True`，会话状态切到 `transferred`；推 `handoff` 帧 `{transferred: true}`。
   - `clarify` → 反问用户补充信息。
6. **完成事件**
   助手消息落库（含 `intent / confidence / sources / extra.harness_trace`），推 `message_end` 帧带 `message_id`，前端拿到 message_id 后才能挂 👍/👎 按钮 → 调 `POST /api/v1/chat/messages/{id}/feedback`。

---

## 4. 人工客服与工单流转（Support Agent 视角）

AI 无法解决所有问题，AskFlow 提供完整的退路机制：

1. **触发转人工**
   - 用户主动表达 → 命中 `HANDOFF_PATTERNS`（要求 `human/agent/person` 与 `talk/speak/transfer/escalate/real/live` 上下文共现，避免误把 "talk to the AI agent" 当成转人工）。
   - 自动诊断为 `fault_report` / `complaint` → 默认 route 是 `ticket`，工单创建后自然引入客服。
2. **工单创建**
   - `ticket_node` → `TicketService.create_ticket` → `TicketRepo.create`。
   - **去重的正确性**靠 alembic `20260519_01` 的 `tickets (user_id, title) WHERE status NOT IN ('closed','resolved')` partial unique index + `ON CONFLICT DO NOTHING`；service 层 `find_duplicate(24h)` 只是 fast-path，漏判也会被 DB 兜回。
3. **客服处理**
   - `agent` / `admin` 角色登录后可见 `/admin/tickets`（系统级列表）与 `/admin/tickets/dashboard`（SLA 看板：open 总数 / 按优先级堆积 / SLA 超时数 / 最老 open 工单年龄 / 最近 7 天 created vs resolved 趋势）。
   - SLA 阈值由 `TICKET_SLA_HOURS`（默认 24h）控制，pending + processing 超过阈值即计入 `sla_breach_total`。
   - 客服可以更新 status / assignee / priority；普通用户只能把自己的工单关掉。
4. **工单关闭**
   `status` 切到 `resolved` 时 `TicketRepo.update_status` 会自动写 `resolved_at`。`closed` / `resolved` 状态的工单退出 partial unique index 范围，允许同标题再开新工单。

---

## 5. 运营分析与系统优化（Admin 视角）

长期的系统运营离不开数据支撑：

1. **看板总览**（`/admin/dashboard` ← `GET /api/v1/admin/analytics`）
   - 全局：会话 / 消息 / 工单 / 文档计数
   - 意图分布：`intent_distribution`
   - Harness 行为：`harness_reason_distribution` / `harness_flag_distribution` / `harness_fallback_rate` / `harness_truncate_rate`
   - 用户反馈：`thumbs_down_rate_7d` / `feedback_total_7d`（基于 `MessageFeedback`）
   - 平均置信度：`avg_confidence`（保留用于折线对比，已不是主信号）
2. **工单看板**（`/admin/tickets/dashboard` ← `GET /api/v1/admin/tickets/dashboard`）
   - 各状态计数 / open 按优先级 / SLA 超时数 + 最老 open 年龄 / 7 日 created vs resolved trend
3. **反馈回收**
   每条助手消息可由用户提交 `rating: -1 | 0 | 1` 与 comment（`upsert` 语义：同一用户对同一消息只保留最新）。Admin 可根据 👎 集中度反推哪些文档源 / 提示词需要优化。
4. **指标采集**
   Prometheus 抓 `/metrics`：`INTENT_CLASSIFICATION_COUNT{intent}` / `ORDER_WEBHOOK_FAILURE_COUNT{reason}` / `TICKET_COUNT{type,priority}` + 标准 ASGI 指标。
5. **迭代闭环**
   修文档 → reindex → 修 prompt（目前需重启）→ 修 intent route（admin UI 即时生效）→ 看 dashboard → 看 harness flag 集中度 → 调策略。

---

## 总结

AskFlow 的核心链路：**"数据入库 → 用户提问 → Harness 入参拦截 → 意图判定 → 路由（rag / tool / ticket / handoff / clarify）→ Harness 路由 / 输出兜底 → 解决失败则落入人工工单 → 反馈与 trace 沉淀回看板 → 反推改进"**——构成一个闭环的智能客服生态。

待补强的部分（详见 [`status/STATUS.md`](status/STATUS.md) §6）：Prompt 模板 CRUD / 异步索引管道 / 审计 + PII / Handoff 摘要 + 队列 + 超时兜底 / `out_of_scope` 意图兜底 / 前端测试框架。
