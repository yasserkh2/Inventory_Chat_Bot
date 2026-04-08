from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import streamlit as st
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from inventory_chatbot.api.server import build_router_service
from inventory_chatbot.config import AppConfig
from inventory_chatbot.models.api import ChatRequest


@st.cache_resource
def get_router_service():
    config = AppConfig.from_env()
    router = build_router_service(config=config)
    return config, router


def ensure_state() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = "demo-session"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "show_result_preview" not in st.session_state:
        st.session_state.show_result_preview = True
    if "show_metadata" not in st.session_state:
        st.session_state.show_metadata = True


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def render_sidebar(config: AppConfig) -> None:
    with st.sidebar:
        st.title("Inventory Chatbot")
        st.caption("Streamlit chat UI for the inventory data copilot")
        st.session_state.session_id = st.text_input(
            "Session ID",
            value=st.session_state.session_id,
        ).strip() or "demo-session"
        st.markdown(
            "\n".join(
                [
                    f"- Provider: `{config.provider}`",
                    f"- Model: `{config.model_name}`",
                ]
            )
        )
        st.session_state.show_result_preview = st.toggle(
            "Show result preview",
            value=st.session_state.show_result_preview,
        )
        st.session_state.show_metadata = st.toggle(
            "Show metadata",
            value=st.session_state.show_metadata,
        )
        if st.button("Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


def render_history() -> None:
    if not st.session_state.messages:
        st.info(
            "Ask about the schema or the data. For example: "
            "`What tables do we have?` or `How many assets by site?`"
        )
        return

    for item in st.session_state.messages:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
            if item["role"] == "assistant":
                if item.get("sql_query"):
                    with st.expander("SQL Query"):
                        st.code(item["sql_query"], language="sql")
                if st.session_state.show_result_preview and item.get("result_preview"):
                    with st.expander("Result Preview"):
                        st.json(item["result_preview"])
                if st.session_state.show_metadata and item.get("metadata"):
                    with st.expander("Metadata"):
                        st.json(item["metadata"])


def main() -> None:
    st.set_page_config(
        page_title="Inventory Chatbot",
        page_icon=":speech_balloon:",
        layout="wide",
    )
    ensure_state()
    config, router = get_router_service()

    st.title("Inventory Data Chatbot")
    st.caption("Chat with the schema and the inventory data, with SQL shown for query-backed answers.")

    render_sidebar(config)
    render_history()

    prompt = st.chat_input("Ask about the data, schema, or business metrics...")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        request = ChatRequest(
            session_id=st.session_state.session_id,
            message=prompt,
            context={},
        )
    except ValidationError as exc:
        error_message = f"Request validation failed: {exc.errors()}"
        st.session_state.messages.append({"role": "assistant", "content": error_message})
        with st.chat_message("assistant"):
            st.error(error_message)
        return

    try:
        response = router.handle_chat(request)
    except Exception as exc:  # pragma: no cover - UI safety net
        error_message = f"Unexpected application error: {exc}"
        st.session_state.messages.append({"role": "assistant", "content": error_message})
        with st.chat_message("assistant"):
            st.error(error_message)
        return

    safe_result_preview = _json_safe(response.result_preview)

    metadata = {
        "status": response.status,
        "provider": response.provider,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "token_usage": response.token_usage.model_dump(),
    }
    assistant_message = {
        "role": "assistant",
        "content": response.natural_language_answer,
        "sql_query": response.sql_query,
        "result_preview": safe_result_preview,
        "metadata": metadata,
    }
    st.session_state.messages.append(assistant_message)

    with st.chat_message("assistant"):
        st.markdown(response.natural_language_answer)
        if response.sql_query:
            with st.expander("SQL Query", expanded=False):
                st.code(response.sql_query, language="sql")
        if st.session_state.show_result_preview and safe_result_preview:
            with st.expander("Result Preview", expanded=False):
                st.json(safe_result_preview)
        if st.session_state.show_metadata:
            with st.expander("Metadata", expanded=False):
                st.json(metadata)


if __name__ == "__main__":
    main()
