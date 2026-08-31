"""
Config API Routes - PR-Review Agent
GET  /api/config - read config (keys masked)
PUT  /api/config - update config
"""

import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from src.core.config_loader import get_config

router = APIRouter(tags=["config"])


class UpdateConfigRequest(BaseModel):
    mimo_api_url: Optional[str] = None
    mimo_api_key: Optional[str] = None
    mimo_model_name: Optional[str] = None
    embedding_api_url: Optional[str] = None
    embedding_api_key: Optional[str] = None


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "***" + key[-4:]


@router.get("/config")
async def read_config():
    config = get_config()
    mimo = config.get_model_config("mimo")
    emb = config.get_model_config("embedding")
    return {
        "mimo": {
            "api_url": os.environ.get("MIMO_API_URL", ""),
            "api_key": _mask_key(os.environ.get("MIMO_API_KEY", "")),
            "model_name": os.environ.get("MIMO_MODEL_NAME", ""),
        },
        "embedding": {
            "api_url": os.environ.get("EMBEDDING_API_URL", ""),
            "api_key": _mask_key(os.environ.get("EMBEDDING_API_KEY", "")),
        },
        "offline_mode": config.offline_mode,
        "flow": config.get_flow_config(),
        "rag": config.get_rag_config(),
    }


@router.put("/config")
async def update_config(req: UpdateConfigRequest):
    updated = {}
    if req.mimo_api_url is not None:
        os.environ["MIMO_API_URL"] = req.mimo_api_url
        updated["mimo_api_url"] = True
    if req.mimo_api_key is not None:
        os.environ["MIMO_API_KEY"] = req.mimo_api_key
        updated["mimo_api_key"] = True
    if req.mimo_model_name is not None:
        os.environ["MIMO_MODEL_NAME"] = req.mimo_model_name
        updated["mimo_model_name"] = True
    if req.embedding_api_url is not None:
        os.environ["EMBEDDING_API_URL"] = req.embedding_api_url
        updated["embedding_api_url"] = True
    if req.embedding_api_key is not None:
        os.environ["EMBEDDING_API_KEY"] = req.embedding_api_key
        updated["embedding_api_key"] = True

    # Reload config
    get_config().reload()
    return {"updated": updated, "offline_mode": get_config().offline_mode}
