# Agent Cognitive Harness

> 最后核对：2026-05-20（对源码 `src/askflow/agent/harness.py`）

AskFlow 的智能体执行链路由 `IntentClassifier`、`AgentGraph` 和各业务节点完成。`CognitiveHarness` 是包在执行链路外侧的一层确定性规范，用来让 Agent 服务更可控、更容易维护——把"输入是否合规、走哪条 route、输出长度上限"这类规则从业务节点里拎出来，交给一个无依赖、可单测的策略类统一处理。

本文是 harness 的实现解释；权威契约请看 [`AGENTS.md`](../AGENTS.md) §4。

## 设计目标

- **输入可控**：统一裁剪历史上下文、拒绝空输入、限制单次问题长度、拦截 prompt 控制类请求。
- **路由可控**：对意图路由结果做白名单校验，并对低置信度请求强制澄清。
- **输出可控**：限制非流式与流式回复长度，避免空回复直接返回给用户。
- **审计可追踪**：为每次处理生成 `run_id`、策略版本、路由、原因和 flags，落到 `messages.extra.harness_trace`（JSONB）供 Admin 分析。

## 执行位置

核心实现位于 `src/askflow/agent/harness.py`，策略字段集中在 `CognitiveHarnessPolicy`（frozen dataclass，`version="askflow-cognitive-harness-v1"`）。

`AgentService.process()` 一轮的实际顺序：

1. `harness.prepare(question, history, user_id, conversation_id)` — 规整输入；命中硬拒绝条件直接 `action="stop"` 返回 `HarnessDecision`，由 service 走 `_state_token_stream` 把固定话术推出去。
2. `classify_node(state, classifier)` — 跑意图分类（规则 + LLM 二次判断）。
3. `_load_route_map()` — 拉取 DB 动态路由配置（60s TTL + Redis pub/sub 失效 + epoch 守护）。
4. `route_by_intent(state, route_map)` — 给出**候选 route**（数据驱动 + 内置兜底）。
5. `harness.choose_route(state, candidate_route)` — 二次校验：白名单 + 低置信度（`< low_confidence_threshold=0.5`）→ `clarify`。
6. 分支：
   - `route == "rag"` → `rag_stream_node` 直拿 `(token_stream, sources)`，`harness.wrap_stream(token_stream)` 包一层流式长度约束后返回。
   - 其他 route → `AgentGraph.run(state, ...)` 执行 `ticket / handoff / tool / clarify` 节点 → `harness.finalize_state(state)` 给非流式输出兜底。

`AgentState.harness_trace` 在每个工作点累积写入；最终由 `chat/service.py::process_user_message` 写到 `messages.extra.harness_trace`。

## 策略字段

| 字段 | 默认值 | 用途 |
|---|---|---|
| `version` | `"askflow-cognitive-harness-v1"` | 落 trace；policy bump 时区分历史样本 |
| `max_question_chars` | `2000` | 问题超长直接 `stop` |
| `max_history_messages` | `12` | 超出取末尾 12 条 + `flag=history_trimmed` |
| `max_history_content_chars` | `1200` | 单条历史超出截断 + `flag=history_content_truncated` |
| `max_response_chars` | `8000` | `finalize_state` / `wrap_stream` 共同上限 |
| `low_confidence_threshold` | `0.5` | `intent.confidence < 0.5` → 强制 `clarify` |
| `fallback_route` | `"rag"` | 候选 route 不在白名单时的兜底 |
| `allowed_routes` | `{"rag","ticket","handoff","clarify","tool"}` | 路由白名单 |
| `allowed_history_roles` | `{"user","assistant"}` | 其他角色（含 `system`）一律丢弃。人工接管的客服回复在 DB 落库为 `staff`，但写入 Redis 会话镜像时转为 `assistant`（`admin/handoff_router.py::reply`）——暖回流后 AI 才能看到人工轮次；**不要**为此扩大本白名单 |
| `prompt_control_patterns` | 5 条正则 | "ignore previous instructions" / "reveal system prompt" / 中文等价 |
| 各 fallback 文案 | 见源码 | `empty_input_response` / `too_long_response` / `prompt_control_response` / `fallback_response` / `response_truncated_notice` |

## 拦截标志（flags）速查

| flag | 来自 | 含义 |
|---|---|---|
| `question_too_long` | `prepare` | 问题超 `max_question_chars`，`action=stop` |
| `prompt_control_request` | `prepare` | 命中 prompt 控制正则，`action=stop` |
| `history_trimmed` | `prepare` | 历史条数被截断 |
| `history_content_truncated` | `prepare` | 单条历史内容被截断 |
| `history_role_dropped` | `prepare` | 历史角色非 `user`/`assistant`，被丢弃 |
| `route_not_allowed` | `choose_route` | 候选 route 不合法，回退 `fallback_route` |
| `low_confidence` | `choose_route` | 强制改写为 `clarify` |
| `empty_response_fallback` | `finalize_state` / `wrap_stream` | 节点没产生有效 token，注入 `fallback_response` |
| `response_truncated` | `finalize_state` / `wrap_stream` | 累计输出超 `max_response_chars` |

## 策略扩展

默认策略在 `CognitiveHarnessPolicy` 中维护。新增规范时优先放在 harness 层：

- 和业务节点无关的规则放在 `prepare()`、`choose_route()` 或 `finalize_state()` / `wrap_stream()`。
- 和具体业务副作用相关的逻辑仍保留在节点中，例如创建工单、转人工、工具调用。
- 新增拦截或改写规则时，同时补充 `tests/unit/test_agent_harness.py`，并在 [`AGENTS.md`](../AGENTS.md) §4 同步契约表。
- 新增 route 必须把它加进 `allowed_routes`，否则 `choose_route` 会把它直接打回 `fallback_route="rag"`。

## 审计字段

`AgentState.harness_trace` 保存本轮执行摘要，结构如下：

```jsonc
{
  "run_id": "<uuid4 hex>",
  "policy_version": "askflow-cognitive-harness-v1",
  "question_chars": 42,
  "history_messages": 6,
  "flags": ["history_trimmed", "low_confidence"],
  "action": "route",                 // prepare:"stop"|"continue" / choose_route:"route" / finalize:"complete"
  "reason": "route_override_low_confidence",
  "route": "clarify",                // choose_route 写入
  "candidate_route": "rag",          // 触发改写时用于回溯
  "intent": "faq",
  "confidence": 0.3,
  "response_chars": 128              // finalize_state 写入
}
```

`chat/service.py::_stream_agent_response` 会把整段 trace 落到 `messages.extra.harness_trace`（JSONB）；`admin/analytics.py` 通过 `harness_trace.reason` 和 `harness_trace.flags`（`jsonb_array_elements_text`）做分布聚合：

- `harness_reason_distribution`：按 `reason` 聚合所有 assistant 消息
- `harness_flag_distribution`：把 flags JSONB 数组展平后聚合
- `harness_fallback_rate` / `harness_truncate_rate`：fallback 与 truncate 命中率
- `thumbs_down_rate_7d` / `feedback_total_7d`：与 `MessageFeedback` 7 日反馈交叉看
