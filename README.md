# semantic-document-search

Proof-of-concept semantic document search for local usage.

- LanceDB: selected over FAISS, PostgreSQL plus pgvector, and ChromaDB. It supports vector search and can later support richer filtering.
- SQLite: lightweight metadata store for this POC.

## Setup

1. Clone the repository.
2. Run setup from the project root:
    ```bash
    /bin/bash setup_venv.sh
    ```
    This creates the virtual environment, installs dependencies, prepares config, and initializes databases/indexes.
3. Activate the virtual environment:
    ```bash
    source .venv/bin/activate
    ```
4. Review auth settings in config.ini and set a real admin password before non-local usage:
    - auth.admin_password
    - auth.admin_jwt_salt
5. Optionally seed data with MSMARCO or Wikipedia:
    ```bash
    python scripts/load_msmarco.py
    ```
    or
    ```bash
    python scripts/load_wikipedia.py
    ```
    - MSMARCO loads much faster but documents are small/simplified.
    - Wikipedia takes much longer on CPU-only machines and is closer to real-world content.
6. Start the server:
    ```bash
    uvicorn app.main:app
    ```
    By default it listens on 127.0.0.1:8000. Use --host and --port to change that.
7. Wait until "Application startup complete." appears.
8. Open:
    - http://127.0.0.1:8000/docs for Swagger UI.
    - http://127.0.0.1:8000/demo for the demo UI.

## Tests

Run the full test suite from the project root:

```bash
pytest -q
```

Useful subsets:

```bash
pytest tests/test_chunker.py -q
pytest tests/test_search.py -q
```

Notes:

1. `tests/test_chunker.py` validates parsing/chunking behavior for TXT, HTML, PDF, and DOCX.
2. `tests/test_search.py` validates hybrid search behavior and expects indexed data to exist.
3. Test discovery is configured in `pytest.ini` with `testpaths = tests`.

## Modular structure

The project is intentionally organized in layers:

1. API layer: `app/routers/`
2. Service/business layer: `app/services/`
3. Persistence/infrastructure layer: `app/database.py` plus `app/models/`
4. API contracts: `app/schemas/`

This separation means core components are swappable with focused changes:

1. Database engine/session setup is centralized in `app/database.py`.
2. ORM entities are isolated in `app/models/`.
3. Most persistence-specific logic is in the service layer (`app/services/document_service.py`, `app/services/search_service.py`, `app/services/indexing_service.py`).

The structure is modular enough to swap storage and indexing backends, but it is not zero-change plug-and-play. Typical changes include:

1. Update `app/database.py` and storage-touching service methods.
2. Keep routers and schema contracts mostly unchanged.
3. If embedding/reranking models change, retune embedding/vector dimensions.
4. Retune ANN index settings (for example partitions and index type).
5. Revisit chunk/batch settings and reindex existing data.

## Notes

### Users and security

1. JWT-based authentication and permission checks are implemented.
2. Admin username is fixed to document-admin.
3. The demo user is seeded by init_db:
    - Username: demo-user
    - Password: sematicsearch
    - Permissions: read-only
4. Upload is batch-only. A single file upload is represented as a batch with one file.
5. CSRF protection is not implemented (API token model; local demo target).

### Storage

1. Storage size mainly depends on embedding dimension/precision and chunk count. Default embedding model is BAAI/bge-small-en-v1.5.
2. Documents are split into chunks (for example headings, paragraphs, lists, code, captions). Chunks can be split further to stay within token limits.
3. More chunks means more vectors and larger storage footprint.
4. Product Quantization (PQ) can reduce vector size, but usually reduces recall and needs tuning.

### Search and quality

1. Ingestion pipeline:
    - Parse documents (PyMuPDF for PDF, other parsers by type).
    - Split content into chunks (spaCy is used for sentence-level splitting where needed).
    - Store documents/chunks in SQLite and vectors in LanceDB.
2. Search pipeline:
    - Build query embedding.
    - ANN vector search.
    - SQLite FTS search.
    - RRF (Reciprocal Rank Fusion) to combine vector and keyword results.
    - Cross-encoder reranking.
    - Return top N results.
3. Quality has not been formally benchmarked in this POC.

### Future improvements

1. Reduce dependency surface where practical.
2. Add and evaluate PQ for large-scale storage constraints.
3. Improve semantic chunking and dynamic chunk sizing.
4. Expand multilingual handling.
5. Evaluate alternative parsers such as unstructured for more complex document layouts.
6. Evaluate index strategy for very large corpora (for example 10M plus documents).
7. Improve incremental reindexing behavior for frequently updated datasets.

### AI used

1. Initial research and consultations were done with ChatGPT:
    - https://chatgpt.com/share/6a118f29-cab4-83eb-b56c-e07eaabce8a6
    - https://chatgpt.com/share/6a142cb8-8994-83eb-84cb-846375f79ba7
2. Development was done with VS Code and GitHub Copilot (Claude Sonnet 4.6 High).

### Performance

1. The project was developed on CPU-only hardware.
2. Embedding, reranking, and indexing are significantly faster with GPUs and tuned runtime settings.