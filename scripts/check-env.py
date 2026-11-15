#!/usr/bin/env python3
"""Validate that .env.example is well-formed and contains no real secrets.

Usage: python3 scripts/check-env.py
Exit code 0 = valid, 1 = invalid.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"

REQUIRED_KEYS = [
    "APP_ENV",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_DB_URL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_DEFAULT_MODEL",
    "VITE_SUPABASE_URL",
    "VITE_SUPABASE_ANON_KEY",
    "VITE_API_BASE_URL",
]

# Patterns that look like real credentials (long opaque tokens).
SUSPICIOUS = re.compile(r"^(sk-|eyJ|sbp_|postgres://[^:]+:[^@]{8,}@)")


def main() -> int:
    if not EXAMPLE.exists():
        print(f"ERROR: {EXAMPLE} not found")
        return 1
    text = EXAMPLE.read_text(encoding="utf-8")
    keys: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            print(f"ERROR: malformed line (no '='): {line!r}")
            return 1
        key, _, value = line.partition("=")
        keys[key.strip()] = value.strip().split("#")[0].strip()

    missing = [k for k in REQUIRED_KEYS if k not in keys]
    if missing:
        print(f"ERROR: missing required keys in .env.example: {missing}")
        return 1

    for key, value in keys.items():
        if SUSPICIOUS.search(value):
            print(f"ERROR: {key} looks like a real secret; placeholders only")
            return 1
        if "your-" in value or "your_" in value or value in ("", "changeme"):
            continue
        # Non-placeholder values must still be clearly labelled examples.
        if key in ("APP_ENV", "APP_NAME", "APP_DEBUG", "APP_HOST", "APP_PORT",
                   "APP_LOG_LEVEL", "APP_CORS_ORIGINS", "OPENROUTER_TIMEOUT_SECONDS",
                   "OPENROUTER_MAX_RETRIES", "OPENROUTER_HTTP_REFERER",
                   "OPENROUTER_APP_TITLE", "VITE_API_BASE_URL"):
            continue
        print(f"WARNING: {key} has a non-placeholder value; ensure it is not a real secret")

    # .env must not be tracked by git.
    gitignore = ROOT / ".gitignore"
    if gitignore.exists() and ".env" not in gitignore.read_text(encoding="utf-8"):
        print("ERROR: .gitignore does not exclude .env")
        return 1

    print(f"OK: .env.example valid ({len(keys)} variables, placeholders only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
