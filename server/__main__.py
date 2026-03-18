import logging

import uvicorn

from server.api.app import app
from shared.config import load_server_config

if __name__ == "__main__":
    cfg = load_server_config()

    # Configure logging
    log_cfg = cfg.get("logging", {})
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    server_cfg = cfg.get("server", {})
    uvicorn.run(
        app, host=server_cfg.get("host", "0.0.0.0"), port=server_cfg.get("port", 4444)
    )
