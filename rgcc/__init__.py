"""RGCC - Remote GCC Compiler System"""

__version__ = "2.0.0"


def _check_client_deps() -> None:
    missing = []
    for pkg in ["rich", "httpx", "typer"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        raise ImportError(
            f"Missing client dependencies: {', '.join(missing)}\n"
            f'Install: pip install "git+https://github.com/whaiman/remote-compiler.git#egg=remote-compiler[client]"'
        )


def _check_server_deps() -> None:
    missing = []
    for pkg in ["starlette", "uvicorn"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        raise ImportError(
            f"Missing server dependencies: {', '.join(missing)}\n"
            f'Install: pip install "git+https://github.com/whaiman/remote-compiler.git#egg=remote-compiler[server]"'
        )


from typing import Any

def client_main() -> Any:
    _check_client_deps()
    from rgcc.client.cli import app

    return app()


def server_main() -> Any:
    _check_server_deps()
    from rgcc.server.__main__ import main

    return main()
