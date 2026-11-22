# Fontes incluídas na interface

Arquivos obtidos dos repositórios oficiais em 06/11/2026, sem instalação no Windows. São servidos somente pela própria Mesa; não há carregamento de fontes pela rede durante o uso da interface.

- [Source Serif 4 — Roman variável](https://github.com/adobe-fonts/source-serif/blob/release/VAR/SourceSerif4Variable-Roman.ttf): `SourceSerif4-Roman.ttf`, usado nos títulos. Licença original preservada em `LICENSE-SourceSerif4.md`.
- [Source Sans 3 — Upright variável](https://github.com/adobe-fonts/source-sans/blob/release/VF/SourceSans3VF-Upright.otf): `SourceSans3-Upright.otf`, usado na interface e na leitura. Licença original preservada em `LICENSE-SourceSans3.md`.

**O que a Mesa carrega (Onda 3, parte C):** os arquivos `SourceSerif4-latin.woff2` e `SourceSans3-latin.woff2`, subconjuntos latinos (ASCII, latim-1, latim estendido A, pontuação, setas e os sinais que a interface usa) das duas fontes acima, com o eixo variável de peso recortado a 400–800 (os pesos que a Mesa usa; o `@font-face` declara a mesma faixa) e os recursos de OpenType. Pesam 154 KB e 65 KB, contra 1,2 MB e 538 KB das fontes inteiras, que continuam aqui como origem e não são mais pedidas pelo CSS. Para refazer os WOFF2 depois de mudar a interface: `python interface/fonts/gerar_woff2.py` (precisa de `fonttools` e `brotli`, de preferência num ambiente à parte; `--conferir` falha se faltar glifo usado nas telas). Caractere fora do subconjunto cai na fonte de sistema: é o caso do ș e do ț romenos, do vietnamita e de sinais como o ≥, que as fontes inteiras tinham (limitação aceita; a interface é em português e inglês).

Os nomes dos arquivos foram abreviados; o conteúdo binário e os nomes internos das fontes foram preservados. Os arquivos `LICENSE-*.md` incluem as condições de redistribuição.
