package app.vlado.mesa

import java.net.URI
import java.util.Base64
import java.util.Locale
import org.json.JSONException
import org.json.JSONObject

/**
 * Regras puras (sem dependência do Android) para origem autorizada, links externos e
 * pedidos de download vindos da página. Ficam isoladas para serem testadas na JVM.
 */
class OrigemAutorizada private constructor(val origem: String) {

    /** Destino de uma navegação pedida pela página. */
    sealed interface Destino {
        /** Mesma origem: carrega na WebView. */
        data object Interno : Destino

        /** http(s), mailto ou tel de outra origem: entrega ao app do sistema. */
        data class Externo(val url: String) : Destino

        /** Esquemas perigosos ou inválidos (intent:, file:, content:, javascript:, data:...). */
        data object Bloqueado : Destino
    }

    fun mesmaOrigem(url: String?): Boolean = url != null && normalizar(url) == origem

    /** blob: criado pela própria página (blob:https://origem/uuid). */
    fun blobDaOrigem(url: String?): Boolean =
        url != null && url.startsWith("blob:", ignoreCase = true) && mesmaOrigem(url.substring(5))

    fun classificar(url: String?): Destino {
        if (url.isNullOrBlank()) return Destino.Bloqueado
        if (mesmaOrigem(url)) return Destino.Interno
        if (blobDaOrigem(url)) return Destino.Interno
        val esquema = esquemaDe(url) ?: return Destino.Bloqueado
        return when (esquema) {
            "https", "http" -> if (hostValido(url)) Destino.Externo(url) else Destino.Bloqueado
            "mailto", "tel" -> Destino.Externo(url)
            else -> Destino.Bloqueado
        }
    }

    companion object {
        /** Cria a política a partir de uma origem HTTPS; recusa qualquer outra coisa. */
        fun de(origem: String): OrigemAutorizada {
            val normalizada = normalizar(origem)
            require(normalizada != null && normalizada.startsWith("https://")) {
                "Origem inválida ou sem HTTPS: $origem"
            }
            return OrigemAutorizada(normalizada)
        }

        /** esquema://host[:porta] em minúsculas, sem porta padrão; null se não for http(s) válido. */
        fun normalizar(url: String): String? {
            val uri = try {
                URI(url.trim())
            } catch (e: Exception) {
                return null
            }
            val esquema = uri.scheme?.lowercase(Locale.ROOT) ?: return null
            if (esquema != "https" && esquema != "http") return null
            if (uri.rawUserInfo != null) return null
            val host = uri.host?.lowercase(Locale.ROOT)?.takeIf { it.isNotEmpty() } ?: return null
            val portaPadrao = if (esquema == "https") 443 else 80
            val porta = if (uri.port == -1 || uri.port == portaPadrao) "" else ":${uri.port}"
            return "$esquema://$host$porta"
        }

        private fun esquemaDe(url: String): String? = try {
            URI(url.trim()).scheme?.lowercase(Locale.ROOT)
        } catch (e: Exception) {
            null
        }

        private fun hostValido(url: String): Boolean = normalizar(url) != null
    }
}

/** Arquivo pronto para gravação, já validado. */
data class ArquivoRecebido(val nome: String, val mime: String, val bytes: ByteArray) {
    override fun equals(other: Any?): Boolean =
        other is ArquivoRecebido && nome == other.nome && mime == other.mime && bytes.contentEquals(other.bytes)

    override fun hashCode(): Int = 31 * (31 * nome.hashCode() + mime.hashCode()) + bytes.contentHashCode()
}

/** Resultado da leitura de uma mensagem da página. */
sealed interface PedidoDownload {
    data class Valido(val arquivo: ArquivoRecebido) : PedidoDownload
    data class Invalido(val motivo: String) : PedidoDownload
}

object Downloads {
    /** Limite do arquivo decodificado (a mensagem em base64 fica ~33% maior). */
    const val TAMANHO_MAXIMO_BYTES = 25 * 1024 * 1024
    private const val TAMANHO_MAXIMO_NOME = 120
    private const val NOME_PADRAO = "arquivo"
    private const val OCTET_STREAM = "application/octet-stream"
    private const val CARACTERES_PROIBIDOS = "<>:\"|?*"

    /** Marcas de direção (LRM, RLM, LRE..RLO, LRI..PDI) usadas para disfarçar extensões. */
    private val CONTROLES_BIDI = setOf(0x200E, 0x200F) + (0x202A..0x202E) + (0x2066..0x2069)

    /** Tipos que o app grava com o próprio MIME; o resto vira application/octet-stream. */
    private val TIPOS_PERMITIDOS = mapOf(
        "application/pdf" to "pdf",
        "image/png" to "png",
        "image/jpeg" to "jpg",
        "image/gif" to "gif",
        "image/webp" to "webp",
        "text/plain" to "txt",
        "text/markdown" to "md",
        "text/csv" to "csv",
        "text/tab-separated-values" to "tsv",
        "application/json" to "json",
        "application/zip" to "zip",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document" to "docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" to "xlsx",
        "application/octet-stream" to "bin",
    )

    /** Extensões reconhecidas quando a página não informa o tipo. */
    private val TIPO_POR_EXTENSAO = mapOf(
        "pdf" to "application/pdf", "png" to "image/png", "jpg" to "image/jpeg", "jpeg" to "image/jpeg",
        "gif" to "image/gif", "webp" to "image/webp", "txt" to "text/plain", "md" to "text/markdown",
        "csv" to "text/csv", "tsv" to "text/tab-separated-values", "json" to "application/json",
        "zip" to "application/zip",
        "docx" to "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx" to "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    /** Remove separadores, caracteres de controle e nomes reservados; limita o tamanho. */
    fun sanitizarNome(nome: String?): String {
        val base = (nome ?: "").substringAfterLast('/').substringAfterLast('\\')
        val limpo = buildString {
            for (c in base) {
                append(
                    when {
                        c.isISOControl() -> '_'
                        c in CARACTERES_PROIBIDOS || c.code in CONTROLES_BIDI -> '_'
                        else -> c
                    }
                )
            }
        }.trim().trim('.').trim()
        val semReservado = if (limpo.isEmpty() || limpo == "." || limpo == "..") NOME_PADRAO else limpo
        if (semReservado.length <= TAMANHO_MAXIMO_NOME) return semReservado
        val ponto = semReservado.lastIndexOf('.')
        val extensao = if (ponto > 0 && semReservado.length - ponto <= 10) semReservado.substring(ponto) else ""
        val corte = semReservado.take(TAMANHO_MAXIMO_NOME - extensao.length)
        // Não deixa metade de um par substituto (emoji etc.) no fim do corte.
        return corte.dropLastWhile { it.isHighSurrogate() } + extensao
    }

    /**
     * Amarra a extensão ao MIME aceito: "x.apk" declarado como PDF vira "x.apk.pdf";
     * octet-stream sempre termina em .bin, para nunca gravar executável com extensão própria.
     */
    fun ajustarExtensao(nome: String, mime: String): String {
        val extensaoEsperada = TIPOS_PERMITIDOS[mime] ?: "bin"
        val atual = nome.substringAfterLast('.', "").lowercase(Locale.ROOT)
        val aceitas = if (extensaoEsperada == "jpg") setOf("jpg", "jpeg") else setOf(extensaoEsperada)
        return if (atual in aceitas) nome else "$nome.$extensaoEsperada"
    }

    /**
     * Converte o atributo accept do input (MIME ou ".ext") para MIMEs do seletor do sistema.
     * Lista vazia = qualquer arquivo (algum item desconhecido ou nenhum filtro).
     */
    fun mimesDeEntrada(aceitos: List<String>): List<String> {
        val itens = aceitos.flatMap { it.split(',') }.map { it.trim().lowercase(Locale.ROOT) }.filter { it.isNotEmpty() }
        if (itens.isEmpty()) return emptyList()
        val mimes = itens.map { item ->
            when {
                item.contains('/') -> item
                item.startsWith('.') -> TIPO_POR_EXTENSAO[item.substring(1)] ?: return emptyList()
                else -> return emptyList()
            }
        }
        return mimes.distinct()
    }

    /** Só tipos conhecidos podem ser abertos direto com o app do sistema. */
    fun podeAbrir(mime: String): Boolean = mime != OCTET_STREAM

    /**
     * MIME final: o informado, se permitido e específico; senão o da extensão; senão octet-stream.
     * Respostas binárias do servidor costumam chegar como octet-stream: aí vale a extensão.
     */
    fun normalizarMime(mime: String?, nome: String): String {
        val informado = mime?.substringBefore(';')?.trim()?.lowercase(Locale.ROOT).orEmpty()
        if (informado in TIPOS_PERMITIDOS && informado != OCTET_STREAM) return informado
        val extensao = nome.substringAfterLast('.', "").lowercase(Locale.ROOT)
        return TIPO_POR_EXTENSAO[extensao] ?: OCTET_STREAM
    }

    /** Lê a mensagem {nome, tipo (MIME), base64} enviada por download() em app.js. */
    fun interpretar(mensagem: String?): PedidoDownload {
        if (mensagem.isNullOrEmpty()) return PedidoDownload.Invalido("mensagem vazia")
        val limiteBase64 = (TAMANHO_MAXIMO_BYTES / 3L + 1) * 4 + 4096
        if (mensagem.length > limiteBase64) return PedidoDownload.Invalido("arquivo grande demais")
        val json = try {
            JSONObject(mensagem)
        } catch (e: JSONException) {
            return PedidoDownload.Invalido("mensagem malformada")
        }
        val conteudo = json.optString("base64", "")
        if (conteudo.isEmpty()) return PedidoDownload.Invalido("arquivo vazio")
        val bytes = try {
            Base64.getDecoder().decode(conteudo)
        } catch (e: IllegalArgumentException) {
            return PedidoDownload.Invalido("conteúdo inválido")
        }
        if (bytes.size > TAMANHO_MAXIMO_BYTES) return PedidoDownload.Invalido("arquivo grande demais")
        // org.json do Android devolve "null" (texto) para valores nulos: trata explicitamente.
        val nomeInformado = if (json.isNull("nome")) null else json.optString("nome")
        val tipoInformado = if (json.isNull("tipo")) null else json.optString("tipo")
        val nome = sanitizarNome(nomeInformado)
        val mime = normalizarMime(tipoInformado, nome)
        return PedidoDownload.Valido(ArquivoRecebido(sanitizarNome(ajustarExtensao(nome, mime)), mime, bytes))
    }
}
