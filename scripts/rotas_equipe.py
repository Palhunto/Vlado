"""A equipe de uma redação (``POST /api/equipe-*``) e quem participa de uma apuração (``POST /api/caso-*``).

Contrato de contas, seções 2.5, 5.5, 5.6 e 5.15. O portão (``autorizacao.conferir``) já conferiu, antes de chegar
aqui, que o papel alcança a operação: as ``equipe-*`` são só do dono; nas ``caso-*``, a apuração está ao alcance de
quem pede, o dono em toda apuração da redação e o repórter, para incluir e retirar, só nas que é responsável. Aqui
ficam a lista fechada dos campos e o despacho para ``acesso``, que guarda as regras:

- tudo age só sobre a redação da sessão: a conta de outra redação responde como inexistente;
- só entram numa apuração contas da mesma redação; o responsável é dono ou repórter e não é retirado sem que outro
  seja indicado;
- a redação nunca fica sem dono ativo; o perfil legado ``convidado`` não é atribuído a ninguém;
- promover a dono, mudar o papel de um dono, desativar um dono e remover qualquer pessoa pedem a senha de quem faz
  (campo ``senha``); a senha errada conta para o teto de tentativas;
- o convite (``equipe-convidar``, ``equipe-convite-reenviar``, ``equipe-convite-cancelar``) leva e-mail, papel e
  apurações; convidar como dono pede a senha. A mensagem sai por ``correio``; o link só volta na resposta com o
  transporte ``tela``.

As respostas levam nomes, e-mails e gasto de colegas da própria redação e nada das apurações. Sem modelo; a única
saída para a rede é o e-mail do convite, pelo transporte ``smtp``. Nenhum caminho vem do cliente. Este módulo não lê
o papel de quem chama.
"""
from __future__ import annotations

import acesso
import correio
import custo

OPERACOES_CASO = ('caso-participantes', 'caso-incluir', 'caso-retirar', 'caso-responsavel')
OPERACOES_EQUIPE = ('equipe-listar', 'equipe-papel', 'equipe-desativar', 'equipe-reativar', 'equipe-remover',
                    'equipe-teto', 'equipe-atividade', 'equipe-convidar', 'equipe-convite-reenviar',
                    'equipe-convite-cancelar')
OPERACOES = (*OPERACOES_CASO, *OPERACOES_EQUIPE)
_CAMPOS = {'caso-participantes': {'caso'}, 'caso-incluir': {'caso', 'conta'}, 'caso-retirar': {'caso', 'conta'},
           'caso-responsavel': {'caso', 'conta'},
           'equipe-listar': set(), 'equipe-papel': {'conta', 'papel', 'senha'}, 'equipe-desativar': {'conta', 'senha'},
           'equipe-reativar': {'conta'}, 'equipe-remover': {'conta', 'senha'}, 'equipe-teto': {'conta', 'teto_brl'},
           'equipe-atividade': {'limite', 'antes'},
           'equipe-convidar': {'email', 'papel', 'casos', 'idioma', 'senha'}, 'equipe-convite-reenviar': {'convite'},
           'equipe-convite-cancelar': {'convite'}}
_ACOES = {'caso-incluir': acesso.incluir_participante, 'caso-retirar': acesso.retirar_participante,
          'caso-responsavel': acesso.definir_responsavel}


def _gasto(root, conta, da_redacao=False):
    """This month's spend of one account in reais, or None when the spend record cannot be read: the team screen
    must still open, to administer people. With `da_redacao`, the newsroom's block instead."""
    try:
        situacao = custo.situacao(root, conta, administrador=da_redacao)
        return {'mes': situacao['mes'], **situacao['organizacao' if da_redacao else 'conta']}
    except (ValueError, OSError, KeyError):
        return None


def _listar(root, redacao, principal, gasto_da_redacao):
    resposta = acesso.equipe(root, redacao)
    for pessoa in resposta['pessoas']:
        pessoa['gasto'] = _gasto(root, pessoa['id'])
    # The newsroom's spend only when the cost module counts it by newsroom: a number that adds newsrooms never goes.
    resposta['gasto'] = _gasto(root, principal['conta'], da_redacao=True) if gasto_da_redacao else None
    return resposta


def _convite(root, operation, data, redacao, quem, ip, origem):
    """Invitations (contrato de contas, 8.1). The store decides and keeps only the hash of the token; the message
    leaves from here, after the transaction. The link goes back in the answer only with the transport ``tela``
    (nothing is sent: who invited hands it over). No answer says whether the e-mail has an account elsewhere."""
    if operation == 'equipe-convite-cancelar':
        return {'convite': acesso.cancelar_convite(root, redacao, quem, data.get('convite'))}
    if operation == 'equipe-convidar':
        convite, token, contexto = acesso.convidar(root, redacao, quem, data.get('email'), data.get('papel'),
                                                   data.get('casos') or [], data.get('idioma'), data.get('senha'), ip)
    else:
        convite, token, contexto = acesso.reenviar_convite(root, redacao, quem, data.get('convite'))
    link = f'{(origem or "").rstrip("/")}/aceitar/{token}'
    try:
        usado = correio.enviar('convite_sem_efeito' if contexto['sem_efeito'] else 'convite', convite['email'],
                               convite['idioma'], {'redacao': contexto['redacao'], 'convidado_por': contexto['convidado_por'],
                                                   'papel': convite['papel'], 'validade': convite['expira_em'][:10],
                                                   'link': link, 'origem': origem}, conta=quem)
        envio = 'tela' if usado == 'tela' else 'enviado'
    except (correio.FalhaDeEnvio, correio.ErroDeCorreio):
        envio = 'falha'  # the dono sees it in the list and sends it again
    acesso.registrar_envio(root, convite['id'], envio)
    return {'convite': {**convite, 'envio': envio}, **({'link': link} if envio == 'tela' else {})}


def executar(root, operation, data, principal, ip=None, parar=None, gasto_da_redacao=False, origem=None):
    """``principal`` é a conta da sessão: dele vêm a redação e quem faz, nunca do corpo do pedido. ``parar`` é
    chamado com o id de uma conta desativada ou removida, para o servidor parar as execuções dela em curso.
    ``origem`` é o endereço da própria instalação, para o link do convite."""
    if operation not in OPERACOES or not isinstance(data, dict):
        raise ValueError('Operação de equipe desconhecida.')
    if set(data) - _CAMPOS[operation]:
        raise ValueError('Campos inválidos no pedido de equipe.')
    redacao = (principal.get('organizacao') or {}).get('id')
    quem = principal.get('conta')
    if not redacao or not quem:
        raise ValueError('Contas só existem nos modos com login.')
    if operation == 'caso-participantes':
        return acesso.participantes(root, data.get('caso'), redacao)
    if operation in _ACOES:
        return _ACOES[operation](root, data.get('caso'), data.get('conta'), quem, redacao)
    if operation == 'equipe-listar':
        return _listar(root, redacao, principal, gasto_da_redacao)
    if operation == 'equipe-atividade':
        return acesso.atividade(root, redacao, data.get('limite', 50), data.get('antes'))
    if 'convi' in operation:
        return _convite(root, operation, data, redacao, quem, ip, origem)
    alvo = data.get('conta')
    if operation == 'equipe-teto':
        if 'teto_brl' not in data:
            raise ValueError(acesso.TETO_INVALIDO)
        padrao = custo.ler_orcamento(root)['mensal_organizacao_brl']  # the installation's, where the newsroom has none
        resultado = acesso.definir_teto(root, redacao, quem, data['teto_brl'], alvo, teto_padrao=padrao)
        return {'conta': resultado} if alvo is not None else {'redacao': resultado}
    if operation == 'equipe-papel':
        return {'conta': acesso.mudar_papel(root, alvo, data.get('papel'), quem, redacao, data.get('senha'), ip)}
    if operation == 'equipe-reativar':
        return {'conta': acesso.reativar(root, alvo, por=quem, organizacao=redacao)}
    if operation == 'equipe-desativar':
        registro = acesso.desativar(root, alvo, por=quem, organizacao=redacao, confirmar=True, senha=data.get('senha'), ip=ip)
    else:
        registro = acesso.remover(root, alvo, quem, redacao, data.get('senha'), ip)
    if parar is not None:
        parar(registro['id'], ())
    return {'conta': registro}

