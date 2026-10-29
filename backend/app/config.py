import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5433/postgres"
)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TOP_K = int(os.environ.get("TOP_K", "4"))
LLM_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-20b")