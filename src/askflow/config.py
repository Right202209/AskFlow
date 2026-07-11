from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Application
    app_name: str = "AskFlow"
    # 默认 production：本地开发必须显式 APP_ENV=development，避免运维忘记配置时仍带默认弱密钥跑起来。
    app_env: str = "production"
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

    # BM25 持久化路径——lifespan 启动时从此文件 reload；写文档后会重新落盘。
    bm25_index_path: str = "data/bm25_index.pkl"

    # 订单查询 webhook——未配置时 search_order 走 mock 行为。
    order_lookup_webhook_url: str | None = None
    order_lookup_timeout_s: float = 5.0
    # 透传给 webhook 的鉴权头（完整字符串，如 "Bearer xxx"）。
    order_lookup_auth_header: str | None = None

    # Auth
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Rate Limiting
    rate_limit_per_minute: int = 60

    # Ticket SLA——pending/processing 工单超过该时长记为 SLA 超时,运营 dashboard 据此告警。
    ticket_sla_hours: int = 24

    # Handoff——queued 超过该分钟数未被认领即超时升级为工单（plan agent-real-handoff/02 §7）。
    handoff_pickup_timeout_min: int = 10

    # PII 脱敏（ops-platform/02，D5）。日志脱敏默认开；存量消息脱敏默认关——
    # 脱敏存档会降级 handoff 摘要质量，是运营取舍（见 Slice 04 部署清单）。
    log_masking_enabled: bool = True
    mask_stored_messages: bool = False

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
