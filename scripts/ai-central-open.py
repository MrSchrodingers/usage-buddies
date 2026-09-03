#!/usr/bin/env python3
"""Open the authenticated AI Central URL in the default browser."""
from __future__ import annotations

import subprocess
from pathlib import Path

SERVER = Path(__file__).with_name("ai-central-web.py")


def main() -> int:
    result = subprocess.run([str(SERVER), "--print-url"], text=True, capture_output=True, check=False, timeout=10)
    if result.returncode != 0 or not result.stdout.strip():
        return 1
    return subprocess.run(["xdg-open", result.stdout.strip()], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
