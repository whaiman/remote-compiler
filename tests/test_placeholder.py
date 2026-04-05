"""Basic smoke tests for RGCC package structure."""
import sys


def test_import_rgcc():
    """Test that rgcc package imports correctly."""
    import rgcc

    assert hasattr(rgcc, "__version__")
    assert rgcc.__version__ == "2.0.0"


def test_lazy_client_import():
    """Test that importing client_main doesn't load server deps."""
    from rgcc import client_main

    assert client_main is not None

    # Check server deps not loaded
    assert "starlette" not in sys.modules
    assert "uvicorn" not in sys.modules
    assert "rgcc.server" not in sys.modules


def test_lazy_server_import():
    """Test that importing server_main doesn't load client deps."""
    from rgcc import server_main

    assert server_main is not None

    # Check client deps not loaded
    assert "rich" not in sys.modules
    assert "httpx" not in sys.modules
    assert "rgcc.client" not in sys.modules


def test_shared_imports():
    """Test that shared module loads without optional deps."""
    from rgcc.shared import checksum, config, crypto

    assert checksum and config and crypto

    # These should work with only cryptography and PyYAML
