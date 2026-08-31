
"""
Read File Tool - PR-Review Agent
Read-only file content reader, registered as AgentScope Tool
"""

import os
from typing import Any

from agentscope.tool._base import ToolBase
from agentscope.tool._response import ToolChunk, ToolResultState
from agentscope.message._block import TextBlock
from agentscope.permission._decision import PermissionDecision
from agentscope.permission._types import PermissionBehavior
from agentscope.permission._context import PermissionContext


class ReadFileTool(ToolBase):
    """Read file content from the repository (read-only)"""

    name: str = "read_file"
    description: str = (
        "Read the content of a file at the given path. "
        "Only reads files, no modification allowed. "
        "Returns the file content with line numbers."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or relative path to the file",
            },
            "encoding": {
                "type": "string",
                "description": "File encoding, default utf-8",
                "default": "utf-8",
            },
        },
        "required": ["file_path"],
    }
    is_read_only: bool = True
    is_concurrency_safe: bool = True

    def __init__(self, allowed_roots: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._allowed_roots = [
            os.path.realpath(r) for r in allowed_roots
        ] if allowed_roots else []

    async def check_permissions(
        self, tool_input: dict[str, Any], context: PermissionContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Read-only file access allowed",
        )

    def _validate_path(self, file_path: str) -> str:
        resolved = os.path.realpath(file_path)
        if self._allowed_roots:
            is_allowed = any(
                resolved.startswith(root) for root in self._allowed_roots
            )
            if not is_allowed:
                raise PermissionError(
                    f"Path \'{file_path}\' is outside allowed directories"
                )
        return resolved

    async def call(self, file_path: str, encoding: str = "utf-8", **kwargs) -> ToolChunk:
        try:
            validated_path = self._validate_path(file_path)
            if not os.path.exists(validated_path):
                return ToolChunk(
                    content=[TextBlock(text=f"Error: File not found: {file_path}")],
                    state=ToolResultState.ERROR,
                )
            with open(validated_path, "r", encoding=encoding) as f:
                lines = f.readlines()
            numbered = []
            for i, line in enumerate(lines, 1):
                numbered.append(f"{i:4d} | {line.rstrip()}")
            content = "\n".join(numbered)
            return ToolChunk(
                content=[TextBlock(text=content)],
                state=ToolResultState.SUCCESS,
            )
        except PermissionError as e:
            return ToolChunk(
                content=[TextBlock(text=f"Permission denied: {e}")],
                state=ToolResultState.ERROR,
            )
        except Exception as e:
            return ToolChunk(
                content=[TextBlock(text=f"Error reading file: {e}")],
                state=ToolResultState.ERROR,
            )

