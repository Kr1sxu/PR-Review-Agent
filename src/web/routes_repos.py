"""
Repository Browser API Routes - PR-Review Agent
GET /api/repos - list demo repos
GET /api/repos/files?path=... - list files in a directory
GET /api/repos/commits?repo=... - list recent git commits
GET /api/repos/file?repo=...&path=... - read file content
"""

import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["repos"])

# Default repos root: project/demo directory
_DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"


def _safe_path(base: Path, user_path: str) -> Path:
    """Resolve path and ensure it stays within base directory."""
    resolved = (base / user_path).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    return resolved


@router.get("/repos")
async def list_repos():
    """List available demo repositories."""
    repos = []
    if _DEMO_DIR.exists():
        for d in sorted(_DEMO_DIR.iterdir()):
            if d.is_dir():
                py_count = len(list(d.glob("*.py")))
                repos.append({
                    "name": d.name,
                    "path": str(d),
                    "file_count": py_count,
                })
    return {"repos": repos}


@router.get("/repos/files")
async def list_files(path: str = Query("", description="Relative path within repo")):
    """List files in a directory. If path is empty, list repo root files."""
    if not path:
        # List all repos as directories
        items = []
        if _DEMO_DIR.exists():
            for d in sorted(_DEMO_DIR.iterdir()):
                if d.is_dir():
                    items.append({"name": d.name, "type": "dir", "path": d.name})
        return {"items": items, "current_path": ""}

    # Handle both absolute paths and relative paths
    user_path = Path(path)
    if user_path.is_absolute() and user_path.exists():
        target = user_path
        # Ensure it's under DEMO_DIR
        if not str(target.resolve()).startswith(str(_DEMO_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        target = _safe_path(_DEMO_DIR, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if target.is_file():
        return {"items": [{"name": target.name, "type": "file", "path": path}], "current_path": path}

    items = []
    for f in sorted(target.iterdir()):
        if f.name.startswith(".") or f.name == "__pycache__":
            continue
        items.append({
            "name": f.name,
            "type": "dir" if f.is_dir() else "file",
            "path": str(f.relative_to(target)),
        })
    return {"items": items, "current_path": path}


@router.get("/repos/commits")
async def list_commits(repo: str = Query(..., description="Repo path")):
    """List recent git commits for a repo."""
    import subprocess
    repo_path = Path(repo).resolve()
    if not (repo_path / ".git").exists():
        # Try as relative to demo dir
        repo_path = _DEMO_DIR / repo
    if not (repo_path / ".git").exists():
        return {"commits": [], "message": "Not a git repository"}

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-20", "--format=%H|%s|%ai|%an"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"commits": []}

        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 3)
                if len(parts) >= 3:
                    commits.append({
                        "hash": parts[0][:8],
                        "full_hash": parts[0],
                        "message": parts[1],
                        "date": parts[2][:19] if len(parts) > 2 else "",
                        "author": parts[3] if len(parts) > 3 else "",
                    })
        return {"commits": commits}
    except Exception as e:
        return {"commits": [], "error": str(e)}


@router.get("/repos/file")
async def read_file(repo: str = Query(...), path: str = Query(...)):
    """Read a file's content from a repo."""
    # Try as absolute path first, then as relative to DEMO_DIR
    repo_path = Path(repo)
    if repo_path.is_absolute() and repo_path.exists():
        pass  # use as-is
    elif (_DEMO_DIR / repo).exists():
        repo_path = _DEMO_DIR / repo
    else:
        repo_path = Path(repo).resolve()
    if not repo_path.exists():
        raise HTTPException(status_code=404, detail="Repository not found")

    file_path = _safe_path(repo_path, path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = file_path.read_text(encoding="utf-8")
        return PlainTextResponse(content)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not a text file")
