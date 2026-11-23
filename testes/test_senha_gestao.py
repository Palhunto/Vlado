"""A senha pedida de novo em ``lixeira-apagar`` e ``ia-config-salvar`` (contrato de contas, seção 5.15).

Onde há contas, apagar de vez e gravar a configuração de IA levam a senha de quem faz, no campo ``senha``: sem
ela 403 ``senha_necessaria``; errada, 403 ``senha_atual_incorreta``, e conta; cinco erradas seguidas, 429. O item
fora do alcance responde como o que não existe, com ou sem senha, e a tentativa não conta. No modo local, sem
contas, nada muda (``test_apagamento.py`` e ``test_config_ia.py``). Sem modelo e sem rede.
"""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import apagamento
import cenario_redacoes as cenario
from comum import escrever_json
from interface_pesquisa import Servidor
import lixeira
from test_acesso import SENHA, hasher_rapido

ERRADA = 'senha-errada-de-teste'


class ApagarDeVezTest(cenario.DuasRedacoes):
    """``lixeira-apagar`` no modo ``piloto``, com duas redações."""

    def setUp(self):
        self.addCleanup(apagamento.aguardar, 60)

    def pedido(self, caso='alpha'):
        item = self.item_na_lixeira(caso)
        alcance = lixeira.alcance(self.root, item)
        return {'item': item, 'nome': 'R999', 'confirmacao': alcance['confirmacao']}

    def recusa(self, quem, dados, status, codigo):
        resposta = self.post(quem, 'lixeira-apagar', dados)
        self.assertEqual((resposta[0], resposta[1].get('codigo')), (status, codigo), resposta[2][:200])
        return resposta

    def na_lixeira(self, item):
        return item in {i['id'] for i in lixeira.ativos(self.root)}

    def test_apagar_de_vez_pede_a_senha_de_quem_apaga(self):
        base = self.pedido()
        self.recusa('dono', base, 403, 'senha_necessaria')
        self.recusa('dono', {**base, 'senha': ''}, 403, 'senha_necessaria')
        self.recusa('dono', {**base, 'senha': ERRADA}, 403, 'senha_atual_incorreta')
        self.assertTrue(self.na_lixeira(base['item']))
        # The name is checked first: a typing slip is not a wrong password, and it deletes nothing either.
        errado = self.post('dono', 'lixeira-apagar', {**base, 'nome': 'outro', 'senha': SENHA})
        self.assertEqual((errado[0], errado[1].get('codigo')), (400, 'nome_confirmacao_divergente'), errado[2][:200])
        self.recusa('dono', {**base, 'nome': 'outro', 'senha': ERRADA}, 400, 'nome_confirmacao_divergente')  # and it did not count
        self.assertTrue(self.na_lixeira(base['item']))
        status, corpo, bruto = self.post('dono', 'lixeira-apagar', {**base, 'senha': SENHA})
        self.assertEqual((status, corpo.get('estado')), (200, 'apagado'), bruto[:200])
        self.assertFalse(self.na_lixeira(base['item']))
        self.assertNotIn(SENHA, bruto.decode('utf-8'))

    def test_item_fora_do_alcance_responde_como_inexistente_com_ou_sem_senha(self):
        de_beta = self.pedido('beta')
        for senha in ({}, {'senha': ERRADA}, {'senha': SENHA}):
            with self.subTest(senha=senha.get('senha')):
                real = self.post('dono', 'lixeira-apagar', {**de_beta, **senha})
                falso = self.post('dono', 'lixeira-apagar', {**de_beta, 'item': 'f' * 32, **senha})
                self.assertEqual((real[0], real[2]), (falso[0], falso[2]))
                self.assertNotIn(real[1].get('codigo'), ('senha_necessaria', 'senha_atual_incorreta'))
                self.sem_sentinela(real[2])
        self.assertTrue(self.na_lixeira(de_beta['item']))
        con = acesso.sqlite3.connect(acesso.caminho_bd(self.root))
        try:  # and the wrong password sent with it counted against nobody
            self.assertEqual(con.execute('SELECT COUNT(*) FROM tentativas WHERE chave = ?',
                                         (acesso.CHAVE_CONFIRMACAO + self.ids['dono'],)).fetchone()[0], 0)
        finally:
            con.close()
        self.assertEqual(self.post('dono_b', 'lixeira-apagar', {**de_beta, 'senha': SENHA})[0], 200)  # its own dono can

    def test_cinco_senhas_erradas_bloqueiam_o_apagamento_de_quem_errou(self):
        self.conta('Dona Apressada', 'dona.apressada', 'dono')  # with the second factor the hosted mode asks of a dono
        acesso.limpar_limites()
        sessao, base = self._entrar('dona.apressada'), self.pedido()
        for _ in range(acesso.FALHAS_BLOQUEIO):
            self.recusa(sessao, {**base, 'senha': ERRADA}, 403, 'senha_atual_incorreta')
        resposta = self.recusa(sessao, {**base, 'senha': SENHA}, 429, 'bloqueado')
        self.assertEqual(resposta[1]['estado'], 'bloqueado')
        self.assertTrue(self.na_lixeira(base['item']))
        self.assertEqual(self.post(sessao, 'gerenciar-listar', {})[0], 200)  # the rest of the session goes on
        self.assertEqual(self.post('dono', 'lixeira-apagar', {**base, 'senha': SENHA})[0], 200)  # another dono is not blocked


class ConfiguracaoDeIATest(unittest.TestCase):
    """``ia-config-salvar`` no modo ``local-contas``: uma redação só, com login."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        escrever_json(self.root / 'configuracao.json', {'provedor': 'anthropic', 'modelo_preferido': None,
                                                         'max_tokens_saida': 4096})
        env = patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': '',
                                      'ANTHROPIC_API_KEY': '', 'OPENAI_API_KEY': '', 'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        hasher_rapido(self)
        acesso.limpar_limites()
        acesso.criar_primeiro_admin(self.root, 'Editora', 'editora', SENHA)
        self.server = Servidor(('127.0.0.1', 0), self.root, modo='local-contas')
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))
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

    def salvar(self, dados):
        status, _, bruto = self.pedir('ia-config-salvar', dados, self.sessao)
        return status, json.loads(bruto or b'{}'), bruto

    def test_gravar_a_configuracao_de_ia_pede_a_senha_e_ela_nao_vai_para_o_ajuste(self):
        base = {'provedor': 'openai', 'modelo_preferido': None}
        for dados, codigo in ((base, 'senha_necessaria'), ({**base, 'senha': ERRADA}, 'senha_atual_incorreta')):
            status, corpo, bruto = self.salvar(dados)
            self.assertEqual((status, corpo.get('codigo')), (403, codigo), bruto[:200])
        self.assertFalse((self.root / 'ajustes' / 'inferencia.json').exists())  # nothing was saved
        status, corpo, bruto = self.salvar({**base, 'senha': SENHA})
        self.assertEqual((status, corpo.get('provedor')), (200, 'openai'), bruto[:200])
        guardado = (self.root / 'ajustes' / 'inferencia.json').read_text(encoding='utf-8')
        for texto in (guardado, bruto.decode('utf-8')):
            self.assertNotIn(SENHA, texto)
        self.assertNotIn('senha', guardado)
        # The closed list of fields of the settings is still the same: the password is the only addition.
        self.assertEqual(self.salvar({**base, 'senha': SENHA, 'outro': 1})[0], 400)


if __name__ == '__main__':
    unittest.main()
