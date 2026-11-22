"""IP do cliente atrás de proxies (SEG-05): lista de proxies confiáveis e o primeiro salto não confiável.

`VLADO_PROXIES_CONFIAVEIS` é uma lista de IPs e redes (CIDR), separados por vírgula, espaço ou ponto e vírgula, por exemplo
`172.18.0.0/16, 203.0.113.0/24, 2001:db8::/32`. Com a lista definida:

- o `X-Forwarded-For` só vale se o par TCP (o endereço do socket) estiver na lista: um cliente que fala direto com a Mesa
  não consegue forjar o IP;
- o IP do cliente é o primeiro salto que NÃO está na lista, lendo o `X-Forwarded-For` da direita para a esquerda: os
  saltos mais à esquerda são do cliente e podem ser forjados, então não contam depois de um salto não confiável;
- um salto ilegível interrompe a leitura e vale o par TCP (nunca um valor que o cliente escolheu).

Uma rede que cobre (quase) toda a internet (`0.0.0.0/0`, `::/0`, IPv4 menor que /8, IPv6 menor que /16) é RECUSADA: confiar
nela deixaria qualquer cliente escolher o próprio IP e escapar do limite e da auditoria. Só com a confirmação explícita
`VLADO_PROXIES_CONFIAVEIS_AMPLAS=1` ela passa.

Sem a lista, nada muda (comportamento anterior, controlado por `VLADO_CONFIAR_PROXY`). A lista tem de incluir o Caddy, que
é o par TCP da Mesa (a rede do Compose, por exemplo `172.18.0.0/16`: `docker network inspect <projeto>_default`) e, atrás de
CDN ou WAF, as faixas dela, que o Caddy também precisa confiar (`trusted_proxies`; ver deploy/MONITORAMENTO.md).
"""
from __future__ import annotations

import ipaddress
import os
import re

VARIAVEL = 'VLADO_PROXIES_CONFIAVEIS'
CONFIRMACAO = 'VLADO_PROXIES_CONFIAVEIS_AMPLAS'
PREFIXO_MINIMO = {4: 8, 6: 16}
SEPARADOR = re.compile(r'[,\s;]+')


def analisar(texto: str | None, confirmar_amplo: bool | None = None) -> tuple | None:
    """Redes da lista; None se a variável está vazia ou ausente. Entrada inválida, ou uma rede ampla demais sem a
    confirmação explícita (VLADO_PROXIES_CONFIAVEIS_AMPLAS=1), levanta ValueError (com o item)."""
    if confirmar_amplo is None:
        confirmar_amplo = os.environ.get(CONFIRMACAO, '').strip() == '1'
    itens = [i for i in SEPARADOR.split((texto or '').strip()) if i]
    if not itens:
        return None
    redes = []
    for item in itens:
        try:
            redes.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            raise ValueError(f'{VARIAVEL}: {item!r} não é um IP nem uma rede (use 172.18.0.0/16, 203.0.113.7, 2001:db8::/32).') from None
    if not confirmar_amplo:
        for rede in redes:
            if rede.prefixlen < PREFIXO_MINIMO[rede.version]:
                raise ValueError(f'{VARIAVEL}: {str(rede)!r} cobre (quase) toda a internet; confiar nela deixa qualquer cliente '
                                 f'escolher o próprio IP. Use as faixas reais do proxy ou da CDN. Se é mesmo isso que quer, defina '
                                 f'{CONFIRMACAO}=1.')
    return tuple(redes)


def do_ambiente() -> tuple | None:
    """A lista configurada; lista inválida vira "só o par TCP" (rede vazia que nunca casa), nunca um erro no pedido."""
    try:
        return analisar(os.environ.get(VARIAVEL))
    except ValueError:
        return ()


def validar_ambiente() -> None:
    """Para a partida do servidor: lista inválida impede de subir, com a mensagem."""
    analisar(os.environ.get(VARIAVEL))


def _endereco(texto: str):
    endereco = ipaddress.ip_address(texto.strip().strip('[]'))
    mapeado = getattr(endereco, 'ipv4_mapped', None)  # ::ffff:a.b.c.d é o IPv4 a.b.c.d
    return mapeado or endereco


def _confia(endereco, redes) -> bool:
    return any(endereco.version == rede.version and endereco in rede for rede in redes)


def ip_do_cliente(par_tcp: str, encaminhado: str | None, redes: tuple) -> str:
    """O IP a usar nos limites e no registro. `redes` vem de `analisar` (tupla vazia: ninguém é confiável)."""
    try:
        par = _endereco(par_tcp)
    except ValueError:
        return par_tcp
    if not _confia(par, redes):
        return str(par)  # quem fala direto com a Mesa não escolhe o próprio IP
    saltos = [s.strip() for s in (encaminhado or '').split(',') if s.strip()]
    ultimo = None
    for salto in reversed(saltos):
        try:
            endereco = _endereco(salto)
        except ValueError:
            return str(par)  # salto ilegível: não dá para saber quem escreveu o que está à esquerda
        if not _confia(endereco, redes):
            return str(endereco)
        ultimo = endereco
    return str(ultimo or par)  # só proxies na cadeia: o mais à esquerda é o de origem
