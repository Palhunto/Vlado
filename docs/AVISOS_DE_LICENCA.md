# Avisos de licença

Componentes de terceiros distribuídos neste pacote ou instalados pela imagem Docker e pelo app Android. Os textos completos das licenças vendorizadas acompanham os arquivos indicados.

## Licença do próprio Vlado

**Pendente.** O repositório não declara licença para o código do Vlado. Até o grupo decidir, o pacote é entregue ao Intercept para avaliação e piloto, sem concessão de redistribuição. Decisão em aberto na seção 12 de `Começar_Analise_Aqui.md`.

## Distribuídos no pacote (interface)

| Componente | Licença | Texto |
| --- | --- | --- |
| Vditor 4.0.1 (inclui Lute) | MIT | `interface/vendor/vditor/LICENSE` |
| pdf.js (pdfjs-dist) | Apache-2.0 | `interface/vendor/pdfjs/LICENSE` |
| Source Serif 4 | SIL Open Font License 1.1 | `interface/fonts/LICENSE-SourceSerif4.md` |
| Source Sans 3 | SIL Open Font License 1.1 | `interface/fonts/LICENSE-SourceSans3.md` |

## Instalados no servidor (requirements.txt e Dockerfile)

| Componente | Licença | Observação |
| --- | --- | --- |
| pypdf | BSD-3-Clause | |
| OCRmyPDF | MPL-2.0 | |
| PyMuPDF | **AGPL-3.0** (ou licença comercial da Artifex) | Num serviço acessível pela rede, a AGPL exige oferecer o código-fonte correspondente aos usuários. O código do Vlado está neste pacote; confirme com o jurídico se isso atende, ou retire o PyMuPDF (a leitura visual de páginas pelo modelo fica indisponível; o OCR segue pelo OCRmyPDF). |
| Ghostscript (apt) | **AGPL-3.0** | Usado pelo OCRmyPDF como programa externo, sem modificação. |
| Tesseract OCR (apt) | Apache-2.0 | |
| python-docx | MIT | |
| ReportLab | BSD-3-Clause | |
| anthropic (SDK) | MIT | |
| openai (SDK) | Apache-2.0 | |
| argon2-cffi | MIT | |
| Caddy 2.8 (imagem) | Apache-2.0 | |
| Python 3.12 (imagem base) | PSF License | |

## Instalador Windows (Vlado-Setup.exe)

O instalador copia para `%LOCALAPPDATA%\Programs\Vlado` o `Vlado.exe` (Python 3.12 e as bibliotecas de `requirements.txt` empacotados pelo PyInstaller) e os programas abaixo, sem modificação. Versões e SHA-256 conferidos em `instalador/dependencias.json`.

| Componente | Licença | Texto e código-fonte |
| --- | --- | --- |
| Ghostscript 10.05.1 (`gswin64c.exe`, `gsdll64.dll`) | **AGPL-3.0** | `licencas\ghostscript\` na pasta instalada (LICENSE/COPYING e `CODIGO_FONTE.txt`). Código-fonte correspondente: https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10051/ghostscript-10.05.1.tar.gz. Usado pelo OCRmyPDF como programa externo. |
| Tesseract OCR 5.4.0 (build UB Mannheim) | Apache-2.0 | `licencas\tesseract\`; código-fonte: https://github.com/tesseract-ocr/tesseract |
| Dados de idioma `por`, `eng`, `osd` (tessdata 4.1.0) | Apache-2.0 | https://github.com/tesseract-ocr/tessdata |
| PyMuPDF (dentro do `Vlado.exe`) | **AGPL-3.0** | Ver a observação da tabela acima; o código do Vlado acompanha o pacote. |
| Python 3.12 (dentro do `Vlado.exe`) | PSF License | |
| PyInstaller (carregador do `Vlado.exe`) | GPL-2.0 com exceção de bootloader | A exceção permite distribuir o executável gerado. |
| Inno Setup 6.5.4 (gera o instalador e o desinstalador) | Licença Inno Setup (permissiva) | https://jrsoftware.org/files/is/license.txt |

## App Android

| Componente | Licença |
| --- | --- |
| Kotlin, AndroidX (WebKit, AppCompat, Core) | Apache-2.0 |

Versões exatas: `requirements.txt`, `android/app/build.gradle.kts` e `interface/vendor/*/manifesto.json`.
