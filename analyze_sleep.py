#!/usr/bin/env python3
"""Thin wrapper — prefer `sleep-analyzer` or `python -m sleep_analyzer`."""

from sleep_analyzer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
