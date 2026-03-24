import pytest

from askflow.core.auth import extract_bearer_token
from askflow.core.exceptions import UnauthorizedError


class TestExtractBearerToken:
    def test_extracts_valid_bearer_token(self):
        assert extract_bearer_token("Bearer token-123") == "token-123"

    def test_allows_case_insensitive_scheme(self):
        assert extract_bearer_token("bearer token-123") == "token-123"

    def test_trims_extra_whitespace(self):
        assert extract_bearer_token("  Bearer    token-123   ") == "token-123"

    @pytest.mark.parametrize(
        "authorization",
        [None, "", "Bearer", "Bearer    ", "Token abc", "Basic abc"],
    )
    def test_raises_for_invalid_header(self, authorization):
        with pytest.raises(UnauthorizedError, match="Missing or invalid authorization header"):
            extract_bearer_token(authorization)
