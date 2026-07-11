"""评估 harness 的全部常量与路径（plan-docs/knowledge-loop/03 §Constants）。"""

from __future__ import annotations

from pathlib import Path

# 与 RAGService 默认 top_k 一致，保证评估口径与线上问答一致。
EVAL_TOP_K = 5
# 并发 case 数上限——保护本地 Ollama/LLM 端点不被打爆。
EVAL_CONCURRENCY = 4
# 核心指标允许的最大回退幅度；超过则 report CLI 以非零码退出。
EVAL_REGRESSION_TOLERANCE = 0.02
EVAL_JUDGE_PROMPT_VERSION = "kb-eval-judge-v1"
# LLM judge 的三档得分：supported / partial / unsupported。
JUDGE_SCORES = (1.0, 0.5, 0.0)
# 确定性护栏（D8）：评估必须在本地 embedding 下跑，分数才能跨 run 可比。
REQUIRED_EMBEDDING_PROVIDER = "local"

# 评估语料在 documents.source 上的标记；reseed 时按它清理旧语料。
EVAL_DOC_SOURCE = "eval-corpus"
EVAL_TITLE_PREFIX = "[EVAL] "
# golden 行内引用语料文档的前缀：expected_doc_ids: ["corpus:invoicing"]，
# 加载时经 corpus_map.json 解析成真实 doc_id——golden 集因此跨全新数据库仍然有效。
CORPUS_REF_PREFIX = "corpus:"
CORPUS_MAP_FILENAME = "corpus_map.json"

# 目录布局：golden 与 corpus 进版本库（D8），reports 是运行产物（git-ignored）。
EVAL_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = EVAL_ROOT / "golden"
CORPUS_DIR = EVAL_ROOT / "corpus"
REPORTS_DIR = EVAL_ROOT / "reports"

# 汇总里参与回归判定的核心指标（--judge off 也全部可得，D9）。
CORE_METRICS = (
    "hit_at_k",
    "mrr",
    "refusal_correctness_unanswerable",
    "refusal_correctness_answerable",
    "evidence_coverage",
    "citation_grounding",
)
