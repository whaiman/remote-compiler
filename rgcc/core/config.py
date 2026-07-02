import os
import secrets
import stat
from pathlib import Path
from typing import Any

import yaml  # type: ignore

# We use per-project configuration files by default
SERVER_CONFIG_PATH = Path.cwd() / "rgccd.yaml"
CLIENT_CONFIG_PATH = Path.cwd() / "rgcc.yaml"


def _secure_dump(config: dict[str, Any], path: Path) -> None:
    """Write YAML config and lock permissions to owner-only (contains secrets)."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600


def load_server_config() -> dict[str, Any]:
    """Load server config or create it if missing. Does NOT touch client config."""
    if not SERVER_CONFIG_PATH.exists():
        SERVER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        auth_token = secrets.token_urlsafe(32)
        config = {
            "logging": {
                "log_file": "server.log",
                "enable_file_logging": False,
                "enable_console_logging": True,
            },
            "server": {
                "host": "0.0.0.0",
                "port": 4444,
                "auth_token": auth_token,
            },
            "compilers": {
                "g++": {
                    "default_args": ["-fdiagnostics-color=always"],
                    "platforms": {
                        "linux": {"target": "x86_64-linux-gnu", "args": []},
                        "win64": {
                            "target": "x86_64-w64-mingw32",
                            "sysroot": "/usr/x86_64-w64-mingw32",
                            "args": ["-static", "-static-libgcc", "-static-libstdc++"],
                        },
                    },
                },
                "gcc": {
                    "default_args": ["-fdiagnostics-color=always"],
                    "platforms": {
                        "linux": {"target": "x86_64-linux-gnu", "args": []},
                        "win64": {
                            "target": "x86_64-w64-mingw32",
                            "sysroot": "/usr/x86_64-w64-mingw32",
                            "args": ["-static"],
                        },
                    },
                },
            },
        }
        _secure_dump(config, SERVER_CONFIG_PATH)
        return config

    with open(SERVER_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_client_config() -> dict[str, Any]:
    """Load client config or create it if missing. Does NOT touch server config."""
    if not CLIENT_CONFIG_PATH.exists():
        # Using placeholders so the user knows they MUST fill them
        config = {
            "client": {
                "endpoint": "http://CHANGE_ME:4444",
                "auth_token": "PASTE_TOKEN_FROM_SERVER_CONFIG",
            }
        }
        CLIENT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _secure_dump(config, SERVER_CONFIG_PATH)
        return config

    with open(CLIENT_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
