# Initial research
[ChatGPT](https://chatgpt.com/share/6a118f29-cab4-83eb-b56c-e07eaabce8a6)

Notes:
- LanceDB
- SQLite3
- float16
- text only in SQLite3
- ef_search (or similar) = 200
- no Product Quantization (PQ) - additional research is required for quantizers training, tuning and results measurement.
- English texts only for storage and vector. Translation will be just a placeholder for future implementation (if ever).
- English only queries - the query will not be translated and will be used "as is". Future possible translation
- Testing data from Wikipedia
- Testing data from hugging face BEIR datasets [msmarco](https://huggingface.co/datasets/BeIR/msmarco)

# Plan

1. Skeleton structure for FastAPI (two endpoints) + swagger calling dummy services for business logic
    - requirements.txt with the necessary packages
    - script to create and activate venv
    - config for embeddings and reranker models, db files paths
2. Implement methods for:
    - embeddings generation - ==**CHUNKING!!!**==
    - store in LanceDB and SQLite (no index update at this point!)
    - vector + fts search
    - reranking
3. Script to seed 10k documents
    - Wikipedia
    - Hugging Face BEIR - msmarco
4. Index updates on insert/update/delete
    - index update after X changex or X time
    - main + delta index
5. Authorisation/Authentication
    - master password set at project initialization
    - login API methods
    - users creation with permissions
    - JWT with salt for permission groups. Salt reset/invalidation for token revocation.
