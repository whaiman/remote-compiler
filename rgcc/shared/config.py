import secrets
from pathlib import Path

import yaml

# Server is usually run per-environment, so standard practice is to use the current working directory.
SERVER_CONFIG_PATH = Path.cwd() / "server_config.yaml"

# The client is a global CLI tool, so we store its configuration globally in the user's home directory!
CLIENT_CONFIG_DIR = Path.home() / ".rgcc"
CLIENT_CONFIG_PATH = CLIENT_CONFIG_DIR / "client_config.yaml"


def load_server_config() -> dict:
    """Load server config or create it if missing. Does NOT touch client config."""
    if not SERVER_CONFIG_PATH.exists():
        auth_token = secrets.token_urlsafe(32)
        config = {
            "server": {
                "host": "0.0.0.0",
                "port": 4444,
                "auth_token": auth_token,
            },
            "logging": {
                "log_file": "server.log",
                "enable_file_logging": False,
                "enable_console_logging": True,
            },
        }
        with open(SERVER_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)
        return config

    with open(SERVER_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_client_config() -> dict:
    """Load client config or create it if missing. Does NOT touch server config."""
    if not CLIENT_CONFIG_PATH.exists():
        # Using placeholders so the user knows they MUST fill them
        config = {
            "client": {
                "endpoint": "http://CHANGE_ME:4444",
                "auth_token": "PASTE_TOKEN_FROM_SERVER_CONFIG",
            }
        }
        CLIENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CLIENT_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)
        return config

    with open(CLIENT_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
