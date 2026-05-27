from pathlib import Path

from sqlalchemy.orm import Session

from app.database import lance_db
from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentUpdate, SearchQuery, SearchResult
from app.services.indexing_service import process_files

VECTOR_TABLE = "chunk_vectors"


class DocumentService:
    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, db: Session, payload: DocumentCreate) -> Document:
        """
        Index a document path end-to-end and return the persisted document row.
        """
        file_path = Path(payload.document_path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Document path does not exist or is not a file: {file_path}")

        process_files([file_path])

        db_doc = (
            db.query(Document)
            .filter(Document.document_path == str(file_path))
            .first()
        )
        if db_doc is None:
            raise RuntimeError("Document indexing completed but no SQLite document row was found")

        # Preserve user-provided display name after indexing (which defaults to file name).
        if payload.name and db_doc.name != payload.name:
            db_doc.name = payload.name
            db.commit()
            db.refresh(db_doc)

        return db_doc

    def create_from_path(self, db: Session, file_path: Path, name: str | None = None) -> Document:
        """Internal helper for indexing a server-side file path."""
        payload = DocumentCreate(document_path=str(file_path), name=name or file_path.name)
        return self.create(db, payload)

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
