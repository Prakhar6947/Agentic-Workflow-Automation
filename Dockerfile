# ==============================================================================
# Production Dockerfile: Agentic Workflow Automation Engine
# Base: python:3.12-slim with non-root security context & healthcheck
# ==============================================================================

FROM python:3.12-slim AS runtime

# Prevents Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install minimal OS dependencies needed for runtime and healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user & group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and configuration
COPY . .

# Ensure appuser owns the application directory and runtime data paths
RUN chown -R appuser:appgroup /app && \
    chmod -R 755 /app

# Switch to unprivileged user
USER appuser

# Expose HTTP port
EXPOSE 8000

# Container healthcheck using the native /health probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# Launch production ASGI server via Gunicorn
CMD ["gunicorn", "-c", "gunicorn_conf.py", "app.main:app"]
