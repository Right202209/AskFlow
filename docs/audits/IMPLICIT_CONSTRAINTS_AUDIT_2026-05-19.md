# AskFlow 隐性业务约束与并发依赖审查

> 审查日期：2026-05-19
> 审查依据：当前 `master` 实际代码（包含 `0a7cf70 docs(audits): append Wave 1 landing table to closure SOP review`）。
> 审查范围：`src/askflow/` 全部 backend 包 + `web/src/` 关键 store / hook。
> 目标：找出**写不在文档里、但违反就会出 bug** 的隐性规则——并发、顺序、跨存储一致性、双入口同步、数据契约、资源生命周期、权限边界。

---

## 一、并发与锁（Concurrency & Locking）

### 1.1 BM25 进程内单例无 asyncio.Lock — **最高危**
- **位置**：`src/askflow/rag/bm25.py:144`，`src/askflow/embedding/service.py:28-30`
- **隐性约束**：`bm25_index = BM25Index()` 是模块级单例，`_corpus / _tokenized / _bm25` 三个内部状态由 `.build()` 写入、`.search()` 读取。当前仅用 `FileLock` 保护文件 I/O，**内存写入路径完全裸奔**。
- **违反后果**：两个并发上传/重索引调用 `_refresh_bm25_index()` → `.build()` 时，两份 `_corpus` 互相覆盖，最终内存索引和持久化文件不一致。检索 API 可能命中"已删除文档的旧 chunk"或返回部分语料。
- **是否文档化**：未文档化

### 1.2 WebSocket `_cancel_flags` 全局 dict 无锁
- **位置**：`src/askflow/chat/router.py:45,251,261`
- **隐性约束**：`_cancel_flags: dict[str, bool]` 由多个 worker / async 任务并发读写。`_run_session` 把 `is_cancelled()` 回调传给 `process_user_message`，回调在流式输出每个 token 节点频繁读这个 dict。
- **违反后果**：取消信号可能在流式中途丢失（dict 重哈希竞态），或被错误地"延后"应用到下一条消息；极端情况 `KeyError`。
- **是否文档化**：未文档化

### 1.3 `_route_map_cache` 与 Redis pub/sub 失效订阅的竞态
- **位置**：`src/askflow/agent/service.py:31-54,57-61,99-105`
- **隐性约束**：本地 `_route_map_cache` + `_route_map_cache_at` 由请求路径写入，Redis pub/sub 订阅在另一个协程触发失效。两者无锁同步——如果 admin 改了 intent 同时大量请求在调用 `_load_route_map()`，订阅消息可能晚于读路径，把刚加载的新值覆盖回旧值。
- **违反后果**：缓存看起来"已失效"，实际新配置在某些 worker 上不可见；路由决策按旧表执行（应该 → ticket 的请求走了 rag）。
- **是否文档化**：部分（CLAUDE.md 提了 TTL 但未提竞态）

---

## 二、顺序约束（Ordering Constraints）

### 2.1 嵌入管道部分状态（已文档化但缺事务）
- **位置**：`src/askflow/embedding/service.py:32-76`，特别是 line 66 `delete_by_doc_id()` 与 line 67-72 `add()` 之间
- **隐性约束**：必须按 `parse → chunk → embed → delete_old → add_new → refresh_bm25` 顺序，中途异常无回滚。
- **违反后果**：删完旧分块、未写新分块时崩溃 → 文档从向量库蒸发，但 DB 显示 `success`，检索完全找不到。用户必须手动重索引。
- **是否文档化**：CLAUDE.md line 75 提了顺序，**未提原子性缺失**

### 2.2 消息持久化 → WebSocket `message_end` 推送顺序
- **位置**：`src/askflow/chat/service.py:25-100`
- **隐性约束**：必须先 `db.commit()`、再 send `message_end {message_id}`、最后才允许关闭连接。前端 `pendingAssistantMessageId` 等这个 message_id 才能把 UUID 替换成真实 DB id。
- **违反后果**：连接在 commit 后、发送 message_end 前断 → 前端 `isStreaming=true` 卡死，feedback API 找不到 message 报 404。
- **是否文档化**：未文档化（仅在代码注释中提到）

### 2.3 工单去重 check-then-create 竞态
- **位置**：`src/askflow/ticket/service.py:21-49`
- **隐性约束**：`find_duplicate()` 与 `create()` 之间无 SELECT FOR UPDATE 也无 DB 唯一约束。
- **违反后果**：同一用户同一 title 的并发请求都判定"无重复"，全部 insert，违反"同一用户同一标题只保留一条"的产品规则。
- **是否文档化**：未文档化

---

## 三、跨存储一致性（Cross-Storage Consistency）

### 3.1 PG / MinIO / Chroma 三写无补偿
- **位置**：`src/askflow/embedding/router.py:56-90`
- **隐性约束**：文档上传需要 Postgres（metadata + status）、MinIO（bytes）、Chroma（chunks）三处同步成功。当前任一步失败都没有补偿机制。
- **违反后果**：MinIO 已存、Chroma 已索引、但 PG status 没更新 → 孤立向量被检索命中，回答里出现"不存在的文档"。
- **是否文档化**：未文档化

### 3.2 会话删除 vs 流式写入竞态
- **位置**：`src/askflow/chat/router.py:136`（REST DELETE）+ `chat/service.py` 中 `session_store.append_*` 路径
- **隐性约束**：REST 端 `session_store.clear()` 清 Redis 时，WebSocket 端可能仍在往同一 history key `rpush`。
- **违反后果**：删除完成后 Redis 里反而又出现碎片记录；用户新开会话看到幻影历史。
- **是否文档化**：未文档化

---

## 四、双入口同步（Dual Entry Points）

### 4.1 Chat REST `get_messages` 与 WebSocket `message_end` 的 message_id 对齐
- **位置**：`chat/router.py:150-164`（REST 拉历史）vs `chat/service.py:25-100`（WS 推 message_end）
- **隐性约束**：前端 `pendingAssistantMessageId` 是临时 UUID，依赖 `message_end` 里的真实 message_id 替换。如果用户在 message_end 到达前刷新页面调 REST，REST 返回的 id 必须与之后 WS 重发的 id 一致。
- **违反后果**：UUID 与 DB id 错位，feedback / regenerate 接口找不到消息；或同一条消息被前端记两次。
- **是否文档化**：CLAUDE.md line 71 提到"REST + WS 必须同步"，但未给出 message_id 对齐策略

---

## 五、隐性数据契约（Data Contracts）

### 5.1 2026-04-17 前的 chunk 缺 `source / indexed_at_epoch`
- **位置**：`src/askflow/rag/filters.py:9-10`，`embedding/service.py:57-64`
- **隐性约束**：老 chunk metadata 没有这两个字段，任何使用 `indexed_after/before/sources` 过滤的查询都会把它们整批排除。
- **违反后果**：用户开了过滤器后查不到老文档，但 UI 不会提示原因。
- **是否文档化**：CLAUDE.md line 95 明文写了

### 5.2 Intent config 无显式状态机
- **位置**：`src/askflow/admin/router.py:98-133`
- **隐性约束**：admin 可以任意创建/删除/改写 intent。分类器返回的 label 如果不在 route_map 里，会 fallback 到 rag。
- **违反后果**：删除/改名一个仍在分类器 prompt 里的 intent，会让所有该意图请求都被错误路由到 RAG。
- **是否文档化**：未文档化

### 5.3 WebSocket `data` 字段语义随 `type` 变化
- **位置**：`web/src/hooks/useWebSocket.ts:114-142`（前端处理）vs `src/askflow/chat/service.py:183-220`（后端发送）
- **隐性约束**：同一个 `data` 字段在 `intent / source / ticket / handoff / harness_trace` 五种事件下含义完全不同；前端用 `?.` 链路解析，字段缺失会被吞掉。
- **违反后果**：后端某次重构改字段名 → 前端无报错，但 intent badge / source 列表静默消失，QA 难发现。
- **是否文档化**：未文档化（仅 Pydantic 模型隐式定义）

---

## 六、资源所有权与生命周期（Resource Ownership）

### 6.1 lifespan 启动顺序硬依赖
- **位置**：`src/askflow/main.py:70-81`
- **隐性约束**：必须 `redis_client.initialize()` → `AgentService()` → `start_route_map_subscriber()`，颠倒会导致 subscriber 拿到的 AgentService 句柄是空、或 invalidate 调到未初始化的缓存。
- **违反后果**：启动失败，或路由订阅静默无效。
- **是否文档化**：代码注释有，CLAUDE.md 没有

### 6.2 测试 mock 边界由 lifespan 绑定决定
- **位置**：`chat/service.py:57`（单例读取）vs CLAUDE.md line 92
- **隐性约束**：CLAUDE.md 提示 patch `askflow.chat.service`——根因是 `AgentService` 在 lifespan 阶段绑定到 `app.state`，patch router 模块改不到引用。
- **违反后果**：测试 mock 失效，单测意外调真实 LLM/RAG，导致慢且不稳定。
- **是否文档化**：部分（CLAUDE.md 提了 what，未提 why）

---

## 七、权限与安全边界（Authorization Boundaries）

### 7.1 upload (admin+agent) vs delete (admin-only) 不对称
- **位置**：`src/askflow/admin/router.py:69-85` vs `embedding/router.py:35-41`
- **隐性约束**：agent 可上传但不能删自己上传的文档，必须找 admin。
- **违反后果**：agent 想纠错只能再传一份 → MinIO 泄漏、可能 doc_id 复用 → Chroma 状态混乱。
- **是否文档化**：未文档化

### 7.2 工单更新权限随用户角色变化
- **位置**：`src/askflow/ticket/service.py:73-106`
- **隐性约束**：普通用户只能关闭自己工单，staff 可改 assignee/priority/content。用户从 user 升 agent 后，旧工单的可写性会突变。
- **违反后果**：升级后用户能改其他人工单（如果工单当初是 by-staff 而非 by-owner 校验）；降级后无法关闭自己已有工单。
- **是否文档化**：未文档化

### 7.3 `tags` 过滤字段"伪支持"
- **位置**：`src/askflow/rag/filters.py:32-37`
- **隐性约束**：API 接受 `filters.tags`，仅 log warning，**永远不过滤**。
- **违反后果**：客户端预期"按 tag 过滤返回 0"实际拿到全量。
- **是否文档化**：CLAUDE.md line 89-90 文档化了，但前端未必知道

---

## 八、Top 5 修复方案（按 "未文档化 × 违反成本 × 修改概率" 排序）

### #1 — BM25 加锁与不可变快照
**风险评分 9/10**

**当前问题**：`rag/bm25.py:144` 的 `_corpus / _tokenized / _bm25` 多写竞态。

**修复方案**（推荐 B 方案）：

A. 最小改动：加 `asyncio.Lock` 包住 `build()` 和 `search()`。
- 缺点：检索路径串行化，QPS 下降。

B. 不可变快照（推荐）：
```python
class BM25Index:
    def __init__(self):
        self._snapshot: BM25Snapshot | None = None  # frozen dataclass

    async def build(self, docs):
        # build off-snapshot
        new_snap = BM25Snapshot(corpus=..., tokenized=..., bm25=...)
        self._snapshot = new_snap  # atomic pointer swap

    def search(self, q):
        snap = self._snapshot  # local binding, immune to concurrent build
        if snap is None: return []
        return snap.bm25.get_top_n(...)
```
原子指针替换避免读侧加锁。`build()` 间互斥仍需 `asyncio.Lock`。

**验证**：写一个并发测试，100 个 task 同时 `build()` 和 `search()`，断言无 KeyError 且最终快照对应最后一次 build。

---

### #2 — 跨存储一致性：outbox 表 + 补偿
**风险评分 8/10**

**当前问题**：`embedding/router.py:56-90` 三写无回滚。

**修复方案**（分阶段）：

阶段 1（一周）：调整顺序为 "**写新 → 切换 → 删旧**"
```python
# 当前：delete_by_doc_id → add  ← 中途崩溃 = 数据消失
# 改为：add(temp_id=doc_id+"::new") → DB swap pointer → delete_by_doc_id(old)
```
关键：让中间态"可读但不对外"，最终态原子切换。

阶段 2（迭代）：引入 `outbox_events` 表，所有跨存储写入先入 DB 同一事务，由独立 worker 消费并标记完成；崩溃后重启自动重放。

**验证**：注入故障（在 add 后 raise），断言文档仍可被检索（旧版本），重试后切换成功。

---

### #3 — 工单去重：DB 唯一约束 + ON CONFLICT
**风险评分 8/10**

**当前问题**：`ticket/service.py:21-49` check-then-create 竞态。

**修复方案**：

1. 加部分唯一索引（仅未关闭的工单）：
```sql
CREATE UNIQUE INDEX uniq_open_user_title ON tickets(user_id, title)
WHERE status != 'closed';
```
2. `create()` 改用 `INSERT ... ON CONFLICT DO NOTHING RETURNING id`，conflict 时再查出已有工单返回。
3. 删除应用层 `find_duplicate()`（或保留作为快路径，但不再作为正确性依赖）。

**Alembic 迁移**：autogenerate 不识别 partial index，需手写 `op.create_index(..., postgresql_where=...)`。

**验证**：100 个并发 create 相同 title，断言只有 1 条记录被插入，其余请求拿到同一个 id。

---

### #4 — Route map 缓存：本地只读副本 + Redis 权威
**风险评分 7/10**

**当前问题**：`agent/service.py:31-54` 本地缓存与 pub/sub 失效竞态。

**修复方案**：

1. Redis 作为权威源：`route_map:v{N}` key 写入完整快照，admin 写入时版本号递增。
2. 本地缓存只缓存当前 `version` 对应的快照，每次读取先 `GET route_map:version` 比对版本号——版本不一致就重拉。
3. pub/sub 仍保留，但只作为"加速失效"用，不作为正确性依赖。

```python
async def _load_route_map():
    redis_ver = await redis.get("route_map:version")
    if redis_ver == _local_ver: return _local_snapshot
    snap = await redis.get(f"route_map:v{redis_ver}")
    _local_ver, _local_snapshot = redis_ver, snap
    return snap
```

**验证**：admin 写入后立即在不同 worker 读取，断言新值可见且无版本回退。

---

### #5 — 嵌入管道事务化（与 #2 配套）
**风险评分 7/10**

**当前问题**：`embedding/service.py:66-72` 删除老分块后新分块写入失败 → 数据丢失。

**修复方案**：

短期：与 #2 同方案——改为 add-then-swap-then-delete 顺序。

中期：引入 task 表
```sql
CREATE TABLE embedding_jobs(
    id UUID PRIMARY KEY,
    doc_id UUID,
    state TEXT,  -- pending|parsed|embedded|swapped|done|failed
    started_at TIMESTAMPTZ, ...
);
```
每个阶段更新 state，独立 worker 可基于 state 续跑。reindex 接口幂等。

**验证**：上传 → kill -9 模拟崩溃 → 重启 worker → 文档完整可检索。

---

## 九、配套维护建议

1. **文档**：CLAUDE.md 新增"并发模型与一致性"章节，明确列出本文 7 类约束（保留 file:line 锚点）。
2. **Lint/CR 清单**：所有"check-then-act"代码路径必须 review（工单去重、文档去重、路由缓存、cancel flags）。
3. **WebSocket schema 治理**：用 Pydantic Discriminated Union 替代 `dict[str, Any]` 形式的 event payload；前端用 zod / openapi-generator 拉同一份类型。
4. **启动依赖图**：把 lifespan 顺序画进 `docs/PROJECT_STRUCTURE.md`，标注每条依赖箭头的根因。
5. **回归测试**：每条 Top 5 修复都要带一个**故障注入测试**（mock 中途异常 / 并发竞态），落入 `tests/integration/`。

---

## 十、未覆盖范围（后续审查 backlog）

- 前端 Zustand store 的乐观更新与 WS 事件冲突（chat / ticket 列表）
- Alembic 迁移的向后兼容（旧版本 worker 仍在跑时新 schema 是否可读）
- LLM client `aclose()` 与 lifespan shutdown 的并发关闭语义
- MinIO presigned URL 的有效期与会话生命周期的对齐

> 完。下一步建议先做 Top 5 中的 #1 (BM25) + #3 (工单唯一约束)，两条改动小、收益大、风险低；#2 / #5 需要更长周期与 outbox 设计。
