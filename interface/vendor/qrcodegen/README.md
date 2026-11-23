# QR Code generator library (Project Nayuki)

Versão: **1.8.0** (commit `720f62bddb7226106071d4728c292cb1df519ceb`), licença MIT (arquivo `LICENSE`). Origem: https://github.com/nayuki/QR-Code-generator, pasta `typescript-javascript`.

O repositório só publica o fonte em TypeScript (`qrcodegen.ts`); `qrcodegen.js` é a compilação dele, sem outra alteração, com `typescript@5.6.3` e as opções do `build.sh` do projeto (`tsc --strict --lib DOM,DOM.Iterable,ES6 --target ES6 qrcodegen.ts`). `manifesto.json` registra o commit, o SHA-256 do fonte, o do arquivo compilado e o da licença. O arquivo não usa rede, `eval` nem o DOM.

Uso: `interface/fator.js` carrega o arquivo sob demanda, só quando o cadastro do segundo fator precisa desenhar o código QR (o endereço `otpauth://` que o servidor manda uma vez), e o desenha em SVG, sem guardar nada. Não há CDN: o servidor publica só `qrcodegen.js`, listado em `scripts/rotas_estaticas.py` (`ARQUIVOS`). Atualizações devem preservar a licença, regenerar o manifesto e rodar `testes/qrcode.cjs`.

Leitura conferida em 23/11/2026 com um decodificador de verdade, fora da suíte: a matriz gerada para o endereço `otpauth://` de teste (versão 8, correção M), para um texto curto, para um com acentos e para um de versão 10 foi lida pelo ZXing-C++ (`zxing-cpp` do PyPI) com o texto exato; as capturas do Chromium do passo 2 do cadastro (375 e 1440 px, tema claro e escuro) também. O detector `cv2.QRCodeDetector` do OpenCV falhou só na matriz da versão 8 (a mesma que o ZXing leu): é uma limitação conhecida dele, e não do gerador.
