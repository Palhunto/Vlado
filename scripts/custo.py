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

**Cota (contrato de contas, 8.5).** Três tetos mensais em reais, mais o do painel do provedor:
da pessoa (o próprio, definido pelo dono; sem ele, o padrão de cada pessoa da redação; sem esse,
``mensal_por_conta_brl``), da redação (``cota_mensal_brl``, definido pelo operador; sem ele,
``mensal_organizacao_brl``) e da instalação (``mensal_instalacao_brl``, a soma que o serviço aceita
pagar; ``null`` deixa só os outros dois). ``chaves_orcamento`` é o ponto único que diz de quem é o
gasto: a conta e a redação dela, lida do armazenamento de contas (``acesso``); sem contas (modo
local), conta desconhecida ou a redação inicial, ``instalacao`` (a redação inicial herdou o que era
da instalação, e a chave do registro não muda). Os tetos vêm de ``acesso.tetos_de_custo``. O gasto
de cada chamada é convertido pelo câmbio do momento e somado em ``ajustes/gasto_mensal.json``, em
milionésimos de real, na conta e na redação; o da instalação é a soma das redações. O mês é o do
calendário em UTC. Uma pergunta é recusada antes de começar quando o saldo não cobre a estimativa
mínima, e interrompida quando o gasto passa de um teto. Quem vê número: a pessoa, o próprio gasto
sempre; o da redação, só quem a rota diz que vê (``ve_redacao``, o dono); o da instalação, ninguém.
A frase de um teto atingido no meio da pergunta vai para a conversa, que os colegas da apuração leem:
nunca leva número (``estouro``); os números ficam na barra e na recusa direta.

**Chave própria da redação (contrato 8.5).** Uma pergunta feita com a chave que a redação cadastrou
(``segredos``) não é paga pelo serviço: o gasto cai na pessoa (o teto dela continua valendo, como
definido, sem o limite da cota da redação) e num lançamento separado da redação
(``chaves_proprias``), fora da cota paga pelo serviço e fora da soma da instalação.

**Gasto sem redação própria.** O gasto sem conta (modo local, ou uma chamada sem conta) e o gasto já
gravado antes desta versão ficam na chave ``instalacao``, a da redação inicial: contam para o teto e a
barra dela e para a soma da instalação, e nunca são redistribuídos. No mês da atualização, se outra
redação já tiver gastado antes dela (só se as contas tiverem rodado sem esta versão), esse gasto fica
somado ao da redação inicial até o mês virar, e o dono da redação inicial o vê na barra dela.

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
``execucoes_simultaneas_por_conta``, ``execucoes_simultaneas_por_organizacao`` (de cada redação nos
modos com contas; ``null``, o padrão, deixa só o total), ``execucoes_simultaneas`` (o total da
instalação), ``mensal_instalacao_brl`` e ``modelos_permitidos``. Cada um
pode ser sobreposto na instalação por ``configuracao.json`` → ``"orcamento"``, que aceita também
``cambio_brl_por_usd``.
Nenhuma chamada de modelo nem de rede.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
import json
import math
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
CHAVES_ORCAMENTO = ('mensal_por_conta_brl', 'mensal_organizacao_brl', 'mensal_instalacao_brl',
                    'estimativa_minima_tokens', 'execucoes_simultaneas_por_conta',
                    'execucoes_simultaneas_por_organizacao', 'execucoes_simultaneas', 'modelos_permitidos')
# Ledger key of the local mode and of the installation's first newsroom (it inherited the installation's spend).
ORGANIZACAO = 'instalacao'
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
    if resultado['mensal_instalacao_brl'] is not None:  # null: no ceiling of the installation above the newsrooms'
        _numero_positivo(resultado['mensal_instalacao_brl'], 'mensal_instalacao_brl')
    if resultado['cambio_brl_por_usd'] is not None:
        _numero_positivo(resultado['cambio_brl_por_usd'], 'cambio_brl_por_usd')
    for nome in ('execucoes_simultaneas_por_conta', 'execucoes_simultaneas'):
        _inteiro_positivo(resultado[nome], nome)
    if resultado['execucoes_simultaneas_por_organizacao'] is not None:  # null: only the installation's total
        _inteiro_positivo(resultado['execucoes_simultaneas_por_organizacao'], 'execucoes_simultaneas_por_organizacao')
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


def chaves_orcamento(conta, root=None) -> dict:
    """Ponto único: whose budgets a question spends, the account and its newsroom (accounts contract 8.5).

    Without ``root`` (or without accounts) the newsroom is ``instalacao``. Raises ValueError when the
    account store cannot be read: a spend is never put on a guessed newsroom."""
    return {'conta': conta if isinstance(conta, str) and conta else CONTA_LOCAL,
            'organizacao': organizacao(root, conta) if root is not None else ORGANIZACAO}


def _com_contas(root) -> bool:
    """The account store exists (modes with accounts). Never created here."""
    import acesso
    return acesso.caminho_bd(Path(root)).is_file()


def organizacao(root, conta) -> str:
    """The newsroom key of the ledger for ``conta``: its newsroom id, or ``instalacao`` (local mode, unknown
    account, the installation's first newsroom)."""
    if not isinstance(conta, str) or not conta or conta == CONTA_LOCAL or not _com_contas(root):
        return ORGANIZACAO
    import acesso
    redacao = acesso.organizacao_da_conta(Path(root), conta)
    if redacao is None or redacao == acesso.organizacao_inicial(Path(root)):
        return ORGANIZACAO
    return redacao


def redacao_do_gasto(root, conta) -> str | None:
    """The id of the newsroom whose budget ``conta`` spends (the first newsroom included, whose ledger key stays
    ``instalacao``); None without accounts or for an unknown account. The ``organizacao`` block of ``situacao`` is
    always this newsroom's, never the installation's total: ``autorizacao.gasto_da_redacao`` relies on it."""
    if not isinstance(conta, str) or not conta or conta == CONTA_LOCAL or not _com_contas(root):
        return None
    import acesso
    return acesso.organizacao_da_conta(Path(root), conta)


def tetos(root, conta, orcamento=None) -> dict:
    """This month's ceilings in reais (Decimal): ``conta`` (the person's, never above the newsroom's),
    ``pessoa`` (the person's as set, which is all a person who does not see the newsroom is shown: the lower
    of the two could be the newsroom's), ``organizacao`` (the newsroom's) and ``instalacao`` (None: none)."""
    orcamento = orcamento or ler_orcamento(root)
    proprios = {}
    if isinstance(conta, str) and conta and conta != CONTA_LOCAL and _com_contas(root):
        import acesso
        proprios = acesso.tetos_de_custo(Path(root), conta) or {}
    redacao = Decimal(proprios['redacao_brl']) if proprios.get('redacao_brl') else Decimal(str(orcamento['mensal_organizacao_brl']))
    pessoa = Decimal(proprios['pessoa_brl']) if proprios.get('pessoa_brl') else Decimal(str(orcamento['mensal_por_conta_brl']))
    instalacao = orcamento['mensal_instalacao_brl']
    return {'conta': min(pessoa, redacao), 'pessoa': pessoa, 'organizacao': redacao,
            'instalacao': Decimal(str(instalacao)) if instalacao is not None else None}


def _arquivo(root) -> Path:
    return Path(root) / 'ajustes' / 'gasto_mensal.json'


def _reserva(root) -> Path:
    return Path(root) / 'ajustes' / 'gasto_mensal.anterior.json'


def _marca(root) -> Path:
    """Written when the copy could not be updated: the generation a copy needs to be read."""
    return Path(root) / 'ajustes' / 'gasto_mensal.anterior.invalida.json'


def _geracao(dados) -> int:
    return dados.get('geracao', 0)  # a ledger from before the generations: 0


def _geracao_minima(root):
    """None without the mark; else the generation a copy needs (an unreadable mark: no copy is read)."""
    try:
        marca = json.loads(_marca(root).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return math.inf
    valor = marca.get('geracao_minima') if isinstance(marca, dict) else None
    return valor if type(valor) is int and valor >= 0 else math.inf


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
    if 'geracao' in dados and (type(dados['geracao']) is not int or dados['geracao'] < 0):
        raise ValueError('geração inválida')
    for quando, atual in dados['meses'].items():
        if not isinstance(atual, dict) or any(
                not isinstance(atual.get(grupo), dict)
                or any(type(v) is not int or v < 0 for v in atual[grupo].values())
                for grupo in ('contas', 'organizacoes')):
            raise ValueError(f'mês {quando} danificado')
        proprias = atual.get('chaves_proprias', {})  # optional: months before the newsroom's own key lack it
        if not isinstance(proprias, dict) or any(type(v) is not int or v < 0 for v in proprias.values()):
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
    minima = _geracao_minima(root)
    if anterior is not None and minima is not None and _geracao(anterior) < minima:
        log.warning('Cópia anterior do gasto mensal mais velha que o registro (geração %s, mínima %s): '
                    'não vale no lugar dele.', _geracao(anterior), minima)
        anterior = None  # it would count less than the ledger it stands in for
    if anterior is not None:
        if defeito is not None:
            log.warning('Registro do gasto mensal ilegível (%s); lido da cópia anterior.', defeito)
        return anterior
    if defeito is None and not _reserva(root).exists() and minima is None:
        return _vazio()  # nothing was ever spent here
    log.warning('Registro do gasto mensal ilegível e sem cópia anterior legível (%s): cota tratada como esgotada.',
                defeito or 'cópia anterior ilegível')
    raise GastoSemRegistro(MENSAGEM_ILEGIVEL)


def _do_mes(dados, quando):
    atual = dados['meses'].get(quando)
    if not isinstance(atual, dict):
        atual = {'contas': {}, 'organizacoes': {}}
    for chave in ('contas', 'organizacoes', 'chaves_proprias'):
        if not isinstance(atual.get(chave), dict):
            atual[chave] = {}
    return atual


def _grupo_da_redacao(chave_propria) -> str:
    """Where a call's newsroom spend goes: the service's quota, or the separate entry of its own key."""
    return 'chaves_proprias' if chave_propria else 'organizacoes'


def _totais(atual, chaves) -> dict:
    valor = lambda d, k: d.get(k) if type(d.get(k)) is int and d.get(k) >= 0 else 0  # noqa: E731
    return {'conta': valor(atual['contas'], chaves['conta']),
            'organizacao': valor(atual['organizacoes'], chaves['organizacao']),
            'instalacao': sum(v for v in atual['organizacoes'].values() if type(v) is int and v >= 0)}


def gasto_chave_propria(root, conta, chaves=None) -> int:
    """Micro-reais the newsroom of ``conta`` spent this month with its own key (not paid by the service)."""
    chaves = chaves or chaves_orcamento(conta, root)
    valor = _do_mes(_ler_gasto(root), mes())['chaves_proprias'].get(chaves['organizacao'])
    return valor if type(valor) is int and valor >= 0 else 0


def gasto(root, conta, chaves=None) -> dict:
    """{'conta', 'organizacao', 'instalacao': micro-reais} spent this month (the installation: all newsrooms)."""
    chaves = chaves or chaves_orcamento(conta, root)
    return _totais(_do_mes(_ler_gasto(root), mes()), chaves)


def somar_gasto(root, conta, micro_brl, chaves=None, *, chave_propria=False) -> dict:
    """Add one call's cost to this month's account and newsroom; returns the new totals (``gasto``).

    ``chave_propria``: the call used the newsroom's own key: the newsroom's part goes to its separate entry, not to
    the service's quota nor to the installation's sum."""
    chaves, quando = chaves or chaves_orcamento(conta, root), mes()
    pendente = (str(Path(root).resolve()), quando, chaves['conta'], chaves['organizacao'], bool(chave_propria))
    try:
        return _somar(root, chaves, quando, micro_brl, bool(chave_propria))
    except (OSError, GastoSemRegistro) as exc:  # no question goes on without its count (R1)
        with _TRAVA:  # kept, and added at the first write that works (the call was spent)
            _PENDENTES[pendente] = _PENDENTES.get(pendente, 0) + max(0, int(micro_brl))
        if isinstance(exc, GastoSemRegistro):
            raise
        log.warning('Gasto do mês não gravado: %s', exc)
        raise GastoSemRegistro(MENSAGEM_SEM_GRAVAR) from exc


def _somar(root, chaves, quando, micro_brl, chave_propria=False):
    with _TRAVA, trava_arquivo(_arquivo(root)):
        dados = _ler_gasto(root)
        raiz = str(Path(root).resolve())
        guardados = {k: v for k, v in _PENDENTES.items() if k[0] == raiz}
        for (_, mes_pendente, conta_pendente, organizacao_pendente, propria), valor in guardados.items():
            atrasado = _do_mes(dados, mes_pendente)
            for grupo, chave in (('contas', conta_pendente), (_grupo_da_redacao(propria), organizacao_pendente)):
                atrasado[grupo][chave] = atrasado[grupo].get(chave, 0) + valor
            dados['meses'][mes_pendente] = atrasado
        atual = _do_mes(dados, quando)
        for grupo, chave in (('contas', chaves['conta']), (_grupo_da_redacao(chave_propria), chaves['organizacao'])):
            atual[grupo][chave] = atual[grupo].get(chave, 0) + max(0, int(micro_brl))
        dados['meses'][quando] = atual
        for antigo in sorted(dados['meses'])[:-MESES_GUARDADOS]:
            del dados['meses'][antigo]
        dados['geracao'] = _geracao(dados) + 1
        conteudo = (json.dumps(dados, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
        _arquivo(root).parent.mkdir(parents=True, exist_ok=True)
        _atomico(_arquivo(root), conteudo)
        for chave in guardados:  # recorded in the ledger now, whatever happens to its copy
            _PENDENTES.pop(chave, None)
        if guardados:
            log.warning('Gasto do mês: %s chamada(s) que não tinham sido gravadas foram somadas agora.', len(guardados))
        try:  # the copy an unreadable ledger is read from; few tries: the mark covers a failure
            _atomico(_reserva(root), conteudo, tentativas=4)
        except OSError as exc:
            _copia_velha(root, dados['geracao'], exc)
        else:
            try:
                _marca(root).unlink(missing_ok=True)
            except OSError:
                pass  # the copy is as new as the mark or newer: read all the same
        return _totais(atual, chaves)


def _copia_velha(root, geracao, exc):
    """The spend is in the ledger; only its copy is stale, and must never stand in for it (it would
    count less). Marked first, then removed: Windows neither replaces nor removes a read-only file,
    and the mark holds all the same. Without a readable copy, an unreadable ledger exhausts the quota."""
    marcada = removida = False
    try:
        _atomico(_marca(root), (json.dumps({'esquema': 1, 'geracao_minima': geracao}) + '\n').encode('utf-8'))
        marcada = True
    except OSError:
        pass
    try:
        _reserva(root).unlink(missing_ok=True)
        removida = True
    except OSError:
        pass
    if marcada or removida:
        log.warning('Cópia anterior do gasto do mês não gravada (%s); %s para não valer no lugar do registro.', exc,
                    'marcada como velha' + (' e removida' if removida else '') if marcada else 'removida')
    else:
        log.error('Cópia anterior do gasto do mês não gravada, nem marcada como velha, nem removida (%s): se o '
                  'registro ficar ilegível, ela contaria menos. Confira as permissões de ajustes/.', exc)


# --- cota ---------------------------------------------------------------------------------------

def reais(valor) -> str:
    """R$ notation of the interface (comma for decimals, dot for thousands)."""
    texto = f'{Decimal(valor).quantize(Decimal("0.01"), ROUND_HALF_UP):,.2f}'
    return texto.replace(',', '_').replace('.', ',').replace('_', '.')


def mensagem_cota_conta(usado, teto) -> str:
    return (f'Sua cota do mês acabou. Você usou R$ {reais(usado)} de R$ {reais(teto)}. '
            'Documentos, conferência e caderno seguem funcionando.')


def mensagem_cota_pessoa() -> str:
    """The person's ceiling reached in the middle of a question: it goes to the conversation's events, which the
    colleagues of the case read, so it never carries a number (the asker sees them in the quota bar)."""
    return 'A cota do mês de quem fez a pergunta acabou. Documentos, conferência e caderno seguem funcionando.'


def mensagem_cota_organizacao(usado=None, teto=None, *, redacao=False) -> str:
    valores = f' Foram usados R$ {reais(usado)} de R$ {reais(teto)}.' if usado is not None else ''
    if redacao:
        return (f'A cota do mês da redação acabou.{valores} Documentos, conferência e caderno seguem '
                'funcionando; o dono da redação pode pedir ao operador uma cota maior.')
    return (f'A cota do mês da instalação acabou.{valores} Documentos, conferência e caderno seguem '
            'funcionando; o dono da instalação pode ampliar a cota.')


def mensagem_cota_instalacao() -> str:
    """Never with a number: it adds up every newsroom (accounts contract, 4.5)."""
    return ('A cota do mês da Mesa acabou. Documentos, conferência e caderno seguem funcionando; '
            'o operador pode ampliar a cota.')


def _numeros_da_redacao(convidado, ve_redacao) -> bool:
    return bool(ve_redacao) if ve_redacao is not None else not convidado


def situacao(root, conta, *, administrador=False) -> dict:
    """This month's spend and balance in reais (the quota bar of the interface).

    Each account sees its own; whoever sees the newsroom (``administrador``: the dono) also sees it.
    The installation's total is never shown.
    """
    orcamento, chaves = ler_orcamento(root), chaves_orcamento(conta, root)
    gastos, limite = gasto(root, conta, chaves), tetos(root, conta, orcamento)
    # Whoever does not see the newsroom is shown the own ceiling as set, never the lower newsroom's.
    teto_conta, teto_org = limite['conta' if administrador else 'pessoa'], limite['organizacao']
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


def _teto_batido(root, conta, totais, estimativa, *, convidado, ve_redacao, publico=False, chave_propria=False):
    """(cause, message) of the first ceiling ``totais`` (+ ``estimativa``) reaches: person, newsroom, installation.
    ``publico``: the message goes where others read it (the conversation), so it carries no number at all.
    ``chave_propria``: the newsroom's own key pays: only the person's ceiling as set holds (contract 8.5)."""
    limite, numeros = tetos(root, conta), not publico and _numeros_da_redacao(convidado, ve_redacao)
    usado = {k: Decimal(totais[k]) / MICRO for k in ('conta', 'organizacao', 'instalacao')}
    # The person's own number never carries the newsroom's ceiling to who does not see it: past the own
    # ceiling as set, the newsroom's refusal (without number) follows. With the own key, the service's quota of
    # the newsroom does not cap the person's either.
    teto_conta = limite['conta' if numeros and not chave_propria else 'pessoa']
    if usado['conta'] >= teto_conta or usado['conta'] + estimativa > teto_conta:
        return 'limite_cota_conta', (mensagem_cota_pessoa() if publico else mensagem_cota_conta(usado['conta'], teto_conta))
    if chave_propria:
        return None
    if usado['organizacao'] >= limite['organizacao'] or usado['organizacao'] + estimativa > limite['organizacao']:
        return 'limite_cota_organizacao', mensagem_cota_organizacao(
            usado['organizacao'] if numeros else None, limite['organizacao'] if numeros else None,
            redacao=_com_contas(root))
    if limite['instalacao'] is not None and (usado['instalacao'] >= limite['instalacao']
                                             or usado['instalacao'] + estimativa > limite['instalacao']):
        return 'limite_cota_instalacao', mensagem_cota_instalacao()
    return None


def conferir_antes(root, conta, modelo, *, convidado=False, ve_redacao=None, chave_propria=False):
    """Refuse the question before it starts when a balance does not cover the minimum estimate, or
    when the month's spend cannot be read or recorded (an unrecorded spend would have no ceiling).

    ``ve_redacao``: whether the asker may see the newsroom's numbers (the route decides, by the gate);
    None keeps the older rule (all but guests)."""
    chaves = chaves_orcamento(conta, root)
    somar_gasto(root, conta, 0, chaves)  # writes the ledger again: GastoSemRegistro when it cannot
    batido = _teto_batido(root, conta, gasto(root, conta, chaves), estimativa_minima_brl(root, modelo),
                          convidado=convidado, ve_redacao=ve_redacao, chave_propria=chave_propria)
    if batido:
        raise CotaEsgotada(batido[1])


def estouro(root, totais, *, conta=None, chave_propria=False):
    """(cause, message) when this month's totals (``somar_gasto``) reached a ceiling in the middle of a question,
    else None. The message is recorded in the conversation, which the colleagues of the case read: it never carries
    a number, whoever asked (B1 of P1). Who asked sees the numbers in the quota bar and in the direct refusal."""
    return _teto_batido(root, conta, totais, Decimal(0), convidado=True, ve_redacao=False, publico=True,
                        chave_propria=chave_propria)
