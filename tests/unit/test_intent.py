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
        assert result.confidence >= 0.9

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
