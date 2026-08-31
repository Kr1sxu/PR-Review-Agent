"""
BM25 Retriever - PR-Review Agent
In-memory BM25 keyword retrieval on RAG chunks.
Loaded from PostgreSQL rag_vectors table at init time.
Used as the keyword branch in hybrid (vector + BM25) retrieval.
"""

import logging
import re
from typing import List, Tuple

from src.rag.chunker import Chunk

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    """
    Simple tokenizer for Chinese + English mixed text.
    - Splits on whitespace and punctuation
    - Keeps Chinese characters as individual tokens
    - Lowercases English words
    - Filters tokens shorter than 2 chars (except single Chinese chars)
    """
    # Split on non-alphanumeric/non-CJK boundaries
    tokens = re.findall(r'[一-鿿]|[a-zA-Z0-9_]{2,}', text.lower())
    return tokens


class BM25Retriever:
    """
    BM25 keyword retriever operating on in-memory chunk index.
    
    Usage:
        bm25 = BM25Retriever(k1=1.5, b=0.75)
        bm25.build_index(chunks)          # load Chunk objects
        results = bm25.search(query, top_k=5)  # -> [(Chunk, score)]
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._chunks: List[Chunk] = []
        self._tokenized_corpus: List[List[str]] = []
        self._doc_lengths: List[int] = []
        self._avg_doc_length: float = 0.0
        self._idf: dict = {}
        self._built = False

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def build_index(self, chunks: List[Chunk]) -> None:
        """
        Build BM25 index from a list of Chunk objects.
        Tokenizes all chunk texts and precomputes IDF values.
        """
        if not chunks:
            logger.warning("BM25Retriever: empty chunk list, skip build")
            return

        self._chunks = chunks
        self._tokenized_corpus = [_tokenize(chunk.text) for chunk in chunks]
        self._doc_lengths = [len(tokens) for tokens in self._tokenized_corpus]
        self._avg_doc_length = sum(self._doc_lengths) / len(self._doc_lengths) if self._doc_lengths else 1.0

        # Compute IDF: log((N - n + 0.5) / (n + 0.5) + 1)
        n_docs = len(chunks)
        df = {}  # document frequency
        for tokens in self._tokenized_corpus:
            seen = set(tokens)
            for token in seen:
                df[token] = df.get(token, 0) + 1

        import math
        self._idf = {}
        for token, freq in df.items():
            self._idf[token] = math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1.0)

        self._built = True
        logger.info(f"BM25Retriever: index built with {n_docs} chunks, "
                    f"avg_len={self._avg_doc_length:.0f}, vocab={len(self._idf)}")

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Chunk, float]]:
        """
        Search index with BM25 scoring.
        :return: List of (Chunk, bm25_score) tuples sorted by score descending
        """
        if not self._built or not self._chunks:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._score_all(query_tokens)

        # Pair with chunks and sort by score descending
        paired = [(self._chunks[i], scores[i]) for i in range(len(scores))]
        paired.sort(key=lambda x: x[1], reverse=True)

        # Filter zero-score and return top_k
        results = [(chunk, score) for chunk, score in paired[:top_k] if score > 0]
        return results

    def _score_all(self, query_tokens: List[str]) -> List[float]:
        """Compute BM25 scores for all documents against query tokens."""
        scores = [0.0] * len(self._chunks)

        for token in query_tokens:
            if token not in self._idf:
                continue

            idf = self._idf[token]
            for i, doc_tokens in enumerate(self._tokenized_corpus):
                # Term frequency in document
                tf = doc_tokens.count(token)
                if tf == 0:
                    continue

                doc_len = self._doc_lengths[i]
                # BM25 formula
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * doc_len / self._avg_doc_length
                )
                scores[i] += idf * numerator / denominator

        return scores

    def clear(self) -> None:
        """Clear the index."""
        self._chunks = []
        self._tokenized_corpus = []
        self._doc_lengths = []
        self._idf = {}
        self._built = False
