"""回答后的证据自检（plan-docs/honest-rag/02）。

两层：确定性层用正则抽取 [n] 引用标记并校验编号范围；LLM 评审层把
"答案 + 编号后的上下文块"交给一次带超时的判定调用，逐条判断引用是否有据可依。
任何失败（超时/解析错误/LLM 异常）都降级为 verdict="skipped"——自检永远不能
阻塞或破坏 message_end。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass

from askflow.core.logging import get_logger

logger = get_logger(__name__)

# 引用标记：与前端 web/src/lib/citations.tsx 的 CITATION_MARKER_RE 保持一致。
CITATION_MARKER_RE = re.compile(r"\[(\d{1,2})\]")
VERIFY_TIMEOUT_S = 8.0
VERIFY_PARTIAL_THRESHOLD = 0.5  # supported/total 低于该比例 → "fail"
VERIFY_MAX_CHUNK_CHARS = 800  # 评审提示词里每个 chunk 的预算
VERIFY_JUDGE_TEMPERATURE = 0.0

VERDICT_PASS = "pass"
VERDICT_PARTIAL = "partial"
VERDICT_FAIL = "fail"
VERDICT_SKIPPED = "skipped"

# harness trace 词表（AGENTS.md §4.5）。
VERIFY_SKIPPED_FLAG = "verify_skipped"
INVALID_CITATIONS_FLAG = "invalid_citations"

JUDGE_PROMPT = """You are a strict fact-checking judge. Given an assistant answer and the numbered context chunks it cites, decide for EACH citation marker whether the claim right before it is actually supported by that chunk.

Respond with ONLY strict JSON, no prose:
{{"claims": [{{"citation": <chunk number>, "supported": true|false}}]}}

### Context chunks
{chunks}

### Answer to verify
{answer}"""


@dataclass(frozen=True)
class VerificationResult:
    """一次自检的结论；随 message_end 下发并持久化到 messages.extra.verification。"""

    checked: bool  # False = 自检被跳过（超时/异常/无引用可查）
    supported: int
    total: int  # 答案中找到的有效引用数
    invalid_citations: list[int]  # 越界标记（如只有 5 条来源却出现 [7]）
    verdict: str  # "pass" | "partial" | "fail" | "skipped"

    def to_payload(self) -> dict:
        return asdict(self)


def extract_citations(answer: str, source_count: int) -> tuple[list[int], list[int]]:
    """抽取答案中的 [n] 标记，按编号是否落在来源范围内分成有效/越界两组（去重保序）。"""
    valid: list[int] = []
    invalid: list[int] = []
    for match in CITATION_MARKER_RE.finditer(answer):
        number = int(match.group(1))
        if 1 <= number <= source_count:
            if number not in valid:
                valid.append(number)
        elif number not in invalid:
            invalid.append(number)
    return valid, invalid


def _skipped(invalid_citations: list[int] | None = None) -> VerificationResult:
    return VerificationResult(
        checked=False,
        supported=0,
        total=0,
        invalid_citations=invalid_citations or [],
        verdict=VERDICT_SKIPPED,
    )


def _band_verdict(supported: int, total: int) -> str:
    if supported == total:
        return VERDICT_PASS
    if total > 0 and supported / total >= VERIFY_PARTIAL_THRESHOLD:
        return VERDICT_PARTIAL
    return VERDICT_FAIL


def _judge_chunks_block(sources: list[dict]) -> str:
    lines = []
    for source in sources:
        index = source.get("index")
        chunk = str(source.get("chunk", ""))[:VERIFY_MAX_CHUNK_CHARS]
        lines.append(f"[{index}] {source.get('title', '')}\n{chunk}")
    return "\n\n".join(lines)


def _parse_judge_response(raw: str, valid_citations: list[int]) -> tuple[int, int]:
    """解析评审 JSON；只统计答案中真实出现过的引用编号，防评审自由发挥。"""
    payload = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip("` \n"))
    claims = payload.get("claims", [])
    cited = set(valid_citations)
    judged = [c for c in claims if isinstance(c, dict) and c.get("citation") in cited]
    supported = sum(1 for c in judged if c.get("supported") is True)
    return supported, len(judged)


async def verify_answer(answer: str, sources: list[dict], llm) -> VerificationResult:
    """对完整答案做证据自检。永不抛异常——所有失败路径都折叠为 skipped。"""
    valid, invalid = extract_citations(answer, len(sources))
    if not valid:
        # 没有可核查的引用（含只有越界标记的情况）：flag 而不是判死。
        return _skipped(invalid_citations=invalid)

    prompt = JUDGE_PROMPT.format(chunks=_judge_chunks_block(sources), answer=answer)
    try:
        raw = await asyncio.wait_for(
            llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=VERIFY_JUDGE_TEMPERATURE,
            ),
            timeout=VERIFY_TIMEOUT_S,
        )
        supported, judged_total = _parse_judge_response(raw, valid)
    except Exception as e:
        logger.warning("verify_answer_skipped", error=str(e))
        return _skipped(invalid_citations=invalid)

    if judged_total == 0:
        return _skipped(invalid_citations=invalid)

    return VerificationResult(
        checked=True,
        supported=supported,
        total=judged_total,
        invalid_citations=invalid,
        verdict=_band_verdict(supported, judged_total),
    )
