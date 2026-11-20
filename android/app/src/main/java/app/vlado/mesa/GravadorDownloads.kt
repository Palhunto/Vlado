package app.vlado.mesa

import android.content.ContentResolver
import android.content.ContentValues
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.annotation.RequiresApi
import java.io.IOException

/** Grava arquivos recebidos da página em Downloads/Vlado (MediaStore) ou num URI escolhido pelo usuário (SAF). */
class GravadorDownloads(private val resolver: ContentResolver) {

    /** API 29+: grava direto em Downloads/Vlado, sem permissão de armazenamento. */
    @RequiresApi(Build.VERSION_CODES.Q)
    fun gravarEmDownloads(arquivo: ArquivoRecebido): Uri {
        val valores = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, arquivo.nome)
            put(MediaStore.MediaColumns.MIME_TYPE, arquivo.mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, "${Environment.DIRECTORY_DOWNLOADS}/$PASTA")
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val colecao = MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val uri = resolver.insert(colecao, valores) ?: throw IOException("MediaStore recusou o arquivo")
        try {
            escrever(uri, arquivo.bytes)
            resolver.update(uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
            return uri
        } catch (e: Exception) {
            resolver.delete(uri, null, null)
            throw e
        }
    }

    /** API 26–28 (ou qualquer versão via SAF): grava no documento criado pelo usuário. */
    fun gravarEm(uri: Uri, bytes: ByteArray) = escrever(uri, bytes)

    private fun escrever(uri: Uri, bytes: ByteArray) {
        val saida = resolver.openOutputStream(uri, "w") ?: throw IOException("Não foi possível abrir o destino")
        saida.use { it.write(bytes) }
    }

    companion object {
        const val PASTA = "Vlado"
    }
}
