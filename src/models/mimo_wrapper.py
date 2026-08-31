"""
MiMo Chat Model Wrapper for PR-Review Agent
Inherits AgentScope v2 ChatModelBase
Compatible with OpenAI Chat Completions API format
Supports timeout retry, JSON output validation, offline fallback
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel, Field

from agentscope.model._base import (
    ChatModelBase,
    ChatResponse,
    TextBlock,
    FinishedReason,
)
from agentscope.message._block import ToolCallBlock, ToolCallState
from agentscope.model._model_usage import ChatUsage
from agentscope.credential._openai import OpenAICredential
from agentscope.message._base import Msg

logger = logging.getLogger(__name__)


class MiMoParameters(BaseModel):
    """MiMo model call parameters"""

    max_tokens: int = Field(
        default=4096,
        title="Max Tokens",
        description="Maximum tokens for model output",
        gt=0,
    )
    temperature: float = Field(
        default=0.3,
        title="Temperature",
        description="Output randomness control, 0 for deterministic",
        ge=0,
        le=2,
    )
    top_p: float | None = Field(
        default=None,
        title="Top P",
        description="Nucleus sampling parameter",
        gt=0,
        le=1,
    )


class MiMoChatModel(ChatModelBase):
    """
    MiMo Chat Model (inherits AgentScope ChatModelBase)
    - OpenAI Chat Completions compatible
    - Timeout retry with configurable count/interval
    - JSON output validation
    - Auto offline fallback when credentials missing
    - Tool calling support via OpenAI function-calling format
    """

    type: str = "mimo_chat"

    def __init__(
        self,
        credential: OpenAICredential,
        model: str = "mimo",
        parameters: MiMoParameters | None = None,
        stream: bool = False,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        context_size: int = 32768,
        timeout: int = 60,
        client_kwargs: dict | None = None,
    ) -> None:
        super().__init__(
            credential=credential,
            model=model,
            parameters=parameters or MiMoParameters(),
            stream=stream,
            max_retries=max_retries,
            retry_delay=retry_delay,
            context_size=context_size,
        )
        self.timeout = timeout
        self.client_kwargs = client_kwargs or {}
        # Normalize base_url: append /chat/completions if needed
        base = credential.base_url.rstrip('/') if credential.base_url else ''
        if base and not base.endswith('/chat/completions'):
            self._api_url = base + '/chat/completions'
        else:
            self._api_url = base
        self.offline = not (
            credential.api_key.get_secret_value()
            and credential.base_url
        )
        if self.offline:
            logger.warning("MiMo offline: missing api_key or base_url")

    @classmethod
    def _get_retryable_exceptions(cls) -> tuple[Type[Exception], ...]:
        return (
            httpx.TimeoutException,
            httpx.HTTPStatusError,
            httpx.ConnectError,
        )

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None = None,
        tool_choice=None,
        **generate_kwargs: Any,
    ) -> ChatResponse:
        if self.offline:
            return self._build_offline_response(messages)

        formatted_messages = self._format_messages(messages)
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": formatted_messages,
            "stream": False,
        }
        params = self.parameters
        if params.max_tokens is not None:
            payload["max_tokens"] = params.max_tokens
        if params.temperature is not None:
            payload["temperature"] = params.temperature
        if params.top_p is not None:
            payload["top_p"] = params.top_p

        # Pass tools to the API if provided
        if tools:
            payload["tools"] = tools

        # Handle tool_choice
        if tool_choice is not None:
            if isinstance(tool_choice, str):
                payload["tool_choice"] = tool_choice
            elif hasattr(tool_choice, 'mode'):
                mode = tool_choice.mode
                if mode in ("auto", "none", "required"):
                    payload["tool_choice"] = mode
                else:
                    # Force a specific tool by name
                    payload["tool_choice"] = {
                        "type": "function",
                        "function": {"name": mode}
                    }

        # Debug: log formatted messages
        for i, m in enumerate(formatted_messages):
            role = m.get('role', '?')
            clen = len(m.get('content', ''))
            if clen == 0:
                logger.warning(f'Empty message at index {i}: role={role}')

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.credential.api_key.get_secret_value()}",
        }
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.post(
                self._api_url,
                headers=headers,
                json=payload,
            )
            if response.status_code != 200:
                logger.warning(
                    f'MiMo API {response.status_code}: {response.text[:500]}'
                )
                logger.debug(f'Request payload: {json.dumps(payload, ensure_ascii=False)[:1000]}')
            response.raise_for_status()
            data = response.json()

        message = data.get("choices", [{}])[0].get("message", {})
        content_text = message.get("content", "") or ""
        reasoning = message.get("reasoning_content", "") or ""
        raw_tool_calls = message.get("tool_calls") or []
        finish_reason = data.get("choices", [{}])[0].get("finish_reason", "stop")

        # If content is empty but reasoning has JSON, extract it
        if not content_text.strip() and reasoning.strip() and not raw_tool_calls:
            content_text = reasoning

        raw_usage = data.get("usage", {})
        usage = ChatUsage(
            input_tokens=raw_usage.get("prompt_tokens", 0),
            output_tokens=raw_usage.get("completion_tokens", 0),
            time=0.0,
        )

        # Build response content blocks
        content_blocks: list = []

        # Add text block if there's content
        if content_text.strip():
            content_blocks.append(TextBlock(text=content_text))

        # Add tool call blocks
        for tc in raw_tool_calls:
            tc_id = tc.get("id", str(uuid.uuid4()))
            func = tc.get("function", {})
            func_name = func.get("name", "")
            func_args = func.get("arguments", "{}")
            content_blocks.append(
                ToolCallBlock(
                    id=tc_id,
                    name=func_name,
                    input=func_args,
                    state=ToolCallState.PENDING,
                )
            )

        # If no blocks at all, add an empty text block
        if not content_blocks:
            content_blocks.append(TextBlock(text=""))

        return ChatResponse(
            content=content_blocks,
            is_last=True,
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            usage=usage,
            finished_reason=FinishedReason.COMPLETED,
        )

    def _build_offline_response(self, messages: list[Msg]) -> ChatResponse:
        last_content = ""
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "get_text_content"):
                last_content = last_msg.get_text_content()
            elif hasattr(last_msg, "content"):
                if isinstance(last_msg.content, str):
                    last_content = last_msg.content
                elif isinstance(last_msg.content, list):
                    for block in last_msg.content:
                        if hasattr(block, "text"):
                            last_content += block.text

        if any(kw in last_content for kw in ["json", "JSON", "findings"]):
            mock_content = json.dumps(
                {"findings": [], "summary": "[Offline] No model connected", "offline": True},
                ensure_ascii=False,
            )
        else:
            mock_content = "[Offline] No MiMo API configured. Please set .env credentials."

        return ChatResponse(
            content=[TextBlock(text=mock_content)],
            is_last=True,
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            usage=ChatUsage(input_tokens=0, output_tokens=0, time=0.0),
            finished_reason=FinishedReason.COMPLETED,
            metadata={"offline": True},
        )

    @staticmethod
    def _format_messages(messages: list[Msg]) -> list[dict]:
        formatted = []
        for msg in messages:
            role = getattr(msg, "role", "user")
            if hasattr(msg, "get_text_content"):
                text = msg.get_text_content()
            elif hasattr(msg, "content"):
                if isinstance(msg.content, str):
                    text = msg.content
                elif isinstance(msg.content, list):
                    text = "".join(
                        getattr(block, "text", str(block))
                        for block in msg.content
                    )
                else:
                    text = str(msg.content)
            else:
                text = str(msg)
            # Skip empty messages (MiMo requires non-empty assistant content)
            if not text or not text.strip():
                continue
            formatted.append({"role": role, "content": text})
        return formatted

    @staticmethod
    def extract_json(text: str) -> Optional[Any]:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except (json.JSONDecodeError, TypeError):
                pass
        for pattern in [r"(\{.*\})", r"(\[.*\])"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except (json.JSONDecodeError, TypeError):
                    continue
        return None

    def get_text(self, response: ChatResponse) -> str:
        parts = []
        for block in response.content:
            if isinstance(block, TextBlock):
                parts.append(block.text)
        return "".join(parts)

    def get_json(self, response: ChatResponse) -> Optional[Any]:
        text = self.get_text(response)
        return self.extract_json(text)


def create_mimo_model(
    api_url: str = "",
    api_key: str = "",
    model_name: str = "mimo",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    timeout: int = 60,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> MiMoChatModel:
    credential = OpenAICredential(api_key=api_key, base_url=api_url)
    parameters = MiMoParameters(max_tokens=max_tokens, temperature=temperature)
    return MiMoChatModel(
        credential=credential,
        model=model_name,
        parameters=parameters,
        timeout=timeout,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )

