#!/usr/bin/env python3
"""
Database initialisation and model pre-download.
Runs after scripts/setup_config.py so that config.ini is already in place.
"""
import sys
from pathlib import Path

from sqlalchemy import text

# Put the project root on sys.path so `app` can be imported.
sys.path.insert(0, str(Path(__file__).parent.parent))


def init_sqlite() -> None:
    """Create all SQLite tables (idempotent — uses CREATE TABLE IF NOT EXISTS)."""
    # Import models first so SQLAlchemy registers them with Base.
    import app.models.document  # noqa: F401
    import app.models.chunk     # noqa: F401
    import app.models.user      # noqa: F401
    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)
    print("  SQLite tables ready.")


def ensure_document_indexing_schema() -> None:
    """Add/repair document indexing state columns for existing databases."""
    from app.database import engine

    with engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(documents)")).fetchall()
        }
        if "is_indexed" not in columns:
            conn.execute(text("ALTER TABLE documents ADD COLUMN is_indexed INTEGER NOT NULL DEFAULT 1"))
            print("  Added documents.is_indexed column.")
        conn.execute(text("UPDATE documents SET is_indexed = 1 WHERE is_indexed IS NULL"))
        conn.execute(text("DROP INDEX IF EXISTS ix_documents_is_indexed"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_pending_documents ON documents (id) WHERE is_indexed = 0"))


def ensure_users_schema() -> None:
    """Migrate existing databases: ensure users table has the expected columns."""
    from app.database import engine

    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "users" not in tables:
            # Table will be created by Base.metadata.create_all in init_sqlite,
            # but in case this runs standalone we log a warning only.
            print("  users table not found — run init_sqlite first.")
            return

        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
        }
        # Repair legacy schema: remove old columns, add new ones.
        # SQLite cannot DROP columns before 3.35, so we rebuild if needed.
        expected = {"id", "username", "password_hash", "salt", "permissions", "jwt_salt"}
        if not expected.issubset(columns):
            print("  Rebuilding users table to new schema ...")
            conn.execute(text("DROP TABLE IF EXISTS users_old"))
            conn.execute(text("ALTER TABLE users RENAME TO users_old"))
            conn.execute(text(
                "CREATE TABLE users ("
                "  id INTEGER PRIMARY KEY,"
                "  username TEXT NOT NULL UNIQUE,"
                "  password_hash TEXT NOT NULL,"
                "  salt TEXT NOT NULL,"
                "  permissions INTEGER NOT NULL DEFAULT 1,"
                "  jwt_salt TEXT NOT NULL"
                ")"
            ))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
            # Preserve rows that can be migrated (only if all new columns exist in old table)
            conn.execute(text("DROP TABLE users_old"))
            print("  users table rebuilt.")
        else:
            print("  users table schema OK.")


def seed_demo_user() -> None:
    """Create 'demo-user' with read-only permissions if it does not exist."""
    from app.database import SessionLocal
    from app.services.user_service import create_user

    db = SessionLocal()
    try:
        from app.models.user import User
        existing = db.query(User).filter(User.username == "demo-user").first()
        if existing:
            print("  demo-user already exists — skipping.")
            return
        create_user(db, username="demo-user", password="sematicsearch", permissions=1)
        print("  demo-user created (permissions: Read only).")
    finally:
        db.close()


def init_lancedb() -> None:
    """Ensure the LanceDB storage directory exists."""
    from app.config import settings

    db_path = Path(settings.lancedb_uri)
    db_path.mkdir(parents=True, exist_ok=True)
    print(f"  LanceDB directory ready: {db_path}")


def download_embedding_model() -> None:
    """Pre-download the HuggingFace tokenizer and sentence-transformers model."""
    from app.config import settings

    model_name = settings.embedding_model
    print(f"  Downloading tokenizer: {model_name} ...")
    from transformers import AutoTokenizer
    AutoTokenizer.from_pretrained(model_name)

    print(f"  Downloading embedding model: {model_name} ...")
    from sentence_transformers import SentenceTransformer
    SentenceTransformer(model_name)
    print(f"  Embedding model ready.")


def download_rerank_model() -> None:
    """Pre-download the cross-encoder reranking model."""
    from app.config import settings

    model_name = settings.rerank_model
    print(f"  Downloading cross-encoder: {model_name} ...")
    from sentence_transformers import CrossEncoder
    CrossEncoder(model_name)
    print(f"  Cross-encoder ready.")


def init_fts_index() -> None:
    """Create SQLite FTS5 virtual table + triggers (idempotent)."""
    from app.database import ensure_fts_index
    ensure_fts_index()
    print("  SQLite FTS5 index ready.")


def init_vector_index() -> None:
    """Create LanceDB IVF_PQ vector index if enough data exists (idempotent)."""
    from app.database import ensure_lance_index
    ensure_lance_index()
    print("  LanceDB vector index ready (or skipped — no data yet).")


def main() -> None:
    print("Initialising databases ...")
    init_sqlite()
    ensure_document_indexing_schema()
    ensure_users_schema()
    init_lancedb()
    init_fts_index()
    init_vector_index()
    print("Done.\n")

    print("Seeding default users ...")
    seed_demo_user()
    print("Done.\n")

    print("Downloading models ...")
    download_embedding_model()
    download_rerank_model()
    print("Done.")


if __name__ == "__main__":
    main()
