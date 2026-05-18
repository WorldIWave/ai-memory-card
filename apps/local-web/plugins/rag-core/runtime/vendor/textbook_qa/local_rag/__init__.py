# Input: local RAG utility imports.
# Output: public local RAG helper symbols.
# Role: expose lightweight retrieval helpers for package consumers.
# Note: keep imports cheap and free of model side effects.

from __future__ import annotations

from textbook_qa.local_rag.aggregation import aggregate_structured_points, augment_structured_points_with_aggregates
from textbook_qa.local_rag.embeddings import LexicalEmbeddingProvider, cosine_similarity
from textbook_qa.local_rag.index import IndexedBlock, LocalBlockIndex, SearchResult, build_block_index
from textbook_qa.local_rag.knowledge_units import RAGKnowledgeUnit, assemble_rag_unit
from textbook_qa.local_rag.retrieval import RetrievedContext, build_retrieval_query, retrieve_contexts

__all__ = [
    "IndexedBlock",
    "LexicalEmbeddingProvider",
    "LocalBlockIndex",
    "RAGKnowledgeUnit",
    "RetrievedContext",
    "SearchResult",
    "aggregate_structured_points",
    "augment_structured_points_with_aggregates",
    "assemble_rag_unit",
    "build_block_index",
    "build_retrieval_query",
    "cosine_similarity",
    "retrieve_contexts",
]
