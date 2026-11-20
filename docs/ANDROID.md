# App Android do Vlado

O app é uma casca WebView: carrega a Mesa hospedada (a mesma interface responsiva do navegador) a partir de **uma única origem HTTPS** fixada no build. Não há lógica de apuração no aparelho e nenhum segredo embutido. O código está em `android/`.

## Campos a preencher

| Campo | Valor |
| --- | --- |
| Domínio da sala (ambiente `demonstracao`) | `https://______________________` (hoje: marcador `https://demo.vlado.invalid`) |
| Domínio da redação (ambiente `editorial`) | `https://______________________` (hoje: marcador `https://redacao.vlado.invalid`) |
| Responsável pela chave de assinatura da redação | ______________________ |
| Onde a chave da redação fica guardada (fora do repositório e do pacote) | ______________________ |

Enquanto os domínios não forem preenchidos, os APKs gerados abrem a tela "Sem conexão": `.invalid` é um domínio reservado que nunca resolve.

## Variantes

| Variante | `applicationId` | Nome no aparelho | Ícone | Origem |
| --- | --- | --- | --- | --- |
| `sala` | `app.vlado.mesa.sala` | Vlado Sala | V branco sobre laranja | `-PvladoOrigemSala` (ambiente `demonstracao`) |
| `redacao` | `app.vlado.mesa.redacao` | Vlado Redação | V branco sobre azul-escuro | `-PvladoOrigemRedacao` (ambiente `editorial`) |

Os dois podem ficar instalados ao mesmo tempo. A variante de depuração (`salaDebug`, `redacaoDebug`) acrescenta `.depuracao` ao identificador, é depurável e serve só para homologação.

Detalhes:

- A origem precisa ser `https://host[:porta]`, sem caminho, consulta, fragmento ou credenciais. Se não for, o build falha.
- O `applicationId` não pode mudar depois de publicado na Google Play. Se a redação quiser outro prefixo (por exemplo, o domínio dela), troque `applicationId` em `android/app/build.gradle.kts` **antes** da primeira distribuição.

## Requisitos

- **JDK 21.** O JDK 26 é novo demais para o Android Gradle Plugin. Usamos o Temurin 21 portátil.
- **Android SDK.**
  - Pacotes: `platform-tools`, `platforms;android-35`, `build-tools;35.0.0`.
  - O AGP baixa sozinho o `build-tools;36.0.0` na primeira compilação, se a licença padrão do SDK já tiver sido aceita.
  - Para o emulador: `emulator` e `system-images;android-35;google_apis;x86_64`.
- **Versões do projeto.**
  - Gradle 9.9.1, pelo wrapper em `android/gradle/wrapper/`, com SHA-256 da distribuição fixado.
  - AGP 9.5.1 com Kotlin embutido.
  - `compileSdk`/`targetSdk` 35, `minSdk` 26.
  - Dependências: `androidx.webkit` 1.12.1, `core-ktx` 1.15.0, `activity-ktx` 1.9.3.

Nesta máquina as ferramentas ficam em `.ferramentas/` (ignorada pelo git e fora do pacote): `jdk/jdk-21.0.13+9`, `sdk/` e `gradle-home/`.

### Instalar o SDK sem `.bat`

O `sdkmanager.bat` das command-line tools 23 apenas repassa para `android.exe`. A classe Java continua no pacote e pode ser chamada direto pelo `java`:

```bash
F=E:/Vlado/Vlado/.worktrees/intercept/.ferramentas
CP=$(find $F/sdk/cmdline-tools/latest/lib -name '*.jar' | tr '\n' ';')
$F/jdk/jdk-21.0.13+9/bin/java.exe -Dcom.android.sdkmanager.toolsdir=$F/sdk/cmdline-tools/latest -cp "$CP" \
  com.android.sdklib.tool.sdkmanager.SdkManagerCli --sdk_root=$F/sdk \
  "platform-tools" "platforms;android-35" "build-tools;35.0.0"
```

Na primeira instalação o comando mostra a licença `android-sdk-license` e pede aceite. Para criar um AVD, use a classe `com.android.sdklib.tool.AvdManagerCli`, com o mesmo classpath.

## Compilar (sem `gradlew.bat`)

Rode o Gradle pelo jar do wrapper, a partir de `android/`:

```bash
export JAVA_HOME=E:/Vlado/Vlado/.worktrees/intercept/.ferramentas/jdk/jdk-21.0.13+9
export ANDROID_HOME=E:/Vlado/Vlado/.worktrees/intercept/.ferramentas/sdk
export GRADLE_USER_HOME=E:/Vlado/Vlado/.worktrees/intercept/.ferramentas/gradle-home
cd android
"$JAVA_HOME/bin/java.exe" -cp gradle/wrapper/gradle-wrapper.jar org.gradle.wrapper.GradleWrapperMain \
  -PvladoOrigemSala=https://sala.exemplo.org \
  -PvladoOrigemRedacao=https://mesa.exemplo.org \
  -PvladoAssinatura=C:/Users/<usuario>/.vlado-assinatura/keystore.properties \
  testSalaDebugUnitTest testRedacaoDebugUnitTest lintSalaRelease lintRedacaoRelease \
  assembleSalaRelease assembleRedacaoRelease bundleSalaRelease bundleRedacaoRelease
```

Saídas:

- APK: `app/build/outputs/apk/<variante>/release/app-<variante>-release.apk`
- AAB: `app/build/outputs/bundle/<variante>Release/app-<variante>-release.aab`

Copie os arquivos para `android/saidas/`, que é ignorada pelo git, e renomeie como `vlado-<variante>-<versionName>-<versionCode>.apk|aab`.

Para compilar uma variante só, passe apenas a tarefa dela, por exemplo `assembleRedacaoRelease`. Sem `-PvladoAssinatura` (ou a variável `VLADO_ASSINATURA`), a release sai **sem assinatura** e o build avisa disso.

### Trocar a origem

Passe `-PvladoOrigemSala=` e/ou `-PvladoOrigemRedacao=` no build. Nada no código muda, e a origem fica gravada em `BuildConfig.ORIGEM`. Para fixar a origem de uma vez, troque os padrões `origemPadraoSala` e `origemPadraoRedacao` em `android/app/build.gradle.kts`. Só vale `https://`.

### Atualizar a versão

| Propriedade | Padrão | O que é |
| --- | --- | --- |
| `-PvladoVersaoCodigo=` | 1 | Inteiro. Precisa crescer a cada distribuição, senão o Android recusa a atualização. |
| `-PvladoVersaoNome=` | `1.0.0` | Texto mostrado ao usuário. Recebe o sufixo `-sala` ou `-redacao`. |

A atualização instala por cima e mantém a sessão **apenas se o APK novo for assinado com a mesma chave**.

## Assinatura

O `keystore.properties` fica **fora do repositório e do pacote**:

```properties
storeFile=C:/caminho/fora/do/repo/vlado-redacao.p12   # absoluto, ou relativo à pasta deste arquivo
storePassword=...
keyAlias=...
keyPassword=...
storeType=pkcs12
```

O build lê esse arquivo do caminho indicado em `-PvladoAssinatura=` ou na variável `VLADO_ASSINATURA`.

**Chave de demonstração.** A chave usada nos artefatos desta entrega é de **demonstração**:

- Gerada em `C:\Users\<usuario>\.vlado-assinatura\` (PKCS12, RSA 3072, alias `vlado-demonstracao`, senha aleatória).
- Arquivos legíveis só pelo usuário.

**Chave da redação.** A redação deve gerar a própria chave e guardá-la com backup. Perder a chave impede atualizar o app já instalado. Comando:

```bash
keytool -genkeypair -storetype PKCS12 -keystore vlado-redacao.p12 -alias vlado-redacao \
  -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=..., O=..." \
  -storepass:env SENHA -keypass:env SENHA
```

Depois:

1. Escreva o `keystore.properties` ao lado da chave.
2. Restrinja as permissões ao responsável.
3. Compile com `-PvladoAssinatura=` apontando para ele.

Para a Google Play, use a assinatura de apps da Play. Nesse caso a chave local vira a **chave de upload**.

## Verificar SHA-256 e certificado

```bash
sha256sum android/saidas/*.apk android/saidas/*.aab
"$JAVA_HOME/bin/java.exe" -jar "$ANDROID_HOME/build-tools/35.0.0/lib/apksigner.jar" verify --verbose --print-certs android/saidas/vlado-sala-1.0.0-1.apk
"$JAVA_HOME/bin/jarsigner.exe" -verify android/saidas/vlado-sala-1.0.0-1.aab
"$JAVA_HOME/bin/keytool.exe" -printcert -jarfile android/saidas/vlado-sala-1.0.0-1.aab
```

Publique o SHA-256 de cada arquivo e o SHA-256 do certificado num canal separado do arquivo. Quem instala confere os dois.

Os artefatos desta entrega usam a chave de demonstração. O SHA-256 do certificado é:

`b6c12b995f92b400f2b8fef8e8561b6ffb38c5a6bcefc146459b98484fadb5dd`

## Distribuir

- **APK direto, por canal privado** (sala, homologação, poucos aparelhos):
  - Envie o APK e, separadamente, o SHA-256 dele.
  - O aparelho precisa permitir "instalar apps desconhecidos" para o app que abre o arquivo.
  - Não há atualização automática: cada versão nova é um APK novo, com `versionCode` maior e a mesma chave.
- **AAB para a Google Play** (redação, distribuição ampla):
  - Envie o `.aab` pelo Play Console, de preferência numa faixa de teste interno.
  - A Play pode exigir `targetSdk` mais recente que 35. Confira a regra vigente antes de enviar; mudar o alvo exige novo teste.

## Segurança (o que o app garante)

**Origem**
- Só a origem configurada carrega na WebView:
  - Links de outra origem (`http`, `https`, `mailto`, `tel`) abrem no app do sistema, e só com toque do usuário.
  - `intent:`, `file:`, `content:`, `javascript:`, `data:` e `blob:` de outra origem são bloqueados.
- Toda requisição de rede para outra origem é recusada em `shouldInterceptRequest`. Isso vale inclusive para POST de formulário, que não passa por `shouldOverrideUrlLoading`.

**WebView**
- Desligados: acesso a arquivos e a content providers, conteúdo misto, múltiplas janelas, geolocalização.
- Permissões de câmera e microfone são negadas.
- Safe Browsing fica ativo.
- Depuração remota da WebView só existe na variante debug.

**Cookies**
- Cookies de primeira parte são aceitos e os de terceiros são recusados. O cookie de sessão é `HttpOnly; Secure; SameSite=Strict`.
- O app grava os cookies em `onPause`, para a sessão sobreviver se o processo for encerrado.
- Backup na nuvem e transferência entre aparelhos estão desligados.

**TLS e rede**
- `network_security_config` da release: só certificados do sistema, sem texto claro.
- Erro de TLS mostra "Conexão não segura" sem opção de prosseguir.

**Ponte de downloads**
- Não há `addJavascriptInterface`. A ponte é `WebViewCompat.addWebMessageListener`, que injeta `window.VladoAndroid` só na origem configurada; o app ainda confere quadro principal e origem.
- A mensagem (`{nome, tipo, base64}`) é tratada assim:
  - limite de 25 MB, um download por vez;
  - nome saneado (sem caminho, controles ou marcas bidi);
  - MIME numa lista permitida;
  - extensão amarrada ao MIME: `x.apk` declarado como PDF vira `x.apk.pdf`, e tipo desconhecido vira `.bin` sem botão "Abrir".

## Homologação local (só variante de depuração)

A variante debug aceita duas propriedades extras. A release nunca as usa.

- `-PvladoOrigemDepuracao=https://10.0.2.2:8443`: no emulador, `10.0.2.2` é o computador.
- `-PvladoCaHomologacao=<ac.pem>`: certificado **público** de uma AC de teste.
  - O build recusa o arquivo se houver chave privada ou mais de um certificado.
  - A AC gera um `network_security_config` só para a debug, e só vale para o host da origem de depuração (`domain-config`).

Roteiro usado nesta entrega:

1. Copiar o projeto para uma pasta temporária e criar uma conta de teste com `VLADO_ACESSO` apontando para um arquivo temporário.
2. Iniciar o servidor em `--modo piloto --porta 8770 --origem https://10.0.2.2:8443`.
3. Colocar à frente um proxy TLS de teste em `127.0.0.1:8443`, com certificado emitido por uma AC autoassinada temporária e `subjectAltName=IP:10.0.2.2`.
4. Compilar `assembleSalaDebug` com as duas propriedades acima, instalar com `adb install` e abrir.

## Testar

**Testes de JVM e lint**

- Testes: `testSalaDebugUnitTest testRedacaoDebugUnitTest`. Cobrem origem autorizada, esquemas bloqueados, nomes, MIME, extensões, limites e `accept`.
- Lint: `lintSalaRelease lintRedacaoRelease`, com `abortOnError`.

**Emulador.** API 35 google_apis x86_64, headless (`emulator.exe -no-window`, aceleração WHPX), com a variante debug de homologação:

| Teste | Resultado |
| --- | --- |
| Login | Passou |
| Navegação e voltar pelo histórico (`pushState`) | Passou |
| Voltar na raiz fecha o app | Passou |
| Rotação | Sem recarregar; o diálogo do original continua aberto |
| Upload | Seletor do sistema e cadastro de um PDF sintético |
| Visualização do original | pdf.js, na Mesa |
| Download do original pela ponte | Bytes idênticos (SHA-256 conferido) |
| Abrir o PDF no visualizador do sistema | Passou |
| Sem conexão e "Tentar de novo" | A sessão continuou válida |
| Sessão após reiniciar o app | Mantida |
| Erro de TLS (AC não confiável) | Tela sem opção de prosseguir |

A release `sala` assinada foi instalada e abre a tela "Sem conexão", porque a origem `.invalid` é o marcador.

**Aparelho físico.** Não houve teste em aparelho físico.

## Limitações conhecidas

**PDF e `#page`**
- Dentro da Mesa, o original é desenhado com pdf.js e abre na página citada.
- Ao baixar e abrir no visualizador do sistema, `#page=N` não vale: o visualizador abre na primeira página. A página citada aparece na tela da Mesa ("Página física N do PDF") e precisa ser procurada manualmente.

**Downloads**
- Chegam como `blob:` gerado por `fetch` POST. Sem a ponte (WebView antigo, sem `WEB_MESSAGE_LISTENER`), o app só avisa e não grava. Atualize o "Android System WebView".
- Limite de 25 MB por arquivo. Acima disso, use a Mesa no navegador.
- No Android 10 ou superior, os arquivos vão para `Downloads/Vlado`. No Android 8 e 9, o sistema pergunta onde salvar.

**Cookies**
- A sessão segue as regras do servidor: 12 h absolutas e 2 h de inatividade.
- Limpar os dados do app encerra a sessão. Como o backup está desligado, trocar de aparelho exige entrar de novo.

**Rascunho do Caderno**
- O rascunho fica em `sessionStorage` e some se o Android encerrar o processo do app em segundo plano.

**Domínios**
- Enquanto os domínios forem `.invalid`, os APKs servem só para conferir instalação e assinatura.
