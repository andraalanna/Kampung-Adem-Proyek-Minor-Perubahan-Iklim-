FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[satellite]"

COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd --system --uid 10001 app
USER app

# Overridden per service in infra/docker-compose.yml (api, ingest, worker).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
