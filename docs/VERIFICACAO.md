# Verificação do VLADO

## 2.0.0 — entrega para o piloto do Intercept (15/11/2026)

Branch `entrega-intercept`. Tudo com dados sintéticos; nenhum dado de reportagem.

- **Suíte Python:** `python -m unittest discover -s testes` — 397 testes OK, 2 pulados de propósito (iniciador `.cmd`; permissão POSIX do backup, que não se aplica no Windows). `scripts/verificar_projeto.py` e `scripts/montar_fluxo.py --check`: OK.
- **Testes Node do Caderno e da Mesa móvel:** 58/58 (`caderno_rascunho`, `caderno_revisao_integrada`, `caderno_notas`, `caderno_estilo`, `editor_sob_demanda`, `editor_notas`, `mobile_navegacao`).
- **Regressões novas:** autorização por papel e revogação (`test_autorizacao.py`, 28), contas, migração v1→v2 e ativação (`test_acesso.py`, 39), persistência da tarefa marcada sem digitação, rascunho após falha de rede e conflito entre abas (`qa_caderno_editor.py` e `caderno_rascunho.cjs`), revisão integrada (`test_revisao_entrega.py`).
- **Homologação pela interface em modo hospedado** (`testes/qa_homologacao.py`, HTTPS de teste com certificado descartável, provedor simulado): 18 verificações no navegador e 4 no servidor — redirecionamento sem sessão, erro genérico de login, faixa de homologação, logout com sessão invalidada; cadastro do lote 1 com recibo (IDs e SHA-256 conferidos) e OCR local da página digitalizada; pergunta concluída com fonte; original citado aberto e baixado com o mesmo SHA-256; conferência de achado só depois de abrir o original; trecho com fonte inserido no Caderno com "Nota salva"; lote 2 no mesmo caso sem alterar os 139 arquivos da rodada anterior; convidada A só no caso liberado; convidado B recusado nas conversas de A, em exportação e notas; retirada de caso, desativação e recuperação de acesso valendo na requisição seguinte; 390 px sem rolagem horizontal. Encontrou e corrigiu um defeito: todo login vindo de IPv4 falhava após uma correção de revisão (`acesso._rede`).
- **Caderno no navegador** (`testes/qa_caderno_editor.py`): três estilos e níveis legados, tarefa por clique, toque e teclado com área de 44 px, marcação salva sem digitar e mantida após recarregar, ida e volta visual↔Markdown, falha de rede e rascunho restaurado, conflito entre abas, volta ao ponto da edição após abrir o original, 320/390 px, claro e escuro. Capturas em `docs/capturas/caderno/`.
- **Mesa móvel** (`testes/qa_mobile.py`): sem rolagem horizontal em 320–1365 px e a 200 % de zoom, alvos de 44 px, teclado virtual simulado, página citada aberta no pdf.js na página certa. Capturas em `docs/capturas/mesa/`.
- **Android:** build e lint das variantes `sala` e `redacao`; testes JVM; **só em emulador** (API 35, sem aparelho físico): login, voltar, rotação, upload, PDF na Mesa, download pela ponte com SHA-256 idêntico, abertura no visualizador do sistema, sem conexão, sessão mantida, recusa de certificado não confiável. Detalhes em `docs/ANDROID.md`.
- **Instalação a partir do pacote extraído:** o ZIP foi extraído numa pasta temporária, o caso sintético cadastrado e o primeiro administrador criado com os scripts do próprio pacote; o servidor do pacote subiu em modo hospedado, a ativação pelo link de uso único e o login funcionaram pela interface (`testes/qa_pergunta_real.py`, ensaio sem chave, sem custo).
- **Revisões:** segurança (backend, Android, isolamento) sem CRITICAL/HIGH; achados médios corrigidos (backup 0600 e preso ao ambiente, semeador recusa instalação real, empacotador mais rígido, execuções canceladas ao desativar conta ou retirar caso, IPv6 por /64, erro genérico para convidado). JS do Caderno: 3 HIGH (inserir em outra nota, sair, descartar com reenvio pendente) corrigidos com testes.

- **Pergunta real paga (15/11, autorizada pelo usuário, teto de US$ 1)** — `testes/qa_pergunta_real.py` sobre o pacote `vlado-d9ae63bc10fb.zip` extraído, em modo hospedado com HTTPS de teste, conta de administração ativada pelo link e login pela interface; corpus sintético Vila Serena (contrato com texto nativo + medição digitalizada lida por OCR local):
  - provedor OpenAI, modelo exibido e registrado `gpt-6.1-sol` (chave já salva, lida só pelo servidor);
  - pergunta com uma parte sustentada e outra sem suporte; execução concluída e publicada em 118 s (138 s com instalação e login);
  - 22 chamadas, 519.624 tokens de entrada (470.727 em cache), 6.138 de saída; custo estimado pelo preço de tabela do ensaio de 13/11: cerca de US$ 0,25 (confirmar no painel do provedor);
  - resposta: valor global R$ 8.750.000,00 (D001, p. 1) e acumulado pago R$ 3.900.000,00 (D002, p. 1, documento digitalizado), com 2 citações clicáveis; sócios da construtora declarados **não localizados** nos documentos, sem inferência. Sem conferência humana. Captura: `docs/capturas/homologacao/pergunta-real.png`.

### Não verificado nesta entrega

- **Docker:** imagem, `docker compose` dos três ambientes e backup/restauração em volumes Docker novos não rodaram (Docker Desktop parado). A restauração em pastas novas e em pastas ocupadas está coberta pelos testes de `backup.py`.
- **Publicação:** não há servidor, domínio nem canal; nada entrou no ar.
- Aparelho Android físico, TalkBack/VoiceOver, Firefox e Safari, teclado virtual real.

## 1.4.0 — integração por API e piloto hospedado (13/11/2026)

- **Testes automatizados:** 252 testes Python e 15 testes JavaScript na estação de desenvolvimento (Windows, Python 3.11). Falhas restantes: um teste de continuidade intermitente por tempo de execução (já existente antes) e, na suíte longa, os testes de exportação que rodaram antes da instalação do `python-docx` (passam depois de instalado). O teste do iniciador `.cmd` só roda com `VLADO_TESTAR_INICIADOR=1`, porque abre uma janela de console.
- **Ensaio real pela API** (`testes/qa_fluxo_real.py`, corpus sintético de dois textos fictícios, uma pergunta, sem complemento):
  - provedor OpenAI, modelo informado `gpt-6.1-sol`, chave colada na Mesa;
  - 6 etapas concluídas, publicação `r3_sintese/g1` verificada com 2 achados, nenhuma referência pendente;
  - 21 chamadas à API, 388.175 tokens de entrada (357.466 em cache) e 4.877 de saída, em 1 min 41 s;
  - custo estimado pelo preço de tabela: cerca de US$ 0,18 (confirmar no painel do provedor);
  - a resposta citou cada documento na linha correta e declarou os limites; não houve conferência humana.
- **Tentativa anterior:** parou na síntese com "Acesso negado" ao gravar `conversa.json` (duas gravações simultâneas no Windows), depois de cerca de US$ 0,16 em tokens. Corrigido no commit `c91912f`.
- **Apagamento definitivo, retomada, caderno com autoria pela conta e teste ponta a ponta** (commits `06ee326` e `0a0d6ce`): suíte completa com 324 testes Python 3.12, todos OK (1 pulado: o iniciador `.cmd`). O teste ponta a ponta (`testes/test_ponta_a_ponta.py`) restaura um backup em outra instalação e confere, pelo HTTP do piloto, originais com o mesmo hash, caderno com autoria, original aberto na página citada, histórico e isolamento entre duas contas. Nenhuma chamada de modelo.
- **Imagem Docker** (`docker build`, Docker 29.9.3 no Windows, imagem de 238 MB comprimida):
  - Python 3.12.16, OCRmyPDF 16.10.4, PyMuPDF 1.28.2, Tesseract 5.3.0 com `por`, `eng` e `osd`, Ghostscript 10.00.0, pngquant 2.17.0, unpaper 7.0.0;
  - OCR real de um PDF só-imagem dentro do container pelo motor `ocrmypdf`, com o texto reconhecido sem erro;
  - processo como usuário `vlado` (uid 10001), código sem permissão de escrita, pastas de dados graváveis; a imagem não contém chaves, ajustes, convites, casos, testes, `.venv` nem `.git`;
  - `HEALTHCHECK` chega a `healthy`, `/saude` responde `{"ok": true}` e a página sem convite responde 401; `docker compose config` válido.
- **Conferida no original:** o servidor só aceita a marcação depois que a mesma sessão da página abriu, pela Mesa, o original de cada trecho citado naquela revisão (registro em memória; reiniciar o servidor pede para reabrir). É uma proteção do fluxo de trabalho, não prova de leitura: quem tem a sessão pode baixar o original sem lê-lo.
- **Ensaio real em inglês sobre PDFs em português** (`testes/qa_fluxo_real.py --pdf --ingles`, provedor OpenAI, modelo informado `gpt-6.1-sol`):
  - corpus sintético com dois PDFs: uma ata com texto nativo e o fato na página 2, e um aviso só-imagem lido pelo OCR local (Tesseract, sem envio externo);
  - a primeira execução concluiu 5 das 6 etapas e parou na síntese pelo teto de 500 mil tokens por consulta, com situação "sem cota" e o que estava pronto preservado;
  - com o teto elevado, **Tentar novamente** retomou a mesma rodada `R001` direto na síntese, sem refazer etapas, e publicou `r3_sintese/g1` com 2 achados verificados;
  - a síntese saiu em inglês, em ordem cronológica, citando documento e página física corretos (ata na página 2, aviso na página 1) e os trechos em português;
  - uso total: 586.448 tokens de entrada (535.790 em cache) e 5.599 de saída; a retomada sozinha usou cerca de 75 mil de entrada e 484 de saída. Custo estimado pelo preço de tabela: cerca de US$ 0,25 no total (confirmar no painel do provedor). Não houve conferência humana.
- **Não verificado:** os PDFs da Americanas, o provedor Anthropic com chave real, o Caddy com certificado real e a implantação num servidor.

## Registro anterior (1.3.0)

O verificador de projeto confere a integridade dos prompts e o estado inicial do catálogo. Os testes automatizados usam dados sintéticos e um runtime simulado. Veja os comandos em [README.md](../README.md). O `INSTALAR_NO_NOTEBOOK.md` citado antes não existe mais; a instalação está na seção Instalação do README.

A cópia de migração de 13/11/2026 passou na integridade inicial, em 165 testes automatizados e na abertura HTTP com catálogo vazio, sem iniciar o modelo. O ensaio usou o Python disponível na estação de preparação. Instalação e login na estação de destino precisam ser verificados após a transferência.
