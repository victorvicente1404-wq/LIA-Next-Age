package com.lia.personal.data

import android.content.Context

/**
 * App-scoped access point for the local persistence layer.
 * The database remains in app-private storage and is never exposed directly
 * to the model or presentation layer.
 */
class LiaStoreProvider(context: Context) : AutoCloseable {
    private val store = LiaStore(context.applicationContext)

    val repository: LiaRepository = LocalLiaRepository(store)

    override fun close() {
        store.close()
    }
}
