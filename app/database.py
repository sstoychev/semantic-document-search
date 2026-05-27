import logging
import os

import lancedb
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
os.makedirs("data", exist_ok=True)

engine = create_engine(
    settings.sqlite_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency that yields a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_fts_index() -> None:
    """Create SQLite FTS5 virtual table + triggers if not already present.

    Uses a content table so ``chunks_fts`` always mirrors ``chunks.raw_text``.
    If the FTS table is newly created, an immediate rebuild populates it from
    all existing rows in ``chunks``.
    """
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'")
        ).fetchone()

        if exists:
            logger.info("SQLite FTS5 index already present.")
            return

        logger.info("Creating SQLite FTS5 index on chunks.raw_text ...")
        conn.execute(text(
            "CREATE VIRTUAL TABLE chunks_fts USING fts5("
            "    raw_text,"
            "    content='chunks',"
            "    content_rowid='id'"
            ")"
        ))
        conn.execute(text(
            "CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN"
            "    INSERT INTO chunks_fts(rowid, raw_text) VALUES (new.id, new.raw_text);"
            " END"
        ))
        conn.execute(text(
            "CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN"
            "    INSERT INTO chunks_fts(chunks_fts, rowid, raw_text)"
            "    VALUES ('delete', old.id, old.raw_text);"
            " END"
        ))
        conn.execute(text(
            "CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN"
            "    INSERT INTO chunks_fts(chunks_fts, rowid, raw_text)"
            "    VALUES ('delete', old.id, old.raw_text);"
            "    INSERT INTO chunks_fts(rowid, raw_text) VALUES (new.id, new.raw_text);"
            " END"
        ))
        # Populate from existing rows
        conn.execute(text("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')"))
        conn.commit()
        logger.info("SQLite FTS5 index created and populated.")


# ---------------------------------------------------------------------------
# LanceDB
# ---------------------------------------------------------------------------
lance_db = lancedb.connect(settings.lancedb_uri)

VECTOR_TABLE = "chunk_vectors"


def ensure_lance_index() -> None:
    """Create an IVF_HNSW_SQ ANN index on the vector column (or replace if config changes)."""
    if VECTOR_TABLE not in lance_db.table_names():
        logger.info("LanceDB vector table not found; skipping index creation.")
        return

    table = lance_db.open_table(VECTOR_TABLE)

    n_rows = table.count_rows()
    if n_rows < 256:
        logger.warning(
            "Only %d rows in vector table — need ≥256 for ANN indexing; skipping.", n_rows
        )
        return

    # Always attempt to create/recreate the index so index type changes are enforced.
    logger.info("Creating IVF_HNSW_SQ vector index on %d rows ...", n_rows)
    table.create_index(
        metric="cosine",
        num_partitions=256,
        index_type="IVF_HNSW_SQ",
        replace=True,  # Allow index type updates
    )
    logger.info("LanceDB vector index created.")


# ---------------------------------------------------------------------------
# Startup verification (check-only — never creates anything)
# ---------------------------------------------------------------------------

def verify_ready() -> None:
    """Check that all required database artifacts are in place.

    Raises ``RuntimeError`` with a clear message if anything is missing.
    Call this at application startup; never performs any writes.
    All setup must be done in advance via ``setup_venv.sh``.
    """
    from pathlib import Path

    errors: list[str] = []

    # SQLite: ORM tables + FTS5 table + triggers
    with engine.connect() as conn:
        for table_name in ("documents", "chunks", "chunks_fts"):
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                {"n": table_name},
            ).fetchone()
            if row is None:
                errors.append(f"SQLite table '{table_name}' is missing")

        document_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(documents)")).fetchall()
        }
        if "is_indexed" not in document_columns:
            errors.append("SQLite column 'documents.is_indexed' is missing")

        for trigger in ("chunks_ai", "chunks_ad", "chunks_au"):
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger' AND name=:n"),
                {"n": trigger},
            ).fetchone()
            if row is None:
                errors.append(f"SQLite trigger '{trigger}' is missing")

    # LanceDB: storage directory must exist
    if not Path(settings.lancedb_uri).exists():
        errors.append(f"LanceDB directory '{settings.lancedb_uri}' does not exist")

    if errors:
        bullet_list = "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(
            "Database setup is incomplete. Run ./setup_venv.sh to initialise.\n"
            f"Missing:\n{bullet_list}"
        )

    # Warn (don't fail) if data is loaded but the ANN index was never built
    if VECTOR_TABLE in lance_db.table_names():
        table = lance_db.open_table(VECTOR_TABLE)
        if table.count_rows() > 0 and not table.list_indices():
            logger.warning(
                "Vector table has %d rows but no ANN index — search will be slow. "
                "Run 'python scripts/init_db.py' to build it.",
                table.count_rows(),
            )
