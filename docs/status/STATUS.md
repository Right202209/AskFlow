# AskFlow Project Status

> Single source of truth as of **2026-05-16**.
> Supersedes: `PROJECT_STATUS.md` (2026-04-17) / `STATUS_CHECK_2026-05-14.md` / `UNIMPLEMENTED_2026-05-14.md` / `TODO_TASKS_5_6.md`.
> Outstanding work is tracked under [`.trellis/tasks/`](../../.trellis/tasks/) — see §6.

## 1. Executive Summary

整体进度 **🟡 黄**：核心链路（Chat / RAG / Agent / Embedding / Ticket / Admin）已可端到端运行并通过单元 + 集成测试；生产上线前仍有 14 项工作（见 §6）。

最关键的四类缺口：
1. 运营侧 **Prompt 模板管理** 仍硬编码（任务 `05-16-prompt-template-crud`）
2. 合规所需的 **审计日志 + PII 脱敏** 完全未建（任务 `05-16-audit-log-pii-redaction`）
3. **Async 索引管道** 同步阻塞（任务 `05-16-async-index-pipeline`）
4. **前端测试框架** 未引入（任务 `05-16-frontend-test-framework`）

外加 SOP 评审（`docs/audits/CLOSURE_SOP_REVIEW_2026-05-16.md`）新提的：**KB 回流 / Handoff 协议 / SLA 引擎 / out_of_scope 兜底 / 三份运维 runbook**——已全部建任务。

## 2. Status by Area

| Area | Status | Notes |
|------|--------|-------|
| Authentication | ✅ Working | register / login / current-user；JWT；RBAC；限流 |
| Chat | ✅ Working | conversation CRUD（含 rename/archive/delete UI）/ history / WebSocket 流式 / 重连 / 心跳；router 已收敛为协议分发，生命周期在 `chat/service.py::process_user_message` |
| RAG | ✅ Working | BM25 + 向量 + rerank hook；`RetrievalFilters`（`sources / doc_ids / indexed_after / indexed_before`，`tags` 预留）；chunk 元数据带 `source / indexed_at_epoch`（旧 chunk 需 reindex 才被过滤选中） |
| Agent routing | ✅ Working | 6 类意图 + Router + Harness 二次校验；DB 动态路由 + Redis pub/sub 跨 worker 失效（健壮性待加固） |
| Tools | 🟡 Partial | `search_order` 已接 webhook 适配器 + mock 兜底；`search_knowledge` 已接 RAGService；订单号未识别仍硬返回（待改 clarify 回退） |
| Tickets | ✅ Working | create / read / update / list / 接管 / 自闭；Admin Ticket Dashboard + 单一 SLA 阈值；**主动 SLA 引擎缺失** |
| Embedding/documents | 🟡 Working with gaps | upload / index / reindex / delete；preview/download 流缺；**同步阻塞**（待 async 化） |
| Admin APIs | ✅ Working | analytics（含 harness reason / flag 分布）+ documents + intents + ticket dashboard |
| Frontend | ✅ Working MVP | auth / chat / tickets / dashboard / documents / intents / ticket dashboard；**无测试框架** |
| Tests | 🟡 Partial | 21 unit + 3 integration（RAG 链路 / Ticket 流转 / Intent 跨 worker 失效）；E2E 仅占位；前端 0 测试 |
| DevOps/ops | 🟡 Partial | `docker-compose` + Makefile；CI（GitHub Actions / CodeQL）2026-05-14 起就位；**无 prod manifest / 无 Grafana dashboard / 无告警规则** |
| Observability | 🟡 Partial | `/metrics` Prometheus；intent / order webhook 失败 / harness reason 计数器；**告警未配置** |
| Compliance | 🔴 Missing | 审计日志 + PII 脱敏 0 实现 |
| Knowledge backflow | 🔴 Missing | 👍/👎 feedback 已收，但无沉淀回 KB 的路径 |
| Handoff | 🔴 Partial | 仅标记 `transferred` + 固定话术；无摘要 / 队列 / 超时兜底 |

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
| 2026-05-14 | `alembic heads` | ✅ `20260327_01 (head)` |

**Re-run before release decisions** — none of the above commands have been re-executed in the 2026-05-16 refresh.

## 4. Recent Milestones (2026-05-14 → 2026-05-16)

| Commit | 摘要 |
|---|---|
| `17229ee` | BM25 索引持久化 + 路由表 Redis pub/sub 跨 worker 一致 |
| `b094a35` | `search_order` webhook 适配器 + 评审/规划文档 |
| `da1ef8f` | GitHub Actions（CI）+ CodeQL workflow |
| `a0427f3` | WS 集成测试 session mock 改 AsyncMock 修复 await 失败 |
| `a06835d` | `search_knowledge` 工具 + Admin Ticket SLA Kanban + harness 指标 |

## 5. Key Risks

按严重度排序：

1. **🔴 合规上线阻塞** — 审计 + 脱敏未建，任何 B 端 / 合规审查对接前必须解决。
2. **🔴 大文件上传 API 锁住** — 索引同步阻塞；100MB 文档会让 worker 长时间不响应。
3. **🟡 Prompt 改动需重新部署** — 运营自助能力为 0。
4. **🟡 前端 0 测试** — 任何 chat / store / hook 改动靠人眼回归。
5. **🟡 多 worker 部署 BM25 各自一份** — 索引在 worker A 重建后 worker B 仍命中旧版（pickle 模式已减轻、但跨 worker 真正一致仍未做）。
6. **🟡 Handoff 是"黑洞"** — 转接成功但客服侧无通知 / 无队列 / 无超时兜底。
7. **🟢 旧 chunk 缺 `source / indexed_at_epoch`** — 启用任意过滤即被排除；正式启用前需安排一次全量 reindex。
8. **🟢 远程 `feat/be-core` 分支可清理**（user-active 校验已在 master）。

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

- **Wave 1**（已立，本任务）：流程梳理三件套（任务导入 + AGENTS.md 拆分 + STATUS 合并）
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
- 评审：[`docs/audits/CLOSURE_SOP_REVIEW_2026-05-16.md`](../audits/CLOSURE_SOP_REVIEW_2026-05-16.md)
- 业务契约：[`AGENTS.md`](../../AGENTS.md)
- Trellis 工程流程：[`TRELLIS.md`](../../TRELLIS.md)

## 8. Maintenance Notes

- 本文件每次发布前或重大里程碑后更新（**不再按月滚动归档**）。
- 任务状态变化以 `.trellis/tasks/` 为准；本文件 §6 仅作索引快照，避免双向维护。
- 历史快照（§7）顶部带 superseded 横幅，**不再更新**。如需新一轮快照，新建 `STATUS_<date>.md` 并把本文件 §7 加一行。
