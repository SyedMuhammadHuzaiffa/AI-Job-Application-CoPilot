# Developer Guide

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env` for live generation.

## Run

```bash
streamlit run app.py
```

## Test

```bash
pytest
```

The test suite is configured in `pyproject.toml` with coverage enabled and an 80% fail-under threshold.

## Development Principles

- Keep Streamlit rendering in `app.py`.
- Put reusable domain behavior in `src/job_copilot`.
- Preserve the public wrapper functions when adding repositories or services.
- Inject `chat_client` in tests instead of calling OpenAI.
- Do not add profile facts in code, prompts, tests, or samples unless they are explicitly provided.
- Prefer temp SQLite databases in tests.
- Do not make live network calls from tests.

## Adding a New LLM Feature

1. Add a prompt-specific module or function.
2. Use `ChatClient` from `llm_client.py` for dependency injection.
3. Normalize the model response into a stable shape.
4. Add tests with `StaticChatClient`.
5. Add UI only after the service function is tested.

## Adding a New Job Source

1. Prefer an official API, RSS feed, or public job-board endpoint.
2. Respect robots.txt for career pages.
3. Fetch through `_request_json` or `_request_text` so retries and logging are consistent.
4. Normalize into the unified job shape.
5. Add tests with mocked fetch responses.

## Database Changes

- Add migrations inside `init_db` or `init_job_db`.
- Add indexes for fields used by filters, joins, charts, or dashboards.
- Keep existing columns compatible with older local databases.
