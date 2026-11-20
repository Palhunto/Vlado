# O que sai da instalação na inferência

Texto para o combinado com o responsável editorial do Intercept. Descreve o código desta versão (`scripts/codex_apuracao.py`, `scripts/inferencia_api.py`, `scripts/provedor_anthropic.py`, `scripts/provedor_openai.py`). Vale para o ambiente editorial e para os demais.

## Quando algo sai

Só quando alguém com conta envia uma **pergunta ou complemento** na área Perguntar à IA. Cadastro de documentos, OCR, índice, Caderno, conferência de achados, diligências, exportações, backup e login **não** chamam o provedor. O OCR é local (OCRmyPDF/Tesseract dentro do servidor).

## Para onde vai

Para a API do provedor configurado pela administração (Anthropic ou OpenAI), com a conta e a chave da redação. O processamento é online e cobrado por uso. A retenção e o uso dos dados pelo provedor seguem o contrato e as configurações dessa conta; confirme-os antes de usar material sensível (por exemplo, prazo de guarda e uso para treinamento).

## O que vai em cada chamada

| Conteúdo | Vai ao provedor? | Observação |
| --- | --- | --- |
| Pergunta e complementos digitados | Sim | Texto integral. |
| Instruções do fluxo (`AGENTS.md`, `prompts/FLUXO_COMPLETO.md`, `README.md` congelados na rodada) | Sim | Texto do projeto, sem dados de reportagem. |
| Identificadores do caso e da rodada, `corpus_id` e a `configuracao.json` congelada | Sim | Metadados técnicos. |
| Lista de documentos do corpus da rodada (IDs, nomes de arquivo, hashes, cobertura de extração) | Sim | Quando o modelo pede a cobertura. Nomes de arquivo podem revelar o assunto: renomeie antes do cadastro se isso importar. |
| Trechos de documentos devolvidos pela busca (`buscar`) e passagens lidas (`ler`) | Sim | Só os trechos que o modelo pede, do corpus da rodada. Não há envio do acervo inteiro de uma vez, mas uma apuração longa pode enviar boa parte dele em trechos. |
| Texto de arquivos `.txt`/`.md`/`.csv`/`.tsv` (`texto`) | Sim | Até 200 linhas por chamada. |
| **Imagens de páginas de PDF** e imagens originais (`imagem`) | Sim | A página é renderizada no servidor (PNG, até 10 MB) e enviada quando o modelo pede leitura visual (tabelas, digitalizações, assinaturas). Imagens avulsas `.png`/`.jpg` vão inteiras. |
| Histórico da conversa (perguntas, respostas e resultados de ferramentas anteriores) | Sim, a cada chamada | A API é usada sem estado (`store=False` na OpenAI; mensagens reenviadas na Anthropic). Só as imagens mais recentes ficam no contexto; as antigas são retiradas e não voltam a ser enviadas. |
| Observações da conferência de achados que o usuário **escolheu** levar à pergunta | Sim | Só as selecionadas em "Continuar com estas observações". |
| Contribuições humanas e diligências que o usuário **escolheu** levar | Sim | Só as selecionadas, com autor declarado. |
| Notas do Caderno editável (área Caderno) | **Não** | Não há caminho de código que envie as notas ao modelo. |
| Documentos de outros casos, de outras rodadas ou fora do corpus congelado | **Não** | A ferramenta recusa. |
| Contas, senhas, sessões, links de ativação, registros de acesso | **Não** | |
| Chave de API | Só como credencial da chamada (cabeçalho), nunca no conteúdo | O texto enviado passa por `seguro()`, que apaga valores de chave conhecidos. |

## O que fica gravado no servidor

- `conversas/<id>/api_historico.json`: histórico enviado e recebido, **sem as imagens**.
- `execucoes/<caso>/<rodada>/saidas/codex_ferramenta_NNNN.json`: cada chamada de ferramenta com argumentos e resultado (sem imagens em base64).
- `execucoes/<caso>/<rodada>/saidas/api_uso_NNNN.json`: consumo de tokens por chamada.

Esses arquivos ficam nos volumes do ambiente e entram no backup.

## Pontos para decidir com a redação

1. Qual conta e qual provedor (e com quais termos de retenção) o ambiente editorial usa; quem paga.
2. Se documentos com fontes protegidas podem ir ao provedor; se não, não cadastrá-los num caso em que se fará pergunta à IA.
3. Se nomes de arquivo devem ser neutralizados antes do cadastro.
4. Por quanto tempo guardar históricos e registros de ferramenta no servidor.
5. Teto de gasto na conta do provedor (além dos limites do Vlado em `configuracao.json`).
