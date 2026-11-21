import multiprocessing
import os

# Server socket
host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8000")
bind = f"{host}:{port}"

# Worker processes
# For I/O bound async FastAPI applications, 2 to 4 workers per core is standard
default_workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
workers = int(os.getenv("WEB_CONCURRENCY", os.getenv("GUNICORN_WORKERS", str(default_workers))))
worker_class = "uvicorn.workers.UvicornWorker"

# Worker lifecycle & timeouts
# Complex agentic dynamic DAGs and LLM completions can take time; allow up to 120s
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

# Logging
loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"
errorlog = "-"
capture_output = True
