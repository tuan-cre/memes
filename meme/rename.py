"""Rename command — local + server."""
from __future__ import annotations

from pathlib import Path

from meme.config import MEME_DIR
from meme.platform import _notify
from meme.server_client import _server_put
from meme.list import _resolve_path


def cmd_rename(name: str) -> int:
    """Rename a meme interactively (local + server if configured)."""
    filepath = _resolve_path(name)

    try:
        raw = input("New name: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        _notify("Meme Collection", "Rename cancelled")
        return 0

    if not raw:
        _notify("Meme Collection", "Rename cancelled")
        return 0

    raw = raw.replace("/", "_").replace(" ", "_")

    # Rename on server if configured (works even if file not local)
    server_result = _server_put(f"memes/{name}:{raw}.png")
    if server_result is not None:
        _notify("Meme Collection", f"Renamed on server → {raw}.png")
        return 0

    # Fall back to local rename
    if not filepath.exists():
        _notify("Meme Collection", f"File not found: {filepath.name}")
        return 1

    new_path = filepath.with_name(f"{raw}.png")
    if new_path.exists():
        print(f"Error: {new_path.name} already exists", file=sys.stderr)
        return 1

    filepath.rename(new_path)
    _notify("Meme Collection", f"Renamed → {new_path.name}", icon=new_path)
    return 0
