from pydantic import BaseModel


class DocumentBase(BaseModel):
    document_path: str
    name: str


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    name: str | None = None


class DocumentResponse(DocumentBase):
    id: int

    model_config = {"from_attributes": True}


class SearchQuery(BaseModel):
    query: str
    limit: int = 10


class SearchResult(BaseModel):
    chunk_id: int
    document_id: int
    document_name: str
    score: float
    snippet: str | None = None
    breadcrumbs: list[str] = []
