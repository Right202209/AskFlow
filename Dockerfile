FROM node:22-slim AS frontend-build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci
COPY static/src/ static/src/
RUN npm run build

FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

FROM base AS runtime

COPY src/ src/
COPY static/*.html static/
COPY static/style.css static/
COPY --from=frontend-build /app/static/dist/ static/dist/
COPY alembic/ alembic/
COPY alembic.ini .

EXPOSE 8000

CMD ["uvicorn", "askflow.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
