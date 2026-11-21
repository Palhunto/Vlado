# Inferência pela API do provedor na Mesa de apuração

Atualizado em 20/11/2026. Perguntas e complementos enviados pela Mesa usam a API do provedor configurado: Anthropic ou OpenAI. A integração anterior, com `codex app-server` e login ChatGPT, foi removida. As seis etapas obrigatórias e a publicação verificada dos achados seguem o [fluxo automático](FLUXO_AUTOMATICO_CODEX.md). O histórico da adaptação está em [MIGRACAO.md](MIGRACAO.md).

## Estado da verificação

- Os testes automatizados (`testes/test_inferencia_api.py`, `testes/test_provedores_api.py` e a suíte `unittest`) usam provedores roteirizados e clientes SDK simulados.
- **Chamadas reais registradas:** três ensaios concluídos e uma tentativa interrompida, também cobrada, com o provedor OpenAI (13/11 e 15/11/2026), descritos em [VERIFICACAO.md](VERIFICACAO.md) com tokens e custo estimado (tempo em dois deles).
- **Não verificado em execução real:** para o provedor Anthropic, que é o padrão, não há execução registrada com chave real; também não foram verificados limites de cobrança do provedor nem a recuperação após queda durante uma inferência.
- `testes/qa_fluxo_real.py` é o teste real opcional. Consome créditos do provedor configurado:

```powershell
python testes/qa_fluxo_real.py --saida-base docs/qa_fluxo_automatico --complemento
```

- Os scripts de navegador de `testes/` (por exemplo `testes/qa_codex.py`) foram atualizados, mas não foram executados.

## Módulos

| Arquivo | Função |
| --- | --- |
| `scripts/inferencia_api.py` | `ServidorAPI`: adaptador com o mesmo contrato de chamada, envio e notificações que a classe `Conversas` de `codex_apuracao.py` já usava. Lê a configuração com `ler_inferencia`; `seguro()` redige chaves; grava o histórico em `conversas/<id>/api_historico.json`, sem imagens. |
| `scripts/provedor_anthropic.py` | Anthropic Messages API, com streaming, `tool_use`/`tool_result` e cache de prompt pelo `cache_control` de nível superior. |
| `scripts/provedor_openai.py` | OpenAI Responses API, sem estado (`store=False`), com streaming, `function_call`/`function_call_output` e itens de raciocínio criptografados reenviados. |
| `scripts/codex_apuracao.py` | Conversas, eventos e a ferramenta `consultar_acervo`, delimitada ao corpus da rodada. |
| `scripts/fluxo_codex.py` | Controle das seis etapas, validação e publicação dos registros. |

Limites do adaptador: no máximo 60 passos do provedor por etapa; espera de até 300 s por chamada de ferramenta; a interrupção fecha as chamadas de ferramenta pendentes.

**Nomes mantidos por compatibilidade com rodadas existentes:** operações HTTP com prefixo `codex-` (`codex-status`, `codex-perguntar`, …), módulos `codex_apuracao.py` e `fluxo_codex.py`, e artefatos `codex_execucao.json`, `codex_fluxo_estado.json` e `codex_mensagem_*.md`. Esses nomes não indicam uso do Codex.

## Configuração

Em `configuracao.json`:

| Chave | Valor |
| --- | --- |
| `"inferência"` | `"api_do_provedor"` |
| `"provedor"` | `"anthropic"` (padrão do arquivo) ou `"openai"` |
| `"modelo_preferido"` | `null`, para o padrão do provedor (Anthropic: `claude-sonnet-5-5`; OpenAI: `gpt-6.1-sol`), ou o nome explícito de um modelo |
| `"max_tokens_saida"` | `16000` (inteiro positivo) |
| `"versao"` | `"2.2.0"` (versão única da release; igual à do instalador e à da imagem Docker) |

Valores inválidos falham com erro claro antes de qualquer chamada ao modelo.

- A conversa mantém o modelo registrado; os complementos usam esse mesmo modelo.
- Trocar `"provedor"` exige uma conversa nova. Retomar uma conversa criada com outro provedor falha com mensagem clara.
- A configuração de cada rodada fica congelada no snapshot.

## Chaves de API

- **Pela Mesa:** em **Perguntar à IA › Conexão e opções**, escolha o provedor e o modelo (opcional), cole a chave e salve. A escolha de provedor/modelo vai para `ajustes/inferencia.json` (sobrepõe `configuracao.json` sem alterá-lo); a chave vai para `segredos/chaves.json`, ou para o caminho em `VLADO_SEGREDOS`. As duas pastas ficam fora do git. O navegador só recebe se há chave, sua origem e os 4 últimos caracteres. No modo piloto, só administradores alteram provedor e chave.
- **Pelo ambiente:** `ANTHROPIC_API_KEY` ou `OPENAI_API_KEY` no processo do servidor têm prioridade sobre a chave salva.
- Nunca vão para configuração versionada, navegador, eventos, logs, histórico ou git; `seguro()` apaga das mensagens os valores conhecidos. Backups (`scripts/backup.py`) só incluem chaves com `--incluir-segredos`.
- Para usar a variável de ambiente, defina-a antes de abrir a Mesa. Com **Abrir mesa.vbs**, ela precisa estar disponível ao Windows (variável de usuário ou de sistema); com **Iniciar pesquisa.cmd**, basta estar definida no terminal que o inicia. Reinicie o servidor se ele já estava aberto.
- Sem a chave, a pergunta é recusada com "Chave de API ausente…" e a Mesa mostra **Chave de API ausente no servidor**.
- Com a chave presente, a área de conversa mostra **Conectado à API · \<Provedor\> · \<modelo\>**.
- `scripts/ambiente.py` informa apenas se cada chave está definida (verdadeiro ou falso) e se os SDKs estão disponíveis. O estado "pronto" exige os dois SDKs.
- A cobrança é feita pelo provedor, por uso. Não há assinatura ChatGPT nem login.

## Uso

1. Defina a chave no ambiente e escolha `"provedor"` e `"modelo_preferido"` em `configuracao.json`.
2. Abra a Mesa com **Abrir mesa.vbs** ou **Iniciar pesquisa.cmd**.
3. Em **Conversa com os documentos**, confira a conexão em **Verificar conexão**, dentro de **Conexão e opções**.
4. Escolha a apuração em **Escolher apuração e conversa** (ou **Nova conversa**), confira o inventário e envie a pergunta. O cadastro dos documentos deve ocorrer antes; ver [cadastro](CADASTRO_DOCUMENTOS.md).
5. Acompanhe as etapas, mensagens, ferramentas e o evento **uso** na lista de atividades.
6. Envie complementos na mesma conversa. Cada pergunta cria uma rodada nova.
7. **Cancelar execução** interrompe a etapa em curso e fecha as chamadas de ferramenta pendentes. **Encerrar serviço** encerra o servidor e interrompe as execuções ativas.

## Uso de tokens e registros

- Cada chamada ao provedor grava `saidas/api_uso_NNNN.json` na rodada.
- A lista de atividades recebe um evento `uso`.
- `saidas/codex_execucao.json` inclui `uso_tokens` e `modelos_informados` (nomes informados pelo provedor).
- `conversas/<id>/conversa.json`: vínculo ao caso, rodadas, modelo e estado.
- `conversas/<id>/eventos.jsonl`: histórico de perguntas, atualizações e fontes, sem tokens.
- `conversas/<id>/api_historico.json`: histórico enviado ao provedor, sem imagens.
- `saidas/codex_ferramenta_*.json`, `saidas/codex_mensagem_*.md`, `saidas/codex_<etapa>_<id>.md` e `saidas/codex_fluxo_estado.json`: mesmos registros de antes.

## Dependências

`requirements.txt` fixa `anthropic==2.8.0` e `openai==3.50.0`, além de `pypdf` para o cadastro. `scripts/preparar_notebook.py` orienta a definir a chave no ambiente antes de abrir a Mesa.

## Ferramentas e segurança

- O modelo alcança os documentos somente pela ferramenta `consultar_acervo`. Não há ferramentas de shell, de arquivos ou de rede.
- Consultas aceitam apenas IDs documentais do manifesto congelado; caminhos e SQL fornecidos pelo modelo são recusados.
- O conteúdo dos documentos é dado não confiável. Regras técnicas e prompts reduzem, mas não garantem, proteção contra injeção de instruções pelos documentos.
- O processamento é online, no provedor. Não foi configurada nenhuma garantia adicional de retenção ou tratamento de dados.
- O token de sessão do servidor local protege as requisições da Mesa; não é credencial de provedor.

## Removido nesta migração

- `scripts/codex_rpc.py` e `testes/qa_mcp_codex.py`.
- Login ChatGPT: botões de login, rota `/codex-login/browser`, operações `codex-login` e `codex-cancelar-login`.
- Verificação do perfil de permissões do Codex.
- Pedidos de aprovação: a tela e a operação `codex-aprovacao`. Solicitações desconhecidas do servidor são recusadas com um evento `aviso`.

## Recuperação do acompanhamento e rascunhos

Se a leitura dos eventos falhar, **Reconectar acompanhamento** volta a observar a mesma conversa a partir do cursor já recebido, sem reenviar a pergunta, criar rodada ou reiniciar a execução. **Cancelar execução** permanece disponível. Durante a reconexão, o envio de perguntas fica bloqueado até a interface recuperar o estado do backend. Isso recupera o acompanhamento HTTP; não retoma automaticamente uma etapa interrompida por queda do backend.

Um envio em andamento ou já aceito não é reabilitado pelo próximo lote de eventos; falhas de resposta permitem tentar novamente.

O campo de pergunta mantém rascunhos separados para cada par apuração/conversa, incluindo uma entrada própria para **Nova conversa** em cada apuração. O destino aparece junto ao campo. Trocar de área ou contexto não descarta esses textos; um envio confirmado limpa apenas o rascunho enviado, e uma falha de envio preserva o texto. Prévia de observações, caderno ou diligências recupera o rascunho do destino antes de sugerir uma pergunta.

Os rascunhos ficam somente na memória da página, sem escrita no corpus, nos registros ou no armazenamento persistente do navegador. Ao fechar ou recarregar com texto pendente, a interface solicita a confirmação nativa do navegador. Confirmar a saída descarta os rascunhos; eles não são recuperados após fechar a página ou cair o navegador. Esta proteção depende das condições do navegador para `beforeunload`.

## Corpus e registros de consulta

O backend entrega ao modelo apenas o corpus congelado da rodada. A ferramenta `consultar_acervo` oferece cobertura, busca, contexto, leitura textual delimitada, imagem ou página de PDF e salvamento de etapas. Conteúdo de fontes chega como resultado de ferramenta, tratado como dado não confiável.

Um complemento precisa buscar e ler a passagem na sua própria rodada antes de citá-la. Os logs SQL originais mantêm a identidade nativa; os registros da ferramenta preservam a referência da rodada e a identidade nativa (`referencia_sqlite`). Complementos retêm o contexto anterior da conversa; isso é registrado como limitação experimental.

Uma queda do servidor preserva os eventos e marca a execução como interrompida ao recuperar. Retomar usa o histórico salvo da conversa vinculada; não usa conversas de outros casos. Se o provedor configurado mudou, a retomada falha com mensagem clara. O uso simultâneo de dois servidores sobre a mesma pasta não é suportado para editar a mesma conversa; use uma única instância.

## Limites e pendências

- Retomada após queda do servidor no meio de uma etapa: não verificada nesta migração.
- Custos, limites de cobrança, chave inválida ou expirada e erros reais do provedor: não verificados em execução real.
- O OCR é local (cadastro), não passa pela API; a leitura visual de PDF depende de dependência opcional.
- DOCX e XLSX continuam sem adaptador próprio neste fluxo.
- Os resultados registrados em 06/11/2026 para a integração anterior, com `codex app-server`, não se aplicam ao código atual.
- Não há tela de aprovação de permissões nem ampliação de acesso pela interface.

Comandos de verificação de manutenção:

```powershell
python scripts/montar_fluxo.py --check
python scripts/verificar_projeto.py
python -m unittest discover -s testes -v
```
