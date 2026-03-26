FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md README_zh.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system askflow && adduser --system --ingroup askflow askflow

COPY --from=builder /usr/local /usr/local
COPY --chown=askflow:askflow alembic/ alembic/
COPY --chown=askflow:askflow alembic.ini ./

USER askflow

EXPOSE 8000

CMD ["uvicorn", "askflow.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
