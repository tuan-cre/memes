"""Trash command — local + server."""
from __future__ import annotations

from meme.config import MEME_DIR, TRASH_DIR
from meme.platform import _notify
from meme.server_client import _server_delete
from meme.list import _resolve_path


def cmd_trash(name: str) -> int:
    """Move a meme to .trash/ (local + server if configured)."""
    filepath = _resolve_path(name)

    # Delete on server if configured (works even if file not local)
    server_result = _server_delete(f"memes/{name}")
    if server_result is not None:
        # Also trash locally if file exists
        if filepath.exists():
            TRASH_DIR.mkdir(parents=True, exist_ok=True)
            dest = TRASH_DIR / filepath.name
            filepath.rename(dest)
        _notify("Meme Collection", f"Trashed: {name}")
        return 0

    # Fall back to local trash
    if not filepath.exists():
        _notify("Meme Collection", f"File not found: {filepath.name}")
        return 1

    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    dest = TRASH_DIR / filepath.name
    filepath.rename(dest)
    _notify("Meme Collection", f"Trashed: {name}", icon=filepath)
    return 0
