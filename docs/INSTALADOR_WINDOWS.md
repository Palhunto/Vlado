# Instalador Windows (Vlado-Setup.exe)

O `Vlado-Setup.exe` instala a Mesa do Vlado num computador Windows 10/11 (64 bits), por usuário, sem pedir administrador. Já vem com tudo: o `Vlado.exe` (Python, OCRmyPDF e demais bibliotecas embutidos), o Tesseract com os idiomas português, inglês e detecção de orientação (`por`, `eng`, `osd`) e o Ghostscript. Nada depende do PATH do sistema nem de instalações prévias.

## Arquivo desta versão

O build 2.0.4 carrega o esquema de achados da pasta interna do executável. Na versão anterior, o backend procurava `modelos/ACHADOS.schema.json` na pasta do programa e falhava ao validar a geração inicial, antes da revisão. Feche o Vlado, instale a atualização e use **Tentar novamente** na conversa para continuar a mesma rodada, se a opção estiver disponível.

Desde o 2.0.3, o instalador inclui `codex-rejected-cas.pem` quando esse arquivo acompanha o Python de build. Sua ausência no 2.0.2 causava `[Errno 2]` ao inicializar HTTPS, antes da primeira chamada à Anthropic ou à OpenAI.

Desde o 2.0.2, a primeira pergunta e os complementos usam a mesma pasta temporária curta em `execucoes`. O teste de 16/11/2026 simulou os limites de caminho do Windows com PDFs sintéticos e um provedor simulado. As duas rodadas completaram as seis etapas, com R001 intacta e o original e o derivado preservados e consultáveis na R002.

| Item | Valor |
| --- | --- |
| Arquivo | `Vlado-Setup.exe` (gerado; fora do git) |
| Versão | 2.1.0 |
| Tamanho | 127,8 MiB (133.974.955 bytes) |
| SHA-256 | `574da2e02d45c2744200373f01871e6fd30f6517d015c5fccf907e30d4cab5fe` |

Confira o hash antes de instalar, no PowerShell:

```powershell
Get-FileHash .\Vlado-Setup.exe -Algorithm SHA256
```

## Aviso do SmartScreen (instalador sem assinatura)

O instalador ainda **não tem assinatura de código**. Na primeira execução o Windows pode mostrar "O Windows protegeu o computador". Depois de conferir o SHA-256 acima, clique em **Mais informações** e em **Executar assim mesmo**. A pendência é obter um certificado de assinatura de código (OV ou EV) e assinar o `Vlado.exe` e o `Vlado-Setup.exe` com `signtool`.

## O que a instalação faz

- Programa em `%LOCALAPPDATA%\Programs\Vlado` (`Vlado.exe`, `tesseract\`, `ghostscript\`, `licencas\`).
- Atalhos no Menu Iniciar (Vlado e Desinstalar Vlado) e, se marcado, na área de trabalho.
- Desinstalador em Configurações > Aplicativos.
- Dados em `%LOCALAPPDATA%\Vlado`: `casos\`, `conversas\`, `execucoes\`, `acesso\` (contas e sessões), `segredos\chaves.json`, `logs\`. Essa pasta é criada pelo próprio Vlado e **é preservada na atualização e na desinstalação**. Para apagar tudo, remova-a à mão depois de desinstalar.

Instalação silenciosa (por exemplo, para TI): `Vlado-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER`. Desinstalação silenciosa: `unins000.exe /VERYSILENT` na pasta do programa.

## Primeira abertura

1. Abra o **Vlado** pelo Menu Iniciar ou pela área de trabalho. Não aparece janela de terminal: o Vlado sobe o servidor em `http://127.0.0.1:<porta>` (8765 quando livre) e abre o navegador padrão.
2. Sem nenhuma conta, a página mostra **Criar administrador**: nome, login, senha (mínimo 12 caracteres) e confirmação. Essa tela só aceita o próprio computador e desaparece de vez depois da primeira conta.
3. Entre com o login criado. Daí em diante, toda abertura pede login e senha (sessão de até 12 h, encerrada após 2 h sem uso; 5 erros seguidos bloqueiam o login por 15 min).
4. Em **Configurações** (só para a administração), crie contas para outras pessoas: convidado (só pergunta à IA, nas apurações liberadas, com cota diária) ou administração. O link de ativação vale para este computador (`http://127.0.0.1:<porta>/ativar/...`).
5. Configure provedor e chave da API em **Perguntar à IA**; a chave fica em `%LOCALAPPDATA%\Vlado\segredos\chaves.json`.

Abrir o Vlado de novo com ele já aberto só reabre o navegador (uma instância por usuário). Para encerrar, use **Encerrar serviço** em Perguntar à IA.

## OCR embutido

O `Vlado.exe` aponta o OCR para as cópias instaladas por `VLADO_TESSERACT`, `VLADO_TESSDATA` e `VLADO_GHOSTSCRIPT` e usa `por+eng`. O OCRmyPDF roda dentro do próprio `Vlado.exe` (`Vlado.exe -m ocrmypdf`), sem janela de console. O texto de OCR continua sujeito a erros e não substitui a conferência no original.

## Gerar o instalador

Requisitos: Windows 64 bits, Python 3.12 em `.venv` com `requirements.txt` e `pyinstaller==6.16.0`.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller==6.16.0
.venv\Scripts\python.exe scripts\gerar_instalador.py
```

O script baixa as dependências de `instalador/dependencias.json` (versão e SHA-256 fixados; arquivo divergente é recusado) para `.ferramentas\downloads`, extrai Tesseract e Ghostscript dos instaladores originais com 7-Zip (sem executá-los), monta `build\instalador\payload`, congela o `Vlado.exe` com `instalador\vlado.spec` (`console=False`) e compila `instalador\vlado.iss` com Inno Setup 6.5.4 (instalado por usuário em `.ferramentas\innosetup`). Saída: `dist\Vlado-Setup.exe` e `dist\Vlado-Setup.exe.sha256`. Nenhuma etapa abre janela de console.

Antes de compilar o instalador, o script executa `Vlado.exe --verificar-https` para inicializar os clientes OpenAI e Anthropic com uma chave fictícia, sem chamadas de rede. O build para se algum deles falhar.

Arquivos: `scripts/vlado_lancador.py` (lançador), `instalador/vlado.spec`, `instalador/vlado.iss`, `instalador/dependencias.json`, `scripts/gerar_instalador.py`. Avisos de licença: `docs/AVISOS_DE_LICENCA.md`.

## Teste do instalador (15/11/2026, Windows 11, build 0bc6a6ff…321f70)

Instalação de teste numa pasta temporária, com dados isolados (`VLADO_DADOS`), sem navegador e sem tocar em `%LOCALAPPDATA%\Vlado`; tudo removido no fim.

| Verificação | Resultado |
| --- | --- |
| Instalação silenciosa `/VERYSILENT /CURRENTUSER` | Saída 0 em ~45 s; log "Administrative install mode: No", sem pedido de administrador; registro de desinstalação em HKCU; atalhos no Menu Iniciar (Vlado, Desinstalar Vlado) e na área de trabalho. |
| Sem console | `Vlado.exe` com subsistema PE 2 (GUI), sem processo filho nem janela própria. Um vigia de processos durante o OCR viu `gswin64c` e `tesseract` sempre com janela 0; os `cmd`/`conhost` presentes eram do Chrome e do Claude, não do Vlado. |
| Primeira abertura | `/` → `/primeiro-acesso`; "Criar administrador" respondeu 200 uma vez e 410 (`primeiro_acesso_encerrado`) na segunda; depois `/primeiro-acesso` → `/entrar`. |
| Login e logout | Login 200, cookie HttpOnly + SameSite=Strict sem Secure; logout 200 e a sessão passa a 401. |
| OCR de ponta a ponta | PDF sintético só com imagem cadastrado pelo instalado: recibo com `paginas_origem {"1": "ocr"}`, motor OCRmyPDF 16.10.4 com Ghostscript 10.05.1 e Tesseract v5.4.0.20240606 embutidos, `por+eng`, sem avisos. |
| Encerrar serviço | `codex-desligar` (admin) devolve 200 e o processo `Vlado.exe` termina. |
| Atualização | Reinstalar por cima: saída 0, `acesso.json` com o mesmo hash. |
| Desinstalação silenciosa | Saída 0; programa, atalhos e registro removidos; os 36 arquivos de dados (casos, contas, sessões) preservados com o mesmo hash. |
| Reinstalação | `/` → `/entrar` (sem nova tela de administrador); login com a conta anterior 200. |

Falha encontrada e corrigida neste teste: no Windows o OCRmyPDF recebia `nul` (`os.devnull`) como arquivo de saída e falhava ("unable to find trailer dictionary"); o cadastro caía no motor alternativo (Tesseract direto) e o Ghostscript nunca era usado. A saída passou a ser `-` em `scripts/ocr.py`.

## Pendências

- Certificado de assinatura de código (SmartScreen).
- O link de ativação de convidados usa a porta do momento; se a porta mudar (8765 ocupada), gere um novo link.
