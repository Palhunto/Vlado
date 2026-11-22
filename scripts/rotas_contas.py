"""Sessão, entrada, ativação, a própria conta e a gestão de contas da Mesa (modos ``local-contas`` e ``piloto``).

Aqui ficam quem chama (a conta relida do armazenamento a cada requisição, com a redação e as
apurações ao alcance), as operações públicas antes da sessão (entrar, ativar, primeiro
administrador), as ``conta-*`` (cada pessoa sobre a própria conta: perfil, senha e sessões; o id
de outra conta nunca é aceito). A gestão das outras contas da redação fica em ``rotas_equipe``; as
antigas ``contas-*`` saíram com o convite por e-mail. O que cada papel alcança é
decidido num lugar só, ``autorizacao.conferir``; este módulo não lê o papel para autorizar.
Origem, CSRF e leitura do corpo continuam no servidor; este módulo nunca lê nem grava chaves de API.
"""
from __future__ import annotations

import html
from http.cookies import SimpleCookie
import ipaddress
import json
import os

import acesso
import autorizacao
import correio
import proxies_confiaveis
import rascunhos
import registro_acesso
import rotas_equipe

# What the legacy guest profile may call: the guest column of the matrix (`autorizacao.MATRIZ`) is exactly
# OPERACOES_CONVIDADO plus the own account (`CONTA_PROPRIA`).
OPERACOES_CONVIDADO = ('codex-status', 'codex-listar', 'codex-perguntar', 'codex-eventos', 'codex-cancelar',
                       'codex-retomar', 'codex-original', 'sessao-sair', *rascunhos.OPERACOES)
# Guest operations on an existing conversation: the conversation's case is checked on every call.
OPERACOES_CONVERSA = ('codex-eventos', 'codex-cancelar', 'codex-original', 'codex-retomar')
# Before a session exists (hosted mode only): Origin + JSON, no CSRF, small bodies.
OPERACOES_PUBLICAS = ('entrar', 'ativar', 'ativacao-consultar', 'primeiro-admin', 'convite-consultar', 'convite-aceitar',
                      'senha-esqueci', 'senha-redefinir', 'email-confirmar', 'entrar-segundo-fator')
ESQUECI_ENVIADO = 'Se houver uma conta com esse e-mail, a mensagem para redefinir a senha foi enviada.'
ESQUECI_DESLIGADO = 'Nesta instalação a senha é recuperada por quem administra a redação.'
AMBIENTES = ('homologacao', 'editorial', 'demonstracao')
SEM_SESSAO = 'Sessão expirada ou encerrada. Entre novamente.'
# Asking and retrying both spend one of the guest's daily questions (given back if refused).
OPERACOES_COM_COTA = ('codex-perguntar', 'codex-retomar')
ATIVOS_CONVERSA = frozenset({'preparando', 'executando', 'publicando'})
COOKIE_PILOTO ='vlado_sessao'
# Each person on the own account (contract, 5.4): the account is always the session's, never one named in the body.
CONTA_PROPRIA = ('conta-ver', 'conta-atualizar', 'conta-senha-trocar', 'conta-sessoes', 'conta-sessao-encerrar',
                 'conta-sessoes-encerrar-outras', 'conta-email-trocar', 'conta-fator-iniciar', 'conta-fator-confirmar',
                 'conta-fator-codigos', 'conta-fator-remover')
_CAMPOS_DA_CONTA = {'conta-ver': set(), 'conta-atualizar': {'nome', 'idioma'}, 'conta-senha-trocar': {'senha_atual', 'senha_nova'},
                    'conta-sessoes': set(), 'conta-sessao-encerrar': {'sessao'}, 'conta-sessoes-encerrar-outras': set(),
                    'conta-email-trocar': {'email', 'senha'}, 'conta-fator-iniciar': {'senha', 'codigo'},
                    'conta-fator-confirmar': {'codigo'}, 'conta-fator-codigos': {'senha', 'codigo'},
                    'conta-fator-remover': {'senha'}}
COOKIE_SEGUNDO_PASSO = 'vlado_passo2'  # the ticket between the right password and the second factor (five minutes)
_NAVEGADORES = (('Edg/', 'Edge'), ('OPR/', 'Opera'), ('Firefox/', 'Firefox'), ('Chrome/', 'Chrome'), ('Safari/', 'Safari'))
_SISTEMAS = (('Android', 'Android'), ('iPhone', 'iOS'), ('iPad', 'iOS'), ('Windows', 'Windows'), ('Mac OS X', 'macOS'),
             ('Linux', 'Linux'))


def aparelho(agente, cliente='web'):
    """The device label of a session, from the browser's header: two words out of closed lists, never the header
    itself (it is text the client chooses, and it would be shown back in the list of sessions)."""
    if cliente == 'android':
        return 'Aplicativo Android'
    agente = agente if isinstance(agente, str) else ''
    navegador = next((nome for marca, nome in _NAVEGADORES if marca in agente), 'Navegador')
    sistema = next((nome for marca, nome in _SISTEMAS if marca in agente), None)
    return f'{navegador} · {sistema}' if sistema else navegador


def _trocar_email(root, conta, data, ip, origem):
    """``conta-email-trocar``: asks the password; the change only happens when the link sent to the NEW address is
    used (``email-confirmar``). The answer is the same whether the address is free or already of another account,
    and the messages leave in another thread, so its time is the same too; nothing is ever sent to an address in
    use. The current address is told of the request. With the transport ``tela`` the link goes back to who asked."""
    pedido = acesso.pedir_troca_de_email(root, conta, data.get('email'), data.get('senha'), ip)
    link = f'{(origem or "").rstrip("/")}/confirmar-email/{pedido["token"]}'
    if pedido['antigo']:
        correio.enviar_depois('email_aviso', pedido['antigo'], pedido['idioma'], {}, conta=conta, raiz=root)
    if not rotas_equipe.com_envio():
        return {'estado': 'confirmacao_enviada', 'link': link}
    if pedido['enviar']:
        correio.enviar_depois('email_novo', pedido['novo'], pedido['idioma'],
                              {'link': link, 'origem': origem, 'minutos': acesso.REDEFINICAO_MINUTOS}, conta=conta, raiz=root)
    return {'estado': 'confirmacao_enviada'}


def _fator(root, operation, conta, data, ip):
    """``conta-fator-*``: the own second factor. The seed and the reserve codes go out once, in the answer of the
    operation that makes them, and never again; the person is told by e-mail of every change."""
    if operation == 'conta-fator-iniciar':
        return acesso.iniciar_fator(root, conta, data.get('senha'), data.get('codigo'), ip)
    if operation == 'conta-fator-confirmar':
        resposta = {'estado': 'fator_ativado', 'codigos_de_reserva': acesso.confirmar_fator(root, conta, data.get('codigo'), ip)}
    elif operation == 'conta-fator-codigos':
        resposta = {'estado': 'codigos_gerados',
                    'codigos_de_reserva': acesso.novos_codigos_do_fator(root, conta, data.get('senha'), data.get('codigo'), ip)}
    else:
        acesso.remover_fator(root, conta, data.get('senha'), ip)
        resposta = {'estado': 'fator_removido'}
    perfil = acesso.ver_conta(root, conta)['conta']
    if perfil['email']:
        correio.enviar_depois('fator_alterado', perfil['email'], perfil['idioma'], {}, conta=conta, raiz=root)
    return resposta


def conta_propria(root, operation, data, principal, ip=None, origem=None):
    """``POST /api/conta-*``: the person on the own account. ``principal`` is the session; nothing here takes the id
    of an account, and the session that asks is told apart by its public id (never the cookie)."""
    if operation not in CONTA_PROPRIA or not isinstance(data, dict):
        raise ValueError('Operação de conta desconhecida.')
    if set(data) - _CAMPOS_DA_CONTA[operation]:
        raise ValueError('Campos inválidos no pedido de conta.')
    conta, atual = principal.get('conta'), principal.get('sessao')
    if not conta:
        raise ValueError('Contas só existem nos modos com login.')
    if operation == 'conta-ver':
        return {**acesso.ver_conta(root, conta), 'sessao': atual}
    if operation == 'conta-atualizar':
        return acesso.atualizar_perfil(root, conta, nome=data.get('nome'), idioma=data.get('idioma'))
    if operation == 'conta-email-trocar':
        return _trocar_email(root, conta, data, ip, origem)
    if operation.startswith('conta-fator-'):
        return _fator(root, operation, conta, data, ip)
    if operation == 'conta-senha-trocar':
        encerradas = acesso.trocar_senha(root, conta, data.get('senha_atual'), data.get('senha_nova'), atual, ip)
        perfil = acesso.ver_conta(root, conta)['conta']
        if perfil['email']:  # the person is told, at the account's own address (contract, 8.1)
            correio.enviar_depois('senha_trocada', perfil['email'], perfil['idioma'], {}, conta=conta, raiz=root)
        return {'estado': 'senha_trocada', 'sessoes_encerradas': encerradas}
    if operation == 'conta-sessao-encerrar':
        acesso.encerrar_sessao_da_conta(root, conta, data.get('sessao'), atual)
    elif operation == 'conta-sessoes-encerrar-outras':
        return {'encerradas': acesso.encerrar_outras_sessoes(root, conta, atual),
                'sessoes': acesso.sessoes_da_conta(root, conta, atual)}
    return {'sessoes': acesso.sessoes_da_conta(root, conta, atual)}


class RotasContas:
    """Mixin of the request handler: uses its ``_send``, ``_json``, ``headers`` and ``server``."""

    def _sessao_piloto(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:  # noqa: BLE001 - malformed cookie header means no session
            return None, None
        morsel = cookie.get(COOKIE_PILOTO)
        sid = morsel.value if morsel else None
        if not sid:
            return None, None
        try:
            return acesso.sessao(self.server.root, sid, ip=self._ip()), sid
        except (ValueError, OSError):
            self.acesso_indisponivel = True  # answered with 503, never with a dropped connection
            return None, sid

    def _bilhete_do_segundo_passo(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:  # noqa: BLE001 - a malformed cookie header means no ticket
            return None
        morsel = cookie.get(COOKIE_SEGUNDO_PASSO)
        return morsel.value if morsel else None

    def _endereco_socket(self):
        """The TCP peer, never a forwarded header."""
        return self.client_address[0]

    def _cliente_local(self):
        """First-administrator form: loopback peer, local Host and local Origin, whatever proxy settings say."""
        try:
            loopback = ipaddress.ip_address(self._endereco_socket()).is_loopback
        except ValueError:
            loopback = False
        return (self.server.modo == 'local-contas' and loopback
                and self.headers.get('Host') == self.server.host_permitido
                and self.headers.get('Origin') == self.server.origin)

    def _primeiro_acesso(self):
        try:
            return acesso.primeiro_acesso_disponivel(self.server.root)
        except (ValueError, OSError):
            return False

    def _principal(self):
        """Who is calling: in local mode the single operator (admin); in hosted mode the account session.

        Read once per request: the account is re-read from the store on every request, so deactivation,
        role and case changes apply to the next one."""
        if self.server.modo == 'local':
            # No accounts, no newsroom, no ownership: the only caller for whom `casos` is None (every case).
            return {'papel': 'dono', 'conta': None, 'nome': None, 'login': None, 'email': None, 'organizacao': None,
                    'casos': None, 'responsavel_de': None, 'pendencias': [], 'csrf': self.server.token}
        if not hasattr(self, '_principal_requisicao'):
            self._principal_requisicao = self._sessao_piloto()[0]
        return self._principal_requisicao

    def _proibido(self, mensagem='Operação não permitida para este acesso.', codigo=None):
        self._json(403, {'estado': 'proibido', 'erro': mensagem, **({'codigo': codigo} if codigo else {})})

    def _sem_principal(self, api=False):
        if getattr(self, 'acesso_indisponivel', False):
            self._json(503, {'estado': 'indisponivel', 'erro': 'Registro de acesso indisponível. Avise a administração.'})
        elif api:
            self._json(401, {'estado': 'sem_sessao', 'codigo': 'sessao_expirada', 'erro': SEM_SESSAO})
        else:
            self._send(303, b'', 'text/plain; charset=utf-8', {'Location': '/entrar'})

    def _convite_antigo(self):
        """Old invitation links no longer sign anyone in; they point to the account sign-in page."""
        texto = ('<p lang="pt-BR">Os convites por link foram substituídos por contas individuais. '
                 'Peça à administração o link de ativação da sua conta, ou <a href="/entrar">entre com login e senha</a>.</p>'
                 '<p lang="en">Invitation links were replaced by individual accounts. Ask the administrators for your '
                 'account activation link, or <a href="/entrar">sign in with your login and password</a>.</p>')
        self._send(410, (f'<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
                         f'<meta name="viewport" content="width=device-width, initial-scale=1">'
                         f'<title>Vlado</title><link rel="stylesheet" href="/tokens.css"><link rel="stylesheet" href="/style.css"><main class="panel">{texto}</main></html>'
                         ).encode('utf-8'), 'text/html; charset=utf-8')

    def _pagina_recusada(self, recusa):
        """The page asked by an account the gate refused (a suspended newsroom): a plain notice, no data of anybody."""
        ingles = {'redacao_suspensa': "This account's newsroom is suspended. Talk to whoever runs the service."}
        texto = (f'<p lang="pt-BR">{html.escape(str(recusa.corpo.get("erro") or "Indisponível para esta conta."))}</p>'
                 f'<p lang="en">{html.escape(ingles.get(recusa.codigo, "Not available for this account."))}</p>')
        self._send(recusa.status, (f'<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
                                   f'<meta name="viewport" content="width=device-width, initial-scale=1">'
                                   f'<title>Vlado</title><link rel="stylesheet" href="/tokens.css"><link rel="stylesheet" href="/style.css"><main class="panel">{texto}</main></html>'
                                   ).encode('utf-8'), 'text/html; charset=utf-8')

    def _esqueci_ligado(self):
        """Whether "esqueci a senha" works here: only with real delivery, as there is nobody to show the link to
        (contract, 8.1). A wrong mail configuration reads as off."""
        try:
            return correio.transporte() != 'tela'
        except ValueError:
            return False

    def _ambiente_publico(self):
        if self.server.modo != 'piloto':
            return None
        valor = os.environ.get('VLADO_AMBIENTE', '').strip()
        return valor if valor in AMBIENTES else 'homologacao'

    def _ip(self):
        """The client address for rate limits and the audit log (SEG-02, SEG-05).

        With VLADO_PROXIES_CONFIAVEIS (IPs or networks): X-Forwarded-For counts only when the TCP peer is in the list,
        and the client is the first hop from the right that is NOT in the list (see scripts/proxies_confiaveis.py).
        Without the list: the TCP peer, or with VLADO_CONFIAR_PROXY=1 the last X-Forwarded-For hop (previous behaviour)."""
        if self.server.modo == 'piloto':
            redes = proxies_confiaveis.do_ambiente()
            if redes is not None:
                return proxies_confiaveis.ip_do_cliente(self.client_address[0],
                                                        ','.join(self.headers.get_all('X-Forwarded-For') or []), redes)
        if self.server.modo == 'piloto' and os.environ.get('VLADO_CONFIAR_PROXY', '').strip() == '1':
            saltos = [s.strip() for s in self.headers.get('X-Forwarded-For', '').split(',') if s.strip()]
            try:
                return str(ipaddress.ip_address(saltos[-1])) if saltos else self.client_address[0]
            except ValueError:
                pass  # garbage in the header: fall back to the socket address
        return self.client_address[0]

    def _sessao_atual(self):
        principal = self._principal()
        if principal is None:
            self._sem_principal(api=True)
            return
        redacao = principal.get('organizacao')
        self._json(200, {'conta': autorizacao.conta_publica(principal),
                         'organizacao': {'id': redacao['id'], 'nome': redacao['nome']} if redacao else None,
                         'pendencias': list(principal.get('pendencias') or []),
                         'capacidades': autorizacao.capacidades(principal),
                         'csrf': principal['csrf'], 'ambiente': self._ambiente_publico(),
                         'modo': self.server.modo, 'expira_em': principal.get('expira_em')})

    def _sair(self):
        acesso.encerrar(self.server.root, self._sessao_piloto()[1])
        self._send(200, b'{"estado": "encerrada"}', extra={
            'Set-Cookie': f'{COOKIE_PILOTO}=; {self.server.atributos_cookie()}; Max-Age=0'})

    def _equipe(self, operation, data, principal):
        """The own account (`conta-*`), the team (`equipe-*`) and who takes part in a case (`caso-*`). A refused
        operation is audited once (`admin_recusada`, with the reason: validation, wrong password, last dono, blocked)."""
        try:
            if operation in CONTA_PROPRIA:
                return conta_propria(self.server.root, operation, data, principal, ip=self._ip(), origem=self.server.origin)
            return rotas_equipe.executar(
                self.server.root, operation, data, principal, ip=self._ip(), parar=self._parar_execucoes,
                gasto_da_redacao=autorizacao.gasto_da_redacao(self.server.root, self.server.modo, principal),
                origem=self.server.origin, modo=self.server.modo)
        except (acesso.SenhaIncorreta, acesso.Bloqueado):
            raise  # already audited where the password is checked (`acesso.confirmar_senha`)
        except (ValueError, OSError) as exc:
            registro_acesso.registrar('admin_recusada', 'falha', principal.get('conta'),
                                      motivo=getattr(exc, 'motivo', 'validacao'), codigo=getattr(exc, 'codigo', None),
                                      alvo=data.get('conta') if isinstance(data.get('conta'), str) else None)
            raise

    def _parar_execucoes(self, conta_id, casos_mantidos):
        """A deactivated account, or a case taken away, must not keep spending the API in the background."""
        manager = self.server.conversas
        with manager.lock:
            alvos = [cid for cid, ctx in manager.contexts.items()
                     if conta_id in (ctx['meta'].get('dono'), ctx['meta'].get('conta'))
                     and ctx['meta'].get('caso') not in casos_mantidos
                     and ctx['meta'].get('estado') in ATIVOS_CONVERSA]
        for identificador in alvos:
            try:
                manager.cancelar(identificador)
            except (ValueError, OSError, KeyError):
                pass  # already finished or removed: nothing left to stop

    def _publico(self, operation):
        """Sign-in and activation, before any session: Origin + JSON, small body, generic refusals."""
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = -1
        if not 0 < length <= 4096:
            self.close_connection = True
            self._descartar_corpo_pequeno()  # up to 32 KB, as for any anonymous request; larger is never read
            self._json(400, {'erro': 'Requisição vazia ou muito grande.'})
            return
        body = self.rfile.read(length)
        registro_acesso.definir(operacao=operation)
        if (self.headers.get('Origin') != self.server.origin
                or self.headers.get_content_type() != 'application/json'):
            self._json(403, {'erro': 'Origem ou sessão não autorizada. Recarregue a página.'})
            return
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError('Requisição deve ser um objeto JSON.')
        except ValueError:
            self._json(400, {'erro': 'Requisição deve ser um objeto JSON.'})
            return
        root = self.server.root
        if operation == 'primeiro-admin':
            self._primeiro_admin(data)
            return
        try:
            if operation == 'entrar':
                sid, csrf, conta = acesso.entrar(root, data.get('login'), data.get('senha'), ip=self._ip(),
                                                 cliente=data.get('cliente', 'web'),
                                                 aparelho=aparelho(self.headers.get('User-Agent'), data.get('cliente', 'web')))
                publica = {k: conta[k] for k in ('id', 'nome', 'login', 'papel', 'casos')}
                self._send(200, json.dumps({'conta': publica, 'csrf': csrf, 'destino': autorizacao.destino_inicial(conta)},
                                           ensure_ascii=False).encode('utf-8'),
                           extra={'Set-Cookie': f'{COOKIE_PILOTO}={sid}; {self.server.atributos_cookie()}'})
            elif operation == 'entrar-segundo-fator':
                # The second step: the ticket is in a cookie of its own, good for this operation only.
                if set(data) - {'codigo'}:
                    raise ValueError('Campos inválidos no segundo passo da entrada.')
                sid, csrf, conta = acesso.entrar_segundo_fator(root, self._bilhete_do_segundo_passo(), data.get('codigo'),
                                                               ip=self._ip())
                publica = {k: conta[k] for k in ('id', 'nome', 'login', 'papel', 'casos')}
                self._send(200, json.dumps({'conta': publica, 'csrf': csrf, 'destino': autorizacao.destino_inicial(conta)},
                                           ensure_ascii=False).encode('utf-8'),
                           extra={'Set-Cookie': f'{COOKIE_PILOTO}={sid}; {self.server.atributos_cookie()}'})
            elif operation == 'ativacao-consultar':
                acesso.limitar_ip(self._ip(), 'consultar')
                self._json(200, acesso.consultar_ativacao(root, data.get('token')))
            elif operation == 'convite-consultar':
                acesso.limitar_ip(self._ip(), 'aceitar')
                self._json(200, acesso.consultar_convite(root, data.get('token')))
            elif operation == 'convite-aceitar':
                # The account is born and its first session opens, as a sign-in does. The e-mail is the invitation's.
                acesso.limitar_ip(self._ip(), 'aceitar')
                if set(data) - {'token', 'nome', 'senha', 'termos_versao', 'cliente'}:
                    raise ValueError('Campos inválidos no aceite do convite.')
                sid, csrf, conta = acesso.aceitar_convite(
                    root, data.get('token'), data.get('nome'), data.get('senha'), data.get('termos_versao'), ip=self._ip(),
                    cliente=data.get('cliente', 'web'),
                    aparelho=aparelho(self.headers.get('User-Agent'), data.get('cliente', 'web')))
                publica = {k: conta[k] for k in ('id', 'nome', 'login', 'email', 'papel', 'casos')}
                self._send(200, json.dumps({'conta': publica, 'csrf': csrf, 'destino': autorizacao.destino_inicial(conta)},
                                           ensure_ascii=False).encode('utf-8'),
                           extra={'Set-Cookie': f'{COOKIE_PILOTO}={sid}; {self.server.atributos_cookie()}'})
            elif operation == 'senha-esqueci':
                # One answer, in the same time, whether an account has the address or not: the message leaves in
                # another thread. Without real delivery there is nobody to show the link to (contract, 8.1).
                acesso.limitar_ip(self._ip(), 'esqueci')
                if not self._esqueci_ligado():
                    self._json(400, {'estado': 'erro', 'codigo': 'transporte_indisponivel', 'erro': ESQUECI_DESLIGADO})
                    return
                pedido = acesso.pedir_redefinicao(root, data.get('email'))
                if pedido:
                    token, quem = pedido
                    correio.enviar_depois('redefinicao', quem['email'], quem['idioma'],
                                          {'link': f'{self.server.origin}/redefinir/{token}', 'origem': self.server.origin,
                                           'minutos': acesso.REDEFINICAO_MINUTOS}, conta=quem['id'], raiz=root)
                self._json(200, {'estado': 'enviado', 'mensagem': ESQUECI_ENVIADO})
            elif operation == 'senha-redefinir':
                acesso.limitar_ip(self._ip(), 'redefinir')
                if set(data) - {'token', 'senha', 'codigo'}:
                    raise ValueError('Campos inválidos na redefinição de senha.')
                quem = acesso.redefinir_senha(root, data.get('token'), data.get('senha'), data.get('codigo'), self._ip())
                if quem['email']:
                    correio.enviar_depois('senha_trocada', quem['email'], quem['idioma'], {}, conta=quem['id'], raiz=root)
                self._json(200, {'estado': 'senha_redefinida'})
            elif operation == 'email-confirmar':
                # The link sent to the new address: the e-mail of the account changes, and the old address is told.
                acesso.limitar_ip(self._ip(), 'confirmar_email')
                if set(data) - {'token'}:
                    raise ValueError('Campos inválidos na confirmação do e-mail.')
                feito = acesso.confirmar_email(root, data.get('token'))
                if feito['antigo']:
                    correio.enviar_depois('email_trocado', feito['antigo'], feito['idioma'], {}, conta=feito['conta'], raiz=root)
                self._json(200, {'estado': 'email_confirmado'})
            else:
                acesso.limitar_ip(self._ip(), 'ativar')
                conta = acesso.ativar(root, data.get('token'), data.get('senha'))
                self._json(200, {'estado': 'senha_definida', 'login': conta['login']})
        except acesso.PedeSegundoFator as passo:
            # The password was right and the account has a second factor: no session, only the five-minute ticket.
            self._send(200, json.dumps({'estado': 'segundo_fator'}).encode('utf-8'), extra={
                'Set-Cookie': f'{COOKIE_SEGUNDO_PASSO}={passo.bilhete}; {self.server.atributos_cookie()}; '
                              f'Max-Age={acesso.ENTRADA_MINUTOS * 60}'})
        except acesso.RegistroIlegivel:
            self._json(503, {'estado': 'indisponivel', 'erro': 'Registro de acesso indisponível. Avise a administração.'})
        except acesso.Bloqueado as exc:
            self._json(429, {'estado': 'bloqueado', 'codigo': 'bloqueado', 'erro': str(exc)})
        except acesso.EntradaExpirada as exc:
            self._json(401, {'estado': 'credenciais', 'codigo': 'entrada_expirada', 'erro': str(exc)})
        except acesso.CodigoInvalido as exc:  # the second factor, in the second step or in a reset by e-mail
            self._json(403, {'estado': 'proibido', 'codigo': 'codigo_invalido', 'erro': str(exc)})
        except acesso.CredenciaisInvalidas as exc:
            self._json(401, {'estado': 'credenciais', 'codigo': 'credenciais', 'erro': str(exc)})
        except acesso.AtivacaoInvalida as exc:
            self._json(400, {'estado': 'erro', 'codigo': 'ativacao_invalida', 'erro': str(exc)})
        except acesso.ConviteInvalido as exc:  # one answer for every link that creates nothing
            self._json(400, {'estado': 'erro', 'codigo': 'convite_invalido', 'erro': str(exc)})
        except acesso.LinkInvalido as exc:  # and one for every reset link that changes nothing
            self._json(400, {'estado': 'erro', 'codigo': 'link_invalido', 'erro': str(exc)})
        except acesso.SenhaInvalida as exc:  # the password chosen is out of size: the page says so under the field
            if operation == 'ativar':
                registro_acesso.registrar('ativacao_falha', 'falha', motivo='validacao', acesso_operacao='ativar')
            self._json(400, {'estado': 'erro', 'codigo': 'senha_invalida', 'erro': str(exc)})
        except (ValueError, OSError) as exc:
            if operation == 'ativar':  # a refused password (too short...) is not a bad link: audited as validation
                registro_acesso.registrar('ativacao_falha', 'falha', motivo='validacao', acesso_operacao='ativar')
            self._json(400, {'estado': 'erro', 'codigo': 'senha_invalida' if operation == 'ativar' else 'requisicao_invalida',
                             'erro': str(exc) if isinstance(exc, ValueError) else 'Falha ao ler arquivos do servidor.'})

    def _primeiro_admin(self, data):
        """'Criar administrador': local mode with accounts, loopback only, while no account exists."""
        if not self._cliente_local():
            self._json(403, {'erro': 'Origem ou sessão não autorizada. Recarregue a página.'})
            return
        try:
            acesso.limitar_ip(self._endereco_socket(), 'primeiro_admin')
            senha = data.get('senha')
            if not isinstance(senha, str) or not acesso.SENHA_MIN <= len(senha) <= acesso.SENHA_MAX:
                self._json(400, {'estado': 'erro', 'codigo': 'senha_invalida',
                                 'erro': f'A senha deve ter de {acesso.SENHA_MIN} a {acesso.SENHA_MAX} caracteres.'})
                return
            if data.get('confirmacao') != senha:
                self._json(400, {'estado': 'erro', 'codigo': 'senha_diferente', 'erro': 'As duas senhas não coincidem.'})
                return
            conta = acesso.criar_primeiro_admin(self.server.root, data.get('nome'), data.get('login'), senha)
            self._json(200, {'estado': 'criada', 'login': conta['login']})
        except acesso.PrimeiroAcessoEncerrado as exc:
            self._json(410, {'estado': 'encerrado', 'codigo': 'primeiro_acesso_encerrado', 'erro': str(exc)})
        except acesso.RegistroIlegivel:
            self._json(503, {'estado': 'indisponivel', 'erro': 'Registro de acesso indisponível.'})
        except acesso.Bloqueado as exc:
            self._json(429, {'estado': 'bloqueado', 'codigo': 'bloqueado', 'erro': str(exc)})
        except (ValueError, OSError) as exc:
            self._json(400, {'estado': 'erro', 'codigo': 'dados_invalidos',
                             'erro': str(exc) if isinstance(exc, ValueError) else 'Falha ao gravar a conta.'})
