from sqlalchemy.orm import Session

from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentUpdate, SearchQuery, SearchResult


class DocumentService:
    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, db: Session, payload: DocumentCreate) -> Document:
        """
        Persist a new document record to SQLite.
        Use indexing_service.process_files() to also chunk and embed.
        """
        db_doc = Document(**payload.model_dump())
        db.add(db_doc)
        db.commit()
        db.refresh(db_doc)
        return db_doc

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
        """
        Remove a document and its chunks from SQLite.
        TODO: delete the corresponding vectors from LanceDB.
        """
        db_doc = self.get(db, document_id)
        if db_doc is None:
            return False
        db.delete(db_doc)
        db.commit()
        return True

    def search(self, db: Session, query: SearchQuery) -> list[SearchResult]:
        """
        Semantic search over indexed chunks.
        TODO: embed query, query LanceDB for nearest vectors, return ranked results.
        """
        return []


document_service = DocumentService()

        db_doc = self.get(db, document_id)
        if db_doc is None:
            return False
        db.delete(db_doc)
        db.commit()
        return True

    # ------------------------------------------------------------------
    # Semantic search
    # ------------------------------------------------------------------

    def search(self, db: Session, query: SearchQuery) -> list[SearchResult]:
        """
        Embed the query and run a vector search in LanceDB.
        TODO: replace with real embedding + LanceDB query.
        """
        _ = db  # will be used once LanceDB integration is wired up
        return []


document_service = DocumentService()
