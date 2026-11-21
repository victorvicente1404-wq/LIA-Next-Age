# Repository guidelines

## Product direction
- Build Lia as a personal, local-first assistant. Local inference and local memory are the default.
- Remote AI providers are opt-in adapters, never silent fallbacks or requirements for core functionality.
- Keep WhatsApp, Google, smart-home, voice, and vision integrations modular.
- Treat Lia Dev as a first-class engineering agent with reviewable plans, diffs, sandboxed workspaces, and explicit approvals.

## Engineering rules
- Prefer small, incremental changes with tests and clear rollback paths.
- Do not remove existing behavior when porting modules; document compatibility decisions.
- Keep secrets, tokens, credentials, personal data, and local databases out of Git.
- Never give an LLM unrestricted shell, filesystem, network, or Git write access.
- Validate workspace paths and command allowlists at the execution boundary.
- Require user approval before file writes, dependency installation, command execution, external data transfer, or sensitive integrations.
- Show the proposed action and diff before applying changes.

## Runtime
- The web client is Vite + React + TypeScript.
- The core service targets Python >=3.10,<3.14 in an isolated environment.
- Local model serving should use a configurable llama.cpp server endpoint.
- Do not make cloud AI credentials mandatory for development, tests, or startup.

## Workflow
- Work on a feature branch; do not push directly to main.
- Run relevant tests and type checks before proposing a merge.
- Update docs when architecture, permissions, or configuration changes.