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

## Local inference

The default `LIA_RUNTIME_BACKEND=auto` tries the optional OpenJarvis `LlamaCppEngine` adapter when OpenJarvis is installed in the same Python environment. If it is not installed, Lia uses its small direct llama.cpp HTTP adapter. Both paths send requests only to the configured local endpoint.

- `LIA_RUNTIME_BACKEND=auto`: prefer OpenJarvis when installed, otherwise use direct llama.cpp.
- `LIA_RUNTIME_BACKEND=openjarvis`: require OpenJarvis; startup fails clearly if it is missing.
- `LIA_RUNTIME_BACKEND=llama.cpp`: force the direct adapter.

Start llama.cpp:

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
```

Configure the core with:

- `LIA_LLM_BASE_URL`: OpenAI-compatible base URL; default `http://127.0.0.1:8080/v1`.
- `LIA_LLM_MODEL`: model identifier sent to the local server; default `local-model`.
- `LIA_LLM_TIMEOUT`: request timeout in seconds; default `120`.
- `LIA_DATA_DIR`: directory for the local SQLite memory database; default `~/.lia`.
- `LIA_DEV_WORKSPACES`: optional, path-separated list of directories Lia Dev is allowed to inspect.

The OpenJarvis adapter uses its `LlamaCppEngine` primitive. The direct adapter remains available for Android setups where installing the full OpenJarvis dependency tree is impractical. Neither adapter has a cloud fallback.

For the tested OpenJarvis checkout, pin commit `c5a7766e` when preserving Python 3.10 compatibility. Newer OpenJarvis main currently declares Python >=3.11,<3.14. Both exclude Python 3.14.

## API

- `GET /health`: service and configured inference status.
- `POST /api/v1/chat`: local chat completion; response includes engine name, `external_traffic: false`, and the number of memories used.
- `POST /api/v1/memories`: save a fact, preference, knowledge item, or note.
- `GET /api/v1/memories?q=...&kind=...`: search/list saved memories.
- `DELETE /api/v1/memories/{id}`: delete one memory.
- `POST /api/v1/conversations`: create a chat session.
- `GET /api/v1/conversations?limit=...`: list recent sessions.
- `GET /api/v1/conversations/{id}?limit=...&offset=...`: load messages with pagination.
- `DELETE /api/v1/conversations/{id}`: delete a session and its messages.
- `GET /api/v1/dev/workspaces`: list explicitly allowed developer workspaces.
- `GET /api/v1/dev/workspaces/{id}/files?path=...`: list a directory.
- `GET /api/v1/dev/workspaces/{id}/file?path=...`: read a UTF-8 text file up to 256 KiB.

## Memory behavior

Memories are stored separately from the model in SQLite. FTS5 is used for local full-text retrieval when available; substring search is the fallback. Explicitly saved preferences are included in the chat context, along with up to five memories total (saved preferences are prioritized, then query matches). The chat API reports `memories_used`. Requests can set `use_memory=false` to disable retrieval for a turn.

The application does not silently extract new memories from conversation. Users add and delete entries through the Memory tab. Retrieved entries are labeled as saved context, not executable instructions.

## Conversation history

Chat sessions and their messages are stored in `LIA_DATA_DIR/conversations.sqlite3`, separately from `memory.sqlite3`. The web interface restores the most recently updated session, lets the user switch between recent sessions or start a new one, and persists each successful user/assistant turn. History is not automatically promoted into long-term memory. The chat request sends only the latest 40 messages as model context while the full history remains stored. The API exposes paginated message retrieval and session deletion.

OpenJarvis's SQLite/FTS5 backend is being evaluated separately because the pinned OpenJarvis checkout requires its Rust extension for that backend; the Lia-owned store remains the reliable minimal Android path for explicit personal memories.

## Lia Dev

Lia Dev can inspect only explicitly allowlisted workspaces. It blocks path traversal, skips symlinks in directory listings, excludes common generated directories and secret files, and rejects oversized or non-UTF-8 files. File edits are proposed as diffs and require a separate apply request; each write is atomic, checks the original file hash, and creates a persistent rollback backup.

Development tasks are selected from a fixed catalog (Git status/diff, pytest, Ruff, and npm build). A proposal displays the exact command and working directory and expires after five minutes. Execution requires a separate approval request, runs without a shell, uses a restricted environment, has a 120-second timeout, captures only a bounded amount of output while continuing to drain the process pipe, and kills the process group on completion or timeout. This is not an OS/container sandbox: approved tests and builds execute project code and may modify the workspace. Do not expose the API beyond loopback until authentication and device pairing exist.

## Tests

```bash
pytest
ruff check .
```
