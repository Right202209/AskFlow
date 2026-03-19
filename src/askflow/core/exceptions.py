from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from askflow.core.logging import get_logger
from askflow.schemas.common import APIResponse

logger = get_logger(__name__)


class AskFlowError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AskFlowError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class UnauthorizedError(AskFlowError):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, status_code=401)


class ForbiddenError(AskFlowError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, status_code=403)


class RateLimitError(AskFlowError):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, status_code=429)


class ServiceUnavailableError(AskFlowError):
    def __init__(self, message: str = "Service temporarily unavailable") -> None:
        super().__init__(message, status_code=503)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AskFlowError)
    async def askflow_error_handler(request: Request, exc: AskFlowError) -> JSONResponse:
        logger.warning("application_error", error=exc.message, status_code=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=APIResponse(success=False, error=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=APIResponse(
                success=False, error="Validation error", data=exc.errors()
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=APIResponse(
                success=False, error="Internal server error", data=None
            ).model_dump(),
        )
