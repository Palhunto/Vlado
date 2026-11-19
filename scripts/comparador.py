"""Comparador de documentos e declarações, com destaque de valores, datas e contexto.

Compara texto já autorizado: trechos de evidências resolvidas ou o texto (nativo ou
OCR) de documentos congelados numa rodada. A comparação é técnica e literal; não
decide qual versão está correta e não substitui a conferência no original.
"""
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
import difflib
import re

import evidencias as ev
import lixeira
from indice_sqlite import _adaptar, _entradas, caminho_rodada
from linha_tempo import data_parcial

MESES = {'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 'abril': 4, 'maio': 5, 'junho': 6, 'julho': 7,
         'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12}
_MES = '|'.join(sorted(MESES, key=len, reverse=True))
DATAS = [
    (re.compile(r'\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b'), lambda m: (m[3], m[2], m[1])),
    (re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b'), lambda m: (m[1], m[2], m[3])),
    (re.compile(r'\b(\d{1,2})º?\s+de\s+(' + _MES + r')\s+de\s+(\d{4})\b', re.I),
     lambda m: (m[3], MESES[m[2].casefold()], m[1])),
]
# Datas sem dia: "março de 2024" e "03/2024" viram data parcial AAAA-MM.
DATAS_PARCIAIS = [
    (re.compile(r'\b(' + _MES + r')\s+de\s+(\d{4})\b', re.I), lambda m: (m[2], MESES[m[1].casefold()])),
    (re.compile(r'(?<![\d/.])(\d{1,2})/(\d{4})\b'), lambda m: (m[2], m[1])),
]
# Lista fechada de unidades: grafia → (unidade canônica, dimensão). Sem conversão automática.
UNIDADES = {
    'mg': ('mg', 'massa'), 'g': ('g', 'massa'), 'grama': ('g', 'massa'), 'gramas': ('g', 'massa'),
    'kg': ('kg', 'massa'), 'quilo': ('kg', 'massa'), 'quilos': ('kg', 'massa'),
    'quilograma': ('kg', 'massa'), 'quilogramas': ('kg', 'massa'),
    't': ('t', 'massa'), 'ton': ('t', 'massa'), 'tonelada': ('t', 'massa'), 'toneladas': ('t', 'massa'),
    'mm': ('mm', 'comprimento'), 'cm': ('cm', 'comprimento'), 'm': ('m', 'comprimento'),
    'metro': ('m', 'comprimento'), 'metros': ('m', 'comprimento'), 'km': ('km', 'comprimento'),
    'quilômetro': ('km', 'comprimento'), 'quilômetros': ('km', 'comprimento'),
    'quilometro': ('km', 'comprimento'), 'quilometros': ('km', 'comprimento'),
    'm²': ('m²', 'area'), 'm2': ('m²', 'area'), 'metros quadrados': ('m²', 'area'),
    'km²': ('km²', 'area'), 'km2': ('km²', 'area'), 'ha': ('ha', 'area'), 'hectare': ('ha', 'area'),
    'hectares': ('ha', 'area'),
    'ml': ('ml', 'volume'), 'l': ('l', 'volume'), 'litro': ('l', 'volume'), 'litros': ('l', 'volume'),
    'm³': ('m³', 'volume'), 'm3': ('m³', 'volume'), 'metros cúbicos': ('m³', 'volume'),
    'mil': ('mil', 'escala'), 'milhão': ('milhão', 'escala'), 'milhao': ('milhão', 'escala'),
    'milhões': ('milhão', 'escala'), 'milhoes': ('milhão', 'escala'), 'bilhão': ('bilhão', 'escala'),
    'bilhao': ('bilhão', 'escala'), 'bilhões': ('bilhão', 'escala'), 'bilhoes': ('bilhão', 'escala'),
}
_UNIDADE = '|'.join(re.escape(u).replace(r'\ ', r'\s+') for u in sorted(UNIDADES, key=len, reverse=True))
VALOR = re.compile(r'(?P<moeda>R\$|US\$|€)?\s?(?<![\w.,])'
                   r'(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+\.\d+|\d+)'
                   r'(?:(?P<pct>\s?%)|\s?(?P<unidade>(?i:' + _UNIDADE + r'))(?![\w²³])|(?!\w))')
TIPOS_DATA_MARCA = ('data', 'data_invalida')
LIMITE_TEXTO = 400000
LIMITE_ALTERACOES = 300
CONTEXTO = 8


def _numero(raw):
    """pt-BR: ponto separa milhar e vírgula separa decimal; '12.5' isolado é decimal."""
    if ',' in raw or re.fullmatch(r'\d{1,3}(\.\d{3})+', raw):
        raw = raw.replace('.', '').replace(',', '.')
    try:
        return format(Decimal(raw).normalize(), 'f')
    except InvalidOperation:
        return raw


def _livre(taken, start, end):
    return not any(start < r.stop and r.start < end for r in taken)


def _data(found, m, value, precision, valid):
    found.append({'tipo': 'data' if valid else 'data_invalida', 'bruto': m[0],
                  'normalizado': value if valid else m[0], 'precisao': precision if valid else None,
                  'posicao': m.start(), 'fim': m.end()})


def marcas(text):
    """Datas e valores encontrados no texto, normalizados para comparação.

    Datas inexistentes (31/02/2024) viram ``data_invalida``, sem normalização. Números
    levam a unidade observada logo depois deles (lista fechada), sem conversão.
    """
    found, taken = [], []
    for pattern, parts in DATAS:
        for m in pattern.finditer(text):
            if not _livre(taken, m.start(), m.end()):
                continue
            year, month, day = (int(x) for x in parts(m))
            try:
                value, valid = date(year, month, day).isoformat(), True
            except ValueError:
                value, valid = None, False
            _data(found, m, value, 'dia', valid)
            taken.append(range(m.start(), m.end()))
    for pattern, parts in DATAS_PARCIAIS:
        for m in pattern.finditer(text):
            if not _livre(taken, m.start(), m.end()):
                continue
            year, month = parts(m)
            value = f'{int(year):04d}-{int(month):02d}'
            try:
                precision, valid = data_parcial(value), True
            except ValueError:
                precision, valid = None, False
            _data(found, m, value, precision, valid)
            taken.append(range(m.start(), m.end()))
    for m in VALOR.finditer(text):
        if not _livre(taken, m.start('num'), m.end('num')):
            continue
        number = _numero(m['num'])
        unit, dimension = UNIDADES[re.sub(r'\s+', ' ', m['unidade']).casefold()] if m['unidade'] else (None, None)
        if m['pct']:
            kind, unit, dimension, normal = 'percentual', '%', 'percentual', number + '%'
        elif m['moeda']:
            kind, dimension = 'valor_monetario', 'moeda'
            normal = f'{m["moeda"]} {number}' + (' ' + unit if unit else '')
            unit = m['moeda'] + (' ' + unit if unit else '')
        else:
            kind, normal = 'numero', number + (' ' + unit if unit else '')
        found.append({'tipo': kind, 'bruto': m[0].strip(), 'posicao': m.start('moeda' if m['moeda'] else 'num'),
                      'fim': m.end(), 'normalizado': normal, 'valor': number, 'unidade': unit, 'dimensao': dimension})
    return sorted(found, key=lambda x: x['posicao'])


def calculo(before, after):
    """Diferença (b − a) entre o único valor de cada lado, só com unidades idênticas; senão, o motivo."""
    return _calculo(marcas(before), marcas(after))


def _calculo(ma, mb):
    ma = [x for x in ma if x['tipo'] not in TIPOS_DATA_MARCA]
    mb = [x for x in mb if x['tipo'] not in TIPOS_DATA_MARCA]
    if not ma or not mb:
        return None
    result = {'operacao': 'b - a', 'a': [x['normalizado'] for x in ma], 'b': [x['normalizado'] for x in mb],
              'unidade': None, 'diferenca': None, 'motivo': None}
    if len(ma) != 1 or len(mb) != 1:
        return {**result, 'motivo': 'pareamento_ambiguo'}
    a, b = ma[0], mb[0]
    if (a['tipo'], a['unidade'], a['dimensao']) != (b['tipo'], b['unidade'], b['dimensao']):
        return {**result, 'motivo': 'unidades_incompativeis'}
    difference = Decimal(b['valor']) - Decimal(a['valor'])
    unit = 'pontos percentuais' if a['tipo'] == 'percentual' else a['unidade']
    return {**result, 'unidade': unit, 'diferenca': format(difference.normalize(), 'f') if difference else '0'}


def _resumo_marcas(a, b):
    ca = Counter((x['tipo'], x['normalizado']) for x in (marcas(a) if isinstance(a, str) else a))
    cb = Counter((x['tipo'], x['normalizado']) for x in (marcas(b) if isinstance(b, str) else b))
    form = lambda counter: [{'tipo': t, 'normalizado': v, 'ocorrencias': n} for (t, v), n in sorted(counter.items())]
    return {'somente_a': form(ca - cb), 'somente_b': form(cb - ca), 'comuns': form(ca & cb)}


def _classe(before, after):
    return _classe_marcas(marcas(before), marcas(after))


def _classe_marcas(ma, mb):
    ca = Counter((x['tipo'], x['normalizado']) for x in ma)
    cb = Counter((x['tipo'], x['normalizado']) for x in mb)
    # Só as marcas que mudaram decidem a classe: uma data repetida nos dois lados não é divergência de data.
    kinds = {t for t, _ in (ca - cb) + (cb - ca)}
    dates = set(TIPOS_DATA_MARCA)
    if ca != cb:
        if kinds & dates and not kinds - dates:
            return 'data'
        if kinds - dates and not kinds & dates:
            return 'valor'
        return 'valor_e_data'
    return 'conteudo'


def comparar_textos(a, b):
    """Diferenças por palavra, com posição, contexto dos dois lados e classificação.

    Em substituições com um valor de cada lado, ``calculo`` traz a diferença b − a só quando
    tipo e unidade são idênticos; caso contrário, ``diferenca`` é nula e ``motivo`` explica.
    """
    if not isinstance(a, str) or not isinstance(b, str) or len(a) + len(b) > LIMITE_TEXTO:
        raise ValueError('Textos ausentes ou grandes demais para comparar; compare trechos menores.')
    words_a, words_b = list(re.finditer(r'\S+', a)), list(re.finditer(r'\S+', b))
    ta, tb = [w[0] for w in words_a], [w[0] for w in words_b]
    marks_a, marks_b = marcas(a), marcas(b)

    def touched(marks, words, i, j):
        # Marcas que se sobrepõem às palavras alteradas: "10 kg" → "10 t" muda só "kg", mas o valor muda.
        if i >= j:
            return []
        start, end = words[i].start(), words[j - 1].end()
        return [x for x in marks if x['posicao'] < end and start < x['fim']]
    matcher = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    segments, changes = [], []
    names = {'equal': 'igual', 'delete': 'removido', 'insert': 'inserido', 'replace': 'substituido'}
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        before, after = ' '.join(ta[i1:i2]), ' '.join(tb[j1:j2])
        segments.append({'operacao': names[op], 'a': before, 'b': after})
        if op != 'equal' and len(changes) < LIMITE_ALTERACOES:
            ma, mb = touched(marks_a, words_a, i1, i2), touched(marks_b, words_b, j1, j2)
            changes.append({'operacao': names[op], 'classe': _classe_marcas(ma, mb), 'a': before, 'b': after,
                            'posicao_a': {'palavra_inicio': i1, 'palavra_fim': i2},
                            'posicao_b': {'palavra_inicio': j1, 'palavra_fim': j2},
                            'contexto_a': {'antes': ' '.join(ta[max(0, i1 - CONTEXTO):i1]),
                                           'depois': ' '.join(ta[i2:i2 + CONTEXTO])},
                            'contexto_b': {'antes': ' '.join(tb[max(0, j1 - CONTEXTO):j1]),
                                           'depois': ' '.join(tb[j2:j2 + CONTEXTO])},
                            'calculo': _calculo(ma, mb) if op == 'replace' else None})
    return {'identicos': ta == tb, 'semelhanca': round(matcher.ratio(), 4), 'segmentos': segments,
            'alteracoes': changes, 'truncado': sum(1 for s in segments if s['operacao'] != 'igual') > LIMITE_ALTERACOES,
            'marcas': _resumo_marcas(marks_a, marks_b)}


def comparar_evidencias(root, case, ref_a, ref_b):
    """Compara os trechos de duas evidências do mesmo caso (declarações, versões, respostas)."""
    cache = {}
    a, b = ev.resolver(root, case, ref_a, cache), ev.resolver(root, case, ref_b, cache)
    if not (a['trecho'] or '').strip() or not (b['trecho'] or '').strip():
        raise ValueError('Evidência sem trecho textual (leitura visual); compare no original.')
    return {'caso': case, 'a': a, 'b': b, **comparar_textos(a['trecho'], b['trecho']),
            'aviso': 'Comparação literal de trechos; diferenças não indicam qual fonte está correta.'}


def _linhas_documento(run, case, rodada, document_id):
    _, descriptor = _entradas(run, case, rodada)
    sources = [s for s in descriptor['fontes'] if s['documento_id'] == document_id]
    if not sources:
        raise ValueError('Documento não pertence a esta rodada.')
    original = next((s for s in sources if s['tipo'] == 'original'), None)
    if original is None:
        raise ValueError('Documento sem original congelado nesta rodada.')
    for source in sorted(sources, key=lambda s: s['tipo'] != 'derivado'):
        _, method, units = _adaptar(run / 'entradas' / source['arquivo'], document_id, original['sha256'], source['tipo'])
        lines = [(u['pagina_pdf'], n, t) for u in units if u['estado'] == 'com_texto' for n, t in u['linhas']]
        if lines:
            gaps = [u['pagina_pdf'] for u in units if u['estado'] != 'com_texto']
            return {'documento_id': document_id, 'original_sha256': original['sha256'], 'fonte': source['arquivo'],
                    'fonte_sha256': source['sha256'], 'tipo_fonte': source['tipo'], 'metodo': method,
                    'paginas_sem_texto': gaps}, lines
    raise ValueError(f'{document_id} não tem texto utilizável nesta rodada; compare no original.')


def _loc(lines, start, end):
    if start >= end:
        return None
    first, last = lines[start], lines[end - 1]
    return {'pagina_pdf': first[0], 'linha_inicio': first[1], 'pagina_pdf_fim': last[0], 'linha_fim': last[1]}


def comparar_documentos(root, case, rodada, doc_a, doc_b, *, contexto=2):
    """Compara linha a linha o texto autorizado de dois documentos de uma rodada congelada."""
    if type(contexto) is not int or not 0 <= contexto <= 10:
        raise ValueError('Contexto deve ter de 0 a 10 linhas.')
    if doc_a == doc_b:
        raise ValueError('Escolha dois documentos diferentes.')
    lixeira.conferir_disponivel(root, case, rodada=rodada)
    run = caminho_rodada(root, case, rodada)
    info_a, la = _linhas_documento(run, case, rodada, doc_a)
    info_b, lb = _linhas_documento(run, case, rodada, doc_b)
    if sum(len(t) for *_, t in la + lb) > LIMITE_TEXTO * 5:
        raise ValueError('Documentos grandes demais para comparar inteiros; compare evidências selecionadas.')
    normal = lambda lines: [re.sub(r'\s+', ' ', t).strip() for *_, t in lines]
    na, nb = normal(la), normal(lb)
    matcher = difflib.SequenceMatcher(None, na, nb, autojunk=False)
    names = {'delete': 'removido', 'insert': 'inserido', 'replace': 'substituido'}
    changes, total = [], 0
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            continue
        total += 1
        if len(changes) >= LIMITE_ALTERACOES:
            continue
        before, after = '\n'.join(na[i1:i2]), '\n'.join(nb[j1:j2])
        detail = None
        if op == 'replace':
            try:
                detail = comparar_textos(before, after)
            except ValueError:  # bloco grande demais para o detalhe por palavra; a alteração da linha continua
                detail = None
        changes.append({'operacao': names[op], 'classe': _classe(before, after), 'a': before, 'b': after,
                        'localizador_a': _loc(la, i1, i2), 'localizador_b': _loc(lb, j1, j2),
                        'contexto_a': [{'pagina_pdf': p, 'linha': n, 'texto': t}
                                       for p, n, t in la[max(0, i1 - contexto):i1] + la[i2:i2 + contexto]],
                        'contexto_b': [{'pagina_pdf': p, 'linha': n, 'texto': t}
                                       for p, n, t in lb[max(0, j1 - contexto):j1] + lb[j2:j2 + contexto]],
                        'calculo': calculo(before, after) if op == 'replace' else None,
                        'palavras': detail and {k: detail[k] for k in ('segmentos', 'alteracoes')}})
    return {'caso': case, 'rodada': rodada, 'a': info_a, 'b': info_b, 'identicos': na == nb,
            'semelhanca': round(matcher.ratio(), 4), 'alteracoes': changes, 'total_alteracoes': total,
            'truncado': total > len(changes), 'marcas': _resumo_marcas('\n'.join(na), '\n'.join(nb)),
            'aviso': 'Comparação do texto extraído (nativo ou OCR); conferir no original nomes, valores e tabelas.'}
