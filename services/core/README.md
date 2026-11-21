# Lia Core

Python service for orchestration, policy enforcement, memory access, and local inference adapters.

## Development

Use an isolated Python environment with Python >=3.10 and <3.14. Do not install into the system Python.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn lia_core.main:app --reload --host 0.0.0.0 --port 8000
```

The initial `/health` endpoint does not yet connect to a model. The llama.cpp adapter will be added as a separate, configurable module.
