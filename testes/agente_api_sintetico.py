"""Agente sintético para o ServidorAPI de verdade (CONF-04): sem rede, sem modelo, sem chamada paga.

Faz cada etapa como o agente de ``agente_fluxo_fixture``, mas por chamadas de ferramenta reais
(o ServidorAPI as entrega à Mesa e devolve o resultado no histórico). Tira tudo do histórico que
recebe: a etapa vem da linha "Etapa obrigatória atual" do turno e a fonte achada vem do resultado
de ``buscar`` já gravado; então funciona igual depois de uma reinicialização, noutro processo,
e só funciona se o histórico salvo voltar inteiro.

As falhas vêm do SDK de verdade: ``falhar_com`` monta o adaptador real (provedor_anthropic ou
provedor_openai) com o cliente do SDK nas opções da produção (2 novas tentativas, prazo de 600 s)
sobre um transporte HTTP falso; o próprio SDK escolhe a exceção e refaz o pedido quando é o caso.
"""
import json
import os
from pathlib import Path
import re
import threading
import time

from agente_fluxo_fixture import entrega
from inferencia_api import Resposta


# Atomic: whoever waits for the mark sees it only whole (a .tmp beside it, then os.replace). Written straight,
# exists() turned true with the file still empty, and reading it gave JSONDecodeError (CI of the 8th round).
def marcar(caminho, texto):
    temporario = Path(f'{caminho}.{os.getpid()}.{threading.get_ident()}.tmp')  # one per writer
    temporario.write_text(texto, encoding='utf-8')
    os.replace(temporario, caminho)


ETAPA = re.compile(r'Etapa obrigatória atual: ([a-z_]+)\.')
USO = {'anthropic': {'entrada': 1000, 'saida': 200, 'cache_leitura': 0, 'cache_escrita': 0,
                     'entrada_sem_cache': 1000, 'cache_escrita_5m': 0, 'cache_escrita_1h': 0},
       'openai': {'entrada': 1000, 'saida': 200, 'cache_leitura': 0, 'entrada_sem_cache': 1000,
                  'cache_escrita': 0, 'cache_escrita_30m': 0, 'cache_escrita_12h': 0}}


def turno(historico):
    """(etapa, passo) of the current turn: its stage prompt and how many answers it already has."""
    inicio = max(i for i, m in enumerate(historico) if m['papel'] == 'usuario')
    achada = ETAPA.search(historico[inicio]['texto'])
    passo = sum(1 for m in historico[inicio + 1:] if m['papel'] == 'assistente')
    return (achada.group(1) if achada else None), passo


def achado(historico):
    """The first search hit recorded in the history (the busca stage's ``buscar``), or None."""
    for mensagem in historico:
        if mensagem['papel'] != 'ferramenta' or mensagem.get('erro'):
            continue
        try:
            dados = json.loads(mensagem['texto'])
        except ValueError:
            continue
        if isinstance(dados, dict) and dados.get('resultados'):
            return dados['resultados'][0]
    return None


def plano(etapa, hit):
    """The tool calls of a stage, in order; the last one saves it."""
    def guardar():
        resultado = {'resultados': [hit]} if hit else {}
        return {'acao': 'guardar', 'etapa': etapa,
                'texto': entrega(etapa, lambda args: resultado, {'hit': hit} if hit else {})}
    if etapa == 'inventario':
        return [lambda: {'acao': 'cobertura'}, guardar]
    if etapa == 'busca':
        return [lambda: {'acao': 'buscar', 'consulta': 'Alfabeto'},
                lambda: {'acao': 'ler', 'referencia': hit['referencia']}, guardar]
    if etapa == 'revisao':
        return [lambda: {'acao': 'ler', 'referencia': hit['referencia']}, guardar]
    return [guardar]


class AgenteSintetico:
    """Provider for ServidorAPI(criar_provedor=...). ``falhas`` maps (etapa, passo) to a provider whose
    ``gerar`` fails (used once); ``parar_em`` (etapa, passo) writes ``marca`` and blocks there, for the
    test to kill the process in the middle of that stage."""

    def __init__(self, provedor='anthropic', falhas=None, parar_em=None, marca=None):
        self.uso = USO[provedor]
        self.falhas = dict(falhas or {})
        self.parar_em, self.marca = parar_em, marca
        self.pedidos = []  # (etapa, passo) of each call
        self.respondidas = 0
        self.achado_do_historico = []  # whether the hit came from the history, per call that needed it
        self.lock = threading.Lock()

    def gerar(self, *, modelo, instrucoes, historico, ferramentas, max_tokens, ao_texto, cancelado):
        etapa, passo = turno(historico)
        with self.lock:
            self.pedidos.append((etapa, passo))
            falha = self.falhas.pop((etapa, passo), None)
        if falha is not None:  # the real SDK path raises (ErroIA from the adapter)
            return falha.gerar(modelo=modelo, instrucoes=instrucoes, historico=historico, ferramentas=ferramentas,
                               max_tokens=max_tokens, ao_texto=ao_texto, cancelado=cancelado)
        if (etapa, passo) == self.parar_em:
            marcar(self.marca, json.dumps({'respondidas': self.respondidas}))
            time.sleep(600)  # killed here
        hit = achado(historico)
        passos = plano(etapa, hit)
        if etapa in ('geracao_inicial', 'revisao', 'sintese'):
            self.achado_do_historico.append(hit is not None)
        with self.lock:
            self.respondidas += 1
        if passo < len(passos):
            chamada = {'id': f'{etapa}-{passo}', 'nome': 'consultar_acervo', 'argumentos': passos[passo]()}
            return Resposta(texto='', chamadas=(chamada,), uso=dict(self.uso), modelo=modelo)
        ao_texto('Etapa sintética entregue.')
        return Resposta(texto='Etapa sintética entregue.', uso=dict(self.uso), modelo=modelo)


def falhar_com(provedor, *, status=None, corpo=None, cabecalhos=None, excecao=None):
    """(adapter, requests) where the real SDK gets ``status``/``corpo`` (or ``excecao`` raised by the
    transport) for every request; ``requests`` counts them (the SDK's own retries included)."""
    import httpx2
    pedidos = []

    def responder(pedido):
        pedidos.append(str(pedido.url))
        if excecao is not None:
            raise excecao('prazo sintético', request=pedido)
        return httpx2.Response(status, json=corpo, headers=cabecalhos or {})
    cliente = httpx2.Client(transport=httpx2.MockTransport(responder))
    if provedor == 'anthropic':
        import anthropic
        import provedor_anthropic
        sdk = anthropic.Anthropic(api_key='sk-ant-sintetica', max_retries=2, timeout=provedor_anthropic.TIMEOUT,
                                  http_client=cliente)
        return provedor_anthropic.ProvedorAnthropic('sk-ant-sintetica', cliente=sdk), pedidos
    import openai
    import provedor_openai
    sdk = openai.OpenAI(api_key='sk-sintetica', max_retries=2, timeout=provedor_openai.TIMEOUT, http_client=cliente)
    return provedor_openai.ProvedorOpenAI('sk-sintetica', cliente=sdk), pedidos
