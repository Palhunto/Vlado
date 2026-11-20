# Vlado — guia rápido para a redação

Para quem vai usar o Vlado numa reportagem. Duas páginas; o guia técnico é [GUIA_TECNICO_IMPLANTACAO.md](GUIA_TECNICO_IMPLANTACAO.md).

| Campo | Preencher |
| --- | --- |
| Endereço do Vlado da redação | `https://______________________` |
| Administração (quem cria contas e recupera acesso) | nome: ______ contato: ______ |
| Suporte técnico | nome: ______ contato: ______ |
| Conta de API usada (provedor e responsável pelo pagamento) | ______ |

## 1. Entrar

1. Você recebe da administração, por canal privado, um **link de ativação** (vale 72 horas e uma só vez).
2. Abra o link, confira o seu login e defina uma senha de pelo menos 12 caracteres.
3. Depois, entre sempre pelo endereço do Vlado com login e senha, no navegador ou no app Android.
4. A sessão termina depois de 2 horas sem uso ou 12 horas no total. Use **Sair** ao terminar, sobretudo em aparelho compartilhado.
5. Esqueceu a senha ou o link venceu? Peça à administração uma **recuperação de acesso**: ela gera um link novo e encerra as sessões abertas.

## 2. O que cada conta pode fazer

- **Administração**: cria contas e define quais apurações cada convidado vê; cadastra documentos; usa a Mesa inteira (perguntas, conferência de achados, Caderno, exportações); configura o provedor de IA.
- **Convidado**: vê só as apurações liberadas e as próprias conversas; faz perguntas e abre as fontes citadas nessas conversas. Não escreve no Caderno, não exporta e não cadastra documentos.

Quando a administração retira uma apuração ou desativa uma conta, o efeito vale na ação seguinte da pessoa.

## 3. Fluxo de uma apuração

1. **Cadastrar documentos** (administração): envie o lote e confira o **recibo** — cada arquivo com ID, nome e hash. Páginas digitalizadas passam por OCR local; o recibo diz quais páginas têm texto nativo, OCR, nenhum texto ou falha. OCR erra: confira nomes e números no original.
2. **Perguntar**: escreva a pergunta. A IA segue etapas (inventário, plano, busca, geração, revisão, síntese) e cita as fontes. Uma resposta sem suporte deve dizer que falta suporte — isso é resultado, não erro.
3. **Abrir a página citada**: toque na citação para ver a página original. Confira sempre antes de publicar.
4. **Conferir achados** (administração): registre se cada achado se sustenta, depois de abrir o original.
5. **Caderno** (administração): escreva notas, insira o trecho com a fonte, abra o original e volte ao mesmo ponto da nota. Exporte em Markdown, PDF ou DOCX.
6. **Segundo lote**: cadastrar mais documentos não apaga a rodada anterior; a próxima pergunta usa a versão nova se você escolher.

## 4. Salvamento do Caderno

- O indicador mostra: *Alterações não salvas* → *Salvando…* → **Nota salva às HH:MM** (só depois da confirmação do servidor).
- Sem conexão, o texto fica guardado **só nesta aba** e o Vlado tenta de novo. Não feche a aba antes de ver "Nota salva".
- Se outra pessoa (ou outra aba) alterou a mesma nota, o Vlado para e mostra **Conflito**: copie o seu texto e recarregue a nota.

## 5. Cuidados com o material

- Perguntas à IA enviam trechos, imagens de páginas e o histórico da conversa ao provedor contratado. As notas do Caderno não são enviadas. Detalhes: [DADOS_NA_INFERENCIA.md](DADOS_NA_INFERENCIA.md).
- A IA não é revisão humana. Nenhuma afirmação vai para o texto sem conferência no original.
- Não envie documentos de uma reportagem para a apuração de outra.
