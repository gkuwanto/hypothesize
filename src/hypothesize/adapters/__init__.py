"""System adapters.

Each adapter builds a ``Runner`` — an ``async`` callable matching the
signature consumed by ``find_discriminating_inputs``'s
``current_runner`` / ``alternative_runner`` arguments — from a
``SystemConfig``. The Python-module adapter is the only fully
implemented adapter in Feature 02; the HTTP and CLI adapters are
scaffolded as import-clean stubs for later features.
"""

from hypothesize.adapters.base import Runner, SystemAdapter
from hypothesize.adapters.cli import CliAdapter
from hypothesize.adapters.config import SystemConfig, load_system_config
from hypothesize.adapters.http import HttpAdapter
from hypothesize.adapters.python_module import PythonModuleAdapter

__all__ = [
    "CliAdapter",
    "HttpAdapter",
    "PythonModuleAdapter",
    "Runner",
    "SystemAdapter",
    "SystemConfig",
    "load_system_config",
]
