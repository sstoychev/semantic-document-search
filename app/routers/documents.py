from pathlib import Path
from html import escape
import time

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.chunker import get_blocks
from app.config import settings
from app.database import get_db
from app.schemas.document import (
    DocumentResponse,
    DocumentUpdate,
    SearchQuery,
    SearchResult,
    UploadBatchResponse,
)
from app.services.document_service import document_service

router = APIRouter()

_ALLOWED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf", ".html", ".htm"}
_MAX_UPLOAD_BYTES = 200 * 1024
_UPLOAD_DIR = Path("data/uploads")


@router.post("/upload", response_model=UploadBatchResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(response: Response, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Upload up to 10 files, validate type/size, persist them, and index once if needed."""
    total_start = time.perf_counter()

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files were uploaded")
    if len(files) > 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can upload at most 10 files at once")

    pending_before = document_service.pending_documents_count(db)
    threshold = int(settings.pending_reindex_threshold)

    t0 = time.perf_counter()
    validated_files: list[tuple[str, Path, bytes]] = []
    validate_ms_total = 0.0
    read_ms_total = 0.0
    save_ms_total = 0.0
    index_ms_total = 0.0
    reindex_ms = 0.0

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for file in files:
        validate_start = time.perf_counter()
        filename = (file.filename or "").strip()
        if not filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing file name")

        suffix = Path(filename).suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {suffix or '(none)'}. Allowed: {allowed}",
            )
        validate_ms_total += (time.perf_counter() - validate_start) * 1000.0

        read_start = time.perf_counter()
        content = await file.read()
        read_ms_total += (time.perf_counter() - read_start) * 1000.0

        size = len(content)
        if size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Uploaded file is empty: {filename}")
        if size > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large: {filename} is {size} bytes. Max allowed is {_MAX_UPLOAD_BYTES} bytes",
            )

        safe_name = Path(filename).name
        target = (_UPLOAD_DIR / safe_name).resolve()
        validated_files.append((safe_name, target, content))

    file_items: list[DocumentResponse] = []
    for safe_name, target, content in validated_files:
        save_start = time.perf_counter()
        target.write_bytes(content)
        save_ms_total += (time.perf_counter() - save_start) * 1000.0

        index_start = time.perf_counter()
        try:
            doc = document_service.create_from_path(db, target, name=safe_name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        index_ms_total += (time.perf_counter() - index_start) * 1000.0

        file_items.append(DocumentResponse.model_validate(doc))

    reindex_start = time.perf_counter()
    reindex_info = document_service.reindex_pending_documents_if_needed(db)
    reindex_ms = (time.perf_counter() - reindex_start) * 1000.0
    pending_after = int(reindex_info.get("pending_after", pending_before))
    indexed_now = bool(reindex_info.get("indexed_now"))
    reindexed_count = int(reindex_info.get("reindexed_count", 0))

    if indexed_now:
        for item in file_items:
            item.is_indexed = True

    total_ms = (time.perf_counter() - total_start) * 1000.0
    response.headers["X-Debug-Upload-Validate-Ms"] = f"{validate_ms_total:.3f}"
    response.headers["X-Debug-Upload-Read-Ms"] = f"{read_ms_total:.3f}"
    response.headers["X-Debug-Upload-Save-Ms"] = f"{save_ms_total:.3f}"
    response.headers["X-Debug-Upload-Index-Ms"] = f"{index_ms_total:.3f}"
    response.headers["X-Debug-Upload-Reindex-Ms"] = f"{reindex_ms:.3f}"
    response.headers["X-Debug-Upload-Total-Ms"] = f"{total_ms:.3f}"
    response.headers["X-Debug-Upload-Indexed-Now"] = str(indexed_now)
    response.headers["X-Debug-Upload-Pending-Before"] = str(pending_before)
    response.headers["X-Debug-Upload-Pending-After"] = str(pending_after)
    response.headers["X-Debug-Upload-Threshold"] = str(threshold)
    response.headers["X-Debug-Upload-Reindexed-Count"] = str(reindexed_count)

    return UploadBatchResponse(
        files=file_items,
        indexed_now=indexed_now,
        pending_before=pending_before,
        pending_after=pending_after,
        threshold=threshold,
        reindexed_count=reindexed_count,
    )


@router.get("/", response_model=list[DocumentResponse])
def list_documents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List indexed documents."""
    return document_service.get_many(db, skip=skip, limit=limit)


@router.post("/search", response_model=list[SearchResult])
def search_documents(query: SearchQuery, response: Response, db: Session = Depends(get_db)):
    """Perform semantic search across stored documents."""
    results, timings = document_service.search(db, query)
    if query.debug and timings:
        response.headers["X-Debug-Vector-Generation-Ms"] = str(timings.get("vector_generation", 0.0))
        response.headers["X-Debug-Lancedb-Search-Ms"] = str(timings.get("lancedb_search", 0.0))
        response.headers["X-Debug-Sqlite-Search-Ms"] = str(timings.get("sqlite_search", 0.0))
        response.headers["X-Debug-Rrf-Ms"] = str(timings.get("rrf", 0.0))
        response.headers["X-Debug-Fetch-Chunks-Ms"] = str(timings.get("fetch_chunks", 0.0))
        response.headers["X-Debug-Rerank-Ms"] = str(timings.get("rerank", 0.0))
        response.headers["X-Debug-Build-Results-Ms"] = str(timings.get("build_results", 0.0))
        response.headers["X-Debug-Total-Ms"] = str(timings.get("total", 0.0))
    return results


@router.get("/{document_id}/view", response_class=HTMLResponse)
def view_document(document_id: int, db: Session = Depends(get_db)):
        """Render one specific document in a dedicated page."""
        doc = document_service.get(db, document_id)
        if doc is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        path = Path(str(doc.document_path))
        if not path.exists() or not path.is_file():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found on server")

        try:
                blocks = get_blocks(path)
                full_text = "\n\n".join(b.text for b in blocks if b.text and b.text.strip())
        except Exception:
                full_text = path.read_text(encoding="utf-8", errors="replace")

        title = escape(str(doc.name))
        body = escape(full_text)
        project_root = Path.cwd().resolve()
        try:
            display_path = str(path.resolve().relative_to(project_root))
        except ValueError:
            display_path = path.name
        src = escape(display_path)
        return f"""
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{title}</title>
    <style>
        body {{ margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', sans-serif; background: #faf8f3; color: #221f19; }}
        .wrap {{ max-width: 980px; margin: 18px auto; padding: 0 14px 24px; }}
        h1 {{ margin: 0 0 6px; font-size: 1.4rem; }}
        .meta {{ color: #6b665b; margin-bottom: 12px; font-size: .92rem; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; background: #fff; border: 1px solid #e5dfd1; border-radius: 10px; padding: 12px; line-height: 1.4; }}
    </style>
</head>
<body>
    <div class=\"wrap\">
        <h1>{title}</h1>
        <div class=\"meta\">Source: {src}</div>
        <pre>{body}</pre>
    </div>
</body>
</html>
"""


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = document_service.get(db, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.put("/{document_id}", response_model=DocumentResponse)
def update_document(document_id: int, payload: DocumentUpdate, db: Session = Depends(get_db)):
    """Update editable document metadata."""
    doc = document_service.update(db, document_id, payload)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    deleted = document_service.delete(db, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
