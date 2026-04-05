#!/usr/bin/env python3
"""Standalone test for lazy loading verification."""

import sys


def test_client_is_lazy():
    """Verify client installation doesn't import server modules."""
    print("Testing client lazy loading...")

    # Import only main entry
    import rgcc

    # Before calling client_main, server should not be in sys.modules
    assert "rgcc.server" not in sys.modules, "Server loaded eagerly!"
    assert "starlette" not in sys.modules, "Starlette loaded eagerly!"

    print("✓ Client lazy loading OK")


def test_server_is_lazy():
    """Verify server installation doesn't import client modules."""
    print("Testing server lazy loading...")

    import rgcc

    assert "rgcc.client" not in sys.modules, "Client loaded eagerly!"
    assert "rich" not in sys.modules, "Rich loaded eagerly!"

    print("✓ Server lazy loading OK")


if __name__ == "__main__":
    test_client_is_lazy()
    test_server_is_lazy()
    print("\n✓ All lazy import tests passed!")
