"""
Phase 2, step 2: embed the Silver documents and load them into a local,
persistent ChromaDB collection.

Uses ChromaDB's built-in sentence-transformers embedding function
(all-MiniLM-L6-v2) — runs locally and free, no API key needed for this step.
Downloads a small model (~80MB) the first time you run this.

Usage:
    python build_vector_store.py
"""

import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = PROJECT_ROOT / "data" / "silver_documents.json"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma_db"
COLLECTION_NAME = "nyc_housing_records"

BATCH_SIZE = 500


def main():
    documents = json.load(open(DOCUMENTS_PATH))
    print(f"Loaded {len(documents)} documents to embed and index")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
    )

    for i in range(0, len(documents), BATCH_SIZE):
        batch = documents[i : i + BATCH_SIZE]
        collection.add(
            ids=[d["id"] for d in batch],
            documents=[d["text"] for d in batch],
            metadatas=[d["metadata"] for d in batch],
        )
        print(f"  indexed {min(i + BATCH_SIZE, len(documents))}/{len(documents)}")

    print(f"\nDone. Collection '{COLLECTION_NAME}' has {collection.count()} records.")
    print(f"Persisted to {CHROMA_DIR}")


if __name__ == "__main__":
    main()
