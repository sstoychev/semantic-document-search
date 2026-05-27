from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import lance_db
from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentUpdate, SearchQuery, SearchResult
from app.services.indexing_service import process_files
from app.config import settings

VECTOR_TABLE = "chunk_vectors"


class DocumentService:
    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, db: Session, payload: DocumentCreate) -> Document:
        """Create or replace a pending document record for a server-side file path."""
        file_path = Path(payload.document_path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Document path does not exist or is not a file: {file_path}")

        existing = self.get_by_path(db, str(file_path))
        if existing is not None:
            if existing.is_indexed:
                db.query(ChunkModel).filter(ChunkModel.document_id == existing.id).delete(synchronize_session=False)
                if VECTOR_TABLE in lance_db.table_names():
                    lance_db.open_table(VECTOR_TABLE).delete(f"document_id = {existing.id}")
            db.delete(existing)
            db.flush()

        db_doc = Document(document_path=str(file_path), name=payload.name or file_path.name, is_indexed=False)
        db.add(db_doc)
        db.commit()
        db.refresh(db_doc)
        return db_doc

    def create_from_path(self, db: Session, file_path: Path, name: str | None = None) -> Document:
        """Internal helper for indexing a server-side file path."""
        payload = DocumentCreate(document_path=str(file_path), name=name or file_path.name)
        return self.create(db, payload)

    def get_by_path(self, db: Session, document_path: str) -> Document | None:
        return db.query(Document).filter(Document.document_path == document_path).first()

    def pending_documents(self, db: Session) -> list[Document]:
        return (
            db.query(Document)
            .filter(Document.is_indexed.is_(False))
            .order_by(Document.id.asc())
            .all()
        )

    def pending_documents_count(self, db: Session) -> int:
        return db.query(func.count(Document.id)).filter(Document.is_indexed.is_(False)).scalar() or 0

    def reindex_pending_documents_if_needed(self, db: Session) -> dict[str, int | bool]:
        pending = self.pending_documents(db)
        pending_before = len(pending)
        threshold = settings.pending_reindex_threshold
        if pending_before < threshold:
            return {
                "indexed_now": False,
                "pending_before": pending_before,
                "pending_after": pending_before,
                "threshold": threshold,
                "reindexed_count": 0,
            }

        process_files([Path(doc.document_path) for doc in pending])
        pending_after = self.pending_documents_count(db)
        return {
            "indexed_now": True,
            "pending_before": pending_before,
            "pending_after": pending_after,
            "threshold": threshold,
            "reindexed_count": pending_before,
        }

    def get(self, db: Session, document_id: int) -> Document | None:
        """Retrieve a single document by primary key."""
        return db.query(Document).filter(Document.id == document_id).first()

    def get_many(self, db: Session, skip: int = 0, limit: int = 100) -> list[Document]:
        """Return a paginated list of documents."""
        return db.query(Document).offset(skip).limit(limit).all()

    def update(self, db: Session, document_id: int, payload: DocumentUpdate) -> Document | None:
        """Update document fields in SQLite."""
        db_doc = self.get(db, document_id)
        if db_doc is None:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(db_doc, field, value)
        db.commit()
        db.refresh(db_doc)
        return db_doc

    def delete(self, db: Session, document_id: int) -> bool:
        """Remove document/chunks from SQLite and vectors from LanceDB."""
        db_doc = self.get(db, document_id)
        if db_doc is None:
            return False

        if VECTOR_TABLE in lance_db.table_names():
            table = lance_db.open_table(VECTOR_TABLE)
            table.delete(f"document_id = {db_doc.id}")

        db.delete(db_doc)
        db.commit()
        return True

    def search(self, db: Session, query: SearchQuery) -> tuple[list[SearchResult], dict[str, float] | None]:
        """Hybrid search: vector + FTS + RRF + cross-encoder reranking."""
        from app.services import search_service
        payload = search_service.search(query.query, top_k=query.limit, debug=query.debug)

        debug_timings: dict[str, float] | None = None
        if query.debug:
            wrapped = payload if isinstance(payload, dict) else {"results": payload, "timings_ms": {}}
            hits = wrapped.get("results", [])
            debug_timings = wrapped.get("timings_ms", None)
        else:
            hits = payload if isinstance(payload, list) else payload.get("results", [])

        results = [
            SearchResult(
                chunk_id=h["chunk_id"],
                document_id=h["document_id"],
                document_name=h["document_name"],
                document_path=h["document_path"],
                score=h["score"],
                snippet=h["snippet"],
                breadcrumbs=h["breadcrumbs"],
            )
            for h in hits
        ]
        return results, debug_timings


document_service = DocumentService()
