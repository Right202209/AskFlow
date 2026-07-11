"""prompt templates + versions（ops-platform/01：DB 化提示词，版本只追加）。

手写迁移：autogenerate 不会产出 FK 环（active_version_id ↔ template_id，
use_alter 语义 → 建表后补约束）也不会产出种子数据。种子内容是迁移日代码常量的
冻结快照（version 1）——之后代码常量只作为 DB 缺行时的兜底，不再回写。

Revision ID: 20260710_02
Revises: 20260710_01
Create Date: 2026-07-10
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260710_02"
down_revision: str | None = "20260710_01"
branch_labels = None
depends_on = None

# --- version 1 种子：与 2026-07-10 的代码常量逐字一致 ---

_RAG_SYSTEM = """You are AskFlow, an intelligent customer service assistant. Answer the user's question based ONLY on the provided numbered context chunks.

Citation rules:
- Immediately after each claim, cite the supporting chunk with a bare marker like [1] or [2]
- Use only the chunk numbers given in the context; never invent a number
- Do not answer beyond the provided context

Style rules:
- Answer in the same language as the user's question
- Be concise and accurate
- Do not make up information not in the context
- If the context doesn't contain enough information, say so honestly"""

_RAG_CONTEXT = """### Context

{chunks}

### User Question
{question}"""

_RAG_NO_RESULTS = (
    "Sorry, I couldn't find relevant information. "
    "Please try rephrasing your question or contact a human agent."
)

_RAG_LLM_DOWN = (
    "AI generation is temporarily unavailable. "
    "Here are the most relevant knowledge base excerpts:\n"
)

_INTENT_CLASSIFIER = """You are an intent classifier for a customer service system. Classify the user's message into one of the following intents:

- faq: General knowledge questions, FAQ inquiries
- product: Product-related questions, feature inquiries
- order_query: Order status, shipping, delivery queries
- fault_report: Bug reports, system errors, fault reports
- complaint: Complaints, dissatisfaction, suggestions
- handoff: Requests to talk to a human agent

Respond with ONLY a JSON object:
{{"intent": "<intent_label>", "confidence": <0.0-1.0>}}

User message: {message}"""

_AGENT_CLARIFY = "我不太确定您的需求，能否请您提供更多细节以便我更好地帮助您？"

# key → (description, variables, content)
_SEED_PROMPTS: dict[str, tuple[str, list[str], str]] = {
    "rag.system": ("RAG 回答系统提示（引用规则 + 风格规则）", [], _RAG_SYSTEM),
    "rag.context": ("RAG 用户消息模板（上下文块 + 问题）", ["chunks", "question"], _RAG_CONTEXT),
    "rag.fallback_no_results": ("检索零命中拒答文案", [], _RAG_NO_RESULTS),
    "rag.fallback_llm_down": (
        "LLM 不可用降级前缀（前端 MessageBubble 按该前缀识别降级渲染，慎改）",
        [],
        _RAG_LLM_DOWN,
    ),
    "intent.classifier": ("意图分类提示（六意图词表是契约，删标签需同步 AGENTS.md §1）", ["message"], _INTENT_CLASSIFIER),
    "agent.clarify": ("低置信度澄清话术", [], _AGENT_CLARIFY),
}


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("key", name="uniq_prompt_template_key"),
    )
    op.create_index("ix_prompt_templates_key", "prompt_templates", ["key"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("template_id", "version", name="uniq_prompt_version"),
    )
    op.create_index("ix_prompt_versions_template_id", "prompt_versions", ["template_id"])

    # FK 环的后补边：active_version_id → prompt_versions.id（模型侧 use_alter=True）。
    op.create_foreign_key(
        "fk_prompt_templates_active_version",
        "prompt_templates",
        "prompt_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _seed_prompts()


def _seed_prompts() -> None:
    """插模板 → 插 version 1 → 回填 active 指针（打破 FK 环的固定顺序）。"""
    templates = sa.table(
        "prompt_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("key", sa.String),
        sa.column("description", sa.Text),
        sa.column("variables", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
    )
    versions = sa.table(
        "prompt_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("template_id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer),
        sa.column("content", sa.Text),
        sa.column("comment", sa.Text),
    )

    for key, (description, variables, content) in _SEED_PROMPTS.items():
        template_id = uuid.uuid4()
        version_id = uuid.uuid4()
        op.bulk_insert(
            templates,
            [
                {
                    "id": template_id,
                    "key": key,
                    "description": description,
                    "variables": variables,
                    "is_active": True,
                }
            ],
        )
        op.bulk_insert(
            versions,
            [
                {
                    "id": version_id,
                    "template_id": template_id,
                    "version": 1,
                    "content": content,
                    "comment": "seed: code constant snapshot 2026-07-10",
                }
            ],
        )
        op.execute(
            sa.text(
                "UPDATE prompt_templates SET active_version_id = :version_id WHERE id = :template_id"
            ).bindparams(version_id=version_id, template_id=template_id)
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_prompt_templates_active_version", "prompt_templates", type_="foreignkey"
    )
    op.drop_index("ix_prompt_versions_template_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_prompt_templates_key", table_name="prompt_templates")
    op.drop_table("prompt_templates")
