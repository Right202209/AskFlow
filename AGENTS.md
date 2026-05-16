# AGENTS.md — AskFlow Agent Business Contract

> Owner: Agent / Chat 子系统
> 最后核对：2026-05-16（对源码 `src/askflow/agent/*`）
> 配套文档：[`PRD.md`](PRD.md) §4.2–§4.4 / [`TRELLIS.md`](TRELLIS.md) / [`docs/status/STATUS.md`](docs/status/STATUS.md)

本文件定义 AskFlow 客服 Agent 的可执行行为契约：**意图清单 → 路由决策 → 工具签名 → Harness 策略 → Handoff 协议**。所有 Agent 节点（`src/askflow/agent/`）的修改必须与本文件双向同步；修改一方而不更新另一方视为违反契约。

---

## 1. 意图分类（Intents）

意图由 `src/askflow/agent/intent_classifier.py` 给出，结合**关键词规则**与 **LLM 二次判断**：

| Intent label | 含义 | 关键词规则（命中即 `confidence=0.7`） | 触发举例 |
|---|---|---|---|
| `faq` | 通用 FAQ / 知识问答（默认意图） | （无规则，LLM 兜底） | "退款政策是什么？" |
| `product` | 产品功能咨询 | （无规则，LLM 判定） | "AskFlow 支持哪些 LLM？" |
| `order_query` | 订单 / 物流 / 发货查询 | `订单 / 快递 / 物流 / 发货 / order / shipping / delivery / tracking` | "我的订单 AB12345678 到哪了？" |
| `fault_report` | 故障 / Bug / 错误报告 | `报错 / 错误 / bug / 500 / 故障 / crash / error / exception` | "页面 500 报错了" |
| `complaint` | 投诉 / 不满 / 建议 | `投诉 / 差评 / 不满 / complain / terrible / worst` | "服务太差了，要投诉" |
| `handoff` | 请求人工接管 | 9 条上下文正则（见 `HANDOFF_PATTERNS`），要求 `human/agent/person` 与 `talk/speak/transfer/escalate/real/live` 共现 | "转人工"、"talk to a real person" |

### 1.1 分类策略

1. **规则优先**：命中关键词规则即返回 `confidence=0.7`；规则 `confidence ≥ 0.9` 时直接返回（当前阈值留给未来规则升级使用，目前 `KEYWORD_HIT_CONFIDENCE=0.7` 不会直接 return）。
2. **LLM 二次判断**：调 `INTENT_PROMPT`（见同文件）拿 `{intent, confidence}` JSON；与规则结果比较，置信度高者胜出。
3. **LLM 失败回退**：返回规则结果；若规则也未命中，返回 `DEFAULT_INTENT=faq`、`confidence=0.5`、`needs_clarification=True`。
4. **歧义防护**：`handoff` 必须命中专用上下文正则——避免 `"I want to talk to the AI agent"` / `"sales agent"` / `"human override"` 等误判。

### 1.2 待实现：`out_of_scope` 兜底（Wave 1 子任务 `intent-out-of-scope-fallback`）

当前 6 类意图不覆盖完全系统外的问题（如"今天天气怎么样"、"帮我写邮件"），会被强塞进 `faq` → RAG 检索空 → 回答幻觉。**Wave 1 已立 `05-16-intent-out-of-scope-fallback` 任务**追踪此缺口：
- 新增 `out_of_scope` 标签；
- prompt 明确拒答 + 引导转人工或换问法；
- Harness 配置 `out_of_scope_fallback_route`。

---

## 2. 路由决策（Router）

路由由 `src/askflow/agent/nodes.py::route_by_intent` 给出，按以下顺序决策：

```
1. 无 intent           → "rag"        （安全默认）
2. needs_clarification && confidence < 0.5
                        → "clarify"   （置信度兜底）
3. DB 动态 route_map[label]            （admin 可配，60s TTL + Redis pub/sub 失效）
4. _FALLBACK_ROUTES[label]             （内置兜底，见下表）
5. 非 VALID_ROUTES 的 target           → "rag" + warning（防御性兜底）
```

### 2.1 内置兜底路由表 `_FALLBACK_ROUTES`

| Intent | Route node | 节点行为 |
|---|---|---|
| `faq` | `rag` | `rag_node` / `rag_stream_node` — 命中检索 + LLM 流式作答 |
| `product` | `rag` | 同上 |
| `order_query` | `tool` | `tool_node` → `execute_tool("order_query")` → `search_order` |
| `fault_report` | `ticket` | `ticket_node` — type=fault_report, priority=high |
| `complaint` | `ticket` | `ticket_node` — type=complaint, priority=high |
| `handoff` | `handoff` | `handoff_node` — 标记 `should_handoff=True` + 会话状态置 `transferred` |

其他默认（如未匹配 intent）→ `rag`。

### 2.2 合法路由集 `VALID_ROUTES`

```python
{"rag", "ticket", "handoff", "clarify", "tool"}
```

新增 route 必须：
1. 在 `nodes.py::VALID_ROUTES` 中加入；
2. 在 `agent/graph.py::AgentGraph` 增加对应分支；
3. 在 `intent_classifier.py::INTENT_PROMPT` 同步意图清单；
4. 同步本文件 §1 与 §2.1。

### 2.3 DB 动态覆盖

- 表：`intent_route_mapping`（admin 后台可改）
- 进程缓存：`agent/service.py:31-47` 字典 + 60s TTL
- 跨 worker 失效：Redis pub/sub channel `route_map_invalidate`（`main.py` 启动期订阅）
- 健壮性追踪：见 `05-16-route-pubsub-resilience` 任务（subscriber 重连 / 强制广播 / lag 监控）

---

## 3. 工具签名（Tools）

工具注册表在 `src/askflow/agent/tools.py::TOOLS`；执行入口为 `execute_tool`。

### 3.1 现有工具

| Name | Trigger intents | 入参 | 出参 | 错误兜底 |
|---|---|---|---|---|
| `search_order` | `order_query` | `order_id: str` (由 `ORDER_ID_PATTERN = \b[A-Z]{2,4}\d{6,}\b` 从 question 抽取) | `{order_id, status, tracking, estimated_delivery, data_source, fallback_reason?}` | 1) 未配 webhook → mock；2) timeout/HTTP/异常 → mock + `fallback_reason` 并递增 `ORDER_WEBHOOK_FAILURE_COUNT{reason=...}` |
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

当前实现：`search_order` 未抽到订单号时直接返回引导文案（"请提供形如 AB12345678 的订单号"）。
**待优化**：见 `05-16-search-order-clarify-fallback` 任务——回退到 Agent `clarify` 分支并携带会话历史，而非工具层硬返回。

### 3.4 新增工具的扩展点

1. 在 `tools.py::TOOLS` 注册 `{name: async_handler}`；
2. 实现 handler，返回 `{display: str, ...other fields}` 格式；
3. 在 `_INTENT_TOOL_MAP` 添加 `intent → tool` 映射（也支持 admin 后台动态配置 `route_target=tool`）；
4. 在 `execute_tool` 增加 mapped 分支（如需特殊参数抽取/格式化）；
5. 同步本文件 §3.1。

---

## 4. Cognitive Harness 策略

Harness 是绕 Agent 图的确定性安全护栏，定义在 `src/askflow/agent/harness.py::CognitiveHarnessPolicy`。三个工作点：

### 4.1 `prepare()` — 入参规整与硬拒绝

| 触发条件 | 动作 | 响应 |
|---|---|---|
| 问题为空 | `stop` | `empty_input_response` |
| 问题 > `max_question_chars=2000` | `stop` + `flag=question_too_long` | `too_long_response` |
| 命中 `prompt_control_patterns`（"ignore previous instructions" / "reveal system prompt" / 中文等价） | `stop` + `flag=prompt_control_request` | `prompt_control_response` |
| 历史超 `max_history_messages=12` 或单条超 `max_history_content_chars=1200` | 截断 + `flag=history_trimmed/history_content_truncated` | continue |
| 历史角色不在 `{user, assistant}` | 丢弃 + `flag=history_role_dropped` | continue |

### 4.2 `choose_route()` — 路由二次校验

| 触发条件 | 动作 |
|---|---|
| 候选 route 不在 `allowed_routes={rag, ticket, handoff, clarify, tool}` | 强制 → `fallback_route=rag` + `flag=route_not_allowed` |
| `intent.confidence < low_confidence_threshold=0.5` | 强制 → `clarify` + `flag=low_confidence` |

### 4.3 `finalize_state()` / `wrap_stream()` — 输出约束

| 触发条件 | 动作 |
|---|---|
| `response_tokens` 全空 | 写入 `fallback_response` + `flag=empty_response_fallback` |
| 输出 > `max_response_chars=8000` | 截断 + `response_truncated_notice` + `flag=response_truncated` |

### 4.4 Harness 追踪与监测

- 每次决策落入 `state.harness_trace`（含 `run_id / policy_version / flags / reason / route / candidate_route`）；
- 持久化到 `messages.extra.harness_trace`；
- Admin Dashboard 已暴露 `harness_reason_distribution` / `harness_flag_distribution`（见 `admin/analytics.py`）。

---

## 5. Handoff 协议（占位，待 Wave 2 完成）

### 5.1 当前实现（最小）

`src/askflow/agent/nodes.py::handoff_node` 仅做两件事：
1. 将 `Conversation.status` 置为 `transferred`；
2. 回固定话术："正在为您转接人工客服，请稍候。您的问题摘要和对话记录将一并转交给客服人员。"

### 5.2 缺口

| 缺口 | 影响 |
|---|---|
| 摘要 API 未实现 | 话术承诺与代码不符 |
| 无人工坐席队列 | 转接后无 downstream 接单方 |
| 无超时兜底 | 用户在"转接中"黑洞里等待 |
| 无人工 → AI 回流状态机 | 客服解决后无法把对话还给 AI 继续 |
| 前端无客服接管 UI | 客服侧零工具 |

### 5.3 计划落地（Wave 2，任务 `05-16-handoff-protocol`）

**`HandoffPayload` 契约**（待 Wave 2 brainstorm 拍板，先行声明字段）：

```python
{
    "summary": str,                   # LLM 生成的对话摘要
    "recent_messages": list[Message], # 最近 N 条原文
    "intent_history": list[str],      # 路径上的意图序列
    "user_meta": {"user_id", "role", "session_start_at", ...},
    "ticket_refs": list[str],         # 相关工单 id
}
```

**关键流程**：handoff_node → 摘要生成 → 入队 → 通知坐席 → `handoff_pickup_timeout_min` 内未接 → 兜底（回 AI / 升级 / 告警）。

---

## 6. 修改约定

1. **代码先于契约**：先改 `src/askflow/agent/*` 并跑 `make test` 通过，再回头同步本文件，避免契约漂移。
2. **契约先于代码**：新增意图 / route / tool 等增量能力，先在本文件落契约 → 在对应 Trellis 子任务 brainstorm → 实现 → 再回标本文件版本。
3. **不要在本文件描述实现细节**：行号 / 函数名 / 复杂分支应留在代码与 docstring，本文件只保留契约层语义。

---

## 7. 相关源码索引

| 主题 | 文件 |
|---|---|
| 意图分类 | `src/askflow/agent/intent_classifier.py` |
| Agent 节点 | `src/askflow/agent/nodes.py` |
| Agent 图 | `src/askflow/agent/graph.py` |
| Agent 服务 | `src/askflow/agent/service.py` |
| 工具注册 | `src/askflow/agent/tools.py` |
| Harness | `src/askflow/agent/harness.py` |
| 状态 | `src/askflow/agent/state.py` |
