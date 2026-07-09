# AskFlow 状态检查报告

> ⚠️ **Superseded** by [`STATUS.md`](STATUS.md) as of 2026-05-16. Kept for history only — do not update.
> 生成时间：2026-05-14
> 范围：只读 audit（Git / 代码改动 / Lint / 迁移 / 配置 / 前端 store / 文档 / 运行时）
> 未执行：`make test`、`make build-web`（待人工确认后单独触发）

## 摘要

整体健康度 **🟡 黄**。仓库已与 `origin/master` 同步，无未追踪文件，但 19 个改动文件全部已 `staged` 待提交，包含 2 个新模块（`chat/service.py`、`rag/filters.py`）以及一次明显的“chat router → service 抽离”重构。`ruff check` 全通过，但 `ruff format --check` 在 3 个文件上失败（含两个新文件 + `agent/harness.py`），属于格式未对齐而非逻辑问题。本机无 docker 运行时（`docker` / `podman` / `docker-compose` 均未安装，`systemctl is-active docker` = inactive），Postgres/Redis/Chroma/MinIO 全部不可达，因此 `alembic current` 无法验证迁移已应用，依赖外部服务的集成路径未在本次 audit 中触达。文档（PRD_AUDIT、PROJECT_STATUS）已同步至 2026-04-17 反映这批改动；PRD.md 本体仍标 2026-04-06，可在产品上线节奏稳定后再统一一次。

## 关键风险

按严重程度排序：

1. **🔴 Ruff 格式检查未通过，会卡 CI 的 `make lint`**
   - `src/askflow/agent/harness.py` — 待 `ruff format`
   - `src/askflow/chat/service.py` — 待 `ruff format`
   - `src/askflow/rag/filters.py` — 待 `ruff format`
2. **🟡 19 个文件全部 staged 未提交**：跨 chat / rag / embedding / agent / core / admin 多个域，建议按“chat 重构”、“rag 过滤器”、“embedding metadata + 测试”、“intent/auth 杂项”四组拆分独立 commit，避免单个提交既改架构又改实现。
3. **🟡 运行时服务全部下线** — 无法验证：
   - `alembic current` 失败（Postgres 5432 拒接） → 迁移已应用状态未知。
   - 任何走真实 DB/Chroma/Redis 的集成测试均会失败。
4. **🟡 PRD 文档时间戳不一致**：`PRD.md:3` 仍是 2026-04-06；`docs/status/PROJECT_STATUS.md:3` 与 `docs/audits/PRD_AUDIT.md:3` 已刷新到 2026-04-17。文字内容尚未发现实质漂移。
5. **🟢 远程 `feat/be-core` 分支未合并**：`abef6ac feat: add user validation in websocket endpoint to ensure active users` — 在本地 master 中已经能看到等价行为（`chat/router.py:171-178` 拒非 active 用户），可考虑删除远程分支以收敛。
6. **🟢 `tags` 过滤字段是预留 no-op**：`rag/filters.py:31-37`、`rag/router.py:31-34` — 已在代码与文档中明确告知；前端如计划暴露 tag 选择 UI，需先定义 tag taxonomy。
7. **🟢 Chunk 元数据兼容性**：`embedding/service.py:45-52` 新增 `source/indexed_at_epoch`，旧分块不带这两个字段，开启任意过滤即被排除 — 已在 `rag/filters.py:9-11` 与 `PRD_AUDIT.md` 中提示，正式发布前需安排一次全量 reindex。

## 各模块状态

| 模块 | 改动文件 | +/− 行数 | Lint | Test | 备注 |
|------|---------|----------|------|------|------|
| `chat/` | router.py, **service.py(新)** | +218 / −157 | ✅ check / ⚠️ format(service.py) | 待跑 | router 收敛为协议分发，生命周期搬到 `service.py::process_user_message`；CLAUDE.md 已说明这一变化对 patch 路径的影响 |
| `rag/` | bm25.py, **filters.py(新)**, retriever.py, router.py, service.py | +176 / −41 | ✅ check / ⚠️ format(filters.py) | 待跑 (`test_retriever.py` 已同步更新 `where=` / `predicate=` 桩) | 端到端引入 `RetrievalFilters`；BM25 改为先过滤再 top_k，避免被无关命中挤占名额 (`bm25.py:48-58`) |
| `embedding/` | router.py, service.py | +18 / −5 | ✅ | 待跑 (`test_embedding_router.py` 已加 `source=None` 断言) | 上传 / reindex 链路把 `source` 一路透到 chunk metadata；加盖 `indexed_at_epoch` |
| `agent/` | intent_classifier.py, service.py | +9 / −5 | ✅ | 待跑 | 引入 `DEFAULT_INTENT="faq"` 常量替换字面量，无行为变化 |
| `admin/` | analytics.py | +18 / −17 | ✅ | 待跑 | 5 个 count + avg_confidence 合并为单次 round-trip；为 admin 面板减少 DB 往返 |
| `core/` | auth.py, rate_limiter.py | +6 / −4 | ✅ | 待跑 | `except Exception` 收窄为 `(jwt.PyJWTError, ValueError, KeyError)`，rate_limiter 小幅清理 |
| `models/` | — | 0 | — | — | 仅 1 个迁移 `20260327_01_initial_schema.py`，无新 migration；模型目录无文件变更 |
| `docs/` | PRD_AUDIT.md, PROJECT_STATUS.md | +20 / −10 | — | — | 同步 2026-04-17 改动；显式区分“历史”与“当前未重跑”的命令验证结果 |
| `tests/unit/` | test_embedding_router.py, test_retriever.py | +5 / −2 | ✅ | 待跑 | 仅桩函数签名同步，不引入新用例 |
| `web/` | package-lock.json | +0 / −10 | — | — | 删除 `"peer": true` 字段，npm 内部 normalize；无 `package.json` 改动 |

引用验证：`grep "from askflow.chat.service"` → `chat/router.py:15` ✅；`grep "from askflow.rag.filters"` → `retriever.py:8`、`router.py:11`、`service.py:8` ✅。

前端 store 与后端 schema 一致性：
- `web/src/stores/chatStore.ts:139-148` 的 `Message` 字段 `intent / confidence / sources` 与 `chat/service.py:77-79` 持久化字段一致。
- `web/src/stores/authStore.ts:23-30` 通过 `decodeToken(token).role / .sub` 取值，与 `core/security.py` JWT 载荷 + `models/user.py` 角色枚举一致。
- 未发现明显字段漂移。

配置一致性：`.env.example` 全部 23 个 key 与 `src/askflow/config.py:8-52` 的字段一一对应（环境变量自动小写映射），无遗漏。

TODO / FIXME / XXX 在 `src/askflow/` 下 **零命中**。

## 建议的下一步动作

按优先级：

- [ ] **P0** 跑一次 `make format`（或 `ruff format` 上述三个文件）让 `make lint` 转绿；随后再补一个独立提交。
- [ ] **P1** 按域拆 commit：
  1. `refactor(chat): extract message lifecycle into chat/service.py`
  2. `feat(rag): add RetrievalFilters for source/time/doc-id filtering`
  3. `feat(embedding): stamp chunks with source + indexed_at_epoch`
  4. `chore(core,agent,admin): tighten exception types & constants, batch analytics counts`
  5. `docs: refresh PROJECT_STATUS / PRD_AUDIT for 2026-04-17`
- [ ] **P1** 启动 docker 服务（`make docker-up`），再跑 `make migrate` + `make test`，确认迁移到 head + 全量测试结果。
- [ ] **P2** 跑 `make build-web` 确认前端能产出 production bundle（package-lock 改动后建议复检）。
- [ ] **P2** 把 `PRD.md:3` 的更新时间同步到 2026-04-17，或在 PRD 头部加一行“实现状态参见 PROJECT_STATUS.md”避免误导。
- [ ] **P3** 清理远程 `feat/be-core` 分支（其 user-active 校验已等价存在于 master），收敛分支视图。
- [ ] **P3** 在前端 chat 输入区暴露 `filters.sources / indexed_after / indexed_before` 之前，安排一次 chunk 全量 reindex，否则旧数据会因为缺 `source` 字段被默默过滤掉。

## 附录：原始命令输出（节选）

### Git 状态 & 最近提交

```
## master...origin/master   (= 同步)
M  docs/audits/PRD_AUDIT.md
M  docs/status/PROJECT_STATUS.md
M  src/askflow/admin/analytics.py
M  src/askflow/agent/intent_classifier.py
M  src/askflow/agent/service.py
M  src/askflow/chat/router.py
A  src/askflow/chat/service.py
M  src/askflow/core/auth.py
M  src/askflow/core/rate_limiter.py
M  src/askflow/embedding/router.py
M  src/askflow/embedding/service.py
M  src/askflow/rag/bm25.py
A  src/askflow/rag/filters.py
M  src/askflow/rag/retriever.py
M  src/askflow/rag/router.py
M  src/askflow/rag/service.py
M  tests/unit/test_embedding_router.py
M  tests/unit/test_retriever.py
M  web/package-lock.json

96336c0 | feat: implement Cognitive Harness for input validation and routing control | Droite | 2026-05-13
24e16e1 | feat: remove clear-context skill and associated OpenAI agent configuration | 2026-04-14
9b83aef | feat: add link to README for localization | 2026-04-14
0df3872 | Add MIT License to the project | 2026-04-14
7f2f550 | feat: add usage guide and enhance documentation index in README | 2026-04-13
f294d12 | feat: enhance message rendering and loading indicators in chat components | 2026-04-13
f9456c2 | feat: add conversation management features and toast notifications | 2026-04-13
b525451 | chore: remove tsconfig build info file | 2026-04-13
40355a4 | feat: update database schema and user creation scripts; add repository guidelines | 2026-04-04
f4df2fe | fix: correct formatting and alignment in PRD document | 2026-04-01
```

### make lint

```
.venv/bin/python -m ruff check src/ tests/
All checks passed!
.venv/bin/python -m ruff format --check src/ tests/
Would reformat: src/askflow/agent/harness.py
Would reformat: src/askflow/chat/service.py
Would reformat: src/askflow/rag/filters.py
3 files would be reformatted, 105 files already formatted
make: *** [Makefile:37: lint] Error 1
```

### 容器运行时与外部服务

```
$ which podman docker-compose nerdctl  → 全部未安装
$ systemctl is-active docker            → inactive
$ alembic heads                          → 20260327_01 (head)
$ alembic current                        → 失败：ConnectionRefusedError 127.0.0.1:5432
```

### diff 行数汇总

```
19 files changed, 457 insertions(+), 222 deletions(-)
```
