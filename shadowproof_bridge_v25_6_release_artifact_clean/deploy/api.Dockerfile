# Minimal API container for pilot deployments.
# Production builders should pin this base image by digest in their registry mirror.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SHADOWPROOF_ENVIRONMENT=production \
    SHADOWPROOF_DATA_DIR=/tmp/shadowproof_data

WORKDIR /app
COPY pyproject.toml ./
COPY shadowproof_core ./shadowproof_core
COPY schemas ./schemas
COPY docs ./docs
COPY examples ./examples
COPY scripts ./scripts
COPY lean_project_template ./lean_project_template
RUN pip install --no-cache-dir -e ".[prod]" \
    && useradd --create-home --shell /usr/sbin/nologin shadowproof \
    && chown -R shadowproof:shadowproof /app

USER shadowproof
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/livez', timeout=2).read()"
CMD ["uvicorn", "shadowproof_core.asgi:app", "--host", "0.0.0.0", "--port", "8765"]
