# PDF.js incorporado

Versão: **6.4.299** (build *legacy*, para navegadores e WebViews mais antigos), licença Apache-2.0 (arquivo `LICENSE`). Origem: https://github.com/mozilla/pdf.js, pacote npm `pdfjs-dist`.

Arquivos copiados sem alterações do pacote oficial (`npm pack pdfjs-dist@6.4.299`, conferido pelo npm contra o SHA-512 publicado no registro): a biblioteca e o worker minificados. `manifesto.json` registra o URL exato, a integridade do pacote e o SHA-256 de cada arquivo.

Uso: `interface/experiencia.js` carrega a biblioteca sob demanda quando um PDF original é aberto, renderiza a página citada em `canvas` (navegação de páginas e zoom) e destaca o trecho citado quando a camada de texto o encontra. A configuração usa `isEvalSupported: false`; a política de segurança permite `worker-src 'self'`, sem `unsafe-eval`. Não há CDN, fontes padrão, CMaps nem WebAssembly incorporados: PDFs com fontes não incorporadas usam fontes do sistema; imagens JPEG 2000/JBIG2 e textos CJK sem fonte incorporada podem não aparecer — "Baixar original" continua disponível.

O servidor publica só os dois `.mjs` listados explicitamente em `scripts/interface_pesquisa.py`. Atualizações devem preservar a licença, regenerar o manifesto e executar os testes de navegador com PDF sintético.
