#!/usr/bin/env python3
"""
Meme Collection TUI — wrapper that opens ``meme pick`` in a dedicated terminal.

Usage:
    meme tui

Opens a terminal window (foot/kitty/alacritty/...) with fzf + chafa for
browsing memes, matching the appearance of a standalone TUI app.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _detect_terminal() -> str | None:
    """Return path to a known terminal emulator, or None."""
    for term in ("foot", "kitty", "alacritty", "gnome-terminal",
                 "konsole", "xfce4-terminal", "wezterm"):
        path = shutil.which(term)
        if path:
            return path
    return None


def run() -> int:
    """Open a terminal window running ``meme pick``."""
    # Find the meme binary (pipx entry point or fallback to argv[0])
    meme_bin = shutil.which("meme")
    if not meme_bin:
        meme_bin = sys.argv[0]

    terminal = _detect_terminal()
    if not terminal:
        print("Error: no terminal emulator found (install foot, kitty, etc.)",
              file=sys.stderr)
        return 1

    # Build command — foot-compatible flags as default
    cmd: list[str] = []

    term_name = shutil.which("foot")
    if term_name and terminal == term_name:
        # Foot: set app-id for window-rule matching + title
        cmd = [terminal,
               "--app-id=meme-picker",
               "--title=Meme Collection",
               meme_bin, "pick"]
    elif "kitty" in terminal:
        cmd = [terminal, "--title=Meme Collection", meme_bin, "pick"]
    elif "alacritty" in terminal:
        cmd = [terminal, "--title", "Meme Collection", "-e", meme_bin, "pick"]
    elif "gnome-terminal" in terminal:
        cmd = [terminal, "--", meme_bin, "pick"]
    elif "konsole" in terminal:
        cmd = [terminal, "--title", "Meme Collection", "-e", meme_bin, "pick"]
    elif "xfce4-terminal" in terminal:
        cmd = [terminal, "--title", "Meme Collection", "-e", meme_bin, "pick"]
    else:
        # Fallback: just run in whatever terminal
        cmd = [terminal, meme_bin, "pick"]

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
