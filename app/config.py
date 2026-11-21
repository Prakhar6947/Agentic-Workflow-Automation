import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
RAW_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/workflow_engine.db")

# Normalize PostgreSQL scheme for SQLAlchemy 2.0+
if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif RAW_DATABASE_URL.startswith("postgresql://") and not RAW_DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

# Application server settings
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# LLM provider settings
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Notification settings
DEFAULT_OPS_EMAIL = os.getenv("DEFAULT_OPS_EMAIL", "ops-team@company.com")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "automation@company.com"))

# Telemetry data paths
_alerts_env = os.getenv("ALERTS_JSON_PATH", "")
if _alerts_env and Path(_alerts_env).exists():
    ALERTS_PATH = Path(_alerts_env)
elif (BASE_DIR / "data" / "alerts.json").exists():
    ALERTS_PATH = BASE_DIR / "data" / "alerts.json"
elif (BASE_DIR / "alerts.json").exists():
    ALERTS_PATH = BASE_DIR / "alerts.json"
else:
    ALERTS_PATH = Path("alerts.json")

_perf_env = os.getenv("PERFORMANCE_JSON_PATH", "")
if _perf_env and Path(_perf_env).exists():
    PERF_PATH = Path(_perf_env)
elif (BASE_DIR / "data" / "performance_stats.json").exists():
    PERF_PATH = BASE_DIR / "data" / "performance_stats.json"
elif (BASE_DIR / "performance_stats.json").exists():
    PERF_PATH = BASE_DIR / "performance_stats.json"
else:
    PERF_PATH = Path("performance_stats.json")
