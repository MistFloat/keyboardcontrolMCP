from __future__ import annotations

import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keyboard_mcp.ipc import launch_broker, request_broker  # noqa: E402


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This elevated smoke test is Windows-only.")
    started = launch_broker()
    try:
        broker = started["broker"]
        if broker["integrity"]["elevated"] is not True:
            raise AssertionError(f"broker is not elevated: {broker['integrity']}")
        result = request_broker("self_test")
        if result.get("success") is not True:
            raise AssertionError(f"elevated self-test failed: {result}")
        print(
            "PASS: elevated broker controlled an elevated diagnostic window; "
            f"integrity={result['broker_integrity']['name']}, "
            "Unicode=true, scan-code Enter=true"
        )
    finally:
        try:
            request_broker("shutdown")
        except (FileNotFoundError, ConnectionError, EOFError, OSError):
            pass


if __name__ == "__main__":
    main()

