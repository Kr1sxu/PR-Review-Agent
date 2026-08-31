"""
Embedding Client for PR-Review Agent
Based on AgentScope v2 EmbeddingModelBase
Supports single/batch embedding, offline fallback with zero vectors
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel, Field

from agentscope.embedding import (
    EmbeddingModelBase,
    EmbeddingResponse,
    EmbeddingUsage,
)
from agentscope.credential._base import CredentialBase

logger = logging.getLogger(__name__)


class EmbeddingParameters(BaseModel):
    """Embedding model parameters (empty for now)"""
    pass


class MiMoEmbeddingModel(EmbeddingModelBase[str]):
    """
    text-embedding-v4 vector model (inherits AgentScope EmbeddingModelBase)
    - Independent HTTP calls, no OpenAI SDK dependency
    - Batch splitting, timeout retry
    - Fallback to zero vectors on failure
    """

    _DEFAULT_BATCH_SIZE: int = 10

    def __init__(
        self,
        credential: CredentialBase,
        model: str = "text-embedding-v4",
        dimensions: int = 1024,
        parameters: EmbeddingParameters | None = None,
        context_size: int = 8191,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
    ) -> None:
        super().__init__(
            credential=credential,
            model=model,
            dimensions=dimensions,
            parameters=parameters or EmbeddingParameters(),
            context_size=context_size,
            batch_size=self._DEFAULT_BATCH_SIZE,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        self.timeout = timeout
        # Normalize base_url: append /embeddings if needed
        base = getattr(credential, 'base_url', '') or ''
        base = base.rstrip('/')
        if base and not base.endswith('/embeddings'):
            self._api_url = base + '/embeddings'
        else:
            self._api_url = base
        self.offline = not (
            credential.api_key.get_secret_value()
            and getattr(credential, "base_url", None)
        )
        if self.offline:
            logger.warning("Embedding offline: missing api_key or base_url")

    @classmethod
    def _get_retryable_exceptions(cls) -> tuple[Type[Exception], ...]:
        return (
            httpx.TimeoutException,
            httpx.HTTPStatusError,
            httpx.ConnectError,
        )

    async def _call_api(self, inputs: list[str]) -> EmbeddingResponse:
        if self.offline:
            return self._build_offline_response(inputs)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.credential.api_key.get_secret_value()}",
        }
        payload = {
            "input": inputs,
            "model": self.model,
            "dimensions": self.dimensions,
        }

        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.post(
                self._api_url,
                headers=headers,
                json=payload,
            )
            if response.status_code != 200:
                logger.warning(f"Embedding API {response.status_code}: {response.text[:500]}")
            response.raise_for_status()
            data = response.json()

        embeddings = []
        for item in data.get("data", []):
            embeddings.append(item.get("embedding", []))

        if len(embeddings) < len(inputs):
            embeddings.extend(
                [self._get_empty_vector() for _ in range(len(inputs) - len(embeddings))]
            )

        raw_usage = data.get("usage", {})
        usage = EmbeddingUsage(
            time=0.0,
            tokens=raw_usage.get("total_tokens", raw_usage.get("prompt_tokens")),
        )
        return EmbeddingResponse(
            embeddings=embeddings,
            usage=usage,
        )

    def _build_offline_response(self, inputs: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(
            embeddings=[self._get_empty_vector() for _ in inputs],
            usage=EmbeddingUsage(time=0.0),
        )

    def _get_empty_vector(self) -> List[float]:
        return [0.0] * self.dimensions

    async def embed_single(self, text: str) -> List[float]:
        if self.offline:
            return self._get_empty_vector()
        if not text.strip():
            return self._get_empty_vector()
        try:
            response = await self._call_api([text])
            return response.embeddings[0] if response.embeddings else self._get_empty_vector()
        except Exception as e:
            logger.warning(f"Embedding failed, fallback to zero vector: {e}")
            return self._get_empty_vector()

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self.offline:
            return [self._get_empty_vector() for _ in texts]
        if not texts:
            return []
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            try:
                response = await self._call_api(batch)
                all_embeddings.extend(response.embeddings)
            except Exception as e:
                logger.warning(f"Batch embedding batch {i // self.batch_size + 1} failed: {e}")
                all_embeddings.extend([self._get_empty_vector() for _ in batch])
        return all_embeddings

    @staticmethod
    def similarity(vec_a: List[float], vec_b: List[float]) -> float:
        if len(vec_a) != len(vec_b) or not vec_a:
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


def create_embedding_model(
    api_url: str = "",
    api_key: str = "",
    model_name: str = "text-embedding-v4",
    dimensions: int = 1024,
    timeout: int = 30,
    batch_size: int = 10,
) -> MiMoEmbeddingModel:
    from agentscope.credential._openai import OpenAICredential
    credential = OpenAICredential(api_key=api_key, base_url=api_url)
    model = MiMoEmbeddingModel(
        credential=credential,
        model=model_name,
        dimensions=dimensions,
        timeout=timeout,
    )
    model._DEFAULT_BATCH_SIZE = batch_size
    model.batch_size = batch_size
    return model

