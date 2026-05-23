from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.document import DocumentCreate, DocumentResponse, SearchQuery, SearchResult
from app.services.document_service import document_service

router = APIRouter()


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def add_document(payload: DocumentCreate, db: Session = Depends(get_db)):
    """Store a new text document and index it for semantic search."""
    return document_service.create(db, payload)


@router.post("/search", response_model=list[SearchResult])
def search_documents(query: SearchQuery, db: Session = Depends(get_db)):
    """Perform semantic search across stored documents."""
    return document_service.search(db, query)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = document_service.get(db, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    deleted = document_service.delete(db, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
