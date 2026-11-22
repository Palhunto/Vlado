"""Custo das perguntas em dinheiro (CUS-01, CUS-03): preço por tipo de token, cota mensal em reais.

**Preço.** ``precos_modelos.json`` (versionado, com data e fonte) dá, por provedor e modelo, o
preço em dólar por milhão de tokens de cada tipo: entrada sem cache, leitura de cache, saída (o
raciocínio é cobrado como saída) e escrita de cache por validade, cada provedor com as suas
(``cache_escrita_5m`` e ``_1h`` na Anthropic, ``cache_escrita_30m`` e ``_12h`` na OpenAI). Os
adaptadores (``provedor_*``) entregam o uso de cada chamada já separado nesses tipos. Escrita de
uma validade que o modelo não tem na tabela é contada pela escrita mais cara dele (ou da tabela),
com ``preco_estimado``. Modelo da Anthropic só é permitido com
preço na tabela. Modelo da OpenAI pode ser permitido sem preço (decisão do dono, 2026-11-21): é
contado pelo preço mais alto da tabela em cada tipo de token, com ``preco_estimado`` no registro e
aviso no log; nenhum gasto fica sem conta. O dono acrescenta o modelo da OpenAI em
``configuracao.json`` → ``"orcamento"`` → ``"modelos_permitidos"`` (a lista substitui a padrão:
repita nela os modelos da Anthropic que quiser manter).

**Cota.** Teto mensal em reais por conta (o administrador também tem a sua) e da organização,
hoje a instalação inteira (``chaves_orcamento`` é o ponto único que a Onda 2 refina). O gasto de
cada chamada é convertido pelo câmbio do momento e somado em ``ajustes/gasto_mensal.json``, em
milionésimos de real; o mês é o do calendário em UTC. Uma pergunta é recusada antes de começar
quando o saldo não cobre a estimativa mínima, e interrompida quando o gasto passa do teto.

**Registro.** Cada gravação do gasto também atualiza uma cópia anterior
(``gasto_mensal.anterior.json``). Registro ilegível, ou com um mês danificado (campo ausente ou de
tipo errado), é lido da cópia; sem cópia legível, a cota é tratada como esgotada, com aviso no
log, nunca como zero gasto. O custo de uma chamada que não pôde ser gravado fica em memória e é
somado na primeira gravação que funcionar. Se o gasto não puder ser gravado
(disco cheio, permissão) ou calculado, a pergunta em curso para antes da próxima chamada, e
nenhuma pergunta começa até o registro voltar a gravar (a recusa antes de começar confere a
gravação).

**Um lugar só para os valores.** ``precos_modelos.json`` também traz o câmbio (``cambio``) e os
padrões do orçamento (``orcamento_padrao``): ``mensal_por_conta_brl``, ``mensal_organizacao_brl``,
``estimativa_minima_tokens`` (entrada e saída de uma pergunta curta, ao preço do modelo),
``execucoes_simultaneas_por_conta``, ``execucoes_simultaneas`` e ``modelos_permitidos``. Cada um
pode ser sobreposto na instalação por ``configuracao.json`` → ``"orcamento"``, que aceita também
``cambio_brl_por_usd``.
Nenhuma chamada de modelo nem de rede.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
import json
import re
from pathlib import Path
import threading

import logging

from cadastrar_documentos import _atomico
from comum import ROOT, ler_json, trava_arquivo

TABELA = 'precos_modelos.json'
# Usage kinds with a fixed price key; cache writes are 'cache_escrita_<validity>' in both (5m, 1h, 30m, 12h...).
TIPOS = ('entrada_sem_cache', 'cache_leitura', 'saida')
PRECO_DE = {'entrada_sem_cache': 'entrada', 'cache_leitura': 'cache_leitura', 'saida': 'saida'}
ESCRITA = re.compile(r'cache_escrita_\d+[mh]')
CHAVES_ORCAMENTO = ('mensal_por_conta_brl', 'mensal_organizacao_brl', 'estimativa_minima_tokens',
                    'execucoes_simultaneas_por_conta', 'execucoes_simultaneas', 'modelos_permitidos')
ORGANIZACAO = 'instalacao'  # the one organization until Onda 2 (accounts and organizations)
CONTA_LOCAL = 'local'  # the single operator of the local mode
MICRO = Decimal(1_000_000)
MESES_GUARDADOS = 12
# Costs whose write failed (R1): {(data folder, month, account key): micro-reais}, added at the next write.
_PENDENTES = {}
SEM_PRECO = 'openai'  # the only provider whose models may be allowed without a price (estimated)
_TRAVA = threading.Lock()
log = logging.getLogger('vlado.custo')


class CotaEsgotada(ValueError):
    """The month's quota does not cover the question (W11 'limite' block)."""


class GastoSemRegistro(CotaEsgotada):
    """The month's spend cannot be read or recorded: no question spends until it can (R1, R2)."""


MENSAGEM_ILEGIVEL = ('O registro do gasto do mês está ilegível (ajustes/gasto_mensal.json, sem cópia anterior '
                     'legível): a cota foi tratada como esgotada até o administrador da instalação recuperá-lo. '
                     'Documentos, conferência e caderno seguem funcionando.')
MENSAGEM_SEM_GRAVAR = ('O gasto do mês não pode ser registrado agora (disco cheio ou sem permissão em ajustes/): '
                       'nenhuma pergunta é feita até o registro voltar a gravar; o que já foi concluído foi '
                       'preservado. Documentos, conferência e caderno seguem funcionando; avise o administrador '
                       'da instalação.')
MENSAGEM_SEM_CALCULO = ('O gasto do mês não pode ser registrado agora: o custo da última chamada não pôde ser '
                        'calculado (tabela de preços ilegível?). A pergunta foi interrompida para nenhum gasto ficar '
                        'sem conta; o que já foi concluído foi preservado. Avise o administrador da instalação.')


# --- configuração ------------------------------------------------------------------------------

def _numero_positivo(valor, nome):
    if type(valor) not in (int, float) or isinstance(valor, bool) or not valor > 0:
        raise ValueError(f'orcamento.{nome} em configuracao.json deve ser um número positivo.')
    return valor


def _inteiro_positivo(valor, nome):
    if type(valor) is not int or valor < 1:
        raise ValueError(f'orcamento.{nome} em configuracao.json deve ser um inteiro positivo.')
    return valor


def tabela_precos(root) -> dict:
    """The versioned price table (the data folder's copy wins, else the project's). Validated."""
    caminho = Path(root) / TABELA
    if not caminho.is_file():
        caminho = ROOT / TABELA
    try:
        tabela = ler_json(caminho)
    except (OSError, ValueError) as exc:
        raise ValueError(f'{TABELA} ilegível; sem a tabela de preços nenhuma pergunta é feita.') from exc
    modelos = tabela.get('modelos') if isinstance(tabela, dict) else None
    if not isinstance(modelos, dict) or not tabela.get('vigente_em'):
        raise ValueError(f'{TABELA} deve ter "vigente_em" e "modelos" por provedor.')
    for provedor, lista in modelos.items():
        if not isinstance(lista, dict):
            raise ValueError(f'{TABELA}: "modelos.{provedor}" deve ser um objeto.')
        for modelo, preco in lista.items():
            if (not isinstance(preco, dict) or not set(PRECO_DE.values()) <= set(preco)
                    or any(k not in PRECO_DE.values() and not ESCRITA.fullmatch(k) for k in preco)
                    or not all(type(v) in (int, float) and not isinstance(v, bool) and v >= 0 for v in preco.values())):
                raise ValueError(f'{TABELA}: preço de {modelo} precisa de entrada, cache_leitura e saida, mais '
                                 'cache_escrita_<validade> (5m, 1h, 30m, 12h...), em dólar por milhão de tokens.')
    cambio = (tabela.get('cambio') or {}).get('brl_por_usd')
    if type(cambio) not in (int, float) or isinstance(cambio, bool) or not cambio > 0:
        raise ValueError(f'{TABELA}: "cambio.brl_por_usd" deve ser um número positivo.')
    return tabela


def ler_orcamento(root) -> dict:
    """``orcamento`` of configuracao.json over the table's ``orcamento_padrao``, validated."""
    padrao = tabela_precos(root).get('orcamento_padrao')
    padrao = {k: v for k, v in padrao.items() if k != 'provisorio'} if isinstance(padrao, dict) else None
    if padrao is None or set(padrao) != set(CHAVES_ORCAMENTO):
        raise ValueError(f'{TABELA}: "orcamento_padrao" deve ter ' + ', '.join(CHAVES_ORCAMENTO) + '.')
    try:
        config = ler_json(Path(root) / 'configuracao.json')
    except (OSError, ValueError) as exc:
        raise ValueError('configuracao.json ilegível; não foi possível ler o orçamento.') from exc
    valores = (config or {}).get('orcamento', {}) if isinstance(config, dict) else None
    aceitas = (*CHAVES_ORCAMENTO, 'cambio_brl_por_usd')
    if not isinstance(valores, dict) or set(valores) - set(aceitas):
        raise ValueError('"orcamento" em configuracao.json aceita só ' + ', '.join(aceitas) + '.')
    resultado = {'cambio_brl_por_usd': None, **padrao, **valores}
    for nome in ('mensal_por_conta_brl', 'mensal_organizacao_brl'):
        _numero_positivo(resultado[nome], nome)
    if resultado['cambio_brl_por_usd'] is not None:
        _numero_positivo(resultado['cambio_brl_por_usd'], 'cambio_brl_por_usd')
    for nome in ('execucoes_simultaneas_por_conta', 'execucoes_simultaneas'):
        _inteiro_positivo(resultado[nome], nome)
    estimativa = resultado['estimativa_minima_tokens']
    if not isinstance(estimativa, dict) or set(estimativa) != {'entrada', 'saida'}:
        raise ValueError('orcamento.estimativa_minima_tokens deve ter "entrada" e "saida".')
    for chave, valor in estimativa.items():
        if type(valor) is not int or valor < 0:
            raise ValueError('orcamento.estimativa_minima_tokens: valores inteiros não negativos.')
    permitidos = resultado['modelos_permitidos']
    if not isinstance(permitidos, list) or not permitidos or not all(isinstance(m, str) and m for m in permitidos):
        raise ValueError('orcamento.modelos_permitidos deve ser uma lista não vazia de nomes de modelo.')
    return resultado


def preco(root, modelo, tabela=None):
    """(provider, price) of ``modelo`` in the table, or (None, None)."""
    tabela = tabela or tabela_precos(root)
    for provedor, lista in tabela['modelos'].items():
        if modelo in lista:
            return provedor, lista[modelo]
    return None, None


def preco_maximo(tabela) -> dict:
    """The highest price of the table in each kind of token: what an unpriced model is counted at.

    Cache writes of every validity at the highest write price of any validity: a write of an
    unknown model never costs less than the highest the table knows.
    """
    precos = [p for lista in tabela['modelos'].values() for p in lista.values()]
    chaves = {k for p in precos for k in p}
    maximo = {k: max(p[k] for p in precos if k in p) for k in chaves}
    escritas = [v for k, v in maximo.items() if ESCRITA.fullmatch(k)]
    if escritas:
        maximo.update({k: max(escritas) for k in maximo if ESCRITA.fullmatch(k)})
    return maximo


def modelos_permitidos(root) -> list:
    """{'modelo', 'provedor', 'preco_estimado'} of each model the installation allows.

    A model of the table has its price. A model outside it can only be an OpenAI one, counted at
    the highest prices (``preco_maximo``): a mistyped Anthropic name is refused at the check.
    """
    tabela, orcamento = tabela_precos(root), ler_orcamento(root)
    permitidos = []
    for modelo in orcamento['modelos_permitidos']:
        provedor, valor = preco(root, modelo, tabela)
        permitidos.append({'modelo': modelo, 'provedor': provedor or SEM_PRECO, 'preco_estimado': valor is None})
    return permitidos


def conferir_modelo(root, provedor, modelo):
    """Refuse a model outside the installation's list (CUS-03), at configuration and at the question."""
    permitidos = modelos_permitidos(root)
    if not any(p['modelo'] == modelo and p['provedor'] == provedor for p in permitidos):
        nomes = ', '.join(p['modelo'] for p in permitidos if p['provedor'] == provedor) or 'nenhum deste provedor'
        raise ValueError(f'O modelo {modelo} não está entre os permitidos nesta instalação ({nomes}). A configuração '
                         'anterior foi mantida; escolha um dos permitidos ou peça ao dono da instalação.')


# --- uso e preço --------------------------------------------------------------------------------

def _inteiro(valor):
    return valor if type(valor) is int and valor >= 0 else 0


def uso_normalizado(uso) -> dict:
    """The priced kinds of one call (or of a sum of calls) from the adapters' usage dict.

    Older or simulated usage with only ``entrada``/``saida`` counts ``entrada`` as uncached input,
    and a total ``cache_escrita`` without validities as 5-minute writes (the Anthropic default).
    """
    uso = uso or {}
    tokens = {'entrada_sem_cache': _inteiro(uso.get('entrada_sem_cache', uso.get('entrada'))),
              'cache_leitura': _inteiro(uso.get('cache_leitura')), 'saida': _inteiro(uso.get('saida'))}
    escritas = {k: _inteiro(v) for k, v in uso.items() if ESCRITA.fullmatch(k)}
    if not escritas and _inteiro(uso.get('cache_escrita')):
        escritas = {'cache_escrita_5m': _inteiro(uso['cache_escrita'])}
    return {**tokens, **escritas}


def tokens_totais(uso) -> int:
    """Every token of the usage, cache included (the token limits count them all, CUS-01)."""
    return sum(uso_normalizado(uso).values())


def _preco_da_escrita(valor, tipo, tabela=None):
    """Price of a cache write of validity ``tipo``; (price, estimated) when the model lacks it."""
    if tipo in valor:
        return valor[tipo], False
    proprias = [v for k, v in valor.items() if ESCRITA.fullmatch(k)]
    if proprias:
        return max(proprias), True
    todas = [v for k, v in preco_maximo(tabela).items() if ESCRITA.fullmatch(k)] if tabela else []
    return (max(todas) if todas else valor['entrada'] * 2), True


def custo_usd(uso, valor, tabela=None, estimado=None) -> Decimal:
    """Dollars of ``uso`` at ``valor`` (prices per million tokens of each kind). ``estimado``, a
    list, gets True when a cache write was counted at a price the model does not list."""
    tokens, total = uso_normalizado(uso), Decimal(0)
    for tipo, quantidade in tokens.items():
        if tipo in PRECO_DE:
            preco_tipo = valor[PRECO_DE[tipo]]
        else:
            preco_tipo, suposto = _preco_da_escrita(valor, tipo, tabela)
            if suposto and quantidade and estimado is not None:
                estimado.append(True)
        total += Decimal(quantidade) * Decimal(str(preco_tipo))
    return total / MICRO


def cambio(root, tabela=None) -> Decimal:
    configurado = ler_orcamento(root)['cambio_brl_por_usd']
    return Decimal(str(configurado if configurado is not None else (tabela or tabela_precos(root))['cambio']['brl_por_usd']))


def custo_da_chamada(root, modelo, uso, modelo_cobrado=None) -> dict:
    """The record of one call's cost: dollars, reais, rate, the price used and the table's date.

    The price is that of the model the provider reported; if it is not in the table, that of the
    model the question was started with (``modelo_cobrado``); if neither, the most expensive in the
    table: a cost is never left out.
    """
    tabela = tabela_precos(root)
    usado, valor = modelo, preco(root, modelo, tabela)[1] if modelo else None
    if valor is None and modelo_cobrado:
        usado, valor = modelo_cobrado, preco(root, modelo_cobrado, tabela)[1]
    estimado = valor is None
    if estimado:
        valor = preco_maximo(tabela)
        usado = f'preço mais alto da tabela em cada tipo (sem preço: {modelo or modelo_cobrado or "modelo não informado"})'
        log.warning('Custo estimado pelo preço mais alto da tabela: o modelo %s não tem preço em %s.',
                    modelo or modelo_cobrado, TABELA)
    taxa = cambio(root, tabela)
    suposto = []
    usd = custo_usd(uso, valor, tabela, suposto)
    estimado = estimado or bool(suposto)
    brl = usd * taxa
    return {'usd': str(usd.quantize(Decimal('0.000001'), ROUND_HALF_UP)),
            'brl': str(brl.quantize(Decimal('0.000001'), ROUND_HALF_UP)),
            'micro_brl': int((brl * MICRO).to_integral_value(ROUND_HALF_UP)),
            'cambio_brl_por_usd': str(taxa), 'preco_de': usado, 'preco_estimado': estimado,
            'tabela_vigente_em': tabela['vigente_em'], 'tokens': uso_normalizado(uso)}


def estimativa_minima_brl(root, modelo) -> Decimal:
    """Reais of a short question at ``modelo``'s uncached input and output prices."""
    estimativa = ler_orcamento(root)['estimativa_minima_tokens']
    tabela = tabela_precos(root)
    _, valor = preco(root, modelo, tabela)
    if valor is None:
        valor = preco_maximo(tabela)  # an unpriced model is counted at the highest prices
    uso = {'entrada': estimativa['entrada'], 'saida': estimativa['saida']}
    return custo_usd(uso, valor) * cambio(root)


# --- gasto do mês -------------------------------------------------------------------------------

def mes() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m')


def chaves_orcamento(conta) -> dict:
    """Ponto único: whose budgets a question spends. Today the account and the installation."""
    return {'conta': conta if isinstance(conta, str) and conta else CONTA_LOCAL, 'organizacao': ORGANIZACAO}


def _arquivo(root) -> Path:
    return Path(root) / 'ajustes' / 'gasto_mensal.json'


def _reserva(root) -> Path:
    return Path(root) / 'ajustes' / 'gasto_mensal.anterior.json'


def _vazio():
    return {'esquema': 1, 'moeda': 'BRL', 'unidade': 'milionesimos de real', 'meses': {}}


def _registro(caminho):
    """The ledger at ``caminho``; None when absent; ValueError when unreadable or malformed."""
    try:
        dados = json.loads(caminho.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(dados, dict) or not isinstance(dados.get('meses'), dict):
        raise ValueError('estrutura inválida')
    for quando, atual in dados['meses'].items():
        if not isinstance(atual, dict) or any(
                not isinstance(atual.get(grupo), dict)
                or any(type(v) is not int or v < 0 for v in atual[grupo].values())
                for grupo in ('contas', 'organizacoes')):
            raise ValueError(f'mês {quando} danificado')
    return dados


def _ler_gasto(root) -> dict:
    """This installation's ledger. Unreadable: the previous copy; neither readable: GastoSemRegistro."""
    try:
        dados, defeito = _registro(_arquivo(root)), None
    except ValueError as exc:
        dados, defeito = None, exc
    if dados is not None:
        return dados
    try:
        anterior = _registro(_reserva(root))
    except ValueError:
        anterior = None
    if anterior is not None:
        if defeito is not None:
            log.warning('Registro do gasto mensal ilegível (%s); lido da cópia anterior.', defeito)
        return anterior
    if defeito is None and not _reserva(root).exists():
        return _vazio()  # nothing was ever spent here
    log.warning('Registro do gasto mensal ilegível e sem cópia anterior legível (%s): cota tratada como esgotada.',
                defeito or 'cópia anterior ilegível')
    raise GastoSemRegistro(MENSAGEM_ILEGIVEL)


def _do_mes(dados, quando):
    atual = dados['meses'].get(quando)
    if not isinstance(atual, dict):
        atual = {'contas': {}, 'organizacoes': {}}
    for chave in ('contas', 'organizacoes'):
        if not isinstance(atual.get(chave), dict):
            atual[chave] = {}
    return atual


def gasto(root, conta) -> dict:
    """{'conta': micro-reais, 'organizacao': micro-reais} spent this month."""
    chaves = chaves_orcamento(conta)
    atual = _do_mes(_ler_gasto(root), mes())
    valor = lambda d, k: d.get(k) if type(d.get(k)) is int and d.get(k) >= 0 else 0  # noqa: E731
    return {'conta': valor(atual['contas'], chaves['conta']), 'organizacao': valor(atual['organizacoes'], chaves['organizacao'])}


def somar_gasto(root, conta, micro_brl) -> dict:
    """Add one call's cost to this month's account and organization; returns the new totals."""
    chaves, quando = chaves_orcamento(conta), mes()
    pendente = (str(Path(root).resolve()), quando, chaves['conta'])
    try:
        return _somar(root, chaves, quando, micro_brl)
    except (OSError, GastoSemRegistro) as exc:  # no question goes on without its count (R1)
        with _TRAVA:  # kept, and added at the first write that works (the call was spent)
            _PENDENTES[pendente] = _PENDENTES.get(pendente, 0) + max(0, int(micro_brl))
        if isinstance(exc, GastoSemRegistro):
            raise
        log.warning('Gasto do mês não gravado: %s', exc)
        raise GastoSemRegistro(MENSAGEM_SEM_GRAVAR) from exc


def _somar(root, chaves, quando, micro_brl):
    with _TRAVA, trava_arquivo(_arquivo(root)):
        dados = _ler_gasto(root)
        raiz = str(Path(root).resolve())
        guardados = {k: v for k, v in _PENDENTES.items() if k[0] == raiz}
        for (_, mes_pendente, conta_pendente), valor in guardados.items():
            atrasado = _do_mes(dados, mes_pendente)
            for grupo, chave in (('contas', conta_pendente), ('organizacoes', chaves['organizacao'])):
                atrasado[grupo][chave] = atrasado[grupo].get(chave, 0) + valor
            dados['meses'][mes_pendente] = atrasado
        atual = _do_mes(dados, quando)
        for grupo, chave in (('contas', chaves['conta']), ('organizacoes', chaves['organizacao'])):
            atual[grupo][chave] = atual[grupo].get(chave, 0) + max(0, int(micro_brl))
        dados['meses'][quando] = atual
        for antigo in sorted(dados['meses'])[:-MESES_GUARDADOS]:
            del dados['meses'][antigo]
        conteudo = (json.dumps(dados, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
        _arquivo(root).parent.mkdir(parents=True, exist_ok=True)
        _atomico(_arquivo(root), conteudo)
        _atomico(_reserva(root), conteudo)  # the copy an unreadable ledger is read from
        for chave in guardados:  # recorded now
            _PENDENTES.pop(chave, None)
        if guardados:
            log.warning('Gasto do mês: %s chamada(s) que não tinham sido gravadas foram somadas agora.', len(guardados))
        return {'conta': atual['contas'][chaves['conta']], 'organizacao': atual['organizacoes'][chaves['organizacao']]}


# --- cota ---------------------------------------------------------------------------------------

def reais(valor) -> str:
    """R$ notation of the interface (comma for decimals, dot for thousands)."""
    texto = f'{Decimal(valor).quantize(Decimal("0.01"), ROUND_HALF_UP):,.2f}'
    return texto.replace(',', '_').replace('.', ',').replace('_', '.')


def mensagem_cota_conta(usado, teto) -> str:
    return (f'Sua cota do mês acabou. Você usou R$ {reais(usado)} de R$ {reais(teto)}. '
            'Documentos, conferência e caderno seguem funcionando.')


def mensagem_cota_organizacao(usado=None, teto=None) -> str:
    valores = f' Foram usados R$ {reais(usado)} de R$ {reais(teto)}.' if usado is not None else ''
    return (f'A cota do mês da instalação acabou.{valores} Documentos, conferência e caderno seguem '
            'funcionando; o dono da instalação pode ampliar a cota.')


def situacao(root, conta, *, administrador=False) -> dict:
    """This month's spend and balance in reais (the quota bar of the interface).

    A guest sees only their own account; an administrator also sees the organization.
    """
    orcamento, gastos = ler_orcamento(root), gasto(root, conta)
    teto_conta, teto_org = Decimal(str(orcamento['mensal_por_conta_brl'])), Decimal(str(orcamento['mensal_organizacao_brl']))
    usado_conta, usado_org = Decimal(gastos['conta']) / MICRO, Decimal(gastos['organizacao']) / MICRO
    tabela = tabela_precos(root)

    def bloco(usado, teto):
        centavos = usado.quantize(Decimal('0.01'), ROUND_HALF_UP)  # spend and balance add up to the ceiling
        return {'gasto_brl': str(centavos), 'teto_brl': str(teto.quantize(Decimal('0.01'))),
                'saldo_brl': str(max(Decimal(0), teto - centavos).quantize(Decimal('0.01'))), 'esgotada': usado >= teto}
    resposta = {'mes': mes(), 'moeda': 'BRL', 'conta': bloco(usado_conta, teto_conta),
                'cambio_brl_por_usd': str(cambio(root, tabela)), 'tabela_vigente_em': tabela['vigente_em']}
    if administrador:
        resposta['organizacao'] = bloco(usado_org, teto_org)
    return resposta


def conferir_antes(root, conta, modelo, *, convidado=False):
    """Refuse the question before it starts when a balance does not cover the minimum estimate, or
    when the month's spend cannot be read or recorded (an unrecorded spend would have no ceiling)."""
    somar_gasto(root, conta, 0)  # writes the ledger again: GastoSemRegistro when it cannot
    orcamento, gastos = ler_orcamento(root), gasto(root, conta)
    estimativa = estimativa_minima_brl(root, modelo)
    teto_conta, teto_org = Decimal(str(orcamento['mensal_por_conta_brl'])), Decimal(str(orcamento['mensal_organizacao_brl']))
    usado_conta, usado_org = Decimal(gastos['conta']) / MICRO, Decimal(gastos['organizacao']) / MICRO
    if usado_conta >= teto_conta or usado_conta + estimativa > teto_conta:
        raise CotaEsgotada(mensagem_cota_conta(usado_conta, teto_conta))
    if usado_org >= teto_org or usado_org + estimativa > teto_org:
        raise CotaEsgotada(mensagem_cota_organizacao(None if convidado else usado_org, None if convidado else teto_org))


def estouro(root, totais, *, convidado=False):
    """The message when this month's totals (``somar_gasto``) reached a ceiling, else None."""
    orcamento = ler_orcamento(root)
    teto_conta, teto_org = Decimal(str(orcamento['mensal_por_conta_brl'])), Decimal(str(orcamento['mensal_organizacao_brl']))
    usado_conta, usado_org = Decimal(totais['conta']) / MICRO, Decimal(totais['organizacao']) / MICRO
    if usado_conta >= teto_conta:
        return 'limite_cota_conta', mensagem_cota_conta(usado_conta, teto_conta)
    if usado_org >= teto_org:
        return 'limite_cota_organizacao', mensagem_cota_organizacao(None if convidado else usado_org,
                                                                   None if convidado else teto_org)
    return None
