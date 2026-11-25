# 04 - Revisão assistida do suporte

Reabrir as fontes autorizadas, não apenas reler o relatório. Verificar cada afirmação A001 etc. contra as evidências e sua localização. Se perder acesso ao original, identificar a limitação e não declarar a checagem concluída.

Referências do SQLite permitem recuperar texto com `banco.py ler` na mesma geração/caso/rodada. A revisão deve conferir também o original congelado quando houver imagem, tabela, valor ou limitação de extração; repetir a busca no índice não constitui essa conferência. Preservar logs e as referências de versão usadas na geração inicial.

Salvar em `06_revisao_assistida.md`: afirmação original; fonte e trecho; existência do localizador; suporte à redação exata; atribuição; comparabilidade de datas/entidades/unidades; cálculo; status **sustentada**, **parcial**, **não sustentada** ou **ilegível**; motivo; correção proposta ou retirada.

Separar três perguntas: a referência existe? O trecho sustenta a frase? A própria declaração foi verificada externamente? No corpus fechado, normalmente só as duas primeiras podem ser avaliadas. Não transformar uma declaração atribuída em comprovação do evento.

Antes de manter uma pendência, procurar o mesmo dado em outras peças do corpus (notas, quadros, anexos) e dizer onde procurou. Classificar cada divergência pela materialidade: muda a conclusão, muda o valor final ou é só grafia. Cada pendência indica a diligência: o destinatário (órgão ou papel), o meio (pedido de acesso à informação, ofício ou entrevista) e o que pedir; o pedido de acesso à informação não exige motivo do requerente (Lei 12.527/2011, art. 10, § 3º).

Numa comparação entre processos, conferir que o documento ou fundamento é de fato o mesmo (versão, data, emissor e trecho) e que os desfechos são comparáveis (mesma questão decidida, mesma fase). Sem essa conferência, a comparação fica como pendência.

Salvar correções em `07_achados_revisados.md`, mantendo IDs e vínculo com a redação inicial. Não sobrescrever `04_evidencias_brutas.md` ou `05_cruzamentos_brutos.md`. Reduzir uma afirmação parcial ao alcance sustentado e voltar a conferir; não promover pendências a fatos.

Relevância e detalhamento não bastam para aprovação factual. Se nenhum achado tiver suporte, registrar insuficiência e produzir somente essa conclusão limitada na síntese. Nunca acionar um fallback que trate relatórios reprovados como fatos. Esta revisão é da IA e permanece sujeita à conferência humana.

## Publicar revisão estruturada

Carregar explicitamente a revisão inicial publicada desta rodada, sem consultar saídas de outra rodada. Preparar novo candidato `achados_revisao_r2.json`, com `revisao: r2_revisao`, vínculo `anterior` contendo revisão/hash do recibo inicial e todo o histórico anterior preservado. Acrescentar eventos de `revisoes_assistidas` para a versão exata de cada redação avaliada, com IDs das fontes efetivamente reabertas, status, motivo, limites e ação. Os valores estruturados são `sustentado`, `parcial`, `nao_sustentado`, `ilegivel` ou `nao_revisado`.

Para corrigir, acrescentar nova versão sequencial em `achados[].versoes`, sem editar a inicial. Acrescentar vínculos e revisão de suporte próprios para essa nova versão; o suporte anterior não se transfere. Evidências anteriores permanecem imutáveis; corrigir uma evidência exige novo E-ID e novos vínculos, com justificativa. Acrescentar procedência `revisao` e os hashes de `06_revisao_assistida.md` e `07_achados_revisados.md` (ou registro de insuficiência).

Se a revisão encontrar novas evidências ou novos achados, acrescentar relatórios brutos em arquivos novos dos tipos `evidencias`/`cruzamentos`, com seus IDs, hashes e procedência de busca adicional. Não editar os brutos publicados. O conjunto de IDs dos relatórios brutos associados deve corresponder aos registros estruturados preservados.

Publicar pelo comando `achados.py registrar` com o novo candidato e conferir o recibo. Um erro de validação/persistência impede declarar esta etapa publicada. A validação técnica de IDs/localizadores/hashes não decide o suporte semântico, que deve ser examinado nesta revisão pela IA.
