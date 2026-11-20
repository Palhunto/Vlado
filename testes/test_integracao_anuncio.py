"""/api/integracao anuncia cada área com rota na Mesa (combinação das fases 01 a 08).

A Interface só mostra uma tela quando a rota está anunciada; uma área com rota e sem
anúncio fica invisível para um cliente que confere a integração. Servidor local, modo local,
fixture sintética; sem modelo nem rede externa.
"""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente
from interface_pesquisa import Servidor
import fontes_web
import rascunhos
import rotas_evidencia
import rotas_redacao
import rotas_tabelas

# Área anunciada -> operações que a Mesa precisa aceitar para ela.
AREAS = {
    'quadros_evidencia': rotas_evidencia.OPERACOES,
    'tabelas_apuracao': rotas_tabelas.OPERACOES,
    'continuidade_resumo': ('continuidade-resumo', *rascunhos.OPERACOES),
    'conferencia_redacao': tuple(op for op in rotas_redacao.OPERACOES if op.startswith('redacao-')),
    'entrevistas': tuple(op for op in rotas_redacao.OPERACOES if op.startswith('entrevistas-')),
    'fontes_web': fontes_web.OPERACOES,
}


class IntegracaoAnuncioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = Ambiente()
        cls.root = cls.env.root

    @classmethod
    def tearDownClass(cls):
        cls.env.cleanup()

    def setUp(self):
        self.server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def pedir(self, method, path, data=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request(method, path, body=None if data is None else json.dumps(data), headers={
            'Content-Type': 'application/json', 'Origin': self.server.origin, 'X-Session-Token': self.server.token})
        response = con.getresponse()
        body = json.loads(response.read() or b'{}')
        con.close()
        return response.status, body

    def test_cada_area_com_rota_e_anunciada(self):
        status, integracao = self.pedir('GET', '/api/integracao')
        self.assertEqual(status, 200)
        for area, operacoes in AREAS.items():
            with self.subTest(area=area):
                self.assertTrue(operacoes, area)
                self.assertIs(integracao.get(area), True, f'{area} tem rota e precisa ser anunciada')

    def test_operacoes_anunciadas_existem_na_mesa(self):
        # Pedido vazio: a rota existe e responde com erro de pedido, nunca "operação desconhecida".
        for area, operacoes in AREAS.items():
            for operacao in operacoes:
                with self.subTest(area=area, operacao=operacao):
                    status, body = self.pedir('POST', '/api/' + operacao, {})
                    self.assertNotEqual(status, 404, body)
                    self.assertNotEqual(body.get('codigo'), 'operacao_desconhecida', body)


if __name__ == '__main__':
    unittest.main()
