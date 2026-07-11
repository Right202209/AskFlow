from __future__ import annotations

import json
import re

from askflow.core.logging import get_logger
from askflow.core.metrics import INTENT_CLASSIFICATION_COUNT
from askflow.core.prompts import PROMPT_KEY_INTENT_CLASSIFIER, get_prompt
from askflow.rag.llm_client import LLMClient
from askflow.schemas.intent import IntentResult

logger = get_logger(__name__)

DEFAULT_INTENT = "faq"

# 代码兜底默认值：运行时优先读 DB 模板（core/prompts.py，键 intent.classifier）。
# 六意图词表是 AGENTS.md §1 的契约——DB 侧编辑删掉标签会改变分类行为，管理端有提示。
INTENT_PROMPT = """You are an intent classifier for a customer service system. Classify the user's message into one of the following intents:

- faq: General knowledge questions, FAQ inquiries
- product: Product-related questions, feature inquiries
- order_query: Order status, shipping, delivery queries
- fault_report: Bug reports, system errors, fault reports
- complaint: Complaints, dissatisfaction, suggestions
- handoff: Requests to talk to a human agent

Respond with ONLY a JSON object:
{{"intent": "<intent_label>", "confidence": <0.0-1.0>}}

User message: {message}"""

KEYWORD_RULES: dict[str, list[str]] = {
    "complaint": ["投诉", "差评", "不满", "complain", "terrible", "worst"],
    "fault_report": ["报错", "错误", "bug", "500", "故障", "crash", "error", "exception"],
    "order_query": ["订单", "快递", "物流", "发货", "order", "shipping", "delivery", "tracking"],
}

# 关键词命中默认置信度。从 0.95 降到 0.7，给 LLM 二次判断留覆盖空间——避免脆性
# 规则在边缘 case（"talk to the AI agent"、"sales agent"）上一锤定音。
KEYWORD_HIT_CONFIDENCE = 0.7

# handoff 规则单独拎出来：必须把 human/agent 与 talk/speak/transfer/escalate/real/
# live/customer service 等上下文词共现才算"想转人工"，否则极易把
# "I want to talk to the AI agent" / "is there a human override" 误判成 handoff。
HANDOFF_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # 中文：直接表达，没有歧义
        r"转人工",
        r"转\s*接\s*人工",
        r"人工客服",
        r"真人客服",
        r"找.{0,6}(?:客服|人工)",
        # talk/speak to (a|the) human —— "AI human" 在客服场景里几乎不存在
        r"\b(?:talk|speak|chat)\s+(?:to|with)\s+(?:a\s+|an\s+|the\s+|some\s+)?human\b",
        # talk/speak to (a) real/live/customer service person/agent/rep/human
        r"\b(?:talk|speak|chat)\s+(?:to|with)\s+(?:a\s+|an\s+|the\s+)?"
        r"(?:real|live|actual|customer\s+service)\s+"
        r"(?:person|agent|rep|representative|human)\b",
        # transfer/escalate (me) (to) (a) human/agent/person/rep
        r"\b(?:transfer|escalate)\s+(?:me\s+)?(?:to\s+)?(?:a\s+|an\s+|the\s+)?"
        r"(?:human|agent|person|rep|representative)\b",
        # standalone "real/live/actual person/human/agent/representative"
        r"\b(?:real|live|actual)\s+(?:person|human|agent|representative)\b",
        # "human agent" / "human rep" —— 与 "sales agent" 区分
        r"\bhuman\s+(?:agent|rep|representative|operator|support)\b",
        # 直接"connect/get me ... human/agent"
        r"\b(?:connect|get)\s+(?:me\s+)?(?:with\s+|to\s+)?(?:a\s+|an\s+|the\s+)?"
        r"(?:real\s+|live\s+|human\s+)(?:person|human|agent|representative|operator)\b",
    )
)


class IntentClassifier:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def classify(
        self, message: str, context: list[dict[str, str]] | None = None
    ) -> IntentResult:
        rule_result = self._rule_classify(message)
        if rule_result and rule_result.confidence >= 0.9:
            INTENT_CLASSIFICATION_COUNT.labels(intent=rule_result.label).inc()
            return rule_result

        try:
            model_result = await self._model_classify(message)
            if rule_result:
                if rule_result.confidence > model_result.confidence:
                    INTENT_CLASSIFICATION_COUNT.labels(intent=rule_result.label).inc()
                    return rule_result
            INTENT_CLASSIFICATION_COUNT.labels(intent=model_result.label).inc()
            return model_result
        except Exception as e:
            logger.warning("model_classification_failed", error=str(e))
            if rule_result:
                INTENT_CLASSIFICATION_COUNT.labels(intent=rule_result.label).inc()
                return rule_result
            result = IntentResult(label=DEFAULT_INTENT, confidence=0.5, needs_clarification=True)
            INTENT_CLASSIFICATION_COUNT.labels(intent=DEFAULT_INTENT).inc()
            return result

    def _rule_classify(self, message: str) -> IntentResult | None:
        # handoff 走专用上下文正则，规避 human/agent 的歧义。
        for pattern in HANDOFF_PATTERNS:
            if pattern.search(message):
                return IntentResult(label="handoff", confidence=KEYWORD_HIT_CONFIDENCE)
        message_lower = message.lower()
        for intent, keywords in KEYWORD_RULES.items():
            for keyword in keywords:
                if keyword.lower() in message_lower:
                    return IntentResult(label=intent, confidence=KEYWORD_HIT_CONFIDENCE)
        return None

    async def _model_classify(self, message: str) -> IntentResult:
        prompt_template = await get_prompt(PROMPT_KEY_INTENT_CLASSIFIER)
        prompt = prompt_template.format(message=message)
        response = await self._llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100,
        )
        response = response.strip()
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            label = data.get("intent", DEFAULT_INTENT)
            confidence = float(data.get("confidence", 0.5))
            needs_clarification = confidence < 0.7
            return IntentResult(
                label=label,
                confidence=confidence,
                needs_clarification=needs_clarification,
            )
        return IntentResult(label=DEFAULT_INTENT, confidence=0.5, needs_clarification=True)
