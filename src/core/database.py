"""
Database Module - PR-Review Agent
PostgreSQL + pgvector 连接管理与初始化
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "127.0.0.1"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "pr_review"),
    "user":     os.getenv("DB_USER", "pr_review"),
    "password": os.getenv("DB_PASSWORD", "pr_review_2026"),
}


async def init_db() -> asyncpg.Pool:
    """初始化连接池，确保数据库和扩展就绪"""
    global _pool
    if _pool is not None:
        return _pool

    _pool = await asyncpg.create_pool(
        **DB_CONFIG,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )

    async with _pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    logger.info(
        f"PostgreSQL connected: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    )
    return _pool


async def close_db():
    """关闭连接池"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


def get_pool() -> asyncpg.Pool:
    """获取当前连接池（必须先调用 init_db）"""
    if _pool is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _pool


@asynccontextmanager
async def get_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """获取单个数据库连接的上下文管理器"""
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn
