from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from askflow.config import settings
from askflow.core.database import engine
from askflow.core.exceptions import register_exception_handlers
from askflow.core.middleware import setup_middleware
from askflow.core.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.initialize()
    yield
    await engine.dispose()
    await redis_client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    setup_middleware(app)
    register_exception_handlers(app)

    from askflow.rag.router import router as rag_router
    from askflow.embedding.router import router as embedding_router
    from askflow.chat.router import router as chat_router
    from askflow.agent.router import router as agent_router
    from askflow.ticket.router import router as ticket_router
    from askflow.admin.router import router as admin_router
    from askflow.core.metrics import router as metrics_router

    app.include_router(rag_router, prefix="/api/v1/rag", tags=["RAG"])
    app.include_router(embedding_router, prefix="/api/v1/embedding", tags=["Embedding"])
    app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
    app.include_router(agent_router, prefix="/api/v1/agent", tags=["Agent"])
    app.include_router(ticket_router, prefix="/api/v1/tickets", tags=["Tickets"])
    app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])
    app.include_router(metrics_router, tags=["Metrics"])

    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return RedirectResponse(url="/static/index.html", status_code=307)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
