# syntax=docker/dockerfile:1
FROM python:3.12-slim

# No .pyc files; unbuffered stdout so magic-link console output shows in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code.
COPY . .

# Run as an unprivileged user. instance/ holds the SQLite DB and media/ holds
# admin-uploaded puzzle images — mount a volume at each (see docker-compose).
RUN useradd --create-home --uid 10001 appuser \
    && chmod +x docker-entrypoint.sh \
    && mkdir -p /app/instance /app/media \
    && chown -R appuser:appuser /app
USER appuser

# Default media location inside the container (override via env if desired).
ENV MEDIA_ROOT=/app/media

# Declared so the image documents its writable data dirs; compose binds named volumes.
VOLUME ["/app/instance", "/app/media"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status==200 else 1)"]

# Entrypoint creates the DB schema, then runs the CMD (gunicorn).
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "wsgi:app"]
