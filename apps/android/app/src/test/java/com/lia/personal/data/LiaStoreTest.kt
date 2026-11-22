package com.lia.personal.data

import android.content.Context
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

@RunWith(RobolectricTestRunner::class)
class LiaStoreTest {
    private lateinit var context: Context
    private lateinit var store: LiaStore

    @Before
    fun setUp() {
        context = RuntimeEnvironment.getApplication()
        context.deleteDatabase("lia_local.db")
        store = LiaStore(context)
    }

    @After
    fun tearDown() {
        store.close()
        context.deleteDatabase("lia_local.db")
    }

    @Test
    fun conversationAndMessagesPersistInLocalDatabase() {
        val conversation = store.createConversation("  Projeto Lia  ")
        val saved = store.appendMessage(conversation.id, "user", "Olá, Lia!")

        val reopenedStore = LiaStore(context)
        val conversations = reopenedStore.listConversations()
        val messages = reopenedStore.getMessages(conversation.id)

        assertEquals("Projeto Lia", conversations.single().title)
        assertEquals(saved.id, messages.single().id)
        assertEquals("Olá, Lia!", messages.single().content)
        reopenedStore.close()
    }

    @Test
    fun messageLimitReturnsTheMostRecentMessagesInChronologicalOrder() {
        val conversation = store.createConversation("Conversa")
        store.appendMessage(conversation.id, "user", "primeira")
        store.appendMessage(conversation.id, "assistant", "segunda")
        store.appendMessage(conversation.id, "user", "terceira")

        val recent = store.getMessages(conversation.id, limit = 2)

        assertEquals(listOf("segunda", "terceira"), recent.map { it.content })
    }

    @Test
    fun explicitMemoriesAreStoredSeparatelyFromConversationHistory() {
        val conversation = store.createConversation("Conversa")
        store.appendMessage(conversation.id, "user", "Gosto de construir projetos.")
        val memory = store.saveMemory("preference", "Gosta de construir projetos.")

        assertEquals(1, store.searchMemories("construir").size)
        assertEquals(memory.id, store.searchMemories("Gosta").single().id)
        assertTrue(store.deleteMemory(memory.id))
        assertFalse(store.deleteMemory(memory.id))
        assertTrue(store.searchMemories("Gosta").isEmpty())
        assertEquals(1, store.getMessages(conversation.id).size)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsUnsupportedMessageRoles() {
        val conversation = store.createConversation("Conversa")
        store.appendMessage(conversation.id, "tool", "Conteúdo não autorizado")
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsEmptyMemories() {
        store.saveMemory("preference", "   ")
    }
}
