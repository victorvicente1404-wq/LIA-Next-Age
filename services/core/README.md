# Lia Core

Python service for orchestration, local inference, persistent memory, and safe developer workspace inspection. It is deliberately independent from hosted AI providers.

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

Start a compatible llama.cpp server separately:

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
```

Configure the core with:

- `LIA_LLM_BASE_URL`: OpenAI-compatible base URL; default `http://127.0.0.1:8080/v1`.
- `LIA_LLM_MODEL`: model identifier sent to the local server; default `local-model`.
- `LIA_DATA_DIR`: directory for the local SQLite memory database; default `~/.lia`.
- `LIA_DEV_WORKSPACES`: optional, path-separated list of directories Lia Dev is allowed to inspect.

The adapter calls only the configured local endpoint. It does not fall back to cloud providers. If the local model is unavailable, chat returns HTTP 503 with a clear error.

## API

- `GET /health`: service and configured inference status.
- `POST /api/v1/chat`: local chat completion.
- `POST /api/v1/memories`: save a fact, preference, knowledge item, or note.
- `GET /api/v1/memories?q=...&kind=...`: search/list saved memories.
- `DELETE /api/v1/memories/{id}`: delete one memory.
- `GET /api/v1/dev/workspaces`: list explicitly allowed developer workspaces.
- `GET /api/v1/dev/workspaces/{id}/files?path=...`: list a directory.
- `GET /api/v1/dev/workspaces/{id}/file?path=...`: read a UTF-8 text file up to 256 KiB.

Lia Dev is read-only at this stage. It blocks path traversal, skips symlinks in directory listings, excludes common generated directories and secret files, and rejects oversized or non-UTF-8 files. It cannot write, install packages, or execute terminal commands yet.

## Tests

```bash
pytest
ruff check .
```

## OpenJarvis

OpenJarvis remains an architectural/backend candidate to integrate behind Lia's interfaces. The first runtime uses the llama.cpp OpenAI-compatible API directly so the core can run on the current Android/Termux setup without requiring a second framework or a cloud account. Integration must preserve the same local-first and Python-version constraints.
