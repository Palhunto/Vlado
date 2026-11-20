package app.vlado.mesa

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.RenderProcessGoneDetail
import android.webkit.SslErrorHandler
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.net.toUri
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import java.io.ByteArrayInputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Casca WebView da Mesa do Vlado. Carrega só [BuildConfig.ORIGEM]; o resto vai para o
 * navegador do sistema. Sem addJavascriptInterface: a única ponte é um WebMessageListener
 * restrito à origem configurada, usado para gravar downloads.
 */
class MainActivity : ComponentActivity() {

    private lateinit var webView: WebView
    private lateinit var painelFalha: View
    private lateinit var tituloFalha: TextView
    private lateinit var textoFalha: TextView
    private lateinit var progresso: ProgressBar

    private val politica = OrigemAutorizada.de(BuildConfig.ORIGEM)
    private val gravador by lazy { GravadorDownloads(contentResolver) }
    private val trabalho: ExecutorService = Executors.newSingleThreadExecutor()
    private val principal = Handler(Looper.getMainLooper())

    /** Um download por vez: evita fila ilimitada na memória e troca de destino no SAF. */
    private val downloadEmCurso = AtomicBoolean(false)

    private var webViewViva = false
    private var urlComFalha: String? = null
    private var cargaFalhou = false
    private var callbackArquivos: ValueCallback<Array<Uri>>? = null
    private var arquivoAguardandoDestino: ArquivoRecebido? = null
    private var dialogo: AlertDialog? = null

    private val escolherArquivos =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { resultado ->
            callbackArquivos?.onReceiveValue(urisEscolhidos(resultado.resultCode, resultado.data))
            callbackArquivos = null
        }

    // Android 8–9 (sem MediaStore.Downloads): o usuário escolhe onde salvar (SAF).
    private val criarDocumento =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { resultado ->
            val arquivo = arquivoAguardandoDestino
            arquivoAguardandoDestino = null
            val destino = resultado.data?.data
            if (arquivo == null || resultado.resultCode != RESULT_OK || destino == null) {
                downloadEmCurso.set(false)
                return@registerForActivityResult
            }
            val aceito = executar {
                val ok = try {
                    gravador.gravarEm(destino, arquivo.bytes)
                    true
                } catch (e: Exception) {
                    Log.w(TAG, "Falha ao gravar via SAF: ${e.javaClass.simpleName}")
                    false
                }
                principal.post {
                    downloadEmCurso.set(false)
                    if (ok) oferecerAbrir(destino, arquivo, R.string.download_salvo_texto_saf) else avisar(R.string.download_falhou)
                }
            }
            if (!aceito) downloadEmCurso.set(false)
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val raiz = findViewById<FrameLayout>(R.id.raiz)
        ViewCompat.setOnApplyWindowInsetsListener(raiz) { v, insets ->
            val barras = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime() or
                    WindowInsetsCompat.Type.displayCutout()
            )
            v.setPadding(barras.left, barras.top, barras.right, barras.bottom)
            WindowInsetsCompat.CONSUMED
        }

        webView = findViewById(R.id.webview)
        webViewViva = true
        painelFalha = findViewById(R.id.painel_falha)
        tituloFalha = findViewById(R.id.titulo_falha)
        textoFalha = findViewById(R.id.texto_falha)
        progresso = findViewById(R.id.progresso)
        findViewById<Button>(R.id.tentar_de_novo).setOnClickListener { tentarDeNovo() }

        configurarWebView()
        configurarVoltar()

        // Depois de queda do renderizador não restaura o histórico (evita laço de quedas).
        val estado = savedInstanceState?.takeUnless { pularRestauracao }
        pularRestauracao = false
        val restaurado = estado?.let { webView.restoreState(it) } != null
        if (!restaurado) webView.loadUrl("${politica.origem}/")
    }

    @SuppressLint("SetJavaScriptEnabled") // A Mesa é uma aplicação JavaScript; a origem é fixa e HTTPS.
    private fun configurarWebView() {
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true // sessionStorage do rascunho do Caderno
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            setGeolocationEnabled(false)
            mediaPlaybackRequiresUserGesture = true
            safeBrowsingEnabled = true
        }
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, false)
        }
        webView.webViewClient = Cliente()
        webView.webChromeClient = Cromo()
        webView.setDownloadListener { _, _, _, _, _ -> avisar(R.string.download_nao_suportado) }
        instalarPonte()
    }

    /** Ponte de downloads: só a origem autorizada recebe o objeto window.VladoAndroid. */
    private fun instalarPonte() {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            Log.w(TAG, "WebView sem WEB_MESSAGE_LISTENER: downloads indisponíveis")
            return
        }
        WebViewCompat.addWebMessageListener(webView, NOME_PONTE, setOf(politica.origem)) { _, mensagem, origem, quadroPrincipal, _ ->
            // Defesa em profundidade: a regra acima já restringe, mas conferimos de novo.
            if (!quadroPrincipal || !politica.mesmaOrigem(origem.toString())) return@addWebMessageListener
            if (!downloadEmCurso.compareAndSet(false, true)) {
                avisar(R.string.download_ocupado)
                return@addWebMessageListener
            }
            val texto = mensagem.data
            if (!executar { processarDownload(texto) }) downloadEmCurso.set(false)
        }
    }

    /** Executa na thread de trabalho; falso se a atividade já está encerrando. */
    private fun executar(tarefa: () -> Unit): Boolean = try {
        trabalho.execute(tarefa)
        true
    } catch (e: RejectedExecutionException) {
        false
    }

    /** Roda na thread de trabalho. Nunca deixa exceção (nem falta de memória) derrubar o app. */
    private fun processarDownload(mensagem: String?) {
        try {
            when (val pedido = Downloads.interpretar(mensagem)) {
                is PedidoDownload.Invalido -> {
                    Log.w(TAG, "Download recusado: ${pedido.motivo}")
                    concluirComFalha()
                }
                is PedidoDownload.Valido -> gravar(pedido.arquivo)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Falha no download: ${e.javaClass.simpleName}")
            concluirComFalha()
        } catch (e: OutOfMemoryError) {
            Log.w(TAG, "Arquivo grande demais para a memória disponível")
            concluirComFalha()
        }
    }

    private fun concluirComFalha() {
        principal.post {
            downloadEmCurso.set(false)
            avisar(R.string.download_falhou)
        }
    }

    private fun gravar(arquivo: ArquivoRecebido) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val uri = gravador.gravarEmDownloads(arquivo)
            principal.post {
                downloadEmCurso.set(false)
                oferecerAbrir(uri, arquivo, R.string.download_salvo_texto)
            }
        } else {
            principal.post {
                if (isFinishing || isDestroyed) {
                    downloadEmCurso.set(false)
                    return@post
                }
                arquivoAguardandoDestino = arquivo
                val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = arquivo.mime
                    putExtra(Intent.EXTRA_TITLE, arquivo.nome)
                }
                try {
                    criarDocumento.launch(intent)
                } catch (e: ActivityNotFoundException) {
                    arquivoAguardandoDestino = null
                    downloadEmCurso.set(false)
                    avisar(R.string.download_falhou)
                }
            }
        }
    }

    private fun oferecerAbrir(uri: Uri, arquivo: ArquivoRecebido, texto: Int) {
        if (isFinishing || isDestroyed) {
            // O arquivo já foi gravado; avisa com o contexto da aplicação.
            Toast.makeText(applicationContext, getString(texto, arquivo.nome), Toast.LENGTH_LONG).show()
            return
        }
        dialogo?.dismiss()
        val construtor = AlertDialog.Builder(this)
            .setTitle(R.string.download_salvo_titulo)
            .setMessage(getString(texto, arquivo.nome))
            .setNegativeButton(R.string.fechar, null)
        if (Downloads.podeAbrir(arquivo.mime)) {
            construtor.setPositiveButton(R.string.abrir) { _, _ -> abrirComSistema(uri, arquivo.mime) }
        }
        dialogo = construtor.show()
    }

    private fun abrirComSistema(uri: Uri, mime: String) {
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, mime)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        iniciar(Intent.createChooser(intent, null))
    }

    private fun abrirFora(url: String) {
        iniciar(Intent(Intent.ACTION_VIEW, url.toUri()).addCategory(Intent.CATEGORY_BROWSABLE))
    }

    private fun iniciar(intent: Intent) {
        try {
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            avisar(R.string.sem_app_para_abrir)
        } catch (e: SecurityException) {
            avisar(R.string.sem_app_para_abrir)
        }
    }

    private fun configurarVoltar() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webViewViva && webView.canGoBack()) webView.goBack() else finish()
            }
        })
    }

    private fun mostrarFalha(titulo: Int, texto: Int) {
        tituloFalha.setText(titulo)
        textoFalha.setText(texto)
        painelFalha.visibility = View.VISIBLE
        progresso.visibility = View.GONE
    }

    private fun tentarDeNovo() {
        if (!webViewViva) {
            pularRestauracao = true
            recreate()
            return
        }
        painelFalha.visibility = View.GONE
        val alvo = urlComFalha?.takeIf { politica.mesmaOrigem(it) } ?: "${politica.origem}/"
        webView.loadUrl(alvo)
    }

    private fun avisar(texto: Int) {
        if (!isFinishing && !isDestroyed) Toast.makeText(this, texto, Toast.LENGTH_LONG).show()
    }

    private fun urisEscolhidos(codigo: Int, dados: Intent?): Array<Uri>? {
        if (codigo != RESULT_OK || dados == null) return null
        val clip = dados.clipData
        if (clip != null && clip.itemCount > 0) {
            return (0 until clip.itemCount).mapNotNull { clip.getItemAt(it).uri }.toTypedArray().takeIf { it.isNotEmpty() }
        }
        return dados.data?.let { arrayOf(it) }
    }

    /** Tira a WebView da janela e a destrói (renderizador caído ou atividade encerrando). */
    private fun descartarWebView() {
        if (!webViewViva) return
        webViewViva = false
        (webView.parent as? ViewGroup)?.removeView(webView)
        webView.removeAllViews()
        webView.destroy()
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush() // não perde a sessão se o processo morrer em segundo plano
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        if (!webViewViva) return
        try {
            webView.saveState(outState)
        } catch (e: RuntimeException) {
            Log.w(TAG, "Histórico da WebView não salvo: ${e.javaClass.simpleName}")
        }
    }

    override fun onDestroy() {
        callbackArquivos?.onReceiveValue(null)
        callbackArquivos = null
        dialogo?.dismiss()
        dialogo = null
        principal.removeCallbacksAndMessages(null)
        trabalho.shutdown()
        descartarWebView()
        super.onDestroy()
    }

    private inner class Cliente : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
            when (val destino = politica.classificar(request.url.toString())) {
                OrigemAutorizada.Destino.Interno -> false
                is OrigemAutorizada.Destino.Externo -> {
                    // Só abre fora com gesto do usuário (clique em link), nunca por redirecionamento.
                    if (request.isForMainFrame && request.hasGesture()) abrirFora(destino.url)
                    true
                }
                OrigemAutorizada.Destino.Bloqueado -> true
            }

        /**
         * Barreira de rede: nenhuma requisição http(s) sai para outra origem, nem por POST de
         * formulário (que não passa por shouldOverrideUrlLoading). Roda fora da thread principal.
         */
        override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
            val esquema = request.url.scheme?.lowercase()
            if ((esquema == "http" || esquema == "https") && !politica.mesmaOrigem(request.url.toString())) {
                return WebResourceResponse("text/plain", "utf-8", 403, "Bloqueado", emptyMap(), ByteArrayInputStream(ByteArray(0)))
            }
            return null
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
            // Segunda barreira: se algo fora da origem chegar a carregar no quadro principal, interrompe.
            if (url != null && url != "about:blank" && !politica.mesmaOrigem(url)) {
                view.stopLoading()
                view.loadUrl("${politica.origem}/")
                return
            }
            cargaFalhou = false
            progresso.visibility = View.VISIBLE
        }

        override fun onPageFinished(view: WebView, url: String?) {
            progresso.visibility = View.GONE
            if (!cargaFalhou) painelFalha.visibility = View.GONE
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (!request.isForMainFrame) return
            if (!politica.mesmaOrigem(request.url.toString())) return // bloqueio nosso, não falta de rede
            cargaFalhou = true
            urlComFalha = request.url.toString()
            mostrarFalha(R.string.sem_conexao_titulo, R.string.sem_conexao_texto)
        }

        @SuppressLint("WebViewClientOnReceivedSslError") // Sempre cancela: nunca prossegue com TLS inválido.
        override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
            handler.cancel()
            if (!politica.mesmaOrigem(error.url)) return
            cargaFalhou = true
            urlComFalha = error.url
            mostrarFalha(R.string.tls_titulo, R.string.tls_texto)
        }

        override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
            if (isFinishing || isDestroyed) return true
            val agora = SystemClock.elapsedRealtime()
            val repetida = ultimaQueda != 0L && agora - ultimaQueda < INTERVALO_QUEDAS_MS
            ultimaQueda = agora
            descartarWebView()
            if (repetida) {
                // Segunda queda seguida: para e deixa o usuário decidir, sem laço de recriação.
                mostrarFalha(R.string.renderizador_titulo, R.string.renderizador_texto)
            } else {
                pularRestauracao = true
                recreate()
            }
            return true
        }
    }

    private inner class Cromo : WebChromeClient() {
        override fun onProgressChanged(view: WebView, newProgress: Int) {
            progresso.progress = newProgress
        }

        override fun onShowFileChooser(
            view: WebView,
            filePathCallback: ValueCallback<Array<Uri>>,
            fileChooserParams: FileChooserParams,
        ): Boolean {
            callbackArquivos?.onReceiveValue(null)
            callbackArquivos = filePathCallback
            val tipos = Downloads.mimesDeEntrada(fileChooserParams.acceptTypes.toList())
            val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = if (tipos.size == 1) tipos.first() else "*/*"
                if (tipos.size > 1) putExtra(Intent.EXTRA_MIME_TYPES, tipos.toTypedArray())
                if (fileChooserParams.mode == FileChooserParams.MODE_OPEN_MULTIPLE) {
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
            }
            return try {
                escolherArquivos.launch(Intent.createChooser(intent, fileChooserParams.title))
                true
            } catch (e: ActivityNotFoundException) {
                callbackArquivos = null
                false
            }
        }

        override fun onPermissionRequest(request: PermissionRequest) {
            request.deny() // câmera, microfone etc. não são usados pela Mesa
        }
    }

    companion object {
        private const val TAG = "VladoMesa"

        /** Nome do objeto injetado na página (window.VladoAndroid). */
        const val NOME_PONTE = "VladoAndroid"
        private const val INTERVALO_QUEDAS_MS = 30_000L

        // Sobrevivem ao recreate() (mesmo processo) para quebrar laços de queda do renderizador.
        private var ultimaQueda = 0L
        private var pularRestauracao = false
    }
}
