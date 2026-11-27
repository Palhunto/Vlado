"""Contrato comum de evidência: documento, localizador e suporte.

Uma evidência nunca é texto livre. Ela é uma *referência* a uma fonte já registrada
neste caso — uma evidência (E-ID) de um conjunto de achados publicado ou a fonte de
um registro humano do caderno — e só é aceita depois de resolvida contra o original
com hash conferido. A referência leva o caso, porque IDs de documentos só são únicos
dentro dele. Um *vínculo* liga essa referência a um item (hipótese, evento, entidade,
relação) e declara o papel, a avaliação do suporte e o tipo de afirmação (natureza).

Também oferece o armazenamento comum por eventos encadeados (append-only) usado
pelos quadros de hipóteses, linha do tempo e mapa de relações. Sem modelo ou rede.
O contrato publicado para a equipe está em ``.maestro/equipe/CONTRATO_EVIDENCIA.md``.
"""
from __future__ import annotations

from contextlib import contextmanager
import contextvars
from copy import deepcopy
from datetime import datetime, timezone
import re

from comum import dentro, escrever_json, ler_json, pasta_preparacao, sha256
from indice_sqlite import ID_DOCUMENTO, ID_GERACAO, _entradas, caminho_rodada
from registros_achados import NATUREZAS, SCHEMA, SUPORTES, carregar, conferir_evidencia
import caderno
import lixeira
import vinculo_ia

ESQUEMA = 1
_ACHADOS = ler_json(SCHEMA)['properties']
# Papéis e E-ID vêm do esquema canônico dos achados, sem cópia literal.
PAPEIS = tuple(_ACHADOS['vinculos']['items']['properties']['papel']['enum'])
ID_EVIDENCIA = _ACHADOS['evidencias']['items']['properties']['id']['pattern']
TIPOS_LOCALIZADOR = (*_ACHADOS['evidencias']['items']['properties']['localizador']['properties']['tipo']['enum'],
                     'descrito')
CAMPOS_REF = {'ia': {'tipo', 'caso_id', 'rodada', 'revisao', 'registros_sha256', 'evidencia_id'},
              'humana': {'tipo', 'caso_id', 'registro_id', 'sha256', 'fonte'}}
CAMPOS_VINCULO = {'referencia', 'papel', 'suporte', 'natureza', 'justificativa'}
CAMPOS_SALVOS = CAMPOS_VINCULO | {'documento_id', 'original_sha256', 'localizador'}
# Onda 4 (#registro-vinculo): optional, computed by the server, never accepted from the client (vinculo_ia).
CAMPOS_REGISTRO = {'revisao_ia', 'alteracoes'}
CAMPOS_LOCALIZADOR = {'tipo', 'pagina_pdf', 'linha_inicio', 'linha_fim', 'descricao', 'legivel'}
# Naturezas que um documento pode estabelecer por si; inferência e pendência não sustentam fato.
NATUREZAS_DOCUMENTAIS = ('declaracao_documental', 'alegacao_atribuida')
HASH = caderno.HASH
MAXIMO_VINCULOS = 100
# Onda 4 (B1; R1 of the Coruja on 446bfc6): the finding each input link chose, by (reference key, role), for
# Colecao.salvar only. It never rides inside the link, so nested links (the story claims) stay as they were.
_ESCOLHAS = contextvars.ContextVar('escolhas_de_achado', default=None)


def texto(value, field, maximum, *, vazio=False):
    return caderno._texto(value, field, maximum, vazio=vazio)


def referencia(ref):
    """Valida somente a forma da referência e devolve uma cópia canônica."""
    kind = ref.get('tipo') if isinstance(ref, dict) else None
    if not isinstance(kind, str) or kind not in CAMPOS_REF or set(ref) != CAMPOS_REF[kind]:
        raise ValueError('Referência de evidência inválida: use uma evidência dos achados ou uma fonte do caderno.')
    if not isinstance(ref['caso_id'], str) or not re.fullmatch(lixeira.ID_CASO, ref['caso_id']):
        raise ValueError('Referência de evidência sem apuração válida.')
    if kind == 'ia':
        if (not isinstance(ref['rodada'], str) or not re.fullmatch(lixeira.ID_RODADA, ref['rodada'])
                or not isinstance(ref['revisao'], str) or not re.fullmatch(ID_GERACAO, ref['revisao'])
                or not isinstance(ref['registros_sha256'], str) or not re.fullmatch(HASH, ref['registros_sha256'])
                or not isinstance(ref['evidencia_id'], str) or not re.fullmatch(ID_EVIDENCIA, ref['evidencia_id'])):
            raise ValueError('Referência a evidência dos achados inválida.')
    elif (not isinstance(ref['registro_id'], str) or not re.fullmatch(caderno.ID, ref['registro_id'])
            or not isinstance(ref['sha256'], str) or not re.fullmatch(HASH, ref['sha256'])
            or type(ref['fonte']) is not int or not 0 <= ref['fonte'] < 1000):
        raise ValueError('Referência a fonte do caderno inválida.')
    return {k: ref[k] for k in sorted(CAMPOS_REF[kind])}


def chave(ref):
    return caderno._hash(referencia(ref))


def identidade(link):
    """Identidade de um vínculo dentro de um item: a referência e o papel."""
    return chave(link['referencia']), link['papel']


def _legivel(doc_id, loc):
    parts = [doc_id]
    page = loc.get('pagina_pdf')
    if page is not None and not re.search(rf'\bPDF {page}\b', loc.get('descricao') or ''):
        parts.append(f'página PDF {page}')
    if loc.get('linha_inicio') is not None:
        start, end = loc['linha_inicio'], loc['linha_fim']
        parts.append(f'linha {start}' if start == end else f'linhas {start}–{end}')
    if loc.get('descricao'):
        parts.append(loc['descricao'])
    return ' · '.join(parts)


def _rodada(root, case, rodada, cache):
    """Entradas congeladas da rodada, lidas uma vez por caso/rodada e reaproveitadas."""
    key = ('rodada', case, rodada)
    if key not in cache:
        run = caminho_rodada(root, case, rodada)
        frozen, descriptor = _entradas(run, case, rodada)
        cache[key] = {'run': run, 'corpus_id': frozen.get('corpus_id'),
                      'documentos': {d['id']: d for d in frozen['documentos']},
                      'fontes': {f"entradas/{s['arquivo']}": s for s in descriptor['fontes']}}
    return cache[key]


def _resolver_ia(root, case, ref, cache):
    lixeira.conferir_disponivel(root, case, rodada=ref['rodada'])
    key = ('ia', case, ref['rodada'], ref['revisao'])
    if key not in cache:
        cache[key] = carregar(root, case, ref['rodada'], ref['revisao'])
    data, manifest = cache[key]
    frozen = _rodada(root, case, ref['rodada'], cache)
    if manifest['registros_sha256'] != ref['registros_sha256']:
        raise ValueError('O conjunto de achados referenciado mudou de identidade.')
    item = next((e for e in data['evidencias'] if e['id'] == ref['evidencia_id']), None)
    if item is None:
        raise ValueError('Evidência não pertence a esta revisão/caso/rodada.')
    conferir_evidencia(root, case, ref['rodada'], item, frozen['fontes'])
    loc = item['localizador']
    doc = frozen['documentos'].get(item['documento_id'], {})
    locator = {'tipo': loc['tipo'], 'pagina_pdf': loc['pagina_pdf'], 'linha_inicio': loc['linha_inicio'],
               'linha_fim': loc['linha_fim'], 'descricao': loc['descricao']}
    locator['legivel'] = _legivel(item['documento_id'], locator)
    textual = None
    if item['fonte_textual'] is not None:
        source = frozen['fontes'][item['fonte_textual']]
        textual = {'arquivo': item['fonte_textual'], 'sha256': item['fonte_sha256'], 'tipo': source['tipo']}
    return {'esquema': ESQUEMA, 'origem': 'ia', 'referencia': ref,
            'documento': {'caso_id': case, 'rodada': ref['rodada'], 'corpus_id': frozen['corpus_id'],
                          'origem_id': None, 'documento_id': item['documento_id'],
                          'original_sha256': item['original_sha256'],
                          'nome': doc.get('nome_recebido', item['original'].rsplit('/', 1)[-1])},
            'localizador': locator, 'trecho': item['trecho'], 'modo': item['modo'], 'fonte_textual': textual,
            'conferencia': 'leitura_visual' if item['modo'] == 'visual' else 'trecho_localizado_no_texto_autorizado',
            'atribuicao': item['atribuicao'], 'limitacoes': item['limitacoes'], 'autor': 'IA',
            'origem_autoria': 'ia'}, \
        dentro(frozen['run'], item['original'])


def _resolver_humana(root, case, ref, cache):
    entry, _ = caderno._carregar(root, case, ref['registro_id'], ref['sha256'], cache=cache)
    if ref['fonte'] >= len(entry['fontes']):
        raise ValueError('Fonte fora deste registro do caderno.')
    source = entry['fontes'][ref['fonte']]
    if source.get('rodada_origem'):
        lixeira.conferir_disponivel(root, case, rodada=source['rodada_origem'])
    origin = ler_json(dentro(root, f'casos/{case}/caderno/origens/{source["origem_id"]}.json'))
    path, _ = caderno._original(root, origin, source['documento_id'], source['original_sha256'], cache)
    locator = {'tipo': 'pagina' if source['pagina_pdf'] is not None else 'descrito',
               'pagina_pdf': source['pagina_pdf'], 'linha_inicio': None, 'linha_fim': None,
               'descricao': source['localizador']}
    locator['legivel'] = _legivel(source['documento_id'], locator)
    return {'esquema': ESQUEMA, 'origem': 'humana', 'referencia': ref,
            'documento': {'caso_id': case, 'rodada': source['rodada_origem'], 'corpus_id': source['corpus_id'],
                          'origem_id': source['origem_id'], 'documento_id': source['documento_id'],
                          'original_sha256': source['original_sha256'], 'nome': source['nome_documento']},
            'localizador': locator, 'trecho': source['trecho'], 'modo': None, 'fonte_textual': None,
            'conferencia': source['conferencia_textual'], 'atribuicao': None, 'limitacoes': None,
            'autor': entry['autor'], 'origem_autoria': entry['origem_autoria']}, path


def resolver(root, case, ref, cache=None, *, caminho=False):
    """Resolve a referência na evidência normalizada (documento, localizador, trecho).

    Recusa, sempre com ``ValueError`` e sem caminho absoluto na mensagem, referência de
    outro caso, rodada na lixeira, hash divergente ou fonte/original ausente.
    Com ``caminho=True`` devolve também o caminho do original conferido, para abertura.
    """
    ref = referencia(ref)
    if ref['caso_id'] != case:
        raise ValueError('Evidência de outra apuração; vincule somente fontes desta apuração.')
    cache = {} if cache is None else cache
    try:
        evidence, path = (_resolver_ia if ref['tipo'] == 'ia' else _resolver_humana)(root, case, ref, cache)
    except PermissionError as exc:
        raise ValueError('Acesso negado à fonte da evidência; verifique as permissões de leitura.') from exc
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ValueError('Fonte da evidência ausente nesta apuração (rodada, revisão, registro ou original).') from exc
    except OSError as exc:
        raise ValueError('Fonte da evidência inacessível.') from exc
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError('Evidência malformada na fonte registrada.') from exc
    return (evidence, path) if caminho else evidence


def original(root, case, ref):
    """Caminho do original da evidência, depois de conferir o hash."""
    return resolver(root, case, ref, caminho=True)[1]


def _regras(papel, suporte, natureza, papeis=PAPEIS):
    if not isinstance(papel, str) or papel not in papeis:
        raise ValueError('Papel da evidência inválido.')
    if not isinstance(suporte, str) or suporte not in SUPORTES:
        raise ValueError('Avaliação de suporte inválida.')
    if not isinstance(natureza, str) or natureza not in NATUREZAS:
        raise ValueError('Tipo de afirmação (natureza) inválido.')
    if papel == 'contexto' and suporte != 'nao_revisado':
        raise ValueError('Evidência de contexto não recebe avaliação de suporte.')
    if natureza == 'pendencia' and suporte == 'sustentado':
        raise ValueError('Pendência não pode ser sustentada; indique o tipo de afirmação.')


def _localizador(loc):
    if (not isinstance(loc, dict) or set(loc) != CAMPOS_LOCALIZADOR or loc['tipo'] not in TIPOS_LOCALIZADOR
            or not (loc['pagina_pdf'] is None or type(loc['pagina_pdf']) is int and loc['pagina_pdf'] >= 1)
            or (loc['linha_inicio'] is None) != (loc['linha_fim'] is None)
            or loc['linha_inicio'] is not None and (type(loc['linha_inicio']) is not int or type(loc['linha_fim']) is not int
                                                    or not 1 <= loc['linha_inicio'] <= loc['linha_fim'])):
        raise ValueError('Localizador preservado inválido.')
    texto(loc['descricao'], 'Localizador', 1000, vazio=True)
    texto(loc['legivel'], 'Localizador', 1200)


def validar_vinculo_salvo(item):
    """Confere a forma preservada de um vínculo, sem abrir fontes."""
    if not _forma_salva(item):
        raise ValueError('Vínculo de evidência preservado é inválido.')
    referencia(item['referencia'])
    _regras(item['papel'], item['suporte'], item['natureza'])
    if (not isinstance(item['original_sha256'], str) or not re.fullmatch(HASH, item['original_sha256'])
            or not isinstance(item['documento_id'], str) or not re.fullmatch(ID_DOCUMENTO, item['documento_id'])):
        raise ValueError('Vínculo de evidência preservado é inválido.')
    texto(item['justificativa'], 'Justificativa do vínculo', 2000)
    _localizador(item['localizador'])
    vinculo_ia.validar(item)


def _forma_salva(item):
    return isinstance(item, dict) and CAMPOS_SALVOS <= set(item) <= CAMPOS_SALVOS | CAMPOS_REGISTRO


def _assinatura(evidence):
    loc = evidence['localizador']
    return (evidence['origem'], evidence['documento']['documento_id'], evidence['documento']['original_sha256'],
            tuple(loc[k] for k in ('tipo', 'pagina_pdf', 'linha_inicio', 'linha_fim', 'descricao')), evidence['trecho'])


def vinculos(root, case, items, *, minimo=0, papeis=PAPEIS, cache=None, preservar_indisponiveis=False):
    """Valida e resolve vínculos antes do salvamento; devolve a forma canônica.

    Aceita a forma de entrada (``referencia``, ``papel``, ``justificativa`` e, opcionais,
    ``suporte`` e ``natureza``) e a forma salva devolvida pelos quadros. A forma salva é
    resolvida de novo e recusada se o documento ou o original mudaram. Com
    ``preservar_indisponiveis``, um vínculo salvo cuja fonte deixou de resolver é mantido
    como está (uso: retirar um registro cuja fonte foi apagada).
    """
    if isinstance(items, list) and len(items) > MAXIMO_VINCULOS:
        raise ValueError(f'Limite de {MAXIMO_VINCULOS} evidências por item: desligue uma antes de ligar outra.')
    if not isinstance(items, list) or not minimo <= len(items):
        raise ValueError(f'Vincule de {minimo} a {MAXIMO_VINCULOS} evidências.')
    cache = {} if cache is None else cache
    result, seen, signatures = [], set(), set()
    for item in items:
        chosen = vinculo_ia.escolha(item)  # Onda 4 (B1): the finding chosen for an E-ID in several findings
        if isinstance(item, dict) and 'achado_id' in item:
            item = {k: v for k, v in item.items() if k != 'achado_id'}
        saved = _forma_salva(item)
        if saved:
            validar_vinculo_salvo(item)
        elif (not isinstance(item, dict) or set(item) - CAMPOS_VINCULO
                or not {'referencia', 'papel', 'justificativa'} <= set(item)):
            raise ValueError('Vínculo de evidência inválido.')
        support, nature = item.get('suporte', 'nao_revisado'), item.get('natureza', 'pendencia')
        _regras(item['papel'], support, nature, papeis)
        ref = referencia(item['referencia'])
        key = (chave(ref), item['papel'])
        if key in seen:
            raise ValueError('Evidência repetida com o mesmo papel.')
        seen.add(key)
        try:
            resolved = resolver(root, case, ref, cache)
        except ValueError:
            if saved and preservar_indisponiveis:
                result.append(deepcopy(item))
                continue
            raise
        document = resolved['documento']
        if saved and (document['documento_id'], document['original_sha256']) != (item['documento_id'], item['original_sha256']):
            raise ValueError('O original da evidência mudou desde o vínculo; vincule a evidência novamente.')
        signature = (_assinatura(resolved), item['papel'])
        if signature in signatures:
            raise ValueError('A mesma evidência já está vinculada com este papel (por outra revisão ou registro).')
        signatures.add(signature)
        result.append({'referencia': ref, 'papel': item['papel'], 'suporte': support, 'natureza': nature,
                       'justificativa': texto(item['justificativa'], 'Justificativa do vínculo', 2000),
                       'documento_id': document['documento_id'], 'original_sha256': document['original_sha256'],
                       'localizador': dict(resolved['localizador'])})
        choices = _ESCOLHAS.get()
        if chosen is not None and choices is not None:
            choices[key] = chosen
    return result


def conferir_vinculos(root, case, items, cache=None):
    """Resolve vínculos já salvos sem falhar a listagem; marca fontes indisponíveis."""
    cache = {} if cache is None else cache
    result = []
    for item in items:
        try:
            evidence = resolver(root, case, item['referencia'], cache)
            if evidence['documento']['original_sha256'] != item['original_sha256']:
                raise ValueError('O original da evidência mudou desde o vínculo.')
            result.append({**item, **vinculo_ia.leitura(root, case, item, cache), 'estado': 'conferida',
                           'evidencia': evidence})
        except ValueError as exc:
            result.append({**item, **vinculo_ia.leitura(root, case, item, cache), 'estado': 'indisponivel',
                           'erro': str(exc), 'evidencia': None})
    return result


def indice_fonte(value, items, field):
    """Índice opcional de um vínculo do próprio item (ex.: a fonte de uma data)."""
    if value is None:
        return None
    if type(value) is not int or not 0 <= value < len(items):
        raise ValueError(f'{field}: indique uma evidência vinculada a este item.')
    return value


def realocar_fontes(antigos, novos, campo):
    """Leva o índice de uma fonte em ``antigos`` ao índice da mesma evidência em ``novos``.

    Usado quando ``evidencias`` muda e um campo dependente (datas, identificadores,
    conferências) vem do estado atual: o índice segue a evidência, nunca a posição.
    """
    position = {identidade(x): i for i, x in enumerate(novos)}

    def mover(index):
        if index is None:
            return None
        key = identidade(antigos[index])
        if key not in position:
            raise ValueError(f'A evidência que documenta {campo} foi retirada ou mudou de papel; reenvie {campo}.')
        return position[key]
    return mover


def mesclar(data, atual, padroes):
    """Atualização parcial: campos ausentes mantêm o estado atual (ou o padrão, na criação)."""
    base = {k: v for k, v in (atual or padroes).items() if k in padroes}
    return {**base, **data}


def retirada(state):
    """Valida ``retirado``/``motivo_retirada``: retirar exige motivo; o histórico continua íntegro.

    Devolve ``(retirado, motivo)``; o motivo só é guardado enquanto o registro está retirado.
    """
    if type(state['retirado']) is not bool:
        raise ValueError('Indique se o registro está retirado.')
    reason = texto(state['motivo_retirada'], 'Motivo da retirada', 1000, vazio=True)
    if state['retirado'] and not reason:
        raise ValueError('Para retirar o registro, informe o motivo.')
    return state['retirado'], reason if state['retirado'] else ''


@contextmanager
def _trava(folder, nome):
    folder.mkdir(parents=True, exist_ok=True)
    lock = dentro(folder, '.trava')
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError(f'O quadro de {nome} está sendo salvo em outra janela ou um salvamento foi interrompido. '
                         'Tente novamente; se persistir, investigar a trava antes de removê-la.') from exc
    try:
        yield
    finally:
        lock.rmdir()


class Colecao:
    """Itens com histórico de eventos encadeados em ``casos/<caso>/quadros/<nome>``.

    ``normalizar(root, case, data, atual, identificador)`` devolve o estado editável validado.
    ``campos`` lista os campos editáveis aceitos no pedido. ``validar`` (opcional) é uma
    função pura ``validar(estado)`` que reaplica as regras do quadro a cada evento lido.
    """

    def __init__(self, nome, prefixo, campos, normalizar, validar=None, rotulo=None):
        self.nome, self.prefixo, self.campos, self.normalizar = nome, prefixo, set(campos), normalizar
        self.validar, self.rotulo = validar, rotulo or nome
        self.id = prefixo + r'[a-f0-9]{32}'

    def pasta(self, root, case):
        if not isinstance(case, str) or not re.fullmatch(lixeira.ID_CASO, case):
            raise ValueError('Selecione uma apuração para os quadros de evidência.')
        caderno._pasta(root, case)
        return dentro(root, f'casos/{case}/quadros/{self.nome}')

    def _evento(self, case, identifier, event, name, events, previous):
        sequence = len(events) + 1
        state = event.get('estado') if isinstance(event, dict) else None
        expected = self.campos | {'origem_autoria', 'atualizado_em_utc'}
        if (not isinstance(state, dict) or event.get('esquema') != ESQUEMA or event.get('caso_id') != case
                or event.get('colecao') != self.nome or event.get('id') != identifier
                or event.get('sequencia') != sequence or event.get('anterior_sha256') != previous
                or event.get('operacao') not in ('criar', 'atualizar') or (event['operacao'] == 'criar') != (not events)
                or not re.fullmatch(r'[a-f0-9]{32}', str(event.get('requisicao_id', '')))
                or name != f'{sequence:08d}_{event["requisicao_id"]}.json'
                or not re.fullmatch(HASH, str(event.get('solicitacao_sha256', '')))
                or set(state) != expected or state['origem_autoria'] not in caderno.ORIGENS_AUTORIA
                or event.get('origem_autoria') != state['origem_autoria']
                or (state['origem_autoria'] == caderno.AUTORIA_CONTA) != isinstance(event.get('conta_id'), str)
                or state['atualizado_em_utc'] != event.get('em_utc')):
            raise ValueError('Histórico do registro divergente; nenhuma atualização foi aplicada.')
        texto(event.get('autor'), 'Autor', 120)
        texto(event.get('observacao'), 'Observação', 5000, vazio=True)
        try:
            for link in state.get('evidencias', []):
                validar_vinculo_salvo(link)
            if self.validar:
                self.validar(state)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            detail = str(exc) if isinstance(exc, ValueError) else 'estado malformado'
            raise ValueError(f'Histórico do registro divergente ({detail}); nenhuma atualização foi aplicada.') from exc

    def detalhe(self, root, case, identifier):
        folder = self.pasta(root, case)
        if not isinstance(identifier, str) or not re.fullmatch(self.id, identifier):
            raise ValueError('Identidade do registro inválida.')
        records = dentro(folder, identifier)
        paths = sorted(records.glob('*.json')) if records.is_dir() else []
        if not paths:
            raise ValueError('Registro não encontrado nesta apuração.')
        events, previous, state = [], None, None
        for path in paths:
            try:
                event = ler_json(dentro(records, path.name))
            except (OSError, ValueError) as exc:
                raise ValueError('Histórico do registro divergente; nenhuma atualização foi aplicada.') from exc
            self._evento(case, identifier, event, path.name, events, previous)
            events.append(event); previous = sha256(path); state = event['estado']
        return {'caso': case, 'colecao': self.nome, 'id': identifier, 'sha256': previous, 'estado': state,
                'historico': events, 'divergente': False}

    @lixeira.leitura_da_exportacao
    def itens_da_conta(self, root, conta, casos):
        """Records of this collection the account created (its first event is of this account), for its own data
        export (E4b-2b of Contas; Viga, with the Maestro's consent): ``[{tipo: <collection>, caso, criado_em, id}]``,
        only in ``casos`` (those it reaches, as the caller says). Never the content or a name. Cases in the trash stay
        out. A record whose history cannot be read raises ValueError (whose actions it holds is unknown)."""
        casos, _ = lixeira.casos_da_exportacao(root, conta, casos)
        itens = []
        for case in casos:
            for record in self.listar(root, case):
                historico = record.get('historico')
                if record.get('divergente') or not historico:
                    raise ValueError(f'Registro ilegível em {self.rotulo}.')
                first = historico[0]
                if first.get('conta_id') == conta and first.get('origem_autoria') == caderno.AUTORIA_CONTA:
                    itens.append(lixeira.item_exportado(self.nome, case, first.get('em_utc'), record.get('id')))
        return itens

    def listar(self, root, case):
        """Todos os itens; um item com histórico divergente vem marcado, sem estado, e não derruba os demais."""
        folder = self.pasta(root, case)
        result, broken = [], []
        for path in sorted(folder.glob(self.prefixo + '*')) if folder.is_dir() else []:
            if path.is_dir() and re.fullmatch(self.id, path.name):
                try:
                    result.append(self.detalhe(root, case, path.name))
                except ValueError as exc:
                    broken.append({'caso': case, 'colecao': self.nome, 'id': path.name, 'sha256': None, 'estado': None,
                                   'historico': [], 'divergente': True, 'erro': str(exc)})
        result.sort(key=lambda item: (item['estado']['atualizado_em_utc'], item['id']), reverse=True)
        return result + broken

    def salvar(self, root, data, operation='criar', conta=None):
        fields = {'caso', 'requisicao_id', 'autor', 'observacao'} | self.campos
        if operation == 'atualizar':
            fields |= {'id', 'anterior_sha256'}
        if operation not in ('criar', 'atualizar') or not isinstance(data, dict) or set(data) - fields:
            raise ValueError('Campos inválidos no registro.')
        case = data.get('caso'); folder = self.pasta(root, case)
        rid = data.get('requisicao_id')
        if not isinstance(rid, str) or not re.fullmatch(r'[a-f0-9]{32}', rid):
            raise ValueError('Identidade de salvamento inválida.')
        identifier = self.prefixo + rid if operation == 'criar' else data.get('id')
        if not isinstance(identifier, str) or not re.fullmatch(self.id, identifier):
            raise ValueError('Registro inválido.')
        who = caderno.autoria(conta, data.get('autor'), 'Autor')
        note = texto(data.get('observacao', ''), 'Observação', 5000, vazio=True)
        request_hash = caderno._hash(caderno.com_conta({'operacao': operation, **data}, caderno.conta_valida(conta)))
        with _trava(folder, self.rotulo):
            records = dentro(folder, identifier)
            current = self.detalhe(root, case, identifier) if records.is_dir() else None
            if current:
                for event in current['historico']:
                    if event['requisicao_id'] == rid:
                        if event['solicitacao_sha256'] != request_hash:
                            raise ValueError('Esta tentativa já foi usada com outro conteúdo. Atualize o registro.')
                        return current
            if operation == 'criar' and current:
                raise ValueError('Registro já existe.')
            if operation == 'atualizar' and not current:
                raise ValueError('Registro não encontrado nesta apuração.')
            if operation == 'atualizar' and data.get('anterior_sha256') != current['sha256']:
                raise ValueError('O registro mudou. Atualize antes de salvar; seu formulário foi preservado.')
            editable = {k: deepcopy(data[k]) for k in self.campos if k in data}
            token = _ESCOLHAS.set({})
            try:
                state = self.normalizar(root, case, editable, deepcopy(current['estado']) if current else None, identifier)
                choices = _ESCOLHAS.get()
            finally:
                _ESCOLHAS.reset(token)
            links = state.get('evidencias') if isinstance(state.get('evidencias'), list) else []
            chosen = [choices.get(identidade(link)) if isinstance(link, dict) and 'referencia' in link else None
                      for link in links]
            if set(state) != self.campos:
                raise ValueError('Estado do registro incompleto.')
            if self.validar:
                self.validar(state)
            now = datetime.now(timezone.utc).isoformat()
            if self.nome in vinculo_ia.COLECOES and isinstance(state.get('evidencias'), list):
                vinculo_ia.registrar(root, case, state['evidencias'],
                                     current['estado'].get('evidencias', []) if current else [], who, now, chave, chosen)
            state.update(origem_autoria=who['origem_autoria'], atualizado_em_utc=now)
            event = {'esquema': ESQUEMA, 'caso_id': case, 'colecao': self.nome, 'id': identifier,
                     'sequencia': len(current['historico']) + 1 if current else 1,
                     'anterior_sha256': current['sha256'] if current else None, 'operacao': operation,
                     'requisicao_id': rid, 'solicitacao_sha256': request_hash, 'autor': who['autor'],
                     'origem_autoria': who['origem_autoria'],
                     **({'conta_id': who['conta_id']} if 'conta_id' in who else {}),
                     'observacao': note, 'em_utc': now, 'estado': state}
            filename = f'{event["sequencia"]:08d}_{rid}.json'
            # O evento passa pelas mesmas regras da leitura antes de gravado: nada salvo fica divergente.
            self._evento(case, identifier, event, filename, current['historico'] if current else [],
                         current['sha256'] if current else None)
            folder.mkdir(parents=True, exist_ok=True)
            with pasta_preparacao(folder, '.preparacao_') as staging:
                staged = staging / 'evento.json'; escrever_json(staged, event, exclusivo=True)
                if current:
                    staged.rename(dentro(records, filename))
                else:
                    staged_folder = staging / identifier; staged_folder.mkdir()
                    staged.rename(staged_folder / filename); staged_folder.rename(records)
            return self.detalhe(root, case, identifier)


# The evidence boards built on Colecao (the newsroom check, conferencia_redacao, gives its own items).
QUADROS = ('entrevistas', 'hipoteses', 'linha_tempo', 'mapa_relacoes', 'tabelas_apuracao')


@lixeira.leitura_da_exportacao
def itens_da_conta(root, conta, casos):
    """The records the account created in every evidence board (``Colecao.itens_da_conta`` of each), for its own
    data export (E4b-2b of Contas). The board modules are imported here, at call time: they import this one."""
    import importlib
    itens, vistas = [], set()
    for nome in QUADROS:
        modulo = importlib.import_module(nome)
        for colecao in (v for v in vars(modulo).values() if isinstance(v, Colecao)):
            if colecao.nome not in vistas:  # a board imported by another module counts once
                vistas.add(colecao.nome)
                itens.extend(colecao.itens_da_conta(root, conta, casos))
    return itens
