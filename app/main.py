import logging

from fastapi import FastAPI

from app.routers import documents, auth
from app.database import verify_ready

logging.basicConfig(level=logging.INFO)

# Verify all database artifacts are in place before serving any traffic.
# If anything is missing, the app will refuse to start with a clear error.
verify_ready()

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
