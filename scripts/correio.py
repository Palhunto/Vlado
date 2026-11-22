"""E-mail transacional da Mesa (contrato de contas, seção 8.1): uma interface, três transportes.

O código de contas chama ``enviar(tipo, para, idioma, dados)``. O transporte vem da configuração
(``VLADO_CORREIO``):

- ``simulado``: guarda as mensagens em memória (``caixa()``). É o dos testes, que leem dali o link.
- ``tela``: não envia nada; quem chamou devolve o link a quem pediu. É o padrão, e vale no modo
  ``local-contas`` e na homologação do ``piloto``. O ambiente ``editorial``, de dados reais, não sobe com ele
  (``conferir_partida``, decisão 12).
- ``smtp``: envio real, com endereço e credenciais só em variáveis de ambiente (``VLADO_SMTP_HOST``,
  ``VLADO_SMTP_PORTA``, ``VLADO_SMTP_USUARIO``, ``VLADO_SMTP_SENHA``, ``VLADO_SMTP_REMETENTE``), sempre com TLS.

As mensagens são só texto, em português e inglês, com modelos versionados (``VERSAO_MODELOS``). Todo valor
que entra num modelo perde quebras de linha e caracteres de controle, e o único link é o da própria
instalação. O token só existe no link: este módulo não grava nada em disco, e o registro de auditoria
recebe o tipo da mensagem, nunca o endereço nem o texto. Trocar de provedor é escrever outro transporte.
"""
from __future__ import annotations

from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import os
import re
import smtplib
import ssl
import threading

import registro_acesso

TRANSPORTES = ('simulado', 'tela', 'smtp')
IDIOMAS = ('pt', 'en')
VERSAO_MODELOS = 1
ESPERA_SMTP_S = 15
MAX_CAIXA = 500  # the simulated transport keeps the newest messages only
# The same shape `acesso.EMAIL` accepts: one address, lower case, no room for a second header line.
_ENDERECO = re.compile(r'[a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+')
_LINK = re.compile(r'https?://[A-Za-z0-9.:\[\]-]+/[A-Za-z0-9/_-]*')
_PAPEIS = {'pt': {'dono': 'dono', 'editor': 'editor', 'reporter': 'repórter', 'leitor': 'leitor'},
           'en': {'dono': 'owner', 'editor': 'editor', 'reporter': 'reporter', 'leitor': 'reader'}}
# tipo -> (nome no registro de auditoria, {idioma: (assunto, corpo)}). Campos entre chaves vêm de `dados`.
MODELOS = {
    'convite': ('convite', {
        'pt': ('Convite para a redação {redacao} no Vlado',
               '{convidado_por} convidou você para a redação {redacao} no Vlado, com o papel de {papel}.\n\n'
               'Para aceitar, abra este endereço e escolha a sua senha:\n{link}\n\n'
               'O convite vale até {validade} e só pode ser usado uma vez.\n'
               'Se você não esperava este convite, ignore esta mensagem: nada acontece sem o seu aceite.\n'),
        'en': ('Invitation to the newsroom {redacao} on Vlado',
               '{convidado_por} invited you to the newsroom {redacao} on Vlado, as {papel}.\n\n'
               'To accept, open this address and choose your password:\n{link}\n\n'
               'The invitation is valid until {validade} and can be used only once.\n'
               'If you were not expecting it, ignore this message: nothing happens unless you accept.\n')}),
    'convite_sem_efeito': ('convite', {
        'pt': ('Convite para a redação {redacao} no Vlado',
               '{convidado_por} convidou você para a redação {redacao} no Vlado.\n\n'
               'Este endereço de e-mail já tem uma conta no Vlado e, neste período de teste, uma conta pertence a uma '
               'redação só. Por isso este convite não cria outra conta e não muda nada na que você já tem.\n\n'
               'Se quiser fazer parte da outra redação, fale com quem convidou.\n'),
        'en': ('Invitation to the newsroom {redacao} on Vlado',
               '{convidado_por} invited you to the newsroom {redacao} on Vlado.\n\n'
               'This e-mail address already has an account on Vlado and, during this trial, an account belongs to one '
               'newsroom only. So this invitation does not create another account and changes nothing in yours.\n\n'
               'If you want to join the other newsroom, talk to whoever invited you.\n')}),
}

_TRAVA = threading.Lock()
_CAIXA: list[dict] = []
_FORCADO: list[str] = []


class ErroDeCorreio(ValueError):
    """The mail configuration is wrong, or forbidden for this environment: the server must not start with it."""


class FalhaDeEnvio(OSError):
    """The message was not sent. The text never carries the address, the link or the server's answer."""


def transporte() -> str:
    """The transport in use: the one forced by a test, else ``VLADO_CORREIO``, else ``tela``."""
    if _FORCADO:
        return _FORCADO[-1]
    valor = os.environ.get('VLADO_CORREIO', '').strip().lower() or 'tela'
    if valor not in TRANSPORTES:
        raise ErroDeCorreio('VLADO_CORREIO deve ser smtp, tela ou simulado.')
    return valor


@contextmanager
def usar(nome: str):
    """Force a transport for a while (tests): ``with correio.usar('simulado'): ...``."""
    if nome not in TRANSPORTES:
        raise ErroDeCorreio('Transporte de e-mail desconhecido.')
    _FORCADO.append(nome)
    try:
        yield
    finally:
        _FORCADO.pop()


def conferir_partida(modo: str, ambiente: str | None) -> str:
    """Called when the server starts. The hosted service with real data (``editorial``) only runs with real
    delivery (decision 12), and ``smtp`` needs its variables. Returns the transport; raises ErroDeCorreio."""
    nome = transporte()
    if modo == 'piloto' and ambiente == 'editorial' and nome != 'smtp':
        raise ErroDeCorreio('O ambiente editorial só sobe com envio real de e-mail: defina VLADO_CORREIO=smtp e as '
                            'variáveis VLADO_SMTP_*.')
    if nome == 'smtp':
        _configuracao_smtp()
    return nome


def _configuracao_smtp() -> dict:
    host, remetente = os.environ.get('VLADO_SMTP_HOST', '').strip(), os.environ.get('VLADO_SMTP_REMETENTE', '').strip()
    try:
        porta = int(os.environ.get('VLADO_SMTP_PORTA') or 587)
    except ValueError:
        porta = 0
    if not host or not 0 < porta < 65536 or not _ENDERECO.fullmatch(remetente.lower()):
        raise ErroDeCorreio('Envio por SMTP sem configuração: defina VLADO_SMTP_HOST, VLADO_SMTP_REMETENTE e, se preciso, '
                            'VLADO_SMTP_PORTA, VLADO_SMTP_USUARIO e VLADO_SMTP_SENHA.')
    return {'host': host, 'porta': porta, 'remetente': remetente, 'usuario': os.environ.get('VLADO_SMTP_USUARIO') or None,
            'senha': os.environ.get('VLADO_SMTP_SENHA') or ''}


def _linha(valor, maximo: int = 200) -> str:
    """One value of a template: a single line, without control characters (names come from people)."""
    texto = ''.join(c if c.isprintable() else ' ' for c in str(valor if valor is not None else ''))
    return ' '.join(texto.split())[:maximo]


def montar(tipo: str, idioma, dados: dict) -> tuple[str, str]:
    """(subject, text) of a message. Unknown type, a missing field or a link that is not a plain address of the
    installation is a programming error, raised as ValueError: nothing half-written is ever sent."""
    if tipo not in MODELOS or not isinstance(dados, dict):
        raise ValueError('Tipo de mensagem desconhecido.')
    idioma = idioma if idioma in IDIOMAS else IDIOMAS[0]
    campos = {chave: _linha(valor) for chave, valor in dados.items()}
    if 'link' in dados:
        link, origem = str(dados['link']), str(dados.get('origem') or '')
        if not _LINK.fullmatch(link) or (origem and not link.startswith(origem.rstrip('/') + '/')):
            raise ValueError('Link de mensagem inválido.')
        campos['link'] = link
    if idioma == 'pt' and re.fullmatch(r'\d{4}-\d{2}-\d{2}', campos.get('validade', '')):
        ano, mes, dia = campos['validade'].split('-')
        campos['validade'] = f'{dia}/{mes}/{ano}'
    if 'papel' in campos:
        campos['papel'] = _PAPEIS[idioma].get(campos['papel'], campos['papel'])
    if not campos.get('convidado_por'):
        campos['convidado_por'] = {'pt': 'A administração', 'en': 'The administrators'}[idioma]
    assunto, corpo = MODELOS[tipo][1][idioma]
    try:
        return _linha(assunto.format_map(campos), 150), corpo.format_map(campos)
    except KeyError as exc:
        raise ValueError('Mensagem sem um dos campos do modelo.') from exc


def enviar(tipo: str, para: str, idioma, dados: dict, *, conta: str | None = None) -> str:
    """Send one message and return the transport used. With ``tela`` nothing is sent: the caller shows the link
    to whoever asked. Raises FalhaDeEnvio when a real delivery fails (the caller records it and goes on)."""
    assunto, corpo = montar(tipo, idioma, dados)
    para = para.strip().lower() if isinstance(para, str) else ''
    if not _ENDERECO.fullmatch(para) or len(para) > 254:
        raise ValueError('Endereço de e-mail inválido.')
    nome, rotulo = transporte(), MODELOS[tipo][0]
    if nome == 'tela':
        return nome
    try:
        if nome == 'simulado':
            with _TRAVA:
                _CAIXA.append({'tipo': tipo, 'para': para, 'idioma': idioma if idioma in IDIOMAS else IDIOMAS[0],
                               'assunto': assunto, 'corpo': corpo, 'link': dados.get('link')})
                del _CAIXA[:-MAX_CAIXA]
        else:
            _smtp(para, assunto, corpo)
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        registro_acesso.registrar('email_falhou', 'falha', conta, mensagem=rotulo)
        raise FalhaDeEnvio('Não foi possível enviar o e-mail.') from (None if isinstance(exc, ErroDeCorreio) else exc)
    registro_acesso.registrar('email_enviado', 'ok', conta, mensagem=rotulo)
    return nome


def _smtp(para: str, assunto: str, corpo: str) -> None:
    conf = _configuracao_smtp()
    mensagem = EmailMessage()
    mensagem['From'], mensagem['To'], mensagem['Subject'] = conf['remetente'], para, assunto
    mensagem['Date'] = formatdate(localtime=False)
    mensagem['Message-ID'] = make_msgid(domain=conf['remetente'].rsplit('@', 1)[1])
    mensagem['Auto-Submitted'] = 'auto-generated'
    mensagem.set_content(corpo)
    contexto = ssl.create_default_context()
    if conf['porta'] == 465:
        servidor = smtplib.SMTP_SSL(conf['host'], conf['porta'], timeout=ESPERA_SMTP_S, context=contexto)
    else:
        servidor = smtplib.SMTP(conf['host'], conf['porta'], timeout=ESPERA_SMTP_S)
    with servidor:
        if conf['porta'] != 465:
            servidor.starttls(context=contexto)  # never in clear text: a server without TLS is a failed delivery
        if conf['usuario']:
            servidor.login(conf['usuario'], conf['senha'])
        servidor.send_message(mensagem)


def caixa() -> list[dict]:
    """The messages the simulated transport kept, oldest first (tests read the link from here)."""
    with _TRAVA:
        return [dict(mensagem) for mensagem in _CAIXA]


def limpar_caixa() -> None:
    with _TRAVA:
        _CAIXA.clear()
