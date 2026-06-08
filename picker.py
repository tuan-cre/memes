#!/usr/bin/env python3
"""
Meme Collection Picker — cross-platform wrapper that opens ``meme pick`` in a
dedicated terminal window, giving the feel of a standalone picker app.

Usage:
    meme picker

Platform behaviour:
    Linux   — detects foot → kitty → alacritty → gnome-terminal → …
    macOS   — opens Terminal.app via osascript
    Windows — opens cmd.exe or Windows Terminal
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _find_meme() -> str:
    """Return path to the ``meme`` executable."""
    exe = shutil.which("meme")
    if exe:
        return exe
    # Fallback: assume we're running from the repo
    return sys.argv[0]


# ── Linux ────────────────────────────────────────────────────────────────────

_LINUX_TERMINALS: list[tuple[str, list[str]]] = [
    ("foot", ["--app-id=meme-picker", "--title=Meme Collection"]),
    ("kitty", ["--title", "Meme Collection"]),
    ("alacritty", ["--title", "Meme Collection", "-e"]),
    ("gnome-terminal", ["--"]),
    ("konsole", ["--title", "Meme Collection", "-e"]),
    ("xfce4-terminal", ["--title", "Meme Collection", "-e"]),
    ("wezterm", ["start", "--"]),
    ("st", ["-e"]),
    ("urxvt", ["-e"]),
    ("xterm", ["-e"]),
]


def _run_linux(meme_bin: str) -> int:
    for exe, args in _LINUX_TERMINALS:
        path = shutil.which(exe)
        if not path:
            continue
        cmd = [path, *args, meme_bin, "pick"]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return 0
        except FileNotFoundError:
            continue
    print("Error: no terminal emulator found (install foot, kitty, etc.)",
          file=sys.stderr)
    return 1


# ── macOS ────────────────────────────────────────────────────────────────────

def _run_macos(meme_bin: str) -> int:
    script = (
        'tell application "Terminal"\n'
        '    activate\n'
        f'    do script "{meme_bin} pick; exit"\n'
        'end tell'
    )
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return 0
    except FileNotFoundError:
        print("Error: osascript not found (unexpected on macOS)", file=sys.stderr)
        return 1


# ── Windows ──────────────────────────────────────────────────────────────────

def _run_windows(meme_bin: str) -> int:
    # Prefer Windows Terminal if available
    wt = shutil.which("wt")
    if wt:
        try:
            cmd = [wt, "-w", "0", "nt", "cmd", "/c", meme_bin, "pick"]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return 0
        except FileNotFoundError:
            pass

    # Fallback: cmd.exe
    try:
        cmd = ["cmd", "/c", "start", "Meme Collection", meme_bin, "pick"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    except FileNotFoundError:
        print("Error: cmd.exe not found (unexpected on Windows)", file=sys.stderr)
        return 1


# ── Entry point ──────────────────────────────────────────────────────────────

def run() -> int:
    """Open a terminal window running ``meme pick``."""
    meme_bin = _find_meme()
    platform = sys.platform

    if platform == "linux":
        return _run_linux(meme_bin)
    if platform == "darwin":
        return _run_macos(meme_bin)
    if platform == "win32":
        return _run_windows(meme_bin)

    print(f"Error: unsupported platform '{platform}'", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(run())
