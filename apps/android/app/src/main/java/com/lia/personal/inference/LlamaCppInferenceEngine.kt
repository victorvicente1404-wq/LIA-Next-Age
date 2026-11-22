package com.lia.personal.inference

import android.app.ActivityManager
import android.content.Context
import android.util.Log
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * llama.cpp CPU runtime embedded in the Android application.
 *
 * No network client, local HTTP server, Termux process, or external API is
 * used. Native source is pinned in CMakeLists.txt.
 */
class LlamaCppInferenceEngine(context: Context) : LiaInferenceEngine {
    private val appContext = context.applicationContext
    private val mutableStatus = MutableStateFlow<InferenceStatus>(InferenceStatus.Unavailable)
    override val status: StateFlow<InferenceStatus> = mutableStatus.asStateFlow()
    private val generationMutex = Mutex()
    private val loaded = AtomicBoolean(false)
    @Volatile private var loadedModelName: String = "modelo local"

    private external fun nativeLoadModel(modelPath: String, threads: Int): Boolean
    private external fun nativeBeginPrompt(roles: Array<String>, contents: Array<String>, maxTokens: Int): Boolean
    private external fun nativeNextToken(): String?
    private external fun nativeCancel()
    private external fun nativeUnload()

    init {
        try {
            System.loadLibrary("lia_llama_jni")
        } catch (_: UnsatisfiedLinkError) {
            mutableStatus.value = InferenceStatus.Failed("NATIVE_LIBRARY_UNAVAILABLE")
        }
    }

    override suspend fun loadModel(modelFile: File) {
        generationMutex.withLock {
            loaded.set(false)
            mutableStatus.value = InferenceStatus.Loading
            try {
                val ready = withContext(Dispatchers.IO) {
                    require(modelFile.isFile && modelFile.canRead()) { "MODEL_FILE_UNAVAILABLE" }
                    val activityManager = appContext.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
                    val memoryInfo = ActivityManager.MemoryInfo()
                    activityManager?.getMemoryInfo(memoryInfo)
                    if (activityManager != null) {
                        val availableBytes = memoryInfo.availMem
                        val minimumBytes = MIN_FREE_MEMORY_BEFORE_LOAD
                        Log.i(
                            LOG_TAG,
                            "Pre-load memory: availableMiB=${availableBytes / MIB}, " +
                                "minimumMiB=${minimumBytes / MIB}, modelMiB=${modelFile.length() / MIB}, " +
                                "lowMemory=${memoryInfo.lowMemory}"
                        )
                        // GGUF weights are memory-mapped by llama.cpp. Requiring the
                        // entire file size as immediately free RAM double-counts pages
                        // that the OS can map/reclaim and rejects otherwise viable loads.
                        // Keep a real safety floor and respect Android's low-memory signal.
                        if (memoryInfo.lowMemory || availableBytes < minimumBytes) {
                            mutableStatus.value = InferenceStatus.Failed("INSUFFICIENT_MEMORY")
                            throw IllegalStateException("INSUFFICIENT_MEMORY")
                        }
                    }
                    nativeLoadModel(modelFile.absolutePath, Runtime.getRuntime().availableProcessors())
                }
                if (!ready) {
                    loaded.set(false)
                    mutableStatus.value = InferenceStatus.Failed("MODEL_LOAD_FAILED")
                    throw IllegalStateException("MODEL_LOAD_FAILED")
                }
                loaded.set(true)
                loadedModelName = modelFile.name
                mutableStatus.value = InferenceStatus.Ready(loadedModelName)
            } catch (error: UnsatisfiedLinkError) {
                loaded.set(false)
                mutableStatus.value = InferenceStatus.Failed("NATIVE_LIBRARY_UNAVAILABLE")
                throw IllegalStateException("NATIVE_LIBRARY_UNAVAILABLE", error)
            } catch (error: Exception) {
                if (mutableStatus.value !is InferenceStatus.Failed) {
                    mutableStatus.value = InferenceStatus.Failed("MODEL_LOAD_FAILED")
                }
                throw error
            }
        }
    }

    override fun generate(messages: List<LiaPromptMessage>, maxTokens: Int): Flow<String> = flow {
        generationMutex.withLock {
            check(loaded.get()) { "MODEL_NOT_LOADED" }
            require(messages.isNotEmpty()) { "PROMPT_EMPTY" }
            require(messages.size <= MAX_PROMPT_MESSAGES) { "PROMPT_TOO_LARGE" }
            mutableStatus.value = InferenceStatus.Generating
            try {
                val roles = messages.map { it.role.name.lowercase() }.toTypedArray()
                val contents = messages.map { it.content.take(MAX_MESSAGE_CHARS) }.toTypedArray()
                val prepared = withContext(Dispatchers.IO) {
                    nativeBeginPrompt(roles, contents, maxTokens.coerceIn(1, MAX_GENERATION_TOKENS))
                }
                check(prepared) { "PROMPT_REJECTED" }

                while (true) {
                    currentCoroutineContext().ensureActive()
                    val token = withContext(Dispatchers.Default) { nativeNextToken() } ?: break
                    if (token.isNotEmpty()) emit(token)
                }
            } finally {
                if (loaded.get()) {
                    nativeCancel()
                    mutableStatus.value = InferenceStatus.Ready(loadedModelName)
                }
            }
        }
    }

    override fun cancelGeneration() {
        if (loaded.get()) {
            try {
                nativeCancel()
            } catch (_: UnsatisfiedLinkError) {
                // The runtime may already be unavailable during process teardown.
            }
        }
    }

    override suspend fun unload() {
        cancelGeneration()
        generationMutex.withLock {
            withContext(Dispatchers.IO) {
                if (loaded.getAndSet(false)) nativeUnload()
            }
            mutableStatus.value = InferenceStatus.Unavailable
        }
    }

    companion object {
        private const val MAX_PROMPT_MESSAGES = 32
        private const val MAX_MESSAGE_CHARS = 32_000
        private const val MAX_GENERATION_TOKENS = 256
        private const val LOG_TAG = "LiaInference"
        private const val MIB = 1024L * 1024
        private const val MIN_FREE_MEMORY_BEFORE_LOAD = 768L * MIB
    }
}
