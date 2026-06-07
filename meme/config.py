"""Application paths and configuration."""
from __future__ import annotations

import json
from pathlib import Path

MEME_DIR = Path.home() / ".local/share/memes"
TRASH_DIR = MEME_DIR / ".trash"
CONFIG_DIR = Path.home() / ".config/memes"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_config() -> dict:
    """Load JSON config.  Returns {} if missing or broken."""
    try:
        with open(CONFIG_FILE) as f:
            return dict(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}
