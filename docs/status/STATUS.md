# AskFlow Project Status

> Single source of truth as of **2026-05-20**.
> Supersedes: `PROJECT_STATUS.md` (2026-04-17) / `STATUS_CHECK_2026-05-14.md` / `UNIMPLEMENTED_2026-05-14.md` / `TODO_TASKS_5_6.md`.
> Outstanding work is tracked under [`.trellis/tasks/`](../../.trellis/tasks/) — see §6.

## 1. Executive Summary

整体进度 **🟡 黄**：核心链路（Chat / RAG / Agent / Embedding / Ticket / Admin）已可端到端运行并通过单元 + 集成测试；2026-05-19 一致性审计沉淀的硬约束已分批落库；生产上线前仍有 14 项工作（见 §6）。

最关键的四类缺口：

1. 运营侧 **Prompt 模板管理** 仍硬编码（任务 `05-16-prompt-template-crud`）
2. 合规所需的 **审计日志 + PII 脱敏** 完全未建（任务 `05-16-audit-log-pii-redaction`）
3. **Async 索引管道** 同步阻塞（任务 `05-16-async-index-pipeline`）
4. **前端测试框架** 未引入（任务 `05-16-frontend-test-framework`）

外加 SOP 评审（`docs/audits/CLOSURE_SOP_REVIEW_2026-05-16.md`）新提的：**KB 回流 / Handoff 协议 / SLA 引擎 / out_of_scope 兜底 / 三份运维 runbook**——已全部建任务。

## 2. Status by Area

| Area | Status | Notes |
|------|--------|-------|
| Authentication | ✅ Working | register / login / current-user；JWT；RBAC；限流；`APP_ENV=production` 启动期拒绝默认 `SECRET_KEY` |
| Chat | ✅ Working | conversation CRUD（含 rename/archive/delete UI）/ history / WebSocket 流式 / 重连 / 心跳；WS 协议已切到 `/ws + auth 帧`，legacy `/ws/{token}` 仅 `APP_ENV=development` 挂载；router 已收敛为协议分发，生命周期在 `chat/service.py::process_user_message`；`POST /messages/{message_id}/feedback` 已上 |
| RAG | ✅ Working | BM25 + 向量 + rerank hook；`RetrievalFilters`（`sources / doc_ids / indexed_after / indexed_before`，`tags` 预留并 WARN）；chunk 元数据带 `source / indexed_at_epoch / generation`（旧 chunk 需 reindex 才被过滤选中） |
| Agent routing | ✅ Working | 6 类意图 + Router + Harness 二次校验；DB 动态路由 + Redis pub/sub 跨 worker 失效；epoch-counter 守护加载期竞态（健壮性待加固） |
| Tools | 🟡 Partial | `search_order` 已接 webhook 适配器 + mock 兜底（`fallback_reason` 走 `ORDER_WEBHOOK_FAILURE_COUNT`）；`search_knowledge` 已接 RAGService；订单号未识别仍硬返回（待改 clarify 回退） |
| Tickets | ✅ Working | create / read / update / list / 接管 / 自闭；**DB-level 去重已上**（partial unique index `uniq_open_user_title` + `INSERT ON CONFLICT`，alembic `20260519_01`）；Admin Ticket Dashboard + 单一 SLA 阈值；**主动 SLA 引擎缺失** |
| Embedding/documents | 🟡 Working with gaps | upload / index / reindex / delete；add-then-swap-then-delete + per-write `generation` 已上；preview/download 流缺；**索引同步阻塞**（待 async 化） |
| Admin APIs | ✅ Working | `analytics`（含 harness fallback/truncate rate、harness reason / flag 分布、👎 7d 率）+ documents + intents（CRUD 触发 `invalidate_route_map_cache` + Redis publish）+ ticket dashboard（SLA breach / 优先级 / 7 日 trend） |
| Frontend | ✅ Working MVP | auth / chat / tickets / dashboard / documents / intents / ticket overview + dashboard；toast store 已上；**无测试框架** |
| Tests | 🟡 Partial | 25 unit + 4 integration（RAG / Ticket / Intent 跨 worker / WS）；新增：`test_bm25_concurrency` / `test_embedding_pipeline_crash` / `test_route_map_epoch` / `test_ticket_repo_conflict`；E2E 仅占位；前端 0 测试 |
| DevOps/ops | 🟡 Partial | `docker-compose` + Makefile；CI（GitHub Actions / CodeQL）2026-05-14 起就位；**无 prod manifest / 无 Grafana dashboard / 无告警规则** |
| Observability | 🟡 Partial | `/metrics` Prometheus；`INTENT_CLASSIFICATION_COUNT` / `ORDER_WEBHOOK_FAILURE_COUNT` / `TICKET_COUNT` / harness reason+flag 分布；**告警未配置** |
| Compliance | 🔴 Missing | 审计日志 + PII 脱敏 0 实现 |
| Knowledge backflow | 🔴 Missing | 👍/👎 feedback 已收，但无沉淀回 KB 的路径 |
| Handoff | 🔴 Partial | 仅标记 `should_handoff=True` + 切 `conversation.status=transferred` + 固定话术；无摘要 / 队列 / 超时兜底 |

## 3. Verification Snapshot

历史命令验证记录（按时间，最近一次未重跑）：

| 日期 | 命令 | 结果 |
|---|---|---|
| 2026-04-06 | `npm run build` (`web/`) | ✅ Pass（large-chunk warning） |
| 2026-04-06 | `make test` | ❌ 在该 shell 中 pytest 不在项目环境 |
| 2026-04-06 | `.venv/bin/pytest ... --cov` | ❌ 出现 failing 用例 |
| 2026-05-14 | `ruff check` | ✅ Pass |
| 2026-05-14 | `ruff format --check` | ❌ 3 个文件待 format（已在后续 commit 修复） |
| 2026-05-14 | `alembic current` | ❌ 5432 拒接（本机无 docker daemon） |
| 2026-05-14 | `alembic heads` | ✅ `20260327_01 (head)` — 之后追加 `20260514_01` + `20260519_01`，当前 head 为 `20260519_01` |

**Re-run before release decisions** — none of the above commands have been re-executed in the 2026-05-20 refresh.

## 4. Recent Milestones

按 commit 倒序：

| Commit | 摘要 |
|---|---|
| `0a7cf70` | docs(audits)：Wave 1 landing 表追加到 closure SOP review |
| `b39b9ed` | docs(status)：合并 docs/status 为单一 STATUS.md |
| `9098b6f` | docs(agents)：拆分 AGENTS.md 为业务契约 + TRELLIS.md meta |
| `a06835d` | `search_knowledge` 工具 + Admin Ticket SLA Kanban + harness 指标 |
| `a0427f3` | WS 集成测试 session mock 改 AsyncMock 修复 await 失败 |
| `da1ef8f` | GitHub Actions（CI）+ CodeQL workflow |
| `b094a35` | `search_order` webhook 适配器 + 评审/规划文档 |
| `17229ee` | BM25 索引持久化 + 路由表 Redis pub/sub 跨 worker 一致 |
| `21d5cbc` | AgentService 移到启动期单例 + WebSocket 集成测试 |
| `2717d63` | `harness_trace` 落 messages.metadata + feedback 表与 👍/👎 闭环 |
| `fdf4d57` | 收窄 handoff 关键词规则——human/agent 必须有上下文词共现 |
| `2028fdc` | fail-safe：legacy WS 仅 dev 挂载、`APP_ENV` 默认 production |
| `e6231ff` | WebSocket auth-frame protocol + secret_key startup guard |
| `a2028bc` | 抽出 chat message lifecycle + RAG retrieval filters |
| `96336c0` | Cognitive Harness（输入/路由/输出三段控制） |

**2026-05-19 新增**：[`docs/audits/IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md`](../audits/IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md) + alembic `20260519_01_ticket_open_unique.py` + `tests/unit/test_{bm25_concurrency,embedding_pipeline_crash,route_map_epoch,ticket_repo_conflict}.py`。

## 5. Key Risks

按严重度排序：

1. **🔴 合规上线阻塞** — 审计 + 脱敏未建，任何 B 端 / 合规审查对接前必须解决。
2. **🔴 大文件上传 API 锁住** — 索引同步阻塞；100MB 文档会让 worker 长时间不响应。
3. **🟡 Prompt 改动需重新部署** — 运营自助能力为 0。
4. **🟡 前端 0 测试** — 任何 chat / store / hook 改动靠人眼回归。
5. **🟡 BM25 多 worker 各自一份** — 文件锁 + atomic replace 防止 pickle 损坏，但跨 worker 内存索引仍各自重建（无 invalidate 广播）；建议单 worker 部署，多 worker 走相同存储 + 30s 内最终一致。
6. **🟡 Handoff 是"黑洞"** — 转接成功但客服侧无通知 / 无队列 / 无超时兜底。
7. **🟡 WS `_cancel_flags` 进程内字典** — 不同 worker 上的连接互相看不到 cancel；多 worker 部署前需迁移到 Redis。
8. **🟢 旧 chunk 缺 `source / indexed_at_epoch`** — 启用任意过滤即被排除；正式启用前需安排一次全量 reindex。
9. **🟢 `filters.tags` 静默丢弃** — 入参传 `tags` 不会报错，只 WARN 日志；调用方需自检。

## 6. Outstanding Work — 14 Trellis Tasks

按优先级 + Wave 排序。详细 PRD 与 brainstorm 见各任务目录。

### 🔴 P0 — 阻塞生产或合规

| 任务 | Wave | 来源 | 估时 |
|---|---|---|---|
| [`05-16-prompt-template-crud`](../../.trellis/tasks/05-16-prompt-template-crud/) | 3 | UNIMPLEMENTED #1 | 3-4 人日 |
| [`05-16-audit-log-pii-redaction`](../../.trellis/tasks/05-16-audit-log-pii-redaction/) | 4 | UNIMPLEMENTED #2 + Review S3 | 3-4 人日 |
| [`05-16-async-index-pipeline`](../../.trellis/tasks/05-16-async-index-pipeline/) | 3 | UNIMPLEMENTED #3 | 3-5 人日 |
| [`05-16-kb-backflow-pipeline`](../../.trellis/tasks/05-16-kb-backflow-pipeline/) | 3 | Review S1 | 4-6 人日 |
| [`05-16-handoff-protocol`](../../.trellis/tasks/05-16-handoff-protocol/) | 2 | Review S2 | 4-6 人日 |

### 🟡 P1 — 影响运营稳定 / 多 worker 扩展

| 任务 | Wave | 来源 | 估时 |
|---|---|---|---|
| [`05-16-frontend-test-framework`](../../.trellis/tasks/05-16-frontend-test-framework/) | 4 | UNIMPLEMENTED #4 | 4-6 人日 |
| [`05-16-bm25-multi-worker-sync`](../../.trellis/tasks/05-16-bm25-multi-worker-sync/) | 4 | UNIMPLEMENTED #5 | 2-4 人日 |
| [`05-16-sla-engine`](../../.trellis/tasks/05-16-sla-engine/) | 2 | Review S4 | 3-4 人日 |

### 🟢 P2 — 体验 / SOP / 文档

| 任务 | Wave | 来源 | 估时 |
|---|---|---|---|
| [`05-16-route-pubsub-resilience`](../../.trellis/tasks/05-16-route-pubsub-resilience/) | 4 | UNIMPLEMENTED #6 | 1 人日 |
| [`05-16-search-order-clarify-fallback`](../../.trellis/tasks/05-16-search-order-clarify-fallback/) | 4 | UNIMPLEMENTED #7 | 0.5 人日 |
| [`05-16-intent-out-of-scope-fallback`](../../.trellis/tasks/05-16-intent-out-of-scope-fallback/) | 2 | Review S5 | 1 人日 |
| [`05-16-runbook-reindex`](../../.trellis/tasks/05-16-runbook-reindex/) | 4 | Review S6 | 0.5 人日 |
| [`05-16-runbook-prompt-model-update`](../../.trellis/tasks/05-16-runbook-prompt-model-update/) | 4 | Review S7 | 0.5 人日 |
| [`05-16-runbook-storage-reconciliation`](../../.trellis/tasks/05-16-runbook-storage-reconciliation/) | 4 | Review S8 | 1 人日 |

### Wave 节奏

- **Wave 1**（已完成 2026-05-19）：流程梳理三件套（任务导入 + AGENTS.md 拆分 + STATUS 合并）+ 一致性硬约束（ticket DB 去重 / BM25 snapshot / route-map epoch / 4 个回归用例）
- **Wave 2**：Handoff + SLA + out_of_scope（运营痛点最强，~8 人日）
- **Wave 3**：Prompt 模板 + Async 索引 + KB 回流（产品故事收口，~12-15 人日）
- **Wave 4**：合规 + 前端测试 + 多 worker + 3 份 runbook（~10-15 人日）

总累计 **~32-44 人日**，单人节奏 **5-8 周**。

## 7. References

- 历史快照（仍保留但已 superseded，请以本文件为准）：
  - `PROJECT_STATUS.md` — 2026-04-17 视角下的模块详情
  - `STATUS_CHECK_2026-05-14.md` — 2026-05-14 readonly audit（lint / 改动文件矩阵 / 命令验证）
  - `UNIMPLEMENTED_2026-05-14.md` — 2026-05-16 末次进度的未实现清单（已被 §6 替代）
  - `TODO_TASKS_5_6.md` — Task 5/6 详细方案（多数已完成）
- 评审：[`docs/audits/CLOSURE_SOP_REVIEW_2026-05-16.md`](../audits/CLOSURE_SOP_REVIEW_2026-05-16.md) / [`docs/audits/IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md`](../audits/IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md)
- 业务契约：[`AGENTS.md`](../../AGENTS.md)
- Claude Code 工程指南：[`CLAUDE.md`](../../CLAUDE.md)
- Trellis 工程流程：[`TRELLIS.md`](../../TRELLIS.md)

## 8. Maintenance Notes

- 本文件每次发布前或重大里程碑后更新（**不再按月滚动归档**）。
- 任务状态变化以 `.trellis/tasks/` 为准；本文件 §6 仅作索引快照，避免双向维护。
- 历史快照（§7）顶部带 superseded 横幅，**不再更新**。如需新一轮快照，新建 `STATUS_<date>.md` 并把本文件 §7 加一行。
