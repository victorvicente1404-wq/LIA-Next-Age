package com.lia.personal.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.util.UUID

data class LiaConversation(
    val id: String,
    val title: String,
    val createdAt: Long,
    val updatedAt: Long,
)

data class LiaMessage(
    val id: String,
    val conversationId: String,
    val role: String,
    val content: String,
    val createdAt: Long,
)

data class LiaMemory(
    val id: String,
    val kind: String,
    val content: String,
    val createdAt: Long,
)

class LiaStore(context: Context) : SQLiteOpenHelper(
    context.applicationContext,
    DATABASE_NAME,
    null,
    DATABASE_VERSION,
) {
    override fun onConfigure(db: SQLiteDatabase) {
        super.onConfigure(db)
        db.setForeignKeyConstraintsEnabled(true)
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY NOT NULL,
                title TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE messages (
                id TEXT PRIMARY KEY NOT NULL,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE INDEX messages_conversation_time
            ON messages(conversation_id, created_at)
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE memories (
                id TEXT PRIMARY KEY NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL("CREATE INDEX memories_kind_time ON memories(kind, created_at)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // Schema migrations are added here before incrementing DATABASE_VERSION.
    }

    fun createConversation(title: String): LiaConversation {
        val cleanTitle = title.trim().ifEmpty { "Nova conversa" }.take(MAX_TITLE_LENGTH)
        val now = System.currentTimeMillis()
        val conversation = LiaConversation(UUID.randomUUID().toString(), cleanTitle, now, now)
        writableDatabase.insertOrThrow("conversations", null, ContentValues().apply {
            put("id", conversation.id)
            put("title", conversation.title)
            put("created_at", conversation.createdAt)
            put("updated_at", conversation.updatedAt)
        })
        return conversation
    }

    fun listConversations(limit: Int = DEFAULT_LIMIT): List<LiaConversation> {
        val safeLimit = limit.coerceIn(1, MAX_LIMIT)
        return readableDatabase.query(
            "conversations",
            arrayOf("id", "title", "created_at", "updated_at"),
            null,
            null,
            null,
            null,
            "updated_at DESC",
            safeLimit.toString(),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    add(
                        LiaConversation(
                            cursor.getString(0),
                            cursor.getString(1),
                            cursor.getLong(2),
                            cursor.getLong(3),
                        ),
                    )
                }
            }
        }
    }

    fun appendMessage(conversationId: String, role: String, content: String): LiaMessage {
        require(role in ALLOWED_ROLES) { "Papel de mensagem inválido." }
        require(content.isNotBlank()) { "A mensagem não pode estar vazia." }
        require(content.length <= MAX_MESSAGE_LENGTH) { "A mensagem excede o limite permitido." }

        val now = System.currentTimeMillis()
        val message = LiaMessage(
            UUID.randomUUID().toString(),
            conversationId,
            role,
            content,
            now,
        )
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.insertOrThrow("messages", null, ContentValues().apply {
                put("id", message.id)
                put("conversation_id", message.conversationId)
                put("role", message.role)
                put("content", message.content)
                put("created_at", message.createdAt)
            })
            db.update(
                "conversations",
                ContentValues().apply { put("updated_at", now) },
                "id = ?",
                arrayOf(conversationId),
            ).also { updated ->
                check(updated == 1) { "Conversa não encontrada." }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return message
    }

    fun getMessages(conversationId: String, limit: Int = DEFAULT_LIMIT): List<LiaMessage> {
        val safeLimit = limit.coerceIn(1, MAX_LIMIT)
        return readableDatabase.query(
            "messages",
            arrayOf("id", "conversation_id", "role", "content", "created_at"),
            "conversation_id = ?",
            arrayOf(conversationId),
            null,
            null,
            "created_at ASC",
            safeLimit.toString(),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    add(
                        LiaMessage(
                            cursor.getString(0),
                            cursor.getString(1),
                            cursor.getString(2),
                            cursor.getString(3),
                            cursor.getLong(4),
                        ),
                    )
                }
            }
        }
    }

    fun saveMemory(kind: String, content: String): LiaMemory {
        val cleanKind = kind.trim().take(MAX_KIND_LENGTH)
        val cleanContent = content.trim()
        require(cleanKind.isNotEmpty()) { "O tipo da memória é obrigatório." }
        require(cleanContent.isNotEmpty()) { "A memória não pode estar vazia." }
        require(cleanContent.length <= MAX_MEMORY_LENGTH) { "A memória excede o limite permitido." }

        val memory = LiaMemory(
            UUID.randomUUID().toString(),
            cleanKind,
            cleanContent,
            System.currentTimeMillis(),
        )
        writableDatabase.insertOrThrow("memories", null, ContentValues().apply {
            put("id", memory.id)
            put("kind", memory.kind)
            put("content", memory.content)
            put("created_at", memory.createdAt)
        })
        return memory
    }

    fun searchMemories(query: String, limit: Int = DEFAULT_LIMIT): List<LiaMemory> {
        val cleanQuery = query.trim()
        if (cleanQuery.isEmpty()) return emptyList()
        val safeLimit = limit.coerceIn(1, MAX_LIMIT)
        return readableDatabase.query(
            "memories",
            arrayOf("id", "kind", "content", "created_at"),
            "content LIKE ? ESCAPE '\\'",
            arrayOf("%${escapeLike(cleanQuery)}%"),
            null,
            null,
            "created_at DESC",
            safeLimit.toString(),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    add(
                        LiaMemory(
                            cursor.getString(0),
                            cursor.getString(1),
                            cursor.getString(2),
                            cursor.getLong(3),
                        ),
                    )
                }
            }
        }
    }

    fun deleteMemory(memoryId: String): Boolean =
        writableDatabase.delete("memories", "id = ?", arrayOf(memoryId)) == 1

    companion object {
        private const val DATABASE_NAME = "lia_local.db"
        private const val DATABASE_VERSION = 1
        private const val DEFAULT_LIMIT = 50
        private const val MAX_LIMIT = 200
        private const val MAX_TITLE_LENGTH = 120
        private const val MAX_KIND_LENGTH = 48
        private const val MAX_MESSAGE_LENGTH = 32_000
        private const val MAX_MEMORY_LENGTH = 4_000
        private val ALLOWED_ROLES = setOf("user", "assistant", "system")

        private fun escapeLike(value: String): String =
            value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    }
}
