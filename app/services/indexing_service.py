"""Indexing pipeline: parse → chunk → SQLite → embed → LanceDB.

Public API
----------
    process_files(file_paths: list[Path]) -> None

Processing is parallelised at the chunking stage (CPU/IO bound per file).
Embedding and storage run sequentially in document-aware batches.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pyarrow as pa

from app.chunker import get_blocks
from app.chunker.semantic import Chunk, build_chunks
from app.config import settings
from app.database import SessionLocal, lance_db
from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document

logger = logging.getLogger(__name__)

VECTOR_TABLE = "chunk_vectors"

# ---------------------------------------------------------------------------
# Lazy singletons — loaded on first use to avoid importing heavy dependencies
# at module import time.
# ---------------------------------------------------------------------------

_tokenizer = None
_embedding_model = None


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer
        logger.info("Loading tokenizer: %s", settings.embedding_model)
        _tokenizer = AutoTokenizer.from_pretrained(
            settings.embedding_model, local_files_only=True
        )
    return _tokenizer


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _embedding_model = SentenceTransformer(
            settings.embedding_model, local_files_only=True
        )
    return _embedding_model


def preload_models() -> None:
    """Eagerly load all indexing-time models once at app startup."""
    _get_tokenizer()
    _get_embedding_model()

    # Chunking relies on spaCy sentence segmentation for paragraph splitting.
    from app.chunker.semantic import preload_nlp
    preload_nlp()


# ---------------------------------------------------------------------------
# LanceDB table
# ---------------------------------------------------------------------------

def _get_or_create_vector_table(dim: int):
    if VECTOR_TABLE in lance_db.table_names():
        return lance_db.open_table(VECTOR_TABLE)
    schema = pa.schema([
        pa.field("chunk_id", pa.int64()),
        pa.field("document_id", pa.int64()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])
    return lance_db.create_table(VECTOR_TABLE, schema=schema)


# ---------------------------------------------------------------------------
# Per-file processing (runs inside thread pool)
# ---------------------------------------------------------------------------

def _process_file(path: Path) -> tuple[dict, list[Chunk]]:
    """Parse and chunk a single file. No DB interaction."""
    blocks = get_blocks(path)
    tokenizer = _get_tokenizer()
    chunks = build_chunks(
        blocks,
        max_tokens=settings.chunk_tokens,
        overlap_tokens=settings.overlap_tokens,
        tokenizer=tokenizer,
    )
    doc_data = {
        "document_path": str(path.resolve()),
        "name": path.name,
    }
    return doc_data, chunks


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------

def _make_doc_batches(
    results: list[tuple[dict, list[Chunk]]],
    batch_size: int,
) -> list[list[tuple[dict, list[Chunk]]]]:
    """
    Pack documents into batches where total chunk count ≤ batch_size.
    A document's chunks are never split across batches.
    A document with more chunks than batch_size occupies its own batch.
    """
    batches: list[list] = []
    current: list = []
    current_count = 0

    for doc_data, chunks in results:
        n = len(chunks)
        if current and current_count + n > batch_size:
            batches.append(current)
            current = []
            current_count = 0
        current.append((doc_data, chunks))
        current_count += n

    if current:
        batches.append(current)

    return batches


# ---------------------------------------------------------------------------
# SQLite storage
# ---------------------------------------------------------------------------

def _store_sqlite_batch(
    batch: list[tuple[dict, list[Chunk]]],
) -> tuple[list[tuple[int, int, str]], list[int]]:
    """
    Persist one batch of documents + chunks to SQLite.

    Returns:
        records  — ``(chunk_id, document_id, embedding_input)`` for LanceDB.
        refreshed_doc_ids — document IDs whose old chunks were replaced, so
                            the caller can purge stale LanceDB vectors.
    """
    records: list[tuple[int, int, str]] = []
    refreshed_doc_ids: list[int] = []

    db = SessionLocal()
    try:
        for doc_data, chunks in batch:
            existing = (
                db.query(Document)
                .filter(Document.document_path == doc_data["document_path"])
                .first()
            )
            if existing:
                # Delete stale chunks; cascade handles ChunkModel rows.
                db.query(ChunkModel).filter(
                    ChunkModel.document_id == existing.id
                ).delete(synchronize_session=False)
                doc_db = existing
                refreshed_doc_ids.append(doc_db.id)
            else:
                doc_db = Document(**doc_data)
                db.add(doc_db)
                db.flush()  # populate doc_db.id

            for chunk in chunks:
                chunk_db = ChunkModel(
                    document_id=doc_db.id,
                    position=chunk.position,
                    breadcrumbs=json.dumps(chunk.breadcrumbs, ensure_ascii=False),
                    token_count=chunk.token_count,
                    embedding_model=settings.embedding_model,
                    raw_text=chunk.text,
                )
                db.add(chunk_db)
                db.flush()  # populate chunk_db.id
                records.append((chunk_db.id, doc_db.id, chunk.embedding_input))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return records, refreshed_doc_ids


# ---------------------------------------------------------------------------
# LanceDB storage
# ---------------------------------------------------------------------------

def _store_lancedb_batch(
    table,
    batch_records: list[tuple[int, int, str]],
    model,
) -> None:
    """Embed a batch of texts and write vectors to the LanceDB table."""
    texts = [r[2] for r in batch_records]
    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    rows = [
        {
            "chunk_id": r[0],
            "document_id": r[1],
            "vector": vec.tolist(),
        }
        for r, vec in zip(batch_records, vectors)
    ]
    table.add(rows)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_files(file_paths: list[Path]) -> None:
    """
    Index a list of files end-to-end:

    1. Parse + chunk all files in parallel (``settings.max_workers`` threads).
    2. Store documents and chunks in SQLite in document-aware batches of
       ``settings.batch_size`` chunks.
    3. Generate embeddings and write vectors to LanceDB in batches of
       ``settings.batch_size``.
    """
    if not file_paths:
        logger.warning("process_files called with empty file list — nothing to do.")
        return

    logger.info(
        "Indexing %d file(s) with %d worker(s).",
        len(file_paths), settings.max_workers,
    )

    # ------------------------------------------------------------------
    # Step 1: Parse + chunk in parallel
    # ------------------------------------------------------------------
    results: list[tuple[dict, list[Chunk]]] = []

    with ThreadPoolExecutor(max_workers=settings.max_workers) as executor:
        futures = {executor.submit(_process_file, Path(p)): p for p in file_paths}
        for future in as_completed(futures):
            path = futures[future]
            try:
                doc_data, chunks = future.result()
                results.append((doc_data, chunks))
                logger.info("  ✓ %s → %d chunk(s)", path, len(chunks))
            except Exception:
                logger.exception("  ✗ Failed to process %s", path)

    if not results:
        logger.warning("No files were processed successfully.")
        return

    # ------------------------------------------------------------------
    # Step 2: SQLite — document-aware batches
    # ------------------------------------------------------------------
    doc_batches = _make_doc_batches(results, settings.batch_size)
    logger.info("Storing in %d SQLite batch(es).", len(doc_batches))

    all_vector_records: list[tuple[int, int, str]] = []
    all_refreshed_ids: list[int] = []

    for i, batch in enumerate(doc_batches, 1):
        chunk_count = sum(len(c) for _, c in batch)
        logger.info(
            "  SQLite batch %d/%d: %d document(s), %d chunk(s).",
            i, len(doc_batches), len(batch), chunk_count,
        )
        records, refreshed_ids = _store_sqlite_batch(batch)
        all_vector_records.extend(records)
        all_refreshed_ids.extend(refreshed_ids)

    # ------------------------------------------------------------------
    # Step 3: LanceDB — flat batches of batch_size vectors
    # ------------------------------------------------------------------
    logger.info(
        "Generating embeddings for %d chunk(s).", len(all_vector_records)
    )
    model = _get_embedding_model()
    # get_embedding_dimension() is the current API;
    # fall back to the legacy name for older sentence-transformers versions.
    dim: int = (
        model.get_embedding_dimension()
        if hasattr(model, "get_embedding_dimension")
        else model.get_sentence_embedding_dimension()
    )
    table = _get_or_create_vector_table(dim)

    # Purge stale vectors for re-indexed documents before adding fresh ones.
    if all_refreshed_ids:
        id_list = ", ".join(str(d) for d in all_refreshed_ids)
        table.delete(f"document_id IN ({id_list})")
        logger.info(
            "  Purged stale vectors for %d re-indexed document(s).",
            len(all_refreshed_ids),
        )

    batch_size = settings.batch_size
    total_batches = (len(all_vector_records) + batch_size - 1) // batch_size

    for i, start in enumerate(range(0, len(all_vector_records), batch_size), 1):
        batch_records = all_vector_records[start : start + batch_size]
        logger.info(
            "  LanceDB batch %d/%d: %d vector(s).",
            i, total_batches, len(batch_records),
        )
        _store_lancedb_batch(table, batch_records, model)

    logger.info("Indexing complete. %d chunk(s) indexed.", len(all_vector_records))
