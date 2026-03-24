from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Application
    app_name: str = "AskFlow"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-to-a-random-secret-key"

    # Database
    database_url: str = "postgresql+asyncpg://askflow:askflow@localhost:5432/askflow"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "askflow-docs"
    minio_secure: bool = False

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8100

    # LLM
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.7

    # Embedding
    embedding_provider: str = "api"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_api_url: str = "http://localhost:11434/v1"
    embedding_api_key: str = "ollama"
    embedding_dimension: int = 384

    # Auth
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Rate Limiting
    rate_limit_per_minute: int = 60

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
