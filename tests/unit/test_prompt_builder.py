import pytest

from askflow.rag.prompt_builder import build_fallback_response, build_rag_prompt
from askflow.rag.retriever import RetrievalResult


def _make_result(title="Test Doc", text="Sample text", score=0.9):
    return RetrievalResult(
        id="test-1",
        document=text,
        metadata={"title": title},
        score=score,
        source="vector",
    )


class TestBuildRagPrompt:
    def test_basic_prompt(self):
        results = [_make_result()]
        messages = build_rag_prompt("What is X?", results)
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert "What is X?" in messages[-1]["content"]
        assert "Test Doc" in messages[-1]["content"]

    def test_with_history(self):
        results = [_make_result()]
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        messages = build_rag_prompt("follow up", results, history)
        assert len(messages) == 4  # system + 2 history + user

    def test_empty_results(self):
        messages = build_rag_prompt("question", [])
        assert len(messages) == 2


class TestBuildFallbackResponse:
    def test_no_results(self):
        response = build_fallback_response([])
        assert "Sorry" in response

    def test_with_results(self):
        results = [_make_result(title="My Doc", text="Important info")]
        response = build_fallback_response(results)
        assert "My Doc" in response
        assert "unavailable" in response.lower()
