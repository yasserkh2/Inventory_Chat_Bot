# Inventory Chatbot

Minimal inventory analytics chatbot for the interview task. The service exposes a REST API, keeps in-memory session context, routes questions through deterministic domain specialists, and returns both a natural-language answer and the exact SQL Server query that would run in production.

## Architecture

- `RouterService` handles request validation, session-aware dispatch, specialist execution, dynamic SQL execution, and final answer phrasing.
- `inventory_chatbot/orchestrator` is a standalone package responsible for LLM-based routing, schema-aware analysis, and agent handoff preparation.
- Domain specialists own supported intents, query plans, SQL templates, and deterministic calculations.
- `LLMQueryMaker` focuses only on query planning for the chosen domain instead of also deciding routing.
- `InMemoryRepository` provides demo data for v1, while the shown SQL is the production-targeted SQL Server query.
- OpenAI and Azure OpenAI providers are supported through the official OpenAI Python SDK clients.

This is intentionally not a RAG system and not a free-form text-to-SQL system. The orchestrator decides which agent should handle the request, and SQL is rendered only from vetted templates or validated dynamic query plans.

## Supported Intents

- Total active asset count
- Asset count by site
- Total asset value by site
- Assets purchased this year
- Vendor that supplied the most active assets
- Total billed amount for the last quarter
- Count of open purchase orders
- Asset breakdown by category
- Sales order count for a named customer last month

## Requirements

- Python 3.12+
- `pydantic`

Install locally:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Environment Variables

The app now loads configuration in this order:

1. `config.yml`
2. `.env`
3. real shell environment variables

So `config.yml` is the base config, `.env` is your local developer override, and exported environment variables win last.

Base config lives in [config.yml](/media/yasser/New Volume/yasser/New_journey/Inventory_Chat_Bot/config.yml) and local secrets live in [.env](/media/yasser/New Volume/yasser/New_journey/Inventory_Chat_Bot/.env).

```bash
export PROVIDER=azure
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_DEPLOYMENT="your-deployment"
export MODEL_NAME="gpt-4.1-mini"
export PORT=8000
```

OpenAI alternative:

```bash
export PROVIDER=openai
export OPENAI_API_KEY="..."
export MODEL_NAME="gpt-4.1-mini"
```

You can also edit `.env` directly instead of exporting variables for each run.

## Run

```bash
source .venv/bin/activate
python -m inventory_chatbot.main
```

Open the UI at `http://localhost:8000`.

## Standalone Orchestrator

You can test the orchestrator directly without going through the full chatbot flow:

```bash
source .venv/bin/activate
python -m inventory_chatbot.orchestrator_cli "How many assets by site?" --pretty
```

Useful standalone modes:

```bash
python -m inventory_chatbot.orchestrator_cli "How many assets by site?" --prompt-only
python -m inventory_chatbot.orchestrator_cli "How many assets by site?" --show-prompt --pretty
python -m inventory_chatbot.orchestrator_cli "How many assets by site?" --show-context
python -m inventory_chatbot.orchestrator_cli "Show me the first 5 rows of customers table" --max-iterations 3 --pretty
```

What the standalone orchestrator does:

- Loads the same config and provider credentials as the main app.
- Builds the same schema-aware prompt context used by the router.
- Runs a bounded orchestration loop with self-review before returning a structured decision.
- Returns JSON with the selected agent, user need summary, required data, handoff instructions, and clarification details when needed.

Detailed documentation lives in [ORCHESTRATOR_EXPLANATION.md](/media/yasser/New Volume/yasser/New_journey/Inventory_Chat_Bot/ORCHESTRATOR_EXPLANATION.md).

## Streamlit UI

You can also run the chatbot as a Streamlit app:

```bash
source .venv/bin/activate
streamlit run inventory_chatbot/streamlit_app.py
```

This launches a chat-style UI that talks to the same router service directly and shows SQL for query-backed answers.

Streamlit UI notes:

- Uses the same hardened router flow as the API (orchestrator -> specialist/planner -> SQL execution).
- Renders SQL, result preview, and metadata per assistant reply.
- Safely serializes `date`/`datetime` values in previews to avoid UI crashes.
- Includes sidebar toggles to show/hide result preview and metadata.

## API Example

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-session",
    "message": "How many assets by site?",
    "context": {}
  }'
```

Example response shape:

```json
{
  "natural_language_answer": "Here is the asset count by site...",
  "sql_query": "SELECT s.SiteName, COUNT(*) AS AssetCount ...",
  "token_usage": {
    "prompt_tokens": 10,
    "completion_tokens": 5,
    "total_tokens": 15
  },
  "latency_ms": 24,
  "provider": "azure",
  "model": "gpt-4.1-mini",
  "status": "ok"
}
```

## Tests

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

Orchestrator-only checks:

```bash
source .venv/bin/activate
python -m unittest tests.test_orchestrator -v
python -m inventory_chatbot.orchestrator_cli "How many assets by site?" --prompt-only
```

## Recent Stabilization Updates (2026-04-08)

The latest debugging and hardening pass focused on pipeline trace reliability, SQL handoff safety, and clearer failure diagnostics.

1. Added orchestrator debug trace visibility in pipeline traces.
2. Expanded provider error messages to include root causes (for example DNS resolution failures).
3. Prevented SQL handoff crashes when SQL-agent output is incomplete.
4. Made pipeline trace JSON serialization robust for `date`/`datetime` values.
5. Added regression tests for all of the above.

New behavior in trace diagnostics:

- `orchestrator_failed` now includes `steps.orchestrator_debug` with attempt status and provider error details.
- `handoff_failed` is returned when execution-request construction fails, instead of throwing an uncaught traceback.

Example trace command:

```bash
source .venv/bin/activate
python -m inventory_chatbot.pipeline_trace_cli "show me any first 5 rows of any table" --pretty
```

Detailed implementation log and architectural decisions are tracked in [DECISIONS_LOG.md](/media/yasser/New Volume/yasser/New_journey/Inventory_Chat_Bot/DECISIONS_LOG.md).

## Notes And Tradeoffs

- Demo answers are computed from embedded seed data.
- The returned SQL is the exact SQL Server query that would run in a production-backed version.
- Provider failures return a controlled API error.
- The orchestrator is now separated from the router for cleaner responsibilities and easier prompt iteration.
- The orchestrator loop is bounded to keep behavior predictable while still allowing limited self-correction.
- v1 deliberately excludes live SQL Server execution, persistent storage, authentication, and broad natural-language coverage beyond the supported intents.
