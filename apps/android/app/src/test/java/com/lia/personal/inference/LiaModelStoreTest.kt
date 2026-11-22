package com.lia.personal.inference

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LiaModelStoreTest {
    @Test
    fun recognizesOnlyTheGgufMagicHeader() {
        assertTrue(LiaModelStore.hasGgufMagic(byteArrayOf(0x47, 0x47, 0x55, 0x46, 0x00)))
        assertFalse(LiaModelStore.hasGgufMagic(byteArrayOf(0x47, 0x47, 0x55)))
        assertFalse(LiaModelStore.hasGgufMagic("not a model".toByteArray()))
    }

    @Test
    fun sanitizesDisplayNamesBeforeUsingThemAsFileNames() {
        assertTrue(LiaModelStore.sanitizeName("../../Meu Modelo Q4_K_M.gguf")
            .matches(Regex("[a-z0-9_-]+")))
        assertTrue(LiaModelStore.sanitizeName("...").isNotBlank())
        assertTrue(LiaModelStore.sanitizeName("A".repeat(200)).length <= 48)
    }
}
