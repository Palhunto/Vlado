"""Recuperação do acesso de outra pessoa e troca do próprio e-mail (contrato de contas, seções 5.3, 5.4, 5.5 e 8.2).

``equipe-recuperar`` tem sempre duas partes e pede sempre a senha de quem age: para quem não é dono, a segunda parte
é a própria pessoa, pelo link que só ela recebe; para um dono, um terceiro dono confirma
(``equipe-recuperar-confirmar``). No serviço hospedado o link nunca volta na resposta; na Mesa instalada
(``local-contas``), o dono recupera quem não é dono confirmando com a própria senha, e o link aparece para ele (P33).
``conta-email-trocar`` pede a senha e só troca quando o link mandado ao endereço NOVO é usado (``email-confirmar``).
No armazenamento e pelo servidor (modo ``piloto``, com o transporte ``simulado``). Sem modelo e sem rede.
"""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
from comum import escrever_json
import correio
from interface_pesquisa import Servidor
import test_acesso  # module import: its TestCases are not collected again here
from test_acesso import SENHA

ERRADA = 'senha-errada-de-teste'
NOVA = 'outra-senha-longa-2'
HOSPEDADO = {'com_envio': True, 'na_tela': False}
HOSPEDADO_SEM_ENVIO = {'com_envio': False, 'na_tela': False}
INSTALADA = {'com_envio': False, 'na_tela': True}


def com_email(root, redacao, dono, email, papel='reporter'):
    _, token, _ = acesso.convidar(root, redacao, dono, email, papel, [], senha=SENHA if papel == 'dono' else None)
    return acesso.aceitar_convite(root, token, 'Pessoa ' + email.split('@')[0], SENHA)[2]['id']


class RecuperacaoTest(test_acesso.DuasRedacoes):
    def setUp(self):
        super().setUp()
        self.pessoa_a = com_email(self.root, self.a, self.dono_a, 'pessoa@exemplo.test')
        self.dona2 = com_email(self.root, self.a, self.dono_a, 'dona2@exemplo.test', 'dono')
        self.dona3 = com_email(self.root, self.a, self.dono_a, 'dona3@exemplo.test', 'dono')

    def pedir(self, alvo, por=None, senha=SENHA, **contexto):
        return acesso.pedir_recuperacao(self.root, self.a, por or self.dono_a, alvo, senha, **(contexto or HOSPEDADO))

    def test_quem_nao_e_dono_recebe_o_link_e_nada_muda_ate_usar(self):
        sid = acesso.entrar(self.root, 'pessoa@exemplo.test', SENHA)[0]
        feito = self.pedir(self.pessoa_a)
        self.assertEqual((feito['estado'], feito['por_email'], feito['destinatario']['email']), ('enviada', True, 'pessoa@exemplo.test'))
        self.assertNotIn(feito['token'], self.bruto())
        self.assertIsNotNone(acesso.sessao(self.root, sid))  # the person is the second party: nothing changed yet
        self.assertEqual(acesso.entrar(self.root, 'pessoa@exemplo.test', SENHA)[2]['id'], self.pessoa_a)
        self.assertEqual(acesso.redefinir_senha(self.root, feito['token'], NOVA)['id'], self.pessoa_a)
        self.assertIsNone(acesso.sessao(self.root, sid))
        self.assertEqual(acesso.entrar(self.root, 'pessoa@exemplo.test', NOVA)[2]['id'], self.pessoa_a)
        with self.assertRaises(acesso.LinkInvalido):
            acesso.redefinir_senha(self.root, feito['token'], 'mais-uma-senha-longa-3')
        self.assertLessEqual({'recuperacao_pedida', 'senha_redefinida'}, set(self.tipos()))
        with self.assertRaisesRegex(ValueError, 'alguns minutos'):  # not a way to fill the person's mailbox
            self.pedir(self.pessoa_a)
            self.pedir(self.pessoa_a)

    def test_pede_sempre_a_senha_e_confere_a_conta_antes(self):
        for senha, erro in ((None, acesso.SenhaNecessaria), (ERRADA, acesso.SenhaIncorreta)):
            with self.assertRaises(erro):
                self.pedir(self.pessoa_a, senha=senha)
            for alvo in (self.rep_b, '0123456789abcdef', None):  # another newsroom's is the one that does not exist
                with self.assertRaisesRegex(ValueError, acesso.CONTA_INEXISTENTE):
                    self.pedir(alvo, senha=senha)
        with self.assertRaisesRegex(ValueError, 'própria senha'):
            self.pedir(self.dono_a)
        acesso.desativar(self.root, self.pessoa_a, por='cli')
        with self.assertRaisesRegex(ValueError, 'Reative'):
            self.pedir(self.pessoa_a)
        self.assertEqual(self.linhas('SELECT 1 FROM links'), [])
        self.assertEqual(len(self.linhas("SELECT 1 FROM tentativas WHERE chave LIKE '#senha|%'")), 1)  # only the wrong ones counted

    def test_recuperar_um_dono_espera_um_terceiro_dono(self):
        feito = self.pedir(self.dona2)
        self.assertEqual(feito['estado'], 'aguardando_confirmacao')
        pedido = feito['recuperacao']
        self.assertEqual((pedido['conta'], pedido['pedida_por'], pedido['pedida_por_nome'], pedido['estado']),
                         (self.dona2, self.dono_a, 'Dona A', 'pendente'))
        self.assertNotIn('token', feito)
        self.assertEqual(self.linhas('SELECT 1 FROM links'), [])  # no link exists before the second confirmation
        self.assertEqual([r['id'] for r in acesso.equipe(self.root, self.a)['recuperacoes']], [pedido['id']])
        self.assertEqual(acesso.equipe(self.root, self.b)['recuperacoes'], [])
        with self.assertRaisesRegex(ValueError, 'à espera'):
            self.pedir(self.dona2, por=self.dona3)
        confirmar = lambda por, senha=SENHA, rid=pedido['id'], redacao=None: acesso.confirmar_recuperacao(  # noqa: E731
            self.root, redacao or self.a, por, rid, senha, **HOSPEDADO)
        for quem in (self.dono_a, self.dona2):  # neither who asked nor the person
            with self.assertRaisesRegex(ValueError, 'outro dono'):
                confirmar(quem)
        for senha, erro in ((None, acesso.SenhaNecessaria), (ERRADA, acesso.SenhaIncorreta)):
            with self.assertRaises(erro):
                confirmar(self.dona3, senha)
        for rid, redacao, quem in (('0123456789abcdef', self.a, self.dona3), (pedido['id'], self.b, self.dono_b), (None, self.a, self.dona3)):
            with self.assertRaisesRegex(ValueError, acesso.RECUPERACAO_INEXISTENTE):
                confirmar(quem, rid=rid, redacao=redacao)
        confirmado = confirmar(self.dona3)
        self.assertEqual((confirmado['estado'], confirmado['por_email'], confirmado['destinatario']['email']),
                         ('enviada', True, 'dona2@exemplo.test'))
        self.assertEqual(acesso.equipe(self.root, self.a)['recuperacoes'], [])
        with self.assertRaisesRegex(ValueError, acesso.RECUPERACAO_INEXISTENTE):
            confirmar(self.dona3)  # once
        self.assertEqual(acesso.redefinir_senha(self.root, confirmado['token'], NOVA)['id'], self.dona2)
        self.assertLessEqual({'recuperacao_pedida', 'recuperacao_confirmada'}, set(self.tipos()))

    def test_sem_terceiro_dono_ou_sem_como_entregar_o_link_e_pelo_operador(self):
        acesso.desativar(self.root, self.dona3, por='cli')
        with self.assertRaises(acesso.SoPeloOperador) as recusa:
            self.pedir(self.dona2)  # two donos: nobody to be the third
        self.assertEqual((recusa.exception.status, recusa.exception.codigo), (400, 'recuperacao_pelo_operador'))
        acesso.reativar(self.root, self.dona3, por='cli')
        for alvo in (self.pessoa_a, self.dona2, self.rep_a):  # the hosted service without delivery: never a link
            with self.assertRaises(acesso.SoPeloOperador):
                self.pedir(alvo, **HOSPEDADO_SEM_ENVIO)
        with self.assertRaises(acesso.SoPeloOperador):
            self.pedir(self.rep_a)  # an account that came without e-mail: no address to send the link to
        self.assertEqual(self.linhas('SELECT 1 FROM links') + self.linhas('SELECT 1 FROM recuperacoes'), [])

    def test_pedido_que_ninguem_confirma_vence_em_um_dia_e_cai_se_quem_pediu_deixa_de_ser_dono(self):
        pedido = self.pedir(self.dona2)['recuperacao']
        with self.depois(hours=acesso.RECUPERACAO_HORAS, minutes=1):
            with self.assertRaisesRegex(ValueError, acesso.RECUPERACAO_INEXISTENTE):
                acesso.confirmar_recuperacao(self.root, self.a, self.dona3, pedido['id'], SENHA, **HOSPEDADO)
            self.assertEqual(acesso.equipe(self.root, self.a)['recuperacoes'], [])
            self.assertEqual(acesso.manutencao(self.root)['recuperacoes_vencidas'], 1)
        outro = self.pedir(self.dona2, por=self.dona3)['recuperacao']
        acesso.mudar_papel(self.root, self.dona3, 'editor', self.dono_a, self.a, SENHA)  # who asked is no longer a dono
        quarta = com_email(self.root, self.a, self.dono_a, 'dona4@exemplo.test', 'dono')
        with self.assertRaisesRegex(ValueError, acesso.RECUPERACAO_INEXISTENTE):
            acesso.confirmar_recuperacao(self.root, self.a, quarta, outro['id'], SENHA, **HOSPEDADO)

    def test_na_mesa_instalada_o_dono_recupera_quem_nao_e_dono_com_a_propria_senha(self):
        # Decision P33: one machine, one newsroom, no e-mail. The link is handed to who asked.
        for senha, erro in ((None, acesso.SenhaNecessaria), (ERRADA, acesso.SenhaIncorreta)):
            with self.assertRaises(erro):
                self.pedir(self.rep_a, senha=senha, **INSTALADA)
        feito = self.pedir(self.rep_a, **INSTALADA)
        self.assertEqual((feito['estado'], feito['por_email'], feito['destinatario']['id']), ('confirmada', False, self.rep_a))
        self.assertEqual(acesso.entrar(self.root, 'rep.a', SENHA)[2]['id'], self.rep_a)  # nothing changed until it is used
        acesso.redefinir_senha(self.root, feito['token'], NOVA)
        self.assertEqual(acesso.entrar(self.root, 'rep.a', NOVA)[2]['id'], self.rep_a)
        # A dono is still recovered by two other donos, there too; with one dono only, by the operator.
        pedido = self.pedir(self.dona2, **INSTALADA)
        self.assertEqual(pedido['estado'], 'aguardando_confirmacao')
        confirmado = acesso.confirmar_recuperacao(self.root, self.a, self.dona3, pedido['recuperacao']['id'], SENHA, **INSTALADA)
        self.assertEqual((confirmado['estado'], confirmado['por_email']), ('confirmada', False))
        with self.assertRaises(acesso.SoPeloOperador):
            acesso.pedir_recuperacao(self.root, self.b, self.dono_b, self.rep_b, SENHA, **HOSPEDADO_SEM_ENVIO)
        self.assertEqual(acesso.pedir_recuperacao(self.root, self.b, self.dono_b, self.rep_b, SENHA, **INSTALADA)['estado'], 'confirmada')


class TrocaDeEmailTest(test_acesso.DuasRedacoes):
    def setUp(self):
        super().setUp()
        self.pessoa_a = com_email(self.root, self.a, self.dono_a, 'antigo@exemplo.test')
        self.de_b = com_email(self.root, self.b, self.dono_b, 'ocupado@exemplo.test')

    def test_a_troca_so_acontece_quando_o_link_do_endereco_novo_e_usado(self):
        for senha, erro in ((None, acesso.SenhaNecessaria), (ERRADA, acesso.SenhaIncorreta)):
            with self.assertRaises(erro):
                acesso.pedir_troca_de_email(self.root, self.pessoa_a, 'novo@exemplo.test', senha)
        for email in ('', 'sem-arroba', None, 'antigo@exemplo.test'):
            with self.assertRaises(ValueError):
                acesso.pedir_troca_de_email(self.root, self.pessoa_a, email, SENHA)
        pedido = acesso.pedir_troca_de_email(self.root, self.pessoa_a, ' Novo@Exemplo.Test ', SENHA)
        self.assertEqual((pedido['novo'], pedido['antigo'], pedido['enviar']), ('novo@exemplo.test', 'antigo@exemplo.test', True))
        self.assertNotIn(pedido['token'], self.bruto())
        self.assertEqual(self.registro(self.pessoa_a)['email'], 'antigo@exemplo.test')  # asking changes nothing
        with self.assertRaisesRegex(ValueError, 'há pouco'):
            acesso.pedir_troca_de_email(self.root, self.pessoa_a, 'terceiro@exemplo.test', SENHA)
        feito = acesso.confirmar_email(self.root, pedido['token'])
        self.assertEqual((feito['conta'], feito['novo'], feito['antigo']), (self.pessoa_a, 'novo@exemplo.test', 'antigo@exemplo.test'))
        self.assertEqual(acesso.entrar(self.root, 'novo@exemplo.test', SENHA)[2]['id'], self.pessoa_a)
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'antigo@exemplo.test', SENHA)  # the old address no longer signs in
        with self.assertRaises(acesso.LinkInvalido) as recusa:
            acesso.confirmar_email(self.root, pedido['token'])  # once
        self.assertEqual(str(recusa.exception), acesso.LINK_DE_EMAIL_INVALIDO)
        self.assertLessEqual({'email_troca_pedida', 'email_trocado'}, set(self.tipos()))

    def test_endereco_que_ja_tem_conta_recebe_a_mesma_resposta_e_nao_troca_nada(self):
        livre = acesso.pedir_troca_de_email(self.root, self.pessoa_a, 'livre@exemplo.test', SENHA)
        with self.depois(minutes=acesso.REDEFINICAO_INTERVALO_MINUTOS + 1):
            ocupado = acesso.pedir_troca_de_email(self.root, self.pessoa_a, 'ocupado@exemplo.test', SENHA)
            self.assertEqual(set(ocupado), set(livre))
            self.assertEqual((livre['enviar'], ocupado['enviar']), (True, False))  # nothing is sent to an address in use
            self.assertEqual(len(self.linhas("SELECT 1 FROM links WHERE tipo = 'email'")), 1)  # the request is kept, without effect
            with self.assertRaises(acesso.LinkInvalido) as recusa:
                acesso.confirmar_email(self.root, ocupado['token'])
            self.assertEqual((str(recusa.exception), recusa.exception.motivo), (acesso.LINK_DE_EMAIL_INVALIDO, 'email_em_uso'))
            with self.assertRaises(acesso.LinkInvalido):
                acesso.confirmar_email(self.root, livre['token'])  # the link before died with the new request
        self.assertEqual((self.registro(self.pessoa_a)['email'], self.registro(self.de_b)['email']),
                         ('antigo@exemplo.test', 'ocupado@exemplo.test'))

    def test_conta_que_veio_sem_email_ganha_um_e_o_link_vence_em_uma_hora(self):
        pedido = acesso.pedir_troca_de_email(self.root, self.rep_a, 'rep.a@exemplo.test', SENHA)
        self.assertIsNone(pedido['antigo'])
        with self.depois(minutes=acesso.REDEFINICAO_MINUTOS, seconds=1):
            with self.assertRaises(acesso.LinkInvalido):
                acesso.confirmar_email(self.root, pedido['token'])
            pedido = acesso.pedir_troca_de_email(self.root, self.rep_a, 'rep.a@exemplo.test', SENHA)
            acesso.confirmar_email(self.root, pedido['token'])
        self.assertEqual(acesso.entrar(self.root, 'rep.a@exemplo.test', SENHA)[2]['id'], self.rep_a)
        self.assertEqual(acesso.entrar(self.root, 'rep.a', SENHA)[2]['id'], self.rep_a)  # the old login goes on


class ServidorTest(cenario.DuasRedacoes):
    numero = 0

    def setUp(self):
        acesso.limpar_limites()
        correio.limpar_caixa()
        type(self).numero += 1
        self.email = f'recuperada{self.numero}@exemplo.test'
        self.pessoa = com_email(self.root, self.a, self.ids['dono'], self.email)

    def publico(self, operacao, dados):
        status, cabecalhos, corpo = self.pedir('POST', '/api/' + operacao, json.dumps(dados),
                                               {'Content-Type': 'application/json', 'Origin': cenario.ORIGEM})
        return status, json.loads(corpo or b'{}'), cabecalhos, corpo

    def entrar(self, email, senha=SENHA):
        status, corpo, cabecalhos, _ = self.publico('entrar', {'login': email, 'senha': senha})
        return (cabecalhos['Set-Cookie'].split(';')[0], corpo['csrf']) if status == 200 else None

    def test_no_servico_hospedado_o_link_vai_so_a_pessoa_e_nunca_volta_na_resposta(self):
        with correio.usar('simulado'):
            for senha, codigo in (({}, 'senha_necessaria'), ({'senha': ERRADA}, 'senha_atual_incorreta')):
                status, corpo, _ = self.post('dono', 'equipe-recuperar', {'conta': self.pessoa, **senha})
                self.assertEqual((status, corpo.get('codigo')), (403, codigo))
        self.assertEqual(correio.caixa(), [])
        # Without real delivery the hosted service has nobody to hand the link to, with or without the password.
        sem_envio = self.post('dono', 'equipe-recuperar', {'conta': self.pessoa, 'senha': SENHA})
        self.assertEqual((sem_envio[0], sem_envio[1].get('codigo')), (400, 'recuperacao_pelo_operador'))
        self.assertNotIn('link', sem_envio[1])
        with correio.usar('simulado'):
            status, corpo, bruto = self.post('dono', 'equipe-recuperar', {'conta': self.pessoa, 'senha': SENHA})
        self.assertEqual((status, corpo), (200, {'estado': 'enviada', 'conta': self.pessoa, 'envio': 'enviado'}), bruto[:200])
        mensagem, = correio.caixa()
        self.assertEqual((mensagem['tipo'], mensagem['para']), ('recuperacao', self.email))
        token = mensagem['link'].rsplit('/', 1)[1]
        self.assertRegex(mensagem['link'], '^' + cenario.ORIGEM + r'/redefinir/[A-Za-z0-9_-]{43}$')
        self.assertNotIn(token, bruto.decode('utf-8'))
        self.assertIsNotNone(self.entrar(self.email))  # nothing changed until the person uses the link
        self.assertEqual(self.publico('senha-redefinir', {'token': token, 'senha': NOVA})[0], 200)
        self.assertIsNone(self.entrar(self.email))
        self.assertIsNotNone(self.entrar(self.email, NOVA))

    def test_conta_de_outra_redacao_responde_como_inexistente_e_outros_papeis_nao_recuperam(self):
        with correio.usar('simulado'):
            for senha in ({}, {'senha': ERRADA}, {'senha': SENHA}):
                real = self.post('dono', 'equipe-recuperar', {'conta': self.ids['reporter_b'], **senha})
                falso = self.post('dono', 'equipe-recuperar', {'conta': '0123456789abcdef', **senha})
                self.assertEqual((real[0], real[2]), (400, falso[2]))
                self.sem_sentinela(real[2])
            for papel in ('editor', 'reporter', 'leitor', 'convidado'):
                for operacao, dados in (('equipe-recuperar', {'conta': self.pessoa, 'senha': SENHA}),
                                        ('equipe-recuperar-confirmar', {'recuperacao': 'x', 'senha': SENHA})):
                    self.assertEqual(self.post(papel, operacao, dados)[0], 403, (papel, operacao))
            campos = self.post('dono', 'equipe-recuperar', {'conta': self.pessoa, 'senha': SENHA, 'email': 'outro@exemplo.test'})
        self.assertEqual((campos[0], campos[1]['erro']), (400, 'Campos inválidos no pedido de equipe.'))  # never another's e-mail
        self.assertEqual(correio.caixa(), [])

    def test_recuperar_um_dono_passa_por_um_terceiro_dono(self):
        alvo = com_email(self.root, self.a, self.ids['dono'], f'dona.alvo{self.numero}@exemplo.test', 'dono')
        terceira = com_email(self.root, self.a, self.ids['dono'], f'dona.terceira{self.numero}@exemplo.test', 'dono')
        da_terceira = self.entrar(f'dona.terceira{self.numero}@exemplo.test')
        with correio.usar('simulado'):
            status, corpo, _ = self.post('dono', 'equipe-recuperar', {'conta': alvo, 'senha': SENHA})
            self.assertEqual((status, corpo['estado'], corpo['recuperacao']['conta']), (200, 'aguardando_confirmacao', alvo))
            pedido = corpo['recuperacao']['id']
            self.assertEqual(correio.caixa(), [])  # no link before the second confirmation
            self.assertIn(pedido, [r['id'] for r in self.post(da_terceira, 'equipe-listar', {})[1]['recuperacoes']])
            self.assertEqual(self.post('dono_b', 'equipe-listar', {})[1]['recuperacoes'], [])
            mesma = self.post('dono', 'equipe-recuperar-confirmar', {'recuperacao': pedido, 'senha': SENHA})
            self.assertEqual(mesma[0], 400)  # who asked does not confirm
            de_fora = self.post('dono_b', 'equipe-recuperar-confirmar', {'recuperacao': pedido, 'senha': SENHA})
            inexistente = self.post('dono_b', 'equipe-recuperar-confirmar', {'recuperacao': '0123456789abcdef', 'senha': SENHA})
            self.assertEqual((de_fora[0], de_fora[2]), (400, inexistente[2]))
            sem_senha = self.post(da_terceira, 'equipe-recuperar-confirmar', {'recuperacao': pedido})
            self.assertEqual((sem_senha[0], sem_senha[1].get('codigo')), (403, 'senha_necessaria'))
            status, corpo, bruto = self.post(da_terceira, 'equipe-recuperar-confirmar', {'recuperacao': pedido, 'senha': SENHA})
        self.assertEqual((status, corpo), (200, {'estado': 'enviada', 'conta': alvo, 'envio': 'enviado'}), bruto[:200])
        mensagem, = correio.caixa()
        self.assertEqual((mensagem['tipo'], mensagem['para']), ('recuperacao', f'dona.alvo{self.numero}@exemplo.test'))
        self.assertNotIn(mensagem['link'].rsplit('/', 1)[1], bruto.decode('utf-8'))
        for conta in (alvo, terceira):  # leave the scenario with the donos it had
            self.assertEqual(self.post('dono', 'equipe-remover', {'conta': conta, 'senha': SENHA})[0], 200)

    def test_a_recuperacao_antiga_saiu_e_nao_ha_caminho_por_fora_da_dupla_confirmacao(self):
        # The old `contas-recuperar` let a dono recover ANOTHER dono, or a reader, with the own password alone: 200, a
        # link in the answer and the other person's session gone. It left with the invitation (P30): 404, like the
        # other `contas-*`, with or without the password, and nothing happens to anybody.
        email_da_outra = f'outra.dona{self.numero}@exemplo.test'
        outra = com_email(self.root, self.a, self.ids['dono'], email_da_outra, 'dono')
        da_outra = self.entrar(email_da_outra)
        inexistente = self.post('dono', 'operacao-que-nunca-existiu', {})
        for alvo in (outra, self.ids['leitor']):
            for senha in ({}, {'senha': SENHA}):
                for corpo in ({'id': alvo, **senha}, {'conta': alvo, **senha}):
                    resposta = self.post('dono', 'contas-recuperar', corpo)
                    self.assertEqual((resposta[0], resposta[2]), (404, inexistente[2]))
                    self.assertNotIn(b'/ativar/', resposta[2])
        for operacao in ('contas-listar', 'contas-criar', 'contas-atualizar', 'contas-desativar', 'contas-reativar'):
            self.assertEqual(self.post('dono', operacao, {'id': outra, 'papel': 'leitor', 'senha': SENHA})[0], 404, operacao)
        self.assertEqual(self.post(da_outra, 'codex-status', {})[0], 200)  # the other dono's session goes on
        self.assertEqual(self.post('leitor', 'codex-status', {})[0], 200)
        self.assertIsNotNone(self.entrar(email_da_outra))  # and her password is the same
        # The way that is left: another dono only with a third dono, and never a link in the answer.
        with correio.usar('simulado'):
            pela_equipe = self.post('dono', 'equipe-recuperar', {'conta': outra, 'senha': SENHA})
        self.assertEqual((pela_equipe[0], pela_equipe[1].get('codigo')), (400, 'recuperacao_pelo_operador'))  # two donos: no third
        self.assertNotIn('link', pela_equipe[1])
        self.assertEqual(self.post(da_outra, 'codex-status', {})[0], 200)
        self.assertEqual(correio.caixa(), [])
        self.assertEqual(self.post('dono', 'equipe-remover', {'conta': outra, 'senha': SENHA})[0], 200)  # the scenario as it was

    def test_trocar_o_proprio_email_pelo_servidor(self):
        sessao = self.entrar(self.email)
        novo = f'nova.caixa{self.numero}@exemplo.test'
        sem_senha = self.post(sessao, 'conta-email-trocar', {'email': novo})
        self.assertEqual((sem_senha[0], sem_senha[1].get('codigo')), (403, 'senha_necessaria'))
        self.assertEqual(self.post(sessao, 'conta-email-trocar', {'email': novo, 'senha': SENHA, 'conta': self.ids['dono']})[0], 400)
        with correio.usar('simulado'):
            status, corpo, bruto = self.post(sessao, 'conta-email-trocar', {'email': novo, 'senha': SENHA})
            correio.aguardar()
        self.assertEqual((status, corpo), (200, {'estado': 'confirmacao_enviada'}), bruto[:200])  # no link in the answer
        mensagens = {m['tipo']: m for m in correio.caixa()}
        self.assertEqual({t: m['para'] for t, m in mensagens.items()}, {'email_novo': novo, 'email_aviso': self.email})
        self.assertNotIn('http', mensagens['email_aviso']['corpo'])  # the old address is told, with nothing to click
        token = mensagens['email_novo']['link'].rsplit('/', 1)[1]
        self.assertRegex(mensagens['email_novo']['link'], '^' + cenario.ORIGEM + r'/confirmar-email/[A-Za-z0-9_-]{43}$')
        self.assertEqual(self.post(sessao, 'conta-ver', {})[1]['conta']['email'], self.email)
        self.assertEqual(self.pedir('GET', '/confirmar-email/' + token)[2], self.pedir('GET', '/entrar')[2])
        correio.limpar_caixa()
        with correio.usar('simulado'):
            self.assertEqual(self.publico('email-confirmar', {'token': token, 'email': 'outro@exemplo.test'})[0], 400)
            status, corpo, _, _ = self.publico('email-confirmar', {'token': token})
            correio.aguardar()
        self.assertEqual((status, corpo), (200, {'estado': 'email_confirmado'}))
        self.assertEqual([(m['tipo'], m['para']) for m in correio.caixa()], [('email_trocado', self.email)])
        self.assertEqual(self.post(sessao, 'conta-ver', {})[1]['conta']['email'], novo)  # the session goes on
        self.assertIsNone(self.entrar(self.email))
        self.assertIsNotNone(self.entrar(novo))
        usado = self.publico('email-confirmar', {'token': token})
        inexistente = self.publico('email-confirmar', {'token': 'x' * 43})
        self.assertEqual((usado[0], usado[1]['codigo'], usado[3]), (400, 'link_invalido', inexistente[3]))

    def test_endereco_de_outra_redacao_tem_a_mesma_resposta_e_nenhuma_mensagem(self):
        sessao = self.entrar(self.email)
        de_beta = f'sentinela{self.numero}@exemplo.test'
        com_email(self.root, self.b, self.ids['dono_b'], de_beta)
        segunda = com_email(self.root, self.a, self.ids['dono'], f'segunda{self.numero}@exemplo.test')
        da_segunda = self.entrar(f'segunda{self.numero}@exemplo.test')
        with correio.usar('simulado'):
            ocupado = self.post(sessao, 'conta-email-trocar', {'email': de_beta, 'senha': SENHA})
            livre = self.post(da_segunda, 'conta-email-trocar', {'email': f'livre{self.numero}@exemplo.test', 'senha': SENHA})
            correio.aguardar()
        self.assertEqual((ocupado[0], ocupado[2]), (200, livre[2]))
        self.assertNotIn(de_beta, [m['para'] for m in correio.caixa()])  # nothing goes to the address in use
        self.assertEqual(acesso.organizacao_da_conta(self.root, segunda), self.a)
        # With the link on the screen (no real delivery) the link goes back to who asked, in both cases.
        acesso.limpar_limites()
        with test_acesso.patch('acesso.agora', return_value=acesso.agora() + test_acesso.timedelta(minutes=6)):
            na_tela = self.post(da_segunda, 'conta-email-trocar', {'email': f'livre2.{self.numero}@exemplo.test', 'senha': SENHA})
        self.assertEqual((na_tela[0], set(na_tela[1])), (200, {'estado', 'link'}))


class MesaInstaladaTest(unittest.TestCase):
    """``local-contas``: one machine, one newsroom, the link on the screen (decision P33)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        escrever_json(self.root / 'configuracao.json', {'provedor': 'anthropic', 'modelo_preferido': None, 'max_tokens_saida': 4096})
        env = test_acesso.patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': '', 'VLADO_CORREIO': ''})
        env.start()
        self.addCleanup(env.stop)
        test_acesso.hasher_rapido(self)
        acesso.limpar_limites()
        self.dono = acesso.criar_primeiro_admin(self.root, 'Editora', 'editora', SENHA)['id']
        conta, token = acesso.criar_conta(self.root, 'Ana Silva', 'ana', papel='leitor', por='cli')
        acesso.ativar(self.root, token, SENHA)
        self.ana = conta['id']
        self.server = Servidor(('127.0.0.1', 0), self.root, modo='local-contas')
        fio = threading.Thread(target=self.server.serve_forever, daemon=True)
        fio.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), fio.join(3)))
        self.origem = f'http://127.0.0.1:{self.server.server_port}'
        status, cabecalhos, corpo = self.pedir('entrar', {'login': 'editora', 'senha': SENHA})
        self.assertEqual(status, 200, corpo)
        self.sessao = {'Cookie': cabecalhos['Set-Cookie'].split(';')[0], 'X-Session-Token': json.loads(corpo)['csrf']}

    def pedir(self, operacao, dados, cabecalhos=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        try:
            con.request('POST', '/api/' + operacao, json.dumps(dados), {
                'Host': f'127.0.0.1:{self.server.server_port}', 'Content-Type': 'application/json', 'Origin': self.origem,
                **(cabecalhos or {})})
            resposta = con.getresponse()
            return resposta.status, dict(resposta.getheaders()), resposta.read()
        finally:
            con.close()

    def test_o_dono_unico_recupera_quem_nao_e_dono_com_a_propria_senha_e_ve_o_link(self):
        antiga = self.pedir('contas-recuperar', {'id': self.ana, 'senha': SENHA}, self.sessao)  # gone here too
        self.assertEqual((antiga[0], b'/ativar/' in antiga[2]), (404, False))
        for senha, codigo in (({}, 'senha_necessaria'), ({'senha': ERRADA}, 'senha_atual_incorreta')):
            status, _, corpo = self.pedir('equipe-recuperar', {'conta': self.ana, **senha}, self.sessao)
            self.assertEqual((status, json.loads(corpo).get('codigo')), (403, codigo))
        status, _, corpo = self.pedir('equipe-recuperar', {'conta': self.ana, 'senha': SENHA}, self.sessao)
        resposta = json.loads(corpo)
        self.assertEqual((status, resposta['estado'], resposta['conta']), (200, 'confirmada', self.ana), corpo[:200])
        self.assertRegex(resposta['link'], '^' + self.origem + r'/redefinir/[A-Za-z0-9_-]{43}$')
        self.assertEqual(self.pedir('entrar', {'login': 'ana', 'senha': SENHA})[0], 200)  # nothing changed until it is used
        acesso.limpar_limites()
        token = resposta['link'].rsplit('/', 1)[1]
        self.assertEqual(self.pedir('senha-redefinir', {'token': token, 'senha': NOVA})[0], 200)
        self.assertEqual(self.pedir('entrar', {'login': 'ana', 'senha': SENHA})[0], 401)
        self.assertEqual(self.pedir('entrar', {'login': 'ana', 'senha': NOVA})[0], 200)
        esqueci = self.pedir('senha-esqueci', {'email': 'ana@exemplo.test'})  # no real delivery here: off
        self.assertEqual((esqueci[0], json.loads(esqueci[2])['codigo']), (400, 'transporte_indisponivel'))


if __name__ == '__main__':
    unittest.main()
