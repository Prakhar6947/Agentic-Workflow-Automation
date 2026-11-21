# Production Deployment Guide: Agentic Workflow Automation Engine

This guide provides end-to-end instructions for deploying the **Agentic Workflow Automation Engine** to production across Docker, Kubernetes, Cloud Run, AWS ECS, and PaaS platforms (Render/Railway).

---

## 1. Production Architecture Overview

The system runs as an enterprise-grade ASGI application with the following production topology:

```text
               ┌────────────────────────┐
               │ Internet / Load Baler  │
               └───────────┬────────────┘
                           │ (HTTPS :443)
                           ▼
               ┌────────────────────────┐
               │    Ingress / NGINX     │
               └───────────┬────────────┘
                           │ (HTTP :8000)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Container Pod (Gunicorn)                 │
│                                                             │
│  Master Process (gunicorn_conf.py)                          │
│  ├── Worker 1 (uvicorn.workers.UvicornWorker)               │
│  ├── Worker 2 (uvicorn.workers.UvicornWorker)               │
│  ├── Worker 3 (uvicorn.workers.UvicornWorker)               │
│  └── Worker 4 (uvicorn.workers.UvicornWorker)               │
│                                                             │
│  Runtime Services:                                          │
│  ├── LangGraph Multi-Agent Orchestrator (StateGraph)        │
│  ├── Extensible Plugin Registry (Pydantic validated)        │
│  └── APScheduler Engine (Synchronized with SQL schedules)   │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
    ┌──────────────────────┐        ┌──────────────────────┐
    │  PostgreSQL 16 DB    │        │  Mounted Volumes     │
    │  (Connection Pool)   │        │  (/app/data/*.json)  │
    └──────────────────────┘        └──────────────────────┘
```

---

## 2. Docker & Container Deployment

### Option A: Full Production Stack (PostgreSQL + Engine App)

The primary deployment model pairs the engine with a high-availability PostgreSQL 16 container:

```bash
# 1. Prepare environment secrets
cp .env.example .env
# Edit .env with your LLM API keys and production passwords

# 2. Build and launch all services in background
docker compose up --build -d

# 3. Verify health
docker compose ps
curl http://localhost:8000/health
```

The app will automatically:
- Wait for PostgreSQL to become healthy via container healthchecks.
- Automatically initialize all database tables (`init_db()`).
- Seed predefined workflows (`WF001`–`WF004`).
- Restore active cron triggers into APScheduler.

### Option B: Standalone Lightweight Container (SQLite)

For resource-constrained environments or edge deployments:

```bash
docker compose -f docker-compose.sqlite.yml up --build -d
```

### Option C: Bare Metal / VM Production Run (Gunicorn)

To run directly on a Linux/macOS host with Gunicorn:

```bash
# Activate virtual environment
source .venv/bin/activate

# Launch Gunicorn with production configuration
gunicorn -c gunicorn_conf.py app.main:app
```

---

## 3. Kubernetes Deployment (EKS, GKE, AKS, On-Prem)

Production manifests are pre-configured in the `k8s/` directory.

### Step 1: Create Secrets

Create your Kubernetes secret from `k8s/secret.example.yaml`:

```bash
kubectl create secret generic workflow-engine-secrets \
  --from-literal=DATABASE_URL="postgresql+psycopg2://user:pass@postgres-host:5432/workflow_engine" \
  --from-literal=GOOGLE_API_KEY="your-google-api-key" \
  --from-literal=OPENAI_API_KEY="" \
  --from-literal=SMTP_HOST="smtp.gmail.com" \
  --from-literal=SMTP_PORT="587" \
  --from-literal=SMTP_USER="alerts@company.com" \
  --from-literal=SMTP_PASSWORD="app-password" \
  --from-literal=SMTP_FROM="alerts@company.com"
```

### Step 2: Apply Manifests

```bash
# 1. Apply ConfigMap
kubectl apply -f k8s/configmap.yaml

# 2. Deploy Application (2 Replicas, rolling update, non-root security context)
kubectl apply -f k8s/deployment.yaml

# 3. Create ClusterIP Service
kubectl apply -f k8s/service.yaml

# 4. Create Ingress (NGINX with 120s timeouts for long-running workflows)
kubectl apply -f k8s/ingress.yaml
```

### Step 3: Monitor Rollout

```bash
kubectl rollout status deployment/workflow-engine
kubectl get pods -l app=workflow-engine
```

---

## 4. Cloud Platform Runbooks

### A. Google Cloud Run

1. **Build and push image to Google Artifact Registry**:
   ```bash
   gcloud builds submit --tag gcr.io/PROJECT_ID/workflow-engine:latest
   ```
2. **Deploy to Cloud Run**:
   ```bash
   gcloud run deploy workflow-engine \
     --image gcr.io/PROJECT_ID/workflow-engine:latest \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars ENVIRONMENT=production,PORT=8080 \
     --set-secrets DATABASE_URL=WORKFLOW_DB_URL:latest,GOOGLE_API_KEY=GEMINI_API_KEY:latest \
     --timeout 120s \
     --memory 1Gi \
     --cpu 1
   ```

### B. AWS ECS (Fargate) / AWS App Runner

1. **Push image to AWS ECR**:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
   docker build -t workflow-engine .
   docker tag workflow-engine:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/workflow-engine:latest
   docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/workflow-engine:latest
   ```
2. **Create ECS Task Definition**:
   - Container port: `8000`
   - CPU: `512` (0.5 vCPU), Memory: `1024` (1 GB)
   - Essential: `true`
   - Healthcheck command: `CMD-SHELL, curl -f http://localhost:8000/health || exit 1`
   - Environment variables: Load from AWS Secrets Manager / Parameter Store.

### C. Render / Railway / Heroku

Both platforms automatically detect `Dockerfile` or `Procfile`:
1. Connect your Git repository.
2. Under **Environment**, attach a Managed PostgreSQL instance. The platform provides `DATABASE_URL` (the app automatically converts `postgres://` to `postgresql+psycopg2://`).
3. Add `GOOGLE_API_KEY` or `OPENAI_API_KEY`.
4. The service will build and launch using `Procfile`:
   ```bash
   web: gunicorn -c gunicorn_conf.py app.main:app
   ```

---

## 5. Health Checks & Observability

The application provides dedicated observability endpoints compatible with Kubernetes and Docker health checks:

| Endpoint | HTTP Status | Purpose | Description |
|---|---|---|---|
| `GET /health` | `200` / `503` | Overall Health | Probes SQL connection (`SELECT 1`), scheduler status, and system uptime. |
| `GET /ready` | `200` / `503` | Readiness Probe | Verifies the database is connected and ready to accept incoming API requests. |
| `GET /live` | `200` | Liveness Probe | Verifies the process is alive. |

### Sample `/health` Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "scheduler": "running",
  "version": "1.0.0",
  "uptime_seconds": 384.12
}
```

---

## 6. Production Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `production` | Deployment mode (`production` or `development`) |
| `PORT` | `8000` | Port for Gunicorn / Uvicorn to bind |
| `HOST` | `0.0.0.0` | Bind host address |
| `DATABASE_URL` | `sqlite:///./workflow_engine.db` | SQLAlchemy connection URI (supports SQLite & PostgreSQL) |
| `GUNICORN_WORKERS` | `min(CPU*2+1, 4)` | Number of worker processes (recommended: 2–4 per CPU core) |
| `GUNICORN_TIMEOUT` | `120` | Max worker execution timeout in seconds (tuned for LLM dynamic DAGs) |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed CORS domains |
| `LLM_PROVIDER` | `gemini` | Primary LLM provider (`gemini`, `openai`, `fallback`) |
| `GOOGLE_API_KEY` | *(empty)* | Google Gemini API key for dynamic planning |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `OPENAI_API_KEY` | *(empty)* | Optional OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model name |
| `DEFAULT_OPS_EMAIL`| `ops-team@company.com` | Default notification recipient for operational reports |
| `SMTP_HOST` | *(empty)* | Outgoing SMTP host for email notifications |
| `SMTP_PORT` | `587` | Outgoing SMTP port (587 for TLS, 465 for SSL) |
| `SMTP_USER` | *(empty)* | SMTP username |
| `SMTP_PASSWORD` | *(empty)* | SMTP password |
| `SMTP_FROM` | *(empty)* | Sender email address |
| `ALERTS_JSON_PATH` | `data/alerts.json` | Path to alert telemetry dataset |
| `PERFORMANCE_JSON_PATH` | `data/performance_stats.json` | Path to link performance telemetry dataset |

---

## 7. Production Security & Hardening

1. **Non-Root Execution**:
   The Docker container runs as unprivileged user `appuser` (UID: `10001`, GID: `10001`).
2. **Safe AST Evaluation**:
   Step conditions in workflow DAGs use Python's `ast` parser (no `eval()` or `exec()`).
3. **Database Connection Pooling**:
   PostgreSQL connections use `pool_pre_ping=True` and `pool_recycle=1800` to prevent stale connection timeouts.
4. **Secret Hygiene**:
   `.gitignore` and `.dockerignore` prevent `.env`, `.db`, credentials, and keys from being baked into images or committed to version control.
