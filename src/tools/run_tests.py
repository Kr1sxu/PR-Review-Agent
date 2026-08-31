
"""
Run Tests Tool - PR-Review Agent
Execute test commands (DISABLED by default)
"""

import subprocess
from typing import Any

from agentscope.tool._base import ToolBase
from agentscope.tool._response import ToolChunk, ToolResultState
from agentscope.message._block import TextBlock
from agentscope.permission._decision import PermissionDecision
from agentscope.permission._types import PermissionBehavior
from agentscope.permission._context import PermissionContext


class RunTestsTool(ToolBase):
    """Execute test commands (disabled by default)"""

    name: str = "run_tests"
    description: str = (
        "Run a test command in the repository. "
        "DISABLED by default for security."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Test command to execute"},
            "cwd": {"type": "string", "description": "Working directory", "default": "."},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
        },
        "required": ["command"],
    }
    is_read_only: bool = False
    is_concurrency_safe: bool = False

    def __init__(self, enabled: bool = False, allowed_commands: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.enabled = enabled
        self.allowed_commands = allowed_commands or []

    async def check_permissions(
        self, tool_input: dict[str, Any], context: PermissionContext
    ) -> PermissionDecision:
        if not self.enabled:
            return PermissionDecision(
                behavior=PermissionBehavior.DENY,
                message="Run tests is DISABLED for security",
            )
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Test execution allowed",
        )

    async def call(self, command: str, cwd: str = ".", timeout: int = 60, **kwargs) -> ToolChunk:
        if not self.enabled:
            return ToolChunk(
                content=[TextBlock(text="Run tests is DISABLED for security.")],
                state=ToolResultState.DENIED,
            )
        if self.allowed_commands:
            cmd_start = command.strip().split()[0] if command.strip() else ""
            if cmd_start not in self.allowed_commands:
                return ToolChunk(
                    content=[TextBlock(text=f"Command \'{cmd_start}\' not in allowed list")],
                    state=ToolResultState.DENIED,
                )
        try:
            result = subprocess.run(
                command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            )
            output = f"Exit code: {result.returncode}\n"
            if result.stdout:
                output += f"STDOUT:\n{result.stdout[-3000:]}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr[-2000:]}\n"
            state = ToolResultState.SUCCESS if result.returncode == 0 else ToolResultState.ERROR
            return ToolChunk(content=[TextBlock(text=output)], state=state)
        except subprocess.TimeoutExpired:
            return ToolChunk(content=[TextBlock(text=f"Command timed out after {timeout}s")], state=ToolResultState.ERROR)
        except Exception as e:
            return ToolChunk(content=[TextBlock(text=f"Error: {e}")], state=ToolResultState.ERROR)
