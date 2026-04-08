# Inventory Chatbot

Interview submission for a schema-aware inventory analytics chatbot.

The app answers business questions, returns the generated SQL (`present query`), and exposes both:
- REST API: `POST /api/chat`
- Streamlit UI

## What This Project Demonstrates

- LLM-based orchestration (route to the right domain agent)
- LLM-based SQL planning with review + execution pipeline
- SQL safety checks (schema/domain validation)
- In-memory session context
- Multiple data backends: `memory`, `sqlite`
- OpenAI/Azure OpenAI provider switch via env

## Project Structure (Key Files)

- `inventory_chatbot/main.py`: API server entrypoint
- `inventory_chatbot/streamlit_app.py`: Streamlit UI entrypoint
- `inventory_chatbot/orchestrator/`: routing + handoff layer
- `inventory_chatbot/sql_agents/`: domain SQL planning agents
- `inventory_chatbot/sql_review/`: SQL normalization and validation
- `inventory_chatbot/sql_execution/`: SQL preview/execution service
- `inventory_chatbot/sql_backend/`: SQL backend init + wiring
- `inventory_chatbot/runtime/backend_factory.py`: backend wiring for API/UI/CLI

## Prerequisites

- Python `3.12+`
- SQLite (stdlib, no external DB required)

## 5-Minute Quick Start (Recommended for Interviewer)

### 1) Create environment and install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2) Configure provider + backend

Use `.env` (recommended) or export env vars.

OpenAI example:

```bash
export PROVIDER=openai
export OPENAI_API_KEY="<your-key>"
export MODEL_NAME="gpt-4.1-mini"
export DATA_BACKEND=sqlite
export SQLITE_DATABASE_PATH=inventory_chatbot.sqlite3
```

Azure OpenAI example:

```bash
export PROVIDER=azure
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
export AZURE_OPENAI_API_KEY="<your-key>"
export AZURE_OPENAI_DEPLOYMENT="<deployment-name>"
export MODEL_NAME="gpt-4.1-mini"
export DATA_BACKEND=sqlite
export SQLITE_DATABASE_PATH=inventory_chatbot.sqlite3
```

### 3) Initialize SQLite schema + seed data

```bash
python -m inventory_chatbot.sql_backend.db_init
```

### 4) Run API server

```bash
python -m inventory_chatbot.main
```

Server starts at: `http://localhost:8000`

### 5) Smoke test API

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-session",
    "message": "What is the total cost of non-disposed assets?",
    "context": {}
  }'
```

You should receive JSON with:
- `natural_language_answer`
- `sql_query`
- `token_usage`
- `latency_ms`
- `provider`, `model`, `status`

## Run Streamlit UI

```bash
source .venv/bin/activate
python -m streamlit run inventory_chatbot/streamlit_app.py
```

## Configuration Notes

Config resolution order:
1. `config.yml`
2. `.env`
3. shell environment variables (highest priority)

Important env vars:
- Provider: `PROVIDER`, `MODEL_NAME`
- OpenAI: `OPENAI_API_KEY`
- Azure: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`
- Backend: `DATA_BACKEND=memory|sqlite`
- SQLite: `SQLITE_DATABASE_PATH`
- API bind: `HOST`, `PORT`

## Run Tests

```bash
source .venv/bin/activate
python -m unittest discover -s tests -p "test_*.py"
```

Integration tests beyond the local stack are not included in this streamlined interview submission.

## Example Questions

- `How many assets do I have?`
- `How many assets by site?`
- `What is the total value of assets per site?`
- `What is the total billed amount for the last quarter?`
- `How many open purchase orders are currently pending?`
- `How many sales orders were created for Acme Corp last month?`

## Notes

- The system is schema-aware and validates SQL before execution.
- It is intentionally constrained to the provided domain schema (not unrestricted text-to-SQL).
- SQLite mode is the fastest path for interviewer evaluation.
