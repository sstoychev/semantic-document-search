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
    is_indexed: bool

    model_config = {"from_attributes": True}


class SearchQuery(BaseModel):
    query: str
    limit: int = 10
    debug: bool = False


class UploadBatchResponse(BaseModel):
    files: list[DocumentResponse]
    indexed_now: bool
    pending_before: int
    pending_after: int
    threshold: int
    reindexed_count: int = 0


class SearchResult(BaseModel):
    chunk_id: int
    document_id: int
    document_name: str
    document_path: str = ""
    score: float
    snippet: str | None = None
    breadcrumbs: list[str] = []
