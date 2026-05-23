#!/usr/bin/env python3
"""
Database initialisation helper.
Checks whether SQLite and LanceDB stores exist and creates them if not.
Run after scripts/setup_config.py so that config.ini is already in place.
"""
import configparser
from pathlib import Path

CONFIG_FILE = Path("config.ini")


def _read_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    return cfg


def init_sqlite(sqlite_url: str) -> None:
    """
    Create the SQLite database file and all tables if they don't exist.
    TODO: replace the placeholder touch() with Base.metadata.create_all(engine)
          once all models are finalised.
    """
    db_path = Path(sqlite_url.replace("sqlite:///", ""))

    if db_path.exists():
        print(f"  SQLite  {db_path} — already exists, skipping.")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    # TODO: import engine + Base and call Base.metadata.create_all(engine)
    db_path.touch()
    print(f"  SQLite  {db_path} — created.")


def init_lancedb(lancedb_uri: str) -> None:
    """
    Create the LanceDB data directory if it doesn't exist.
    TODO: connect via lancedb.connect() and create the documents table schema.
    """
    db_path = Path(lancedb_uri)

    if db_path.exists():
        print(f"  LanceDB {db_path} — already exists, skipping.")
        return

    db_path.mkdir(parents=True, exist_ok=True)
    # TODO: lancedb.connect(lancedb_uri) and create initial table
    print(f"  LanceDB {db_path} — created.")


def main() -> None:
    cfg = _read_config()
    sqlite_url = cfg.get("database", "sqlite_url", fallback="sqlite:///./data/app.db")
    lancedb_uri = cfg.get("database", "lancedb_uri", fallback="./data/lancedb")

    print("Checking databases ...")
    init_sqlite(sqlite_url)
    init_lancedb(lancedb_uri)
    print("Database check complete.")


if __name__ == "__main__":
    main()
