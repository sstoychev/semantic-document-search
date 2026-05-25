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

    # Chunking
    chunk_tokens: int = _cfg.getint("chunking", "chunk_tokens", fallback=500)
    overlap_tokens: int = _cfg.getint("chunking", "overlap_tokens", fallback=100)
    max_workers: int = _cfg.getint("chunking", "max_workers", fallback=5)
    batch_size: int = _cfg.getint("chunking", "batch_size", fallback=100)

    # Embedding
    embedding_model: str = _cfg.get("embedding", "model", fallback="BAAI/bge-small-en-v1.5")

    # Auth
    secret_key: str = _cfg.get("auth", "secret_key", fallback="change-me-in-production")
    algorithm: str = _cfg.get("auth", "algorithm", fallback="HS256")
    access_token_expire_minutes: int = _cfg.getint("auth", "access_token_expire_minutes", fallback=30)
    admin_username: str = _cfg.get("auth", "admin_username", fallback="admin")
    admin_hashed_password: str = _cfg.get("auth", "admin_hashed_password", fallback="")
    admin_salt: str = _cfg.get("auth", "admin_salt", fallback="")


settings = Settings()
