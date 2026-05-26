"""Hybrid search: vector (cosine) + FTS5 (BM25) → RRF → cross-encoder rerank.

Public API
----------
    search(query, top_k=20, retrieval_k=200) -> list[dict]
"""
from __future__ import annotations

import json
import logging
import re

from sqlalchemy import bindparam, text

from app.config import settings
from app.database import SessionLocal, lance_db

logger = logging.getLogger(__name__)

VECTOR_TABLE = "chunk_vectors"
_RRF_K = 60        # standard RRF constant (higher → less aggressive rank fusion)
_RERANK_POOL = 50  # top-N from RRF fed into the cross-encoder

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_embed_model = None
_cross_encoder = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _embed_model = SentenceTransformer(
            settings.embedding_model, local_files_only=True
        )
    return _embed_model


def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading cross-encoder: %s", settings.rerank_model)
        _cross_encoder = CrossEncoder(
            settings.rerank_model, local_files_only=True
        )
    return _cross_encoder


# ---------------------------------------------------------------------------
# FTS5 query sanitisation
# ---------------------------------------------------------------------------

_FTS_SPECIAL = re.compile(r'["\^\*\(\)\:\-\+]')


def _fts_query(raw: str) -> str:
    """Convert a raw user query to a safe FTS5 MATCH expression.

    Each token is wrapped in double-quotes so it is treated as a literal
    phrase, avoiding FTS5 syntax errors on special characters.
    """
    cleaned = _FTS_SPECIAL.sub(" ", raw).strip()
    if not cleaned:
        return '""'
    return " ".join(f'"{tok}"' for tok in cleaned.split())


# ---------------------------------------------------------------------------
# Individual retrievers
# ---------------------------------------------------------------------------

def _vector_search(query_vector: list[float], k: int) -> list[dict]:
    """Return up to *k* results from LanceDB cosine similarity search."""
    table = lance_db.open_table(VECTOR_TABLE)
    return (
        table.search(query_vector)
        .metric("cosine")
        .limit(k)
        .select(["chunk_id", "document_id"])
        .to_list()
    )


def _fts_search(query: str, k: int) -> list[tuple[int, float]]:
    """Return up to *k* (chunk_id, bm25_score) pairs from SQLite FTS5.

    ``bm25()`` returns negative values; more negative = better match.
    Ordering ascending (ORDER BY score) returns best matches first.
    """
    q = _fts_query(query)
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT rowid, bm25(chunks_fts) AS score "
                "FROM chunks_fts "
                "WHERE chunks_fts MATCH :q "
                "ORDER BY score "
                "LIMIT :k"
            ),
            {"q": q, "k": k},
        ).fetchall()
    except Exception:
        logger.warning("FTS search failed for query %r — returning no FTS hits.", query, exc_info=True)
        rows = []
    finally:
        db.close()
    return [(int(row[0]), float(row[1])) for row in rows]


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def _rrf(
    vector_hits: list[dict],
    fts_hits: list[tuple[int, float]],
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion of two ranked lists.

    Returns (chunk_id, rrf_score) sorted descending (highest score first).
    """
    scores: dict[int, float] = {}

    for rank, hit in enumerate(vector_hits, 1):
        cid = int(hit["chunk_id"])
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank)

    for rank, (cid, _) in enumerate(fts_hits, 1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# Metadata fetch
# ---------------------------------------------------------------------------

def _fetch_chunks(chunk_ids: list[int]) -> dict[int, dict]:
    """Fetch chunk text + document metadata for a list of chunk IDs."""
    if not chunk_ids:
        return {}
    db = SessionLocal()
    try:
        stmt = (
            text(
                "SELECT c.id, c.raw_text, c.breadcrumbs, c.document_id, "
                "       d.name, d.document_path "
                "FROM chunks c "
                "JOIN documents d ON c.document_id = d.id "
                "WHERE c.id IN :ids"
            )
            .bindparams(bindparam("ids", expanding=True))
        )
        rows = db.execute(stmt, {"ids": chunk_ids}).fetchall()
    finally:
        db.close()

    return {
        row[0]: {
            "chunk_id": row[0],
            "raw_text": row[1],
            "breadcrumbs": json.loads(row[2]),
            "document_id": row[3],
            "document_name": row[4],
            "document_path": row[5],
        }
        for row in rows
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def search(query: str, top_k: int = 20, retrieval_k: int = 200) -> list[dict]:
    """Hybrid search pipeline.

    Steps
    -----
    1. Embed *query* with the bi-encoder.
    2. Vector search → top *retrieval_k* chunks by cosine similarity.
    3. FTS5 BM25 search → top *retrieval_k* chunks.
    4. RRF fusion of both ranked lists.
    5. Cross-encoder reranks the top-``_RERANK_POOL`` RRF candidates.
    6. Return top *top_k* results with metadata.

    Returns
    -------
    List of dicts with keys:
        chunk_id, document_id, document_name, document_path,
        score (cross-encoder), snippet (raw_text), breadcrumbs.
    """
    if not query.strip():
        return []

    # 1. Embed
    embed = _get_embed_model()
    query_vec = embed.encode(
        query, normalize_embeddings=True, show_progress_bar=False
    ).tolist()

    # 2. & 3. Retrieve
    vector_hits = _vector_search(query_vec, retrieval_k)
    fts_hits = _fts_search(query, retrieval_k)
    logger.debug(
        "query=%r  vector_hits=%d  fts_hits=%d",
        query, len(vector_hits), len(fts_hits),
    )

    # 4. RRF
    rrf_ranked = _rrf(vector_hits, fts_hits)
    pool_ids = [cid for cid, _ in rrf_ranked[:_RERANK_POOL]]

    if not pool_ids:
        return []

    # Fetch metadata for the rerank pool
    meta = _fetch_chunks(pool_ids)
    present_ids = [cid for cid in pool_ids if cid in meta]

    # 5. Cross-encoder rerank
    encoder = _get_cross_encoder()
    pairs = [(query, meta[cid]["raw_text"]) for cid in present_ids]
    ce_scores = encoder.predict(pairs, show_progress_bar=False)

    reranked = sorted(
        zip(present_ids, ce_scores),
        key=lambda x: float(x[1]),
        reverse=True,
    )

    # 6. Build results
    results = []
    for cid, score in reranked[:top_k]:
        m = meta[cid]
        results.append({
            "chunk_id": m["chunk_id"],
            "document_id": m["document_id"],
            "document_name": m["document_name"],
            "document_path": m["document_path"],
            "score": float(score),
            "snippet": m["raw_text"],
            "breadcrumbs": m["breadcrumbs"],
        })

    return results
