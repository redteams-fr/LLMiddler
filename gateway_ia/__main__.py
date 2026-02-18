from __future__ import annotations

import uvicorn

from gateway_ia.app import create_app
from gateway_ia.config import load_config


def main() -> None:
    config = load_config()
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.proxy.host,
        port=config.proxy.port,
        log_level=config.logging.level.lower(),
        access_log=not config.logging.quiet,
    )


if __name__ == "__main__":
    main()
