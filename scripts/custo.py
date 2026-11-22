"""Custo das perguntas em dinheiro (CUS-01, CUS-03): preço por tipo de token, cota mensal em reais.

**Preço.** ``precos_modelos.json`` (versionado, com data e fonte) dá, por provedor e modelo, o
preço em dólar por milhão de tokens de cada tipo: entrada sem cache, leitura de cache, escrita de
cache com validade de 5 minutos e de 1 hora, e saída (o raciocínio é cobrado como saída). Os
adaptadores (``provedor_*``) entregam o uso de cada chamada já separado nesses tipos; a OpenAI
conta o cache dentro da entrada e não cobra escrita. Modelo sem preço na tabela não pode ser
permitido: nenhum gasto fica sem conta.

**Cota.** Teto mensal em reais por conta (o administrador também tem a sua) e da organização,
hoje a instalação inteira (``chaves_orcamento`` é o ponto único que a Onda 2 refina). O gasto de
cada chamada é convertido pelo câmbio do momento e somado em ``ajustes/gasto_mensal.json``, em
milionésimos de real; o mês é o do calendário em UTC. Uma pergunta é recusada antes de começar
quando o saldo não cobre a estimativa mínima, e interrompida quando o gasto passa do teto.

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
from pathlib import Path
import threading

from cadastrar_documentos import _atomico
from comum import ROOT, ler_json, trava_arquivo

TABELA = 'precos_modelos.json'
TIPOS = ('entrada_sem_cache', 'cache_leitura', 'cache_escrita_5m', 'cache_escrita_1h', 'saida')
PRECO_DE = {'entrada_sem_cache': 'entrada', 'cache_leitura': 'cache_leitura', 'cache_escrita_5m': 'cache_escrita_5m',
            'cache_escrita_1h': 'cache_escrita_1h', 'saida': 'saida'}
CHAVES_ORCAMENTO = ('mensal_por_conta_brl', 'mensal_organizacao_brl', 'estimativa_minima_tokens',
                    'execucoes_simultaneas_por_conta', 'execucoes_simultaneas', 'modelos_permitidos')
ORGANIZACAO = 'instalacao'  # the one organization until Onda 2 (accounts and organizations)
CONTA_LOCAL = 'local'  # the single operator of the local mode
MICRO = Decimal(1_000_000)
MESES_GUARDADOS = 12
_TRAVA = threading.Lock()


class CotaEsgotada(ValueError):
    """The month's quota does not cover the question (W11 'limite' block)."""


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
            if not isinstance(preco, dict) or set(preco) != set(PRECO_DE.values()) or not all(
                    type(v) in (int, float) and not isinstance(v, bool) and v >= 0 for v in preco.values()):
                raise ValueError(f'{TABELA}: preço de {modelo} precisa de entrada, cache_leitura, '
                                 'cache_escrita_5m, cache_escrita_1h e saida, em dólar por milhão de tokens.')
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


def modelos_permitidos(root) -> list:
    """{'modelo', 'provedor'} of each model the installation allows; each one has a price."""
    tabela, orcamento = tabela_precos(root), ler_orcamento(root)
    permitidos = []
    for modelo in orcamento['modelos_permitidos']:
        provedor, valor = preco(root, modelo, tabela)
        if valor is None:
            raise ValueError(f'O modelo {modelo} está em orcamento.modelos_permitidos sem preço em {TABELA}: '
                             'cadastre o preço antes de permitir o modelo.')
        permitidos.append({'modelo': modelo, 'provedor': provedor})
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
    """The five priced kinds of one call (or of a sum of calls) from the adapters' usage dict.

    Older or simulated usage with only ``entrada``/``saida`` counts ``entrada`` as uncached input.
    """
    uso = uso or {}
    escrita_1h = _inteiro(uso.get('cache_escrita_1h'))
    escrita_5m = (_inteiro(uso['cache_escrita_5m']) if 'cache_escrita_5m' in uso
                  else max(0, _inteiro(uso.get('cache_escrita')) - escrita_1h))
    return {'entrada_sem_cache': _inteiro(uso.get('entrada_sem_cache', uso.get('entrada'))),
            'cache_leitura': _inteiro(uso.get('cache_leitura')), 'cache_escrita_5m': escrita_5m,
            'cache_escrita_1h': escrita_1h, 'saida': _inteiro(uso.get('saida'))}


def tokens_totais(uso) -> int:
    """Every token of the usage, cache included (the token limits count them all, CUS-01)."""
    return sum(uso_normalizado(uso).values())


def custo_usd(uso, valor) -> Decimal:
    """Dollars of ``uso`` at ``valor`` (prices per million tokens of each kind)."""
    tokens = uso_normalizado(uso)
    return sum((Decimal(tokens[tipo]) * Decimal(str(valor[PRECO_DE[tipo]])) for tipo in TIPOS), Decimal(0)) / MICRO


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
    if valor is None:
        candidatos = [(m, p) for lista in tabela['modelos'].values() for m, p in lista.items()]
        usado, valor = max(candidatos, key=lambda c: (c[1]['saida'], c[1]['entrada']))
        usado = f'{usado} (preço mais alto da tabela: modelo informado sem preço)'
    taxa = cambio(root, tabela)
    usd = custo_usd(uso, valor)
    brl = usd * taxa
    return {'usd': str(usd.quantize(Decimal('0.000001'), ROUND_HALF_UP)),
            'brl': str(brl.quantize(Decimal('0.000001'), ROUND_HALF_UP)),
            'micro_brl': int((brl * MICRO).to_integral_value(ROUND_HALF_UP)),
            'cambio_brl_por_usd': str(taxa), 'preco_de': usado, 'tabela_vigente_em': tabela['vigente_em'],
            'tokens': uso_normalizado(uso)}


def estimativa_minima_brl(root, modelo) -> Decimal:
    """Reais of a short question at ``modelo``'s uncached input and output prices."""
    estimativa = ler_orcamento(root)['estimativa_minima_tokens']
    _, valor = preco(root, modelo)
    if valor is None:
        return Decimal(0)
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


def _ler_gasto(root) -> dict:
    try:
        dados = json.loads(_arquivo(root).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        dados = None  # a damaged ledger restarts empty; the per-call records stay in the rounds
    if not isinstance(dados, dict) or not isinstance(dados.get('meses'), dict):
        dados = {'esquema': 1, 'moeda': 'BRL', 'unidade': 'milionesimos de real', 'meses': {}}
    return dados


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
    with _TRAVA, trava_arquivo(_arquivo(root)):
        dados = _ler_gasto(root)
        atual = _do_mes(dados, quando)
        for grupo, chave in (('contas', chaves['conta']), ('organizacoes', chaves['organizacao'])):
            anterior = atual[grupo].get(chave)
            atual[grupo][chave] = (anterior if type(anterior) is int and anterior >= 0 else 0) + max(0, int(micro_brl))
        dados['meses'][quando] = atual
        for antigo in sorted(dados['meses'])[:-MESES_GUARDADOS]:
            del dados['meses'][antigo]
        _arquivo(root).parent.mkdir(parents=True, exist_ok=True)
        _atomico(_arquivo(root), (json.dumps(dados, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
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
    """Refuse the question before it starts when a balance does not cover the minimum estimate."""
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
