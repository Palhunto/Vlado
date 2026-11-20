# Fluxo automático da Mesa de apuração — 06/11/2026 (atualizado em 13/11/2026)

Novas perguntas e complementos passam por um controlador no backend. A inferência é feita pela API do provedor configurado (Anthropic ou OpenAI; ver [INTEGRACAO_API.md](INTEGRACAO_API.md)). Uma resposta do modelo encerrando seu turno já não basta para marcar a rodada como concluída: é preciso registrar as seis etapas, publicar os registros canônicos e verificar o índice separado de achados.

## Como funciona

1. A pergunta congela uma rodada e seu índice documental. Complementos preservam a conversa e a versão atual do corpus, criando outra rodada. Uma ampliação exige seleção explícita em **Continuar com novos documentos**.
2. O backend conduz inventário, plano, busca, geração inicial, revisão e síntese em seis etapas internas, na mesma conversa. Os prompts existentes permanecem no snapshot; instruções adicionais descrevem os contratos de entrega pela ferramenta `consultar_acervo`.
3. Inventário, plano e busca recebem registros textuais. Geração inicial, revisão e síntese entregam JSON pelo campo `texto` da ação `guardar`, mantendo a ferramenta compatível com conversas existentes.
4. O backend valida as entregas e monta os campos técnicos: IDs, referências, localizadores, hashes, versões e vínculos de evidência. A geração inicial publica `r1_busca`; a revisão, `r2_revisao`; a síntese, `r3_sintese`.
5. Na continuidade com novos documentos, uma sétima etapa obrigatória entrega a comparação estruturada com a última rodada concluída. Depois das etapas exigidas, o backend valida novamente os registros e os artefatos, constrói ou confere o índice de achados `g1` e só então publica a resposta final, o comparativo quando aplicável e o estado concluído.

O SQLite documental continua sendo um índice de fontes. As conclusões da IA entram no banco separado de achados; não viram documentos nem resultados do FTS documental.

## Validação e rastreabilidade

A evidência precisa corresponder a uma leitura real da rodada. A revisão exige nova leitura das fontes utilizadas. Correções criam versões com revisão explícita; evidências adicionais preservam as anteriores. A síntese só inclui a versão mais recente com suporte registrado e exige vínculos aos achados e às fontes. Sem achados sustentados, o resultado deve registrar insuficiência.

Declaração documental, alegação atribuída, inferência e pendência permanecem distintas. Ausência em busca não é prova de inexistência. Fontes continuam sendo dados de análise, sem autorização para executar instruções. Nenhum registro automático equivale a revisão independente ou aprovação humana; a execução não preenche marcações humanas automaticamente. A conferência pela interface é registrada separadamente, conforme [ACHADOS_IA.md](ACHADOS_IA.md).

Essas verificações asseguram o contrato técnico e a rastreabilidade. A avaliação semântica do suporte continua dependendo do modelo e de conferência humana.

## Correção automática, estados e cancelamento

Cada etapa tem até duas tentativas. Uma entrega inválida ou ausente retorna o motivo ao modelo para correção na mesma rodada. Candidatos rejeitados ficam preservados em arquivos novos. Cada etapa tem no máximo 60 passos do provedor, e cada chamada de ferramenta aguarda até 300 s. Erros do provedor (autenticação, conexão ou limite) encerram a execução com a mensagem correspondente. Configuração inválida ou chave ausente interrompem a pergunta antes de qualquer chamada ao modelo.

Falha persistente de entrega resulta em `incompleto`. A publicação final tem até duas tentativas técnicas e reutiliza registros idênticos, sem duplicar versões. Falhas não recebem resposta final verificada. Cancelamento interrompe a chamada em execução, fecha as chamadas de ferramenta pendentes e preserva saídas parciais.

A interface apresenta a etapa atual, mensagens provisórias e o estado `publicando`. O botão **Consultar achados desta rodada** abre a revisão final e a geração verificadas na área existente de achados. Atualizações anteriores à verificação continuam identificadas como provisórias, mesmo que o modelo use linguagem conclusiva.

## Arquivos e compatibilidade

- `scripts/fluxo_codex.py`: controlador das entregas, evidências, revisões e publicação.
- `scripts/codex_apuracao.py`: conversas, eventos, cancelamento e integração com as ferramentas existentes.
- `scripts/inferencia_api.py` e `scripts/provedor_anthropic.py` / `scripts/provedor_openai.py`: chamadas ao provedor, histórico e uso de tokens.
- `interface/codex.js`: etapas, estados provisórios e acesso aos achados publicados.
- `saidas/codex_fluxo_estado.json`: ponteiro operacional atualizado atomicamente.
- `saidas/codex_execucao.json`: estado final, etapas validadas, recibo de publicação, `uso_tokens` e `modelos_informados`.
- `saidas/api_uso_NNNN.json`: uso de tokens de cada chamada ao provedor na rodada.
- `saidas/codex_tentativa_*.json` e artefatos identificados por hash: preservação das entregas e tentativas.

Os nomes `codex_*` e `fluxo_codex.py` foram mantidos por compatibilidade com rodadas existentes.

As novas rodadas registram `fluxo_automatico: 2`. As rodadas históricas R004/R005 da Americanas não foram reescritas nem publicadas retroativamente. A auditoria que encontrou etapas/publicação ausentes continua válida para aquelas execuções.

## Como usar

Configure a chave de API no ambiente do servidor e inicie a Mesa pelo iniciador habitual. Após uma atualização do backend, recarregue a página com Ctrl+F5. Em **Conversa com os documentos**, escolha a apuração e envie a pergunta. O restante do fluxo acontece automaticamente. Um complemento na mesma conversa também percorre todas as etapas. Para incorporar outro lote, use **Continuar com novos documentos**, confira o cadastro e escolha a versão antes de enviar. O [guia da continuidade](CONTINUIDADE_DOCUMENTAL.md) descreve comparação, conferência e preservação.

O modelo processa online e o uso é cobrado pelo provedor, por uso. Não há assinatura nem login ChatGPT.

## Verificações

Nesta migração, as verificações são os testes automatizados com provedores roteirizados e clientes SDK simulados. **Nenhuma chamada real à API foi executada.** Os resultados de 06/11/2026 registrados para a integração anterior, com `codex app-server`, não se aplicam ao código atual e não são repetidos aqui.

O teste real é opcional e consome créditos do provedor configurado:

```powershell
python testes/qa_fluxo_real.py --saida-base docs/qa_fluxo_automatico --complemento
```

## Limitações remanescentes

Retomada automática no meio de uma etapa após queda do servidor não foi verificada nesta migração. O histórico parcial é preservado e a recuperação registra interrupção; a próxima pergunta cria outra rodada. Achados inteiramente novos descobertos só durante a revisão não são inseridos como se já tivessem geração inicial; o fluxo aceita correções e evidências adicionais dos achados gerados e deve declarar a limitação.

OCR, adaptadores específicos para DOCX/XLSX e leitura visual de PDF sem a dependência opcional continuam fora desta alteração. A publicação automática usa evidência textual indexada ou evidência visual autorizada; leitura textual sem vínculo verificável ao índice não é promovida automaticamente a evidência canônica.

As seis etapas consomem várias chamadas ao provedor. Custos reais, limites de cobrança, expiração de chave e recuperação após queda durante uma inferência não foram provocados em execução real; os caminhos de falha pertinentes foram simulados.
