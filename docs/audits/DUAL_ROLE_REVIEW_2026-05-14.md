# AskFlow 双角色严格评审（更新版）

> 评审日期：2026-05-14
> 评审依据：当前 `master` 实际代码（覆盖到 `e6231ff feat: WebSocket auth-frame protocol + secret_key startup guard`）。
> 测试基线：`.venv/bin/python -m pytest tests/` 实跑 **118 passed / 59% coverage / 1 warning / 49.15s**。`README.md:206` 仍写 "backend suite should not be treated as green"，**严重过时**，必须删。
> 本次相较前一版，重点核查 `e6231ff` 是否真的修了上一轮的两条红旗，并对当时未识别的几个新问题做了独立标注。

---

## 一、产品经理视角（10 年 B 端 / SaaS / AI 产品）

### 1. 一句话定位评判
面向"有私有知识库的中小客服团队"的 RAG + 工单 + 转人工 一体化 **可演示参考实现**。问题是真问题（FAQ 重复、知识分散、关键词检索差），但 AskFlow 解决的不是别人没解决——它的实质受众是"想自建客服 AI 的工程团队"，而非"想买客服 SaaS 的业务方"。**当前阶段不要把它当 SaaS 看**：没有租户隔离、没有计费、没有 SLA、没有 audit log（PRD_AUDIT 自己标 Missing）。

### 2. 三大优点

1. **意图 → 路由数据驱动**（`agent/service.py:23-47` + `intent_config` 表）。运营改 DB 就能调整路由，比把规则写死在 prompt 里的同类项目高一截。`admin/service.py` 在写入时显式 `invalidate_route_map_cache()`，是产品化的正确切口（虽然失效模型还有缺陷，详见招聘方红旗 #2）。
2. **Cognitive Harness 把安全护栏做成独立层**（`agent/harness.py`）。空输入、超长（`max_question_chars=2000`）、prompt 注入（中英文双语正则）在意图分类前就被拦下，并通过 `harness_trace` 留痕。多数同档项目这块直接信 LLM，AskFlow 把"哪条规则把对话拦下来"做成了产品可解释的元数据。
3. **`e6231ff` 这次提交的"事后修复链"水平在线**：握手后首帧 auth (`chat/router.py:229-259`)、前端 `useWebSocket.ts:83` 同步迁移到 `/ws`、旧 `/ws/{token}` 保留但日志告警 (`router.py:262-273`)、`main.py:15-23` 加了非 development 启动期默认 `secret_key` 拦截。**懂得分阶段迁移而不是一刀切**——这是有过线上经验的迹象。

### 3. 三大缺点 / 风险

1. **"半步修复"风险**：
   - 旧 `/ws/{token}` 仍挂着 (`chat/router.py:262`)。**第三方客户端、旧浏览器缓存都还能用 URL 携带 JWT**——access log、企业代理、浏览器历史照样能截到。
   - `_assert_production_safe_settings()` 只在 `settings.app_env != "development"` 时拦截 (`main.py:17-23`)，而 `config.py:9` 默认 `app_env="development"`。**不主动配 APP_ENV 就什么都不会发生**——这两个护栏都需要运维主动配置一次才生效，**没有 fail-safe 默认**。
2. **业务工具仍然是假娃娃**：`search_order` 硬编码 `{"status":"shipped","tracking":"SF1234567890"}` (`agent/tools.py:21-25`)；订单号提取靠 `re.search(r"[A-Za-z0-9]{6,}")` (`agent/tools.py:73`)，会把 "PRODUCT001"、"abcdef"、"hello123" 都当订单号。**客服场景里"订单查询"是流量大头**，这一块不接通外部业务，所谓"自动化闭环"就是一张静态海报。
3. **如果上线 6 个月后会怎样**：
   - BM25 是模块级内存索引 (`rag/bm25.py:68`)，单实例可用，**水平扩展每个实例独立空索引、命中飘忽，且重启后丢失**——目前没有任何持久化或冷启动 reload 流程；
   - embedding 同步阻塞，PRD 自己承认 Async indexing Missing，50MB PDF 上传会卡住整条 API；
   - LLM 质量唯一指标是 `avg_confidence` (`admin/analytics.py`)，没有人工标注回路、没有 A/B、没有 bad case 复盘——**6 个月后没人能回答"它到底变好还是变坏了"**。

### 4. 一个季度的取舍：砍什么、加什么

**砍**：
- 砍 PRD §4.6 的 "Prompt 模板管理" 与 "意图分类后台 CRUD UI 扩展"——6 类意图 + 内置 prompt 已经够 demo，先冻结这块。
- 砍 "目标能力：Redis Streams 异步索引"——Streams 是 hype，不是当前瓶颈。最小可用的后台线程 + 任务表足矣。
- 砍 Admin Dashboard 多图表扩展——`avg_confidence` 之外的指标都不够 actionable。

**加**：
- 加一个**真业务接入样本**：把 `search_order` 改为可配置的 HTTP webhook 适配器 + 1 份 demo CSV。这是产品故事的命门。
- 加一个 **bad case 标注与回流闭环**：聊天页给 "👎 这条不好" 按钮 → 写 `feedback` 表 → Dashboard 用它替换空洞的 `avg_confidence`。这是衡量 "RAG 命中率 ≥85%" 唯一可信的来源。
- **明确定位**：在 README 顶部三选一——单租户私有部署 / 多租户 SaaS / 教学模板。当前一切代码基于"单组织、共享意图配置"的隐含前提，**不写明白就让招聘方和潜在用户两边猜**。

---

## 二、招聘方 / 项目组长视角

### 1. 技术亮点（值得在简历 / 面试展开讲）

1. **Cognitive Harness 的分层设计**（`agent/harness.py` + `agent/service.py:113-127, 152-172`）——**加分原因**：候选人在 LLM 应用里**显式区分了 "硬约束（速率/长度/注入）" 与 "软建议（模型置信度/重排）"**，并通过 `harness_trace` 留下决策证据。`wrap_stream` (`harness.py:174-202`) 不缓冲整条响应就能 enforce `max_response_chars=8000`，这种"流式 + 边界"的实现细节是教程级项目里抄不来的。
2. **混合检索的 RRF 融合 + 单路降级**（`rag/retriever.py:109-143, 45-59`）——**加分原因**：RRF k=60、可配置权重、单路失败自动 fallback。说明候选人理解 "两路召回怎么避免互相覆盖" 的实际权衡。`bm25.py:44-50` 还做了"先过滤再 top_k"以避免被无关命中挤名额——这是看过实际命中分布的人才会写的。
3. **WebSocket auth-frame 迁移路径**（`chat/router.py:229-273` + `web/src/hooks/useWebSocket.ts:83-98`）——**加分原因**：新协议在 `/ws`、旧协议保留 `/ws/{token}` 并日志告警、前端已切走。**懂得"修复 + 灰度"两步走**，比直接断老接口的工程师高一档。

### 2. 技术红旗（会让我犹豫是否过技术面）

1. **`bm25_index` 是模块级单例**（`rag/bm25.py:68`）——**我会追问**：*"重启服务后 BM25 索引从哪儿恢复？我看 `BM25Index.build()` 只在哪个调用点被触发？冷启动后第一个 RAG 请求是空索引返回还是会先全量重建？水平扩展两个 uvicorn worker，它们的 BM25 怎么同步？"* 这条**两次新提交都没碰**，说明候选人可能没在生产里被这个坑过。
2. **`_route_map_cache` 是进程内全局字典**（`agent/service.py:23-47`）——**我会追问**：*"管理员在后台改一条意图路由，`invalidate_route_map_cache()` 只能失效**当前 worker** 的缓存。3 个 worker 怎么同步？如果用 Redis pub/sub 失败、其中一个 worker 错过失效事件，下一次用户问 '转人工' 走错路由你怎么发现？"* 当前代码把它当"产品级缓存"在写，没有 TTL、没有跨进程通知。
3. **`get_agent_service()` 每条消息重建整个 RAG 栈**（`chat/service.py:57-60`）——`embedder` + `vector_store` + `HybridRetriever` + `Reranker` + `RAGService` + `IntentClassifier` + `AgentGraph` 每条用户消息都 new 一遍。**我会追问**：*"QPS 上到 50 时，每条消息重建 Reranker、构造 retriever、（可能）重连 Chroma，连接池握手成本谁来摊？为什么不在应用启动时注入单例？知道这是 FastAPI dependency injection 该解决的问题吗？"*
4. **Harness prompt-control 用字面量正则**（`agent/harness.py:30-36`）——**我会追问**：*"`忽 略 之前的指令`（夹空格）、`ig nore previous instructions`（字符切分）、base64 编码、bidi 字符，你这五条正则还拦得住吗？是有意把它当'低成本一道墙'，还是认为这就够了？"*
5. **`KEYWORD_RULES["handoff"]` 把 `"human"`/`"agent"` 设为 0.95 置信度**（`agent/intent_classifier.py:30-44, 81`）——**我会追问**：*"`'I want to talk to the AI agent'`、`'I'm a sales agent looking for help'`、`'is there a human override for this rule'`——这三句都会被你的规则秒判为 0.95 置信度的 handoff，而且 Harness 的 `low_confidence_threshold=0.5` 反而救不了——置信度太高反而坏事。你跑过 case 分布吗？"*
6. **`harness_trace` 不落盘**（`chat/service.py:73-80` 的 `MessageRepo.create` 没写 `harness_trace`）——**我会追问**：*"线上出了一条坏回答，要查当时 harness 为什么 truncate / fallback，只能去翻 ELK 吗？为什么不顺手存到 `message.metadata`？这是设计选择还是漏了？"*

### 3. 工程成熟度评分（1–5 分，5 = 可直接进生产）

| 维度 | 分数 | 一句话依据 |
|------|------|----------|
| 架构合理性 | **4** | 分层清晰，domain × infra 分明；但 BM25 / 路由缓存的"单进程隐式假设"未修，且 `get_agent_service()` 每次重建依赖是中级以下的写法 |
| 代码质量 | **4** | 类型注解齐全、async/await 一致、`agent/harness.py` 的 `_stop` / `_limit_tokens` 等小函数职责清晰，中文注释严格只解释"为什么" |
| 测试覆盖 | **3** | 118 passed / 59% 覆盖率，**新功能（harness、auth-frame）都补了单测**（`test_agent_harness.py`, `test_chat_router_auth.py`）；`repositories/ticket_repo.py` 仅 25%、`ticket/router.py` 0%，`tests/integration/`、`tests/e2e/` 仍是空目录 |
| 可观测性 | **2.5** | `/metrics` 有 `INTENT_CLASSIFICATION_COUNT`、`RAG_QUERY_COUNT`，结构化日志到位；但**没有 trace_id 串整条请求**、没有 SLO 样本、`harness_trace` 进日志不进指标也不进 message metadata |
| 文档与协作 | **3** | PRD/STATUS/AUDIT 三件套保持互相一致（2026-04-17 起统一刷新）；**减分项**：`README.md:206` "test should not be treated as green" 在 118 passed 现状下**严重失实**，必须立即修 |

**综合工程分**：**3.3 / 5**——*能跑能 demo，进生产还差异步索引、跨进程缓存、依赖装配、E2E 测试这四道关*。比上一次评估**没有明显抬升**：`e6231ff` 修了门口的锁，没修客厅的承重墙。

### 4. 如果这是候选人的代表作

**结论：通过技术面 / 待业务面定**。

候选人 demonstrably 能**完成一条端到端 RAG + Agent + Ticket + 安全护栏链路**，并表现出**层间隔离、降级、留痕、灰度迁移**这些"高于教程"的工程意识——这在面 P5/P6 候选人里已属上游。**`e6231ff` 那次"半步修复"反而是个加分项**：说明他在收到反馈后会改、且懂得不一刀切。

但是上面 6 条红旗里**至少要能在面试里答出 4 条**（特别是 #1 BM25 持久化、#2 缓存跨进程、#3 依赖单例），否则到 P7/资深那一关会被卡：如果他答不出 BM25 重启策略、路由缓存跨进程失效、依赖装配模式，那就说明这套东西**有相当一部分是 AI 协助写出来的、没经过自己手动 trace 过生产事故**。

---

## 三、综合建议（两位达成共识的部分）

**Top 6 优先级改进**（按 收益 / 投入 排序）：

| # | 改进 | 预计投入 | 预期收益 |
|---|------|---------|---------|
| 1 | 把 `search_order` 改为可配置的外部 webhook 适配器 + 1 份 demo CSV/接口 (`agent/tools.py:17-25`) | 2-3 人日 | 让"自动化闭环"从口号变成可演示能力——产品故事的命门 |
| 2 | BM25 索引落 Postgres `tsvector`（或至少持久化到本地文件 + 启动 reload），路由缓存换 Redis（带 pub/sub 失效）(`rag/bm25.py:68`, `agent/service.py:23`) | 4-6 人日 | 移除两个"单进程隐式假设"，水平扩展才不再自欺 |
| 3 | 摘掉 `/ws/{token}` legacy endpoint + 把 `app_env` 默认改成 `production`（development 需显式设置）(`chat/router.py:262`, `config.py:9`) | 0.5 人日 | 让 `e6231ff` 的两项护栏真的 fail-safe，而不是依赖运维记得配置 |
| 4 | 把 `harness_trace` 落到 `message.metadata`（schema 已有 `sources` 字段，扩展即可），Dashboard 暴露 fallback/truncate 率 + 加一张 `feedback` 表 + 聊天页 👍/👎 按钮 | 3-4 人日 | "为什么这条回答不好"能在 24h 内查到；替换空洞的 `avg_confidence` 作为唯一可信质量信号 |
| 5 | 关键词规则收窄：`"human"`/`"agent"` 必须与 "talk to" / "real" / "transfer" 上下文词共现才命中；信心降到 0.7 让 LLM 有覆盖空间 (`agent/intent_classifier.py:30-44`) | 0.5 人日 | 修一条**高概率影响真实对话**的脆性规则 |
| 6 | `get_agent_service()` 改成应用启动单例（`AgentService` 不持 `db`，依赖 DB 的 `ticket_service`/`conversation_repo` 改成方法参数）+ 补一套 WebSocket integration 测试 (`chat/service.py:57`, `tests/integration/`) | 3-5 人日 | 单消息延迟下降可观；最容易回归的链路有兜底，工程分能从 3.3 拉到 4.0 |

**附**：3 个 0.5–1 人日就能消的"清单类"任务，建议顺手做掉：
- 删 `README.md:206` "should not be treated as green" 这句话；
- `docs/PRD.md:3` 时间戳同步到 2026-04-17（PROJECT_STATUS 已同步）；
- 远程 `feat/be-core` 分支删掉（已被 master 覆盖）。

---

**一句话总结**：项目最稀缺的仍然是 **"真实业务接入 + bad-case 回流"**——所有精巧设计（harness、RRF、intent CRUD、auth-frame）都在为一个**还没接到血管的器官**做精装修。`e6231ff` 这一周新增了一项叫 "半步修复" 的债：把它走完整（红旗 #1/#2 + 上表 #3），比再上新功能更紧。
