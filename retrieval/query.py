"""
Phase 2, step 3: query the vector store with a combination of semantic
search (the query text) and structured filters (zip, source type, etc.).
"""

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma_db"
COLLECTION_NAME = "nyc_housing_records"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        _collection = _client.get_collection(COLLECTION_NAME, embedding_function=embedding_fn)
    return _collection


def retrieve(
    query_text: str,
    zip_code: str | None = None,
    source: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    collection = _get_collection()

    where = {}
    if zip_code:
        where["zip"] = zip_code
    if source:
        where["source"] = source

    results = collection.query(
        query_texts=[query_text],
        n_results=top_k,
        where=where or None,
    )

    hits = []
    for doc_id, doc, meta, dist in zip(
        results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({"id": doc_id, "text": doc, "metadata": meta, "distance": dist})
    return hits


def _interactive():
    print("NYC Housing Records — retrieval test (Ctrl+C to quit)")
    print("Optionally filter by ZIP first, or press Enter to skip.\n")

    while True:
        zip_filter = input("ZIP filter (or Enter for none): ").strip() or None
        query = input("Question: ").strip()
        if not query:
            continue

        hits = retrieve(query, zip_code=zip_filter, top_k=5)

        print(f"\nTop {len(hits)} results:")
        for i, hit in enumerate(hits, 1):
            print(f"\n[{i}] (distance={hit['distance']:.3f})")
            print(hit["text"])
        print("\n" + "-" * 60 + "\n")


if __name__ == "__main__":
    _interactive()
