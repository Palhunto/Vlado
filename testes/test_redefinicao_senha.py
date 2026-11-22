"""Redefinição de senha por e-mail (``senha-esqueci`` e ``senha-redefinir``; contrato de contas, seções 5.3, 8.1 e 8.2).

A pessoa digita o e-mail e recebe sempre a mesma resposta, exista a conta ou não. O link vale uma hora e uma vez;
usá-lo troca a senha, encerra as sessões e avisa a pessoa. Sem envio de verdade (transporte ``tela``) a operação
fica desligada: não há a quem mostrar o link. No armazenamento e pelo servidor (duas redações em modo ``piloto``,
com o transporte ``simulado``, de onde o teste lê o link). Sem modelo e sem rede.
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

NOVA = 'outra-senha-longa-2'
EMAIL = 'pessoa@exemplo.test'


def conta_com_email(root, redacao, dono, email=EMAIL, papel='reporter', casos=()):
    """An account born of an invitation: the only kind that has an e-mail."""
    _, token, _ = acesso.convidar(root, redacao, dono, email, papel, list(casos))
    return acesso.aceitar_convite(root, token, 'Pessoa Com E-mail', SENHA)


class ArmazenamentoTest(test_acesso.DuasRedacoes):
    def setUp(self):
        super().setUp()
        self.sid, _, self.conta = conta_com_email(self.root, self.a, self.dono_a)

    def test_pedido_guarda_so_o_hash_do_link_e_o_link_troca_a_senha_uma_vez(self):
        token, quem = acesso.pedir_redefinicao(self.root, ' Pessoa@Exemplo.Test ')
        self.assertEqual(quem, {'id': self.conta['id'], 'email': EMAIL, 'nome': 'Pessoa Com E-mail', 'idioma': 'pt'})
        self.assertNotIn(token, self.bruto())
        self.assertEqual(acesso.sessao(self.root, self.sid)['conta'], self.conta['id'])  # asking changes nothing
        self.assertEqual(acesso.entrar(self.root, EMAIL, SENHA)[2]['id'], self.conta['id'])
        with self.assertRaisesRegex(ValueError, '12 a 256'):
            acesso.redefinir_senha(self.root, token, 'curta')
        self.assertEqual(acesso.redefinir_senha(self.root, token, NOVA)['email'], EMAIL)
        self.assertIsNone(acesso.sessao(self.root, self.sid))  # every session of the account ended
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, EMAIL, SENHA)
        self.assertEqual(acesso.entrar(self.root, EMAIL, NOVA)[2]['id'], self.conta['id'])
        with self.assertRaises(acesso.LinkInvalido):
            acesso.redefinir_senha(self.root, token, 'mais-uma-senha-longa-3')  # the link works once
        self.assertEqual(self.linhas('SELECT 1 FROM links'), [])
        self.assertLessEqual({'redefinicao_pedida', 'senha_redefinida'}, set(self.tipos()))
        for segredo in (token, NOVA):
            self.assertNotIn(segredo, self.bruto())

    def test_email_sem_conta_conta_sem_senha_desativada_ou_de_redacao_suspensa_nao_recebem_link(self):
        self.assertIsNone(acesso.pedir_redefinicao(self.root, 'ninguem@exemplo.test'))
        for invalido in ('', None, 'sem-arroba', 'dona.a', ['x'], 'a@b'):
            self.assertIsNone(acesso.pedir_redefinicao(self.root, invalido))
        acesso.desativar(self.root, self.conta['id'], por='cli')
        self.assertIsNone(acesso.pedir_redefinicao(self.root, EMAIL))
        acesso.reativar(self.root, self.conta['id'], por='cli')
        acesso.definir_situacao_redacao(self.root, self.a, 'suspensa')
        with self.depois(minutes=acesso.REDEFINICAO_INTERVALO_MINUTOS + 1):
            self.assertIsNone(acesso.pedir_redefinicao(self.root, EMAIL))
        self.assertEqual(self.linhas('SELECT 1 FROM links'), [])

    def test_o_armazenamento_e_escrito_do_mesmo_jeito_com_conta_e_sem_conta(self):
        # When a reset was last asked for the address is kept in both cases: neither the answer nor its time tells.
        acesso.pedir_redefinicao(self.root, EMAIL)
        acesso.pedir_redefinicao(self.root, 'ninguem@exemplo.test')
        chaves = {l['chave'] for l in self.linhas("SELECT chave FROM tentativas WHERE chave LIKE '#esqueci|%'")}
        self.assertEqual(chaves, {acesso.CHAVE_ESQUECI + EMAIL, acesso.CHAVE_ESQUECI + 'ninguem@exemplo.test'})
        self.assertEqual(acesso.entrar(self.root, EMAIL, SENHA)[2]['id'], self.conta['id'])  # and it is not a sign-in counter

    def test_um_endereco_recebe_no_maximo_uma_mensagem_a_cada_cinco_minutos_e_o_link_novo_mata_o_anterior(self):
        primeiro, _ = acesso.pedir_redefinicao(self.root, EMAIL)
        self.assertIsNone(acesso.pedir_redefinicao(self.root, EMAIL))  # asked a moment ago: nothing new is sent
        with self.depois(minutes=acesso.REDEFINICAO_INTERVALO_MINUTOS + 1):
            segundo, _ = acesso.pedir_redefinicao(self.root, EMAIL)
            with self.assertRaises(acesso.LinkInvalido):
                acesso.redefinir_senha(self.root, primeiro, NOVA)
            self.assertEqual(acesso.redefinir_senha(self.root, segundo, NOVA)['id'], self.conta['id'])

    def test_link_vence_em_uma_hora_e_morre_com_o_que_encerra_as_sessoes(self):
        token, _ = acesso.pedir_redefinicao(self.root, EMAIL)
        with self.depois(minutes=acesso.REDEFINICAO_MINUTOS, seconds=1):
            with self.assertRaises(acesso.LinkInvalido) as recusa:
                acesso.redefinir_senha(self.root, token, NOVA)
            self.assertEqual((str(recusa.exception), recusa.exception.motivo), (acesso.LINK_INVALIDO, 'link_expirado'))
        for encerra in (lambda: acesso.trocar_senha(self.root, self.conta['id'], SENHA, 'senha-do-meio-longa-4'),
                        lambda: acesso.desativar(self.root, self.conta['id'], por='cli'),
                        lambda: acesso.remover(self.root, self.conta['id'], self.dono_a, self.a, SENHA)):
            with self.depois(minutes=acesso.REDEFINICAO_INTERVALO_MINUTOS + 1):
                pedido = acesso.pedir_redefinicao(self.root, EMAIL)
            if pedido is None:  # the account is no longer active: no link to kill
                continue
            encerra()
            with self.assertRaises(acesso.LinkInvalido):
                acesso.redefinir_senha(self.root, pedido[0], NOVA)
        for token in ('x' * 43, '', None, 5):
            with self.assertRaises(acesso.LinkInvalido):
                acesso.redefinir_senha(self.root, token, NOVA)

    def test_o_link_de_uma_conta_nao_mexe_em_outra(self):
        _, _, outra = conta_com_email(self.root, self.b, self.dono_b, 'outra@exemplo.test')
        token, _ = acesso.pedir_redefinicao(self.root, EMAIL)
        acesso.redefinir_senha(self.root, token, NOVA)
        self.assertEqual(acesso.entrar(self.root, 'outra@exemplo.test', SENHA)[2]['id'], outra['id'])
        self.assertEqual(acesso.entrar(self.root, 'dona.a', SENHA)[2]['id'], self.dono_a)


class ServidorTest(cenario.DuasRedacoes):
    numero = 0

    def setUp(self):
        acesso.limpar_limites()
        correio.limpar_caixa()
        type(self).numero += 1
        self.email = f'esquecida{self.numero}@exemplo.test'
        self.sid, _, self.conta = conta_com_email(self.root, self.a, self.ids['dono'], self.email, casos=['alpha'])

    def publico(self, operacao, dados):
        status, _, corpo = self.pedir('POST', '/api/' + operacao, json.dumps(dados),
                                      {'Content-Type': 'application/json', 'Origin': cenario.ORIGEM})
        return status, json.loads(corpo or b'{}'), corpo

    def test_a_resposta_e_a_mesma_com_conta_e_sem_conta_e_o_link_vai_so_na_mensagem(self):
        with correio.usar('simulado'):
            com_conta = self.publico('senha-esqueci', {'email': self.email})
            sem_conta = self.publico('senha-esqueci', {'email': 'ninguem@exemplo.test'})
            malformado = self.publico('senha-esqueci', {'email': 'sem-arroba'})
            correio.aguardar()
        self.assertEqual(com_conta[0], 200)
        self.assertEqual(com_conta[2], sem_conta[2])
        self.assertEqual(com_conta[2], malformado[2])
        mensagem, = correio.caixa()  # one message, to the account's own address
        self.assertEqual((mensagem['tipo'], mensagem['para']), ('redefinicao', self.email))
        self.assertRegex(mensagem['link'], '^' + cenario.ORIGEM + r'/redefinir/[A-Za-z0-9_-]{43}$')
        token = mensagem['link'].rsplit('/', 1)[1]
        self.assertNotIn(token, com_conta[2].decode('utf-8'))
        correio.limpar_caixa()
        for dados in ({'token': token, 'senha': 'curta'}, {'token': token, 'senha': NOVA, 'email': 'outro@exemplo.test'},
                      {'token': token, 'senha': NOVA, 'conta': self.ids['dono']}):
            self.assertEqual(self.publico('senha-redefinir', dados)[0], 400, dados)
        with correio.usar('simulado'):
            status, corpo, bruto = self.publico('senha-redefinir', {'token': token, 'senha': NOVA})
            correio.aguardar()
        self.assertEqual((status, corpo), (200, {'estado': 'senha_redefinida'}), bruto[:200])
        self.assertEqual([(m['tipo'], m['para']) for m in correio.caixa()], [('senha_trocada', self.email)])  # the person is told
        self.assertIsNone(acesso.sessao(self.root, self.sid))
        self.assertEqual(self.publico('entrar', {'login': self.email, 'senha': SENHA})[0], 401)
        self.assertEqual(self.publico('entrar', {'login': self.email, 'senha': NOVA})[0], 200)
        usado = self.publico('senha-redefinir', {'token': token, 'senha': 'mais-uma-senha-longa-3'})
        inexistente = self.publico('senha-redefinir', {'token': 'x' * 43, 'senha': 'mais-uma-senha-longa-3'})
        self.assertEqual((usado[0], usado[1]['codigo'], usado[2]), (400, 'link_invalido', inexistente[2]))
        self.assertEqual(self.post('dono', 'codex-status', {})[0], 200)  # nobody else was touched

    def test_sem_envio_de_verdade_esqueci_a_senha_fica_desligado(self):
        antes = self.linhas_de_links()
        for email in (self.email, 'ninguem@exemplo.test'):
            status, corpo, _ = self.publico('senha-esqueci', {'email': email})
            self.assertEqual((status, corpo['codigo']), (400, 'transporte_indisponivel'))
        self.assertEqual(self.linhas_de_links(), antes)  # no link is made that nobody could receive
        self.assertEqual(correio.caixa(), [])

    def linhas_de_links(self):
        con = acesso.sqlite3.connect(acesso.caminho_bd(self.root))
        try:
            return con.execute('SELECT COUNT(*) FROM links').fetchone()[0]
        finally:
            con.close()

    def test_a_pagina_de_entrada_sabe_sem_sessao_se_esqueci_a_senha_esta_ligado(self):
        status, _, corpo = self.pedir('GET', '/api/entrada')
        self.assertEqual((status, json.loads(corpo)), (200, {'esqueci_senha': False}))  # the link on the screen: off
        with correio.usar('simulado'):
            self.assertEqual(json.loads(self.pedir('GET', '/api/entrada')[2]), {'esqueci_senha': True})
        with patch.dict(acesso.os.environ, {'VLADO_CORREIO': 'pombo'}):  # a wrong configuration reads as off
            self.assertEqual(json.loads(self.pedir('GET', '/api/entrada')[2]), {'esqueci_senha': False})
        self.sem_sentinela(corpo)

    def test_paginas_de_aceitar_e_de_redefinir_sao_a_de_entrar_sem_cache_e_sem_referencia(self):
        entrar = self.pedir('GET', '/entrar')
        for caminho in ('/aceitar/' + 'T' * 43, '/redefinir/' + 'T' * 43, '/ativar/' + 'T' * 43):
            status, cabecalhos, corpo = self.pedir('GET', caminho)
            self.assertEqual((status, corpo), (200, entrar[2]), caminho)
            self.assertEqual((cabecalhos['Cache-Control'], cabecalhos['Referrer-Policy']), ('no-store', 'no-referrer'), caminho)
            self.assertNotIn(b'T' * 43, corpo)  # the token stays in the path: the page is the same for everybody
        for caminho in ('/aceitar', '/redefinir/', '/aceitar/a/b', '/redefinir/' + 'T' * 101, '/aceitar/..%2f'):
            self.assertNotEqual(self.pedir('GET', caminho)[2], entrar[2], caminho)

    def test_senha_fora_do_tamanho_tem_codigo_proprio_no_aceite_e_na_redefinicao(self):
        _, convite, _ = acesso.convidar(self.root, self.a, self.ids['dono'], f'tamanho{self.numero}@exemplo.test', 'leitor', [])
        with correio.usar('simulado'):
            self.publico('senha-esqueci', {'email': self.email})
            correio.aguardar()
        token = correio.caixa()[0]['link'].rsplit('/', 1)[1]
        for operacao, dados in (('convite-aceitar', {'token': convite, 'nome': 'Nova Pessoa'}), ('senha-redefinir', {'token': token})):
            for senha in ('curta', 'x' * 257, None):
                status, corpo, _ = self.publico(operacao, {**dados, 'senha': senha})
                self.assertEqual((status, corpo['codigo']), (400, 'senha_invalida'), operacao)
        status, corpo, _ = self.publico('convite-aceitar', {'token': convite, 'nome': '', 'senha': NOVA})
        self.assertEqual((status, corpo['codigo']), (400, 'requisicao_invalida'))
        invalido = self.publico('senha-redefinir', {'token': 'x' * 43, 'senha': NOVA})[1]
        self.assertEqual((invalido['codigo'], invalido['erro']),
                         ('link_invalido', 'Link inválido, usado ou vencido. Peça outro em Esqueci a senha.'))

    def test_falha_de_envio_nao_muda_a_resposta(self):
        with correio.usar('smtp'), patch.object(correio, '_smtp', side_effect=OSError('sem rede')) as envio, \
                patch.object(correio.registro_acesso, 'registrar') as registrar:
            resposta = self.publico('senha-esqueci', {'email': self.email})
            correio.aguardar()
        self.assertEqual(envio.call_count, 1)  # the delivery broke in its own thread ...
        self.assertIn(('email_falhou', 'redefinicao'), [(c.args[0], c.kwargs.get('mensagem')) for c in registrar.call_args_list])
        with correio.usar('simulado'):
            sem_conta = self.publico('senha-esqueci', {'email': 'ninguem2@exemplo.test'})
        self.assertEqual((resposta[0], resposta[2]), (200, sem_conta[2]))  # ... and who asked got the answer of always

    def test_trocar_a_propria_senha_avisa_no_email_da_conta(self):
        status, cabecalhos, corpo = self.pedir('POST', '/api/entrar', json.dumps({'login': self.email, 'senha': SENHA}),
                                               {'Content-Type': 'application/json', 'Origin': cenario.ORIGEM})
        sessao = (cabecalhos['Set-Cookie'].split(';')[0], json.loads(corpo)['csrf'])
        with correio.usar('simulado'):
            self.assertEqual(self.post(sessao, 'conta-senha-trocar', {'senha_atual': SENHA, 'senha_nova': NOVA})[0], 200)
            self.assertEqual(self.post('dono', 'conta-senha-trocar', {'senha_atual': SENHA, 'senha_nova': SENHA})[0], 400)
            correio.aguardar()
        self.assertEqual([(m['tipo'], m['para']) for m in correio.caixa()], [('senha_trocada', self.email)])
        self.assertNotIn('http', correio.caixa()[0]['corpo'])


if __name__ == '__main__':
    unittest.main()
