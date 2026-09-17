#!/usr/bin/env python3
"""Standalone test for lazy loading verification."""

import subprocess
import sys


def run_isolated(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )


def test_client_is_lazy():
    result = run_isolated("""
import sys
import rgcc

assert "rgcc.server" not in sys.modules
assert "starlette" not in sys.modules

import rgcc.client

assert "rgcc.client" in sys.modules
assert "rgcc.server" not in sys.modules
""")

    assert result.returncode == 0, result.stderr


def test_server_is_lazy():
    result = run_isolated("""
import sys
import rgcc

assert "rgcc.client" not in sys.modules
assert "rich" not in sys.modules

import rgcc.server

assert "rgcc.server" in sys.modules
assert "rgcc.client" not in sys.modules
""")

    assert result.returncode == 0, result.stderr


def test_core_imports():
    """Verify that core shared modules can be imported."""
    print("Testing core imports...")
    from rgcc.core import checksum, config, crypto, manifest, platforms

    assert checksum
    assert config
    assert crypto
    assert manifest
    assert platforms

    assert all([checksum, config, crypto, manifest, platforms])
    print("✓ Core imports OK")


if __name__ == "__main__":
    test_client_is_lazy()
    test_server_is_lazy()
    test_core_imports()
    print("\n✓ All lazy import tests passed!")
