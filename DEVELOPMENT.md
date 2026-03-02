# Development Guide

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Project Structure

```
src/second_brain/
├── main.py              # Entry point — orchestrates the full pipeline
├── core/
│   ├── config.py        # Pydantic Settings: loads .env + config.yaml
│   └── models.py        # Shared data structures (Message, Category)
├── agent/
│   ├── agent.py         # LangGraph ReAct agent construction + invocation
│   ├── llm.py           # OpenRouter LLM factory (ChatOpenAI wrapper)
│   └── prompts.py       # System prompt template for the agent
├── utils/
│   └── parser.py        # Parses dump file into Message objects
├── services/
│   └── drive.py         # Google Drive CRUD via service account
└── tools/
    └── drive_tools.py   # LangChain @tool wrappers over drive.py
```

### Layer Responsibilities

| Layer | Purpose | LangChain Aware? |
|-------|---------|------------------|
| `core/` | Config and shared models used by all layers | No |
| `services/` | Raw API clients (Drive, future: Telegram, Calendar) | No |
| `tools/` | LangChain `@tool` wrappers that the agent can invoke | Yes |
| `agent/` | LLM factory, prompt engineering, agent construction | Yes |
| `utils/` | Pure utility functions (parsing, formatting) | No |

## Running Tests

```bash
# All tests
pytest

# Verbose with test names
pytest -v

# Single test file
pytest tests/test_parser.py

# Single test
pytest tests/test_parser.py::test_single_message
```

## Test Structure

```
tests/
├── conftest.py            # Shared fixtures (sample dump path/text)
├── test_parser.py         # Dump file parser unit tests
├── test_drive_service.py  # Drive API client tests (mocked Google API)
├── test_drive_tools.py    # LangChain tool tests (mocked DriveService)
├── test_agent.py          # Prompt, LLM factory, and agent wiring tests
├── test_pipeline.py       # End-to-end pipeline tests (all deps mocked)
└── fixtures/
    └── sample_dump.md     # Sample dump file used by parser tests
```

All external dependencies (Google Drive API, OpenRouter) are mocked in tests. No credentials needed to run the test suite.

## Running Locally

```bash
# Copy and fill in your credentials
cp .env.example .env

# Single run for today
python -m second_brain.main

# Specific date
python -m second_brain.main --date 2026-03-01

# Cron mode
python -m second_brain.main --schedule
```

## Google Drive Setup

1. Create a [Google Cloud service account](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Enable the Google Drive API for the project
3. Download the service account JSON key file
4. Create two Google Drive folders (input and output)
5. Share both folders with the service account email (found in the JSON key file under `client_email`)
6. Copy the folder IDs (from the URL: `drive.google.com/drive/folders/{THIS_IS_THE_ID}`) into `.env`

## Dump File Format

Files in the input folder must be named `YYYY-MM-DD.md` and use this delimiter format:

```markdown
<!-- msg_id: unique-id-001 -->
Message content goes here. Can be multiple lines.

<!-- msg_id: unique-id-002 -->
Another message.
```

The `msg_id` values should be unique within a file. Content between delimiters is captured as-is (whitespace stripped).

## Swapping the LLM

Change the model in `config.yaml`:

```yaml
llm:
  model: "openai/gpt-4o"          # or any OpenRouter-supported model
  temperature: 0.3
  max_tokens: 4096
```

No code changes needed. See [OpenRouter models](https://openrouter.ai/models) for available options.

## Adding a New Integration

Follow the two-layer pattern:

1. **Add a client** in `services/` (e.g., `services/telegram.py`) — raw API wrapper, no LangChain awareness
2. **Add tools** in `tools/` (e.g., `tools/telegram_tools.py`) — LangChain `@tool` functions wrapping the client
3. **Register tools** in `agent/agent.py` by including them in the tools list

The agent autonomously decides when to invoke tools based on message content during its reasoning loop.

## Docker

```bash
# Build
docker build -t second-brain .

# Run once
docker run --env-file .env \
  -v ./token.json:/app/token.json \
  second-brain

# Run with schedule
docker run --env-file .env \
  -v ./token.json:/app/token.json \
  second-brain --schedule
```
