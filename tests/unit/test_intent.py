from askflow.agent.intent_classifier import IntentClassifier
from askflow.agent.nodes import route_by_intent
from askflow.agent.state import AgentState
from askflow.schemas.intent import IntentResult


class TestRuleClassification:
    def test_handoff_keywords(self):
        classifier = IntentClassifier(llm=None)
        result = classifier._rule_classify("I want to talk to a human")
        assert result is not None
        assert result.label == "handoff"
        # 命中置信度从 0.95 降到 0.7，给 LLM 二次判断留覆盖空间。
        assert result.confidence == 0.7

    def test_complaint_keywords(self):
        classifier = IntentClassifier(llm=None)
        result = classifier._rule_classify("I want to complain about service")
        assert result is not None
        assert result.label == "complaint"

    def test_fault_keywords(self):
        classifier = IntentClassifier(llm=None)
        result = classifier._rule_classify("The system shows error 500")
        assert result is not None
        assert result.label == "fault_report"

    def test_order_keywords(self):
        classifier = IntentClassifier(llm=None)
        result = classifier._rule_classify("Where is my order?")
        assert result is not None
        assert result.label == "order_query"

    def test_no_match(self):
        classifier = IntentClassifier(llm=None)
        result = classifier._rule_classify("What is the weather today?")
        assert result is None


class TestHandoffRuleNarrowed:
    """Task 2：human/agent 必须在 talk/speak/transfer/escalate/real/live 上下文里
    才视为 handoff，否则脆性规则会把 "talk to the AI agent"、"sales agent"、
    "human override" 这类句子全部秒判 0.95 handoff。
    """

    @staticmethod
    def _classify(text: str):
        return IntentClassifier(llm=None)._rule_classify(text)

    # ---- 不应该进 handoff ----
    def test_talking_to_ai_agent_is_not_handoff(self):
        result = self._classify("I want to talk to the AI agent")
        assert result is None or result.label != "handoff"

    def test_sales_agent_self_intro_is_not_handoff(self):
        result = self._classify("I'm a sales agent looking for help")
        assert result is None or result.label != "handoff"

    def test_human_override_question_is_not_handoff(self):
        result = self._classify("is there a human override for this rule")
        assert result is None or result.label != "handoff"

    def test_descriptive_human_is_not_handoff(self):
        result = self._classify("this is more human than I expected")
        assert result is None or result.label != "handoff"

    # ---- 应该继续命中 handoff ----
    def test_transfer_to_human_agent_is_handoff(self):
        result = self._classify("transfer me to a human agent please")
        assert result is not None
        assert result.label == "handoff"

    def test_chinese_transfer_human_is_handoff(self):
        result = self._classify("我要转人工")
        assert result is not None
        assert result.label == "handoff"

    def test_speak_to_real_person_is_handoff(self):
        result = self._classify("can I speak to a real person")
        assert result is not None
        assert result.label == "handoff"


class TestRouteByIntent:
    def test_rag_route(self):
        state = AgentState(intent=IntentResult(label="faq", confidence=0.9))
        assert route_by_intent(state) == "rag"

    def test_handoff_route(self):
        state = AgentState(intent=IntentResult(label="handoff", confidence=0.95))
        assert route_by_intent(state) == "handoff"

    def test_ticket_route_fault(self):
        state = AgentState(intent=IntentResult(label="fault_report", confidence=0.8))
        assert route_by_intent(state) == "ticket"

    def test_ticket_route_complaint(self):
        state = AgentState(intent=IntentResult(label="complaint", confidence=0.85))
        assert route_by_intent(state) == "ticket"

    def test_clarify_route(self):
        state = AgentState(
            intent=IntentResult(label="faq", confidence=0.3, needs_clarification=True),
            needs_clarification=True,
        )
        assert route_by_intent(state) == "clarify"

    def test_no_intent_defaults_to_rag(self):
        state = AgentState()
        assert route_by_intent(state) == "rag"
