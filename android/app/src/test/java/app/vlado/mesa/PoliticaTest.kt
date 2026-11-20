package app.vlado.mesa

import java.util.Base64
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OrigemAutorizadaTest {
    private val politica = OrigemAutorizada.de("https://Demo.Vlado.invalid:443/")

    @Test
    fun `normaliza origem removendo porta padrao e barra`() {
        assertEquals("https://demo.vlado.invalid", politica.origem)
    }

    @Test(expected = IllegalArgumentException::class)
    fun `recusa origem sem https`() {
        OrigemAutorizada.de("http://demo.vlado.invalid")
    }

    @Test
    fun `mesma origem carrega na webview`() {
        assertEquals(OrigemAutorizada.Destino.Interno, politica.classificar("https://demo.vlado.invalid/entrar?x=1#a"))
        assertEquals(OrigemAutorizada.Destino.Interno, politica.classificar("blob:https://demo.vlado.invalid/1234-abcd"))
    }

    @Test
    fun `subdominio, porta ou esquema diferentes nao sao a mesma origem`() {
        assertFalse(politica.mesmaOrigem("https://evil.demo.vlado.invalid/"))
        assertFalse(politica.mesmaOrigem("https://demo.vlado.invalid.evil.com/"))
        assertFalse(politica.mesmaOrigem("https://demo.vlado.invalid:8443/"))
        assertFalse(politica.mesmaOrigem("http://demo.vlado.invalid/"))
        assertFalse(politica.mesmaOrigem("https://user@demo.vlado.invalid/"))
        assertFalse(politica.blobDaOrigem("blob:https://outra.invalid/1234"))
    }

    @Test
    fun `links externos vao para o sistema`() {
        assertEquals(
            OrigemAutorizada.Destino.Externo("https://exemplo.org/doc"),
            politica.classificar("https://exemplo.org/doc"),
        )
        assertEquals(OrigemAutorizada.Destino.Externo("mailto:a@b.org"), politica.classificar("mailto:a@b.org"))
    }

    @Test
    fun `esquemas perigosos sao bloqueados`() {
        for (url in listOf(
            "intent://x#Intent;scheme=https;end", "file:///sdcard/a.pdf", "content://x/y",
            "javascript:alert(1)", "data:text/html,oi", "blob:https://outra.invalid/1", "", "::::",
        )) {
            assertEquals(url, OrigemAutorizada.Destino.Bloqueado, politica.classificar(url))
        }
    }
}

class DownloadsTest {
    private fun mensagem(nome: String?, tipo: String?, bytes: ByteArray): String =
        JSONObject().apply {
            nome?.let { put("nome", it) }
            tipo?.let { put("tipo", it) }
            put("base64", Base64.getEncoder().encodeToString(bytes))
        }.toString()

    @Test
    fun `aceita pdf valido`() {
        val pedido = Downloads.interpretar(mensagem("original.pdf", "application/pdf", byteArrayOf(1, 2, 3)))
        assertTrue(pedido is PedidoDownload.Valido)
        val arquivo = (pedido as PedidoDownload.Valido).arquivo
        assertEquals("original.pdf", arquivo.nome)
        assertEquals("application/pdf", arquivo.mime)
        assertEquals(3, arquivo.bytes.size)
    }

    @Test
    fun `nome com caminho e caracteres de controle e saneado`() {
        assertEquals("passwd", Downloads.sanitizarNome("../../etc/passwd"))
        assertEquals("a.pdf", Downloads.sanitizarNome("C:\\x\\a.pdf"))
        assertEquals("a_b.txt", Downloads.sanitizarNome("a\u0000b.txt"))
        assertEquals("arquivo", Downloads.sanitizarNome(".."))
        assertEquals("arquivo", Downloads.sanitizarNome(null))
        assertEquals("fdp._exe", Downloads.sanitizarNome("fdp.\u202Eexe"))
        val longo = Downloads.sanitizarNome("x".repeat(500) + ".pdf")
        assertEquals(120, longo.length)
        assertTrue(longo.endsWith(".pdf"))
    }

    @Test
    fun `tipo nao permitido vira octet-stream ou o da extensao`() {
        assertEquals("application/octet-stream", Downloads.normalizarMime("text/html", "pagina.html"))
        assertEquals("application/octet-stream", Downloads.normalizarMime("image/svg+xml", "x.svg"))
        assertEquals("text/markdown", Downloads.normalizarMime("text/markdown;charset=utf-8", "nota.md"))
        assertEquals("application/pdf", Downloads.normalizarMime("", "original.PDF"))
        // Blob de fetch() com Content-Type genérico: a extensão decide (achado no emulador).
        assertEquals("application/pdf", Downloads.normalizarMime("application/octet-stream", "original.pdf"))
        assertEquals("application/octet-stream", Downloads.normalizarMime("application/octet-stream", "x.exe"))
    }

    @Test
    fun `mensagens invalidas sao recusadas`() {
        assertTrue(Downloads.interpretar(null) is PedidoDownload.Invalido)
        assertTrue(Downloads.interpretar("nao e json") is PedidoDownload.Invalido)
        assertTrue(Downloads.interpretar("""{"nome":"a.pdf","tipo":"application/pdf"}""") is PedidoDownload.Invalido)
        assertTrue(Downloads.interpretar("""{"nome":"a.pdf","base64":"@@@"}""") is PedidoDownload.Invalido)
    }

    @Test
    fun `extensao e amarrada ao tipo`() {
        val pdf = Downloads.interpretar(mensagem("x.apk", "application/pdf", byteArrayOf(1))) as PedidoDownload.Valido
        assertEquals("x.apk.pdf", pdf.arquivo.nome)
        val bin = Downloads.interpretar(mensagem("instalar.apk", "application/vnd.android.package-archive", byteArrayOf(1)))
        assertEquals("instalar.apk.bin", (bin as PedidoDownload.Valido).arquivo.nome)
        assertEquals("application/octet-stream", bin.arquivo.mime)
        assertFalse(Downloads.podeAbrir(bin.arquivo.mime))
        assertEquals("foto.jpeg", Downloads.ajustarExtensao("foto.jpeg", "image/jpeg"))
    }

    @Test
    fun `nome e tipo nulos usam padrao`() {
        val pedido = Downloads.interpretar("""{"nome":null,"tipo":null,"base64":"AQ=="}""") as PedidoDownload.Valido
        assertEquals("arquivo.bin", pedido.arquivo.nome)
    }

    @Test
    fun `accept do input vira mimes`() {
        assertEquals(listOf("application/pdf", "image/png"), Downloads.mimesDeEntrada(listOf(".pdf, image/png")))
        assertEquals(emptyList<String>(), Downloads.mimesDeEntrada(listOf(".pdf", ".xyz")))
        assertEquals(emptyList<String>(), Downloads.mimesDeEntrada(listOf("")))
    }

    @Test
    fun `arquivo acima do limite e recusado sem decodificar`() {
        val grande = "A".repeat(((Downloads.TAMANHO_MAXIMO_BYTES / 3L + 1) * 4 + 8192).toInt())
        assertTrue(Downloads.interpretar("""{"nome":"a.bin","base64":"$grande"}""") is PedidoDownload.Invalido)
    }
}
