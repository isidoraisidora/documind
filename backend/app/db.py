import time
import psycopg
from pgvector.psycopg import register_vector
from .config import DATABASE_URL


def init_db(retries: int = 30):
    """Create the extension and table. Retries because the DB may still be starting."""
    for _ in range(retries):
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chunks (
                        id SERIAL PRIMARY KEY,
                        filename TEXT NOT NULL,
                        page INT,
                        content TEXT NOT NULL,
                        embedding vector(384)
                    )
                """)
            return
        except psycopg.OperationalError:
            time.sleep(2)
    raise RuntimeError("Database not reachable")


def get_conn():
    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    register_vector(conn)
    return conn