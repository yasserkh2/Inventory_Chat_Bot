from __future__ import annotations

import logging

from inventory_chatbot.api.server import create_server
from inventory_chatbot.config import AppConfig, ConfigurationError


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = AppConfig.from_env()
    try:
        config.validate_provider_credentials()
        config.validate_sql_backend_configuration()
        server = create_server(config=config)
    except ConfigurationError as exc:
        logging.error("Configuration error: %s", exc)
        raise SystemExit(1) from exc
    except Exception as exc:
        logging.error("Failed to initialize services: %s", exc)
        raise SystemExit(1) from exc
    try:
        logging.info("Serving on http://%s:%s", config.host, config.port)
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
