from fastapi import FastAPI

from app.routers import documents, auth
from app.database import Base, engine

# Import all models so SQLAlchemy registers their tables before create_all.
import app.models.document  # noqa: F401
import app.models.chunk     # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Semantic Document Search",
    description="Store and semantically search text documents",
    version="0.1.0",
)

app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
