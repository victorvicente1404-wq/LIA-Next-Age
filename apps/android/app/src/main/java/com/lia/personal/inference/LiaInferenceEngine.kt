package com.lia.personal.inference

import java.io.File
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow

/**
 * Platform-facing inference boundary.
 *
 * The UI, conversation repository, and memory repository must not call JNI
 * or a provider SDK directly. Implementations own model-specific details and
 * expose incremental output through [Flow].
 */
interface LiaInferenceEngine {
    val status: StateFlow<InferenceStatus>

    /** Loads a user-selected model already copied into Lia's private storage. */
    suspend fun loadModel(modelFile: File)

    /**
     * Generates a response from an explicit, bounded conversation snapshot.
     * Implementations must not access the repository or Android tools.
     */
    fun generate(
        messages: List<LiaPromptMessage>,
        maxTokens: Int = DEFAULT_MAX_TOKENS,
    ): Flow<String>

    /** Requests cancellation of the active generation, if any. */
    fun cancelGeneration()

    /** Releases native model/context resources. Safe to call more than once. */
    suspend fun unload()

    companion object {
        const val DEFAULT_MAX_TOKENS = 512
    }
}

/** A deliberately small prompt DTO; persistence entities never cross this boundary. */
data class LiaPromptMessage(
    val role: Role,
    val content: String,
) {
    enum class Role {
        SYSTEM,
        USER,
        ASSISTANT,
    }
}

/**
 * Safe runtime status. Do not place prompts, model paths, or exception messages
 * in this state because it may be rendered in the UI or diagnostic logs.
 */
sealed interface InferenceStatus {
    data object Unavailable : InferenceStatus
    data object Loading : InferenceStatus
    data class Ready(
        val modelName: String,
        val engineId: String = "llama.cpp",
        val externalTraffic: Boolean = false,
    ) : InferenceStatus
    data object Generating : InferenceStatus
    data class Failed(val diagnosticCode: String) : InferenceStatus
}
