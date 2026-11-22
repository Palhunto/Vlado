"""Rodada sintética completa para a regressão visual, gravada numa pasta de dados TEMPORÁRIA.

Roda no Python do projeto, chamada por `regressao_visual_semear.py`. Nenhuma chamada de modelo ou de rede:
pergunta, índice, achados em duas revisões (a segunda com revisão assistida e briefing), hipóteses, mapa de
relações, linha do tempo, diligências e uma conversa, tudo escrito pelas mesmas funções que a Mesa usa para
gravar. As evidências citam linhas literais do derivado de texto do contrato sintético (`dados_sinteticos.py`).

Os identificadores vêm de `requisicao_id` fixos (derivados do rótulo) e a conversa usa datas fixas; as datas
que o servidor grava com a hora real são mascaradas na captura (`MASCARAS` em `regressao_visual.py`).
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

CASO = 'vila_serena_sintetico'
RODADA = 'R001'
CONVERSA = 'c' * 32
PERGUNTA = 'Qual é o valor global do contrato 041/2025 e o que a medição nº 3 informa sobre os pagamentos?'
AUTOR = 'Repórter sintético'


def rid(rotulo):
    """requisicao_id fixo por rótulo: os ids gravados (H..., P..., G...) saem iguais em toda semeadura."""
    return hashlib.sha256(('vlado-regressao-visual:' + rotulo).encode()).hexdigest()[:32]


def linhas_do_derivado(root, documento):
    """{numero: texto} das linhas [Lnnnn] do derivado de texto do documento, lidas do arquivo gravado."""
    derivado = next(d for d in documento['derivados'] if d['tipo'] == 'texto_extraido_pdf')
    linhas = {}
    for linha in (root / derivado['arquivo']).read_text(encoding='utf-8').splitlines():
        if linha.startswith('[L') and '] ' in linha:
            linhas[int(linha[2:linha.index(']')])] = linha[linha.index('] ') + 2:]
    return linhas


def semear_rodada(pasta):
    """Cria a rodada R001 de vila_serena_sintetico em `pasta`. Devolve um resumo do que gravou."""
    from comum import sha256
    from indice_achados import construir
    from indice_sqlite import cobertura, pesquisar
    from nova_rodada import criar_rodada
    from registros_achados import publicar
    from selecionar_caso import selecionar
    import diligencias
    import hipoteses
    import linha_tempo
    import mapa_relacoes

    root = Path(pasta)
    selecionar(root, CASO)
    try:
        run = Path(criar_rodada(root, RODADA, PERGUNTA, indice=True))
    finally:
        selecionar(root, None)
    manifesto = json.loads((run / f'entradas/casos/{CASO}/manifesto.json').read_text(encoding='utf-8'))
    d1 = next(d for d in manifesto['documentos'] if d['id'] == 'D001')
    d2 = next(d for d in manifesto['documentos'] if d['id'] == 'D002')
    texto = linhas_do_derivado(root, d1)
    hit = pesquisar(root, CASO, RODADA, 'valor global')['resultados'][0]
    identidade = cobertura(root, CASO, RODADA)
    indice = {'indice_id': identidade['indice_id'], 'banco_sha256': identidade['banco_sha256'], 'geracao': 'v1',
              'referencia': hit['referencia']}

    def indexada(eid, linha):
        return {'id': eid, 'documento_id': 'D001', 'modo': 'indexada', 'original': 'entradas/' + d1['arquivo'],
                'original_sha256': d1['sha256'], 'fonte_textual': hit['fonte_textual'], 'fonte_sha256': hit['fonte_sha256'],
                'indice': indice,
                'localizador': {'tipo': 'linhas', 'pagina_pdf': 1, 'linha_inicio': linha, 'linha_fim': linha, 'descricao': ''},
                'trecho': texto[linha], 'atribuicao': 'Contrato 041/2025 (sintético)',
                'contexto': 'Cláusula do contrato sintético.', 'limitacoes': 'Documento fictício, sem verificação externa.'}

    e5 = {'id': 'E005', 'documento_id': 'D002', 'modo': 'visual', 'original': 'entradas/' + d2['arquivo'],
          'original_sha256': d2['sha256'], 'fonte_textual': None, 'fonte_sha256': None, 'indice': None,
          'localizador': {'tipo': 'pagina', 'pagina_pdf': 1, 'linha_inicio': None, 'linha_fim': None,
                          'descricao': 'Boletim de medição nº 3, página digitalizada'},
          'trecho': '', 'atribuicao': 'Boletim de medição nº 3 (sintético)',
          'contexto': 'Página digitalizada, sem texto extraído.', 'limitacoes': 'Leitura visual; sem OCR.'}
    achado = lambda aid, sub, redacao, natureza, limites: {
        'id': aid, 'subquestao': sub, 'versoes': [{'versao': 1, 'redacao': redacao, 'natureza': natureza, 'limitacoes': limites}]}
    data = {
        'esquema': 1, 'caso_id': CASO, 'rodada': RODADA, 'snapshot_sha256': sha256(run / 'snapshot.json'),
        'revisao': 'r1', 'anterior': None,
        'achados': [
            achado('A001', 'Qual o valor global do contrato?', 'O contrato 041/2025 declara valor global de R$ 8.750.000,00.',
                   'declaracao_documental', 'Redação inicial sujeita à revisão.'),
            achado('A002', 'Qual o prazo e a data de assinatura?',
                   'O contrato declara prazo de 240 dias e assinatura em 3 de março de 2025.',
                   'declaracao_documental', 'Declaração documental, sem verificação externa.'),
            achado('A003', 'Os pagamentos acompanharam as medições?',
                   'Não foi estabelecida a relação entre pagamentos e medições.', 'pendencia',
                   'A medição nº 3 está digitalizada e não foi lida por texto.')],
        'evidencias': [indexada('E001', 6), indexada('E002', 7), indexada('E003', 8), indexada('E004', 9), e5],
        'vinculos': [{'achado_id': a, 'versao': 1, 'evidencia_id': e, 'papel': papel, 'justificativa': 'Relação sintética atribuída.'}
                     for a, e, papel in (('A001', 'E001', 'suporte'), ('A002', 'E002', 'suporte'), ('A002', 'E003', 'suporte'),
                                         ('A003', 'E005', 'contexto'), ('A003', 'E004', 'contexto'))],
        'revisoes_assistidas': [], 'destinos': [], 'conferencias_humanas': [],
        'verificacao_externa': {'estado': 'nao_realizada', 'relato': None, 'limitacao': 'Corpus fechado; sem verificação externa.'},
        'procedencia': [{'etapa': 'busca', 'artefatos': [], 'ferramentas': ['semeadura sintética'],
                         'modelo_informado_ou_observado': None}],
        'artefatos': []}

    def relatorio(dados, nome, tipo, conteudo, evento):
        caminho = run / nome
        caminho.write_text(conteudo, encoding='utf-8')
        dados['artefatos'].append({'arquivo': nome, 'sha256': sha256(caminho), 'tipo': tipo})
        dados['procedencia'][evento]['artefatos'].append(nome)

    relatorio(data, 'saidas/04_evidencias_brutas.md', 'evidencias', 'E001 E002 E003 E004 E005 · fontes sintéticas.', 0)
    relatorio(data, 'saidas/05_cruzamentos_brutos.md', 'cruzamentos', 'A001@v1 A002@v1 A003@v1 · redações sintéticas.', 0)
    primeira = publicar(root, CASO, RODADA, data)

    revisada = copy.deepcopy(data)
    revisada.update(revisao='r2', anterior={'revisao': 'r1', 'registros_sha256': primeira['manifesto']['registros_sha256']})
    revisada['achados'][0]['versoes'].append({
        'versao': 2, 'natureza': 'declaracao_documental', 'limitacoes': 'Declaração documental, sem verificação externa.',
        'redacao': 'O contrato 041/2025 declara valor global de R$ 8.750.000,00 (oito milhões, setecentos e cinquenta mil reais).'})
    revisada['vinculos'].extend({**v, 'versao': 2} for v in data['vinculos'] if v['achado_id'] == 'A001')
    revisada['revisoes_assistidas'] = [
        {'achado_id': 'A001', 'versao': 1, 'suporte': 'parcial', 'motivo': 'Citar o valor por extenso, como no contrato.',
         'fontes_reabertas': ['E001'], 'limitacoes': 'Revisão pela IA.', 'acao': 'corrigir'},
        {'achado_id': 'A001', 'versao': 2, 'suporte': 'sustentado', 'motivo': 'Valor conferido na linha 6 do derivado.',
         'fontes_reabertas': ['E001'], 'limitacoes': 'Revisão pela IA.', 'acao': 'manter'}]
    revisada['procedencia'].append({'etapa': 'revisao', 'artefatos': [], 'ferramentas': ['semeadura sintética'],
                                    'modelo_informado_ou_observado': None})
    relatorio(revisada, 'saidas/06_revisao_assistida.md', 'revisao', 'A001@v1 parcial; A001@v2 sustentado; A003 pendente.', -1)
    relatorio(revisada, 'saidas/07_achados_revisados.md', 'achados_revisados', 'A001@v2 A002@v1 A003@v1 · síntese sintética.', -1)
    revisada['procedencia'].append({'etapa': 'sintese', 'artefatos': [], 'ferramentas': ['semeadura sintética'],
                                    'modelo_informado_ou_observado': None})
    relatorio(revisada, 'saidas/08_briefing.md', 'briefing', '[A001@v2] Valor global de R$ 8.750.000,00. E001, D001, linha 6.\n', -1)
    revisada['destinos'].append({'achado_id': 'A001', 'versao': 2, 'destino': 'incluido', 'motivo': 'Declaração documental conferida.',
                                 'briefing': 'saidas/08_briefing.md', 'revisao_suporte': 2})
    segunda = publicar(root, CASO, RODADA, revisada)
    construir(root, CASO, RODADA, 'r1', 'g1')
    construir(root, CASO, RODADA, 'r2', 'g2')
    registros = segunda['manifesto']['registros_sha256']

    def vinculo(eid, papel='suporte', suporte='nao_revisado'):
        referencia = {'tipo': 'ia', 'caso_id': CASO, 'rodada': RODADA, 'revisao': 'r2', 'registros_sha256': registros,
                      'evidencia_id': eid}
        natureza = 'declaracao_documental' if suporte == 'sustentado' else 'pendencia'
        return {'referencia': referencia, 'papel': papel, 'suporte': suporte, 'natureza': natureza,
                'justificativa': 'Vínculo sintético.'}

    def base(rotulo, **campos):
        return {'caso': CASO, 'requisicao_id': rid(rotulo), 'autor': AUTOR, **campos}

    hipoteses.salvar(root, base('h1', enunciado='O contrato 041/2025 foi firmado por R$ 8,75 milhões.',
                                evidencias=[vinculo('E001', suporte='sustentado'), vinculo('E003', suporte='sustentado')],
                                lacunas=[{'descricao': 'Publicação do extrato do contrato no diário oficial.'}]))
    hipoteses.salvar(root, base('h2', enunciado='Os pagamentos acompanharam as medições aprovadas.',
                                evidencias=[vinculo('E005', 'contexto')],
                                lacunas=[{'descricao': 'Ordem bancária dos pagamentos.'}, {'descricao': 'Medição nº 3 lida por texto.'}]))
    hipoteses.salvar(root, base('h3', enunciado='O prazo de 240 dias foi cumprido.',
                                evidencias=[vinculo('E002', suporte='sustentado')],
                                lacunas=[{'descricao': 'Termo de recebimento da obra.'}]))

    prefeitura = mapa_relacoes.salvar_entidade(root, base(
        'p1', tipo='organizacao', nome='Prefeitura Municipal de Vila Serena (fictícia)', evidencias=[vinculo('E001')]))
    construtora = mapa_relacoes.salvar_entidade(root, base(
        'p2', tipo='organizacao', nome='Construtora Horizonte Azul Ltda. (fictícia)', evidencias=[vinculo('E001')]))
    fiscal = mapa_relacoes.salvar_entidade(root, base(
        'p3', tipo='pessoa', nome='Lucia Prates (fictícia)', evidencias=[vinculo('E004')]))
    mapa_relacoes.salvar_relacao(root, base('r1', origem=prefeitura['id'], destino=construtora['id'], tipo='contratante de',
                                            evidencias=[vinculo('E001', suporte='sustentado')]))
    mapa_relacoes.salvar_relacao(root, base('r2', origem=fiscal['id'], destino=construtora['id'], tipo='fiscal do contrato de',
                                            evidencias=[vinculo('E004', suporte='sustentado')]))

    linha_tempo.salvar(root, base('t1', descricao='Assinatura do contrato 041/2025', evidencias=[vinculo('E003', suporte='sustentado')],
                                  datas=[{'tipo': 'assinatura', 'valor': '2025-03-03', 'fonte': 0}]))
    linha_tempo.salvar(root, base('t2', descricao='Medição nº 3 (julho de 2025)', evidencias=[vinculo('E005')],
                                  datas=[{'tipo': 'declarada_por_fonte', 'valor': '2025-07', 'fonte': 0}]))
    linha_tempo.salvar(root, base('t3', descricao='Início do prazo de 240 dias', evidencias=[vinculo('E002')],
                                  datas=[{'tipo': 'fato', 'valor': '2025', 'fonte': 0, 'aproximada': True}]))

    origem_ia = {'tipo': 'ia', 'rodada': RODADA, 'revisao': 'r2', 'registros_sha256': registros,
                 'achado_id': 'A003', 'achado_versao': 1}
    g1 = diligencias.salvar(root, {
        'caso': CASO, 'requisicao_id': rid('g1'), 'autor': AUTOR, 'origem': origem_ia,
        'acao': 'Solicitar à prefeitura as ordens bancárias dos pagamentos do contrato 041/2025',
        'responsavel': 'Repórter sintético', 'prazo': '2030-03-11',
        'observacao': 'Pendência apontada pela análise; atribuída a quem apura.'})
    diligencias.salvar(root, {
        'caso': CASO, 'diligencia_id': g1['id'], 'anterior_sha256': g1['sha256'], 'requisicao_id': rid('g1b'),
        'autor': AUTOR, 'acao': g1['diligencia']['acao'], 'responsavel': 'Repórter sintético', 'prazo': None,
        'estado': 'aguardando_resposta', 'observacao': 'Pedido enviado pela pessoa responsável, fora do sistema.'}, 'atualizar')
    diligencias.salvar(root, {
        'caso': CASO, 'requisicao_id': rid('g2'), 'autor': AUTOR, 'origem': None,
        'acao': 'Conferir a medição nº 3 no original impresso', 'responsavel': 'Editora sintética', 'prazo': '2030-03-25',
        'observacao': 'Sem fonte de origem: diligência livre.'})

    resposta = ('## Leitura sintética com fonte\n\nO contrato declara valor global de R$ 8.750.000,00. [fonte:' + hit['referencia']
                + ']\n\n### O que ainda falta verificar\n\nA medição nº 3 está digitalizada e não foi lida por texto. '
                'Este conteúdo existe apenas para testar a interface, sem execução de modelo.')
    eventos = [('pergunta', {'texto': PERGUNTA}),
               ('escopo', {'caso': CASO, 'rodada': RODADA, 'corpus_id': manifesto['corpus_id'], 'modelo': 'semeadura sem inferência'}),
               ('fonte', {**hit, 'rodada': RODADA, 'geracao': 'v1'}),
               ('resposta', {'item': 'final', 'fase': 'final_answer', 'publicada': True, 'rodada': RODADA, 'texto': resposta})]
    pasta_conversa = root / f'conversas/{CONVERSA}'
    pasta_conversa.mkdir(parents=True, exist_ok=True)
    (pasta_conversa / 'conversa.json').write_text(json.dumps({
        'id': CONVERSA, 'caso': CASO, 'titulo': 'Conversa sintética de conferência', 'estado': 'concluido',
        'rodadas': [RODADA], 'criada_em_utc': '2026-01-01T00:00:00Z'}, ensure_ascii=False, indent=1), encoding='utf-8')
    (pasta_conversa / 'eventos.jsonl').write_text(''.join(
        json.dumps({'seq': i, 'tipo': tipo, 'dados': dados, 'em_utc': '2026-01-01T00:00:00Z'}, ensure_ascii=False) + '\n'
        for i, (tipo, dados) in enumerate(eventos, 1)), encoding='utf-8')
    return {'rodada': RODADA, 'achados': 3, 'hipoteses': 3, 'entidades': 3, 'relacoes': 2, 'eventos': 3,
            'diligencias': 2, 'conversa': CONVERSA}
