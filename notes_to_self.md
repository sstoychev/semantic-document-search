# Initial research
Chats are split because the bot starts halucinating.
[ChatGPT - part 1](https://chatgpt.com/share/6a118f29-cab4-83eb-b56c-e07eaabce8a6)
[ChatGPT - part 2](https://chatgpt.com/share/6a142cb8-8994-83eb-84cb-846375f79ba7)

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

1. ✅Skeleton structure for FastAPI (two endpoints) + swagger calling dummy services for business logic
    - ✅requirements.txt with the necessary packages
    - ✅script to create and activate venv
    - ✅config for embeddings and reranker models, db files paths
2. ✅Implement methods for:
    - ✅embeddings generation - ==**CHUNKING!!!**== -> recursive: heading -> section -> paragraph -> sentence -> tokens, respecting headings, code blocks, bullet lists, tables. 500 tokens, 100 tokens overlap. PyMuPDF
    - ✅store in LanceDB and SQLite (no index update at this point!)
    - ✅vector + fts search
    - ✅reranking
3. ✅Script to seed 10k documents
    - ✅Wikipedia - 10k documents (78076 chunks) in 16972s
    - ✅Hugging Face BEIR - msmarco -> insert 10k documents (10k chunks, 30-90tokens) in 644s
4. Index updates on insert/update/delete
    - index update after X changes or X time
    - main + delta index
5. Authorisation/Authentication
    - ✅master password set at project initialization
    - login API methods
    - users creation with permissions
    - JWT with salt for permission groups. Salt reset/invalidation for token revocation.

# Further future improvements
1. Review used packages/libraries and remove ones, which are used very little, with custom code. This is for security reasons
2. Product Quantization (PQ) - reducing the vector database size by compressing vectors to 2x, 4x, 8x, 16x smaller ones. If storage/size is a problem we should train quantizers + fine tune their parameters and evaluate results. There will be loss of quality(recall) and we should evaluate if we are OK with this and eventually to what extend.
3. Semantic chunking - detecting actual topic changes/transitions, for example installation instructions -> troubleshooting.
4. Dynamic chunk size - analyze the document if it is more of short statements/facts(FAQs, support docs, short ansers) or long statements (conceptual docs, fiction writing). Small chunks = ⬆️precision, ⬆️reranker quality, ⬇️context loss, ⬇️vectors/storage. Large chunks = ⬆️context, ⬆️vectors/storage, ⬇️semantic delusion, ⬇️ANN precision, ⬇️reranker noise, ⬇️latency
5. Multilangual native support - depending on quality and if we have enough resources we may check if using the native language of the document/query gives significantly better results.
6. Replace PyMuPDF with unstructured.io for more complex analysis.
6.a - Consider different chunkers/splitters for different sources.
7. In case we keep LanceDB for 10M documents we have to review non-HNSW indexes. They require more training and fine-tuning, but they use less memory and are faster.