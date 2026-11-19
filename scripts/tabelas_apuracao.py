"""Tabelas de apuração conferíveis: cada célula aponta para a evidência que a sustenta.

Uma tabela tem colunas tipadas (``texto``, ``data``, ``monetario`` com moeda e
``numero`` com unidade) e linhas de células. Cada célula guarda o valor, a fonte (o
índice de um vínculo de evidência da própria tabela, no contrato do Core, como
``datas[].fonte`` na linha do tempo) e o estado: ``extraido`` (valor com fonte),
``corrigido_manual`` (valor ou fonte alterados por uma pessoa, com justificativa) ou
``pendente`` (sem fonte ou sem valor). O armazenamento é o do Core
(``evidencias.Colecao``): cada salvamento grava um evento novo, encadeado por hash, e a
correção de uma célula grava um evento com o autor (o da conta, quando há conta), a
data, o valor anterior e a justificativa. Nada é sobrescrito; linhas e colunas só são
acrescentadas, e uma célula já registrada só muda por correção.

Os cálculos são declarativos (soma, diferença, contagem e média) e usam
``decimal.Decimal`` sem conversão: unidades ou moedas diferentes são recusadas, e uma
média que não termina é arredondada pela regra declarada na saída. A saída lista as
células usadas, a operação e o resultado, para que qualquer pessoa repita a conta.
Nada aqui chama modelo ou rede, e a tabela não avalia a veracidade dos valores.
"""
from copy import deepcopy
import csv
from decimal import (Context, Decimal, DivisionByZero, Inexact, InvalidOperation, Overflow, ROUND_HALF_UP, Rounded,
                     localcontext)
from fractions import Fraction
import io
import re

import caderno
import evidencias as ev
from linha_tempo import data_parcial

TIPOS_COLUNA = ('texto', 'data', 'monetario', 'numero')
ESTADOS_CELULA = ('extraido', 'corrigido_manual', 'pendente')
TIPOS_CORRECAO = ('correcao', 'preenchimento')
OPERACOES_CALCULO = ('soma', 'diferenca', 'contagem', 'media')
FORMATOS_CSV = ('padrao', 'excel_br')
ID_TABELA = r'Q[a-f0-9]{32}'
ID_COLUNA = r'[a-z][a-z0-9_]{0,39}'
ID_CALCULO = ID_COLUNA
MOEDA = r'[A-Z]{3}'
# Número como texto: ponto decimal, sem separador de milhar nem expoente ("8750000.00").
NUMERO = r'-?[0-9]{1,30}(\.[0-9]{1,12})?'
MAXIMO_COLUNAS, MAXIMO_LINHAS, MAXIMO_CELULAS = 30, 500, 5000
MAXIMO_CALCULOS, MAXIMO_CORRECOES = 50, 100
# Casas decimais da média quando a divisão não termina; a saída declara a regra usada.
CASAS_MEDIA = 6
PADROES = {'titulo': None, 'descricao': '', 'colunas': None, 'linhas': [], 'evidencias': [], 'calculos': [],
           'correcoes': [], 'retirado': False, 'motivo_retirada': ''}
CAMPOS_COLUNA = ('id', 'nome', 'tipo', 'moeda', 'unidade')
CAMPOS_CELULA = {'valor', 'fonte', 'estado'}
CAMPOS_CORRECAO = {'linha', 'coluna', 'tipo', 'valor_anterior', 'fonte_anterior', 'valor', 'fonte', 'justificativa'}
CAMPOS_CALCULO = ('id', 'nome', 'operacao', 'coluna', 'linhas', 'celulas', 'casas_decimais')
CAMPOS_PEDIDO_CORRECAO = {'caso', 'requisicao_id', 'autor', 'observacao', 'id', 'anterior_sha256', 'correcoes'}
# Contas exatas: precisão muito acima do maior valor aceito; qualquer arredondamento interrompe a conta.
EXATO = Context(prec=100, rounding=ROUND_HALF_UP, traps=[InvalidOperation, DivisionByZero, Overflow, Inexact, Rounded])
NOMES_OPERACAO = {'soma': 'a soma', 'diferenca': 'a diferença', 'contagem': 'a contagem', 'media': 'a média'}
AVISO = ('Valores transcritos ou extraídos das fontes indicadas; conferir no original antes de publicar. '
         'Célula pendente (sem fonte ou sem valor) não é fato, e a tabela não avalia a veracidade dos valores.')
AVISO_CALCULO = ('Conta exata com decimal.Decimal, sem conversão de unidade ou moeda; repita-a com as células e os '
                 'valores listados. Resultado com célula pendente não pode ser publicado como fato, e só se apoia '
                 'em fato quando todas as fontes foram avaliadas como sustentadas, de natureza documental.')


def _id_linha(position):
    return f'L{position + 1:04d}'


def _ref(cell):
    return f"{cell['linha']}/{cell['coluna']}"


def _lista(items, limit=10):
    return ', '.join(items[:limit]) + (f' e mais {len(items) - limit}' if len(items) > limit else '')


def _decimal_texto(value):
    """Forma fixa do Decimal, sem expoente e sem zero negativo."""
    return format(value.copy_abs() if value.is_zero() else value, 'f')


def _rotulo_coluna(column):
    if column['tipo'] == 'monetario':
        return f"{column['nome']} ({column['moeda']}{' ' + column['unidade'] if column['unidade'] else ''})"
    if column['tipo'] == 'numero':
        return f"{column['nome']} ({column['unidade']})"
    return column['nome']


def _rotulo_grandeza(kind, currency, unit):
    if kind == 'monetario':
        return f'moeda {currency}' + (f' ({unit})' if unit else '')
    return f'unidade {unit}'


# Colunas, valores e células

def _coluna(item):
    if not isinstance(item, dict) or set(item) - set(CAMPOS_COLUNA) or not {'id', 'nome', 'tipo'} <= set(item):
        raise ValueError('Coluna inválida: informe id, nome e tipo (e a moeda ou a unidade, conforme o tipo).')
    identifier, kind = item['id'], item['tipo']
    if not isinstance(identifier, str) or not re.fullmatch(ID_COLUNA, identifier):
        raise ValueError('Coluna inválida: o id usa letras minúsculas sem acento, números e _, começa por letra '
                         'e tem até 40 caracteres.')
    if not isinstance(kind, str) or kind not in TIPOS_COLUNA:
        raise ValueError('Coluna inválida: o tipo deve ser texto, data, monetario ou numero.')
    currency, unit = item.get('moeda'), item.get('unidade')
    if kind == 'monetario':
        if not isinstance(currency, str) or not re.fullmatch(MOEDA, currency):
            raise ValueError('Coluna inválida: valor monetário exige a moeda em código de três letras maiúsculas '
                             '(BRL, USD, EUR).')
    elif currency is not None:
        raise ValueError('Coluna inválida: só valor monetário leva moeda.')
    if kind == 'numero' and unit is None:
        raise ValueError('Coluna inválida: número exige a unidade (kg, km, %, pessoas…).')
    if kind in ('texto', 'data') and unit is not None:
        raise ValueError('Coluna inválida: texto e data não levam unidade.')
    if unit is not None:  # em valor monetário, a unidade é a escala declarada pela fonte (mil, milhões)
        unit = ' '.join(ev.texto(unit, 'Unidade da coluna', 30).split())
    return {'id': identifier, 'nome': ev.texto(item['nome'], 'Nome da coluna', 120), 'tipo': kind,
            'moeda': currency, 'unidade': unit}


def _colunas(items, atual=None):
    """Colunas canônicas; as já registradas não mudam de id, ordem, tipo, moeda ou unidade (só de nome)."""
    if not isinstance(items, list) or not 1 <= len(items) <= MAXIMO_COLUNAS:
        raise ValueError(f'Coluna inválida: registre de 1 a {MAXIMO_COLUNAS} colunas.')
    result = [_coluna(item) for item in items]
    if len({c['id'] for c in result}) != len(result):
        raise ValueError('Coluna inválida: id repetido.')
    fixed = lambda c: (c['id'], c['tipo'], c['moeda'], c['unidade'])  # noqa: E731
    if atual is not None and (len(result) < len(atual) or any(fixed(c) != fixed(a) for c, a in zip(result, atual))):
        raise ValueError('As colunas já registradas não mudam de id, ordem, tipo, moeda ou unidade; '
                         'acrescente uma coluna nova ao fim.')
    return result


def _valor(column, value, where='célula'):
    """Valor canônico da célula conforme o tipo da coluna; ``None`` é célula sem valor."""
    if value is None:
        return None
    kind = column['tipo']
    if kind == 'texto':
        try:
            return ev.texto(value, 'Texto da célula', 2000)
        except ValueError:
            raise ValueError(f'Valor inválido em {where}: informe texto de até 2000 caracteres, '
                             'ou null para célula vazia.') from None
    if kind == 'data':
        try:
            data_parcial(value)
        except ValueError:
            raise ValueError(f'Valor inválido em {where}: use a data AAAA, AAAA-MM ou AAAA-MM-DD, conforme a '
                             'precisão do documento, existente no calendário.') from None
        return value
    if not isinstance(value, str) or not re.fullmatch(NUMERO, value):
        raise ValueError(f'Valor inválido em {where}: informe o número como texto, com ponto decimal e sem '
                         'separador de milhar (ex.: 8750000.00).')
    return _decimal_texto(Decimal(value))


def _fonte(value, links):
    """Índice de uma evidência de suporte vinculada à tabela, ou ``None`` (célula sem fonte)."""
    index = ev.indice_fonte(value, links, 'Fonte da célula')
    if index is not None and links[index]['papel'] != 'suporte':
        raise ValueError('Fonte da célula: indique uma evidência de suporte vinculada a esta tabela.')
    return index


def _estado(value, source, corrected):
    if value is None or source is None:
        return 'pendente'
    return 'corrigido_manual' if corrected else 'extraido'


def _limite(rows, columns):
    if rows > MAXIMO_LINHAS or rows * columns > MAXIMO_CELULAS:
        raise ValueError(f'Tabela grande demais: até {MAXIMO_LINHAS} linhas e {MAXIMO_CELULAS} células.')


def _base(atual, links, columns):
    """Linhas registradas, com as fontes seguindo a identidade da evidência e células vazias nas colunas novas."""
    if atual is None:
        return []
    rows = deepcopy(atual['linhas'])
    if links is not atual['evidencias']:
        kept = {ev.identidade(x) for x in links}
        blocked = [f"{row['id']}/{cid}" for row in rows for cid, cell in row['celulas'].items()
                   if cell['fonte'] is not None and ev.identidade(atual['evidencias'][cell['fonte']]) not in kept]
        if blocked:
            raise ValueError(f'Evidência ainda é fonte de célula ({_lista(blocked)}): corrija essas células antes de '
                             'retirar a evidência ou mudar o papel dela.')
        mover = ev.realocar_fontes(atual['evidencias'], links, 'a célula')
        for row in rows:
            for cell in row['celulas'].values():
                if cell['fonte'] is not None:
                    cell['fonte'] = mover(cell['fonte'])
    for column in columns[len(atual['colunas']):]:
        for row in rows:
            row['celulas'][column['id']] = {'valor': None, 'fonte': None, 'estado': 'pendente'}
    return rows


def _linhas(items, columns, links, base, old_columns):
    """Linhas canônicas: as registradas voltam como estão salvas; as novas vão ao fim, com id seguinte.

    Devolve ``(linhas, fontes)``, em que ``fontes`` são os índices das evidências usadas por células novas.
    """
    if not isinstance(items, list):
        raise ValueError('Linha inválida: envie a lista de linhas.')
    _limite(len(items), len(columns))
    if len(items) < len(base):
        raise ValueError('Linha inválida: linhas já registradas não podem ser retiradas nem reordenadas; '
                         'corrija as células com justificativa.')
    known = {c['id'] for c in columns}
    rows, sources = [], set()
    for position, item in enumerate(items):
        row_id = _id_linha(position)
        if not isinstance(item, dict) or set(item) - {'id', 'celulas'} or not isinstance(item.get('celulas'), dict):
            raise ValueError(f'Linha inválida ({row_id}): envie as células como {{"coluna": {{"valor", "fonte"}}}}.')
        if item.get('id', row_id) != row_id:
            raise ValueError(f'Linha inválida ({row_id}): fora da ordem registrada; linhas novas vão ao fim, sem id.')
        unknown = sorted(str(k) for k in set(item['celulas']) - known)
        if unknown:
            raise ValueError(f'Linha inválida ({row_id}): coluna inexistente ({_lista(unknown)}).')
        existing = base[position] if position < len(base) else None
        cells = {}
        for column in columns:
            cid = column['id']
            where = f'{row_id}/{cid}'
            given = item['celulas'].get(cid)
            if existing is not None and cid in old_columns:
                if given != existing['celulas'][cid]:
                    raise ValueError(f'Célula já registrada ({where}): reenvie-a como está salva, ou omita as linhas; '
                                     'valor e fonte só mudam por correção com justificativa.')
                cells[cid] = existing['celulas'][cid]
                continue
            given = {} if given is None else given
            if not isinstance(given, dict) or set(given) - {'valor', 'fonte'}:
                raise ValueError(f'Célula inválida ({where}): envie valor e fonte; o estado é calculado.')
            value = _valor(column, given.get('valor'), where)
            source = _fonte(given.get('fonte'), links)
            if source is not None:
                sources.add(source)
            cells[cid] = {'valor': value, 'fonte': source, 'estado': _estado(value, source, False)}
        rows.append({'id': row_id, 'celulas': cells})
    return rows, sources


def _conferir_fontes(root, case, links, indices, cache=None):
    """Fontes novas de células precisam resolver agora contra o original (rodada, revisão ou caderno)."""
    order = sorted(indices)
    for index, item in zip(order, ev.conferir_vinculos(root, case, [links[i] for i in order], cache)):
        if item['estado'] != 'conferida':
            raise ValueError(f'Fonte indicada indisponível (evidência {index}): {item["erro"]}')


# Cálculos

def _grandeza(columns, operation):
    """Tipo, moeda e unidade comuns às células de uma conta; recusa misturas, sem converter."""
    other = sorted({c['nome'] for c in columns if c['tipo'] not in ('monetario', 'numero')})
    if other:
        raise ValueError(f'Cálculo recusado: {NOMES_OPERACAO[operation]} exige colunas de valor monetário ou número '
                         f'(não numérica: {_lista(other)}).')
    kinds = sorted({(c['tipo'], c['moeda'] or '', c['unidade'] or '') for c in columns})
    if len(kinds) > 1:
        raise ValueError('Cálculo recusado: unidades ou moedas diferentes ('
                         + '; '.join(_rotulo_grandeza(*k) for k in kinds)
                         + '); não há conversão automática, calcule cada grandeza em separado.')
    kind, currency, unit = kinds[0]
    return {'tipo': kind, 'moeda': currency or None, 'unidade': unit or None}


def _calculo(item, columns, rows):
    """Definição declarada e canônica de um cálculo, conferida contra as colunas e as linhas da tabela."""
    if not isinstance(item, dict) or set(item) - set(CAMPOS_CALCULO) or not {'id', 'operacao'} <= set(item):
        raise ValueError('Cálculo inválido: informe id, operacao e as células (coluna, com linhas opcionais, '
                         'ou celulas).')
    identifier, operation = item['id'], item['operacao']
    if not isinstance(identifier, str) or not re.fullmatch(ID_CALCULO, identifier):
        raise ValueError('Cálculo inválido: o id usa letras minúsculas sem acento, números e _, começa por letra '
                         'e tem até 40 caracteres.')
    if not isinstance(operation, str) or operation not in OPERACOES_CALCULO:
        raise ValueError('Cálculo inválido: a operação deve ser soma, diferenca, contagem ou media.')
    by_column = {c['id']: c for c in columns}
    row_ids = {r['id'] for r in rows}
    column, lines, cells = item.get('coluna'), item.get('linhas'), item.get('celulas')
    if (column is None) == (cells is None) or (lines is not None and column is None):
        raise ValueError('Cálculo inválido: indique uma coluna (com linhas opcionais) ou a lista de células.')
    if column is not None:
        if not isinstance(column, str) or column not in by_column:
            raise ValueError('Cálculo inválido: coluna inexistente nesta tabela.')
        if lines is not None:
            if (not isinstance(lines, list) or not 1 <= len(lines) <= MAXIMO_LINHAS
                    or not all(isinstance(x, str) and x in row_ids for x in lines) or len(set(lines)) != len(lines)):
                raise ValueError('Cálculo inválido: indique linhas existentes nesta tabela, sem repetição.')
            lines = list(lines)
        used, count = [by_column[column]], None if lines is None else len(lines)
    else:
        if not isinstance(cells, list) or not 1 <= len(cells) <= MAXIMO_LINHAS:
            raise ValueError(f'Cálculo inválido: indique de 1 a {MAXIMO_LINHAS} células.')
        pairs = []
        for cell in cells:
            if (not isinstance(cell, dict) or set(cell) != {'linha', 'coluna'}
                    or not isinstance(cell['linha'], str) or cell['linha'] not in row_ids
                    or not isinstance(cell['coluna'], str) or cell['coluna'] not in by_column):
                raise ValueError('Cálculo inválido: célula inexistente nesta tabela.')
            pairs.append((cell['linha'], cell['coluna']))
        if len(set(pairs)) != len(pairs):
            raise ValueError('Cálculo inválido: célula repetida no cálculo.')
        cells = [{'linha': r, 'coluna': c} for r, c in pairs]
        used, count = [by_column[c] for _, c in pairs], len(pairs)
    if operation == 'diferenca' and count != 2:
        raise ValueError('Cálculo inválido: a diferença usa exatamente duas células, na ordem minuendo, subtraendo.')
    places = item.get('casas_decimais')
    if places is not None and (operation != 'media' or type(places) is not int or not 0 <= places <= 12):
        raise ValueError('Cálculo inválido: casas decimais só na média, de 0 a 12.')
    if operation != 'contagem':
        _grandeza(used, operation)
    name = item.get('nome')
    return {'id': identifier, 'nome': ev.texto('' if name is None else name, 'Nome do cálculo', 200, vazio=True),
            'operacao': operation, 'coluna': column, 'linhas': lines, 'celulas': cells, 'casas_decimais': places}


def _calculos(items, columns, rows):
    if not isinstance(items, list) or len(items) > MAXIMO_CALCULOS:
        raise ValueError(f'Cálculo inválido: registre até {MAXIMO_CALCULOS} cálculos.')
    result = [_calculo(item, columns, rows) for item in items]
    if len({c['id'] for c in result}) != len(result):
        raise ValueError('Cálculo inválido: id repetido.')
    return result


def _operandos(calc, rows):
    if calc['coluna'] is None:
        return [(c['linha'], c['coluna']) for c in calc['celulas']]
    lines = calc['linhas'] if calc['linhas'] is not None else [r['id'] for r in rows]
    return [(line, calc['coluna']) for line in lines]


def _somar(values):
    with localcontext(EXATO):
        total = Decimal(0)
        for value in values:
            total += value
    return total


def _dividir(total, divisor, places, declared):
    """``(quociente, exato)``. Sem casas declaradas, o quociente que termina sai exato; o que não termina,
    e o que passa das casas declaradas, sai arredondado meio para cima (a metade vai para longe do zero)."""
    try:
        with localcontext(EXATO):
            quotient = total / divisor
    except (Inexact, Rounded):
        quotient = None
    if quotient is not None and (not declared or -quotient.as_tuple().exponent <= places):
        return quotient, True
    exact = Fraction(total) / divisor
    scaled = abs(exact) * 10 ** places
    whole, rest = divmod(scaled.numerator, scaled.denominator)
    if 2 * rest >= scaled.denominator:
        whole += 1
    value = Decimal(f'{whole}E-{places}')  # construção exata, sem o contexto
    return (value.copy_negate() if exact < 0 and whole else value), False


def _termo(value):
    return f'({value})' if value.startswith('-') else value


def calcular(state, definicao):
    """Refaz um cálculo declarado sobre um estado da tabela: função pura e determinística.

    Soma, diferença (primeira célula menos a segunda) e média exigem colunas de valor
    monetário ou número com a mesma moeda e a mesma unidade, e recusam célula sem valor.
    A média é exata quando a divisão termina; quando não termina (``CASAS_MEDIA`` casas)
    ou passa das ``casas_decimais`` declaradas, é arredondada meio para cima e a saída
    traz o arredondamento usado. A contagem conta as células com valor e lista as vazias.
    A saída traz as células usadas (com valor, estado e fonte), a expressão, o resultado e
    ``entrada_sha256``, o hash canônico da operação e dos valores, para conferir que a
    conta repetida usou as mesmas entradas.
    """
    calc = _calculo(definicao, state['colunas'], state['linhas'])
    columns = {c['id']: c for c in state['colunas']}
    rows = {r['id']: r for r in state['linhas']}
    operands = _operandos(calc, state['linhas'])
    links = state['evidencias']
    cells = []
    for row_id, column_id in operands:
        cell = rows[row_id]['celulas'][column_id]
        link = links[cell['fonte']] if cell['fonte'] is not None else None
        cells.append({'linha': row_id, 'coluna': column_id, 'nome_coluna': columns[column_id]['nome'],
                      'valor': cell['valor'], 'estado': cell['estado'], 'fonte': cell['fonte'],
                      'fonte_legivel': link['localizador']['legivel'] if link else None,
                      'fonte_suporte': link['suporte'] if link else None,
                      'fonte_natureza': link['natureza'] if link else None})
    operation, places, extra = calc['operacao'], None, {}
    if operation == 'contagem':
        counted = [x for x in cells if x['valor'] is not None]
        quantity = {'tipo': 'contagem', 'moeda': None, 'unidade': 'células com valor'}
        result, exact, rounding = str(len(counted)), True, None
        expression = f'{len(counted)} de {len(cells)} célula(s) com valor'
        extra = {'celulas_sem_valor': [_ref(x) for x in cells if x['valor'] is None]}
    else:
        if not cells:
            raise ValueError(f'Cálculo recusado: nenhuma célula para {NOMES_OPERACAO[operation]}.')
        quantity = _grandeza([columns[c] for _, c in operands], operation)
        empty = [_ref(x) for x in cells if x['valor'] is None]
        if empty:
            raise ValueError(f'Cálculo recusado: célula sem valor ({_lista(empty)}); preencha a célula ou escolha '
                             'as células do cálculo.')
        values = [Decimal(x['valor']) for x in cells]
        terms = [_termo(x['valor']) for x in cells]
        exact, rounding = True, None
        if operation == 'soma':
            result, expression = _decimal_texto(_somar(values)), ' + '.join(terms)
        elif operation == 'diferenca':
            with localcontext(EXATO):
                difference = values[0] - values[1]
            result, expression = _decimal_texto(difference), f'{terms[0]} - {terms[1]}'
            if quantity['tipo'] == 'numero' and quantity['unidade'] == '%':
                quantity = {**quantity, 'unidade': 'pontos percentuais'}
                extra = {'observacao': 'A diferença entre percentuais é dada em pontos percentuais.'}
        else:
            declared = calc['casas_decimais'] is not None
            places = calc['casas_decimais'] if declared else CASAS_MEDIA
            total = _somar(values)
            mean, exact = _dividir(total, len(values), places, declared)
            result, expression = _decimal_texto(mean), f'({" + ".join(terms)}) / {len(values)}'
            extra = {'soma': _decimal_texto(total), 'divisor': len(values)}
            if not exact:
                rounding = {'casas_decimais': places, 'regra': 'meio_para_cima', 'casas_declaradas': declared,
                            'descricao': f'Resultado arredondado a {places} casa(s) decimal(is); a metade exata '
                                         'arredonda para longe do zero.'}
    pending = [_ref(x) for x in cells if x['estado'] == 'pendente']
    # Como nos quadros do Core, só sustenta fato a fonte avaliada como sustentada e de natureza documental.
    unsupported = [_ref(x) for x in cells if x['fonte'] is not None and (
        x['fonte_suporte'] != 'sustentado' or x['fonte_natureza'] not in ev.NATUREZAS_DOCUMENTAIS)]
    entry = {'operacao': operation, 'grandeza': quantity, 'casas_decimais': places,
             'operandos': [[x['linha'], x['coluna'], x['valor']] for x in cells]}
    return {'id': calc['id'], 'nome': calc['nome'], 'operacao': operation, 'definicao': calc, 'celulas': cells,
            'n': len(cells), 'grandeza': quantity, 'expressao': expression, 'resultado': result, 'exato': exact,
            'arredondamento': rounding, **extra, 'estado': 'pendente' if pending else 'com_fonte',
            'celulas_pendentes': pending, 'fontes_sustentadas': not pending and not unsupported,
            'fontes_nao_sustentadas': unsupported, 'entrada_sha256': caderno._hash(entry), 'aviso': AVISO_CALCULO}


# Regras puras, reaplicadas a cada evento lido

def _conferir_linhas(rows, columns, links):
    if not isinstance(rows, list):
        raise ValueError('Linhas preservadas divergem da forma canônica.')
    _limite(len(rows), len(columns))
    by_column = {c['id']: c for c in columns}
    for position, row in enumerate(rows):
        if (not isinstance(row, dict) or set(row) != {'id', 'celulas'} or row['id'] != _id_linha(position)
                or not isinstance(row['celulas'], dict) or set(row['celulas']) != set(by_column)):
            raise ValueError('Linhas preservadas divergem da forma canônica.')
        for cid, cell in row['celulas'].items():
            if (not isinstance(cell, dict) or set(cell) != CAMPOS_CELULA
                    or _valor(by_column[cid], cell['valor']) != cell['valor']
                    or cell['fonte'] is not None and _fonte(cell['fonte'], links) != cell['fonte']
                    or cell['estado'] not in ESTADOS_CELULA
                    or (cell['estado'] == 'pendente') != (cell['valor'] is None or cell['fonte'] is None)):
                raise ValueError('Célula preservada diverge da forma canônica.')


def _conferir_correcoes(records, state):
    """As correções gravadas no evento correspondem às células do próprio estado."""
    if not isinstance(records, list) or len(records) > MAXIMO_CORRECOES:
        raise ValueError('Correções preservadas inválidas.')
    columns = {c['id']: c for c in state['colunas']}
    rows = {r['id']: r for r in state['linhas']}
    links, seen = state['evidencias'], set()
    for record in records:
        if (not isinstance(record, dict) or set(record) != CAMPOS_CORRECAO or record['tipo'] not in TIPOS_CORRECAO
                or record['linha'] not in rows or record['coluna'] not in columns
                or (record['linha'], record['coluna']) in seen):
            raise ValueError('Correções preservadas inválidas.')
        seen.add((record['linha'], record['coluna']))
        cell = rows[record['linha']]['celulas'][record['coluna']]
        before, after = (record['valor_anterior'], record['fonte_anterior']), (record['valor'], record['fonte'])
        changed = (before[0] is not None and after[0] != before[0]) or (before[1] is not None and after[1] != before[1])
        reason = record['justificativa']
        if (after != (cell['valor'], cell['fonte']) or after == before or (record['tipo'] == 'correcao') != changed
                or _valor(columns[record['coluna']], before[0]) != before[0]
                or before[1] is not None and _fonte(before[1], links) != before[1]
                or not isinstance(reason, str) or ev.texto(reason, 'Justificativa', 2000, vazio=True) != reason
                or changed and not reason
                # Preencher célula já corrigida antes mantém a marca de correção manual (o histórico mostra a origem).
                or cell['estado'] not in {_estado(cell['valor'], cell['fonte'], changed),
                                          _estado(cell['valor'], cell['fonte'], record['tipo'] == 'preenchimento')}):
            raise ValueError('Correções preservadas inválidas.')


def _regras(state):
    ev.texto(state['titulo'], 'Título da tabela', 300)
    ev.texto(state['descricao'], 'Descrição da tabela', 2000, vazio=True)
    if _colunas(state['colunas']) != state['colunas']:
        raise ValueError('Colunas preservadas divergem da forma canônica.')
    if not isinstance(state['evidencias'], list) or len(state['evidencias']) > ev.MAXIMO_VINCULOS:
        raise ValueError('Evidências preservadas inválidas.')
    _conferir_linhas(state['linhas'], state['colunas'], state['evidencias'])
    if _calculos(state['calculos'], state['colunas'], state['linhas']) != state['calculos']:
        raise ValueError('Cálculos preservados divergem da forma canônica.')
    _conferir_correcoes(state['correcoes'], state)
    if ev.retirada(state) != (state['retirado'], state['motivo_retirada']):
        raise ValueError('Retirada preservada inválida.')


# Normalização dos pedidos (criar, atualizar e corrigir)

def _corrigidas_antes(root, case, identifier):
    """Células que já receberam correção manual em algum evento anterior da tabela."""
    if not identifier:
        return set()
    record = COLECAO.detalhe(root, case, identifier)
    return {(r['linha'], r['coluna']) for event in record['historico']
            for r in event['estado'].get('correcoes', []) if r['tipo'] == 'correcao'}


def _corrigir(root, case, data, atual, identifier=None):
    if atual is None:
        raise ValueError('Correção inválida: só se corrige célula de tabela já registrada.')
    if set(data) != {'correcoes'}:
        raise ValueError('Correção inválida: envie as correções separadas das demais alterações da tabela.')
    items = data['correcoes']
    if not isinstance(items, list) or not 1 <= len(items) <= MAXIMO_CORRECOES:
        raise ValueError(f'Correção inválida: envie de 1 a {MAXIMO_CORRECOES} correções.')
    state = {k: deepcopy(atual[k]) for k in PADROES}
    columns = {c['id']: c for c in state['colunas']}
    rows = {r['id']: r for r in state['linhas']}
    links, records, sources = state['evidencias'], [], set()
    manual = _corrigidas_antes(root, case, identifier)
    for item in items:
        if (not isinstance(item, dict) or set(item) - {'linha', 'coluna', 'valor', 'fonte', 'justificativa'}
                or not {'linha', 'coluna'} <= set(item) or not {'valor', 'fonte'} & set(item)):
            raise ValueError('Correção inválida: indique linha, coluna e o novo valor ou a nova fonte.')
        row_id, column_id = item['linha'], item['coluna']
        if not isinstance(row_id, str) or row_id not in rows or not isinstance(column_id, str) or column_id not in columns:
            raise ValueError('Célula inexistente nesta tabela.')
        where = f'{row_id}/{column_id}'
        if any((r['linha'], r['coluna']) == (row_id, column_id) for r in records):
            raise ValueError(f'Correção inválida: a célula {where} aparece duas vezes no pedido.')
        cell = rows[row_id]['celulas'][column_id]
        value = _valor(columns[column_id], item['valor'], where) if 'valor' in item else cell['valor']
        source = _fonte(item['fonte'], links) if 'fonte' in item else cell['fonte']
        if (value, source) == (cell['valor'], cell['fonte']):
            raise ValueError(f'Correção inválida: a célula {where} já tem este valor e esta fonte.')
        # Preencher o que faltava (valor ou fonte nulos) não é correção; mudar o que já havia é, e exige justificativa.
        changed = ((cell['valor'] is not None and value != cell['valor'])
                   or (cell['fonte'] is not None and source != cell['fonte']))
        reason = item.get('justificativa', '')
        if changed and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError(f'Para corrigir uma célula, informe a justificativa ({where}).')
        reason = ev.texto(reason, 'Justificativa da correção', 2000, vazio=True)
        if source is not None and source != cell['fonte']:
            sources.add(source)
        rows[row_id]['celulas'][column_id] = {'valor': value, 'fonte': source,
                                              'estado': _estado(value, source, changed or (row_id, column_id) in manual)}
        records.append({'linha': row_id, 'coluna': column_id, 'tipo': 'correcao' if changed else 'preenchimento',
                        'valor_anterior': cell['valor'], 'fonte_anterior': cell['fonte'], 'valor': value,
                        'fonte': source, 'justificativa': reason})
    if sources:
        _conferir_fontes(root, case, links, sources)
    state['correcoes'] = records
    _regras(state)
    return state


def _normalizar(root, case, data, atual, identificador):
    if 'correcoes' in data:
        return _corrigir(root, case, data, atual, identificador)
    state = ev.mesclar(data, atual, PADROES)
    removing, reason = ev.retirada(state)
    cache = {}
    # Evidências só são resolvidas de novo quando a lista muda; as salvas já foram conferidas no vínculo.
    resolved = atual is None or 'evidencias' in data
    if resolved:
        links = ev.vinculos(root, case, state['evidencias'], preservar_indisponiveis=removing, cache=cache)
    else:
        links = atual['evidencias']
    columns = _colunas(state['colunas'], atual['colunas'] if atual else None)
    base = _base(atual, links, columns)
    if atual is None or 'linhas' in data:
        old_columns = {c['id'] for c in atual['colunas']} if atual else set()
        rows, sources = _linhas(state['linhas'], columns, links, base, old_columns)
    else:
        rows, sources = base, set()
    if sources and (not resolved or removing):  # célula nova só aponta para fonte que resolve agora
        _conferir_fontes(root, case, links, sources, cache)
    result = {'titulo': ev.texto(state['titulo'], 'Título da tabela', 300),
              'descricao': ev.texto(state['descricao'], 'Descrição da tabela', 2000, vazio=True),
              'colunas': columns, 'linhas': rows, 'evidencias': links,
              'calculos': _calculos(state['calculos'], columns, rows), 'correcoes': [],
              'retirado': removing, 'motivo_retirada': reason}
    _regras(result)
    return result


COLECAO = ev.Colecao('tabelas', 'Q', PADROES, _normalizar, _regras, 'tabelas de apuração')


def salvar(root, data, operation='criar', conta=None):
    """Cria ou atualiza a tabela: título, descrição, colunas e linhas novas, evidências, cálculos e retirada.

    Na atualização, campos ausentes mantêm o estado atual; ``linhas`` traz as linhas já
    registradas como estão salvas e as novas ao fim. Células já registradas só mudam
    por ``corrigir``.
    """
    if isinstance(data, dict) and 'correcoes' in data:
        raise ValueError('Correção inválida: para corrigir células, use a correção com justificativa '
                         '(tabelas-corrigir).')
    return COLECAO.salvar(root, data, operation, conta)


def corrigir(root, data, conta=None):
    """Corrige ou preenche células já registradas, num evento novo com autor, data, valor anterior e justificativa.

    ``data = {caso, requisicao_id, autor, observacao?, id, anterior_sha256, correcoes: [{linha, coluna,
    valor?, fonte?, justificativa?}]}``. Mudar um valor ou uma fonte que já existiam é correção e exige
    justificativa; preencher o valor ou a fonte que faltavam é preenchimento.
    """
    if not isinstance(data, dict) or 'correcoes' not in data or set(data) - CAMPOS_PEDIDO_CORRECAO:
        raise ValueError('Correção inválida: envie caso, requisicao_id, autor, id, anterior_sha256 e correcoes.')
    return COLECAO.salvar(root, data, 'atualizar', conta)


def detalhe(root, case, identifier):
    return COLECAO.detalhe(root, case, identifier)


def listar(root, case):
    return COLECAO.listar(root, case)


def compacto(record):
    """Registro sem os estados completos do histórico: cada evento com autor, data, observação e correções."""
    keep = ('sequencia', 'operacao', 'autor', 'origem_autoria', 'conta_id', 'em_utc', 'observacao')
    return {**{k: record[k] for k in ('caso', 'colecao', 'id', 'sha256', 'estado', 'divergente')},
            'historico': [{**{k: e[k] for k in keep if k in e}, 'correcoes': e['estado']['correcoes']}
                          for e in record['historico']]}


def _ultimas_correcoes(history):
    last = {}
    for event in history:
        for item in event['estado']['correcoes']:
            if item['tipo'] == 'correcao':
                last[(item['linha'], item['coluna'])] = {
                    'sequencia': event['sequencia'], 'em_utc': event['em_utc'], 'autor': event['autor'],
                    'origem_autoria': event['origem_autoria'], 'valor_anterior': item['valor_anterior'],
                    'justificativa': item['justificativa']}
    return last


def _calculo_na_tabela(state, definition, links):
    """Cálculo refeito na visão da tabela; fonte indisponível deixa o resultado pendente."""
    try:
        result = calcular(state, definition)
    except ValueError as exc:
        return {'id': definition['id'], 'nome': definition['nome'], 'operacao': definition['operacao'],
                'definicao': definition, 'estado': 'recusado', 'erro': str(exc)}
    missing = []
    for cell in result['celulas']:
        cell['fonte_conferida'] = cell['fonte'] is not None and links[cell['fonte']]['estado'] == 'conferida'
        if cell['fonte'] is not None and not cell['fonte_conferida']:
            missing.append(_ref(cell))
    result['fontes_indisponiveis'] = missing
    if missing:
        result['estado'] = 'pendente'
    return result


def tabela(root, case, identifier):
    """A tabela com cada célula ligada à fonte conferida e os cálculos refeitos sobre a versão atual."""
    record = COLECAO.detalhe(root, case, identifier)
    state, history = record['estado'], record['historico']
    links = ev.conferir_vinculos(root, case, state['evidencias'])
    last = _ultimas_correcoes(history)
    counts = {e: 0 for e in ESTADOS_CELULA}
    rows = []
    for row in state['linhas']:
        cells = {}
        for column in state['colunas']:
            cell = row['celulas'][column['id']]
            counts[cell['estado']] += 1
            link = links[cell['fonte']] if cell['fonte'] is not None else None
            cells[column['id']] = {**cell, 'fonte_legivel': link['localizador']['legivel'] if link else None,
                                   'fonte_conferida': link is not None and link['estado'] == 'conferida',
                                   'ultima_correcao': last.get((row['id'], column['id']))}
        rows.append({'id': row['id'], 'celulas': cells})
    return {'caso': case, 'id': identifier, 'sha256': record['sha256'],
            'versao': {'sequencia': len(history), 'sha256': record['sha256']},
            'titulo': state['titulo'], 'descricao': state['descricao'], 'colunas': state['colunas'], 'linhas': rows,
            'evidencias': links, 'calculos': [_calculo_na_tabela(state, c, links) for c in state['calculos']],
            'celulas_por_estado': counts, 'retirado': state['retirado'], 'motivo_retirada': state['motivo_retirada'],
            'atualizado_em_utc': state['atualizado_em_utc'], 'historico': compacto(record)['historico'],
            'aviso': AVISO}


def quadro(root, case, *, incluir_retirados=False):
    """Resumo das tabelas do caso; uma tabela com histórico divergente vem marcada e não derruba as demais."""
    rows, broken = [], []
    for item in COLECAO.listar(root, case):
        if item['divergente']:
            broken.append({'id': item['id'], 'erro': item['erro']})
            continue
        state = item['estado']
        if state['retirado'] and not incluir_retirados:
            continue
        counts = {e: 0 for e in ESTADOS_CELULA}
        for row in state['linhas']:
            for cell in row['celulas'].values():
                counts[cell['estado']] += 1
        rows.append({'id': item['id'], 'sha256': item['sha256'], 'titulo': state['titulo'],
                     'descricao': state['descricao'], 'colunas': state['colunas'], 'total_linhas': len(state['linhas']),
                     'celulas_por_estado': counts, 'total_evidencias': len(state['evidencias']),
                     'calculos': [{k: c[k] for k in ('id', 'nome', 'operacao')} for c in state['calculos']],
                     'versao': len(item['historico']), 'retirado': state['retirado'],
                     'motivo_retirada': state['motivo_retirada'], 'atualizado_em_utc': state['atualizado_em_utc']})
    return {'caso': case, 'tabelas': rows, 'total': len(rows), 'divergentes': broken, 'aviso': AVISO}


def calcular_tabela(root, case, identifier, calculo, sequencia=None):
    """Refaz um cálculo registrado (pelo id) ou avulso (pela definição) sobre uma versão da tabela.

    ``sequencia`` escolhe a versão (evento do histórico, 1 = criação); sem ela, a atual.
    A saída leva a versão usada (sequência e hash do evento), para repetir a conta.
    """
    record = COLECAO.detalhe(root, case, identifier)
    history = record['historico']
    sequence = len(history) if sequencia is None else sequencia
    if type(sequence) is not int or not 1 <= sequence <= len(history):
        raise ValueError('Versão da tabela inexistente: indique a sequência de um evento do histórico.')
    state = history[sequence - 1]['estado']
    digest = history[sequence]['anterior_sha256'] if sequence < len(history) else record['sha256']
    if isinstance(calculo, str):
        definition = next((c for c in state['calculos'] if c['id'] == calculo), None)
        if definition is None:
            raise ValueError('Cálculo não encontrado nesta tabela (versão indicada).')
    elif isinstance(calculo, dict):
        definition = {'id': 'avulso', **calculo}
    else:
        raise ValueError('Cálculo inválido: indique o id de um cálculo registrado ou a definição do cálculo.')
    return {'caso': case, 'tabela': {'id': identifier, 'titulo': state['titulo'], 'sequencia': sequence,
                                     'sha256': digest},
            **calcular(state, definition)}


def historico_celula(root, case, identifier, linha, coluna):
    """Versões de uma célula ao longo do histórico, com autor, data, valor, fonte e correção de cada mudança."""
    record = COLECAO.detalhe(root, case, identifier)
    state = record['estado']
    if (not isinstance(linha, str) or linha not in {r['id'] for r in state['linhas']}
            or not isinstance(coluna, str) or coluna not in {c['id'] for c in state['colunas']}):
        raise ValueError('Célula inexistente nesta tabela.')
    versions, previous = [], None
    for event in record['historico']:
        snapshot = event['estado']
        row = next((r for r in snapshot['linhas'] if r['id'] == linha), None)
        cell = row['celulas'].get(coluna) if row else None
        if cell is None:
            continue
        link = snapshot['evidencias'][cell['fonte']] if cell['fonte'] is not None else None
        change = next((c for c in snapshot['correcoes'] if (c['linha'], c['coluna']) == (linha, coluna)), None)
        # A fonte é comparada pela identidade da evidência: reordenar a lista não cria versão nova.
        signature = (cell['valor'], cell['estado'], ev.identidade(link) if link else None)
        if signature == previous and change is None:
            continue
        previous = signature
        versions.append({'sequencia': event['sequencia'], 'operacao': event['operacao'], 'em_utc': event['em_utc'],
                         'autor': event['autor'], 'origem_autoria': event['origem_autoria'], 'valor': cell['valor'],
                         'estado': cell['estado'],
                         'fonte': None if link is None else {
                             'referencia': link['referencia'], 'documento_id': link['documento_id'],
                             'original_sha256': link['original_sha256'], 'localizador': link['localizador']['legivel'],
                             'suporte': link['suporte'], 'natureza': link['natureza']},
                         'correcao': None if change is None else {
                             k: change[k] for k in ('tipo', 'valor_anterior', 'justificativa')}})
    return {'caso': case, 'id': identifier, 'linha': linha, 'coluna': coluna, 'versoes': versions,
            'aviso': 'Cada versão vem de um evento do histórico; nenhuma versão anterior é apagada.'}


# Exportação CSV

def _planilha(text):
    """Texto que uma planilha leria como fórmula ganha apóstrofo inicial (injeção de fórmula em CSV)."""
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def _fonte_texto(link):
    if link is None:
        return 'PENDENTE: sem fonte'
    ref = link['referencia']
    origin = (f"achados {ref['caso_id']}/{ref['rodada']}/{ref['revisao']}/{ref['evidencia_id']}" if ref['tipo'] == 'ia'
              else f"caderno {ref['caso_id']}/{ref['registro_id']}/fonte {ref['fonte']}")
    text = (f"{link['localizador']['legivel']} | {origin} | original sha256 {link['original_sha256']} | "
            f"papel {link['papel']}, suporte {link['suporte']}, natureza {link['natureza']}")
    return text if link['estado'] == 'conferida' else f'{text} | FONTE INDISPONÍVEL: {link["erro"]}'


def _valor_csv(column, value, decimal_comma):
    if value is None:
        return ''
    if column['tipo'] in ('monetario', 'numero'):
        return value.replace('.', ',') if decimal_comma else value
    return _planilha(value) if column['tipo'] == 'texto' else value


def exportar_csv(root, case, identifier, formato='padrao'):
    """``(nome do arquivo, bytes)`` da tabela em CSV UTF-8 (com BOM), com uma coluna de fonte por coluna de valor.

    Cada coluna da tabela vira três: o valor, a fonte (localizador legível, referência,
    hash do original e avaliação do vínculo, ou ``PENDENTE: sem fonte``) e o estado da
    célula. ``padrao`` usa vírgula como separador e ponto decimal; ``excel_br`` usa
    ponto e vírgula e vírgula decimal, para o Excel em português.
    """
    if formato not in FORMATOS_CSV:
        raise ValueError('Formato de exportação inválido: use padrao ou excel_br.')
    view = tabela(root, case, identifier)
    decimal_comma = formato == 'excel_br'
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';' if decimal_comma else ',', lineterminator='\r\n')
    header = ['linha']
    for column in view['colunas']:
        label = _rotulo_coluna(column)
        header += [label, f'{label} - fonte', f'{label} - estado']
    writer.writerow([_planilha(h) for h in header])
    for row in view['linhas']:
        line = [row['id']]
        for column in view['colunas']:
            cell = row['celulas'][column['id']]
            link = view['evidencias'][cell['fonte']] if cell['fonte'] is not None else None
            line += [_valor_csv(column, cell['valor'], decimal_comma), _planilha(_fonte_texto(link)), cell['estado']]
        writer.writerow(line)
    return f'tabela_{identifier}.csv', ('﻿' + output.getvalue()).encode('utf-8')
