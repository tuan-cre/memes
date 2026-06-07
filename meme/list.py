"""List commands and meme data helpers."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from meme.config import MEME_DIR
from meme.platform import _notify
from meme.server_client import _server_get


# ── Data helpers ──────────────────────────────────────────────────────────────


def _list_memes() -> list[dict]:
    """Return sorted list of local memes with metadata."""
    MEME_DIR.mkdir(parents=True, exist_ok=True)
    memes: list[dict] = []
    for f in sorted(MEME_DIR.iterdir()):
        if f.suffix.lower() != ".png" or not f.is_file():
            continue
        name = f.stem
        display = name
        ts = None
        if name.startswith("meme_") and name[5:].isdigit():
            ts = int(name[5:])
            display = datetime.fromtimestamp(ts).strftime("%b %d %H:%M")
        memes.append({
            "filename": f.name,
            "path": f,
            "name": name,
            "display": display,
            "timestamp": ts,
            "size": f.stat().st_size,
        })
    return memes


def _resolve_path(name: str) -> Path:
    """Return absolute path to a meme by name, searching MEME_DIR."""
    p = Path(name)
    if p.is_absolute() and p.exists():
        return p
    return MEME_DIR / name


def _format_size(size: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _format_remote_time(ts: float | None) -> str:
    if ts:
        return datetime.fromtimestamp(ts).strftime("%b %d %H:%M")
    return ""


# ── Table rendering ───────────────────────────────────────────────────────────


def _render_meme_table(memes: list[dict]) -> None:
    """Display a list of meme dicts (local or remote) as a table."""
    if not memes:
        print("No memes on server!")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Date")
        table.add_column("Filename", style="dim")
        table.add_column("Size")
        for m in memes:
            modified = _format_remote_time(m.get("modified"))
            table.add_row(modified, m["filename"],
                          _format_size(m["size"]))
        console.print(table)
    except ImportError:
        print(f"{'Date':<16} {'Filename':<30} {'Size':<8}")
        print("-" * 56)
        for m in memes:
            modified = _format_remote_time(m.get("modified"))
            print(f"{modified:<16} {m['filename']:<30} {_format_size(m['size']):<8}")


# ── Commands ──────────────────────────────────────────────────────────────────


def cmd_list() -> int:
    """List all memes (tries server first, falls back to local)."""
    remote = _server_get("memes")
    if remote is not None:
        _render_meme_table(list(remote))
        return 0

    memes = _list_memes()
    if not memes:
        _notify("Meme Collection", "No memes yet!")
        return 0

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
        console = Console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Date")
        table.add_column("Filename", style="dim")
        table.add_column("Size")
        for m in memes:
            table.add_row(m["display"], m["filename"],
                          _format_size(m["size"]))
        console.print(table)
    except ImportError:
        print(f"{'Date':<16} {'Filename':<30} {'Size':<8}")
        print("-" * 56)
        for m in memes:
            print(f"{m['display']:<16} {m['filename']:<30} {_format_size(m['size']):<8}")
    return 0
