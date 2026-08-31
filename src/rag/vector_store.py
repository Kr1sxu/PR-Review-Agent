"""
Vector Store - PR-Review Agent
基于 PostgreSQL + pgvector 的向量存储
替代原有纯内存向量存储，支持持久化和跨任务检索
"""

import logging
from typing import List, Optional, Tuple

from src.core.database import get_pool
from src.rag.chunker import Chunk

logger = logging.getLogger(__name__)


class VectorStore:
    """
    基于 pgvector 的向量存储。
    - 向量持久化到 PostgreSQL（rag_vectors 表）
    - 余弦相似度 Top-K 检索
    - 兼容原有 add / search / save_cache / load_cache 接口
    """

    def __init__(self):
        self._is_built = False
        self._count = 0

    @property
    def is_built(self) -> bool:
        return self._is_built

    @property
    def count(self) -> int:
        return self._count

    async def _sync_count(self):
        pool = get_pool()
        row = await pool.fetchval("SELECT COUNT(*) FROM rag_vectors")
        self._count = row or 0
        self._is_built = self._count > 0

    def add(self, chunk: Chunk, vector: List[float]) -> None:
        """同步接口保留（内部转异步写入）"""
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self._add_async(chunk, vector)
        )

    async def add_async(self, chunk: Chunk, vector: List[float]) -> None:
        """异步添加单条向量"""
        await self._add_async(chunk, vector)

    async def _add_async(self, chunk: Chunk, vector: List[float]) -> None:
        pool = get_pool()
        vec_str = "[" + ",".join(str(v) for v in vector) + "]"
        await pool.execute(
            """INSERT INTO rag_vectors (chunk_text, source_file, section_title, chunk_index, embedding)
               VALUES ($1, $2, $3, $4, $5::vector)""",
            chunk.text,
            chunk.source_file,
            chunk.section_title,
            chunk.chunk_index,
            vec_str,
        )
        await self._sync_count()

    async def add_batch_async(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        """异步批量添加"""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")

        pool = get_pool()
        records = []
        for chunk, vec in zip(chunks, vectors):
            vec_str = "[" + ",".join(str(v) for v in vec) + "]"
            records.append((
                chunk.text,
                chunk.source_file,
                chunk.section_title,
                chunk.chunk_index,
                vec_str,
            ))

        await pool.executemany(
            """INSERT INTO rag_vectors (chunk_text, source_file, section_title, chunk_index, embedding)
               VALUES ($1, $2, $3, $4, $5::vector)""",
            records,
        )
        await self._sync_count()
        logger.info(f"VectorStore: batch inserted {len(records)} vectors")

    def add_batch(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        """同步批量添加（兼容原有接口）"""
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self.add_batch_async(chunks, vectors)
        )

    async def search_async(
        self, query_vector: List[float], top_k: int = 5, threshold: float = 0.0
    ) -> List[Tuple[Chunk, float]]:
        """异步检索：余弦相似度 Top-K"""
        pool = get_pool()
        vec_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        rows = await pool.fetch(
            """SELECT chunk_text, source_file, section_title, chunk_index,
                      1 - (embedding <=> $1::vector) AS similarity
               FROM rag_vectors
               WHERE 1 - (embedding <=> $1::vector) >= $2
               ORDER BY embedding <=> $1::vector
               LIMIT $3""",
            vec_str,
            threshold,
            top_k,
        )

        results = []
        for row in rows:
            chunk = Chunk(
                text=row["chunk_text"],
                source_file=row["source_file"],
                section_title=row["section_title"],
                chunk_index=row["chunk_index"],
            )
            results.append((chunk, float(row["similarity"])))

        return results

    def search(self, query_vector: List[float], top_k: int = 5,
               threshold: float = 0.0) -> List[Tuple[Chunk, float]]:
        """同步检索（兼容原有接口）"""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self.search_async(query_vector, top_k, threshold)
        )

    def save_cache(self, cache_path: str) -> None:
        """兼容原有接口：pgvector 本身已持久化，此方法仅记录日志"""
        logger.info("VectorStore: data is persisted in PostgreSQL, skip JSON cache")

    def load_cache(self, cache_path: str) -> bool:
        """兼容原有接口：pgvector 本身已持久化，检查表中是否有数据"""
        import asyncio
        try:
            return asyncio.get_event_loop().run_until_complete(self._check_data())
        except Exception:
            return False

    async def _check_data(self) -> bool:
        pool = get_pool()
        count = await pool.fetchval("SELECT COUNT(*) FROM rag_vectors")
        self._count = count or 0
        self._is_built = self._count > 0
        return self._is_built

    async def get_all_chunks_async(self) -> List[Chunk]:
        """Load all chunks from rag_vectors table (for BM25 index building)."""
        pool = get_pool()
        rows = await pool.fetch(
            """SELECT chunk_text, source_file, section_title, chunk_index
               FROM rag_vectors
               ORDER BY id"""
        )
        chunks = []
        for row in rows:
            chunks.append(Chunk(
                text=row["chunk_text"],
                source_file=row["source_file"],
                section_title=row["section_title"],
                chunk_index=row["chunk_index"],
            ))
        return chunks

    async def clear_async(self) -> None:
        """清空所有向量"""
        pool = get_pool()
        await pool.execute("DELETE FROM rag_vectors")
        self._count = 0
        self._is_built = False
        logger.info("VectorStore: cleared all vectors")

    def clear(self) -> None:
        """清空所有向量"""
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.clear_async())

    async def load_cache_async(self) -> bool:
        """异步检查 pgvector 中是否已有数据"""
        return await self._check_data()
