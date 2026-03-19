import pytest

from askflow.core.exceptions import (
    AskFlowError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    UnauthorizedError,
)


class TestExceptions:
    def test_askflow_error(self):
        err = AskFlowError("test error", 500)
        assert err.message == "test error"
        assert err.status_code == 500

    def test_not_found(self):
        err = NotFoundError()
        assert err.status_code == 404

    def test_unauthorized(self):
        err = UnauthorizedError()
        assert err.status_code == 401

    def test_forbidden(self):
        err = ForbiddenError()
        assert err.status_code == 403

    def test_rate_limit(self):
        err = RateLimitError()
        assert err.status_code == 429

    def test_service_unavailable(self):
        err = ServiceUnavailableError()
        assert err.status_code == 503

    def test_custom_message(self):
        err = NotFoundError("Document not found")
        assert err.message == "Document not found"
