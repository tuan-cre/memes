"""Interactive fzf picker (local + remote) — cmd_pick and cmd_list_tsv."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from meme.config import MEME_DIR, _load_config
from meme.platform import _debug, _notify, _tool_available
from meme.server_client import _server_get, _server_get_file
from meme.list import _list_memes, _format_remote_time


def cmd_list_tsv() -> int:
    """Tab-separated output for fzf input.  Tries server first, falls back to local."""
    remote = _server_get("memes")
    if remote is not None:
        for m in list(remote):
            print(f"{m.get('display', m['filename'])}\t{m['filename']}")
        return 0
    for m in _list_memes():
        print(f"{m['display']}\t{m['filename']}")
    return 0


def cmd_pick() -> int:
    """Interactive meme browser via fzf (local or remote)."""
    if not _tool_available("fzf"):
        print("Error: fzf is required (install via your package manager)", file=sys.stderr)
        return 1

    color = (
        "bg:#050508,bg+:#282838,fg:#d8d8d8,fg+:#ffffff,"
        "hl:#b48ead,hl+:#c7a0c8,pointer:#c7a0c8,info:#5c5c6e,"
        "spinner:#5c5c6e,header:#b48ead,prompt:#b48ead,"
        "border:#5c5c6e,marker:#c7a0c8"
    )
    self_path = Path(sys.argv[0]).resolve()

    # ── Try remote mode ──────────────────────────────────────────────────
    remote_memes = _server_get("memes")
    if remote_memes is not None:
        memes: list[dict] = list(remote_memes)  # type: ignore[assignment]
        if not memes:
            _notify("Meme Collection", "No memes on server!")
            return 0

        input_lines = "\n".join(
            f"{m.get('display', m['filename'])}\t{m['filename']}"
            for m in memes
        )
        server_url = _load_config()['server_url'].rstrip('/')

        if _tool_available("chafa"):
            preview = (
                "mkdir -p /tmp/meme-cache; "
                f"cache='/tmp/meme-cache/{{2}}'; "
                f"[ -f \"$cache\" ] || curl -s -o \"$cache\" "
                f"'{server_url}/api/memes/'{{2}}; "
                f"chafa --symbols=block --fill=block --scale max --align=mid,mid "
                f"--size=${{FZF_PREVIEW_COLUMNS}}x$(( ${{FZF_PREVIEW_LINES}} - 2 )) "
                f"\"$cache\" 2>/dev/null; "
                f"echo '  {{2}}'"
            )
        else:
            preview = (
                f"echo '  {{2}}' && echo && echo 'Select to download and open'"
            )

        fzf = _run_fzf(input_lines, preview, "  MEME COLLECTION (SERVER)  ", color, self_path,
                        preview_window="right:60%:border-rounded",
                        ctrl_p_path="/tmp/meme-cache")
        result, _ = fzf.communicate(input=input_lines)

        if fzf.returncode != 0 or not result.strip():
            return 0

        filename = result.strip().split("\t")[-1]
        # Download to temp and copy to clipboard
        tmp = Path(tempfile.mkstemp(suffix=".png")[1])
        if not _server_get_file(f"memes/{filename}", tmp):
            print(f"Error: could not download {filename}", file=sys.stderr)
            return 1

        # Open with image viewer
        for viewer in ("imv", "feh", "sxiv", "xdg-open"):
            if _tool_available(viewer):
                subprocess.Popen([viewer, str(tmp)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break

        # Copy to clipboard
        from meme.clipboard import _copy_image
        if _copy_image(tmp):
            _notify("Meme Collection", f"Copied from server: {filename}", icon=tmp)
        else:
            print(f"Downloaded: {tmp}")
        return 0

    # ── Local mode ───────────────────────────────────────────────────────
    memes = _list_memes()
    if not memes:
        _notify("Meme Collection", "No memes yet!")
        return 0

    input_lines = "\n".join(f"{m['display']}\t{m['filename']}" for m in memes)

    if _tool_available("chafa"):
        preview = (
            "chafa --symbols=block --fill=block --scale max --align=mid,mid "
            "--size=${FZF_PREVIEW_COLUMNS}x$(( ${FZF_PREVIEW_LINES} - 2 )) "
            f"'{MEME_DIR}/" "{2}'"
        )
    else:
        preview = (f"cd '{MEME_DIR}' && echo {{2}} && file {{2}} && echo && "
                   "stat --printf='Size: %s\\n' {{2}} 2>/dev/null || "
                   "stat -f 'Size: %z' {{2}} 2>/dev/null; echo; echo "
                   "'Install chafa for image previews (brew install chafa)'")

    fzf = _run_fzf(input_lines, preview, "  MEME COLLECTION  ", color, self_path,
                    ctrl_p_path=str(MEME_DIR))
    result, _ = fzf.communicate(input=input_lines)

    if fzf.returncode != 0 or not result.strip():
        return 0

    selected = result.strip()
    filename = selected.split("\t")[-1]
    display = selected.split("\t")[0]
    filepath = MEME_DIR / filename

    if not filepath.exists():
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        return 1

    from meme.clipboard import _copy_image
    if _copy_image(filepath):
        _notify("Meme Collection", f"Copied: {display}", icon=filepath)
    else:
        print(f"Saved at: {filepath}")
    return 0


# ── Fzf launcher (shared between remote and local) ───────────────────────────


def _run_fzf(
    input_lines: str,
    preview: str,
    header: str,
    color: str,
    self_path: Path,
    preview_window: str = "right:80%:border-rounded:wrap",
    ctrl_p_path: str = "",
) -> subprocess.Popen:
    """Launch fzf with shared options."""
    binds = [
        "--bind", f"ctrl-p:execute(imv '{ctrl_p_path}/" "{2}' 2>/dev/null)+abort",
        "--bind", f"ctrl-d:execute({self_path} trash " "{2})+reload("
                  f"{self_path} _list-tsv)",
        "--bind", f"ctrl-r:execute({self_path} rename " "{2})+reload("
                  f"{self_path} _list-tsv)",
    ]

    return subprocess.Popen(
        [
            "fzf",
            "--delimiter", "\t",
            "--with-nth", "1",
            "--preview", preview,
            "--preview-window", preview_window,
            "--layout=reverse",
            "--border=rounded",
            "--header", header,
            "--prompt", "▸ ",
            "--color", color,
            "--height=100%",
            "--no-info",
            *binds,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
