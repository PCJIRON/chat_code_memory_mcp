"""Pytest configuration for Windows DLL compatibility."""

from __future__ import annotations

import sys


def pytest_configure(config):
    """Apply Windows DLL fix before any torch imports."""
    if sys.platform == "win32":
        import os
        # Add torch lib to PATH for Windows DLL resolution
        import torch
        torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        if os.path.exists(torch_lib):
            os.add_dll_directory(torch_lib)
