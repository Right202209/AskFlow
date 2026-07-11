# AGENTS.md — AskFlow Agent Business Contract

> Owner: Agent / Chat 子系统
> 最后核对：2026-07-10（对源码 `src/askflow/agent/*`）
> 配套文档：[`PRD.md`](PRD.md) §4.2–§4.4 / [`TRELLIS.md`](TRELLIS.md) / [`docs/status/STATUS.md`](docs/status/STATUS.md)

本文件定义 AskFlow 客服 Agent 的可执行行为契约：**意图清单 → 路由决策 → 工具签名 → Harness 策略 → Handoff 协议**。所有 `src/askflow/agent/` 修改必须与本文件双向同步；改一方而不更新另一方视为违反契约。

---

## 1. 意图分类（Intents）

由 `src/askflow/agent/intent_classifier.py::IntentClassifier.classify` 给出，规则 + LLM 二次判断混合：

| Intent label | 含义 | 关键词规则（命中即 `confidence=KEYWORD_HIT_CONFIDENCE=0.7`） | 触发举例 |
|---|---|---|---|
| `faq` | 通用 FAQ / 知识问答（`DEFAULT_INTENT`） | （无规则，LLM 兜底） | "退款政策是什么？" |
| `product` | 产品功能咨询 | （无规则，LLM 判定） | "AskFlow 支持哪些 LLM？" |
| `order_query` | 订单 / 物流 / 发货查询 | `订单 / 快递 / 物流 / 发货 / order / shipping / delivery / tracking` | "我的订单 AB12345678 到哪了？" |
| `fault_report` | 故障 / Bug / 错误报告 | `报错 / 错误 / bug / 500 / 故障 / crash / error / exception` | "页面 500 报错了" |
| `complaint` | 投诉 / 不满 / 建议 | `投诉 / 差评 / 不满 / complain / terrible / worst` | "服务太差了，要投诉" |
| `handoff` | 请求人工接管 | 9 条上下文正则（`HANDOFF_PATTERNS`），要求 `human/agent/person` 与 `talk/speak/transfer/escalate/real/live` 共现 | "转人工"、"talk to a real person" |

### 1.1 分类策略

1. **规则优先**：命中关键词或 `HANDOFF_PATTERNS` 即返回 `confidence=0.7`；规则 `confidence ≥ 0.9` 时直接返回（当前阈值预留给未来强规则升级，不会触发）。
2. **LLM 二次判断**：调 `INTENT_PROMPT` 拿 `{intent, confidence}` JSON；与规则结果比较，置信度高者胜出。LLM 返回 `confidence < 0.7` 自动 `needs_clarification=True`。
3. **LLM 失败回退**：返回规则结果；若规则也未命中，返回 `DEFAULT_INTENT="faq"`、`confidence=0.5`、`needs_clarification=True`。
4. **歧义防护**：`handoff` 必须命中 `HANDOFF_PATTERNS`——避免 `"I want to talk to the AI agent"` / `"sales agent"` / `"human override"` 等误判。

> **提示词来源（ops-platform/01）**：LLM 二次判断用的分类提示词以 DB 模板 `intent.classifier` 为准（admin 后台「提示词模板」可热更新），`intent_classifier.py::INTENT_PROMPT` 仅作 DB 缺失/不可用时的代码兜底。模板**必须保留 `{message}` 占位符且六个意图标签不可删改**——写入时服务层 `content.format(...)` 渲染校验只能拦住占位符错拼，删标签不会报错但会让分类退化，前端编辑页对该 key 显式警示。同理 `clarify` 澄清话术走模板 `agent.clarify`（`nodes.py::CLARIFY_RESPONSE` 为兜底）。

### 1.2 待实现：`out_of_scope` 兜底

当前 6 类意图不覆盖完全系统外的问题（如"今天天气怎么样"、"帮我写邮件"），会被强塞进 `faq` → RAG 检索空 → 回答幻觉。任务 `05-16-intent-out-of-scope-fallback` 追踪此缺口（新增标签 / prompt 拒答 / harness `out_of_scope_fallback_route`）。

---

## 2. 路由决策（Router）

由 `src/askflow/agent/nodes.py::route_by_intent` 给出，按以下顺序决策：

```
1. 无 intent                                  → "rag"            （安全默认）
2. needs_clarification && confidence < 0.5    → "clarify"        （置信度兜底）
3. DB 动态 route_map[label]                   （admin 可配；60s TTL + Redis pub/sub 失效；epoch 守护）
4. _FALLBACK_ROUTES[label]                    （内置兜底，见下表）
5. 落入 VALID_ROUTES 外的 target              → "rag" + warning  （防御性兜底）
```

> 注：`route_by_intent` 的结果会被 `CognitiveHarness.choose_route` 二次校验，置信度 < 0.5 时会再次强制改写为 `clarify`（与第 2 步语义重复，是有意的双层兜底）。

### 2.1 内置兜底路由表 `_FALLBACK_ROUTES`

| Intent | Route node | 节点行为 |
|---|---|---|
| `faq` | `rag` | `rag_node` / `rag_stream_node` — 混合检索 + LLM 流式作答 |
| `product` | `rag` | 同上 |
| `order_query` | `tool` | `tool_node` → `execute_tool("order_query")` → `search_order` |
| `fault_report` | `ticket` | `ticket_node` — `type=fault_report`, `priority=high` |
| `complaint` | `ticket` | `ticket_node` — `type=complaint`, `priority=high` |
| `handoff` | `handoff` | `handoff_node` — 置 `state.should_handoff=True` + 会话状态切到 `transferred` |
| 其他 | `rag` | 默认 |

### 2.2 合法路由集 `VALID_ROUTES`

```python
{"rag", "ticket", "handoff", "clarify", "tool"}
```

新增 route 必须：

1. 在 `nodes.py::VALID_ROUTES` 中加入；
2. 在 `agent/graph.py::AgentGraph.run` 增加对应分支；
3. 在 `harness.py::CognitiveHarnessPolicy.allowed_routes` 同步白名单；
4. 在 `intent_classifier.py::INTENT_PROMPT` 同步意图清单（如有新 intent）；
5. 同步本文件 §1 与 §2.1。

### 2.3 DB 动态覆盖

- 表：`intent_route_mapping`（admin 后台 `POST/PUT/DELETE /api/v1/admin/intents` 可改）
- 进程缓存：`agent/service.py` 模块级 `_route_map_cache` + `ROUTE_MAP_CACHE_TTL_SECONDS=60`
- 跨 worker 失效：Redis pub/sub channel `askflow:route_map:invalidate`，`main.py` lifespan 启动期由 `start_route_map_subscriber()` 挂上后台订阅协程
- **Epoch 守护**：`_load_route_map` 在打 DB 前快照 `_route_map_invalidate_seq`，加载完成后比对——序号变化即丢弃本次结果（防止"加载中收到 invalidate，把刚清掉的缓存又写回旧版本"的竞态）
- 健壮性追踪：`05-16-route-pubsub-resilience`（subscriber 重连 / 强制广播 / lag 监控）

---

## 3. 工具签名（Tools）

工具注册表 `src/askflow/agent/tools.py::TOOLS`；执行入口 `execute_tool`。

### 3.1 现有工具

| Name | Trigger intents | 入参 | 出参 | 错误兜底 |
|---|---|---|---|---|
| `search_order` | `order_query` | `order_id: str`（由 `ORDER_ID_PATTERN = r"\b[A-Z]{2,4}\d{6,}\b"` 从 question 抽取） | `{order_id, status, tracking, estimated_delivery, data_source, fallback_reason?}` | 1) 未配 `ORDER_LOOKUP_WEBHOOK_URL` → mock；2) timeout/HTTP/异常 → mock + `fallback_reason` 并递增 `ORDER_WEBHOOK_FAILURE_COUNT{reason=timeout|http_<status>|other}` |
| `search_knowledge` | `knowledge_search` / `kb_search`（admin 可配的 intent name） | `query: str, rag_service, top_k=5` | `list[{title, source, content, score}]` top-k | 缺 `rag_service` 或 RAG 异常 → 空列表 + warning |

### 3.2 意图 → 工具映射 `_INTENT_TOOL_MAP`

```python
{
    "order_query": "search_order",
    "knowledge_search": "search_knowledge",
    "kb_search": "search_knowledge",
}
```

### 3.3 槽位填充（多轮工具入参收集）

`search_order` 抽不到订单号不再是死胡同：`execute_tool` 返回追问文案 + `needs_slot="order_id"`，`tool_node` 经 `agent/slots.py` 把挂起记录持久化到 `conversations.metadata` 的 `pending_tool` 键（durable、跨 worker；结构 `{tool, slot, intent, turns_waited}`），下一轮由 `AgentService.process` 在**分类之前**做续跑判定：

| 来消息 | 决策 |
|---|---|
| 命中 `ORDER_ID_PATTERN` | **续跑**：跳过分类，`intent = (pending.intent, RESUME_SLOT_CONFIDENCE=0.9)`（高于 harness 低置信线 0.5，防止被改写成 clarify），候选路由 `tool`；工具成功后清档 |
| 未命中 → 分类为**同一意图** | `turns_waited` +1 继续追问；达到 `MAX_SLOT_TURNS=3` 清档转 `clarify`（不无限追问） |
| 未命中 → 分类为**不同意图**且置信度 ≥ `ABANDON_CONFIDENCE=0.7` | **弃槽**：清档，按新意图正常路由（`handoff` 等自然接管） |
| 未命中 → 不同意图但置信度不足 | 保留槽位走正常路由，下一轮补号仍可续跑 |

正则先于分类是刻意的：裸订单号（"AB12345678"）没有关键词特征，抽取不能依赖分类结果。清档一律是 merge-patch（只删 `pending_tool` 键，不覆盖整个 metadata）。任务 `05-16-search-order-clarify-fallback` 由此收口。

### 3.4 新增工具的扩展点

1. 在 `tools.py::TOOLS` 注册 `{name: async_handler}`，返回 `{display: str, ...}`；
2. 在 `_INTENT_TOOL_MAP` 添加 `intent → tool` 映射（也支持 admin 后台动态配置 `route_target=tool`）；
3. 在 `execute_tool` 增加 mapped 分支（如需特殊参数抽取/格式化）；
4. 同步本文件 §3.1。

### 3.5 HTTP client 生命周期

`search_order` 的 `httpx.AsyncClient` 是模块级单例，由 `main.py` lifespan 通过 `init_http_client()` / `close_http_client()` 管控；测试场景未启 lifespan 时按需懒建。

---

## 4. Cognitive Harness 策略

Harness 是绕 Agent 图的确定性安全护栏，定义在 `src/askflow/agent/harness.py::CognitiveHarnessPolicy`（`version="askflow-cognitive-harness-v1"`）。四个工作点：

> **提示词模板边界（ops-platform/01 D3）**：可热更新的 DB 模板只覆盖 RAG（`rag.system`/`rag.context`/`rag.fallback_no_results`/`rag.fallback_llm_down`）、分类（`intent.classifier`）、澄清（`agent.clarify`）六个 key。**Harness 自身的文案（硬拒绝提示、`fallback_response`、`response_truncated_notice`、注入拒绝语）是代码常量，不进模板表**——它们是安全护栏的一部分，必须随代码版本走、可被测试锚定，不能被运营在线改写。

### 4.1 `prepare()` — 入参规整与硬拒绝

| 触发条件 | 动作 | 响应文案 |
|---|---|---|
| 问题为空 | `stop` + `reason=empty_input` | `empty_input_response` |
| 问题 > `max_question_chars=2000` | `stop` + `flag=question_too_long` | `too_long_response` |
| 命中 `prompt_control_patterns`（"ignore previous instructions" / "reveal system prompt" / 中文等价 5 条正则） | `stop` + `flag=prompt_control_request` | `prompt_control_response` |
| 历史超 `max_history_messages=12` | 截取末尾 12 条 + `flag=history_trimmed` | continue |
| 单条历史超 `max_history_content_chars=1200` | 截断 + `flag=history_content_truncated` | continue |
| 历史角色不在 `allowed_history_roles={"user","assistant"}` | 丢弃 + `flag=history_role_dropped` | continue |

### 4.2 `choose_route()` — 路由二次校验

| 触发条件 | 动作 | reason |
|---|---|---|
| 候选 route 不在 `allowed_routes={"rag","ticket","handoff","clarify","tool"}` | 强制 → `fallback_route="rag"` + `flag=route_not_allowed` | `route_fallback_not_allowed` |
| `intent.confidence < low_confidence_threshold=0.5` | 强制 → `"clarify"` + `flag=low_confidence` | `route_override_low_confidence` |
| 其他 | 直通候选 route | `route_accepted` |

### 4.3 `finalize_state()` — 非流式分支输出约束

| 触发条件 | 动作 |
|---|---|
| `response_tokens` 全空 | 写入 `fallback_response` + `flag=empty_response_fallback` |
| 累计输出 > `max_response_chars=8000` | 截断并附 `response_truncated_notice` + `flag=response_truncated` |

### 4.4 `wrap_stream()` — 流式分支输出约束

逐 token 累计字符数；超过 `max_response_chars` 立刻截断并 yield `response_truncated_notice`。整段无输出时 yield `fallback_response`。**不缓存全量答复**，保持流式语义。注意：RAG 回答现携带 `[n]` 行内引用标记（编号与 sources[].index 对齐），截断可能切掉尾部引用——自检层（`rag/verifier.py`）对"零可查引用"按 `skipped` 处理而非报错。

### 4.5 Harness 追踪与监测

- 每次决策落入 `AgentState.harness_trace`，固定包含 `run_id / policy_version / question_chars / history_messages / flags`；分支更新追加 `action / reason / route / candidate_route / intent / confidence / response_chars`；
- `rag` 路由额外追加检索证据字段：`retrieval_confidence`（0..1，按检索通道归一化）与 `retrieval_channel`（`vector | bm25 | fused | empty`）；检索证据不足触发确定性拒答时追加 flag `weak_retrieval_refusal`（判定逻辑集中在 `rag/grounding.py`，拒答直接返回固定文案、不调 LLM，弱证据来源仍随响应下发）。该拒答是**检索后**的证据判定，与 §1.2 计划中的 `out_of_scope`（分类期、检索前）互补而非替代；
- 回答后证据自检（`rag/verifier.py`）新增 flag：`verify_skipped`（自检超时/失败/无引用可查）与 `invalid_citations`（答案出现越界 `[n]` 标记）；自检结论持久化在 `messages.extra.verification`，回答置信度在 `messages.extra.answer_confidence`（`chat/confidence.py` 计算，`messages.confidence` 列仍表示**意图**置信度）；
- 槽位续跑轮追加 flag `slot_resume`（`agent/slots.py`，§3.3）——admin 的 harness flag 分布因此能统计多轮槽位填充的续跑量；
- 持久化路径：`messages.extra.harness_trace`（JSONB）；
- Admin Dashboard 暴露 `harness_reason_distribution` / `harness_flag_distribution` / `harness_fallback_rate` / `harness_truncate_rate`（`admin/analytics.py`）。
- **消费者契约（knowledge-loop 知识缺口雷达）**：`knowledge/gap_recorder.py` 作为**被动消费者**读取 `harness_trace` 的 `route` / `reason` / `flags` 与 `retrieval_confidence` 字段来识别失败信号（`clarify` / `rag_refusal` / `low_retrieval_score` / `handoff`），不改变任何路由行为。这三个 key 因此成为稳定读契约：改名或改语义前需同步 `gap_recorder.py`。拒答识别复用 `rag/grounding.py::REFUSAL_RESPONSE`、`rag/prompt_builder.py::NO_RESULTS_REFUSAL`、`harness` 的 `fallback_response` 三个常量（非子串启发式）。捕获全程 best-effort，异常只记 `gap_record_failed` 不回抛聊天主流程。

---

## 5. Handoff 协议（已实现，agent-real-handoff/02）

### 5.1 转接轮（AI → 人工）

`src/askflow/agent/nodes.py::handoff_node`：

1. `state.should_handoff = True`；
2. 若拿到 `conversation_repo` + 合法 `conversation_id`，置 `Conversation.status = transferred`；
3. 若拿到 `handoff_service`，调 `HandoffService.enqueue(state)` 入队（失败只记 `handoff_enqueue_failed`，不影响转接状态本身）；
4. 回固定话术："正在为您转接人工客服，请稍候。您的问题摘要和对话记录将一并转交给客服人员。"

`chat/turns.py` 收到 `should_handoff=True` 后向 WebSocket 推 `handoff` 帧 `{transferred: True}`（前端据此进入"排队等待认领"状态）。

### 5.2 载荷与摘要（`agent/handoff.py`）

`HandoffSession.payload`（JSONB）实际形状：

```python
{
    "recent_messages": [{"role", "content", "created_at"}],  # MessageRepo.list_recent，最近 HANDOFF_RECENT_MESSAGES=10 条（durable，不用 Redis 镜像）
    "intent_history": list[str],                             # 消息序列上去重后的意图路径
    "user_meta": {"user_id", "session_start_at"},
    "ticket_refs": list[str],                                # 同会话关联工单 id
    "flags": ["summary_failed"?],                            # 摘要失败时追加
}
```

**摘要失败策略（D4）**：摘要同步生成但带硬超时 `HANDOFF_SUMMARY_TIMEOUT_S=8`；超时/LLM 异常一律降级为"仅转录"载荷（`summary=""` + `payload.flags += ["summary_failed"]`），转接绝不因 LLM 阻塞或失败。

### 5.3 会话生命周期与状态机

`HandoffSession.status`: `queued → claimed → resolved | returned`；`queued → timed_out`（超时清扫）。

- **一会话一开放接管**：partial unique index `uniq_open_handoff_per_conversation`（`WHERE status IN ('queued','claimed')`，alembic `20260710_01`）+ `HandoffRepo.create` 的 `ON CONFLICT DO NOTHING` → 回查 `find_open_by_conversation`。重复转接收敛到已有 open session。
- **认领竞态**：`HandoffRepo.claim` 是条件 UPDATE（`WHERE status='queued'`），输家收 409（`ConflictError`）。回复/关闭仅限当前 `assignee`。

### 5.4 transferred 网关与 staff 角色镜像

- **网关**（`chat/service.py::_handle_transferred_message`）：会话处于 `transferred` 时，用户消息照常落库 + 写 Redis 会话镜像，但**绝不派发给 AI**；回 `handoff_update` 回执，客服已认领则经推送桥转发 `{status, new_user_message}`。
- **staff 镜像为 assistant（D8）**：客服回复 DB 落库为 `Message(role=staff)`（渲染/审计可区分人机），但 Redis 会话镜像写成 `assistant`——§4.1 的 `allowed_history_roles={"user","assistant"}` 会丢弃其他角色，若按 `staff` 镜像，暖回流后 AI 将看不到人工说过什么。**不要**为此扩大 harness 白名单。
- **跨 worker 推送桥**（`chat/push.py`）：Redis 频道 `askflow:chat:push`，客服操作（认领/回复/关闭）与超时通知经 `publish_user_push` 送达用户全部在线连接；帧类型 `staff_message`（`{content, staff_name}`）与 `handoff_update`（`{status, ticket_id?}`）。

### 5.5 超时兜底与暖回流

- **超时清扫**：lifespan 后台任务每 `HANDOFF_SWEEP_INTERVAL_S=60` 秒执行 `sweep_expired`（`FOR UPDATE SKIP LOCKED`，多 worker 不重复升级）。`queued` 超过 `handoff_pickup_timeout_min`（settings，默认 10 分钟）：经 **`TicketRepo.create`**（§6 强制路径）创建 `handoff_timeout` 高优工单 → 标 `timed_out` → **会话回 `active`（AI 恢复应答，避免既无客服也无 AI 的黑洞）** → 推 `handoff_update {status: timed_out, ticket_id}` → `HANDOFF_TIMEOUT_COUNT` 计数。
- **暖回流**：`resolve` 端点把 `claimed` 关闭为 `resolved`（默认会话回 `active`，`close_conversation=true` 则 `closed`）或 `returned`（显式"交还 AI"）。回流后 AI 的下一轮能在历史中看到镜像后的人工轮次（§5.4）。

### 5.6 客服收件箱

`/api/v1/admin/handoffs`（`admin/handoff_router.py`，staff 角色）：列表（按 status 过滤）/ 详情（session + 全量消息）/ 认领 / 回复 / 关闭。前端 `web/src/pages/Admin/HandoffsPage.tsx`；用户侧横幅与 staff 气泡在 `ChatPage.tsx` / `MessageBubble.tsx`（`chatStore.handoffStatus` 驱动）。

---

## 6. Ticket 一致性约定（与 `agent` 协作）

`ticket_node` 调用 `ticket_service.create_ticket(...)` → `TicketRepo.create(...)`。**禁止**在新写路径里走 `db.add(Ticket(...))`——`TicketRepo.create` 用 `INSERT ... ON CONFLICT DO NOTHING` 走 partial unique index `uniq_open_user_title`（alembic `20260519_01`，`WHERE status NOT IN ('closed','resolved')`），冲突时回查 `find_open_duplicate` 返回赢家，是并发下唯一的正确去重路径。`TicketService.find_duplicate` 是性能 fast-path，不再是正确性边界。详见 [`docs/audits/IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md`](docs/audits/IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md)。

---

## 7. 修改约定

1. **代码先于契约**：先改 `src/askflow/agent/*` 跑 `make test` 通过，再回头同步本文件，避免契约漂移。
2. **契约先于代码**：新增意图 / route / tool 等增量能力，先在本文件落契约 → 在对应 Trellis 子任务 brainstorm → 实现 → 回标本文件版本。
3. **不要在本文件描述实现细节**：行号 / 函数名 / 复杂分支留在代码与 docstring，本文件只保留契约层语义。

---

## 8. 相关源码索引

| 主题 | 文件 |
|---|---|
| 意图分类 | `src/askflow/agent/intent_classifier.py` |
| Agent 节点 | `src/askflow/agent/nodes.py` |
| Agent 图 | `src/askflow/agent/graph.py` |
| Agent 服务（orchestrator + route map 缓存） | `src/askflow/agent/service.py` |
| 工具注册 | `src/askflow/agent/tools.py` |
| 槽位填充（pending_tool 读写 + 续跑判定） | `src/askflow/agent/slots.py` |
| Harness | `src/askflow/agent/harness.py` |
| RAG 证据强度评估（弱检索拒答） | `src/askflow/rag/grounding.py` |
| RAG 证据自检（引用核查） | `src/askflow/rag/verifier.py` |
| 回答置信度 | `src/askflow/chat/confidence.py` |
| 知识缺口雷达（harness trace 消费者） | `src/askflow/knowledge/gap_recorder.py` |
| Handoff 服务（载荷/摘要/入队/超时清扫） | `src/askflow/agent/handoff.py` |
| Handoff 会话仓储（认领/关闭/清扫 SQL） | `src/askflow/repositories/handoff_repo.py` |
| 客服收件箱 API | `src/askflow/admin/handoff_router.py` |
| 跨 worker 用户推送桥 | `src/askflow/chat/push.py` |
| 一轮 agent 交互驱动（事件推送半边） | `src/askflow/chat/turns.py` |
| 状态 | `src/askflow/agent/state.py` |
| Admin intent CRUD（pub/sub publisher） | `src/askflow/admin/service.py` |
| 配置缓存基类（TTL + epoch + pub/sub） | `src/askflow/core/config_cache.py` |
| 提示词读路径（get_prompt + 兜底常量） | `src/askflow/core/prompts.py` |
| 提示词模板仓储（版本追加/激活） | `src/askflow/repositories/prompt_repo.py` |
| 提示词模板 CRUD API | `src/askflow/admin/prompt_router.py` |
