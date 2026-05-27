"""Download 10 k documents from BeIR/msmarco and index them.

Download behaviour
------------------
Documents are saved as individual .txt files under
``<datasets_dir>/msmarco/`` (configured via the ``[data] datasets_dir``
key in config.ini, defaulting to ``data/datasets``).
If that directory already contains >= LIMIT files the download step is
skipped entirely and the existing files are used directly — no network call
is made on subsequent runs.

Indexing
--------
Files are fed to ``indexing_service.process_files()`` in batches of
BATCH_SIZE.  After every batch the script prints the batch number, cumulative
progress, per-batch elapsed time, and total elapsed time.

The heavy INFO logging from indexing_service is suppressed so the progress
output is readable; only WARNING+ messages from it are shown.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Silence the per-file INFO chatter from the indexing pipeline so our own
# progress lines are readable.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logging.getLogger("app.services.indexing_service").setLevel(logging.WARNING)

# Import after sys.path is set so app.config can find config.ini.
from app.config import settings  # noqa: E402

DOCS_DIR = (Path(settings.datasets_dir) if Path(settings.datasets_dir).is_absolute()
            else ROOT / settings.datasets_dir) / "msmarco"
LIMIT = 10_000
BATCH_SIZE = 30


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _write_docs(limit: int) -> list[Path]:
    """Stream the corpus from HuggingFace and write one .txt per document."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading BeIR/msmarco corpus (first {limit:,} documents) …")

    from datasets import load_dataset  # type: ignore[import-untyped]

    ds = load_dataset(
        "BeIR/msmarco",
        "corpus",
        split="corpus",
        streaming=True,
        trust_remote_code=False,
    )

    written = 0
    t0 = time.perf_counter()

    for row in ds:
        if written >= limit:
            break

        doc_id = str(row["_id"]).strip()
        title  = (row.get("title") or "").strip()
        text   = (row.get("text")  or "").strip()

        # Use a markdown heading for the title so the txt parser promotes it
        # to a HEADING block; fall back to plain text when title is absent.
        content = f"# {title}\n\n{text}" if title else text

        (DOCS_DIR / f"{doc_id}.txt").write_text(content, encoding="utf-8")

        written += 1
        if written % 1_000 == 0:
            elapsed = time.perf_counter() - t0
            print(f"  {written:>{len(str(limit))}}/{limit:,} written  ({elapsed:.1f}s elapsed)")

    elapsed = time.perf_counter() - t0
    print(f"  Done — {written:,} documents saved to {DOCS_DIR}  ({elapsed:.1f}s)")
    return sorted(DOCS_DIR.glob("*.txt"))[:limit]


def _get_docs() -> list[Path]:
    """Return LIMIT .txt paths, downloading if necessary."""
    existing: list[Path] = sorted(DOCS_DIR.glob("*.txt")) if DOCS_DIR.exists() else []

    if len(existing) >= LIMIT:
        print(f"Found {len(existing):,} existing documents in {DOCS_DIR} — skipping download.")
        return existing[:LIMIT]

    if existing:
        print(
            f"Found only {len(existing):,} documents in {DOCS_DIR} "
            f"(need {LIMIT:,}) — re-downloading …"
        )

    return _write_docs(LIMIT)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    docs = _get_docs()
    total        = len(docs)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    batch_w       = len(str(total_batches))   # width for zero-padding

    print(f"\nIndexing {total:,} documents in {total_batches} batches of {BATCH_SIZE} …\n")

    # Import after sys.path is set and logging is configured.
    from app.services.indexing_service import process_files  # noqa: PLC0415

    t_start  = time.perf_counter()
    indexed  = 0

    for batch_num, start in enumerate(range(0, total, BATCH_SIZE), 1):
        batch = docs[start : start + BATCH_SIZE]

        t_batch = time.perf_counter()
        process_files(batch)
        t_now   = time.perf_counter()

        indexed       += len(batch)
        pct            = indexed / total * 100
        batch_elapsed  = t_now - t_batch
        total_elapsed  = t_now - t_start

        print(
            f"  Batch {batch_num:>{batch_w}}/{total_batches}"
            f"  [{indexed:>{len(str(total))}}/{total}  {pct:5.1f}%]"
            f"  batch {batch_elapsed:5.1f}s"
            f"  total {total_elapsed:6.1f}s"
        )

    print("\nFinalizing ANN index ...")
    from app.database import ensure_lance_index  # noqa: PLC0415
    ensure_lance_index()

    print(f"\nDone. {indexed:,} documents indexed in {time.perf_counter() - t_start:.1f}s")


if __name__ == "__main__":
    main()
