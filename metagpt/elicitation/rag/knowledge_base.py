"""
E-commerce RAG Knowledge Base
-------------------------------
ChromaDB-backed vector store for e-commerce architecture patterns,
domain constraints, and reference SRS documents.

Used by:
  - CompletenessAnalyser  : to detect implied coverage in SRS text
  - QuestionPrioritiser   : to enrich clarifying questions with domain context

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

DEFAULT_PERSIST_DIR = str(Path(__file__).parent.parent.parent.parent / "rag_store" / "ecommerce")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "ecommerce_patterns"


class EcommerceKnowledgeBase:
    """
    Persistent vector store for e-commerce domain knowledge.

    Documents are grouped by category tag so queries can be
    filtered to a specific domain area (e.g. 'payment', 'security').
    """

    def __init__(self, persist_dir: str = DEFAULT_PERSIST_DIR):
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._model: Optional[SentenceTransformer] = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(EMBEDDING_MODEL)
        return self._model

    # ------------------------------------------------------------------ #
    #  Write                                                               #
    # ------------------------------------------------------------------ #

    def add_documents(self, docs: List[dict]) -> None:
        """
        Add documents to the knowledge base.

        Each doc must have:
          - id       : unique string identifier
          - text     : the document content
          - category : schema category tag (e.g. 'payment', 'performance')

        Duplicate ids are silently skipped.
        """
        existing_ids = set(self.collection.get()["ids"])
        new_docs = [d for d in docs if d["id"] not in existing_ids]

        if not new_docs:
            return

        texts = [d["text"] for d in new_docs]
        ids = [d["id"] for d in new_docs]
        metadatas = [{"category": d.get("category", "general")} for d in new_docs]
        embeddings = self.model.encode(texts, show_progress_bar=False).tolist()

        self.collection.add(
            documents=texts,
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    # ------------------------------------------------------------------ #
    #  Read                                                                #
    # ------------------------------------------------------------------ #

    def query(
        self,
        query_text: str,
        n_results: int = 3,
        category_filter: Optional[str] = None,
    ) -> List[str]:
        """
        Return the n_results most similar documents to query_text.
        Optionally restrict to a specific category.
        """
        embedding = self.model.encode([query_text], show_progress_bar=False).tolist()

        where = {"category": category_filter} if category_filter else None

        results = self.collection.query(
            query_embeddings=embedding,
            n_results=n_results,
            where=where,
        )
        return results["documents"][0] if results["documents"] else []

    def query_with_metadata(
        self,
        query_text: str,
        n_results: int = 3,
        category_filter: Optional[str] = None,
    ) -> List[dict]:
        """Return documents together with their category metadata."""
        embedding = self.model.encode([query_text], show_progress_bar=False).tolist()
        where = {"category": category_filter} if category_filter else None

        results = self.collection.query(
            query_embeddings=embedding,
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        return [
            {"text": doc, "category": meta.get("category"), "distance": dist}
            for doc, meta, dist in zip(docs, metas, distances)
        ]

    # ------------------------------------------------------------------ #
    #  Utility                                                             #
    # ------------------------------------------------------------------ #

    def count(self) -> int:
        return self.collection.count()

    def is_seeded(self) -> bool:
        return self.count() > 0

    def reset(self) -> None:
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
