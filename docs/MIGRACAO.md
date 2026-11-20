# Migração para operação online no Codex

> **Nota de 13/11/2026.** Este registro é histórico e não foi reescrito. As referências abaixo ao `codex app-server`, ao login ChatGPT e ao perfil de permissões do Codex descrevem a integração anterior. Na versão atual, a Mesa de apuração envia a inferência à API do provedor configurado (Anthropic ou OpenAI), com a chave apenas nas variáveis de ambiente do servidor. O estado atual está em [INTEGRACAO_API.md](INTEGRACAO_API.md).

Versão 1.0.0, preparada em 02/11/2026. Origem técnica: `NHagar/semantic-search-assistant`, commit `0d5fa4cbe2c98e9c961a16c52a47d7bc0d708f6c`. A migração foi solicitada pelo usuário para testar o procedimento no próprio Codex antes de continuar a avaliação local.

Este registro descreve a migração inicial. Em 04/11/2026, a versão **1.1.0** acrescentou [SQLite/FTS5 por rodada](BANCO_SQLITE.md), derivado das entradas congeladas, com cobertura e logs de consulta. Os prompts foram versionados; não há recuperação por embeddings, reprodução dos experimentos do original ou validação editorial decorrente dessa mudança.

## Arquitetura entregue

```text
Pergunta do usuário + corpus autorizado
                |
      snapshot dos arquivos e prompts
                |
 inventário -> plano -> busca/leitura -> cruzamento
                |
 revisão de afirmações com passagens originais
                |
 briefing com suporte, atribuições e lacunas
                |
       retorno humano quando existir
```

O Codex usa o modelo da sua sessão e as ferramentas disponíveis para leitura, busca e cálculo. O agente salva artefatos no workspace. Os scripts são utilitários de arquivos, sem inferência, rede ou servidor de modelos.

O projeto é genérico e inicia sem caso ativo. Apurações diferentes são cadastradas em `casos/<id>`; o catálogo identifica as opções, mas não autoriza sua leitura conjunta. Cada caso tem estado de piloto próprio e suas rodadas ficam em `execucoes/<caso_id>`. Covaxin foi incluído somente como exemplo opcional inativo. Uma pergunta pode usar um caso escolhido ou um novo corpus conjunto explicitamente autorizado; não há mistura automática.

Não foi migrada a interface Flask/Svelte como aplicação hospedada; o chat e o workspace assumem essa interação. Não foi implementado um serviço RAG vetorial: retirar o ChromaDB altera o mecanismo de recuperação e impede afirmar equivalência com o original. O modelo maior é uma condição pretendida pelo usuário, não evidência de maior precisão antes do piloto.

## Correspondência das funções

| Fonte original | Equivalente ativo | Mudança |
| --- | --- | --- |
| prompts/compress.md; extração/amostragem | 01_DESCREVER_CORPUS.md; extrair_pdf.py | Inventário mensurável e cobertura explícita; sem percentuais estimados sem base |
| prompts/plan.md; generate_search_plans | 02_PLANEJAR.md | A pergunta editorial passa a orientar o plano; quantidade de frentes proporcional |
| prompts/search.md; SearchAgent | 03_BUSCAR_E_CRUZAR.md | Busca textual/contextual/visual disponível no Codex e registro real das consultas |
| VectorDB e ferramenta search_documents | Manifesto, textos paginados e leitura de originais | Não há embeddings; limitar afirmações sobre cobertura da busca |
| prompts/evaluate.md | 04_REVISAR_SUPORTE.md | Revisão por afirmação com reabertura de fonte; continua sendo IA, sem independência garantida |
| prompts/synthesize.md | 05_SINTETIZAR.md | Somente achados sustentados como fatos; alegações e inferências atribuídas; insuficiência explícita |
| ProjectManager; arquivos por corpus/modelo | nova_rodada.py; snapshots e saídas por rodada | Congelar pergunta, configuração, prompts e corpus; não sobrescrever geração inicial |
| Consulta às citações na interface | Referências por ID/página/campo/linhas e links locais | Linhas de cópia textual não são linhas do original; imagens continuam conferíveis |
| Edição humana na interface | 06_INCORPORAR_REVISAO_HUMANA.md | Retorno informado, versão nova e histórico separado |

## O que foi preservado

Os cinco prompts originais, fontes, interface e arquivos de configuração rastreados foram copiados para `referencia_original/codigo`, sem execução. As pastas `newsworthiness-test-cases` não foram duplicadas: são corpora de outras pesquisas, não necessários à operação desta versão. O repositório completo permanece preservado no projeto de origem. Não há dependência de acesso àquela cópia para rodar este pacote.

As peças públicas Covaxin foram copiadas sem alteração para `casos/exemplo_covaxin`. Seus derivados estão identificados e não são fontes independentes. Os nove arquivos de imagem fornecidos e seus PDFs selecionáveis anteriores foram incluídos como apoio dentro desse exemplo, fora da seleção automática da rodada. O projeto não os usa até o operador selecionar explicitamente esse caso.

Relatórios de avaliação da CGU/CPI, gabaritos e conclusões da preparação não foram copiados. As fichas de revisão incluídas são vazias. Nenhuma pergunta principal ou resposta esperada foi inserida nos prompts.

## Limites e condições

- A inferência é online; não há garantia de privacidade local. Manter documentos públicos ou sintéticos identificados.
- O modelo e as ferramentas são escolhidos/disponibilizados na sessão, não pelo pacote. Registrar o que foi observado, sem inventar nome, versão ou parâmetros.
- Um AGENTS.md orienta comportamento; não configura isolamento de rede ou filesystem. Consultar somente entradas autorizadas é regra operacional, não barreira técnica comprovada.
- Abrir a pasta como projeto separado estabelece o contexto pretendido. Foi preparado um repositório Git independente para que a raiz de trabalho não seja a pesquisa acadêmica pai; configurações globais da conta e instruções superiores continuam aplicáveis.
- O snapshot preserva arquivos; não preserva pesos do modelo, histórico interno do serviço ou configurações não observáveis.
- Não são criados agentes paralelos automaticamente. As etapas podem ocorrer em uma única conversa e não constituem revisão independente.
- Manter comparação futura entre local e online com mesmos originais, perguntas e critérios; registrar diferenças de mecanismo de busca, visão, ferramentas e derivados.
- Não foi realizado piloto de apuração durante a montagem. Verificação de scripts não demonstra qualidade da recuperação, exatidão de respostas ou ganho editorial.

## Fontes de preparação

- [Repositório original no commit fixado](https://github.com/NHagar/semantic-search-assistant/tree/0d5fa4cbe2c98e9c961a16c52a47d7bc0d708f6c): estrutura e código de referência.
- [Artigo-base, arXiv v1](https://arxiv.org/html/2509.25494v1): contexto técnico; experimentos publicados não reproduzidos por este pacote.
- [OpenAI Docs: instruções com AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md): descoberta de instruções de projeto, consultada em 02/11/2026.

As mudanças de prompts são propostas de método ainda sujeitas a piloto, não melhorias demonstradas por resultado experimental.
