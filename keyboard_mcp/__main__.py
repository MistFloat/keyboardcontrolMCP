from __future__ import annotations

import argparse
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Codex Keyboard MCP for Windows")
    parser.add_argument(
        "--broker",
        action="store_true",
        help="run the native keyboard broker instead of the STDIO MCP server",
    )
    parser.add_argument(
        "--allow-medium",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Codex Keyboard MCP currently supports Windows only.")

    args = _parse_args()
    if args.broker:
        from .broker import run_broker

        run_broker(allow_medium=args.allow_medium)
    else:
        from .server import run_stdio_server

        run_stdio_server()


if __name__ == "__main__":
    main()

