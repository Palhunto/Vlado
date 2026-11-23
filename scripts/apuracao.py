"""Editable human notebook, versioned separately from documents and AI outputs."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

import caderno
import indice_achados
from comum import dentro, escrever_json, ler_json, pasta_preparacao, sha256
from indice_sqlite import ler_passagem, caminho_rodada
import lixeira

OPERACOES = ('apuracao-listar', 'apuracao-salvar', 'apuracao-excluir',
             'apuracao-adicionar', 'apuracao-exportar', 'apuracao-original')
# Espaço de escrita do Caderno (revisão por nota, sem trava global do caderno inteiro).
OPERACOES_NOTAS = ('apuracao-notas', 'apuracao-nota', 'apuracao-nota-salvar',
                   'apuracao-nota-inserir', 'apuracao-nota-excluir')
AUTORIA_CONTA = 'conta_autenticada_da_mesa'
MENSAGEM_CONFLITO = 'Conflito: a nota foi alterada em outra aba.'


class ConflitoNota(ValueError):
    """A nota mudou desde a revisão que o editor conhecia; nada foi gravado."""

    def __init__(self, atual):
        super().__init__(MENSAGEM_CONFLITO)
        self.atual = atual


def _pasta(root, case):
    caderno._pasta(root, case)  # Same case validation and trash policy, no source reads.
    return dentro(root, f'casos/{case}/apuracao')


def listar(root, case):
    folder = _pasta(root, case)
    paths = sorted((folder / 'revisoes').glob('*.json'))
    if not paths:
        return {'esquema': 1, 'caso': case, 'revisao': 0, 'notas': [], 'requisicoes': {}}
    state = ler_json(paths[-1])
    if state.get('caso') != case or state.get('esquema') != 1 or not isinstance(state.get('notas'), list):
        raise ValueError('Caderno editável inválido; os registros foram preservados.')
    return state


def _nota(state, identifier):
    note = next((n for n in state['notas'] if n['id'] == identifier), None)
    if note is None:
        raise ValueError('Nota não encontrada nesta apuração. Atualize o caderno.')
    return note


def _selecao(text, source):
    caderno._texto(text, 'Texto selecionado', 12000)
    if text not in source:
        raise ValueError('A seleção não pertence ao trecho de origem. Selecione novamente.')
    return text


def _evidencia(root, case, data):
    """Resolve all attribution server-side; never trust browser filenames or pages."""
    run = data.get('rodada')
    lixeira.conferir_disponivel(root, case, rodada=run)
    common = {'caso': case, 'rodada': run}
    if data.get('tipo') == 'pesquisa':
        generation = data.get('geracao', 'v1')
        passage = ler_passagem(root, case, run, data.get('referencia'), geracao=generation)['passagem']
        selected = _selecao(data.get('texto'), passage['trecho'])
        source = {**common, 'tipo': 'pesquisa', 'geracao': generation,
                  'referencia': passage['referencia'], 'texto_selecionado': selected,
                  'documentos': [{**passage, 'localizador': f"Linhas {passage['linha_inicio']}–{passage['linha_fim']}"}]}
    elif data.get('tipo') == 'ia':
        revision, generation = data.get('revisao'), data.get('geracao_achados')
        claim = indice_achados.detalhe(root, case, run, revision, generation, data.get('achado_id'))['achado']
        if claim['versao'] != data.get('achado_versao'):
            raise ValueError('A versão do achado mudou. Selecione novamente.')
        evidence_id = data.get('evidencia_id')
        evidences = [e for e in claim['evidencias'] if any(v['evidencia_id'] == e['id'] for v in claim['vinculos'])]
        if evidence_id:
            evidences = [e for e in evidences if e['id'] == evidence_id]
            if not evidences:
                raise ValueError('Evidência fora deste achado.')
        selected = _selecao(data.get('texto'), evidences[0]['trecho'] if evidence_id else claim['redacao'])
        docs = []
        for ev in evidences:
            # Validates originals, textual context and hashes using the existing contract.
            indice_achados.evidencia(root, case, run, revision, ev['id'])
            loc = ev['localizador']
            docs.append({**ev, 'pagina_pdf': loc.get('pagina_pdf'),
                         'localizador': loc.get('descricao') or (f"Linhas {loc['linha_inicio']}–{loc['linha_fim']}" if loc.get('linha_inicio') else loc['tipo'])})
        source = {**common, 'tipo': 'ia', 'revisao': revision, 'geracao_achados': generation,
                  'achado_id': claim['id'], 'achado_versao': claim['versao'],
                  'evidencia_id': evidence_id, 'texto_selecionado': selected, 'documentos': docs}
    else:
        raise ValueError('Origem de evidência inválida.')
    # Add human-readable names from this run's frozen manifest, never another case.
    origin, _ = caderno.contexto(root, case, run)
    names = {d['id']: d.get('nome_recebido', Path(d['arquivo']).name) for d in origin['manifesto']['documentos']}
    for doc in source['documentos']:
        doc['nome_documento'] = names.get(doc['documento_id'], doc['documento_id'])
    return source


def _ref_conta(conta):
    return {'origem': AUTORIA_CONTA, 'conta_id': conta['id'], 'nome': conta['nome']}


def _identificador_requisicao(data):
    request = data.get('requisicao_id')
    if not isinstance(request, str) or not re.fullmatch(r'[a-f0-9]{32}', request):
        raise ValueError('Identidade de salvamento inválida.')
    return request


def _aplicar(root, case, operation, data, state, note_id, conta, now):
    """Muta `state` (cópia) conforme a operação; devolve nada. Autoria vem só da conta."""
    if operation == 'apuracao-excluir':
        state['notas'].remove(_nota(state, note_id))
        return
    if note_id and any(n['id'] == note_id for n in state['notas']):
        note = _nota(state, note_id)
    elif data.get('nota_id'):
        note = _nota(state, data['nota_id'])
    else:
        note = {'id': note_id or 'E' + uuid.uuid4().hex, 'titulo': 'Nova nota', 'texto': '',
                'fontes': [], 'criado_em_utc': now}
        if conta:
            note['criado_por'] = _ref_conta(conta)
        state['notas'].append(note)
    if operation == 'apuracao-salvar':
        note['titulo'] = caderno._texto(data.get('titulo'), 'Título', 200)
        text = data.get('texto')
        caderno._texto(text, 'Nota', 200000, vazio=True)
        note['texto'] = text  # Keep Markdown whitespace intact.
    elif operation == 'apuracao-adicionar':
        source = _evidencia(root, case, data.get('origem', {}))
        source['id'] = 'F' + uuid.uuid4().hex
        if conta:
            source['adicionada_por'] = _ref_conta(conta)
        note['fontes'].append(source)
        if not data.get('nota_id'):
            note['titulo'] = 'Seleção da IA' if source['tipo'] == 'ia' else 'Seleção documental'
        number = len(note['fontes'])
        quote = '\n'.join('> ' + line for line in source['texto_selecionado'].splitlines())
        note['texto'] += ('\n\n' if note['texto'] else '') + quote + f'\n\n[Fonte {number}]'
        caderno._texto(note['texto'], 'Nota', 200000, vazio=True)
    else:
        raise ValueError('Operação de edição desconhecida.')
    note['atualizado_em_utc'] = now
    note['revisao'] = note.get('revisao', 0) + 1
    if conta:
        note['atualizado_por'] = _ref_conta(conta)


def _executar(root, operation, data, conta, por_nota):
    case = data.get('caso')
    folder = _pasta(root, case)
    request = _identificador_requisicao(data)
    conta = caderno.conta_valida(conta)
    digest = caderno._hash(caderno.com_conta(data, conta))
    identifier = data.get('nota_id')
    # Em modo por nota, uma nota nova nasce com ID derivado da requisição (reenvio idempotente).
    note_id = identifier or ('E' + request if por_nota and operation != 'apuracao-excluir' else None)
    with caderno._trava(folder):
        state = deepcopy(listar(root, case))
        if request in state['requisicoes']:
            if state['requisicoes'][request] != digest:
                raise ValueError('Esta tentativa já foi usada com outro conteúdo.')
            return state, note_id, True
        if por_nota:
            if identifier:
                current = _nota(state, identifier)
                if type(data.get('revisao_nota')) is not int or data['revisao_nota'] != current.get('revisao', 0):
                    raise ConflitoNota({'nota_id': identifier, 'revisao': current.get('revisao', 0),
                                        'atualizado_em_utc': current.get('atualizado_em_utc')})
        elif type(data.get('revisao')) is not int or data['revisao'] != state['revisao']:
            raise ValueError('O caderno mudou em outra janela. Reabra as notas antes de salvar; copie seu texto para preservá-lo.')
        _aplicar(root, case, operation, data, state, note_id, conta, datetime.now(timezone.utc).isoformat())
        state['revisao'] += 1
        state['requisicoes'][request] = digest
        if len(caderno._canon(state)) > 8 * 1024 * 1024:
            raise ValueError('O caderno excede 8 MB. Reduza o conteúdo antes de salvar.')
        target = folder / 'revisoes' / f"{state['revisao']:010d}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        with pasta_preparacao(folder, '.preparacao_') as staging:
            staged = staging / 'caderno.json'
            escrever_json(staged, state, exclusivo=True)
            staged.rename(target)
        return state, note_id, False


def alterar(root, operation, data, conta=None):
    """Operação com trava de revisão do caderno inteiro (compatível com a versão anterior)."""
    return _executar(root, operation, data, conta, False)[0]


def alterar_nota(root, operation, data, conta=None):
    """Salvar/inserir fonte/excluir com revisão por nota (`revisao_nota`), própria para autosave.

    Levanta ConflitoNota (ValueError) sem gravar quando a nota mudou desde `revisao_nota`.
    """
    state, note_id, replay = _executar(root, operation, data, conta, True)
    note = next((n for n in state['notas'] if n['id'] == note_id), None)
    return {'estado': 'ja_registrado' if replay else 'salvo', 'revisao_caderno': state['revisao'],
            'nota_id': note_id, 'nota': deepcopy(note) if note else None,
            'salvo_em_utc': (note or {}).get('atualizado_em_utc')}


def listar_notas(root, case):
    """Lista leve para a coluna esquerda: sem texto nem fontes completas."""
    state = listar(root, case)
    notas = [{'id': n['id'], 'titulo': n['titulo'], 'atualizado_em_utc': n.get('atualizado_em_utc') or n['criado_em_utc'],
              'criado_em_utc': n['criado_em_utc'], 'revisao': n.get('revisao', 0), 'fontes': len(n['fontes']),
              'autor': (n.get('atualizado_por') or n.get('criado_por') or {}).get('nome')}
             for n in state['notas']]
    notas.sort(key=lambda n: (n['atualizado_em_utc'], n['id']), reverse=True)
    return {'caso': case, 'revisao_caderno': state['revisao'], 'notas': notas}


def itens_da_conta(root, conta, casos):
    """Notes the account created, for its own data export (E4b-2b of Contas; Viga, with the Maestro's consent):
    ``[{tipo: 'nota', caso, criado_em, id}]``, only in ``casos`` (those it reaches, as the caller says) and only
    those whose ``criado_por`` is this account. Never the title, the text or a name. Deleted notes and cases in the
    trash stay out. A notebook that cannot be read raises ValueError or OSError (the export says it is incomplete)."""
    casos, _ = lixeira.casos_da_exportacao(root, conta, casos)
    itens = []
    for case in casos:
        for note in listar(root, case)['notas']:
            if isinstance(note, dict) and (note.get('criado_por') or {}).get('conta_id') == conta:
                itens.append({'tipo': 'nota', 'caso': case, 'criado_em': note['criado_em_utc'], 'id': note['id']})
    return itens


def _disponivel(root, case, source, doc):
    try:
        lixeira.conferir_disponivel(root, case, rodada=source['rodada'])
        return dentro(caminho_rodada(root, case, source['rodada']), doc['original']).is_file()
    except (ValueError, OSError, KeyError):
        return False


def nota_com_fontes(root, case, note_id):
    """Nota completa mais as fontes resolvidas para a coluna direita (sem ler os originais)."""
    state = listar(root, case)
    note = _nota(state, note_id)
    fontes = []
    for number, source in enumerate(note['fontes'], 1):
        docs = []
        for index, doc in enumerate(source['documentos']):
            docs.append({'indice': index, 'documento_id': doc['documento_id'], 'nome_documento': doc['nome_documento'],
                         'pagina_pdf': doc.get('pagina_pdf'), 'localizador': doc['localizador'],
                         'original_sha256': doc['original_sha256'], 'disponivel': _disponivel(root, case, source, doc),
                         'abrir': {'operacao': 'apuracao-original', 'caso': case, 'nota_id': note_id,
                                   'fonte_id': source['id'], 'documento_indice': index}})
        fontes.append({'id': source['id'], 'numero': number, 'marcador': f'[Fonte {number}]', 'tipo': source['tipo'],
                       'caso': source['caso'], 'rodada': source['rodada'],
                       'referencia': source.get('referencia') or source.get('achado_id'),
                       'achado_versao': source.get('achado_versao'),
                       'texto_selecionado': source['texto_selecionado'], 'documentos': docs,
                       'adicionada_por': (source.get('adicionada_por') or {}).get('nome')})
    return {'caso': case, 'revisao_caderno': state['revisao'], 'nota': deepcopy(note), 'fontes': fontes}


def executar(root, operation, data, conta=None):
    """Despacho único para o HTTP. `apuracao-exportar` e `apuracao-original` seguem fora (binários)."""
    case = data.get('caso')
    if operation == 'apuracao-notas':
        return listar_notas(root, case)
    if operation == 'apuracao-nota':
        return nota_com_fontes(root, case, data.get('nota_id'))
    mapa = {'apuracao-nota-salvar': 'apuracao-salvar', 'apuracao-nota-inserir': 'apuracao-adicionar',
            'apuracao-nota-excluir': 'apuracao-excluir'}
    if operation in mapa:
        return alterar_nota(root, mapa[operation], data, conta)
    raise ValueError('Operação desconhecida do caderno editável.')


def original(root, data):
    state = listar(root, data.get('caso'))
    note = _nota(state, data.get('nota_id'))
    source = next((s for s in note['fontes'] if s['id'] == data.get('fonte_id')), None)
    if not source:
        raise ValueError('Fonte não encontrada nesta nota.')
    index = data.get('documento_indice')
    if type(index) is not int or not 0 <= index < len(source['documentos']):
        raise ValueError('Documento fora da fonte selecionada.')
    lixeira.conferir_disponivel(root, state['caso'], rodada=source['rodada'])
    doc = source['documentos'][index]
    path = dentro(caminho_rodada(root, state['caso'], source['rodada']), doc['original'])
    if sha256(path) != doc['original_sha256']:
        raise ValueError('Hash da fonte divergente; a nota foi preservada.')
    return path
