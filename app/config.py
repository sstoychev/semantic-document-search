import configparser
from pathlib import Path

_CONFIG_FILE = Path("config.ini")

if not _CONFIG_FILE.exists():
    raise FileNotFoundError(
        f"{_CONFIG_FILE} not found. Run ./setup_venv.sh to initialise the project."
    )

_cfg = configparser.ConfigParser()
_cfg.read(_CONFIG_FILE)


class Settings:
    # Database
    sqlite_url: str = _cfg.get("database", "sqlite_url", fallback="sqlite:///./data/app.db")
    lancedb_uri: str = _cfg.get("database", "lancedb_uri", fallback="./data/lancedb")

    # Data directories
    datasets_dir: str = _cfg.get("data", "datasets_dir", fallback="data/datasets")

    # Chunking
    chunk_tokens: int = _cfg.getint("chunking", "chunk_tokens", fallback=500)
    overlap_tokens: int = _cfg.getint("chunking", "overlap_tokens", fallback=100)
    max_workers: int = _cfg.getint("chunking", "max_workers", fallback=5)
    batch_size: int = _cfg.getint("chunking", "batch_size", fallback=100)

    # Indexing / reindexing
    pending_reindex_threshold: int = _cfg.getint("indexing", "pending_reindex_threshold", fallback=10)

    # Embedding
    embedding_model: str = _cfg.get("embedding", "model", fallback="BAAI/bge-small-en-v1.5")
    rerank_model: str = _cfg.get("embedding", "rerank_model", fallback="cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Auth
    algorithm: str = _cfg.get("auth", "algorithm", fallback="HS256")
    access_token_expire_minutes: int = _cfg.getint("auth", "access_token_expire_minutes", fallback=60)
    # Admin user is always "document-admin"; password stored here as plain text
    admin_password: str = _cfg.get("auth", "admin_password", fallback="change-me-in-production")
    admin_jwt_salt: str = _cfg.get("auth", "admin_jwt_salt", fallback="change-me-admin-jwt-salt")


settings = Settings()
