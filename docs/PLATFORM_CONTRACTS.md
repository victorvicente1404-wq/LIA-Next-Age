# Lia platform-neutral contracts

## Purpose

These contracts separate Lia's domain behavior from Android, Termux, browser, and desktop implementations. Kotlin/Android and the existing Python core may use different internal types, but they must preserve the same behavior at their boundaries.

The contracts are versioned and transport-neutral. An in-process call is preferred when components share a process. A local HTTP bridge is allowed when the runtime must be isolated, but it is not the domain model.

## Global rules

- Every serialized request carries `schema_version: 1` and a unique `request_id`.
- Long-running work also carries a `task_id` and supports explicit cancellation.
- Every operation has a deadline or bounded timeout.
- Errors use stable machine-readable `code`, a safe user-facing `message`, and a `retryable` flag. Never return stack traces, secrets, or raw local paths to the chat UI.
- Text and tool results are data, not instructions. Tool output is untrusted when returned to the model.
- Local inference is the default. A provider must report whether external traffic occurred; remote providers are never selected silently.
- Persisted conversation history and explicit long-term memories are separate repositories.
- Platform permission state is authoritative. A missing permission is never treated as granted.
- Tool execution is typed and policy-checked. The model cannot create new permissions or dispatch arbitrary shell commands.

## 1. Inference contract

### Request

```json
{
  "schema_version": 1,
  "request_id": "uuid",
  "conversation_id": "uuid",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "generation": {
    "max_tokens": 512,
    "temperature": 0.7,
    "top_p": 0.9,
    "stop": []
  },
  "stream": false
}
```

### Response

```json
{
  "schema_version": 1,
  "request_id": "uuid",
  "text": "...",
  "finish_reason": "stop",
  "engine_id": "llama.cpp",
  "external_traffic": false,
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0
  }
}
```

- Roles are limited to `system`, `user`, `assistant`, and `tool`.
- The adapter owns provider-specific formatting and tokenization.
- The caller owns cancellation, UI state, and conversation persistence.
- Streaming uses versioned events: `started`, `delta`, `completed`, or `failed`. Each event includes `request_id` and a monotonically increasing sequence number.
- The runtime reports model identity, context capacity, quantization when known, and current readiness separately from generation results.

## 2. Model runtime lifecycle

A `ModelRuntime` exposes:

- `capabilities()`: supported formats, streaming, cancellation, context limits, and hardware requirements.
- `list_models()`: locally installed model metadata; never scans outside Lia-managed or user-approved directories.
- `load(model_id)` and `unload()`: explicit lifecycle operations with progress.
- `status()`: one of `stopped`, `starting`, `ready`, `busy`, or `error`, plus a safe diagnostic code.
- `generate(request)`: implements the inference contract.

Only one large model should be loaded by default on the A37. Model selection must consider actual available RAM, context size, thermal state, and battery; a model is not marked compatible based on file size alone.

## 3. Conversation and memory storage

### Conversation repository

- `create_conversation(title)`
- `list_conversations(cursor, limit)`
- `get_messages(conversation_id, cursor, limit)`
- `append_turn(conversation_id, user_message, assistant_message)`
- `delete_conversation(conversation_id)`

A successful turn is persisted as one logical operation. History is not automatically promoted into long-term memory.

### Memory repository

- `save_memory(kind, content, metadata)`
- `search_memories(query, kinds, limit)`
- `list_memories(kind, limit)`
- `delete_memory(memory_id)`

Memory writes are explicit and attributable to a user action or a separately approved memory workflow. Retrieval returns provenance and relevance metadata. A memory item is never executable policy.

Android may implement these repositories with Room/SQLite. Python may keep the existing SQLite implementation. Both must pass the same repository contract tests.

## 4. Audio contracts

### Capture

`AudioCapture` exposes permission state, start, stop, and cancellation. A capture result contains:

- media type and encoding;
- sample rate and channel count when known;
- duration and byte length;
- an app-private file handle or stream, not an unrestricted filesystem path.

The UI displays a recording indicator while the microphone is active. Audio is not captured in the background without a distinct, user-visible feature and the required Android permission/service.

### Speech recognition and synthesis

- `SpeechToText.transcribe(audio)` returns text, language when known, and confidence when available.
- `TextToSpeech.synthesize(text, voice_id)` returns an audio stream or app-private audio asset plus codec metadata.
- Both report the engine used and whether external traffic occurred.
- No cloud fallback is permitted unless the user explicitly selected a remote provider for that operation.

Android can use native audio APIs and local engines. The current whisper.cpp/Piper adapters remain a prototype until tested with real audio on the phone.

## 5. Permission and capability broker

A platform adapter exposes:

- `query(capability)`: current state, such as `granted`, `denied`, `requires_user_action`, or `unsupported`.
- `request(capability, reason)`: launches the platform's official permission flow where possible.
- `revoke_or_disable(capability)`: stops use and clears app-held state when the platform supports it.

Capabilities are named and narrow, for example `microphone.capture`, `camera.capture`, `notifications.read`, `files.read_selected`, `location.foreground`, and `accessibility.interact`.

A permission grant is not a blanket authorization for every action using that capability. Sensitive actions still pass through Lia's action policy and may require a separate confirmation.

## 6. Tool execution and approval

A tool registration contains:

- stable `tool_id` and schema version;
- JSON input schema and output schema;
- required capabilities and data scopes;
- risk class: `read_only`, `reversible_write`, or `sensitive`;
- timeout and output-size limits.

Execution is a two-step protocol for writes:

1. `propose(tool_id, arguments)` validates the schema and policy, then returns a human-readable preview and an expiring `proposal_id`.
2. `approve_and_execute(proposal_id)` verifies that the proposal is unchanged, still authorized, and not expired before dispatch.

Read-only tools may execute directly when their capability is already granted. Every action records a local audit event with the tool, time, outcome, and approval reference. Secrets and full sensitive payloads are excluded from logs.

Lia Dev remains a separate, higher-trust tool surface. Its workspace allowlist, file protections, previews, approvals, tests, Git safeguards, and rollback rules are not inherited by ordinary chat tools.

## 7. Local bridge contract

When a separate runtime process is necessary:

- Bind only to `127.0.0.1` or an Android-supported local IPC mechanism. Never bind to `0.0.0.0` for local app communication.
- Prefer direct in-process interfaces where practical.
- Authenticate each bridge session with a high-entropy, short-lived secret generated by the app. Never place credentials in URLs, logs, or model context.
- On Android, persistent device credentials use Android Keystore. Session secrets should be rotated when the runtime restarts.
- Validate the peer, Host header, and request origin; do not expose browser CORS access.
- Enforce payload limits, timeouts, cancellation, and a strict route allowlist.
- The bridge exposes only the capabilities required by the native client. It does not expose Lia Dev or arbitrary filesystem/shell access.
- Remote-device pairing is a separate protocol and must never be reused as a shortcut for local app authentication.

## 8. Android mapping

| Contract | Android implementation direction |
|---|---|
| UI and lifecycle | Kotlin + Jetpack Compose |
| Local data | Room/SQLite in app-private storage |
| Preferences | DataStore |
| Device secrets | Android Keystore |
| Local model | llama.cpp through NDK/JNI, evaluated against optional Termux runtime |
| Audio capture/playback | AudioRecord / MediaRecorder and AudioTrack / platform playback |
| Files | Storage Access Framework and scoped storage |
| Notifications | NotificationListenerService after explicit user enablement |
| Background work | WorkManager or a foreground service when required |
| Optional UI automation | AccessibilityService, user-enabled and narrowly scoped |

These are implementation choices, not claims that each integration already exists.

## 9. Contract test requirements

Before the Android client is considered connected:

- Run shared fixtures against the Python implementation and Kotlin adapters.
- Verify request/response versioning, cancellation, timeouts, and malformed-input rejection.
- Verify that conversation history and explicit memories remain separate.
- Verify that missing/revoked permissions fail closed.
- Verify that tool arguments outside the schema are rejected and writes cannot execute without approval.
- Verify that local inference reports `external_traffic: false` and no remote provider is contacted when the local runtime fails.
- Verify app restart, model unload, low-memory recovery, and interrupted audio capture.
- Measure peak RAM, load time, tokens/second, thermal behavior, and battery use on the actual Galaxy A37.

## Current implementation status

The existing Python core already provides local inference adapters, SQLite history and memory, a bounded tool registry, Lia Dev approval flows, and prototype voice adapters. These interfaces are not yet unified behind all the contracts above. No native Android module, Android Keystore integration, or in-app llama.cpp runtime exists yet.
