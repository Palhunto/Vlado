"""Human UI annotations, separate from immutable AI records and both indexes."""
from datetime import datetime, timezone
import json
import re
import uuid

from comum import dentro, escrever_json, ler_json, pasta_preparacao, sha256
from indice_sqlite import caminho_rodada
import caderno
import indice_achados
import lixeira
from registros_achados import carregar, recibo, trava

ORIGEM_DECLARADA = 'declaracao_do_usuario_na_interface'
ORIGEM_CONTA = 'conta_autenticada_da_mesa'
ORIGENS = (ORIGEM_DECLARADA, ORIGEM_CONTA)
ESTADOS = ('pendente', 'conferida_no_original', 'precisa_de_ajuste', 'sem_suporte_suficiente')


class OriginalNaoConferido(ValueError):
    """'Conferida no original' asked before every cited original was opened in this session."""

    def __init__(self, faltam):
        self.faltam = sorted(faltam)
        super().__init__('Para marcar “Conferida no original”, abra antes o original de cada trecho citado '
                         f'(falta{"m" if len(self.faltam) > 1 else ""}: {", ".join(self.faltam)}).')


def _pasta(run, revision):
    # Keep Windows paths short. Every event binds the full canonical hash below.
    return dentro(run, f'saidas/revisao_humana/{revision}/eventos')


def _historico(run, revision, origin):
    folder = _pasta(run, revision)
    events, previous = [], None
    try:
        paths = sorted(path for path in folder.iterdir() if path.suffix == '.json')
    except FileNotFoundError:
        paths = []
    # Access errors must not look like an empty history and reset marks to pending.
    for path in paths:
        path = dentro(folder, path.name)
        item = ler_json(path)
        if (item.get('sequencia') != len(events) + 1 or item.get('anterior_sha256') != previous
                or item.get('revisao') != revision or item.get('registros_sha256') != origin
                or item.get('estado') not in ESTADOS
                or item.get('caso_id') != run.parent.name or item.get('rodada') != run.name
                or not re.fullmatch(r'A[0-9]{3,}', str(item.get('achado_id', '')))
                or type(item.get('achado_versao')) is not int or item['achado_versao'] < 1
                or not isinstance(item.get('observacao'), str) or len(item['observacao']) > 500
                or not isinstance(item.get('em_utc'), str)
                or item.get('origem') not in ORIGENS
                or (item['origem'] == ORIGEM_CONTA and not isinstance(item.get('responsavel'), str))
                or not re.fullmatch(r'[a-f0-9]{32}', str(item.get('evento_id', '')))):
            raise ValueError('Histórico de revisão humana inválido; marcações não foram carregadas.')
        events.append(item)
        previous = sha256(path)
    return events, previous


def itens_da_conta(root, conta, casos):
    """Human review marks the account made, for its own data export (E4b-2b of Contas; Viga, with the Maestro's
    consent): ``[{tipo: 'revisao', caso, criado_em, id}]`` (id: the event's), only in ``casos`` (those it reaches,
    as the caller says) and only events of this account. Never the observation, the finding or a name. Rounds in
    the trash (on their own or with their conversation) and cases in the trash stay out. An event that cannot be
    read raises ValueError or OSError (the export says it is incomplete)."""
    casos, removidos = lixeira.casos_da_exportacao(root, conta, casos)
    itens = []
    for case in casos:
        execucoes = dentro(root, f'execucoes/{case}')
        for run in sorted(execucoes.iterdir()) if execucoes.is_dir() else []:
            if (not run.is_dir() or not re.fullmatch(lixeira.ID_RODADA, run.name)
                    or lixeira.excluido(root, case, rodada=run.name, itens=removidos)):
                continue
            revisoes = run / 'saidas/revisao_humana'
            for path in sorted(revisoes.glob('*/eventos/*.json')) if revisoes.is_dir() else []:
                item = ler_json(path)
                if not isinstance(item, dict) or item.get('caso_id') != case or item.get('rodada') != run.name:
                    raise ValueError('Histórico de revisão humana inválido.')
                if item.get('origem') == ORIGEM_CONTA and item.get('conta_id') == conta:
                    itens.append({'tipo': 'revisao', 'caso': case, 'criado_em': item.get('em_utc'),
                                  'id': item.get('evento_id')})
    return itens


def _marca(events, identifier, version):
    history = [e for e in events if e['achado_id'] == identifier and e['achado_versao'] == version]
    last = history[-1] if history else {}
    return {'estado': last.get('estado', 'pendente'), 'observacao': last.get('observacao', ''),
            'evento_id': last.get('evento_id'), 'atualizada_em_utc': last.get('em_utc'),
            'origem': last.get('origem') if last else None,
            'responsavel': last.get('responsavel'),
            'historico': history}


def _progresso(data, events):
    counts = dict.fromkeys(ESTADOS, 0)
    for claim in data['achados']:
        counts[_marca(events, claim['id'], claim['versoes'][-1]['versao'])['estado']] += 1
    total = len(data['achados'])
    return {'total': total, 'revisados': total - counts['pendente'], 'pendentes': counts['pendente'],
            'por_estado': counts, 'escopo': 'revisao_inteira; independente_dos_filtros_e_da_paginacao'}


def consultar(root, caso, rodada, revisao, geracao, *, filtros=None, limite=10, deslocamento=0, completa=False):
    filtros = {} if filtros is None else filtros
    if not isinstance(filtros, dict):
        raise ValueError('Filtros inválidos.')
    state = filtros.get('revisao_humana', '')
    if not isinstance(state, str) or state and state not in ESTADOS:
        raise ValueError('Estado de conferência humana inválido.')
    result, data = indice_achados._consulta(root, caso, rodada, revisao, geracao,
        filtros={k: v for k, v in filtros.items() if k != 'revisao_humana'},
        limite=limite, deslocamento=deslocamento, completa=True)
    run = caminho_rodada(root, caso, rodada)
    events, _ = _historico(run, revisao, result['registros_sha256'])
    all_results = []
    for original in result['resultados']:
        item = {**original, 'revisao_humana': _marca(events, original['id'], original['versao'])}
        if not state or item['revisao_humana']['estado'] == state:
            all_results.append(item)
    total = len(all_results)
    selected = all_results if completa else all_results[deslocamento:deslocamento + limite]
    result.update(filtros=filtros, resultados=selected, total_correspondencias=total,
                  retornados=len(selected), deslocamento=0 if completa else deslocamento,
                  limite=None if completa else limite, completa=completa,
                  escopo_exportacao='selecao_filtrada_inteira' if completa else 'pagina',
                  truncado=False if completa else deslocamento > 0 or deslocamento + len(selected) < total,
                  proximo_deslocamento=None if completa or deslocamento + len(selected) >= total else deslocamento + len(selected),
                  progresso_revisao_humana=_progresso(data, events),
                  revisao_humana_separada=True)
    return recibo(run, 'exportar_com_revisao_humana' if completa else 'consultar_com_revisao_humana', **result)


def detalhe(root, caso, rodada, revisao, geracao, identifier):
    con, data, manifest = indice_achados._abrir(root, caso, rodada, revisao, geracao)
    con.close()
    claim = next((c for c in data['achados'] if c['id'] == identifier), None)
    if claim is None:
        raise ValueError('Achado não pertence a esta seleção.')
    run = caminho_rodada(root, caso, rodada)
    events, _ = _historico(run, revisao, manifest['registros_sha256'])
    item = indice_achados.resumo(data, claim)
    item['revisao_humana'] = _marca(events, item['id'], item['versao'])
    return recibo(run, 'detalhe_com_revisao_humana', **manifest, achado=item)


def selecionar(root, caso, rodada, revisao, geracao, selecoes):
    """Resolve explicitly selected, current marks from storage, never client prose."""
    fields = {'achado_id', 'achado_versao', 'evento_id', 'registros_sha256'}
    if not isinstance(selecoes, list) or not 1 <= len(selecoes) <= 20:
        raise ValueError('Selecione de 1 a 20 observações salvas.')
    run = caminho_rodada(root, caso, rodada)
    with trava(run):
        con, data, manifest = indice_achados._abrir(root, caso, rodada, revisao, geracao)
        con.close()
        events, _ = _historico(run, revisao, manifest['registros_sha256'])
        selected, seen = [], set()
        for choice in selecoes:
            if (not isinstance(choice, dict) or set(choice) != fields
                    or not isinstance(choice['achado_id'], str)
                    or type(choice['achado_versao']) is not int
                    or not isinstance(choice['evento_id'], str)
                    or not re.fullmatch(r'[a-f0-9]{32}', choice['evento_id'])
                    or choice['registros_sha256'] != manifest['registros_sha256']):
                raise ValueError('Seleção de observações inválida ou de outra revisão. Selecione novamente.')
            identifier = choice['achado_id']
            if identifier in seen:
                raise ValueError('Observação duplicada na seleção.')
            seen.add(identifier)
            claim = next((c for c in data['achados'] if c['id'] == identifier), None)
            if claim is None or claim['versoes'][-1]['versao'] != choice['achado_versao']:
                raise ValueError('A versão do achado mudou. Selecione novamente.')
            mark = _marca(events, identifier, choice['achado_versao'])
            if not mark['evento_id'] or mark['evento_id'] != choice['evento_id']:
                raise ValueError('A marcação mudou ou não foi salva. Selecione novamente as observações.')
            event = mark['historico'][-1]
            item = indice_achados.resumo(data, claim)
            selected.append({'achado_id': identifier, 'achado_versao': item['versao'],
                'redacao_anterior': item['redacao'], 'natureza_anterior': item['natureza'],
                'subquestao': item['subquestao'], 'estado': mark['estado'],
                'observacao': mark['observacao'], 'evento_id': mark['evento_id'],
                'evento_sha256': sha256(_pasta(run, revisao) / f'{event["sequencia"]:08d}_{event["evento_id"]}.json'),
                'marcada_em_utc': mark['atualizada_em_utc'],
                'fontes': item['evidencias'], 'vinculos': item['vinculos']})
        result = {'esquema': 1, 'caso_id': caso, 'rodada_origem': rodada,
            'revisao_origem': revisao, 'geracao_achados': geracao,
            'registros_sha256': manifest['registros_sha256'],
            'snapshot_origem_sha256': data['snapshot_sha256'],
            'origem': 'observacoes_humanas_selecionadas_explicitamente', 'observacoes': selected}
        if len(json.dumps(result, ensure_ascii=False)) > 200000:
            raise ValueError('As observações e fontes excedem o limite de contexto. Selecione menos achados.')
        return result


def salvar(root, caso, rodada, revisao, *, achado_id, achado_versao, registros_sha256,
           estado, observacao='', anterior=None, conta=None, originais_abertos=None):
    """`originais_abertos`: evidence ids whose original this session opened (HTTP); None skips the check."""
    if estado not in ESTADOS or not isinstance(estado, str):
        raise ValueError('Escolha um dos quatro estados de conferência.')
    if (not isinstance(observacao, str) or len(observacao) > 500
            or any(ord(c) < 32 and c not in '\n\t' for c in observacao)):
        raise ValueError('A observação deve ter até 500 caracteres, sem controles inválidos.')
    if type(achado_versao) is not int or not isinstance(achado_id, str) or not re.fullmatch(r'A[0-9]{3,}', achado_id):
        raise ValueError('Identidade do achado inválida.')
    if anterior is not None and (not isinstance(anterior, str) or not re.fullmatch(r'[a-f0-9]{32}', anterior)):
        raise ValueError('Identidade da marcação anterior inválida.')
    conta = caderno.conta_valida(conta)
    run = caminho_rodada(root, caso, rodada)
    with trava(run):
        data, origin = carregar(root, caso, rodada, revisao)
        if registros_sha256 != origin['registros_sha256']:
            raise ValueError('A revisão da IA mudou. Abra Conferir novamente antes de salvar.')
        claim = next((c for c in data['achados'] if c['id'] == achado_id), None)
        if not claim or claim['versoes'][-1]['versao'] != achado_versao:
            raise ValueError('Achado ou versão fora desta revisão.')
        if estado == 'conferida_no_original' and not any(v['achado_id'] == achado_id and v['versao'] == achado_versao for v in data['vinculos']):
            raise ValueError('Este achado não tem fontes vinculadas. Registre ajuste ou suporte insuficiente, conforme sua avaliação.')
        events, previous_hash = _historico(run, revisao, origin['registros_sha256'])
        current = _marca(events, achado_id, achado_versao)
        if estado == 'conferida_no_original' and current['estado'] != estado and originais_abertos is not None:
            citadas = {v['evidencia_id'] for v in data['vinculos']
                       if v['achado_id'] == achado_id and v['versao'] == achado_versao}
            if citadas - set(originais_abertos):
                raise OriginalNaoConferido(citadas - set(originais_abertos))
        observation = observacao.strip()
        # Retrying a lost response or saving the same values adds no duplicate event.
        if current['estado'] == estado and current['observacao'] == observation:
            return {'estado': 'sem_alteracao', 'revisao_humana': current, 'progresso': _progresso(data, events)}
        if anterior != current['evento_id']:
            raise ValueError('A marcação foi alterada em outra janela. Abra Conferir novamente para não sobrescrever a avaliação anterior.')
        item = {'evento_id': uuid.uuid4().hex, 'sequencia': len(events) + 1,
                'caso_id': caso, 'rodada': rodada, 'revisao': revisao,
                'registros_sha256': origin['registros_sha256'], 'snapshot_sha256': data['snapshot_sha256'],
                'achado_id': achado_id, 'achado_versao': achado_versao,
                'estado': estado, 'observacao': observation,
                'em_utc': datetime.now(timezone.utc).isoformat(), 'responsavel': conta['nome'] if conta else None,
                'origem': ORIGEM_CONTA if conta else ORIGEM_DECLARADA, 'anterior_sha256': previous_hash}
        if conta:
            item['conta_id'] = conta['id']
        folder = _pasta(run, revisao)
        folder.mkdir(parents=True, exist_ok=True)
        with pasta_preparacao(folder, '.preparacao_') as temp:
            staged = temp / 'evento.json'
            escrever_json(staged, item, exclusivo=True)
            staged.rename(folder / f'{item["sequencia"]:08d}_{item["evento_id"]}.json')
        events.append(item)
        return {'estado': 'registrado', 'revisao_humana': _marca(events, achado_id, achado_versao),
                'progresso': _progresso(data, events), 'originais_ia_preservados': True}
