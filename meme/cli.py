"""CLI entry point — parser, dispatch, main()."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from meme.platform import _DEBUG


def main() -> None:
    argv = sys.argv[1:]
    prog = Path(sys.argv[0]).stem  # e.g. "meme", "meme-pick", "meme-capture"

    # Legacy name → command mapping (so symlinks/wrappers still work)
    legacy: dict[str, str] = {
        "meme-pick": "pick",
        "meme-list": "list",
        "meme-capture": "capture",
        "meme-from-clip": "from-clip",
        "meme-rename": "rename",
        "meme-trash": "trash",
        "meme-native-host": "native-host",
    }

    if prog in legacy:
        # Called as e.g. "meme-pick" — insert the subcommand
        argv = [legacy[prog]] + ([" ".join(argv)] if prog in ("rename", "trash") else argv)

    parser = _build_parser()
    args = parser.parse_args(argv)

    exit(_run(args))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="meme", description="Meme Collection CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all memes")
    sub.add_parser("pick", help="Interactive browser (requires fzf + chafa)")

    cp = sub.add_parser("capture", help="Capture screen region")
    cp.add_argument("-m", "--monitor", type=int, default=None,
                    help="Monitor index to capture (1-indexed, default: primary)")
    cp.add_argument("-d", "--debug", action="store_true",
                    help="Print debug diagnostics to stderr")

    sub.add_parser("from-clip", help="Save clipboard image")

    rn = sub.add_parser("rename", help="Rename a meme")
    rn.add_argument("file", help="Filename to rename")

    tr = sub.add_parser("trash", help="Move meme to .trash/")
    tr.add_argument("file", help="Filename to trash")

    sv = sub.add_parser("serve", help="Start meme sharing server")
    sv.add_argument("--port", type=int, default=9876,
                    help="Port to listen on (default: 9876)")
    sv.add_argument("--dir", default=None,
                    help="Memes directory (default: ~/.local/share/memes)")
    sv.add_argument("--seed", metavar="SERVER_URL",
                    help="Upload local memes to existing server and exit")

    sub.add_parser("native-host", help="Native messaging host (browser extension)")
    sub.add_parser("_list-tsv", help=argparse.SUPPRESS)

    return p


def _run(args: argparse.Namespace) -> int:
    # Enable debug mode before dispatching
    if getattr(args, "debug", False):
        global _DEBUG
        _DEBUG = True

    from meme.list import cmd_list
    from meme.pick import cmd_pick, cmd_list_tsv
    from meme.capture import cmd_capture
    from meme.clipboard import cmd_from_clip
    from meme.rename import cmd_rename
    from meme.trash import cmd_trash
    from meme.serve import cmd_serve
    from meme.native_host import cmd_native_host

    dispatch: dict[str, Callable[..., int]] = {
        "list": cmd_list,
        "_list-tsv": cmd_list_tsv,
        "pick": cmd_pick,
        "capture": lambda: cmd_capture(monitor=args.monitor),
        "from-clip": cmd_from_clip,
        "rename": lambda: cmd_rename(args.file),
        "trash": lambda: cmd_trash(args.file),
        "serve": lambda: cmd_serve(args.port, args.dir, args.seed),
        "native-host": cmd_native_host,
    }
    handler = dispatch.get(args.command)
    if handler:
        return handler()
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1
