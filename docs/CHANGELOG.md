# Mudanças

## 2.2.0 — Onda 0 (código; instalador ainda não gerado)

Uma versão por release: `configuracao.json`, `VLADO_VERSAO` e o instalador passam a ter o mesmo número, e `testes/test_versoes_alinhadas.py` exige a igualdade. O campo `versao` de `configuracao.json` não é lido por nenhum código e não é a versão dos prompts (`1.4.1`, em `scripts/comum.py`). Só a string de versão do instalador mudou; o `Vlado-Setup.exe` publicado continua o da release 2.1.0.

## 2.1.0 — 2026-11-20 — Instalador Windows com as fases 01 a 09

Primeiro instalador com a lapidação completa: contrato de evidência e quadros, tabelas de apuração, leitura de DOCX e XLSX com localizador, fontes web por apuração (modo opcional de domínio único), conferência da redação, entrevistas e pedidos, salvamento automático de rascunhos e as correções de segurança da fase 09. O detalhamento de cada fase está na seção abaixo.

## 2026-11-19 — Lapidação: fases 01 a 09

Novas áreas, integradas em `codex/lapidacao`: contrato de evidência e quadros (hipóteses, linha do tempo, comparador, mapa de relações), tabelas de apuração com fonte por célula, leitura de DOCX e XLSX com localizador e OCR de imagens a pedido, rascunhos com retomada do caso, design system com tokens, fontes web por caso com domínio único, conferência da redação por afirmação e preparação de entrevistas e pedidos de informação. Ver o README ("Quadros, redação e retomada" e "Fontes web por apuração") e [FLUXO_PONTA_A_PONTA.md](FLUXO_PONTA_A_PONTA.md).

### Segurança (revisão da fase 09)

- **S1:** os descartes de rascunho de cada conta têm teto (20 arquivos por convidado, 200 para as demais contas); ao chegar ao teto, os descartes mais antigos são apagados. Rascunho aberto nunca é apagado.
- **S2:** texto escondido por CSS nas capturas continua sem detecção; o README avisa os casos. Decisão em aberto.
- **S3** (`54ce720`, `41c7c2f`): `<li hidden><b>X<li>Y` e equivalentes com `td`, `th`, `tr`, `dt`, `dd` e `option` não escondem mais o item seguinte. Como no navegador, o fechamento implícito de `li`, `dt` e `dd` para nos elementos especiais do HTML, menos `address`, `div` e `p`; `td`, `th`, `tr` e `option` param no limite da tabela ou da lista. A primeira versão (`54ce720`) atravessava `section`, `article`, `nav` e outros elementos especiais e deixava texto oculto entrar na cópia sem a marca (B1); `41c7c2f` corrigiu.
- **S4:** as rotas que recebem o texto inteiro da redação aceitam pedido de até 512 KB, o bastante para 50 000 caracteres acentuados; acima do limite do texto, a recusa tem mensagem própria.
- **S5:** `continuidade-resumo` entrou na lista de operações só para administração dos testes; um teste novo confere que o convidado alcança só os rascunhos da pergunta.
- **S6:** o editor de notas retira `<iframe>`, `<object>` e `<embed>` do HTML que gera, além da limpeza do Vditor e da CSP. O `innerHTML` do editor fica como exceção aceita.

### Pendências corrigidas

- **N4:** o resumo da entrada do caso só aparece quando o servidor anuncia `continuidade_resumo`.
- **N6:** na conta da tabela, só os valores recebem o ponto de milhar; IDs como `E1234` ficam como estão.
- **N7:** no mapa, a ligação aberta tem traço próprio (6 px e cor própria) e o foco tem 4 px com halo, com contraste de 3:1 nos dois temas.
- **M3:** na exportação da redação, a URL do arquivo anterior é liberada antes de criar a nova.
- **M5:** o resumo da conferência concorda em número ("1 parcial", "2 parciais"), em português e em inglês.
- **M6:** as seções da redação e das entrevistas ganharam margem superior no celular.

### Integração

- `/api/integracao` passa a anunciar `fontes_web`, como as outras áreas com rota.
- Teste de ponta a ponta das fases 01 a 08 em `testes/test_ponta_a_ponta_fases.py`.
