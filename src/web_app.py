"""
FastAPI Web Application Entry - PR-Review Agent
启动时自动连接 PostgreSQL + pgvector
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时连接数据库，关闭时释放连接"""
    from src.core.database import init_db, close_db
    import logging
    logger = logging.getLogger(__name__)

    try:
        await init_db()
        logger.info("PostgreSQL 连接成功")
    except Exception as e:
        logger.warning(f"PostgreSQL 连接失败，降级为无持久化模式: {e}")

    yield

    await close_db()


app = FastAPI(
    title="PR-Review Agent",
    description="Multi-agent PR code review system",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.web.routes_task import router as task_router
from src.web.routes_report import router as report_router
from src.web.routes_score import router as score_router
from src.web.routes_config import router as config_router
from src.web.routes_repos import router as repos_router

app.include_router(task_router, prefix="/api")
app.include_router(report_router, prefix="/api")
app.include_router(score_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(repos_router, prefix="/api")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "PR-Review Agent"}
