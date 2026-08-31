"""
Git Ops Tool - PR-Review Agent
Read-only git operations, registered as AgentScope Tool.
Replaces the former git_ops.py + git_ops_tool.py split.
"""

import subprocess
from pathlib import Path
from typing import Any, List

from agentscope.tool._base import ToolBase
from agentscope.tool._response import ToolChunk, ToolResultState
from agentscope.message._block import TextBlock
from agentscope.permission._decision import PermissionDecision
from agentscope.permission._types import PermissionBehavior
from agentscope.permission._context import PermissionContext


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------

class GitOpsError(Exception):
    pass


class RepoNotFoundError(GitOpsError):
    pass


class CommitNotFoundError(GitOpsError):
    pass


# ---------------------------------------------------------------------------
# GitOps - low-level git operations (used by flows, task_manager, etc.)
# ---------------------------------------------------------------------------

class GitOps:
    """Read-only git operations: diff, file content, changed files.
    Supports commit hash, branch name, HEAD~N.
    """

    def __init__(self, repo_path: str = "."):
        self._repo_path = Path(repo_path).resolve()
        self._validate_repo()

    def _validate_repo(self):
        if not (self._repo_path / ".git").exists():
            raise RepoNotFoundError(f"Not a git repo: {self._repo_path}")

    def _run_git(self, args: List[str]) -> str:
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd, cwd=str(self._repo_path), capture_output=True,
                text=True, timeout=30, encoding="utf-8",
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if "unknown revision" in stderr or "bad object" in stderr:
                    raise CommitNotFoundError(f"Invalid ref: {stderr}")
                raise GitOpsError(f"Git error: {stderr}")
            return result.stdout.strip()
        except FileNotFoundError:
            raise GitOpsError("Git not found in PATH")
        except subprocess.TimeoutExpired:
            raise GitOpsError("Git command timed out")

    def get_diff(self, base_commit: str, target_commit: str) -> str:
        return self._run_git(["diff", base_commit, target_commit])

    def get_file_content(self, commit: str, filepath: str) -> str:
        return self._run_git(["show", f"{commit}:{filepath}"])

    def list_changed_files(self, base_commit: str, target_commit: str) -> List[str]:
        output = self._run_git(["diff", "--name-only", base_commit, target_commit])
        return [l.strip() for l in output.split("\n") if l.strip()] if output else []

    def get_commit_message(self, commit: str) -> str:
        return self._run_git(["log", "-1", "--format=%s", commit])

    def get_commit_hash(self, ref: str) -> str:
        return self._run_git(["rev-parse", ref])

    def is_valid_ref(self, ref: str) -> bool:
        try:
            self.get_commit_hash(ref)
            return True
        except (CommitNotFoundError, GitOpsError):
            return False


# ---------------------------------------------------------------------------
# GitOpsTool - AgentScope tool wrapper
# ---------------------------------------------------------------------------

class GitOpsTool(ToolBase):
    """Read-only git operations: diff, changed files, file content, commit info."""

    name: str = "git_ops"
    description: str = (
        "Perform read-only git operations on the repository. "
        "Supported actions: "
        "'diff' (get code diff between two refs), "
        "'list_files' (list changed files between two refs), "
        "'file_content' (get file content at a specific commit), "
        "'commit_message' (get commit message for a ref)."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["diff", "list_files", "file_content", "commit_message"],
                "description": "Git operation to perform",
            },
            "base_ref": {
                "type": "string",
                "description": "Base commit/branch/ref (used by diff, list_files)",
            },
            "target_ref": {
                "type": "string",
                "description": "Target commit/branch/ref (used by diff, list_files)",
            },
            "commit": {
                "type": "string",
                "description": "Commit ref (used by file_content, commit_message)",
            },
            "file_path": {
                "type": "string",
                "description": "File path (used by file_content)",
            },
        },
        "required": ["action"],
    }
    is_read_only: bool = True
    is_concurrency_safe: bool = True

    def __init__(self, repo_path: str = ".", **kwargs):
        super().__init__(**kwargs)
        self._repo_path = repo_path

    async def check_permissions(
        self, tool_input: dict[str, Any], context: PermissionContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Read-only git operations allowed",
        )

    async def call(
        self,
        action: str,
        base_ref: str = "",
        target_ref: str = "",
        commit: str = "",
        file_path: str = "",
        **kwargs,
    ) -> ToolChunk:
        try:
            git = GitOps(self._repo_path)
        except GitOpsError as e:
            return ToolChunk(
                content=[TextBlock(text=f"Git repo error: {e}")],
                state=ToolResultState.ERROR,
            )

        try:
            if action == "diff":
                if not base_ref or not target_ref:
                    return ToolChunk(
                        content=[TextBlock(text="Error: diff requires base_ref and target_ref")],
                        state=ToolResultState.ERROR,
                    )
                result = git.get_diff(base_ref, target_ref)
                if len(result) > 10000:
                    result = result[:10000] + "\n... (truncated, diff too large)"
                return ToolChunk(
                    content=[TextBlock(text=result or "No differences found.")],
                    state=ToolResultState.SUCCESS,
                )

            elif action == "list_files":
                if not base_ref or not target_ref:
                    return ToolChunk(
                        content=[TextBlock(text="Error: list_files requires base_ref and target_ref")],
                        state=ToolResultState.ERROR,
                    )
                files = git.list_changed_files(base_ref, target_ref)
                if not files:
                    text = "No changed files found."
                else:
                    text = f"Changed files ({len(files)}):\n" + "\n".join(files)
                return ToolChunk(
                    content=[TextBlock(text=text)],
                    state=ToolResultState.SUCCESS,
                )

            elif action == "file_content":
                if not commit or not file_path:
                    return ToolChunk(
                        content=[TextBlock(text="Error: file_content requires commit and file_path")],
                        state=ToolResultState.ERROR,
                    )
                result = git.get_file_content(commit, file_path)
                return ToolChunk(
                    content=[TextBlock(text=result)],
                    state=ToolResultState.SUCCESS,
                )

            elif action == "commit_message":
                if not commit:
                    return ToolChunk(
                        content=[TextBlock(text="Error: commit_message requires commit")],
                        state=ToolResultState.ERROR,
                    )
                result = git.get_commit_message(commit)
                return ToolChunk(
                    content=[TextBlock(text=result or "No commit message found.")],
                    state=ToolResultState.SUCCESS,
                )

            else:
                return ToolChunk(
                    content=[TextBlock(text=f"Error: Unknown action '{action}'. Use: diff, list_files, file_content, commit_message")],
                    state=ToolResultState.ERROR,
                )

        except GitOpsError as e:
            return ToolChunk(
                content=[TextBlock(text=f"Git error: {e}")],
                state=ToolResultState.ERROR,
            )
        except Exception as e:
            return ToolChunk(
                content=[TextBlock(text=f"Unexpected error: {e}")],
                state=ToolResultState.ERROR,
            )
