import pytest

from askflow.config import Settings


class TestConfig:
    def test_defaults(self):
        s = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        )
        assert s.app_name == "AskFlow"
        assert s.rate_limit_per_minute == 60
        assert s.jwt_algorithm == "HS256"
        assert s.embedding_provider == "local"

    def test_custom_values(self):
        s = Settings(
            _env_file=None,
            app_name="CustomApp",
            debug=True,
            rate_limit_per_minute=120,
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        )
        assert s.app_name == "CustomApp"
        assert s.debug is True
        assert s.rate_limit_per_minute == 120
