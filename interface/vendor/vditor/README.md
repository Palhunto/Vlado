# Vditor incorporado

Versão: **4.0.1**, licença MIT (arquivo `LICENSE`). Origem: https://github.com/Vanessa219/vditor.

Arquivos essenciais copiados do pacote oficial npm, sem alterações: editor, CSS, Lute, português brasileiro, ícones Ant e tema claro. O pacote foi conferido com o SHA-512 publicado no registro npm antes da extração. `manifesto.json` registra o URL exato, a integridade do pacote e o SHA-256 de cada arquivo incorporado.

O servidor publica somente os seis recursos em `dist/` listados explicitamente em `scripts/rotas_estaticas.py` (`ARQUIVOS`). Licença, manifesto e este documento não são rotas públicas. Não há instalação npm nem requisição a CDN ao abrir o caderno.

A integração e os estilos da Mesa ficam em `interface/editor_notas.js` e `interface/style.css`. Atualizações devem preservar a licença, regenerar o manifesto e executar os testes de HTTP/integridade e de navegador com corpus sintético.
