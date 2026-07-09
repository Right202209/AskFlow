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
        assert s.embedding_provider == "api"

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


class TestProductionSafetyCheck:
    """`_assert_production_safe_settings` 必须阻止生产环境继续使用默认 secret_key。"""

    def test_default_secret_in_development_is_allowed(self, monkeypatch):
        from askflow.main import DEFAULT_SECRET_KEY, _assert_production_safe_settings, settings

        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)
        # 不应抛出
        _assert_production_safe_settings()

    def test_default_secret_in_production_raises(self, monkeypatch):
        import pytest

        from askflow.main import DEFAULT_SECRET_KEY, _assert_production_safe_settings, settings

        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _assert_production_safe_settings()

    def test_custom_secret_in_production_passes(self, monkeypatch):
        from askflow.main import _assert_production_safe_settings, settings

        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "secret_key", "a-real-secret-please-rotate")
        _assert_production_safe_settings()

    def test_unconfigured_defaults_fail_fast(self, monkeypatch):
        """没有任何环境变量时，默认 app_env=production + 默认 secret_key 必须直接报错。"""
        import pytest

        from askflow.main import DEFAULT_SECRET_KEY, _assert_production_safe_settings, settings

        # 这是"运维忘了配 .env"的部署场景：Settings 的内置默认值组合（production +
        # 默认 secret）必须 fail-fast，不能默默放行。
        bare = Settings(_env_file=None)
        assert bare.app_env == "production"
        assert bare.secret_key == DEFAULT_SECRET_KEY

        monkeypatch.setattr(settings, "app_env", bare.app_env)
        monkeypatch.setattr(settings, "secret_key", bare.secret_key)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _assert_production_safe_settings()
