import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TOP_K = int(os.environ.get("TOP_K", "4"))