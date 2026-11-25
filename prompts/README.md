# Prompts ativos

Prompts online, com cadastro antes da pergunta, consulta documental SQLite/FTS5, leitura dos originais e registro estruturado de achados no fluxo, com banco separado para consulta. Os sete módulos 00 a 06 são a fonte de autoria; [FLUXO_COMPLETO.md](FLUXO_COMPLETO.md) é montado por script e contém exatamente esses módulos. O [manifesto dos prompts](manifesto_prompts.json) registra os hashes. A versão dos prompts é uma só, `VERSAO_PROMPTS` em `scripts/comum.py`, e aparece no cabeçalho do `FLUXO_COMPLETO.md`; os módulos não escrevem número de versão. Rodadas antigas preservam os prompts congelados que efetivamente utilizaram.

O [MESA.md](MESA.md) é a instrução que a Mesa de apuração manda ao modelo. Ele não entra no `FLUXO_COMPLETO.md`, que continua sendo o roteiro do agente de chat. O manifesto o registra na chave `mesa`, com versão e hash, e cada rodada escolhe a instrução pelo manifesto que congelou: sem a chave, a Mesa manda o sistema antigo; com a chave e o hash divergente, recusa a rodada.

O agente deve carregar o fluxo completo como instrução, respeitar os estados e aguardar a pergunta. Ler os módulos não autoriza executar todas as tarefas imediatamente.

| Módulo | Relação com o original |
| --- | --- |
| 00_REGRAS | Estado, fontes, operação online e preservação de registros |
| 01_DESCREVER_CORPUS | Adaptação de compress.md |
| 02_PLANEJAR | Adaptação de plan.md |
| 03_BUSCAR_E_CRUZAR | Adaptação de search.md, com registro explícito do cruzamento |
| 04_REVISAR_SUPORTE | Substitui a triagem temática de evaluate.md por revisão com as passagens |
| 05_SINTETIZAR | Adaptação de synthesize.md |
| 06_INCORPORAR_REVISAO_HUMANA | Registro posterior de conferência humana efetiva |

Após editar um módulo, executar `python scripts/montar_fluxo.py` a partir da raiz e depois `python scripts/montar_fluxo.py --check`. O modelo disponível e o acesso às ferramentas são condições da sessão, não definidos pelo prompt.
