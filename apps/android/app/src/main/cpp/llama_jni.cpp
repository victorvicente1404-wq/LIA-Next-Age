#include <jni.h>
#include <android/log.h>
#include <llama.h>

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#define LOG_TAG "LiaLlama"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace {
std::mutex g_mutex;
std::atomic<bool> g_cancelled{false};
bool g_backend_initialized = false;
llama_model * g_model = nullptr;
llama_context * g_context = nullptr;
llama_sampler * g_sampler = nullptr;
llama_batch g_batch{};
int32_t g_position = 0;
int32_t g_max_tokens = 0;
int32_t g_generated = 0;
bool g_batch_initialized = false;
std::string g_utf8_pending;
constexpr uint32_t CONTEXT_SIZE = 2048;
constexpr int32_t BATCH_SIZE = 128;

void release_model_locked() {
    if (g_sampler) {
        llama_sampler_free(g_sampler);
        g_sampler = nullptr;
    }
    if (g_batch_initialized) {
        llama_batch_free(g_batch);
        g_batch = {};
        g_batch_initialized = false;
    }
    if (g_context) {
        llama_free(g_context);
        g_context = nullptr;
    }
    if (g_model) {
        llama_model_free(g_model);
        g_model = nullptr;
    }
    g_position = 0;
    g_generated = 0;
    g_utf8_pending.clear();
}

void append_utf8(std::string & output, uint32_t codepoint) {
    if (codepoint <= 0x7F) {
        output.push_back(static_cast<char>(codepoint));
    } else if (codepoint <= 0x7FF) {
        output.push_back(static_cast<char>(0xC0 | (codepoint >> 6)));
        output.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    } else if (codepoint <= 0xFFFF) {
        output.push_back(static_cast<char>(0xE0 | (codepoint >> 12)));
        output.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
        output.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    } else {
        output.push_back(static_cast<char>(0xF0 | (codepoint >> 18)));
        output.push_back(static_cast<char>(0x80 | ((codepoint >> 12) & 0x3F)));
        output.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
        output.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    }
}

std::string jstring_to_string(JNIEnv * env, jstring value) {
    if (!value) return {};
    const jsize length = env->GetStringLength(value);
    const jchar * chars = env->GetStringChars(value, nullptr);
    if (!chars) return {};
    std::string result;
    result.reserve(static_cast<size_t>(length) * 3);
    for (jsize i = 0; i < length; ++i) {
        uint32_t codepoint = chars[i];
        if (codepoint >= 0xD800 && codepoint <= 0xDBFF && i + 1 < length) {
            const uint32_t low = chars[i + 1];
            if (low >= 0xDC00 && low <= 0xDFFF) {
                codepoint = 0x10000 + ((codepoint - 0xD800) << 10) + (low - 0xDC00);
                ++i;
            }
        }
        append_utf8(result, codepoint);
    }
    env->ReleaseStringChars(value, chars);
    return result;
}

jstring utf8_to_jstring(JNIEnv * env, const std::string & value) {
    std::vector<jchar> utf16;
    utf16.reserve(value.size());
    const auto * bytes = reinterpret_cast<const unsigned char *>(value.data());
    size_t i = 0;
    while (i < value.size()) {
        const unsigned char first = bytes[i++];
        uint32_t codepoint = first;
        if ((first & 0xE0) == 0xC0) {
            codepoint = (first & 0x1F) << 6;
            codepoint |= bytes[i++] & 0x3F;
        } else if ((first & 0xF0) == 0xE0) {
            codepoint = (first & 0x0F) << 12;
            codepoint |= (bytes[i++] & 0x3F) << 6;
            codepoint |= bytes[i++] & 0x3F;
        } else if ((first & 0xF8) == 0xF0) {
            codepoint = (first & 0x07) << 18;
            codepoint |= (bytes[i++] & 0x3F) << 12;
            codepoint |= (bytes[i++] & 0x3F) << 6;
            codepoint |= bytes[i++] & 0x3F;
        }
        if (codepoint <= 0xFFFF) {
            utf16.push_back(static_cast<jchar>(codepoint));
        } else {
            codepoint -= 0x10000;
            utf16.push_back(static_cast<jchar>(0xD800 + (codepoint >> 10)));
            utf16.push_back(static_cast<jchar>(0xDC00 + (codepoint & 0x3FF)));
        }
    }
    if (utf16.empty()) { const jchar empty = 0; return env->NewString(&empty, 0); }
    return env->NewString(utf16.data(), static_cast<jsize>(utf16.size()));
}

bool valid_utf8(const std::string & value) {
    const auto * p = reinterpret_cast<const unsigned char *>(value.data());
    size_t i = 0;
    while (i < value.size()) {
        const unsigned char c = p[i];
        size_t count = 0;
        if ((c & 0x80) == 0) count = 1;
        else if ((c & 0xE0) == 0xC0) count = 2;
        else if ((c & 0xF0) == 0xE0) count = 3;
        else if ((c & 0xF8) == 0xF0) count = 4;
        else return false;
        if (i + count > value.size()) return false;
        for (size_t j = 1; j < count; ++j) {
            if ((p[i + j] & 0xC0) != 0x80) return false;
        }
        i += count;
    }
    return true;
}

bool decode_prompt_tokens(const std::vector<llama_token> & tokens) {
    if (tokens.empty() || tokens.size() >= CONTEXT_SIZE - 8) return false;
    if (g_batch_initialized) {
        llama_batch_free(g_batch);
        g_batch = {};
        g_batch_initialized = false;
    }
    g_batch = llama_batch_init(BATCH_SIZE, 0, 1);
    g_batch_initialized = true;
    if (!g_batch.token || !g_batch.pos || !g_batch.n_seq_id || !g_batch.seq_id || !g_batch.logits) {
        return false;
    }
    for (size_t offset = 0; offset < tokens.size(); offset += BATCH_SIZE) {
        const size_t count = std::min<size_t>(BATCH_SIZE, tokens.size() - offset);
        g_batch.n_tokens = static_cast<int32_t>(count);
        for (size_t i = 0; i < count; ++i) {
            const size_t index = offset + i;
            g_batch.token[i] = tokens[index];
            g_batch.pos[i] = static_cast<llama_pos>(index);
            g_batch.n_seq_id[i] = 1;
            g_batch.seq_id[i][0] = 0;
            g_batch.logits[i] = (index == tokens.size() - 1) ? 1 : 0;
        }
        if (llama_decode(g_context, g_batch) != 0) return false;
    }
    g_position = static_cast<int32_t>(tokens.size());
    return true;
}

bool prepare_prompt(const std::vector<std::string> & roles,
                    const std::vector<std::string> & contents,
                    std::vector<llama_token> & tokens) {
    if (roles.empty() || roles.size() != contents.size() || roles.size() > 32) return false;

    std::vector<llama_chat_message> messages;
    messages.reserve(roles.size());
    for (size_t i = 0; i < roles.size(); ++i) {
        messages.push_back({roles[i].c_str(), contents[i].c_str()});
    }

    const char * chat_template = llama_model_chat_template(g_model, nullptr);
    std::string prompt;
    bool template_applied = false;
    if (chat_template) {
        std::vector<char> formatted(32768);
        int32_t required = llama_chat_apply_template(
            chat_template, messages.data(), messages.size(), true,
            formatted.data(), static_cast<int32_t>(formatted.size()));
        if (required >= 0) {
            if (required >= static_cast<int32_t>(formatted.size())) {
                if (required > 128 * 1024) return false;
                formatted.resize(static_cast<size_t>(required) + 1);
                required = llama_chat_apply_template(
                    chat_template, messages.data(), messages.size(), true,
                    formatted.data(), static_cast<int32_t>(formatted.size()));
            }
            if (required >= 0 && required < static_cast<int32_t>(formatted.size())) {
                prompt.assign(formatted.data(), static_cast<size_t>(required));
                template_applied = true;
            }
        }
    }
    if (!template_applied) {
        for (size_t i = 0; i < roles.size(); ++i) {
            prompt += roles[i] + ":\\n" + contents[i] + "\\n";
        }
        prompt += "assistant:\\n";
    }

    const llama_vocab * vocab = llama_model_get_vocab(g_model);
    int32_t count = llama_tokenize(vocab, prompt.data(),
        static_cast<int32_t>(prompt.size()), nullptr, 0, true, false);
    if (count >= 0) return false;
    tokens.resize(static_cast<size_t>(-count));
    count = llama_tokenize(vocab, prompt.data(),
        static_cast<int32_t>(prompt.size()), tokens.data(),
        static_cast<int32_t>(tokens.size()), true, false);
    if (count <= 0 || count >= static_cast<int32_t>(CONTEXT_SIZE - 8)) return false;
    tokens.resize(static_cast<size_t>(count));
    return true;
}
} // namespace

extern "C" JNIEXPORT jboolean JNICALL
Java_com_lia_personal_inference_LlamaCppInferenceEngine_nativeLoadModel(
    JNIEnv * env, jobject, jstring model_path, jint threads) {
    std::lock_guard<std::mutex> lock(g_mutex);
    release_model_locked();
    const std::string path = jstring_to_string(env, model_path);
    if (path.empty()) return JNI_FALSE;

    if (!g_backend_initialized) {
        llama_backend_init();
        g_backend_initialized = true;
    }

    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0;
    g_model = llama_model_load_from_file(path.c_str(), model_params);
    if (!g_model || llama_model_has_encoder(g_model) || !llama_model_has_decoder(g_model)) {
        release_model_locked();
        return JNI_FALSE;
    }

    llama_context_params context_params = llama_context_default_params();
    context_params.n_ctx = CONTEXT_SIZE;
    context_params.n_batch = BATCH_SIZE;
    context_params.n_ubatch = BATCH_SIZE;
    const int32_t safe_threads = std::max(1, std::min(4, static_cast<int32_t>(threads)));
    context_params.n_threads = safe_threads;
    context_params.n_threads_batch = safe_threads;
    context_params.offload_kqv = false;
    g_context = llama_init_from_model(g_model, context_params);
    if (!g_context) {
        release_model_locked();
        return JNI_FALSE;
    }
    auto sampler_params = llama_sampler_chain_default_params();
    g_sampler = llama_sampler_chain_init(sampler_params);
    if (!g_sampler) {
        release_model_locked();
        return JNI_FALSE;
    }
    llama_sampler_chain_add(g_sampler, llama_sampler_init_greedy());
    return JNI_TRUE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_lia_personal_inference_LlamaCppInferenceEngine_nativeBeginPrompt(
    JNIEnv * env, jobject, jobjectArray role_array, jobjectArray content_array, jint max_tokens) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_model || !g_context || !g_sampler || !role_array || !content_array) return JNI_FALSE;
    const jsize count = env->GetArrayLength(role_array);
    if (count <= 0 || count > 32 || env->GetArrayLength(content_array) != count) return JNI_FALSE;

    std::vector<std::string> roles;
    std::vector<std::string> contents;
    roles.reserve(count);
    contents.reserve(count);
    size_t total_chars = 0;
    for (jsize i = 0; i < count; ++i) {
        auto role = static_cast<jstring>(env->GetObjectArrayElement(role_array, i));
        auto content = static_cast<jstring>(env->GetObjectArrayElement(content_array, i));
        roles.push_back(jstring_to_string(env, role));
        contents.push_back(jstring_to_string(env, content));
        if (role) env->DeleteLocalRef(role);
        if (content) env->DeleteLocalRef(content);
        total_chars += contents.back().size();
        if (total_chars > 96 * 1024) return JNI_FALSE;
        if (roles.back() != "system" && roles.back() != "user" && roles.back() != "assistant") return JNI_FALSE;
    }

    std::vector<llama_token> tokens;
    if (!prepare_prompt(roles, contents, tokens)) return JNI_FALSE;
    llama_memory_clear(llama_get_memory(g_context), true);
    llama_sampler_reset(g_sampler);
    g_utf8_pending.clear();
    g_generated = 0;
    g_max_tokens = std::max(1, std::min(256, static_cast<int32_t>(max_tokens)));
    g_cancelled.store(false);
    return decode_prompt_tokens(tokens) ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_lia_personal_inference_LlamaCppInferenceEngine_nativeNextToken(
    JNIEnv * env, jobject) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_context || !g_model || !g_sampler || g_cancelled.load() || g_generated >= g_max_tokens) {
        return nullptr;
    }

    const llama_vocab * vocab = llama_model_get_vocab(g_model);
    const llama_token token = llama_sampler_sample(g_sampler, g_context, -1);
    llama_sampler_accept(g_sampler, token);
    ++g_generated;
    if (llama_vocab_is_eog(vocab, token)) return nullptr;

    char piece[512];
    int32_t piece_size = llama_token_to_piece(vocab, token, piece, sizeof(piece), 0, false);
    if (piece_size < 0) return nullptr;
    g_utf8_pending.append(piece, static_cast<size_t>(piece_size));

    g_batch.n_tokens = 1;
    g_batch.token[0] = token;
    g_batch.pos[0] = g_position++;
    g_batch.n_seq_id[0] = 1;
    g_batch.seq_id[0][0] = 0;
    g_batch.logits[0] = 1;
    if (llama_decode(g_context, g_batch) != 0) return nullptr;

    if (!valid_utf8(g_utf8_pending)) return env->NewStringUTF("");
    jstring output = utf8_to_jstring(env, g_utf8_pending);
    g_utf8_pending.clear();
    return output;
}

extern "C" JNIEXPORT void JNICALL
Java_com_lia_personal_inference_LlamaCppInferenceEngine_nativeCancel(
    JNIEnv *, jobject) {
    g_cancelled.store(true);
}

extern "C" JNIEXPORT void JNICALL
Java_com_lia_personal_inference_LlamaCppInferenceEngine_nativeUnload(
    JNIEnv *, jobject) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_cancelled.store(true);
    release_model_locked();
}

