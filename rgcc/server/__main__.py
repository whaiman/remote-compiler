import argparse
import logging

import uvicorn

from rgcc import __version__
    
from rgcc.shared.config import load_server_config


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rgccd",
        description="RGCC Build Server Daemon",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"rgccd {__version__}",
    )
    parser.add_argument("--host", default=None, help="Override host from config")
    parser.add_argument("--port", type=int, default=None, help="Override port from config")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only)",
    )
    args = parser.parse_args()

    cfg = load_server_config()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    server_cfg = cfg.get("server", {})
    host = args.host or server_cfg.get("host", "0.0.0.0")
    port = args.port or server_cfg.get("port", 4444)

    uvicorn.run(
        "rgcc.server.api.app:app",
        host=host,
        port=port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
