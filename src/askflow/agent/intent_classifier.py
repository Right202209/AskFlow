from __future__ import annotations

import json
import re
from dataclasses import dataclass

from askflow.core.logging import get_logger
from askflow.core.metrics import INTENT_CLASSIFICATION_COUNT
from askflow.rag.llm_client import LLMClient
from askflow.schemas.intent import IntentResult

logger = get_logger(__name__)

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
    "handoff": ["转人工", "人工客服", "talk to human", "real person", "agent"],
    "complaint": ["投诉", "差评", "不满", "complain", "terrible", "worst"],
    "fault_report": ["报错", "错误", "bug", "500", "故障", "crash", "error", "exception"],
    "order_query": ["订单", "快递", "物流", "发货", "order", "shipping", "delivery", "tracking"],
}


class IntentClassifier:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def classify(self, message: str, context: list[dict[str, str]] | None = None) -> IntentResult:
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
            result = IntentResult(label="faq", confidence=0.5, needs_clarification=True)
            INTENT_CLASSIFICATION_COUNT.labels(intent="faq").inc()
            return result

    def _rule_classify(self, message: str) -> IntentResult | None:
        message_lower = message.lower()
        for intent, keywords in KEYWORD_RULES.items():
            for keyword in keywords:
                if keyword.lower() in message_lower:
                    return IntentResult(label=intent, confidence=0.95)
        return None

    async def _model_classify(self, message: str) -> IntentResult:
        prompt = INTENT_PROMPT.format(message=message)
        response = await self._llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100,
        )
        response = response.strip()
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            label = data.get("intent", "faq")
            confidence = float(data.get("confidence", 0.5))
            needs_clarification = confidence < 0.7
            return IntentResult(
                label=label,
                confidence=confidence,
                needs_clarification=needs_clarification,
            )
        return IntentResult(label="faq", confidence=0.5, needs_clarification=True)
