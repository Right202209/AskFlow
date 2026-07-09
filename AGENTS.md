# AGENTS.md — AskFlow Agent Business Contract

> Owner: Agent / Chat 子系统
> 最后核对：2026-05-20（对源码 `src/askflow/agent/*`）
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

### 3.3 工具入参未提取兜底

当前 `execute_tool` 在 `search_order` 抽不到订单号时直接返回引导文案（"请提供形如 AB12345678 的订单号"）。**待优化**：任务 `05-16-search-order-clarify-fallback` 回退到 Agent `clarify` 分支并携带会话历史。

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

逐 token 累计字符数；超过 `max_response_chars` 立刻截断并 yield `response_truncated_notice`。整段无输出时 yield `fallback_response`。**不缓存全量答复**，保持流式语义。

### 4.5 Harness 追踪与监测

- 每次决策落入 `AgentState.harness_trace`，固定包含 `run_id / policy_version / question_chars / history_messages / flags`；分支更新追加 `action / reason / route / candidate_route / intent / confidence / response_chars`；
- 持久化路径：`messages.extra.harness_trace`（JSONB）；
- Admin Dashboard 暴露 `harness_reason_distribution` / `harness_flag_distribution` / `harness_fallback_rate` / `harness_truncate_rate`（`admin/analytics.py`）。

---

## 5. Handoff 协议（最小实现，Wave 2 完善）

### 5.1 当前实现

`src/askflow/agent/nodes.py::handoff_node`：

1. `state.should_handoff = True`；
2. 若拿到 `conversation_repo` + 合法 `conversation_id`，置 `Conversation.status = transferred`；
3. 回固定话术："正在为您转接人工客服，请稍候。您的问题摘要和对话记录将一并转交给客服人员。"

`chat/service.py` 收到 `should_handoff=True` 后向 WebSocket 推 `ServerMessageType.handoff` 帧 `{transferred: True}`。

### 5.2 缺口

| 缺口 | 影响 |
|---|---|
| 摘要 API 未实现 | 话术承诺与代码不符 |
| 无人工坐席队列 | 转接后无 downstream 接单方 |
| 无超时兜底 | 用户在"转接中"黑洞里等待 |
| 无 人工 → AI 回流状态机 | 客服解决后无法把对话还给 AI 继续 |
| 前端无客服接管 UI | 客服侧零工具 |

### 5.3 计划落地（Wave 2 — 任务 `05-16-handoff-protocol`）

**`HandoffPayload` 契约**（草案，Wave 2 brainstorm 落锤）：

```python
{
    "summary": str,                   # LLM 生成的对话摘要
    "recent_messages": list[Message], # 最近 N 条原文
    "intent_history": list[str],      # 路径上的意图序列
    "user_meta": {"user_id", "role", "session_start_at", ...},
    "ticket_refs": list[str],         # 相关工单 id
}
```

**关键流程**：`handoff_node` → 摘要生成 → 入队 → 通知坐席 → `handoff_pickup_timeout_min` 内未接 → 兜底（回 AI / 升级 / 告警）。

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
| Harness | `src/askflow/agent/harness.py` |
| 状态 | `src/askflow/agent/state.py` |
| Admin intent CRUD（pub/sub publisher） | `src/askflow/admin/service.py` |
