# Android local inference

## Decision

Lia's Android application will own local inference in-process through a native Android library built with the Android NDK. A Termux server may remain an optional developer/debug adapter, but it is not the production runtime and is not required to open or use Lia.

The initial backend candidate is llama.cpp with GGUF models. The Android integration will be isolated behind the platform-neutral inference contract in `docs/PLATFORM_CONTRACTS.md`; the conversation UI and memory repository must not call JNI directly.

## Why this path

- The upstream llama.cpp project documents an Android Studio binding under `examples/llama.android`, including GGUF metadata reading, model loading from app-private storage, and token streaming through Kotlin Flow.
- Its Android build documentation supports `arm64-v8a` through the Android NDK. The current portable CMake configuration uses Android API 28, disables host-native tuning, OpenMP, llamafile, and OpenSSL, and can enable Arm KleidiAI for arm64.
- Packaging the native libraries inside the APK removes the need for a separately running shell process, localhost server, PC, or remote inference API.
- Keeping the inference adapter behind a Kotlin interface allows replacing or benchmarking the backend without rewriting chat, memory, or UI.

## Upstream integration review

The official Android binding was inspected at llama.cpp commit `cbb1c1c50bba81929387dea473873d1df87a6212` (2026-11-21). Its project license is MIT; retain the upstream copyright and license notice if any source is copied or redistributed.

The sample provides a Kotlin `InferenceEngine` API, token streaming, GGUF metadata reader, and JNI/C++ implementation. However, its current Android library sample declares `minSdk = 33`, `ndkVersion = 29.0.13113456`, and CMake 3.31.6, while Lia currently targets `minSdk = 26` and a lower compile SDK. It is therefore not safe to add the sample as a drop-in dependency without an explicit compatibility decision and CI toolchain update. The sample also contains an app-specific singleton/lifecycle design that should not be adopted unchanged.

Lia now defines its own Kotlin boundary in `apps/android/.../inference/LiaInferenceEngine.kt`. The planned adapter will own native model lifecycle and streaming, while Lia retains control of conversation context, persistence, cancellation, and policy. Before implementation, choose whether to raise the minimum Android version or build a smaller JNI adapter against a pinned llama.cpp source revision; do not silently change supported Android versions.

## Runtime boundaries

1. The user chooses/imports a compatible GGUF model through Android's Storage Access Framework. Lia copies it into app-private model storage only after checking available space and confirming the action.
2. Model files are not embedded in the APK. This keeps the app package small and makes model licensing, replacement, and storage usage explicit.
3. Model loading, prompt evaluation, token generation, and unloading run away from the main thread. The UI receives incremental output through Kotlin Flow.
4. The runtime exposes explicit states: unavailable, importing, ready, loading, generating, stopping, and failed. Errors must be actionable; there is no silent remote fallback.
5. The runtime has one active model at a time initially. It must release native contexts and file handles when unloaded and handle Activity/process recreation safely.
6. The model receives only the conversation context assembled by Lia. It does not get direct access to SQLite, Android APIs, files, or tools.
7. Tool calls remain structured proposals dispatched by Lia's policy layer, never arbitrary native commands.

## Device constraints and first benchmark

The target phone has 6 GB RAM. Do not assume a model size or context length before measuring it. Start with a small, permissively licensed quantized GGUF candidate and benchmark at least:

- cold load time and peak memory;
- prompt processing and generated tokens per second;
- memory pressure while the UI and Android system remain active;
- sustained thermal behavior and battery drain;
- cancellation, backgrounding, process death, and model unload/reload;
- Portuguese instruction following and output quality on a fixed local test set.

The first safe profile should use conservative context and generation limits, then expose advanced tuning only after stability is demonstrated. A model that causes Android to kill Lia or other foreground apps is not an acceptable default.

## Build and integration stages

- [x] Choose Android-native NDK packaging over a mandatory Termux server.
- [x] Define the separation between UI, repository, inference adapter, and policy/orchestrator.
- [x] Inspect and pin the upstream llama.cpp Android integration revision and its license.
- [ ] Add the NDK/CMake native module and Kotlin JNI boundary.
- [x] Add the initial GGUF import primitive, app-private copy, size/hash checks, and partial-file cleanup.
- [x] Connect the Storage Access Framework picker and app-private model import flow in the Android UI.
- [x] Add a persistent model catalog reconstructed from app-private GGUF files, with header and SHA-256 filename verification.
- [ ] Parse complete GGUF metadata and validate runtime compatibility.
- [ ] Add streaming generation and cancellation.
- [ ] Add deterministic native smoke tests and CI packaging.
- [ ] Benchmark on the actual Galaxy A37 before enabling chat by default.

## Model import implementation status

`LiaModelStore` now provides the first Android-side import primitive. It accepts a Storage Access Framework `Uri`, copies the selected file into app-private model storage, checks the GGUF magic header, enforces a configurable maximum file size (3 GiB by default), checks available storage while copying, computes SHA-256, uses a temporary file plus final rename, and removes partial files after failure. The display name is sanitized and never used as a path by itself. The importer does not retain the source URI or request broad storage permissions.

This is intentionally only the import foundation: the current check does not yet parse the complete GGUF metadata or establish that a model architecture, tokenizer, quantization, and context configuration are supported. The native Storage Access Framework picker is connected to the import primitive. The app now rebuilds its catalog on launch by scanning only regular `.gguf` files in app-private storage, validating the GGUF magic header, recomputing SHA-256, and checking that the digest matches the stored filename prefix. Invalid, partial, renamed, or modified files are omitted from the catalog. The UI lists recovered models after process restart and explicitly labels them as imported but not loaded. Full GGUF metadata inspection and runtime compatibility checks remain before any imported file can be loaded. The catalog is derived from private files rather than a separate mutable index, so it cannot become stale independently of the files. The UI must not label a file as ready merely because its header is valid.

## Safety and privacy

- Model inference is offline by default. Network permission is not required for local inference itself.
- Never download model files without the user's explicit selection/approval.
- Verify model source, license, file size, and SHA-256 before import where metadata is available.
- Do not log prompts, completions, memory contents, or model paths in production logs.
- Do not enable remote pairing or expose the native model runtime over LAN as part of this integration.
- Keep the UI honest: if no model is installed or the native library is unavailable, explain that instead of generating placeholder replies.

## Upstream references

- llama.cpp Android integration: https://github.com/ggml-org/llama.cpp/tree/master/examples/llama.android
- llama.cpp Android build guidance: https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md
- llama.cpp portable Android NDK build options: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
