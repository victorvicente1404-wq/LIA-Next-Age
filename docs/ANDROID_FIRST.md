# Android-first architecture

## Product decision

Android is Lia's primary platform. The first usable release must install and run directly on the user's Android phone; it must not require a PC, a hosted server, a Linux distribution, or a cloud AI quota.

Desktop support is a secondary deployment target. A PC may run the same Lia core and local model runtime when available, but it is not the default host and must not be required for normal phone use.

Termux is an optional development/runtime bridge for the first Android prototype. It may provide Python, Git, and llama.cpp without installing Ubuntu, Debian, proot, or another Linux distribution. The final Android experience must not require the user to operate a terminal.

## Platform responsibilities

### Native Android application (primary user experience)

The Android app owns:
- Chat, conversation history, settings, and memory controls.
- Microphone capture and audio playback, with clear recording/processing indicators.
- Android permission flows and platform integrations.
- Notifications and user-approved background work.
- A local bridge to the Lia core and model runtime.
- Device-protected credentials using Android Keystore where credentials are needed.
- A clear permission and action history for sensitive operations.

The native app should use Kotlin and Android platform APIs. Compose is the preferred UI direction unless an existing project constraint argues otherwise.

### Lia core (shared domain layer)

The Lia core remains responsible for:
- The assistant's identity, policies, and orchestration loop.
- Conversation and long-term memory semantics.
- Tool registry, schemas, permission checks, and approval workflow.
- Lia Dev plans, diffs, test execution, Git operations, and rollback.
- Provider-neutral inference contracts.

The core must not assume that it always runs in Termux, a browser, or a desktop process. Platform-specific capabilities are exposed through narrow, authenticated adapters.

### Local inference

Local inference is the default and must work without API credits:
- Keep llama.cpp as a supported inference backend.
- On Android, evaluate a native llama.cpp/NDK integration against a local Termux llama-server process.
- Prefer an in-process/native runtime for the polished Android release if memory, thermal behavior, model loading, and lifecycle tests support it.
- Keep model selection and quantization configurable. On a 6 GB device, start with compact quantized models and conservative context sizes; do not promise a model will fit without measuring actual peak RAM.
- Remote model providers remain explicit, optional adapters. No silent cloud fallback.

### Optional Termux bridge

Termux may be used during development or as an early runtime:
- Install Termux only; do not require a proot Linux distribution.
- Keep all data under Termux's private home or an explicitly approved shared directory.
- Do not ask the user to manually maintain multiple terminal sessions as the permanent product experience.
- The native app should eventually manage the backend lifecycle or replace the Termux process with an in-app runtime.
- Do not grant Termux broad Android permissions as a substitute for a native platform adapter.

### Desktop

Desktop support should reuse the core contracts and domain behavior. It may use a desktop-specific launcher, UI, and local model process. It must not become the central server that the phone depends on.

## Android capability model

Lia may offer broad device integration, but Android permissions remain explicit and user-controlled. Implement capabilities through the narrowest supported platform mechanism:

- App-specific data and user-selected files: Android Storage Access Framework and scoped storage.
- Notifications: notification-listener access only after the user enables it in Android settings.
- UI interaction: Accessibility Service only as an optional, clearly explained capability, enabled manually by the user; never attempt to bypass Android permission prompts.
- Camera and microphone: runtime permissions and visible use indicators.
- Location: only when a feature needs it, with foreground/background permission handling appropriate to that feature.
- Background actions: WorkManager or a foreground service where Android policy requires it; respect battery optimization and background execution limits.
- Other apps and protected settings: use public intents, documented APIs, or user confirmation. Do not promise unrestricted control of every app or system setting.

The fact that Lia is intended for one owner simplifies account and sharing design; it does not bypass Android's security model.

## Security boundaries

- The model never receives unrestricted shell, filesystem, accessibility, or Git access.
- Every capability is registered with a typed schema and a permission policy.
- Sensitive actions show the proposed action and request approval before execution.
- Android credentials belong in Android Keystore, not browser localStorage or a plaintext file.
- Termux and desktop runtimes use separate local credential storage appropriate to their platform.
- Remote pairing remains disabled by default until HTTPS, trusted proxy behavior, origin checks, replay protection, scopes, revocation, and real-device tests are complete.
- Remote devices do not gain Lia Dev, memory-write, or arbitrary device-control access by default.

## Delivery sequence

1. Finish the current core foundation and its security review without merging an unvalidated runtime.
2. Define stable platform-neutral contracts for local inference, storage, audio, permissions, and tool execution.
3. Create the native Android shell and connect it to the existing core through a loopback-only bridge.
4. Validate local chat, conversation history, persistent memory, and one local model on the actual phone.
5. Add native voice and Android capabilities incrementally, each with permission UX and tests.
6. Make Termux optional in the normal launch flow; evaluate an in-app llama.cpp runtime and background lifecycle.
7. Add desktop packaging using the same core contracts.
8. Validate performance, thermal behavior, battery impact, recovery, backups, and upgrade/rollback before calling the Android release stable.

## Current status

This is the target architecture, not a claim that a native Android app already exists. The current repository contains a Python core and a responsive web client. It has no native Android application module yet, and the current voice and pairing implementations have not been validated end-to-end on a physical Android device.
