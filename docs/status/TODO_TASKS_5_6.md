# AskFlow 评审落地——剩余任务（Task 5 / Task 6）

> ⚠️ **Superseded** by [`STATUS.md`](STATUS.md) as of 2026-05-16. Task 5 / Task 6 已多数落地（见 commit `17229ee` / `b094a35`）。Kept for history only — do not update.
> 创建日期：2026-05-14
> 上下文：`docs/audits/DUAL_ROLE_REVIEW_2026-05-14.md` 红旗 #1/#2
> 当前进度：Task 0–4 已落地并提交（参见最近 5 个 commit）。
> 协作约束：沿用主指令——一个 Task 一次提交、一次 `make lint && make test`、PR 描述带 Before/After/Risk/Rollback。

---

## 已完成（上下文回顾）

| Task | Commit | 摘要 |
|------|--------|------|
| 0 | `f5bbf01` | README/PRD/format 清理；远端 `feat/be-core` 由本地无 git 凭据，需用户手动执行 `git push origin --delete feat/be-core` |
| 1 | `e4db6fe` | `app_env` 默认翻成 production；legacy `/ws/{token}` 仅 dev 注册 |
| 2 | `468fd59` | handoff 关键词换 9 条上下文正则；confidence 0.95→0.7 |
| 3 | `<after Task 3>` | `messages.metadata` JSONB + `feedback` 表 + 👍/👎 按钮 + admin 三项指标 |
| 4 | `52ebaba` | AgentService 启动单例 + 4 个 WS 集成用例 |

⚠️ **Task 0.3 未完成**：本会话 shell 没有 GitHub 凭据，需要用户手动执行：
```bash
git push origin --delete feat/be-core
```
（前置已确认远端无未合并提交。）

---

## Task 5 — BM25 持久化 + 路由缓存跨进程一致性（4-6 人日）

**目的**：移除两个"单进程隐式假设"，让水平扩展不再自欺。

### 5A — BM25 索引

**文件**：`src/askflow/rag/bm25.py:44-68`、`src/askflow/embedding/service.py`

**二选一**（在 PR 描述里写明选择理由）：

#### 方案 A（推荐，生产级）：迁到 Postgres tsvector
- migration 给 `document_chunks` 加：
  ```sql
  ALTER TABLE document_chunks
    ADD COLUMN fts tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
  CREATE INDEX ix_document_chunks_fts ON document_chunks USING GIN (fts);
  ```
- `BM25Index.search()` 改成 `SELECT ... WHERE fts @@ plainto_tsquery(:q) ORDER BY ts_rank(fts, ...) LIMIT k`。
- 删除模块级 `bm25_index` 单例。
- **中文分词注意**：`'simple'` 配置对中文召回有限，若 demo 包含中文文档需在 PR 描述说明取舍（或引入 `pg_jieba`/`zhparser`，但要评估部署成本）。

#### 方案 B（最少改动）：本地序列化
- 文档上传/重建后将索引 pickle 到 `data/bm25_index.pkl`。
- 应用 lifespan 启动时 reload，文件不存在则从 `document_chunks` 全量重建。
- 多 worker：用 `filelock` + 文件 mtime 触发其他 worker reload，或仅在主 worker 写、其他 worker 定时 reload。

### 5B — 路由缓存

**文件**：`src/askflow/agent/service.py:23-47`、`src/askflow/admin/service.py::invalidate_route_map_cache`

- 用 Redis 存路由表：`key = askflow:route_map`，值为 JSON，TTL 60s。
- `admin/service.py` 写入意图后 `redis.publish("askflow:route_map:invalidate", new_version_id)`。
- 应用启动时订阅该 channel（用 `asyncio.create_task` 跑后台协程），收到消息即清本地缓存并下次 lazy 重载。
- 兜底：即使 pub/sub 漏消息，TTL 60s 也能最终一致。

### 验收

- 重启服务后第一条 RAG 请求命中（不再返回空 BM25 结果）。
- 起 2 个 uvicorn worker，管理员通过 worker A 改路由，worker B 在 ≤5s 内对同一意图返回新路由。
- 单测/集成测试覆盖：Redis pub/sub 失败 → TTL 兜底仍最终一致。

### 实现要点（开始时先看）

- `src/askflow/rag/bm25.py` 当前的模块级 `bm25_index` 在 `_build_index_for_corpus` 里只在文档上传时构建——重启即丢。
- `src/askflow/embedding/service.py` 是唯一同时写 Postgres + MinIO + Chroma 的位置，方案 A 的 fts 列由 GENERATED 自动维护，写入路径基本不动。
- `src/askflow/core/redis.py` 的 `redis_client` 已经接好；pub/sub 协程的生命周期挂在 `main.py::lifespan`，shutdown 时记得取消。
- 单元测试用 `fakeredis` 替代真实 Redis（已在 `pyproject.toml` 的 dev 依赖里）。

### Rollback

- 方案 A：`alembic downgrade` 删除 `fts` 列；BM25Index 回退到内存重建。
- 方案 B：删除 `data/bm25_index.pkl` 文件 + 还原 `bm25.py`。

---

## Task 6 — `search_order` 改 webhook 适配器 + demo（2-3 人日）

**目的**：让"自动化闭环"从口号变成可演示能力——产品故事的命门。

**文件**：`src/askflow/agent/tools.py:17-25, 73`、`src/askflow/config.py`

### 配置层

新增 `Settings`：
```python
order_lookup_webhook_url: str | None = None
order_lookup_timeout_s: float = 5.0
order_lookup_auth_header: str | None = None
```

### 行为分支

`search_order(order_id: str)` 三种行为：

1. **未配置 webhook** → 维持现 mock 行为，但日志 `warn` 一次（用 `warnings.warn` + `lru_cache` 避免刷屏），响应里加 `"data_source": "mock"`。
2. **已配置但失败** → `httpx.AsyncClient` POST/GET 到 webhook，带 timeout；4xx/5xx/超时 → fallback to mock 并 `RAG_QUERY_COUNT` 风格打点（新增 `ORDER_WEBHOOK_FAILURE_COUNT` Counter）。
3. **成功** → 透传响应字段，响应里加 `"data_source": "webhook"`。

### 订单号提取

`agent/tools.py:73` 当前是 `re.search(r"[A-Za-z0-9]{6,}")`，会把 `PRODUCT001`/`abcdef`/`hello123` 全部当订单号。改成：
```python
ORDER_ID_PATTERN = re.compile(r"\b[A-Z]{2,4}\d{6,}\b")
```
仅这个模式命中才视为订单号；否则让 LLM 在工具调用前显式 confirm（在 prompt 里告知工具结果"未能识别订单号"，让模型反问）。

### Demo 资料

- `docs/examples/order_webhook_demo.py`（≤ 20 行 FastAPI 示例）
- `docs/examples/orders.csv`（5–10 行 demo 数据）
- README 新加一节"接入真实业务的最小路径"，指向上面两份文件。

### 验收

- 单测三分支：
  - 未配置 → 返回 mock + `data_source: "mock"`；
  - 配置但超时 → fallback + `ORDER_WEBHOOK_FAILURE_COUNT` 计数器+1；
  - 配置且 200 → 返回真数据 + `data_source: "webhook"`。
- `python docs/examples/order_webhook_demo.py` 起本地服务，配置 webhook 后通过聊天页问"查我的订单 `AB12345678`"，前端能看到真实响应。

### 实现要点（开始时先看）

- `src/askflow/agent/tools.py` 当前 `search_order` 是同步硬编码 dict——改异步需要把 `tool_node` 调用链路一起改成 `await`（看 `agent/nodes.py::tool_node`）。
- `httpx.AsyncClient` 推荐做模块级单例（lifespan 管开关），别每次 `search_order` 都新建。
- 计数器在 `src/askflow/core/metrics.py` 与已有 `RAG_QUERY_COUNT` 并列定义即可。
- 测试用 `httpx.MockTransport` 拦请求，比起 `monkeypatch` AsyncClient 整个类更精确。

### Rollback

- 单 commit 即可——`git revert <commit>`，配置项是新增的、所以无 down migration。

---

## 全局约束（沿用主指令）

1. **顺序**：Task 5 → Task 6，每个一次提交。
2. **测试**：`make lint && make test` 至少保持 118 passed / 59% coverage 下限。Task 5 应再 +3-5 用例，Task 6 应再 +3 用例。
3. **commit message**：`feat:` / `fix:` / `refactor:` + 中文一句话摘要；body 引用 `DUAL_ROLE_REVIEW_2026-05-14 红旗 #N / 优先级 #N`。
4. **不要做的事**：
   - 不要顺手做 PRD §4.6 "Prompt 模板管理"、"Admin Dashboard 多图表扩展"、"Redis Streams 异步索引"。
   - 不要为兼容旧测试 stub harness/缓存——测试必须真跑过新路径。
   - 不要在 review 未列出的地方做"顺手优化"，scope creep 一律拒绝。
5. **PR 描述模板**：
   - Addresses：评审编号
   - Before/After：1-2 行验证脚本或截图
   - Risk：本次改动可能影响的链路
   - Rollback：如何回退（尤其 Task 5 的索引迁移）

---

## 完成 Task 6 后的总验收

- `.venv/bin/python -m pytest tests/` ≥ 130 passed（预期新增 ~12-15 测试，目前已落地约 8 条）。
- 起 2 个 worker，完整跑一遍：登录 → 上传文档 → RAG 提问（命中 BM25 + 向量） → 触发 handoff → 点 👎 → admin 后台看到指标变化 → 改一条意图路由 → 5s 内另一个 worker 生效。
- 评审里 6 条红旗逐条给出"已闭环"的证据（代码 diff 行号 + 测试用例名）。
