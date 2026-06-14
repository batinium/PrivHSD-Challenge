"""Backward-compatible alias for :mod:`contextsafe_hsd`.

New code should import :mod:`contextsafe_hsd`. This module remains so older
experiment scripts and saved commands continue to run during the rename.
"""

from importlib import import_module
import pkgutil
import sys as _sys

_impl = import_module("contextsafe_hsd")

for _module_info in pkgutil.walk_packages(
    _impl.__path__,
    prefix=f"{_impl.__name__}.",
):
    if _module_info.name == "contextsafe_hsd.cli":
        continue
    _module = import_module(_module_info.name)
    _alias = f"{__name__}{_module_info.name[len(_impl.__name__):]}"
    _sys.modules[_alias] = _module

_sys.modules[__name__] = _impl
