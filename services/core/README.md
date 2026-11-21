# Lia Core

Python service for orchestration, local inference, and persistent memory. It is deliberately independent from hosted AI providers.

## Requirements

Use an isolated Python environment with Python >=3.10 and <3.14. Do not install into the system Python.

## Development

From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn lia_core.main:app --reload --host 127.0.0.1 --port 8000
```

The service binds to loopback by default in the documented command. Do not expose it to a LAN or the public internet until authentication and device pairing are implemented.

## Local inference with llama.cpp

Start a compatible llama.cpp server separately, for example:

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
```

Configure the core with:

- `LIA_LLM_BASE_URL`: OpenAI-compatible base URL; default `http://127.0.0.1:8080/v1`.
- `LIA_LLM_MODEL`: model identifier sent to the local server; default `local-model`.
- `LIA_DATA_DIR`: directory for the local SQLite memory database; default `~/.lia`.

The adapter calls only the configured local endpoint. It does not fall back to cloud providers. If the local model is unavailable, chat returns HTTP 503 with a clear error.

## API

- `GET /health`: service and configured inference status.
- `POST /api/v1/chat`: local chat completion.
- `POST /api/v1/memories`: save a fact, preference, knowledge item, or note.
- `GET /api/v1/memories?q=...&kind=...`: search/list saved memories.
- `DELETE /api/v1/memories/{id}`: delete one memory.

Memory is stored separately from the model in SQLite. This first version stores explicit memory entries; automatic extraction and retrieval into prompts will be added only after the consent and memory-policy layer is defined.

## Tests

```bash
pytest
ruff check .
```

## OpenJarvis

OpenJarvis remains an architectural/backend candidate to integrate behind Lia's interfaces. The first runtime uses the llama.cpp OpenAI-compatible API directly so the core can run on the current Android/Termux setup without requiring a second framework or a cloud account. Integration must preserve the same local-first and Python-version constraints.
