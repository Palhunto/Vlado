import com.android.build.api.variant.BuildConfigField
import java.net.URI
import java.util.Properties

plugins {
    id("com.android.application")
}

// ---------------------------------------------------------------------------
// Origens autorizadas (uma por variante). Vêm de propriedades de build e nunca
// de segredos: -PvladoOrigemSala=https://... e -PvladoOrigemRedacao=https://...
// Os padrões usam o domínio reservado .invalid e não resolvem em lugar nenhum.
// ---------------------------------------------------------------------------
val origemPadraoSala = "https://demo.vlado.invalid"
val origemPadraoRedacao = "https://redacao.vlado.invalid"

/** Valida e normaliza uma origem HTTPS: esquema://host[:porta], sem caminho, consulta ou credenciais. */
fun normalizarOrigem(nomePropriedade: String, valor: String): String {
    val uri = try {
        URI(valor.trim())
    } catch (e: Exception) {
        throw GradleException("$nomePropriedade inválida: '$valor' (${e.message})")
    }
    if (!uri.scheme.equals("https", ignoreCase = true)) {
        throw GradleException("$nomePropriedade precisa usar https:// (recebido: '$valor').")
    }
    val host = uri.host?.lowercase()
    if (host.isNullOrBlank()) throw GradleException("$nomePropriedade sem host: '$valor'.")
    if (uri.rawUserInfo != null) throw GradleException("$nomePropriedade não pode conter usuário/senha.")
    if (!(uri.rawPath.isNullOrEmpty() || uri.rawPath == "/") || uri.rawQuery != null || uri.rawFragment != null) {
        throw GradleException("$nomePropriedade deve ser só a origem (sem caminho, consulta ou fragmento): '$valor'.")
    }
    val porta = if (uri.port == -1 || uri.port == 443) "" else ":${uri.port}"
    return "https://$host$porta"
}

fun propriedade(nome: String): String? =
    (findProperty(nome) as String?)?.takeIf { it.isNotBlank() }

val origemSala = normalizarOrigem("vladoOrigemSala", propriedade("vladoOrigemSala") ?: origemPadraoSala)
val origemRedacao = normalizarOrigem("vladoOrigemRedacao", propriedade("vladoOrigemRedacao") ?: origemPadraoRedacao)
// Só para a variante de depuração (homologação local, ex.: https://10.0.2.2:8443 no emulador).
val origemDepuracao = propriedade("vladoOrigemDepuracao")?.let { normalizarOrigem("vladoOrigemDepuracao", it) }
// Certificado (PEM, só a parte pública) da AC de teste confiada apenas na variante de depuração.
val caHomologacao = propriedade("vladoCaHomologacao")?.let { file(it) }?.also {
    if (!it.isFile) throw GradleException("vladoCaHomologacao não encontrado: $it")
    val texto = it.readText()
    if (texto.contains("PRIVATE KEY")) throw GradleException("vladoCaHomologacao contém chave privada; use só o certificado público.")
    if (Regex("BEGIN CERTIFICATE").findAll(texto).count() != 1) {
        throw GradleException("vladoCaHomologacao deve conter exatamente um certificado PEM.")
    }
}
if (caHomologacao != null && origemDepuracao == null) {
    throw GradleException("vladoCaHomologacao exige vladoOrigemDepuracao (a AC vale só para esse host).")
}

// ---------------------------------------------------------------------------
// Assinatura: keystore.properties fica fora do repositório e do pacote.
// -PvladoAssinatura=C:/caminho/keystore.properties ou variável VLADO_ASSINATURA.
// Chaves esperadas: storeFile, storePassword, keyAlias, keyPassword.
// ---------------------------------------------------------------------------
val arquivoAssinatura = (propriedade("vladoAssinatura") ?: System.getenv("VLADO_ASSINATURA"))
    ?.takeIf { it.isNotBlank() }?.let { File(it) }

if (arquivoAssinatura == null) {
    logger.warn("Aviso: sem -PvladoAssinatura/VLADO_ASSINATURA as variantes release saem SEM assinatura.")
}

val versaoCodigo = propriedade("vladoVersaoCodigo")?.let {
    it.toIntOrNull()?.takeIf { v -> v > 0 } ?: throw GradleException("vladoVersaoCodigo deve ser inteiro positivo: '$it'")
} ?: 1
val versaoNome = propriedade("vladoVersaoNome") ?: "1.0.0"

android {
    namespace = "app.vlado.mesa"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.vlado.mesa"
        minSdk = 26
        targetSdk = 35
        versionCode = versaoCodigo
        versionName = versaoNome
        manifestPlaceholders["configRede"] = "@xml/network_security_config"
    }

    buildFeatures {
        buildConfig = true
    }

    flavorDimensions += "ambiente"
    productFlavors {
        create("sala") {
            dimension = "ambiente"
            applicationIdSuffix = ".sala"
            versionNameSuffix = "-sala"
        }
        create("redacao") {
            dimension = "ambiente"
            applicationIdSuffix = ".redacao"
            versionNameSuffix = "-redacao"
        }
    }

    signingConfigs {
        if (arquivoAssinatura != null) {
            if (!arquivoAssinatura.isFile) throw GradleException("Arquivo de assinatura não encontrado: $arquivoAssinatura")
            val props = Properties().apply { arquivoAssinatura.inputStream().use { load(it) } }
            fun obrigatoria(chave: String): String =
                props.getProperty(chave)?.takeIf { it.isNotBlank() }
                    ?: throw GradleException("Chave '$chave' ausente em $arquivoAssinatura")
            create("vlado") {
                val loja = File(obrigatoria("storeFile"))
                storeFile = if (loja.isAbsolute) loja else File(arquivoAssinatura.parentFile, loja.path)
                storePassword = obrigatoria("storePassword")
                keyAlias = obrigatoria("keyAlias")
                keyPassword = obrigatoria("keyPassword")
                storeType = props.getProperty("storeType", "pkcs12")
            }
        }
    }

    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".depuracao"
            versionNameSuffix = "-depuracao"
        }
        getByName("release") {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("vlado")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkReleaseBuilds = true
    }

    testOptions {
        unitTests.isIncludeAndroidResources = false
    }
}

/** Gera a configuração de rede da depuração confiando na AC de homologação informada. */
abstract class GerarConfigRedeHomologacao : DefaultTask() {
    @get:InputFile
    abstract val certificado: RegularFileProperty

    @get:Input
    abstract val host: Property<String>

    @get:OutputDirectory
    abstract val saida: DirectoryProperty

    @TaskAction
    fun gerar() {
        val raiz = saida.get().asFile
        raiz.deleteRecursively()
        File(raiz, "raw").mkdirs()
        File(raiz, "xml").mkdirs()
        certificado.get().asFile.copyTo(File(raiz, "raw/homologacao_ca.pem"), overwrite = true)
        File(raiz, "xml/network_security_config_homologacao.xml").writeText(
            """
            <?xml version="1.0" encoding="utf-8"?>
            <!-- Gerado só para a variante de depuração. A release não usa este arquivo. -->
            <network-security-config>
                <base-config cleartextTrafficPermitted="false">
                    <trust-anchors>
                        <certificates src="system" />
                    </trust-anchors>
                </base-config>
                <domain-config cleartextTrafficPermitted="false">
                    <domain includeSubdomains="false">${host.get()}</domain>
                    <trust-anchors>
                        <certificates src="@raw/homologacao_ca" />
                    </trust-anchors>
                </domain-config>
            </network-security-config>
            """.trimIndent() + "\n"
        )
    }
}

val gerarConfigRede = caHomologacao?.let { ca ->
    tasks.register<GerarConfigRedeHomologacao>("gerarConfigRedeHomologacao") {
        certificado.set(ca)
        host.set(URI(requireNotNull(origemDepuracao)).host)
        saida.set(layout.buildDirectory.dir("generated/vlado/homologacao/res"))
    }
}

androidComponents {
    onVariants { variante ->
        val depuracao = variante.buildType == "debug"
        val origemDoSabor = when (variante.flavorName) {
            "sala" -> origemSala
            "redacao" -> origemRedacao
            else -> throw GradleException("Sabor desconhecido: ${variante.flavorName}")
        }
        val origem = if (depuracao && origemDepuracao != null) origemDepuracao else origemDoSabor
        variante.buildConfigFields?.put(
            "ORIGEM",
            BuildConfigField("String", "\"$origem\"", "Única origem carregada na WebView")
        )
        if (depuracao && gerarConfigRede != null) {
            variante.sources.res?.addGeneratedSourceDirectory(gerarConfigRede, GerarConfigRedeHomologacao::saida)
            variante.manifestPlaceholders.put("configRede", "@xml/network_security_config_homologacao")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.webkit:webkit:1.12.1")

    testImplementation("junit:junit:4.13.2")
    // Implementação real de org.json para os testes de JVM (o android.jar só traz stubs).
    testImplementation("org.json:json:20240303")
}
