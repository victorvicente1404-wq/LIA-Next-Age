package com.lia.personal.data

/**
 * Storage boundary for the Android presentation layer.
 *
 * Implementations must keep conversation history and explicit memories
 * separate. Callers should perform database operations off the main thread.
 */
interface LiaRepository {
    fun createConversation(title: String): LiaConversation
    fun listConversations(limit: Int = 50): List<LiaConversation>
    fun appendMessage(conversationId: String, role: String, content: String): LiaMessage
    fun getMessages(conversationId: String, limit: Int = 50): List<LiaMessage>
    fun saveMemory(kind: String, content: String): LiaMemory
    fun searchMemories(query: String, limit: Int = 50): List<LiaMemory>
    fun deleteMemory(memoryId: String): Boolean
}

/** SQLite-backed implementation using the app-private LiaStore database. */
class LocalLiaRepository(
    private val store: LiaStore,
) : LiaRepository {
    override fun createConversation(title: String): LiaConversation =
        store.createConversation(title)

    override fun listConversations(limit: Int): List<LiaConversation> =
        store.listConversations(limit)

    override fun appendMessage(
        conversationId: String,
        role: String,
        content: String,
    ): LiaMessage = store.appendMessage(conversationId, role, content)

    override fun getMessages(conversationId: String, limit: Int): List<LiaMessage> =
        store.getMessages(conversationId, limit)

    override fun saveMemory(kind: String, content: String): LiaMemory =
        store.saveMemory(kind, content)

    override fun searchMemories(query: String, limit: Int): List<LiaMemory> =
        store.searchMemories(query, limit)

    override fun deleteMemory(memoryId: String): Boolean =
        store.deleteMemory(memoryId)
}
