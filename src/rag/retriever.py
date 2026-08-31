"""
RAG Retriever - PR-Review Agent
Hybrid retrieval: Vector (pgvector) + BM25 keyword search
Fusion ranking via Reciprocal Rank Fusion (RRF)

Pipeline:
  1. Load knowledge base -> chunk -> vectorize -> store in pgvector
  2. On query: parallel vector search + BM25 search
  3. RRF fusion -> merged Top-K results

Graceful degradation: falls back to whichever branch is available.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.rag.chunker import MarkdownChunker, Chunk
from src.rag.vector_store import VectorStore
from src.rag.bm25_retriever import BM25Retriever
from src.models.embedding import MiMoEmbeddingModel

logger = logging.getLogger(__name__)

# RRF constant: standard value from the original RRF paper
RRF_K = 60


def reciprocal_rank_fusion(
    result_lists: List[List[Tuple[Chunk, float]]],
    k: int = RRF_K,
    weights: Optional[List[float]] = None,
) -> List[Tuple[Chunk, float]]:
    """
    Reciprocal Rank Fusion (RRF) - merge multiple ranked result lists.

    RRF_score(d) = sum( w_i / (k + rank_i(d)) )
    where rank_i(d) is the 1-based rank of document d in list i.

    :param result_lists: List of ranked result lists, each is [(Chunk, score)]
    :param k: RRF constant (default 60, from original paper)
    :param weights: Optional per-list weights (default all 1.0)
    :return: Merged list of (Chunk, rrf_score) sorted descending
    """
    if not result_lists:
        return []

    if weights is None:
        weights = [1.0] * len(result_lists)

    # Use chunk text as dedup key (same text = same chunk)
    rrf_scores: Dict[str, float] = {}
    chunk_map: Dict[str, Chunk] = {}

    for result_list, weight in zip(result_lists, weights):
        for rank, (chunk, _score) in enumerate(result_list, start=1):
            key = chunk.text
            if key not in rrf_scores:
                rrf_scores[key] = 0.0
                chunk_map[key] = chunk
            rrf_scores[key] += weight / (k + rank)

    # Sort by RRF score descending
    merged = [
        (chunk_map[text], score)
        for text, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    ]
    return merged


class RAGRetriever:
    """
    Hybrid RAG Retriever - Vector + BM25 with RRF fusion.

    Architecture:
        RAGRetriever (orchestrator)
        ├── VectorStore      (pgvector cosine similarity - semantic)
        ├── BM25Retriever     (in-memory BM25 - keyword)
        └── RRF fusion        (merge both result sets)

    External API unchanged:
        - retrieve(query) -> List[dict]
        - get_context_string(query) -> str
    """

    def __init__(
        self,
        embedding_model: MiMoEmbeddingModel,
        knowledge_base_path: str = "./knowledge_base",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        top_k: int = 5,
        similarity_threshold: float = 0.7,
        cache_path: Optional[str] = None,
    ):
        self.embedding_model = embedding_model
        self.kb_path = Path(knowledge_base_path)
        self.chunker = MarkdownChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.store = VectorStore()
        self.bm25 = BM25Retriever()
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Load knowledge base, chunk, vectorize, build BM25 index.
        If pgvector already has data, skip embedding and just load BM25 index.
        """
        if self._initialized:
            return True

        # Check if pgvector already has data
        if await self.store.load_cache_async():
            # Data exists in pgvector, just build BM25 index from DB
            await self._build_bm25_from_db()
            self._initialized = True
            logger.info(
                f"RAG initialized from PostgreSQL "
                f"({self.store.count} chunks, BM25 index ready)"
            )
            return True

        # Load and chunk knowledge base files
        if not self.kb_path.exists():
            logger.warning(f"Knowledge base path not found: {self.kb_path}")
            return False

        all_chunks = []
        md_files = list(self.kb_path.glob("*.md"))
        if not md_files:
            logger.warning(f"No Markdown files found in {self.kb_path}")
            return False

        for md_file in md_files:
            chunks = self.chunker.chunk_file(str(md_file))
            all_chunks.extend(chunks)
            logger.debug(f"Chunked {md_file.name}: {len(chunks)} chunks")

        if not all_chunks:
            logger.warning("No chunks generated from knowledge base")
            return False

        # Vectorize
        texts = [chunk.text for chunk in all_chunks]
        try:
            vectors = await self.embedding_model.embed_batch(texts)
        except Exception as e:
            logger.warning(f"Embedding failed, RAG degraded: {e}")
            return False

        if all(all(v == 0 for v in vec) for vec in vectors):
            logger.warning("All vectors are zero (offline mode), RAG degraded")
            return False

        # Write to pgvector
        await self.store.add_batch_async(all_chunks, vectors)

        # Build BM25 index from the same chunks
        self.bm25.build_index(all_chunks)

        self._initialized = True
        logger.info(
            f"RAG initialized: {len(all_chunks)} chunks from {len(md_files)} files "
            f"-> pgvector + BM25 index"
        )
        return True

    async def _build_bm25_from_db(self) -> None:
        """Load all chunks from PostgreSQL and build BM25 index."""
        try:
            chunks = await self.store.get_all_chunks_async()
            if chunks:
                self.bm25.build_index(chunks)
                logger.info(f"BM25 index built from {len(chunks)} DB chunks")
        except Exception as e:
            logger.warning(f"BM25 index build failed (will use vector-only): {e}")

    async def retrieve(self, query: str) -> List[dict]:
        """
        Hybrid retrieval: vector + BM25 with RRF fusion.
        Falls back to whichever branch is available.

        :return: List of {text, source_file, section_title, score, method} dicts
        """
        if not self._initialized:
            if not await self.initialize():
                return []

        # Run both searches in parallel
        vector_results, bm25_results = await asyncio.gather(
            self._vector_search(query),
            self._bm25_search(query),
            return_exceptions=True,
        )

        # Handle exceptions
        if isinstance(vector_results, Exception):
            logger.warning(f"Vector search failed: {vector_results}")
            vector_results = []
        if isinstance(bm25_results, Exception):
            logger.warning(f"BM25 search failed: {bm25_results}")
            bm25_results = []

        # Fusion strategy
        if vector_results and bm25_results:
            # Both available: RRF fusion
            merged = reciprocal_rank_fusion(
                [vector_results, bm25_results],
                k=RRF_K,
                weights=[1.0, 0.8],  # Slightly favor vector (semantic)
            )
            method = "hybrid"
        elif vector_results:
            merged = vector_results
            method = "vector-only"
        elif bm25_results:
            merged = bm25_results
            method = "bm25-only"
        else:
            return []

        # Take top_k
        top_results = merged[:self.top_k]

        logger.debug(
            f"Hybrid retrieval: vector={len(vector_results)}, "
            f"bm25={len(bm25_results)}, fused={len(merged)}, "
            f"method={method}, returned={len(top_results)}"
        )

        return [
            {
                "text": chunk.to_context_text(),
                "source_file": chunk.source_file,
                "section_title": chunk.section_title,
                "score": round(score, 4),
                "method": method,
            }
            for chunk, score in top_results
        ]

    async def _vector_search(self, query: str) -> List[Tuple[Chunk, float]]:
        """Semantic search via pgvector cosine similarity."""
        try:
            query_vector = await self.embedding_model.embed_single(query)
            if all(v == 0 for v in query_vector):
                return []
            results = await self.store.search_async(
                query_vector,
                top_k=self.top_k * 2,  # Retrieve more for fusion
                threshold=self.similarity_threshold,
            )
            return results
        except Exception as e:
            logger.warning(f"Vector search error: {e}")
            return []

    async def _bm25_search(self, query: str) -> List[Tuple[Chunk, float]]:
        """Keyword search via BM25."""
        try:
            if not self.bm25.is_built:
                return []
            results = self.bm25.search(query, top_k=self.top_k * 2)
            return results
        except Exception as e:
            logger.warning(f"BM25 search error: {e}")
            return []

    async def get_context_string(self, query: str) -> str:
        """Retrieve and format context as a single string for prompt injection."""
        results = await self.retrieve(query)
        if not results:
            return ""
        parts = []
        for idx, r in enumerate(results, 1):
            method_tag = "[" + r["method"] + "]"
            score_val = r["score"]
            text_val = r["text"]
            parts.append(
                f"### Reference {idx} (score: {score_val}, {method_tag})\n{text_val}"
            )
        return "\n\n".join(parts)

    async def reload(self) -> bool:
        """Force reload knowledge base (clear pgvector + BM25 and rebuild)."""
        await self.store.clear_async()
        self.bm25.clear()
        self._initialized = False
        return await self.initialize()
