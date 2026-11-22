"""Convite por e-mail (contrato de contas, seções 5.3, 5.5 e 8.1), no armazenamento e pelo servidor.

O dono convida um e-mail com papel e apurações; a pessoa aceita pelo link, escolhe nome e senha, e a conta nasce
com o e-mail do convite, que passa a ser o identificador da entrada. O token só existe no link. Convite para
e-mail que já tem conta em outra redação recebe a mesma resposta de qualquer outro e não cria conta. Pelo
servidor: duas redações em modo ``piloto`` (``cenario_redacoes``), com o transporte ``tela`` (o padrão) e com o
``simulado``, de onde o teste lê o link. Sem modelo e sem rede.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
import correio
import test_acesso  # module import: its TestCases are not collected again here
from test_acesso import SENHA

ERRADA = 'senha-errada-de-teste'
CHAVES_DO_CONVITE = {'id', 'email', 'papel', 'casos', 'idioma', 'estado', 'criado_em', 'enviado_em', 'expira_em', 'envio',
                     'convidado_por', 'convidado_por_nome'}


class ArmazenamentoTest(test_acesso.DuasRedacoes):
    """The rules of the store."""

    def convidar(self, email='nova@exemplo.test', papel='reporter', casos=('caso_a',), redacao=None, por=None, **mais):
        redacao = redacao or self.a
        return acesso.convidar(self.root, redacao, por or (self.dono_a if redacao == self.a else self.dono_b), email, papel,
                               list(casos), **mais)

    def aceitar(self, token, nome='Nova Pessoa', senha=SENHA, **mais):
        return acesso.aceitar_convite(self.root, token, nome, senha, **mais)

    def test_convite_guarda_so_o_hash_do_token_e_aparece_entre_os_pendentes(self):
        convite, token, contexto = self.convidar(' Nova@Exemplo.Test ', idioma='en')
        self.assertEqual(set(convite), CHAVES_DO_CONVITE)
        self.assertEqual((convite['email'], convite['papel'], convite['casos'], convite['idioma'], convite['estado']),
                         ('nova@exemplo.test', 'reporter', ['caso_a'], 'en', 'pendente'))
        self.assertEqual((convite['convidado_por'], convite['convidado_por_nome']), (self.dono_a, 'Dona A'))
        self.assertEqual(contexto, {'redacao': 'Redação A', 'convidado_por': 'Dona A', 'sem_efeito': False})
        self.assertNotIn(token, self.bruto())
        self.assertNotIn(token, json.dumps(convite))
        self.assertEqual(acesso._data(convite['expira_em']) - acesso._data(convite['criado_em']),
                         test_acesso.timedelta(days=acesso.CONVITE_DIAS))
        self.assertEqual([c['id'] for c in acesso.equipe(self.root, self.a)['convites']], [convite['id']])
        self.assertEqual(acesso.equipe(self.root, self.b)['convites'], [])  # the other newsroom does not see it
        self.assertIn('convite_enviado', self.tipos())

    def test_email_papel_e_apuracoes_do_convite_sao_conferidos(self):
        for email in ('', None, 'sem-arroba', 'a@b', 'ana@exem\nplo.test', 'ana maria@exemplo.test', 'x' * 250 + '@exemplo.test',
                      'ana@exemplo.test|203.0.113.5', '#senha@exemplo.test'):
            with self.assertRaisesRegex(ValueError, 'e-mail'):
                self.convidar(email)
        for papel in ('convidado', 'admin', 'operador', None):
            with self.assertRaisesRegex(ValueError, 'Papel'):
                self.convidar(papel=papel)
        for casos in (['caso_b'], ['nao_existe'], ['../x'], 'caso_a'):  # another newsroom's case reads as unknown
            with self.assertRaises(ValueError):
                self.convidar(casos=casos)
        with self.assertRaisesRegex(ValueError, 'Idioma'):
            self.convidar(idioma='fr')
        self.assertEqual(self.linhas('SELECT * FROM convites'), [])

    def test_convidar_como_dono_pede_a_senha_de_quem_convida_e_ignora_apuracoes(self):
        with self.assertRaises(acesso.SenhaNecessaria):
            self.convidar(papel='dono')
        with self.assertRaises(acesso.SenhaIncorreta):
            self.convidar(papel='dono', senha=ERRADA)
        self.assertEqual(self.linhas('SELECT * FROM convites'), [])
        convite, token, _ = self.convidar(papel='dono', casos=['caso_a'], senha=SENHA)
        self.assertEqual((convite['papel'], convite['casos']), ('dono', []))
        sid, _, conta = self.aceitar(token)
        self.assertEqual((conta['papel'], acesso.sessao(self.root, sid)['casos']), ('dono', ['caso_a']))  # a dono reaches every case

    def test_aceitar_cria_a_conta_com_o_email_o_papel_e_as_apuracoes_e_abre_a_sessao(self):
        convite, token, _ = self.convidar(idioma='en')
        consulta = acesso.consultar_convite(self.root, token)
        self.assertEqual(consulta, {'redacao': 'Redação A', 'email': 'nova@exemplo.test', 'papel': 'reporter',
                                    'convidado_por': 'Dona A', 'expira_em': convite['expira_em'], 'idioma': 'en',
                                    'termos_versao': None})
        for nome, senha in (('', SENHA), ('a\nb', SENHA), ('Nova', 'curta')):
            with self.assertRaises(ValueError):
                self.aceitar(token, nome, senha)
        with self.assertRaisesRegex(ValueError, 'termos'):
            self.aceitar(token, termos_versao='2026-01')
        sid, csrf, conta = self.aceitar(token, '  Nova Pessoa ', ip='198.51.100.7', aparelho='Firefox · Linux')
        self.assertEqual((conta['nome'], conta['email'], conta['login'], conta['papel'], conta['casos'], conta['situacao']),
                         ('Nova Pessoa', 'nova@exemplo.test', None, 'reporter', ['caso_a'], 'ativa'))
        self.assertEqual(conta['organizacao'], self.a)
        principal = acesso.sessao(self.root, sid)
        self.assertEqual((principal['conta'], principal['email'], principal['casos']), (conta['id'], 'nova@exemplo.test', ['caso_a']))
        self.assertEqual(acesso.sessoes_da_conta(self.root, conta['id'])[0]['aparelho'], 'Firefox · Linux')
        self.assertEqual(acesso.ver_conta(self.root, conta['id'])['conta']['idioma'], 'en')
        self.assertEqual(self.registro(conta['id'])['criada_por'], self.dono_a)
        for segredo in (token, sid, SENHA):  # the store keeps hashes of the link, of the cookie and of the password
            self.assertNotIn(segredo, self.bruto())
        self.assertTrue(csrf)
        self.assertIn('convite_aceito', self.tipos())
        self.assertEqual(acesso.equipe(self.root, self.a)['convites'], [])
        self.assertEqual(self.linhas('SELECT estado, conta, token_sha256 FROM convites'),
                         [{'estado': 'aceito', 'conta': conta['id'], 'token_sha256': None}])
        for acao in (lambda: self.aceitar(token), lambda: acesso.consultar_convite(self.root, token)):  # the link works once
            with self.assertRaises(acesso.ConviteInvalido):
                acao()

    def test_o_email_passa_a_ser_o_identificador_da_entrada(self):
        _, token, _ = self.convidar()
        _, _, conta = self.aceitar(token)
        self.assertEqual(acesso.entrar(self.root, ' Nova@Exemplo.Test ', SENHA)[2]['id'], conta['id'])
        self.assertEqual(acesso.entrar(self.root, 'dona.a', SENHA)[2]['id'], self.dono_a)  # the old login goes on
        # Wrong passwords: the same answers for an e-mail with an account and for one without.
        respostas = {}
        for email in ('nova@exemplo.test', 'ninguem@exemplo.test'):
            respostas[email] = []
            for _ in range(acesso.FALHAS_BLOQUEIO + 1):
                try:
                    acesso.entrar(self.root, email, ERRADA, ip='203.0.113.5')
                except ValueError as exc:
                    respostas[email].append((type(exc).__name__, str(exc)))
        self.assertEqual(respostas['nova@exemplo.test'], respostas['ninguem@exemplo.test'])
        self.assertEqual(respostas['nova@exemplo.test'][-1][0], 'Bloqueado')
        acesso.trocar_senha(self.root, conta['id'], SENHA, 'outra-senha-longa-2')  # clears the counters of the e-mail too
        self.assertEqual(self.linhas("SELECT chave FROM tentativas WHERE chave LIKE 'nova@%'"), [])

    def test_email_que_ja_e_da_redacao_e_recusado_dizendo_por_que(self):
        _, token, _ = self.convidar()
        with self.assertRaisesRegex(acesso.ConviteDuplicado, 'pendente') as recusa:
            self.convidar()
        self.assertEqual((recusa.exception.status, recusa.exception.codigo), (400, 'convite_duplicado'))
        self.aceitar(token)
        with self.assertRaisesRegex(acesso.ConviteDuplicado, 'já faz parte'):
            self.convidar(papel='leitor')
        self.assertEqual(len(self.linhas('SELECT 1 FROM convites')), 1)

    def test_email_com_conta_em_outra_redacao_recebe_a_mesma_resposta_e_o_link_nao_cria_conta(self):
        _, token_b, _ = self.convidar('pessoa@exemplo.test', casos=['caso_b'], redacao=self.b)
        _, _, de_b = self.aceitar(token_b, 'Pessoa de B')
        livre, _, contexto_livre = self.convidar('livre@exemplo.test')
        convite, token, contexto = self.convidar('pessoa@exemplo.test')  # Alfa invites who is already of Beta
        self.assertEqual(set(convite), set(livre))
        self.assertEqual((convite['estado'], convite['envio']), (livre['estado'], livre['envio']))
        self.assertEqual((contexto_livre['sem_efeito'], contexto['sem_efeito']), (False, True))  # only the message knows
        self.assertNotIn('sem_efeito', json.dumps(convite))
        self.assertIn(convite['id'], [c['id'] for c in acesso.equipe(self.root, self.a)['convites']])  # pending like the rest
        for acao in (lambda: acesso.consultar_convite(self.root, token), lambda: self.aceitar(token)):
            with self.assertRaises(acesso.ConviteInvalido) as recusa:
                acao()
            self.assertEqual((str(recusa.exception), recusa.exception.motivo), (acesso.CONVITE_INVALIDO, 'email_em_uso'))
        self.assertEqual(self.registro(de_b['id'])['organizacao'], self.b)  # nothing changed in the account
        self.assertEqual(len(self.linhas('SELECT 1 FROM contas WHERE email = ?', 'pessoa@exemplo.test')), 1)
        with self.depois(minutes=acesso.REENVIO_MINUTOS + 1):
            self.assertTrue(acesso.reenviar_convite(self.root, self.a, self.dono_a, convite['id'])[2]['sem_efeito'])
        self.assertEqual(acesso.cancelar_convite(self.root, self.a, self.dono_a, convite['id'])['estado'], 'cancelado')

    def test_dois_convites_para_o_mesmo_email_em_redacoes_diferentes_o_primeiro_aceite_vale(self):
        _, token_a, _ = self.convidar('disputado@exemplo.test')
        _, token_b, _ = self.convidar('disputado@exemplo.test', casos=['caso_b'], redacao=self.b)
        self.assertEqual(self.aceitar(token_b)[2]['organizacao'], self.b)
        with self.assertRaises(acesso.ConviteInvalido):
            self.aceitar(token_a)

    def test_reenviar_troca_o_link_e_so_uma_vez_por_hora(self):
        convite, token, _ = self.convidar()
        with self.assertRaises(acesso.LimiteDeConvites) as recusa:
            acesso.reenviar_convite(self.root, self.a, self.dono_a, convite['id'])
        self.assertEqual((recusa.exception.status, recusa.exception.codigo), (429, 'limite_de_convites'))
        self.assertEqual(acesso.consultar_convite(self.root, token)['email'], 'nova@exemplo.test')  # still the first link
        with self.depois(minutes=acesso.REENVIO_MINUTOS + 1):
            novo, token2, _ = acesso.reenviar_convite(self.root, self.a, self.dono_a, convite['id'])
            self.assertEqual(novo['id'], convite['id'])
            self.assertGreater(novo['expira_em'], convite['expira_em'])  # a new week
            with self.assertRaises(acesso.ConviteInvalido):
                acesso.consultar_convite(self.root, token)  # the link of before stopped working
            self.assertEqual(self.aceitar(token2)[2]['email'], 'nova@exemplo.test')
        self.assertIn('convite_reenviado', self.tipos())

    def test_cancelar_mata_o_link_e_convite_de_outra_redacao_responde_como_inexistente(self):
        convite, token, _ = self.convidar()
        for acao in (acesso.cancelar_convite, acesso.reenviar_convite):
            for alvo, redacao, quem in ((convite['id'], self.b, self.dono_b), ('0123456789abcdef', self.a, self.dono_a),
                                        (None, self.a, self.dono_a), (['x'], self.a, self.dono_a)):
                with self.assertRaisesRegex(ValueError, acesso.CONVITE_INEXISTENTE):
                    acao(self.root, redacao, quem, alvo)
        self.assertEqual(acesso.consultar_convite(self.root, token)['papel'], 'reporter')  # untouched by the other newsroom
        self.assertEqual(acesso.cancelar_convite(self.root, self.a, self.dono_a, convite['id'])['estado'], 'cancelado')
        with self.assertRaises(acesso.ConviteInvalido):
            self.aceitar(token)
        with self.assertRaisesRegex(ValueError, acesso.CONVITE_INEXISTENTE):
            acesso.cancelar_convite(self.root, self.a, self.dono_a, convite['id'])
        self.assertEqual(self.convidar()[0]['estado'], 'pendente')  # the e-mail can be invited again
        self.assertIn('convite_cancelado', self.tipos())

    def test_cada_redacao_tem_teto_de_convites_pendentes(self):
        with patch.object(acesso, 'CONVITES_PENDENTES', 3):
            for numero in range(3):
                self.convidar(f'pessoa{numero}@exemplo.test')
            with self.assertRaises(acesso.LimiteDeConvites):
                self.convidar('demais@exemplo.test')
            self.assertEqual(self.convidar('pessoa0@exemplo.test', casos=['caso_b'], redacao=self.b)[0]['estado'], 'pendente')
            acesso.cancelar_convite(self.root, self.a, self.dono_a, acesso.equipe(self.root, self.a)['convites'][0]['id'])
            self.assertEqual(self.convidar('demais@exemplo.test')[0]['estado'], 'pendente')

    def test_cancelar_e_convidar_de_novo_nao_passa_do_teto_por_endereco(self):
        # "Once an hour" for each invitation is not enough if cancelling and inviting again starts another one.
        for _ in range(acesso.CONVITES_POR_ENDERECO):
            convite, _, _ = self.convidar()
            acesso.cancelar_convite(self.root, self.a, self.dono_a, convite['id'])
        with self.assertRaisesRegex(acesso.LimiteDeConvites, 'última hora'):
            self.convidar()
        self.assertEqual(self.convidar('outra@exemplo.test')[0]['estado'], 'pendente')  # another address is not held back
        self.assertEqual(self.convidar(casos=['caso_b'], redacao=self.b)[0]['estado'], 'pendente')  # nor another newsroom
        with self.depois(minutes=acesso.REENVIO_MINUTOS + 1):
            self.assertEqual(self.convidar()[0]['estado'], 'pendente')

    def test_convite_pendente_nao_sobrevive_a_quem_convidou(self):
        # An invitation is an act of a dono: it stays good only while who made it could still make it.
        outra = self.pessoa('Outra Dona', 'outra.dona', 'dono', self.a)
        tokens = {}
        for acao in ('rebaixar', 'desativar', 'remover'):
            _, tokens[acao], _ = self.convidar(f'{acao}@exemplo.test', por=outra)
            _, da_dona, _ = self.convidar(f'fica.{acao}@exemplo.test')
            if acao == 'rebaixar':
                acesso.mudar_papel(self.root, outra, 'editor', self.dono_a, self.a, SENHA)
            elif acao == 'desativar':
                acesso.desativar(self.root, outra, por=self.dono_a, organizacao=self.a)
            else:
                acesso.remover(self.root, outra, self.dono_a, self.a, SENHA)
            with self.assertRaises(acesso.ConviteInvalido, msg=acao):
                acesso.consultar_convite(self.root, tokens[acao])
            self.assertEqual(acesso.consultar_convite(self.root, da_dona)['papel'], 'reporter')  # the others' go on
            if acao == 'rebaixar':
                acesso.mudar_papel(self.root, outra, 'dono', self.dono_a, self.a, SENHA)
            elif acao == 'desativar':
                acesso.reativar(self.root, outra, por=self.dono_a, organizacao=self.a)
                self.assertEqual(len(self.linhas("SELECT 1 FROM convites WHERE criado_por = ? AND estado = 'pendente'", outra)), 0)
        self.assertEqual(len(self.linhas("SELECT 1 FROM convites WHERE criado_por = ? AND estado = 'cancelado'", outra)), 3)
        self.assertGreaterEqual(self.tipos().count('convite_cancelado'), 3)

    def test_convite_vence_em_sete_dias_e_a_varredura_o_encerra(self):
        convite, token, _ = self.convidar()
        with self.depois(days=acesso.CONVITE_DIAS, minutes=1):
            with self.assertRaises(acesso.ConviteInvalido) as recusa:
                acesso.consultar_convite(self.root, token)
            self.assertEqual(recusa.exception.motivo, 'link_expirado')
            with self.assertRaises(acesso.ConviteInvalido):
                self.aceitar(token)
            self.assertEqual(acesso.equipe(self.root, self.a)['convites'], [])  # not pending any more, even before the sweep
            self.assertEqual(self.linhas('SELECT estado FROM convites'), [{'estado': 'pendente'}])
            self.assertEqual(acesso.manutencao(self.root)['convites_vencidos'], 1)
            self.assertEqual(self.linhas('SELECT estado, token_sha256 FROM convites'), [{'estado': 'expirado', 'token_sha256': None}])
            self.assertEqual(acesso.manutencao(self.root)['convites_vencidos'], 0)
            evento = self.linhas("SELECT * FROM eventos WHERE tipo = 'convite_expirado'")[0]
            self.assertEqual((evento['organizacao'], evento['por'], evento['conta']), (self.a, 'manutencao', None))
            self.assertEqual(self.convidar()[0]['estado'], 'pendente')  # and the e-mail can be invited again
        self.assertEqual(self.linhas('SELECT 1 FROM contas WHERE email IS NOT NULL'), [])  # no account was ever half-made

    def test_varredura_poda_a_atividade_com_mais_de_noventa_dias(self):
        self.convidar()
        antes = len(self.tipos())
        self.gravar("INSERT INTO eventos (em, tipo, conta, por, organizacao) VALUES (?, 'conta_criada', 'x', 'cli', ?)",
                    acesso._iso(acesso.agora() - test_acesso.timedelta(days=acesso.ATIVIDADE_DIAS + 1)), self.a)
        with patch.object(acesso.registro_acesso, 'arquivar_evento') as arquivar:
            self.assertEqual(acesso.manutencao(self.root), {'convites_vencidos': 0, 'eventos_podados': 1})
        self.assertEqual(arquivar.call_count, 1)  # what leaves goes to the audit log
        self.assertEqual(len(self.tipos()), antes)

    def test_apuracao_apagada_depois_do_convite_fica_de_fora_e_redacao_suspensa_nao_recebe_ninguem(self):
        _, token, _ = self.convidar()
        acesso.marcar_caso_apagado(self.root, 'caso_a')
        acesso.definir_situacao_redacao(self.root, self.a, 'suspensa')
        with self.assertRaises(acesso.ConviteInvalido):
            self.aceitar(token)
        acesso.definir_situacao_redacao(self.root, self.a, 'ativa')
        self.assertEqual(self.aceitar(token)[2]['casos'], [])


class ServidorTest(cenario.DuasRedacoes):
    """Through the server, with two newsrooms."""
    numero = 0

    def setUp(self):
        acesso.limpar_limites()
        correio.limpar_caixa()

    def email(self):
        type(self).numero += 1
        return f'convidada{self.numero}@exemplo.test'

    def publico(self, operacao, dados):
        status, cabecalhos, corpo = self.pedir('POST', '/api/' + operacao, json.dumps(dados),
                                               {'Content-Type': 'application/json', 'Origin': cenario.ORIGEM})
        return status, json.loads(corpo or b'{}'), cabecalhos, corpo

    def convidar(self, quem='dono', **dados):
        dados = {'email': self.email(), 'papel': 'reporter', 'casos': ['alpha'], **dados}
        status, corpo, bruto = self.post(quem, 'equipe-convidar', dados)
        self.assertEqual(status, 200, bruto[:300])
        return corpo, bruto

    def pendentes(self, quem='dono'):
        return {c['id']: c for c in self.post(quem, 'equipe-listar', {})[1]['convites']}

    def test_com_o_link_na_tela_o_dono_recebe_o_link_e_a_pessoa_aceita(self):
        corpo, _ = self.convidar(idioma='en')
        convite, link = corpo['convite'], corpo['link']
        self.assertEqual(set(convite), CHAVES_DO_CONVITE)
        self.assertEqual((convite['papel'], convite['casos'], convite['envio'], convite['convidado_por_nome']),
                         ('reporter', ['alpha'], 'tela', 'Dona Alfa'))
        self.assertRegex(link, '^' + cenario.ORIGEM + r'/aceitar/[A-Za-z0-9_-]{43}$')
        self.assertEqual(self.pendentes()[convite['id']]['envio'], 'tela')
        self.assertNotIn(convite['id'], self.pendentes('dono_b'))
        self.assertNotIn(link.rsplit('/', 1)[1], self.post('dono', 'equipe-listar', {})[2].decode('utf-8'))  # the token is only in the link
        token = link.rsplit('/', 1)[1]
        status, consulta, _, bruto = self.publico('convite-consultar', {'token': token})
        self.assertEqual((status, consulta['redacao'], consulta['email'], consulta['papel'], consulta['convidado_por']),
                         (200, 'Redação Alfa', convite['email'], 'reporter', 'Dona Alfa'), bruto[:200])
        self.sem_sentinela(bruto)
        for dados in ({'token': token, 'nome': 'Nova Pessoa', 'senha': 'curta'},
                      {'token': token, 'nome': 'Nova Pessoa', 'senha': SENHA, 'email': 'outro@exemplo.test'},  # W10, rule 3
                      {'token': token, 'nome': 'Nova Pessoa', 'senha': SENHA, 'papel': 'dono'}):
            self.assertEqual(self.publico('convite-aceitar', dados)[0], 400, dados)
        status, aceite, cabecalhos, bruto = self.publico('convite-aceitar', {'token': token, 'nome': 'Nova Pessoa', 'senha': SENHA,
                                                                             'termos_versao': None})
        self.assertEqual((status, aceite['conta']['email'], aceite['conta']['papel'], aceite['conta']['casos']),
                         (200, convite['email'], 'reporter', ['alpha']), bruto[:200])
        self.assertNotIn(SENHA, bruto.decode('utf-8'))
        sessao = (cabecalhos['Set-Cookie'].split(';')[0], aceite['csrf'])
        self.assertIn('HttpOnly', cabecalhos['Set-Cookie'])
        perfil = self.post(sessao, 'conta-ver', {})[1]
        self.assertEqual((perfil['conta']['email'], perfil['conta']['idioma'], perfil['organizacao']['nome']),
                         (convite['email'], 'en', 'Redação Alfa'))
        self.assertEqual(self.post(sessao, 'analises', {'caso': 'beta'})[0], 404)  # the new account reaches its newsroom only
        self.assertEqual(self.post(sessao, 'equipe-listar', {})[0], 403)
        self.assertNotIn(convite['id'], self.pendentes())
        self.assertIn(convite['email'], {p['email'] for p in self.post('dono', 'equipe-listar', {})[1]['pessoas']})
        usado = self.publico('convite-aceitar', {'token': token, 'nome': 'Outra', 'senha': SENHA})
        self.assertEqual((usado[0], usado[1]['codigo']), (400, 'convite_invalido'))
        entrada = self.publico('entrar', {'login': convite['email'], 'senha': SENHA})
        self.assertEqual((entrada[0], entrada[1]['conta']['id']), (200, aceite['conta']['id']))

    def test_com_envio_de_verdade_o_link_vai_so_na_mensagem(self):
        with correio.usar('simulado'):
            corpo, bruto = self.convidar()
        self.assertNotIn('link', corpo)
        self.assertEqual(corpo['convite']['envio'], 'enviado')
        mensagem, = correio.caixa()
        self.assertEqual((mensagem['tipo'], mensagem['para']), ('convite', corpo['convite']['email']))
        self.assertRegex(mensagem['link'], '^' + cenario.ORIGEM + r'/aceitar/[A-Za-z0-9_-]{43}$')
        self.assertNotIn(mensagem['link'].rsplit('/', 1)[1], bruto.decode('utf-8'))
        for trecho in ('Dona Alfa', 'Redação Alfa', mensagem['link']):
            self.assertIn(trecho, mensagem['corpo'])
        self.assertEqual(self.publico('convite-consultar', {'token': mensagem['link'].rsplit('/', 1)[1]})[0], 200)

    def test_email_que_ja_tem_conta_em_outra_redacao_recebe_a_mesma_resposta(self):
        de_beta = self.email()
        _, token, _ = acesso.convidar(self.root, self.b, self.ids['dono_b'], de_beta, 'leitor', ['beta'])
        acesso.aceitar_convite(self.root, token, 'Pessoa Sentinela', SENHA)
        with correio.usar('simulado'):
            normal, _ = self.convidar()
            correio.limpar_caixa()
            status, corpo, bruto = self.post('dono', 'equipe-convidar', {'email': de_beta, 'papel': 'reporter', 'casos': ['alpha']})
        self.assertEqual(status, 200, bruto[:200])
        self.assertEqual(set(corpo), set(normal))
        self.assertEqual({k: v for k, v in corpo['convite'].items() if k not in ('id', 'email', 'criado_em', 'enviado_em', 'expira_em')},
                         {k: v for k, v in normal['convite'].items() if k not in ('id', 'email', 'criado_em', 'enviado_em', 'expira_em')})
        self.sem_sentinela(bruto)
        self.assertIn(corpo['convite']['id'], self.pendentes())  # listed, sent again and cancelled like any other
        mensagem, = correio.caixa()
        self.assertEqual((mensagem['tipo'], mensagem['para']), ('convite_sem_efeito', de_beta))
        self.assertNotIn('http', mensagem['corpo'])  # the person is told why; the message carries no link
        self.assertNotIn(cenario.REDACAO_B, mensagem['corpo'])
        recusa = self.publico('convite-aceitar', {'token': mensagem['link'].rsplit('/', 1)[1], 'nome': 'Pessoa', 'senha': SENHA})
        inexistente = self.publico('convite-aceitar', {'token': 'x' * 43, 'nome': 'Pessoa', 'senha': SENHA})
        self.assertEqual((recusa[0], recusa[3]), (inexistente[0], inexistente[3]))
        self.assertEqual(acesso.organizacao_da_conta(self.root, self.post('dono_b', 'equipe-listar', {})[1]['pessoas'][-1]['id']), self.b)
        self.assertEqual(self.post('dono', 'equipe-convite-cancelar', {'convite': corpo['convite']['id']})[1]['convite']['estado'], 'cancelado')

    def test_convidar_como_dono_pede_a_senha(self):
        dados = {'email': self.email(), 'papel': 'dono'}
        for senha, codigo in (({}, 'senha_necessaria'), ({'senha': ERRADA}, 'senha_atual_incorreta')):
            status, corpo, bruto = self.post('dono', 'equipe-convidar', {**dados, **senha})
            self.assertEqual((status, corpo.get('codigo')), (403, codigo), bruto[:200])
        self.assertNotIn(dados['email'], {c['email'] for c in self.pendentes().values()})
        status, corpo, bruto = self.post('dono', 'equipe-convidar', {**dados, 'senha': SENHA})
        self.assertEqual((status, corpo['convite']['papel']), (200, 'dono'), bruto[:200])
        self.assertNotIn(SENHA, bruto.decode('utf-8'))

    def test_recusas_do_convite_e_campos_fora_da_lista(self):
        existente = self.convidar()[0]['convite']
        for dados, status, codigo in (
                ({'email': existente['email'], 'papel': 'leitor'}, 400, 'convite_duplicado'),
                ({'email': 'edu.editor', 'papel': 'leitor'}, 400, 'erro'),
                ({'email': self.email(), 'papel': 'convidado'}, 400, 'erro'),
                ({'email': self.email(), 'papel': 'leitor', 'organizacao': self.b}, 400, 'erro'),
                ({'email': self.email(), 'papel': 'leitor', 'nome': 'Fulana'}, 400, 'erro')):
            resposta = self.post('dono', 'equipe-convidar', dados)
            self.assertEqual((resposta[0], resposta[1].get('codigo')), (status, codigo), dados)
            self.sem_sentinela(resposta[2])
        # A case of the other newsroom is the case that does not exist, byte for byte.
        email = self.email()
        de_beta = self.post('dono', 'equipe-convidar', {'email': email, 'papel': 'leitor', 'casos': ['beta']})
        inexistente = self.post('dono', 'equipe-convidar', {'email': email, 'papel': 'leitor', 'casos': ['nao_existe']})
        self.assertEqual((de_beta[0], de_beta[2]), (400, inexistente[2]))
        self.assertNotIn(email, {c['email'] for c in self.pendentes().values()})
        cedo = self.post('dono', 'equipe-convite-reenviar', {'convite': existente['id']})
        self.assertEqual((cedo[0], cedo[1].get('codigo')), (429, 'limite_de_convites'))
        with patch.object(acesso, 'CONVITES_PENDENTES', len(self.pendentes())):
            cheio = self.post('dono', 'equipe-convidar', {'email': self.email(), 'papel': 'leitor'})
        self.assertEqual((cheio[0], cheio[1].get('codigo')), (429, 'limite_de_convites'))

    def test_convite_de_outra_redacao_responde_como_inexistente(self):
        _, bruto = self.convidar('dono_b', casos=['beta'])
        de_beta = json.loads(bruto)['convite']['id']
        for operacao in ('equipe-convite-reenviar', 'equipe-convite-cancelar'):
            real = self.post('dono', operacao, {'convite': de_beta})
            falso = self.post('dono', operacao, {'convite': '0123456789abcdef'})
            self.assertEqual((real[0], real[2]), (falso[0], falso[2]))
            self.assertEqual((real[0], real[1]['erro']), (400, 'Convite não encontrado.'))
        self.assertIn(de_beta, self.pendentes('dono_b'))
        self.assertNotIn(de_beta, self.pendentes())

    def test_falha_de_envio_aparece_ao_dono_e_o_convite_fica_para_reenviar(self):
        with correio.usar('simulado'), patch.object(correio, 'enviar', side_effect=correio.FalhaDeEnvio('falhou')):
            status, corpo, bruto = self.post('dono', 'equipe-convidar', {'email': self.email(), 'papel': 'leitor'})
        self.assertEqual((status, corpo['convite']['envio']), (200, 'falha'), bruto[:200])
        self.assertNotIn('link', corpo)
        self.assertEqual(self.pendentes()[corpo['convite']['id']]['envio'], 'falha')

    def test_link_que_nao_cria_conta_tem_uma_resposta_so(self):
        corpo, _ = self.convidar()
        token = corpo['link'].rsplit('/', 1)[1]
        self.post('dono', 'equipe-convite-cancelar', {'convite': corpo['convite']['id']})
        respostas = {self.publico('convite-consultar', {'token': alvo})[3] for alvo in (token, 'x' * 43, '', None, 'curto')}
        self.assertEqual(len(respostas), 1)
        self.assertEqual(json.loads(respostas.pop())['codigo'], 'convite_invalido')
        self.assertEqual(self.publico('convite-consultar', {'token': token})[0], 400)
        sem_origem = self.pedir('POST', '/api/convite-consultar', json.dumps({'token': token}), {'Content-Type': 'application/json'})
        self.assertEqual(sem_origem[0], 403)


if __name__ == '__main__':
    unittest.main()
