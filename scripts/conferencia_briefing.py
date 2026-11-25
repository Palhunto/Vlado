"""Conferência do briefing contra os achados, sem modelo, antes de publicar a síntese (L5 da auditoria editorial).

O briefing só pode dizer o que os achados revisados dizem. Cada frase factual do briefing precisa estar coberta
por um achado revisado, com localizador: a marca ``[A001@v1]`` (ou, na lista "Outros achados sustentados", o
``A001 v1`` por extenso) ou um ``[fonte:REFERENCIA]`` de uma evidência ligada a um achado, na própria frase ou no
mesmo parágrafo ou item de lista. Coberta a frase, ela é comparada, por regras fixas, com a redação desses achados
e com os trechos das evidências deles. A síntese é recusada, com o motivo de cada frase, quando:

- ``afirmacao_sem_achado``: a frase traz número, data ou valor (em qualquer seção, também numa frase negativa) ou
  um quantificador forte, e nenhum achado a cobre;
- ``fonte_sem_achado``: o ``[fonte:...]`` é uma leitura da rodada que não sustenta nenhum achado publicado;
- ``numero_fora_do_achado``: número, data ou valor que não está na redação nem nos trechos dos achados citados
  (o resultado de uma conta escrita por extenso, depois do ``=``, é derivado e não precisa estar);
- ``quantificador_mais_forte``: "tudo", "todos", "integralmente", "sempre"... sem correspondente no achado;
- ``ressalva_omitida``: o achado diz que algo é parcial ("parcialmente", "em parte") e nenhuma frase que o cita
  conserva a ressalva. É a falha "o Acórdão X reformou tudo" quando a reforma foi parcial.

Número sempre precisa de achado, em qualquer seção e também numa frase negativa: "não houve licitação para o
contrato de R$ 5 milhões" afirma o valor do contrato (B2 da Coruja à L5). Só o quantificador forte fica livre numa
frase de limite (não localizado, não se aplica, pendência, insuficiência) e na seção de lacunas e diligências, que
declaram o que falta e não um fato; se citarem um achado, as regras valem igual. Números que já estão na pergunta
e contagens pequenas (inteiros até 10, sem unidade) não contam como fato novo.

Quantificador é só o de fato (todos, tudo, sempre, nunca, nenhum, integralmente...): adjetivos como "inteiro teor"
e "nome completo" não dizem alcance e não entram na lista.

A conferência vale para as rodadas congeladas com os prompts 1.5.0 ou depois, nos dois modos de instrução; uma
rodada legada (até 1.4.1), inclusive a retomada de uma interrompida, segue sem ela (decisão do Maestro, R3).

Causalidade e certeza onde o achado atribui a alguém (as regras da Conferência da redação) ficam como alerta, sem
barrar: o falso positivo ali é comum e travaria a pergunta.

Os limites conhecidos estão nos testes: as regras são lexicais e não leem o sentido. Uma frase de limite pode
carregar um fato junto ("o contrato foi pago, mas o aditivo não foi localizado"); a revisão humana continua.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
import unicodedata

import comparador
import conferencia_redacao

LIMITE_MOTIVOS = 6
# Os da Conferência da redação mais os que faltavam para o texto de síntese ("tudo", "integralmente"...). Só
# quantificadores e advérbios de alcance: um adjetivo solto ("inteiro teor", "nome completo", "valor integral")
# não diz alcance, e recusá-lo travaria a frase certa.
QUANTIFICADORES = tuple(dict.fromkeys(conferencia_redacao._QUANTIFICADORES + (
    'tudo', 'integralmente', 'na integra', 'por inteiro', 'totalidade', 'por completo', 'plenamente',
    'unanimemente', 'por unanimidade', 'all', 'every', 'everything', 'entirely', 'fully', 'totally', 'wholly',
    'always', 'never', 'none', 'nobody', 'completely', 'unanimously')))
_RE_QUANTIFICADOR = re.compile(r'\b(?:' + '|'.join(re.escape(q) for q in sorted(QUANTIFICADORES, key=len, reverse=True)) + r')\b')
_RE_PARCIAL = re.compile(r'\b(?:parcial|parciais|parcialmente|em parte|partial|partially|in part)\b')
_RE_LIMITE = re.compile(
    r'\bnao (?:foi|foram|ha|houve|se aplica|consta|constam|aparece|aparecem|traz|trazem|permite|permitem|'
    r'localiz|encontr|identific|esta|estao)|\b(?:insuficien|pendenc|pendente|lacuna|nao localizad|sem (?:suporte|'
    r'evidencia|achado|registro|documento|fonte))|\bnot (?:found|located|applicable|available|apply)|'
    r'\bno (?:evidence|record|support)\b|\binsufficien|\bpending\b|\bgaps?\b')
_RE_SECAO_LIVRE = re.compile(r'lacuna|diligenc|pendenc|limite|limitac|gaps?\b|follow|next step|limitation')
_RE_MARCA = re.compile(r'\[(A[0-9]{3,})@v([1-9][0-9]*)\]')
_RE_FONTE = re.compile(r'\[fonte:([^\]\n]+)\]')
_RE_POR_EXTENSO = re.compile(r'(?<![\w@\[])(A[0-9]{3,})[ \t]+v([1-9][0-9]*)(?!\d)')
# A heading, a bold line or a short label ("Outro lado:"), up to five words, on a line of its own.
_RE_TITULO = re.compile(r'^\s*(?:#{1,6}\s+.*|(?:\*\*|__)[^*_\n]+(?:\*\*|__):?|(?:\*\*|__)?[^\W\d][^.!?:\n]{0,48}:(?:\*\*|__)?)\s*$')
_RE_ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)]|\|)\s*')
_MULTIPLICADORES = (('trilh', 10 ** 12), ('trillion', 10 ** 12), ('bilh', 10 ** 9), ('billion', 10 ** 9),
                    ('milh', 10 ** 6), ('million', 10 ** 6), ('mil', 10 ** 3), ('thousand', 10 ** 3))
_DEPOIS = re.compile(r'\s*(trilh\w*|bilh\w*|milh\w*|mil\b|thousand|million|billion|trillion|bi\b|mi\b|tri\b)', re.I)


def _plano(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c)).casefold()


def _sem_marcas(texto):
    return _RE_POR_EXTENSO.sub(' ', _RE_FONTE.sub(' ', _RE_MARCA.sub(' ', texto)))


def _multiplicador(mark, texto):
    unidade = _plano(mark.get('unidade') or '')
    for nome, fator in _MULTIPLICADORES:
        if nome in unidade:
            return fator
    seguinte = _DEPOIS.match(texto, mark['posicao'] + len(mark['bruto']))
    if seguinte:
        palavra = _plano(seguinte.group(1))
        return next((f for n, f in _MULTIPLICADORES if palavra.startswith(n)),
                    {'bi': 10 ** 9, 'mi': 10 ** 6, 'tri': 10 ** 12}.get(palavra, 1))
    return 1


def valores(texto):
    """[(chave, bruto, posição)] dos números, datas e valores, comparáveis entre formatos ("8,75 milhões" e
    "8.750.000,00" têm a mesma chave; "2024" casa com qualquer data de 2024)."""
    result = []
    for mark in comparador.marcas(texto):
        if mark['tipo'] == 'data':
            result.append((('data', mark['normalizado']), mark['bruto'], mark['posicao']))
        elif mark['tipo'] in ('numero', 'valor_monetario', 'percentual'):
            try:
                valor = Decimal(mark['valor']) * _multiplicador(mark, texto)
            except (InvalidOperation, TypeError):
                continue
            kind = 'pct' if mark['tipo'] == 'percentual' else 'qtd'
            result.append(((kind, valor.normalize()), mark['bruto'], mark['posicao']))
    return result


def _coberto(chave, conhecidas):
    if chave in conhecidas:
        return True
    kind, valor = chave
    datas = [v for k, v in conhecidas if k == 'data']
    if kind == 'data':  # "março de 2025" diante de "2025-03-03"
        return any(d.startswith(valor) for d in datas)
    if kind == 'qtd' and valor == valor.to_integral_value() and 1000 <= valor <= 2999:
        return any(d.startswith(str(int(valor))) for d in datas)  # o ano de uma data citada
    return False


def _contagem_pequena(chave, bruto):
    kind, valor = chave
    return kind == 'qtd' and re.fullmatch(r'\d{1,2}', bruto.strip()) is not None and valor <= 10


def _blocos(texto):
    """Parágrafos, itens de lista e linhas de tabela, cada um com o título da seção em que está."""
    blocos, atual, titulo = [], [], ''

    def fechar():
        if atual:
            blocos.append((titulo, '\n'.join(atual)))
            atual.clear()
    for linha in texto.splitlines():
        if not linha.strip():
            fechar()
        elif (_RE_TITULO.match(linha) and len(linha.split()) <= 6 and not _RE_MARCA.search(linha)
              and not _RE_FONTE.search(linha)):
            fechar()
            titulo = linha.strip().strip('#*_: ')
        elif _RE_ITEM.match(linha):
            fechar()
            atual.append(linha)
            fechar()
        else:
            atual.append(linha)
    fechar()
    return blocos


def _citacoes(texto, lista):
    marcas = {(a, int(v)) for a, v in _RE_MARCA.findall(texto)}
    if lista:
        marcas |= {(a, int(v)) for a, v in _RE_POR_EXTENSO.findall(texto)}
    return marcas, set(_RE_FONTE.findall(texto))


def _resumo(frase):
    frase = ' '.join(frase.split())
    return frase if len(frase) <= 160 else frase[:157] + '...'


def aplica(instrucoes):
    """A conferência vale para rodadas congeladas com os prompts 1.5.0 ou depois (R3); a legada segue sem ela."""
    try:
        versao = tuple(int(x) for x in str((instrucoes or {}).get('versao_prompts') or '').split('.'))
    except ValueError:
        return False
    return len(versao) == 3 and versao >= (1, 5, 0)


def conferir(texto, data, evidence_refs, pergunta=''):
    """{'recusas': [...], 'alertas': [...]} do briefing ``texto`` contra os achados de ``data`` (a revisão que a
    síntese vai publicar, já com os destinos); ``evidence_refs`` liga cada E-ID à referência que o modelo cita."""
    from registros_achados import secao_fora_do_briefing
    versoes = {(c['id'], v['versao']): v for c in data['achados'] for v in c['versoes']}
    atuais = {c['id']: c['versoes'][-1]['versao'] for c in data['achados']}
    evidencias = {e['id']: e for e in data['evidencias']}
    por_referencia = {}
    for v in data['vinculos']:
        if atuais.get(v['achado_id']) == v['versao']:
            por_referencia.setdefault(evidence_refs.get(v['evidencia_id']), set()).add((v['achado_id'], v['versao']))

    def trechos(chave, papeis=None):
        result = []
        for v in data['vinculos']:
            if (v['achado_id'], v['versao']) == chave and (papeis is None or v['papel'] in papeis):
                e = evidencias.get(v['evidencia_id']) or {}
                result += [e.get('trecho') or '', (e.get('localizador') or {}).get('descricao') or '']
        return [t for t in result if t]

    da_pergunta = {k for k, _, _ in valores(pergunta or '')}
    recusas, alertas, citadas_com_ressalva, frases_por_achado = [], [], set(), {}
    principal, lista = secao_fora_do_briefing(texto)
    partes = [(False, b) for b in _blocos(principal)] + [(True, b) for b in _blocos(lista or '')]
    for na_lista, (titulo, bloco) in partes:
        marcas, fontes = _citacoes(bloco, na_lista)
        for ref in sorted(fontes - set(por_referencia)):
            recusas.append({'tipo': 'fonte_sem_achado', 'frase': _resumo(bloco),
                            'motivo': f'[fonte:{ref[:16]}...] não sustenta nenhum achado revisado desta rodada; a '
                                      'síntese não acrescenta fatos novos: cite o achado ou retire a frase.'})
        achados = {k for k in marcas if k in versoes}
        for ref in fontes:
            achados |= por_referencia.get(ref, set())
        livre = bool(_RE_SECAO_LIVRE.search(_plano(titulo)))
        for item in conferencia_redacao.dividir(bloco):
            frase = item['texto']
            limpa = _sem_marcas(frase)
            plano = _plano(limpa)
            numeros = [(k, b, p) for k, b, p in valores(limpa)
                       if k not in da_pergunta and not _contagem_pequena(k, b)]
            fortes = [m.group(0) for m in _RE_QUANTIFICADOR.finditer(plano)]
            if _RE_PARCIAL.search(plano):
                citadas_com_ressalva |= achados
            for chave in achados:
                frases_por_achado.setdefault(chave, []).append(frase)
            if not achados:
                # A number is always a fact (B2): also in a negative sentence and in the gaps section.
                forte_livre = livre or _RE_LIMITE.search(plano)
                if numeros or (fortes and not forte_livre):
                    recusas.append({'tipo': 'afirmacao_sem_achado', 'frase': _resumo(frase),
                                    'motivo': 'a frase afirma ' + (f'"{numeros[0][1]}"' if numeros else f'"{fortes[0]}"')
                                              + ' sem achado revisado: ponha na frase ou no parágrafo a marca [A…@v…] '
                                                'do achado incluído que a sustenta, ou retire a frase'
                                              + (' (número precisa de achado mesmo numa frase negativa ou de lacuna; '
                                                 'cite a lei pelo nome, sem número).' if numeros else '.')})
                continue
            redacoes = [versoes[k]['redacao'] for k in achados]
            conhecidas_texto = redacoes + [t for k in achados for t in trechos(k)]
            conhecidas = {k for t in conhecidas_texto for k, _, _ in valores(t)}
            igual = limpa.find('=')
            nomes = ', '.join(f'{a} v{v}' for a, v in sorted(achados))
            for chave, bruto, posicao in numeros:
                if igual != -1 and posicao > igual:
                    continue  # resultado de conta escrita por extenso
                if not _coberto(chave, conhecidas):
                    recusas.append({'tipo': 'numero_fora_do_achado', 'frase': _resumo(frase),
                                    'motivo': f'"{bruto}" não está na redação nem nos trechos de {nomes}. Use o valor '
                                              'como o achado o registra; um valor recalculado vem com a conta '
                                              '(operandos = resultado).'})
            suporte = [_plano(t) for t in redacoes + [t for k in achados for t in trechos(k, ('suporte',))]]
            for forte in dict.fromkeys(fortes):
                if not any(re.search(r'\b' + re.escape(forte) + r'\b', s) for s in suporte):
                    parcial = [f'{a} v{v}' for a, v in sorted(achados) if _RE_PARCIAL.search(_plano(versoes[(a, v)]['redacao']))]
                    recusas.append({'tipo': 'quantificador_mais_forte', 'frase': _resumo(frase),
                                    'motivo': f'"{forte}" é mais forte que {nomes}'
                                              + (f', que registra alcance parcial ({", ".join(parcial)})' if parcial else '')
                                              + '. Escreva no alcance do achado.'})
            atribuida = any(versoes[k]['natureza'] == 'alegacao_atribuida' for k in achados)
            for sinal in conferencia_redacao.sinais(limpa, [t for k in achados for t in trechos(k, ('suporte',))],
                                                    atribuida=atribuida):
                if sinal['tipo'] in ('causalidade_sem_suporte', 'certeza_sem_atribuicao'):
                    alertas.append({'tipo': sinal['tipo'], 'frase': _resumo(frase), 'achados': sorted(achados),
                                    'motivo': sinal['detalhe']})
    for chave, frases in sorted(frases_por_achado.items()):
        redacao = _plano(versoes[chave]['redacao'])
        if _RE_PARCIAL.search(redacao) and chave not in citadas_com_ressalva:
            recusas.append({'tipo': 'ressalva_omitida', 'frase': _resumo(frases[0]),
                            'motivo': f'{chave[0]} v{chave[1]} registra alcance parcial '
                                      f'("{_RE_PARCIAL.search(redacao).group(0)}"), e nenhuma frase que o cita '
                                      'conserva a ressalva. Diga o que foi parcial, como o achado diz.'})
    return {'recusas': recusas, 'alertas': alertas}


def mensagem(resultado):
    """Texto da recusa para o modelo refazer a etapa: um motivo por frase, até LIMITE_MOTIVOS."""
    recusas = resultado['recusas']
    linhas = [f'{n}) "{r["frase"]}": {r["motivo"]}' for n, r in enumerate(recusas[:LIMITE_MOTIVOS], 1)]
    if len(recusas) > LIMITE_MOTIVOS:
        linhas.append(f'... e mais {len(recusas) - LIMITE_MOTIVOS} frase(s) com o mesmo problema.')
    return ('Conferência do briefing contra os achados (regras fixas, sem modelo): o briefing diz o que os achados '
            'revisados não dizem. Refaça a síntese só com o que os achados sustentam. ' + ' '.join(linhas))
