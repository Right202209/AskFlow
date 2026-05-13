# Agent Cognitive Harness

AskFlow 的智能体执行链路由 `IntentClassifier`、`AgentGraph` 和各业务节点完成。
`CognitiveHarness` 是包在执行链路外侧的一层确定性规范，用来让 Agent 服务更可控、更容易维护。

## 设计目标

- 输入可控：统一裁剪历史上下文、拒绝空输入、限制单次问题长度。
- 路由可控：对意图路由结果做白名单校验，并对低置信度请求强制澄清。
- 输出可控：限制非流式与流式回复长度，避免空回复直接返回给用户。
- 审计可追踪：为每次处理生成 `run_id`、策略版本、路由、原因和 flags。

## 执行位置

核心实现位于 `src/askflow/agent/harness.py`。

`AgentService.process()` 的顺序为：

1. `CognitiveHarness.prepare()` 规范化输入，必要时直接拦截。
2. `classify_node()` 执行意图识别。
3. `route_by_intent()` 给出候选路由。
4. `CognitiveHarness.choose_route()` 校验或改写路由。
5. RAG 路径使用 `wrap_stream()` 约束流式输出。
6. 非 RAG 路径通过 `AgentGraph` 执行后使用 `finalize_state()` 兜底输出。

## 策略扩展

默认策略在 `CognitiveHarnessPolicy` 中维护。新增规范时优先放在 harness 层：

- 和业务节点无关的规则放在 `prepare()`、`choose_route()` 或 `finalize_state()`。
- 和具体业务副作用相关的逻辑仍保留在节点中，例如创建工单、转人工、工具调用。
- 新增拦截或改写规则时，同时补充 `tests/unit/test_agent_harness.py`。

## 审计字段

`AgentState.harness_trace` 保存本轮执行摘要。聊天入口会将摘要写入结构化日志：

- `run_id`
- `policy_version`
- `route`
- `reason`
- `flags`
- `intent`
- `confidence`
