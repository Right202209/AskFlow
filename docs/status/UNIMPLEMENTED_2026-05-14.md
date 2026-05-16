# AskFlow 未实现功能清单

> 生成时间：2026-05-14
> 范围：基于 `PRD.md`、`AGENTS.md`、`docs/status/*`、`docs/audits/*`、`README.md` 等文档逐项对照代码现状
> 用途：开发排期与文档同步的单一事实源；每项均给出"文档出处"+"代码状态"双向引用

## 摘要

整体进度 **🟡 黄**：核心链路（Chat / RAG / Agent / Embedding / Ticket / Admin）已可端到端运行，但生产化所需的若干能力仍空缺。最关键的四类缺口为：(1) 运营侧 **Prompt 模板管理** 完全未建；(2) 合规所需的 **审计日志 + 脱敏** 完全未建；(3) **Async 索引管道** 未做，大文件上传会阻塞 API；(4) 前端 **测试框架** 未引入。其余多为 Task 5/6 收尾、骨架补全与文档过时同步。

## 优先级总览

| 等级 | 项数 | 含义 |
|------|------|------|
| 🔴 高 | 4 | 阻塞生产或合规上线 |
| 🟡 中 | 5 | 影响多 worker 扩展、关键演示场景 |
| 🟢 低 | 5 | 体验/质量/文档同步 |

---

## 🔴 高优先级 — 阻塞生产或合规

### 1. Prompt 模板 CRUD + 版本管理

- **文档出处**：`PRD.md:237`、`docs/audits/PRD_AUDIT.md:45`
- **代码状态**：
  - `src/askflow/models/` 下无 `prompt.py`（已确认目录列表）
  - `src/askflow/admin/router.py` 无对应端点
  - 当前所有 prompt 仍硬编码在 `agent/intent_classifier.py`、`rag/service.py` 等模块
- **预期落地**：新增 `PromptTemplate` 模型 + 迁移；admin router 暴露 `GET/POST/PUT/DELETE /admin/prompts`；运行时从 DB 取最新版本（带缓存 + Redis pub/sub 失效，参照路由表方案）

### 2. 审计日志 + 敏感数据脱敏

- **文档出处**：`PRD.md:249-253`、`docs/audits/PRD_AUDIT.md:49`
- **代码状态**：
  - 无 `AuditLog` 模型
  - chat 消息、`agent/tools.py::search_order` 返回的订单字段明文落库
  - 无脱敏中间件，无 PII 检测
- **预期落地**：`AuditLog` 模型记录关键操作（登录、文档上传、意图配置变更、订单查询）；统一脱敏工具函数（手机号、邮箱、订单号尾段）；写入路径与读取路径分离，admin 可查询完整审计流

### 3. Async 索引管道

- **文档出处**：`PRD.md:150`、`docs/status/PROJECT_STATUS.md:89` 标记 "Missing"
- **代码状态**：
  - `src/askflow/embedding/service.py` 的 parse → chunk → embed → 写 Chroma 全链路同步阻塞
  - 上传接口在大文件上等待整个流程返回，API 锁住
- **预期落地**：上传立即返回 `task_id`，索引落入 Redis Streams / Celery / RQ；新增 worker 进程消费；提供 `GET /embedding/tasks/{id}` 查询进度；失败重试与死信队列

### 4. 前端测试框架

- **文档出处**：`docs/audits/PRD_AUDIT.md:52`
- **代码状态**：
  - `web/package.json` 无 vitest / jest / playwright 任何测试依赖（已确认）
  - 全仓零 `*.test.ts` / `*.spec.ts` 文件
- **预期落地**：引入 Vitest + React Testing Library；优先覆盖 `useWebSocket`、`chatStore`、`authStore` 三个高价值模块；CI workflow 增加 `npm run test`

---

## 🟡 中优先级 — Task 5/6 收尾与扩展性

### 5. BM25 Postgres `tsvector` 方案

- **文档出处**：`docs/status/TODO_TASKS_5_6.md:28-82`（Task 5A）
- **代码状态**：
  - 已实现 pickle 落盘 + 启动 reload（`main.py` 启动期加载）
  - 仍是进程内单例（`rag/bm25.py:144`），多 worker 各自一份
  - TODO 文档原本推荐的 Postgres FTS 方案未做
- **预期落地**：评估是否切到 Postgres `tsvector` + GIN 索引；或保留 pickle 但加文件 mtime watch，多 worker 收到 inotify 后统一 reload

### 6. 路由缓存 pub/sub 健壮性

- **文档出处**：`docs/status/TODO_TASKS_5_6.md:55-62`（Task 5B）
- **代码状态**：
  - `agent/service.py:31-47` 进程内字典 + 60s TTL
  - `start_route_map_subscriber` 已在 `main.py` 接入（最近一次提交 `17229ee`）
  - 缺：订阅失败重连、消息丢失补偿、admin 强制刷新接口
- **预期落地**：subscriber 增加 backoff 重连；admin 路由配置页加"强制广播"按钮；监控订阅 lag

### 7. `search_order` 订单号兜底

- **文档出处**：`docs/status/TODO_TASKS_5_6.md:107-113`（Task 6）
- **代码状态**：
  - `agent/tools.py:22` 已用 `ORDER_ID_PATTERN = re.compile(r"\b[A-Z]{2,4}\d{6,}\b")`
  - 匹配失败时 `tools.py:187-193` 直接返回"请提供订单号"
  - 无 LLM 二次解析、无与前一轮对话上下文联动
- **预期落地**：失败时回退到让 Agent 在 `clarify` 分支提问，把 message history 带上,而非工具层硬返回

### 8. `search_knowledge` 工具实现

- **文档出处**：`AGENTS.md` 工具清单
- **代码状态**：**已验证**完全 stub —— `src/askflow/agent/tools.py:126-128`：
  ```python
  async def search_knowledge(query: str) -> list[dict]:
      logger.info("tool_search_knowledge", query=query)
      return []
  ```
- **预期落地**：调用 `RAGService.query`（非 stream），返回 top-k chunk 的 `{title, source, content}` 列表;Agent 在 tool 分支可拼回答

### 9. 集成 / E2E 测试补全

- **文档出处**：`docs/status/PROJECT_STATUS.md:18`
- **代码状态**：
  - `tests/integration/` 仅 `test_chat_websocket.py`（已完成）
  - `tests/e2e/` 完全空（只有 `__init__.py`）
- **预期落地**：RAG 完整链路（上传 → 索引 → 查询）、Ticket 客服流转、Admin 意图修改跨 worker 失效三个场景至少各补一条

---

## 🟢 低优先级 — 体验、可观测性、文档

### 10. ~~Harness 拦截指标看板~~ ✅ 已完成 (2026-05-16)

- 后端 `admin/analytics.py` 新增 `harness_reason_distribution` / `harness_flag_distribution` 聚合(基于 `messages.extra.harness_trace.reason` 与 `flags[]` 展平计数)
- 前端 `DashboardPage` 增加两个分类型柱状图

### 11. ~~Admin Ticket 系统级总览 + SLA~~ ✅ 已完成 (2026-05-16)

- 后端 `admin/analytics.py::get_ticket_dashboard` + `GET /api/v1/admin/tickets/dashboard`
- 字段:open 总数 / SLA 超时(`settings.ticket_sla_hours`)/ open 按优先级 / 最老未处理工单年龄 / 7 天 created vs resolved 趋势
- 前端新增 `web/src/pages/Admin/TicketDashboard.tsx`,路由 `/admin/tickets/dashboard`,侧边栏菜单"工单看板"

### 12. Admin 意图删除按钮

- **文档出处**：`docs/status/PROJECT_STATUS.md:44`、`docs/audits/PRD_AUDIT.md:44`
- **代码状态**：后端 DELETE 端点已支持；`web/src/pages/Admin/IntentsPage.tsx` 无删除 UI
- **预期落地**：列表行加"⋮"菜单暴露删除 + 确认弹窗

### 13. 聊天对话操作 UI（重命名 / 归档 / 删除）

- **文档出处**：`README.md:119`（Known Frontend Gaps）
- **代码状态**：后端接口在 `chat/router.py` 已有；前端 `ConversationList` 组件可能缺操作菜单（待 UI 核查）
- **预期落地**：列表项右侧加菜单，调用现有接口

### 14. 文档时间戳与告警同步

- **文档出处 / 待修**：
  - `README.md:206` "backend tests should not be treated as green" — 已 118 passed / 59% 覆盖率（参考 `DUAL_ROLE_REVIEW_2026-05-14.md:5`），文案过时
  - `PRD.md:3` 仍标 2026-04-06；其他文档已到 2026-04-17
- **预期落地**：一次性同步,可与下次 PRD 主体更新合并

---

## 落地建议

按"演示价值 × 投入"由低到高滚动，分四阶段推进。每阶段完成后同步删除本文件对应条目，并在 commit 中引用阶段与项编号。

### Phase 1 — 快赢补齐（0.5-1.5 人日）

> 目标：让 tool 分支演示完整、补齐前端缺失的轻量交互。风险低、可立即在 demo 看到效果。

| 编号 | 任务 | 估时 | 关键改动点 |
|------|------|------|-----------|
| 8 | `search_knowledge` 接 `RAGService.query`（非 stream） | 0.5 人日 | `src/askflow/agent/tools.py:126-128` |
| 12 | Admin 意图删除按钮（后端已就绪） | 0.25 人日 | `web/src/pages/Admin/IntentsPage.tsx` 行菜单 + 确认弹窗 |
| 13 | 聊天对话操作 UI（重命名 / 归档 / 删除） | 0.5 人日 | `web/src/components/ConversationList`（或同级）右侧菜单 |

**验收**：tool 分支返回 top-k 知识；Admin 列表可删除意图并即时刷新；侧边栏对话可重命名/归档/删除。

### Phase 2 — 测试与可观测（2-4 人日）

> 目标：把 `tests/integration/` 与 `tests/e2e/` 从骨架转为多场景，并把已有的 harness 拦截指标暴露成看板。

| 编号 | 任务 | 估时 |
|------|------|------|
| 9 | 集成测试：RAG 完整链路（上传 → 索引 → 查询） | 1 人日 |
| 9 | 集成测试：Ticket 客服流转 | 0.5-1 人日 |
| 9 | 集成测试：Admin 意图修改跨 worker 失效 | 0.5-1 人日 |
| 10 | Harness 拦截指标 admin analytics 聚合 + 前端看板 | 0.5-1 人日 |
| 11 | Admin Ticket 系统级总览 + SLA 看板 | 0.5-1 人日 |

**验收**：`pytest tests/integration/` 三类新增用例通过；admin Analytics 页可见拦截分类型计数；Ticket 看板可见待处理 / SLA 超时数。

### Phase 3 — 生产化阻塞项（6-9 人日）

> 目标：解锁运营自助、解决大文件上传痛点。两项均需迁移 + Redis pub/sub，建议串行实施以共用基础设施。

| 编号 | 任务 | 估时 | 依赖 |
|------|------|------|-----|
| 1 | Prompt 模板 CRUD + 版本管理 + DB 缓存 + pub/sub 失效 | 3-4 人日 | 复用 Task 5B 的路由表 pub/sub 模式（`agent/service.py:31-47`） |
| 3 | Async 索引管道：Redis Streams worker + `GET /embedding/tasks/{id}` | 3-5 人日 | 新增 worker 进程入口、死信队列、上传接口改为返回 `task_id` |

**验收**：admin 改 prompt 后多 worker 1s 内全部生效；100MB 文档上传立即返回 task_id，索引进度可查询。

### Phase 4 — 合规与多 worker 扩展性（10-15 人日）

> 目标：补齐合规底座 + 前端测试 + 已知多 worker 隐患。可拆给多人并行。

| 编号 | 任务 | 估时 |
|------|------|------|
| 2 | 审计日志 + 敏感数据脱敏中间件 | 3-4 人日 |
| 4 | 前端 Vitest + RTL；覆盖 `useWebSocket` / `chatStore` / `authStore` | 4-6 人日 |
| 5 | BM25 Postgres `tsvector` 或文件 mtime watch 多 worker 同步 | 2-4 人日 |
| 6 | 路由 pub/sub 重连 + admin 强制广播按钮 + lag 监控 | 1 人日 |
| 7 | `search_order` 失败回退到 Agent `clarify` 分支 | 0.5 人日 |

**验收**：所有关键操作落入 `AuditLog`，PII 字段脱敏；CI 执行 `npm run test` 且核心 hook/store 覆盖；多 worker 部署 BM25 与路由表 1s 内一致。

### Phase 5 — 文档同步（0.5 人日，可与任何阶段合并）

| 编号 | 任务 |
|------|------|
| 14 | `README.md:206` 后端测试现状描述、`PRD.md:3` 时间戳同步至 2026-05-14 |

### 总投入与节奏

- 累计 **19-30 人日**（含 Phase 5），单人节奏 **4-6 周** 抵达生产可上线
- 推荐起步路径：**Phase 1 → Phase 2 → Phase 3**，Phase 4 可与 Phase 3 后半段并行
- 若合规优先（如需对外接入），将 Phase 4 项 2（审计 + 脱敏）前移到 Phase 3 之前

---

## 维护说明

- 每完成一项请同步删除本文件对应条目，并在 git commit 中引用条目编号
- 新发现的缺口请补充到对应优先级，保持编号连续
- 与 `docs/status/TODO_TASKS_5_6.md` 的关系：本文件是全量清单，后者是 Task 5/6 的详细方案；项 5-7 在两份文档中重复列出，以本文件为索引、TODO_TASKS_5_6.md 为执行细节
