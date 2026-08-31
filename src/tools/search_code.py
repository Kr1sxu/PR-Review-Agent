
"""
Search Code Tool - PR-Review Agent
Keyword/regex search in repository files (read-only)
"""

import os
import re
from typing import Any

from agentscope.tool._base import ToolBase
from agentscope.tool._response import ToolChunk, ToolResultState
from agentscope.message._block import TextBlock
from agentscope.permission._decision import PermissionDecision
from agentscope.permission._types import PermissionBehavior
from agentscope.permission._context import PermissionContext


class SearchCodeTool(ToolBase):
    """Search code by keyword or regex pattern (read-only)"""

    name: str = "search_code"
    description: str = (
        "Search for a keyword or regex pattern in repository files. "
        "Returns matching lines with file paths and line numbers."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Search keyword or regex pattern"},
            "directory": {"type": "string", "description": "Directory to search in", "default": "."},
            "file_pattern": {"type": "string", "description": "File extension filter, e.g. .py", "default": ""},
            "max_results": {"type": "integer", "description": "Max results to return", "default": 50},
        },
        "required": ["keyword"],
    }
    is_read_only: bool = True
    is_concurrency_safe: bool = True

    async def check_permissions(
        self, tool_input: dict[str, Any], context: PermissionContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Read-only code search allowed",
        )

    async def call(self, keyword: str, directory: str = ".", file_pattern: str = "",
                   max_results: int = 50, **kwargs) -> ToolChunk:
        try:
            pattern = re.compile(keyword, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)

        results = []
        dir_path = os.path.realpath(directory)
        if not os.path.isdir(dir_path):
            return ToolChunk(
                content=[TextBlock(text=f"Error: Directory not found: {directory}")],
                state=ToolResultState.ERROR,
            )

        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       {"__pycache__", "node_modules", ".git", "venv", ".venv"}]
            for fname in files:
                if file_pattern and not fname.endswith(file_pattern):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, 1):
                            if pattern.search(line):
                                rel = os.path.relpath(fpath, dir_path)
                                results.append(f"{rel}:{lineno}: {line.rstrip()}")
                                if len(results) >= max_results:
                                    break
                except (OSError, UnicodeDecodeError):
                    continue
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

        if not results:
            text = f"No matches found for '{keyword}'"
        else:
            text = f"Found {len(results)} match(es):\n" + "\n".join(results)
        return ToolChunk(content=[TextBlock(text=text)], state=ToolResultState.SUCCESS)

