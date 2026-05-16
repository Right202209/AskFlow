# AskFlow 闭环完整性 & SOP 缺口评审

> 评审日期：2026-05-16
> 评审范围：`PRD.md` / `AGENTS.md` / `docs/status/*.md` / `.trellis/spec/` + 代码现状交叉验证
> 评审视角：产品运营与流程完整性
> 关联文档：`docs/audits/PRD_AUDIT.md`、`docs/audits/DUAL_ROLE_REVIEW_2026-05-14.md`、`docs/status/UNIMPLEMENTED_2026-05-14.md`

---

## 摘要

整体闭环状态 **🟡 黄**。核心功能（Chat / RAG / Agent / Ticket / Embedding / Admin）代码已落地并通过单元 + 集成测试，但**从"需求"到"任务"到"验收"的过程闭环存在结构性断裂**，且四个关键运营 SOP（知识回流、Handoff 协议、Ticket SLA 主动引擎、审计与脱敏）处于不同程度的缺失状态。

最关键的三个发现：

1. **PRD 与 Trellis 任务体系完全脱钩**——所有功能需求均未进入 `.trellis/tasks/`，实际工作追踪散落在 `docs/status/*.md`，无法触发 Trellis 子代理流程。
2. **AGENTS.md 名不副实**——文件 21 行全部为 Trellis 元说明，未定义任何 Agent 业务行为契约。
3. **知识库回流、Handoff 协议、SLA 主动引擎三个核心 SOP 几乎从零开始**——产品故事"自动化闭环"缺最后几环。

---

## 一、需求 → 任务 → 实现 → 验收 闭环矩阵

| PRD 需求 | Trellis 任务 | 实现位置 | 自动化验收 | 闭环状态 |
|---|---|---|---|---|
| §4.1 RAG 智能问答 | ❌ 无 | `src/askflow/rag/service.py` 等 | `tests/integration/test_rag_pipeline.py` | 🟡 代码完整、无任务追踪 |
| §4.2 意图识别（6 类） | ❌ 无 | `src/askflow/agent/intent_classifier.py`（规则 + 模型） | `tests/unit/test_agent.py` | 🟡 同上 |
| §4.3 Router Agent | ❌ 无 | `src/askflow/agent/graph.py` + `_FALLBACK_ROUTES` + DB 动态路由 | `test_intent_invalidation.py` | 🟡 同上 |
| §4.4 聊天 WS 流式 | ❌ 无 | `src/askflow/chat/router.py` + `chat/service.py` | WS 集成用例 | 🟡 同上 |
| §4.5 工单闭环 | ❌ 无 | `src/askflow/ticket/*` + `admin/analytics.py` Dashboard | `test_ticket_flow.py` | 🟡 缺 SLA 主动引擎（见 S4） |
| §4.6 知识 / 意图管理 | ❌ 无 | `src/askflow/admin/*` | 单元测试 | 🟢 |
| §4.6 Prompt 模板管理 | ❌ 无 | **不存在** | 无 | 🔴 完全缺失（UNIMPLEMENTED #1） |
| §5.1 安全（JWT / RBAC / 限流） | ❌ 无 | `src/askflow/core/auth.py` + `rate_limiter.py` | 单元测试 | 🟢 |
| §5.2 数据治理（审计 + 脱敏） | ❌ 无 | **不存在**（grep `audit / redact / PII` = 0 命中） | 无 | 🔴 完全缺失（UNIMPLEMENTED #2） |
| §5.3 可观测性 | ❌ 无 | `src/askflow/core/metrics.py` + `/metrics` | 无看板 / 无告警 | 🟡 有指标无告警 |
| §1.3 业务指标（FAQ ≥70% / 命中 ≥85% / 复杂工单 ≥80%） | ❌ 无 | **无监测代码** | 无 | 🔴 无回归保护 |

### 结构性问题（最严重）

#### 1. PRD 与 Trellis 任务体系完全脱钩

- `.trellis/tasks/` 仅 1 个 `00-bootstrap-guidelines`（spec 填充元任务），PRD 的 6 大功能模块**均未进入任务系统**。
- 实际的工作追踪散落在 `docs/status/UNIMPLEMENTED_2026-05-14.md` 与 `docs/status/TODO_TASKS_5_6.md`，这些不是 Trellis 任务，无法触发 `trellis-implement` / `trellis-check` 子代理流程，spec 注入机制完全用不上。
- **建议**：将 UNIMPLEMENTED 剩余 8 项（Prompt 模板、审计、Async 索引、前端测试、BM25 多 worker 等）逐项 `task.py create`，纳入 prd → jsonl → implement → check 闭环。

#### 2. AGENTS.md 名不副实

- 文件仅 21 行，**只描述 Trellis 元说明**，未定义任何 Agent 业务行为、路由、工具协议——与文件名暗示完全不符。
- 评审要求"AGENTS.md 中定义的行为是否覆盖业务路径"——答案是 **0 覆盖**。
- **建议**：要么改名（如 `TRELLIS.md`），要么补全 Agent 行为契约（意图清单、工具签名、handoff 协议、harness 策略）。

#### 3. `.trellis/spec/` 只覆盖编码规范，缺业务规约

- `spec/backend/*.md` 全是通用工程规范（目录结构、错误处理、日志）。
- **缺失**：业务领域 spec——意图清单与路由策略、工单 SLA 矩阵、handoff 上下文契约、知识回流流程。

---

## 二、SOP 缺口（按严重程度排序）

### 🔴 P0 — 阻塞产品上线

#### S1. 知识库回流（Knowledge Backflow）— 0% 设计

- **现状**：`feedback` 表能收集 👍/👎，但**没有任何路径把"好回答"或工单解决方案沉淀回 KB**；grep `knowledge_contribute / faq_backflow / 审核` 全部 0 命中。
- **缺失**：
  - FAQ 草稿生成（从对话/工单提取）
  - 审核工作流（pending → approved → published）
  - 入库版本管理 + 灰度发布
  - 命中追踪（沉淀后是否真的减少了重复问题）
  - 回滚机制（坏沉淀如何下线）
- **影响**：PRD §1.2 "自动化闭环" 缺最后一环；客服解的题下次还得重解，业务指标"重复问题处理量降低 50%"无法实现。
- **建议**：
  - 新建 `kb_contribution` 表：`{id, source_type (conversation/ticket), source_id, draft_content, status, reviewer_id, published_at, rolled_back_at}`
  - admin 后台增加"草稿审核"页
  - 与 `embedding/service.py::reindex` 联动，发布即触发增量索引
  - 落 spec 到 `.trellis/spec/backend/knowledge-backflow.md`

#### S2. Handoff 协议 — 仅有标记位，无交接协议

- **现状**：`src/askflow/agent/nodes.py:117` `handoff_node` 实际只做两件事：
  1. 把 `Conversation.status` 置为 `transferred`
  2. 回固定话术："您的问题摘要和对话记录将一并转交给客服人员"
- **缺失**：
  - **摘要根本没生成**——话术承诺了，但代码里没有摘要 API/字段
  - 没有人工坐席队列（grep `notify / notification` 在 src/askflow 下 0 命中）
  - 没有"无人接单"超时兜底（如 10 分钟未接 → 回 AI / 升级 / 告警）
  - 没有人工处理完回流到 AI 的状态机
  - 前端无客服接管 UI
- **影响**：转人工后会话黑洞——用户以为有人接，实际没人收到通知。
- **建议**：
  - 定义 `HandoffPayload` 契约：`{summary, recent_messages, intent_history, user_meta, ticket_refs}`
  - 新建 agent 工作台 + 待接管队列页
  - 超时（如 `handoff_pickup_timeout_min`）触发兜底动作
  - 落 spec 到 `.trellis/spec/backend/handoff-protocol.md`

#### S3. 审计日志 + PII 脱敏 — 0 行代码

- **现状**：grep `audit / redact / mask_pii / PII` 在 `src/askflow/` 下 = **0 命中**；`search_order` 返回的订单字段明文落 `messages.extra`。
- **影响**：合规阻断——任何对外（B 端客户、合规审查）接入前必须解决。
- **已在 UNIMPLEMENTED #2 标注**，此处再次强调严重性。

### 🟡 P1 — 影响运营稳定性

#### S4. Ticket SLA — 有阈值但无主动 SLA 引擎

- **现状**：
  - `settings.ticket_sla_hours = 24` 是**单一全局阈值**
  - `admin/analytics.py::get_ticket_dashboard` 能**统计**超时数 + 最老未处理工单年龄
  - 但**没有任何主动检测/告警/升级**：grep `cron / scheduler / celery / apscheduler / periodic` = **0 命中**
- **缺失**：
  - 按 priority 分级 SLA（urgent 也是 24h，与 low 相同）
  - 定时扫描 worker → 写超时事件
  - 超时后自动指派 / 邮件 / IM 通知 / 升级到上级
- **建议**：
  - 定义优先级 × SLA 矩阵：`urgent 1h / high 4h / medium 24h / low 72h`
  - 引入定时器（APScheduler 或 Redis Streams + cron worker）
  - 复用 `ticket/service.py` 的 `notification helper` 接入实际通道（当前可能仅 log）
  - 与 §4.5 PRD 同步更新——目前 PRD 只提"支持优先级"，未说 SLA 与升级策略

#### S5. 意图兜底缺"系统外意图"处理策略

- **现状**：6 类意图 + `confidence < 0.5 → clarify`；`_FALLBACK_ROUTES` 缺省落 RAG。
- **缺失**：用户问完全在系统外的话题（如"今天天气"、"帮我写邮件"），会被强制塞进 `faq` → RAG 检索空 → 回答幻觉。无明确"我无法处理这类问题"的策略。
- **建议**：
  - intent_classifier 增加 `out_of_scope` 标签
  - prompt 明确话术拒答 + 引导转人工或换问法
  - harness 增加 `out_of_scope_fallback_route` 配置

### 🟢 P2 — 运维 SOP 缺失

#### S6. 索引重建 SOP 未文档化

- 代码层：admin reindex 端点存在；但**无运维 runbook**——何时重建、停机窗口、对在线流量的影响、回滚（旧 chunk 仍命中？）。
- `docs/status/STATUS_CHECK_2026-05-14.md` 第 26 行提到"chunk 元数据兼容性需全量 reindex"，这是个埋雷——**未排期**。
- **建议**：写 `docs/runbooks/reindex.md`，覆盖全量/增量/灰度三种场景。

#### S7. 模型 / Prompt 更新 SOP 缺失

- Prompt 全硬编码（UNIMPLEMENTED #1），更新需改代码 + 重新部署。
- 模型版本切换（LLM endpoint / embedding model）无回归基线、无 A/B、无回滚清单。
- **建议**：Prompt 模板落地后，配套写 `docs/runbooks/prompt-update.md` 与 `docs/runbooks/model-rotation.md`。

#### S8. 数据修复 SOP 缺失

- 三存储（Postgres / MinIO / Chroma）不一致时如何修复？无 reconciliation 脚本，无运维 runbook。
- `embedding/service.py` 一旦写入过程中失败（如 Chroma 中断），残留 metadata 无清理路径。
- **建议**：
  - 写 `scripts/reconcile_storage.py`：扫描三方差异，报告 + 可选修复
  - 写 `docs/runbooks/storage-reconciliation.md`

---

## 三、文档一致性问题

| 问题 | 位置 | 处理建议 |
|---|---|---|
| AGENTS.md 与实际无关 | 根目录 `AGENTS.md` | 重命名为 `TRELLIS.md`，或补全 Agent 行为契约 |
| PRD §4.6 "Prompt 模板管理" 与代码状态矛盾 | `PRD.md:237` vs `admin/router.py` 无端点 | UNIMPLEMENTED #1 已记录，须建任务 |
| PRD §3.4 "Redis Streams 异步索引（目标能力）" 与实际同步阻塞 | `PRD.md:150` vs `embedding/service.py` | 已在 UNIMPLEMENTED #3 标注 |
| PRD §4.5 工单只提"优先级"，未提 SLA / 升级策略 | `PRD.md:226-231` | 补全 SLA 矩阵与升级策略章节 |
| `docs/status/` 4 份文档日期 / 口径不一 | `PROJECT_STATUS=04-17 / STATUS_CHECK=05-14 / UNIMPLEMENTED=05-16` | 合并为单一 STATUS.md |
| 业务指标（§1.3）无任何回归保护 | `PRD.md:31-37` | 配套监测代码 + Dashboard 告警阈值 |

---

## 四、行动优先级建议

| 序 | 动作 | 类别 | 估时 | 阻塞关系 |
|---|---|---|---|---|
| 1 | 把 UNIMPLEMENTED 剩余 8 项逐个 `task.py create` 进 Trellis | 流程 | 0.5 人日 | 解锁后续所有 trellis-implement / check 流 |
| 2 | 重写 AGENTS.md，补齐意图清单 / 工具签名 / harness 策略契约 | 文档 | 0.5 人日 | 独立 |
| 3 | 合并 `docs/status/` 4 文档为单一事实源 | 文档 | 0.5 人日 | 独立 |
| 4 | 设计 Handoff 协议 spec + 实现摘要生成 + 客服待接管队列 | 功能 | 4-6 人日 | 依赖 1 |
| 5 | 设计 KB 回流流程 spec + 草稿/审核/发布表 | 功能 | 4-6 人日 | 依赖 1 |
| 6 | SLA 引擎：priority × SLA 矩阵 + 定时扫描 worker + 升级通知 | 功能 | 3-4 人日 | 依赖 1 |
| 7 | 写运维 runbook（reindex / model 升级 / 三存储一致性修复） | SOP | 1-2 人日 | 独立，可与 4-6 并行 |
| 8 | 补全合规底座（审计 + 脱敏） | 功能 | 3-4 人日 | UNIMPLEMENTED #2 已规划，建议前移 |

### 推荐起步路径

```
Week 1: 动作 1 + 2 + 3（梳理基础）
Week 2-3: 动作 4 + 6 并行（Handoff + SLA — 体感最强）
Week 3-4: 动作 5（KB 回流 — 完成"自动化闭环"产品故事）
Week 4-5: 动作 7 + 8（合规与运维收口）
```

---

## 五、附录：评审证据索引

### 意图识别与路由

- 6 类意图定义：`src/askflow/agent/intent_classifier.py:13` `DEFAULT_INTENT = "faq"` + prompt 模板
- 路由表：`src/askflow/agent/nodes.py:185-192` `_FALLBACK_ROUTES` + DB 动态覆盖
- Harness 二次校验：`src/askflow/agent/harness.py:24-26` `low_confidence_threshold + allowed_routes`
- Clarify 兜底：`src/askflow/agent/nodes.py:204` `confidence < 0.5 → clarify`

### Ticket SLA

- 阈值：`src/askflow/config.py:62` `ticket_sla_hours: int = 24`
- 统计：`src/askflow/admin/analytics.py:120-229` `get_ticket_dashboard`（仅展示，不主动告警）
- 定时器扫描：grep `cron / scheduler / celery / apscheduler / periodic` 在 `src/askflow/` 下 = **0 命中**

### Handoff

- 节点实现：`src/askflow/agent/nodes.py:117-138` `handoff_node`
- 无摘要生成 / 无人工队列 / 无超时兜底（代码层面 0 实现）

### 知识回流

- grep `faq_backflow / knowledge_contribute / SOP` 在 `src/askflow/` 下 = **0 命中**
- `feedback` 表存在（messages 👍/👎），但无下游沉淀路径

### 审计 + 脱敏

- grep `audit / 脱敏 / redact / mask_pii / PII` 在 `src/askflow/` 下 = **0 命中**

### Trellis 任务体系

- `.trellis/tasks/` 仅 `00-bootstrap-guidelines/`
- `.trellis/spec/backend/` 仅通用编码规范（目录/数据库/错误/日志/质量），无业务领域 spec

---

## 维护说明

- 本文件是一次性快照评审，**不替代** `docs/status/UNIMPLEMENTED_2026-05-14.md` 这类滚动清单
- 评审中提出的"建议落地的任务"应分别走 Trellis `task.py create` 流程纳入正式追踪
- 若 6 个月后再做同类评审，请新建文件（如 `CLOSURE_SOP_REVIEW_2026-11-XX.md`），保留本份历史

---

## 附录：Wave 1 落地状态（2026-05-16）

本评审提出的 8 个动作已被拆为 4 个 Wave，由 Trellis 任务系统正式追踪。父任务：[`.trellis/tasks/05-16-closure-sop-audit-followup-wave-1-breakdown/`](../../.trellis/tasks/05-16-closure-sop-audit-followup-wave-1-breakdown/)

### Wave 1 — 流程梳理三件套（已完成）

| 动作 | 状态 | 产物 |
|---|---|---|
| 1. 把 UNIMPLEMENTED 剩余条目 + 评审新增条目纳入 Trellis | ✅ | 14 个子任务在 `.trellis/tasks/` |
| 2. 重写 AGENTS.md（Agent 业务契约） | ✅ | `AGENTS.md`（契约）+ `TRELLIS.md`（元说明） |
| 3. 合并 `docs/status/` 4 文档 | ✅ | `docs/status/STATUS.md` + 旧 4 份加 superseded 横幅 |

### Wave 2-4 — 功能落地

| 动作 | 对应任务 | Wave |
|---|---|---|
| 4. Handoff 协议 | `05-16-handoff-protocol` + `05-16-intent-out-of-scope-fallback` | Wave 2 |
| 6. SLA 引擎 | `05-16-sla-engine` | Wave 2 |
| 5. KB 回流流程 | `05-16-kb-backflow-pipeline` | Wave 3 |
| 1（旧 UNIMPL）Prompt 模板 | `05-16-prompt-template-crud` | Wave 3 |
| 3（旧 UNIMPL）Async 索引 | `05-16-async-index-pipeline` | Wave 3 |
| 7. 三份运维 runbook | `05-16-runbook-{reindex,prompt-model-update,storage-reconciliation}` | Wave 4 |
| 8. 审计 + 脱敏 | `05-16-audit-log-pii-redaction` | Wave 4 |
| （新增）前端测试 / BM25 多 worker / 路由健壮性 / search_order clarify | 4 个对应任务 | Wave 4 |

详细索引见 [`docs/status/STATUS.md`](../status/STATUS.md) §6。
