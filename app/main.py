import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from app.api.routes import router
from app.config import CORS_ORIGINS
from app.db.database import engine
from app.db.seed import init_db
from app.scheduler.service import scheduler_service

STATIC_DIR = Path(__file__).resolve().parent / "static"
APP_START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Seed predefined workflows and initialize background cron scheduler
    init_db()
    scheduler_service.start()
    yield
    # Shutdown: Stop scheduler gracefully
    scheduler_service.shutdown()


app = FastAPI(
    title="Agentic Workflow Automation Engine",
    description="Multi-agent workflow orchestrator using LangGraph, Plugin Registry, and APScheduler.",
    version="1.0.0",
    lifespan=lifespan,
)

# Production CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health & Observability Endpoints
@app.get("/health", tags=["Observability"])
@app.get("/api/health", tags=["Observability"])
def health_check():
    """
    Production health check probing database connectivity and scheduler status.
    Returns 200 when healthy, 503 if any core subsystem is degraded.
    """
    db_ok = True
    db_error = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    scheduler_ok = getattr(scheduler_service, "_started", False)
    is_healthy = db_ok and scheduler_ok

    payload = {
        "status": "healthy" if is_healthy else "degraded",
        "database": "connected" if db_ok else f"error: {db_error}",
        "scheduler": "running" if scheduler_ok else "stopped",
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
    }
    return JSONResponse(status_code=200 if is_healthy else 503, content=payload)


@app.get("/live", tags=["Observability"])
@app.get("/api/live", tags=["Observability"])
def liveness_probe():
    """Kubernetes liveness probe indicating the process is alive."""
    return {"status": "alive"}


@app.get("/ready", tags=["Observability"])
@app.get("/api/ready", tags=["Observability"])
def readiness_probe():
    """Kubernetes readiness probe verifying database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(exc)})


# Mount application routes at / and /api
app.include_router(router)
app.include_router(router, prefix="/api")


# Serve UI static index.html on root
@app.get("/", response_class=HTMLResponse, tags=["UI"])
def index_page():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "<h1>Agentic Workflow Automation Engine API</h1><p>Visit <a href='/docs'>/docs</a> for Swagger documentation.</p>"


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
