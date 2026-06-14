#!/usr/bin/env python3
"""Compatibility wrapper for the packaged Dynahate preparation command."""

from contextsafe_hsd.datasets import main


if __name__ == "__main__":
    raise SystemExit(main())
