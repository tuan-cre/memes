#!/usr/bin/env python3
"""Install Meme Collection — cross-platform bootstrap script.

Usage:
    python3 install.py              # Install locally (~/.local/bin/)
    python3 install.py --global     # Install system-wide (may need sudo/admin)
    python3 install.py --user       # Install into user site-packages (pip)

Detects your OS and installs dependencies where possible.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


def main():
    install_global = "--global" in sys.argv
    install_user = "--user" in sys.argv or not install_global

    print("=" * 50)
    print("  Meme Collection — Cross-platform Installer")
    print("=" * 50)
    print()

    # ── Check Python ──────────────────────────────────────────────
    if sys.version_info < (3, 10):
        print("Error: Python 3.10+ required", file=sys.stderr)
        sys.exit(1)

    # ── Locate source files ────────────────────────────────────────
    src = Path(__file__).resolve().parent
    cli_src = src / "meme.py"
    if not cli_src.exists():
        print(f"Error: {cli_src} not found. Run install.py from the repo root.", file=sys.stderr)
        sys.exit(1)

    # ── Install Python deps ────────────────────────────────────────
    print("[1/4] Installing Python dependencies...")
    pip_args = [sys.executable, "-m", "pip", "install", "--quiet"]
    if install_user and not install_global:
        pip_args.append("--user")
    # Also offer installing from GitHub
    print("  Or install directly from GitHub:")
    print("  pip install git+https://github.com/tuan-cre/memes.git")
    pip_args.append(str(src))  # local package install

    try:
        subprocess.run(pip_args, check=True)
    except subprocess.CalledProcessError:
        print("Warning: pip install failed, trying without --quiet...")
        subprocess.run(pip_args[:-1] + ["--no-quiet", str(src)], check=False)

    # ── Install optional extras ────────────────────────────────────
    print("[2/4] Installing optional extras (mss, plyer)...")
    extras = ["mss", "plyer"]
    for pkg in extras:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pkg],
            check=False,
        )

    # ── System tool: fzf ───────────────────────────────────────────
    print("[3/4] Checking system dependencies...")
    check_fzf()

    # ── Create meme directory ──────────────────────────────────────
    print("[4/4] Creating meme collection directory...")
    meme_dir = Path.home() / ".local/share/memes"
    meme_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Created: {meme_dir}")

    # ── Done ───────────────────────────────────────────────────────
    print()
    print("=" * 50)
    print("  Installation complete!")
    print("=" * 50)
    print()
    print("  Run: meme --help")
    print()
    print("  To capture from your browser, also run:")
    print(f"    {src / 'setup-browser.sh'}")
    print()


def check_fzf():
    """Check if fzf is available, offer to install."""
    if shutil.which("fzf"):
        print("  fzf: found")
        return

    print("  fzf: not found")
    system = sys.platform

    if system == "linux":
        if shutil.which("apt"):
            print("  Install: sudo apt install fzf")
        elif shutil.which("pacman"):
            print("  Install: sudo pacman -S fzf")
        elif shutil.which("dnf"):
            print("  Install: sudo dnf install fzf")
        elif shutil.which("brew"):
            print("  Install: brew install fzf")
        else:
            print("  Install fzf via your package manager")
    elif system == "darwin":
        if shutil.which("brew"):
            ans = input("  Install fzf via Homebrew? [Y/n] ").strip().lower()
            if ans in ("", "y", "yes"):
                subprocess.run(["brew", "install", "fzf"], check=False)
        else:
            print("  Install: brew install fzf")
    elif system == "win32":
        if shutil.which("scoop"):
            ans = input("  Install fzf via Scoop? [Y/n] ").strip().lower()
            if ans in ("", "y", "yes"):
                subprocess.run(["scoop", "install", "fzf"], check=False)
        elif shutil.which("winget"):
            ans = input("  Install fzf via winget? [Y/n] ").strip().lower()
            if ans in ("", "y", "yes"):
                subprocess.run(["winget", "install", "fzf"], check=False)
        else:
            print("  Install: scoop install fzf")
    else:
        print("  Please install fzf manually: https://github.com/junegunn/fzf")


if __name__ == "__main__":
    main()
