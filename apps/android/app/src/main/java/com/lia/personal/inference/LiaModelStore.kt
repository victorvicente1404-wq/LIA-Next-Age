package com.lia.personal.inference

import android.content.ContentResolver
import android.net.Uri
import android.os.StatFs
import android.provider.OpenableColumns
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.security.MessageDigest

/**
 * Imports user-selected GGUF files into app-private storage.
 *
 * The source URI is read only for this operation; Lia does not retain broad
 * storage permissions. Partial files are deleted on every failed import.
 */
class LiaModelStore(
    private val contentResolver: ContentResolver,
    private val modelsDirectory: File,
    private val maxModelBytes: Long = DEFAULT_MAX_MODEL_BYTES,
) {
    init {
        require(maxModelBytes > 0) { "Limite de tamanho inválido." }
    }

    fun importModel(source: Uri): ImportedModel {
        val displayName = queryDisplayName(source)
        val declaredSize = querySize(source)
        if (declaredSize != null && declaredSize > maxModelBytes) {
            throw ModelImportException("MODEL_TOO_LARGE")
        }

        if (!modelsDirectory.exists() && !modelsDirectory.mkdirs()) {
            throw ModelImportException("STORAGE_UNAVAILABLE")
        }
        if (!modelsDirectory.isDirectory || !modelsDirectory.canWrite()) {
            throw ModelImportException("STORAGE_UNAVAILABLE")
        }

        val availableBytes = StatFs(modelsDirectory.absolutePath).availableBytes
        if (declaredSize != null && declaredSize > availableBytes) {
            throw ModelImportException("INSUFFICIENT_SPACE")
        }

        val input = contentResolver.openInputStream(source)
            ?: throw ModelImportException("SOURCE_UNAVAILABLE")
        val temporary = File.createTempFile("lia-model-", ".part", modelsDirectory)
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            var copied = 0L
            input.use { stream ->
                FileOutputStream(temporary).use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    val header = ByteArray(GGUF_MAGIC.size)
                    var headerBytes = 0
                    while (true) {
                        val count = stream.read(buffer)
                        if (count < 0) break
                        if (count == 0) continue
                        copied += count
                        if (copied > maxModelBytes) {
                            throw ModelImportException("MODEL_TOO_LARGE")
                        }
                        if (copied > availableBytes) {
                            throw ModelImportException("INSUFFICIENT_SPACE")
                        }
                        if (headerBytes < header.size) {
                            val take = minOf(count, header.size - headerBytes)
                            buffer.copyInto(header, headerBytes, 0, take)
                            headerBytes += take
                        }
                        digest.update(buffer, 0, count)
                        output.write(buffer, 0, count)
                    }
                    output.fd.sync()
                    if (headerBytes != GGUF_MAGIC.size || !hasGgufMagic(header)) {
                        throw ModelImportException("INVALID_GGUF")
                    }
                }
            }

            if (declaredSize != null && copied != declaredSize) {
                throw ModelImportException("SOURCE_SIZE_MISMATCH")
            }

            val sha256 = digest.digest().joinToString("") { "%02x".format(it) }
            val safeName = sanitizeName(displayName)
            val destination = File(modelsDirectory, "${sha256.take(16)}-$safeName.gguf")
            if (destination.exists()) {
                temporary.delete()
                return ImportedModel(destination, displayName, copied, sha256, alreadyPresent = true)
            }
            if (!temporary.renameTo(destination)) {
                throw ModelImportException("FINALIZE_FAILED")
            }
            return ImportedModel(destination, displayName, copied, sha256, alreadyPresent = false)
        } catch (error: ModelImportException) {
            throw error
        } catch (_: SecurityException) {
            throw ModelImportException("SOURCE_PERMISSION_DENIED")
        } catch (_: IOException) {
            throw ModelImportException("IMPORT_IO_ERROR")
        } finally {
            if (temporary.exists()) temporary.delete()
        }
    }

    private fun queryDisplayName(uri: Uri): String {
        return try {
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                        if (index >= 0) cursor.getString(index) else null
                    } else null
                }?.takeIf { it.isNotBlank() } ?: "modelo"
        } catch (_: Exception) {
            "modelo"
        }
    }

    private fun querySize(uri: Uri): Long? {
        return try {
            contentResolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)
                ?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        val index = cursor.getColumnIndex(OpenableColumns.SIZE)
                        if (index >= 0 && !cursor.isNull(index)) cursor.getLong(index) else null
                    } else null
                }?.takeIf { it >= 0 }
        } catch (_: Exception) {
            null
        }
    }

    companion object {
        const val DEFAULT_MAX_MODEL_BYTES = 3L * 1024 * 1024 * 1024
        private val GGUF_MAGIC = byteArrayOf(0x47, 0x47, 0x55, 0x46)

        internal fun sanitizeName(name: String): String {
            val withoutExtension = name.substringBeforeLast('.', name)
            return withoutExtension
                .lowercase()
                .replace(Regex("[^a-z0-9_-]+"), "-")
                .trim('-', '_')
                .take(48)
                .ifBlank { "modelo" }
        }

        internal fun hasGgufMagic(header: ByteArray): Boolean =
            header.size >= GGUF_MAGIC.size &&
                header.copyOfRange(0, GGUF_MAGIC.size).contentEquals(GGUF_MAGIC)
    }
}

data class ImportedModel(
    val file: File,
    val originalName: String,
    val sizeBytes: Long,
    val sha256: String,
    val alreadyPresent: Boolean,
)

class ModelImportException(val diagnosticCode: String) : Exception(diagnosticCode)
