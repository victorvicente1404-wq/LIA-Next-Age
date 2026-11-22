package com.lia.personal.data

import android.content.Context
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

@RunWith(RobolectricTestRunner::class)
class LocalLiaRepositoryTest {
    private lateinit var context: Context
    private lateinit var store: LiaStore
    private lateinit var repository: LiaRepository

    @Before
    fun setUp() {
        context = RuntimeEnvironment.getApplication()
        context.deleteDatabase("lia_local.db")
        store = LiaStore(context)
        repository = LocalLiaRepository(store)
    }

    @After
    fun tearDown() {
        store.close()
        context.deleteDatabase("lia_local.db")
    }

    @Test
    fun repositoryPersistsConversationAndMessages() {
        val conversation = repository.createConversation("Lia no Android")
        repository.appendMessage(conversation.id, "user", "Teste de persistência")

        assertEquals("Lia no Android", repository.listConversations().single().title)
        assertEquals(
            "Teste de persistência",
            repository.getMessages(conversation.id).single().content,
        )
    }

    @Test
    fun repositoryKeepsExplicitMemoriesSeparate() {
        val conversation = repository.createConversation("Histórico")
        repository.appendMessage(conversation.id, "user", "Texto de conversa")
        val memory = repository.saveMemory("preference", "Prefere execução local")

        assertEquals(1, repository.searchMemories("execução local").size)
        assertTrue(repository.getMessages(conversation.id).single().content == "Texto de conversa")
        assertTrue(repository.deleteMemory(memory.id))
        assertTrue(repository.searchMemories("execução local").isEmpty())
    }
}
