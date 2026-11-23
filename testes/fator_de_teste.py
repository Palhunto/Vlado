"""Segundo fator nos cenários de teste (contrato de contas, seção 8.2). Não é um arquivo de teste.

No modo ``piloto`` o segundo fator é obrigatório para dono e editor: sem ele a sessão só alcança o próprio
cadastro do fator. Os cenários que sobem uma Mesa em ``piloto`` cadastram o fator dessas contas por aqui, pelo
mesmo caminho que a pessoa usa (``acesso.iniciar_fator`` e ``acesso.confirmar_fator``), sem atalho no
armazenamento, e entram em dois passos.

Um código do aplicativo vale uma vez a cada 30 segundos, e os cenários entram muitas vezes seguidas com a mesma
conta. Por isso o segundo passo dos cenários usa os códigos de reserva, de uso único, e gera dez novos quando
sobra um (``codigo``). Quem quiser o código do aplicativo usa ``do_aplicativo``.
"""
import base64
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import acesso
import segundo_fator

_CADASTRADOS: dict = {}  # (data folder, account id) -> {'senha', 'segredo', 'reserva'}


def do_aplicativo(segredo: str, desvio: int = 0, momento=None) -> str:
    """The code an authenticator app shows for the seed given in base32 (`desvio` steps of 30 seconds away)."""
    semente = base64.b32decode(segredo + '=' * (-len(segredo) % 8))
    return segundo_fator.codigo_do_passo(semente, segundo_fator.passo_de(momento or acesso.agora()) + desvio)


def cadastrar(root, conta: str, senha: str) -> str:
    """Enrol the second factor of an account, as the person does. Returns the seed in base32."""
    segredo = acesso.iniciar_fator(root, conta, senha)['segredo']
    reserva = acesso.confirmar_fator(root, conta, do_aplicativo(segredo))
    _CADASTRADOS[str(root), conta] = {'senha': senha, 'segredo': segredo, 'reserva': list(reserva)}
    return segredo


def tem(root, conta: str) -> bool:
    return (str(root), conta) in _CADASTRADOS


def codigo(root, conta: str) -> str:
    """A code good for one second step of the sign-in of an account enrolled by `cadastrar`: a reserve code."""
    dados = _CADASTRADOS[str(root), conta]
    if len(dados['reserva']) == 1:  # the last one buys ten new ones (asks the password and a code, as the person would)
        dados['reserva'] = list(acesso.novos_codigos_do_fator(root, conta, dados['senha'], dados['reserva'][0]))
    return dados['reserva'].pop()


def entrar(pedir, root, conta: str, login: str, senha: str, origem: str) -> tuple[str, str]:
    """Sign in through the server, as the person does: the password and, for an account enrolled by `cadastrar`,
    the second step. `pedir(method, path, body, headers)` answers (status, headers, body). Returns (session
    cookie, csrf)."""
    import json
    cabecalhos = {'Content-Type': 'application/json', 'Origin': origem}
    status, recebidos, corpo = pedir('POST', '/api/entrar', json.dumps({'login': login, 'senha': senha}), cabecalhos)
    assert status == 200, corpo
    if json.loads(corpo).get('estado') == 'segundo_fator':
        bilhete = recebidos['Set-Cookie'].split(';')[0]
        status, recebidos, corpo = pedir('POST', '/api/entrar-segundo-fator', json.dumps({'codigo': codigo(root, conta)}),
                                         {**cabecalhos, 'Cookie': bilhete})
        assert status == 200, corpo
    return recebidos['Set-Cookie'].split(';')[0], json.loads(corpo)['csrf']


def levar(origem, destino) -> None:
    """The data folder was restored somewhere else (a backup): what was enrolled in it goes along."""
    for (pasta, conta), dados in list(_CADASTRADOS.items()):
        if pasta == str(origem):
            _CADASTRADOS[str(destino), conta] = dados


def esquecer(root) -> None:
    """Forget what was enrolled in a data folder (a scenario that ends)."""
    for chave in [c for c in _CADASTRADOS if c[0] == str(root)]:
        del _CADASTRADOS[chave]
