"""Restatement backend adapters."""

from .local_http import LocalHttpRestatementBackend, NoopRestatementBackend

__all__ = ["LocalHttpRestatementBackend", "NoopRestatementBackend"]
