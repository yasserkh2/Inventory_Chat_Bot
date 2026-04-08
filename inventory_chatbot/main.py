from __future__ import annotations

import logging

from inventory_chatbot.api.server import create_server
from inventory_chatbot.config import AppConfig


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = AppConfig.from_env()
    server = create_server(config=config)
    try:
        logging.info("Serving on http://%s:%s", config.host, config.port)
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
