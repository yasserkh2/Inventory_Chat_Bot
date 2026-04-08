from __future__ import annotations

import json
import logging
import mimetypes
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from inventory_chatbot.config import AppConfig
from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.dynamic_sql.service import DynamicSQLService
from inventory_chatbot.llm.base import LLMClient
from inventory_chatbot.llm.factory import build_llm_client
from inventory_chatbot.models.api import ChatRequest, TokenUsage
from inventory_chatbot.orchestrator.llm_based import LLMOrchestrator
from inventory_chatbot.query_makers.llm_based import LLMQueryMaker
from inventory_chatbot.router.registry import SpecialistRegistry
from inventory_chatbot.router.service import RouterService
from inventory_chatbot.services.date_parser import DateParser
from inventory_chatbot.services.response_formatter import build_response
from inventory_chatbot.services.session_store import SessionStore
from inventory_chatbot.sql_execution.service import SQLExecutionService
from inventory_chatbot.specialists.assets import AssetSpecialist
from inventory_chatbot.specialists.billing import BillingSpecialist
from inventory_chatbot.specialists.procurement import ProcurementSpecialist
from inventory_chatbot.specialists.sales import SalesSpecialist

LOGGER = logging.getLogger(__name__)


def build_router_service(
    *,
    config: AppConfig,
    repository: InMemoryRepository | None = None,
    llm_client: LLMClient | None = None,
    today_provider: Callable | None = None,
    session_store: SessionStore | None = None,
) -> RouterService:
    repository = repository or InMemoryRepository()
    date_parser = DateParser(today_provider=today_provider)
    llm_client = llm_client or build_llm_client(config)
    resolved_today = today_provider() if today_provider is not None else date.today()
    registry = SpecialistRegistry(
        [
            AssetSpecialist(repository, date_parser),
            BillingSpecialist(repository, date_parser),
            ProcurementSpecialist(repository),
            SalesSpecialist(repository, date_parser),
        ]
    )
    sql_execution_service = SQLExecutionService(seed_data=repository._data)
    return RouterService(
        config=config,
        registry=registry,
        session_store=session_store or SessionStore(),
        llm_client=llm_client,
        dynamic_sql_service=DynamicSQLService(seed_data=repository._data),
        sql_execution_service=sql_execution_service,
        orchestrator=LLMOrchestrator(
            llm_client=llm_client,
            today=resolved_today,
            customer_names=[
                customer["customer_name"] for customer in repository.list_customers()
            ],
        ),
        query_maker=LLMQueryMaker(
            llm_client=llm_client,
            today=resolved_today,
            customer_names=[
                customer["customer_name"] for customer in repository.list_customers()
            ],
            execution_service=sql_execution_service,
        ),
        customer_names=[customer["customer_name"] for customer in repository.list_customers()],
    )


def health_payload(config: AppConfig) -> tuple[HTTPStatus, dict]:
    return (
        HTTPStatus.OK,
        {
            "status": "ok",
            "provider": config.provider,
            "model": config.model_name,
        },
    )


def history_payload(*, session_id: str, session_store: SessionStore) -> tuple[HTTPStatus, dict]:
    session_state = session_store.get(session_id)
    return (
        HTTPStatus.OK,
        {
            "status": "ok",
            "session_id": session_id,
            "turns": [turn.model_dump(mode="json") for turn in session_state.turns],
        },
    )


def handle_chat_payload(
    *, payload: bytes, router_service: RouterService, config: AppConfig
) -> tuple[HTTPStatus, dict]:
    try:
        decoded = json.loads(payload.decode("utf-8") or "{}")
        request = ChatRequest.model_validate(decoded)
    except json.JSONDecodeError:
        response = build_response(
            answer="Request body must be valid JSON.",
            sql_query="",
            usage=TokenUsage(),
            latency_ms=0,
            config=config,
            status="error",
        )
        return HTTPStatus.BAD_REQUEST, response.model_dump(mode="json")
    except ValidationError as exc:
        response = build_response(
            answer=f"Request validation failed: {exc.errors()}",
            sql_query="",
            usage=TokenUsage(),
            latency_ms=0,
            config=config,
            status="error",
        )
        return HTTPStatus.BAD_REQUEST, response.model_dump(mode="json")

    response = router_service.handle_chat(request)
    return HTTPStatus.OK, response.model_dump(mode="json")


def create_server(
    *,
    config: AppConfig,
    host: str | None = None,
    port: int | None = None,
    repository: InMemoryRepository | None = None,
    llm_client: LLMClient | None = None,
    today_provider: Callable | None = None,
    session_store: SessionStore | None = None,
) -> ThreadingHTTPServer:
    router_service = build_router_service(
        config=config,
        repository=repository,
        llm_client=llm_client,
        today_provider=today_provider,
        session_store=session_store,
    )
    static_dir = Path(__file__).resolve().parent.parent / "static"

    class InventoryChatHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)

            if parsed.path == "/health":
                status, payload = health_payload(config)
                self._write_json(status, payload)
                return

            if parsed.path == "/api/history":
                session_id = parse_qs(parsed.query).get("session_id", [""])[0].strip()
                if not session_id:
                    self._write_json(
                        HTTPStatus.BAD_REQUEST,
                        {
                            "status": "error",
                            "message": "session_id is required",
                            "turns": [],
                        },
                    )
                    return
                status, payload = history_payload(
                    session_id=session_id,
                    session_store=router_service._session_store,
                )
                self._write_json(status, payload)
                return

            relative_path = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
            file_path = (static_dir / relative_path).resolve()
            if static_dir not in file_path.parents and file_path != static_dir / "index.html":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            content_type = mimetypes.guess_type(str(file_path))[0] or "text/plain"
            payload = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/chat":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            status, response = handle_chat_payload(
                payload=raw_body,
                router_service=router_service,
                config=config,
            )
            self._write_json(status, response)

        def log_message(self, fmt: str, *args) -> None:
            LOGGER.info("%s - %s", self.address_string(), fmt % args)

        def _write_json(self, status: HTTPStatus, payload: dict) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer((host or config.host, port or config.port), InventoryChatHandler)
    return server
