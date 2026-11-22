"""Stable error codes for the interface to translate. The Portuguese messages stay as they are.

Each HTTP error answer carries `codigo` (and `parametros` when the message has numbers the
interface needs). Codes are part of the contract with the interface: rename only together with it.
No model or network calls.
"""
from __future__ import annotations

import json
import re

# Order matters: the first pattern that matches the message wins.
PADROES: tuple[tuple[str, str], ...] = (
    ('endereco_nao_autorizado', r'^Endereço não autorizado'),
    ('sessao_expirada', r'^Sessão expirada ou convite revogado'),
    ('acesso_indisponivel', r'^Registro de acesso (indisponível|ilegível)'),
    ('origem_nao_autorizada', r'^Origem ou sessão não autorizada'),
    ('operacao_inexistente', r'^Operação não encontrada'),
    ('pagina_inexistente', r'^Página não encontrada'),
    ('requisicao_invalida', r'^Requisição (vazia ou muito grande|deve ser um objeto JSON)'),
    ('operacao_proibida', r'^Operação não permitida'),
    ('servico_nao_encerravel', r'^O serviço hospedado não pode ser encerrado'),
    ('caso_nao_liberado', r'^Apuração não liberada para (este convite|esta conta)'),
    ('campos_nao_permitidos', r'^Convidados enviam somente'),
    ('convite_invalido', r'^Convite inválido'),
    ('cota_diaria_esgotada', r'^Limite diário de (?P<cota>\d+) pergunta'),
    ('limite_tokens_dia', r'^Limite diário de (tokens|uso) da instalação'),
    ('limite_tokens_consulta', r'^(Limite de tokens por consulta atingido|O limite de tokens por consulta)'),
    ('pergunta_em_andamento', r'^Já há uma pergunta em andamento'),
    ('conversa_indisponivel', r'^Conversa indisponível para este acesso'),
    ('conversa_invalida', r'^Conversa inválida'),
    ('conversa_em_execucao', r'^(Esta conversa está em execução|Esta conversa já tem uma execução ativa|'
                             r'A conversa de origem está em execução)'),
    ('execucao_em_andamento', r'^Há uma execução em andamento'),
    ('conversa_concluida', r'^Esta pergunta já foi concluída e publicada'),
    ('conversa_nao_retomavel', r'^(Esta conversa não tem uma execução interrompida|A pergunta não chegou a ser congelada|'
                               r'A etapa \w+ publicou a revisão)'),
    ('pergunta_invalida', r'^Informe uma pergunta'),
    ('chave_ausente', r'^Chave de API ausente'),
    ('caso_nao_selecionado', r'^Selecione um caso'),
    ('cursor_invalido', r'^Cursor/espera inválidos'),
    ('cursor_posterior', r'^Cursor posterior ao histórico'),
    ('caso_invalido', r'^Identificador de caso inv[aá]lido'),
    ('apuracao_inexistente', r'^Apuração não encontrada'),
    ('chave_formato_invalido', r'^Chave de API em formato inválido'),
    ('revisao_ia_mudou', r'^A revisão da IA mudou'),
    ('marcacao_alterada', r'^A marcação foi alterada em outra janela'),
    ('achado_fora_da_revisao', r'^Achado ou versão fora desta revisão'),
    ('achado_sem_fontes', r'^Este achado não tem fontes vinculadas'),
    ('id_invalido', r'^ID de (evidência|achado) inválido'),
    ('nome_confirmacao_divergente', r'^Digite o nome do item'),
    ('alcance_alterado', r'^O conteúdo do item mudou desde a conferência'),
    ('confirmacao_ausente', r'^Confirmação ausente'),
    ('item_fora_da_lixeira', r'^Só é possível apagar definitivamente um item que está na lixeira'),
    ('lixeira_id_invalido', r'^Identificador da lixeira inválido'),
    ('apagamento_incompleto', r'^Não foi possível apagar tudo'),
    ('apagamento_pendente', r'^Um apagamento definitivo desta apuração ficou pela metade'),
    ('conferencia_sem_original', r'^Para marcar “Conferida no original”'),
    ('falha_leitura', r'^Falha ao ler arquivos do servidor'),
    # Evidence boards (hipoteses, linha_tempo, comparador, mapa_relacoes via rotas_evidencia).
    ('quadro_sem_caso', r'^Selecione uma apuração para os quadros'),
    ('quadro_campos_invalidos', r'^Campos inválidos no (registro|pedido do quadro)'),
    ('registro_inexistente', r'^Registro não encontrado nesta apuração'),
    ('registro_invalido', r'^(Identidade do registro inválida|Registro inválido|Identidade de salvamento inválida)'),
    ('registro_existente', r'^Registro já existe'),
    ('registro_mudou', r'^O registro mudou'),
    ('tentativa_reutilizada', r'^Esta tentativa já foi usada com outro conteúdo'),
    ('historico_divergente', r'^Histórico do registro divergente'),
    ('quadro_em_uso', r'^O quadro de .+ está sendo salvo'),
    ('retirada_sem_motivo', r'^Para retirar o registro, informe o motivo'),
    ('evidencia_outro_caso', r'^Evidência de outra apuração'),
    ('evidencia_ausente', r'^Fonte da evidência ausente nesta apuração'),
    ('evidencia_original_mudou', r'^O original da evidência mudou desde o vínculo'),
    ('evidencia_sem_trecho', r'^Evidência sem trecho textual'),
    ('referencia_evidencia_invalida', r'^Referência (de evidência inválida|a evidência dos achados inválida|'
                                      r'a fonte do caderno inválida|de evidência sem apuração válida)'),
    ('tipos_data_invalidos', r'^Filtro de tipos de data inválido'),
    ('filtro_retirados_invalido', r'^Indique com verdadeiro ou falso se inclui registros retirados'),
    ('rodada_comparacao_ausente', r'^Selecione uma rodada da apuração para comparar'),
    ('documentos_comparacao_invalidos', r'^(Escolha dois documentos da rodada|Escolha dois documentos diferentes)'),
    ('documento_fora_da_rodada', r'^Documento não pertence a esta rodada'),
    ('contexto_comparacao_invalido', r'^Contexto deve ter de 0 a 10 linhas'),
    ('achados_mudaram', r'^O conjunto de achados referenciado mudou de identidade'),
    ('evidencia_fora_da_revisao', r'^Evidência não pertence a esta revisão'),
    ('documento_sem_original', r'^Documento sem original congelado nesta rodada'),
    ('documento_sem_texto', r'^(?P<documento>[A-Za-z0-9][A-Za-z0-9_-]{0,63}) não tem texto utilizável nesta rodada'),
    # Investigation tables (tabelas_apuracao via rotas_tabelas): cells, corrections and calculations.
    ('tabela_coluna_invalida', r'^Coluna inválida'),
    ('tabela_colunas_registradas', r'^As colunas já registradas não mudam'),
    ('tabela_linha_invalida', r'^Linha inválida'),
    ('tabela_celula_invalida', r'^Célula inválida'),
    ('tabela_celula_inexistente', r'^Célula inexistente nesta tabela'),
    ('tabela_celula_registrada', r'^Célula já registrada \((?P<celula>[^)]{1,60})\)'),
    ('tabela_valor_invalido', r'^Valor inválido em (?P<celula>\S{1,60}):'),
    ('tabela_fonte_invalida', r'^Fonte da célula'),
    ('tabela_fonte_em_uso', r'^Evidência ainda é fonte de célula'),
    ('tabela_fonte_indisponivel', r'^Fonte indicada indisponível \(evidência (?P<evidencia>\d+)\)'),
    ('tabela_grande_demais', r'^Tabela grande demais'),
    ('tabela_versao_inexistente', r'^Versão da tabela inexistente'),
    ('correcao_sem_justificativa', r'^Para corrigir uma célula, informe a justificativa \((?P<celula>[^)]{1,60})\)'),
    ('correcao_invalida', r'^Correção inválida'),
    ('calculo_unidades_incompativeis', r'^Cálculo recusado: unidades ou moedas diferentes'),
    ('calculo_celula_sem_valor', r'^Cálculo recusado: célula sem valor'),
    ('calculo_recusado', r'^Cálculo recusado'),
    ('calculo_invalido', r'^Cálculo inválido'),
    ('calculo_inexistente', r'^Cálculo não encontrado nesta tabela'),
    ('exportacao_formato_invalido', r'^Formato de exportação inválido'),
    # Claim-by-claim review of the story text (conferencia_redacao via rotas_redacao).
    ('revisao_humana_sem_conta', r'^A revisão humana exige uma conta autenticada'),
    ('afirmacao_inexistente', r'^Afirmação não encontrada nesta versão do texto'),
    ('afirmacao_sem_suporte_vinculado', r'^Esta afirmação não tem evidência de suporte vinculada'),
    ('redacao_sem_alteracao', r'^Nada mudou (no texto|nos vínculos desta afirmação|na revisão desta afirmação)'),
    ('redacao_texto_invalido', r'^Texto da reportagem: informe texto válido'),
    ('redacao_afirmacoes_demais', r'^O texto tem mais de (?P<limite>\d+) afirmações'),
    ('revisao_humana_invalida', r'^(Revisão humana inválida|Escolha uma decisão de revisão válida)'),
    ('vinculos_afirmacao_invalidos', r'^Vínculos da afirmação inválidos'),
    # Interviews and information requests (entrevistas, diligencias via rotas_redacao).
    ('lacuna_origem_mudou', r'^A lacuna de origem mudou ou não existe mais'),
    ('pergunta_origem_invalida', r'^Origem da pergunta inválida'),
    ('contato_tipo_invalido', r'^Escolha o tipo de contato'),
    ('resposta_sem_fonte', r'^Resposta respondida ou parcial precisa da fonte'),
    ('resposta_situacao_invalida', r'^Situação da resposta inválida'),
    ('resposta_fonte_invalida', r'^(Campos inválidos na fonte da resposta|A fonte da resposta deve ser um registro do caderno)'),
    ('pergunta_sem_alteracao', r'^Nada mudou na pergunta'),
    ('pedido_destinatario_misto', r'^Para o pedido, selecione perguntas de pedido de informação'),
    ('exportacao_selecao_invalida', r'^Selecione de 1 a (?P<limite>\d+) perguntas para exportar'),
    # Web sources per case (scripts/fontes_web.py).
    ('fontes_web_caso_documental', r'^Este caso foi criado como apuração somente documental'),
    ('fontes_web_modo_na_criacao', r'^O modo de fontes \(.*\) só é escolhido na criação'),
    ('fontes_web_modo_mudou', r'^O modo de fontes do caso mudou durante a captura'),
    ('fontes_web_dominio_invalido', r'^(Informe o domínio permitido|Domínio permitido)'),
    ('fontes_web_dominio_recusado', r'^Domínio recusado: '),
    ('fontes_web_endereco_interno', r'^O site aponta para um endereço de rede interno'),
    ('fontes_web_https', r'^Endereço deve começar com https://'),
    ('fontes_web_endereco_invalido', r'^(Informe o endereço completo da página|Endereço com |Porta inválida no endereço'
                                     r'|Endereço de rede inválido)'),
    ('fontes_web_resposta_http', r'^O site respondeu (?P<status>\d{3})'),
    ('fontes_web_tipo_recusado', r'^Tipo de conteúdo não aceito'),
    ('fontes_web_grande_demais', r'^Página excede 20 MB'),
    ('fontes_web_redirecionamentos', r'^Redirecionamentos demais'),
    ('fontes_web_tempo_esgotado', r'^Tempo limite da captura esgotado'),
    ('fontes_web_inacessivel', r'^Não foi possível (acessar o endereço|resolver o nome do site)'),
    ('fontes_web_conteudo_comprimido', r'^Conteúdo comprimido não aceito'),
    ('fontes_web_limite', r'^Limite de (?P<limite>\d+) capturas web por caso'),
    ('fontes_web_captura_inexistente', r'^Captura web inexistente'),
    ('fontes_web_campos_invalidos', r'^Campos não permitidos na operação de fontes web'),
    # Extraction queue (scripts/fila_extracao.py): W11 'limite' block; onde = 'desta apuração' or 'na Mesa'.
    ('fila_limite_envios', r'^Limite de envios em processamento\. Há (?P<arquivos>\d+) arquivos? '
                           r'(?P<onde>desta apuração|na Mesa) sendo lidos?\.'),
    # Month's quota in reais and execution ceilings (scripts/custo.py, codex_apuracao): W11 'limite' block.
    ('cota_mensal_conta', r'^Sua cota do mês acabou\. Você usou R\$ (?P<usado>[\d.]+,\d{2}) de R\$ (?P<teto>[\d.]+,\d{2})\.'),
    ('cota_mensal_organizacao', r'^A cota do mês da instalação acabou\.'),
    ('gasto_ilegivel', r'^O registro do gasto do mês está ilegível'),
    ('gasto_nao_registrado', r'^O gasto do mês não pode ser registrado agora'),
    ('modelo_nao_permitido', r'^O modelo .+ não está entre os permitidos nesta instalação'),
    ('execucoes_simultaneas_conta', r'^Já há (?P<limite>\d+) perguntas? em andamento nesta conta'),
    ('execucoes_simultaneas_mesa', r'^A Mesa já está com (?P<limite>\d+) perguntas em andamento'),
    # Drafts (rascunhos): one per account, case and screen, with a growing version.
    ('rascunho_conflito', r'^O rascunho mudou em outra aba'),
    ('rascunho_sem_caso', r'^Selecione uma apuração para o rascunho'),
    ('rascunho_tela_invalida', r'^Tela de rascunho inválida'),
    ('rascunho_conta_invalida', r'^Conta do rascunho inválida'),
    ('rascunho_com_chave', r'^Rascunhos não guardam chaves de API'),
    ('rascunho_grande_demais', r'^Rascunho grande demais \(limite de (?P<limite>\d+) KB\)'),
    ('rascunhos_caso_cheio', r'^Rascunhos desta apuração ocupam o limite do caso \(limite de (?P<limite>\d+) KB\)'),
    ('rascunhos_caso_limite', r'^Rascunhos desta apuração chegaram ao limite \((?P<limite>\d+) abertos\)'),
    ('rascunhos_conta_limite', r'^Rascunhos desta conta chegaram ao limite \((?P<limite>\d+) abertos\)'),
    ('rascunho_ilegivel', r'^Rascunho ilegível no servidor'),
    ('rascunho_invalido', r'^Rascunho inválido'),
    ('rascunho_so_pergunta', r'^Convidados guardam somente o rascunho da pergunta'),
    # Resume summary of the active case (continuidade.resumo_caso).
    ('resumo_campos_invalidos', r'^Campos inválidos no resumo de retomada'),
    ('resumo_sem_caso', r'^Selecione uma apuração para o resumo de retomada'),
)
_COMPILADOS = tuple((codigo, re.compile(padrao)) for codigo, padrao in PADROES)


def codigo_de(mensagem: str, exc: BaseException | None = None) -> tuple[str, dict]:
    """(codigo, parametros) for an error message; ErroIA falls back to 'ia_<its code>'."""
    for codigo, padrao in _COMPILADOS:
        achado = padrao.search(mensagem or '')
        if achado:
            parametros = {k: int(v) if v.isdigit() else v for k, v in achado.groupdict().items() if v is not None}
            return codigo, parametros
    if isinstance(exc, json.JSONDecodeError):
        return 'json_invalido', {}
    codigo_ia = getattr(exc, 'codigo', None)
    if isinstance(codigo_ia, str) and re.fullmatch(r'[a-z_]{1,40}', codigo_ia):
        return 'ia_' + codigo_ia, {}
    return 'erro', {}
