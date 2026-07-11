"""草稿知识条目：素材组装 → 可选 LLM 草拟 → 审批发布/驳回（plan-docs/knowledge-loop/02）。

LLM 草拟是便利功能而非信任边界（D7）：超时/失败一律回落到原始素材，接口总能建出草稿；
真正的信任边界是人工审批（approve），发布走 knowledge/publisher.py 的唯一三 store 实现。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from askflow.config import settings
from askflow.core.exceptions import ConflictError, NotFoundError
from askflow.core.logging import get_logger
from askflow.knowledge.publisher import PublishError, PublishRequest, publish_document_bytes
from askflow.models.document import Document
from askflow.models.knowledge_draft import DraftStatus, KnowledgeDraft
from askflow.models.knowledge_gap import GapStatus
from askflow.rag.llm_client import LLMClient
from askflow.repositories.knowledge_draft_repo import KnowledgeDraftRepo
from askflow.repositories.knowledge_gap_repo import KnowledgeGapRepo
from askflow.repositories.message_repo import MessageRepo
from askflow.repositories.ticket_repo import TicketRepo

logger = get_logger(__name__)

# --- 常量（plan-docs/knowledge-loop/02 §Constants）---
DRAFT_SYNTHESIS_TIMEOUT_S = 8
DRAFT_SYNTHESIS_PROMPT_VERSION = "kb-draft-v1"
MAX_TRANSCRIPT_CHARS = 8000
MAX_DRAFT_ANSWER_CHARS = 20000
KB_DOC_SOURCE = "knowledge-loop"
KB_TITLE_PREFIX = "[KB] "
DEFAULT_DRAFTS_PAGE_SIZE = 20
KB_DOC_CONTENT_TYPE = "text/markdown"
# documents.title 列宽（String(255)）；发布标题按此截断。
DOCUMENT_TITLE_MAX_CHARS = 255
EMPTY_ANSWER_PLACEHOLDER = "（待补充：请在评审时填写答案内容。）"

DRAFT_SYNTHESIS_SYSTEM_PROMPT = (
    "You are a knowledge-base editor. Write a concise Q&A knowledge entry in markdown, "
    "grounded ONLY in the provided material. Answer in the same language as the question. "
    "Do not invent facts that are not in the material."
)
DRAFT_SYNTHESIS_USER_TEMPLATE = """### Question
{question}

### Material
{material}

### Task
Write the answer body (markdown, no title heading) for this question based only on the material."""


@dataclass(frozen=True)
class DraftSource:
    """草稿素材来源：工单 / 会话转录 / 人工输入，三选一（可全空建空草稿）。"""

    ticket_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    manual_answer: str | None = None
    synthesize: bool = False


def render_draft_markdown(draft: KnowledgeDraft) -> bytes:
    """发布用 markdown：# 问题 + 答案 + 溯源脚注（gap/ticket/conversation id）。"""
    provenance = [f"source: {KB_DOC_SOURCE}"]
    if draft.gap_id:
        provenance.append(f"gap: {draft.gap_id}")
    if draft.source_ticket_id:
        provenance.append(f"ticket: {draft.source_ticket_id}")
    if draft.source_conversation_id:
        provenance.append(f"conversation: {draft.source_conversation_id}")
    lines = [f"# {draft.question}", "", draft.answer, "", "---", "", " | ".join(provenance), ""]
    return "\n".join(lines).encode("utf-8")


class DraftService:
    def __init__(self, db: AsyncSession, llm: LLMClient) -> None:
        self._db = db
        self._llm = llm
        self._drafts = KnowledgeDraftRepo(db)

    async def create_from_gap(
        self,
        gap_id: uuid.UUID,
        source: DraftSource,
        created_by: uuid.UUID,
    ) -> KnowledgeDraft:
        gap = await KnowledgeGapRepo(self._db).get_by_id(gap_id)
        if gap is None:
            raise NotFoundError("Knowledge gap not found")

        material = await self._assemble_material(source)
        answer, synthesis = material, None
        if source.synthesize:
            answer, synthesis = await self._synthesize(gap.question, material)
        answer = answer[:MAX_DRAFT_ANSWER_CHARS] or EMPTY_ANSWER_PLACEHOLDER

        return await self._drafts.create(
            gap_id=gap.id,
            question=gap.question,
            answer=answer,
            created_by=created_by,
            source_ticket_id=source.ticket_id,
            source_conversation_id=source.conversation_id,
            synthesis=synthesis,
        )

    async def approve(self, draft_id: uuid.UUID, reviewer_id: uuid.UUID) -> Document:
        """条件迁移抢锁 → 渲染 → 三 store 发布 → 回填 doc id + gap promoted；失败回退可重试。"""
        draft = await self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError("Draft not found")
        won = await self._drafts.transition_status(
            draft_id,
            from_status=DraftStatus.draft,
            to_status=DraftStatus.approved,
            reviewed_by=reviewer_id,
        )
        if won is None:
            raise ConflictError("Draft already reviewed")

        title = f"{KB_TITLE_PREFIX}{won.question}"[:DOCUMENT_TITLE_MAX_CHARS]
        request = PublishRequest(
            title=title,
            filename=f"kb-{draft_id}.md",
            content_bytes=render_draft_markdown(won),
            content_type=KB_DOC_CONTENT_TYPE,
            source=KB_DOC_SOURCE,
            extra_tags={"kb_draft_id": str(draft_id)},
        )
        try:
            doc = await publish_document_bytes(self._db, request)
        except PublishError:
            # 发布失败不能把草稿滞留在 approved：回退到 draft，让审批可重试。
            await self._drafts.transition_status(
                draft_id, from_status=DraftStatus.approved, to_status=DraftStatus.draft
            )
            raise

        won.published_doc_id = doc.id
        await self._promote_gap(won.gap_id, doc.id)
        await self._db.flush()
        return doc

    async def reject(
        self,
        draft_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        review_note: str | None,
    ) -> KnowledgeDraft:
        """驳回草稿；gap 保持 open——问题本身仍是真实缺口。"""
        draft = await self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError("Draft not found")
        updated = await self._drafts.transition_status(
            draft_id,
            from_status=DraftStatus.draft,
            to_status=DraftStatus.rejected,
            reviewed_by=reviewer_id,
            review_note=review_note,
        )
        if updated is None:
            raise ConflictError("Draft already reviewed")
        return updated

    async def _assemble_material(self, source: DraftSource) -> str:
        if source.ticket_id is not None:
            return await self._ticket_material(source.ticket_id)
        if source.conversation_id is not None:
            return await self._transcript_material(source.conversation_id)
        if source.manual_answer:
            return source.manual_answer
        # 没有任何素材也允许建草稿，评审页里人工补齐。
        return EMPTY_ANSWER_PLACEHOLDER

    async def _ticket_material(self, ticket_id: uuid.UUID) -> str:
        ticket = await TicketRepo(self._db).get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Source ticket not found")
        parts = [f"## {ticket.title}"]
        if ticket.description:
            parts.append(ticket.description)
        if ticket.content:
            parts.append(json.dumps(ticket.content, ensure_ascii=False, indent=2))
        return "\n\n".join(parts)

    async def _transcript_material(self, conversation_id: uuid.UUID) -> str:
        messages = await MessageRepo(self._db).list_by_conversation(conversation_id)
        if not messages:
            raise NotFoundError("Source conversation has no messages")
        lines = [f"{m.role.value}: {m.content}" for m in messages]
        return "\n".join(lines)[:MAX_TRANSCRIPT_CHARS]

    async def _synthesize(self, question: str, material: str) -> tuple[str, dict]:
        """一次 LLM 调用草拟答案；超时/异常回落原始素材并标记 generated=false（D7）。"""
        meta = {
            "model": settings.llm_model,
            "prompt_version": DRAFT_SYNTHESIS_PROMPT_VERSION,
            "generated": True,
        }
        messages = [
            {"role": "system", "content": DRAFT_SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": DRAFT_SYNTHESIS_USER_TEMPLATE.format(
                    question=question, material=material[:MAX_TRANSCRIPT_CHARS]
                ),
            },
        ]
        try:
            answer = await asyncio.wait_for(
                self._llm.chat(messages), timeout=DRAFT_SYNTHESIS_TIMEOUT_S
            )
            if answer.strip():
                return answer, meta
        except Exception as exc:
            logger.warning("draft_synthesis_failed", error=str(exc))
        return material, {**meta, "generated": False}

    async def _promote_gap(self, gap_id: uuid.UUID | None, doc_id: uuid.UUID) -> None:
        if gap_id is None:
            return
        gap = await KnowledgeGapRepo(self._db).get_by_id(gap_id)
        if gap is None:
            return
        gap.status = GapStatus.promoted
        gap.promoted_doc_id = doc_id
