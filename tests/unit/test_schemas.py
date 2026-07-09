import pytest
from pydantic import ValidationError

from askflow.schemas.common import APIResponse, PaginatedResponse
from askflow.schemas.ticket import TicketCreate, TicketUpdate
from askflow.schemas.auth import LoginRequest, RegisterRequest


class TestAPIResponse:
    def test_success_response(self):
        resp = APIResponse(data={"key": "value"})
        assert resp.success is True
        assert resp.data == {"key": "value"}
        assert resp.error is None

    def test_error_response(self):
        resp = APIResponse(success=False, error="Not found")
        assert resp.success is False
        assert resp.error == "Not found"


class TestPaginatedResponse:
    def test_pagination(self):
        resp = PaginatedResponse(data=[1, 2, 3], total=100, page=2, limit=20)
        assert len(resp.data) == 3
        assert resp.total == 100


class TestTicketCreate:
    def test_valid_ticket(self):
        ticket = TicketCreate(type="bug", title="Test bug")
        assert ticket.type == "bug"
        assert ticket.priority == "medium"

    def test_with_all_fields(self):
        ticket = TicketCreate(
            type="complaint",
            title="Bad service",
            description="Details here",
            priority="high",
        )
        assert ticket.priority == "high"


class TestTicketUpdate:
    def test_rejects_null_status_when_provided(self):
        with pytest.raises(ValidationError):
            TicketUpdate(status=None)

    def test_rejects_null_priority_when_provided(self):
        with pytest.raises(ValidationError):
            TicketUpdate(priority=None)


class TestAuthSchemas:
    def test_login_request(self):
        req = LoginRequest(username="test", password="pass")
        assert req.username == "test"

    def test_register_request(self):
        req = RegisterRequest(username="test", email="t@t.com", password="pass")
        assert req.email == "t@t.com"
