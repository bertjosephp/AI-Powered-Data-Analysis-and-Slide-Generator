# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install .

RUN useradd --create-home appuser
USER appuser
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')"

# Jobs live in memory, so run exactly one worker process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
