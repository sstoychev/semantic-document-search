#!/usr/bin/env python3
"""
Database initialisation and model pre-download.
Runs after scripts/setup_config.py so that config.ini is already in place.
"""
import sys
from pathlib import Path

# Put the project root on sys.path so `app` can be imported.
sys.path.insert(0, str(Path(__file__).parent.parent))


def init_sqlite() -> None:
    """Create all SQLite tables (idempotent — uses CREATE TABLE IF NOT EXISTS)."""
    # Import models first so SQLAlchemy registers them with Base.
    import app.models.document  # noqa: F401
    import app.models.chunk     # noqa: F401
    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)
    print("  SQLite tables ready.")


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
    init_lancedb()
    init_fts_index()
    init_vector_index()
    print("Done.\n")

    print("Downloading models ...")
    download_embedding_model()
    download_rerank_model()
    print("Done.")


if __name__ == "__main__":
    main()
