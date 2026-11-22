package com.lia.personal.data

import android.content.Context

/**
 * App-scoped access point. The SQLiteOpenHelper keeps one database file
 * in app-private storage; callers must not expose its path to the model/UI.
 */
class LiaStoreProvider(context: Context) {
    val store: LiaStore = LiaStore(context.applicationContext)
}
