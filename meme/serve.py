"""Serve command — starts the meme sharing server."""
from __future__ import annotations

from pathlib import Path


def cmd_serve(port: int = 9876, directory: str | None = None,
              seed_url: str | None = None) -> int:
    """Start or seed a meme sharing server."""
    from server import seed as _seed, serve as _serve

    if seed_url:
        memes_dir = Path(directory) if directory else None
        _seed(seed_url, memes_dir=memes_dir)
        return 0

    _serve(port=port, directory=directory)
    return 0  # unreachable (_serve loops forever)
