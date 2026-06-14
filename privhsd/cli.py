"""Compatibility entry point for ``python -m privhsd.cli``."""

from contextsafe_hsd.cli import *  # noqa: F401,F403
from contextsafe_hsd.cli import main


if __name__ == "__main__":
    main()
