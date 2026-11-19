"""HTTP routes of the evidence boards (scripts/rotas_evidencia.py) over a local port.

Synthetic cases in a temporary folder; no model or network call. Covers success of every route,
refusal without a session, refusal of another case and readable validation errors (code + message).
"""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rotas_evidencia
from criar_caso import criar_caso
from fixture_achados import Ambiente
from interface_pesquisa import Servidor
from nova_rodada import criar_rodada
from selecionar_caso import selecionar
import test_autorizacao as autorizacao  # module import: its TestCases are not re-collected here


class RotasEvidenciaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = Ambiente()
        cls.root = cls.env.root
        _, _, _, second = cls.env.completo()
        cls.regs = second['manifesto']['registros_sha256']
        a, b = cls.root / 'v1.txt', cls.root / 'v2.txt'
        a.write_text('Cláusula 1.\nValor R$ 10,00.\n', encoding='utf-8')
        b.write_text('Cláusula 1.\nValor R$ 12,00.\n', encoding='utf-8')
        criar_caso(cls.root, 'gamma', 'Comparação sintética', [a, b], 'sinteticos')
        selecionar(cls.root, 'gamma')
        criar_rodada(cls.root, 'R001', 'Teste técnico sintético.', indice=False)
        selecionar(cls.root, None)
        cls.env.caso('beta')

    @classmethod
    def tearDownClass(cls):
        cls.env.cleanup()

    def setUp(self):
        self.server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def post(self, op, data, token=None, origin=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        headers = {'Content-Type': 'application/json', 'Origin': origin or self.server.origin}
        if token is not False:
            headers['X-Session-Token'] = token or self.server.token
        con.request('POST', '/api/' + op, body=json.dumps(data), headers=headers)
        response = con.getresponse()
        body = json.loads(response.read() or b'{}')
        con.close()
        return response.status, body

    def ok(self, op, data):
        status, body = self.post(op, data)
        self.assertEqual(status, 200, (op, body))
        return body

    def erro(self, op, data, codigo):
        status, body = self.post(op, data)
        self.assertEqual(status, 400, (op, body))
        self.assertEqual(body.get('codigo'), codigo, body)
        self.assertTrue(isinstance(body.get('erro'), str) and body['erro'].strip(), body)
        self.assertNotIn('Traceback', body['erro'])
        self.assertNotIn(str(self.root), body['erro'])
        return body

    def ia(self, evidence='E001', case='alpha'):
        return {'tipo': 'ia', 'caso_id': case, 'rodada': 'R001', 'revisao': 'r2',
                'registros_sha256': self.regs, 'evidencia_id': evidence}

    @staticmethod
    def link(ref, papel='suporte'):
        return {'referencia': ref, 'papel': papel, 'suporte': 'sustentado',
                'natureza': 'declaracao_documental', 'justificativa': 'Trecho sintético.'}

    @staticmethod
    def base(caso='alpha', **fields):
        return {'caso': caso, 'requisicao_id': uuid.uuid4().hex, 'autor': 'Editora', **fields}

    def test_hipoteses_criar_listar_detalhar_atualizar_e_quadro(self):
        created = self.ok('hipoteses-criar', self.base(enunciado='Hipótese sintética',
                                                       evidencias=[self.link(self.ia())]))
        listed = self.ok('hipoteses-listar', {'caso': 'alpha'})
        self.assertIn(created['id'], [h['id'] for h in listed['hipoteses']])
        detail = self.ok('hipoteses-detalhe', {'caso': 'alpha', 'id': created['id']})
        self.assertEqual(len(detail['evidencias']), 1)
        self.assertIn('estado', detail['evidencias'][0])
        self.ok('hipoteses-atualizar', self.base(id=created['id'], anterior_sha256=created['sha256'],
                                                 situacao='sustentada'))
        board = self.ok('hipoteses-quadro', {'caso': 'alpha'})
        mine = [h for h in board['hipoteses'] if h['id'] == created['id']]
        self.assertEqual(len(mine), 1)
        self.assertEqual(len(mine[0]['sustentam']), 1)
        # Updating against a stale hash is refused with a readable code.
        self.erro('hipoteses-atualizar', self.base(id=created['id'], anterior_sha256=created['sha256'],
                                                   situacao='refutada'), 'registro_mudou')

    def test_linha_do_tempo_criar_listar_filtrar_e_detalhar(self):
        data = {'tipo': 'fato', 'valor': '2021-03', 'aproximada': False, 'fonte': 0, 'observacao': ''}
        event = self.ok('linha-tempo-criar', self.base(descricao='Fato sintético',
                                                       evidencias=[self.link(self.ia())], datas=[data]))
        listed = self.ok('linha-tempo-listar', {'caso': 'alpha', 'tipos': ['fato']})
        self.assertIn(event['id'], json.dumps(listed))
        detail = self.ok('linha-tempo-detalhe', {'caso': 'alpha', 'id': event['id']})
        self.assertEqual(len(detail['evidencias']), 1)
        self.ok('linha-tempo-listar', {'caso': 'alpha', 'incluir_retirados': True})
        self.erro('linha-tempo-listar', {'caso': 'alpha', 'tipos': ['inventado']}, 'tipos_data_invalidos')
        self.erro('linha-tempo-listar', {'caso': 'alpha', 'incluir_retirados': 'sim'}, 'filtro_retirados_invalido')

    def test_comparador_de_evidencias_e_de_documentos(self):
        result = self.ok('comparar-evidencias', {'caso': 'alpha', 'a': self.ia('E001'), 'b': self.ia('E002')})
        self.assertIsInstance(result, dict)
        docs = self.ok('comparar-documentos', {'caso': 'gamma', 'rodada': 'R001', 'documento_a': 'D001',
                                               'documento_b': 'D002', 'contexto': 1})
        self.assertGreaterEqual(docs['total_alteracoes'], 1)
        self.erro('comparar-documentos', {'caso': 'gamma', 'rodada': 'R001', 'documento_a': 'D001',
                                          'documento_b': 'D009'}, 'documento_fora_da_rodada')
        self.erro('comparar-documentos', {'caso': 'gamma', 'rodada': '../R001', 'documento_a': 'D001',
                                          'documento_b': 'D002'}, 'rodada_comparacao_ausente')
        self.erro('comparar-documentos', {'caso': 'gamma', 'rodada': 'R001', 'documento_a': 'D001',
                                          'documento_b': 'D002', 'contexto': 99}, 'contexto_comparacao_invalido')

    def test_mapa_entidades_relacao_ver_e_homonimos(self):
        p1 = self.ok('mapa-entidade-criar', self.base(tipo='pessoa', nome='João da Silva'))
        p2 = self.ok('mapa-entidade-criar', self.base(tipo='pessoa', nome='Joao Silva'))
        self.ok('mapa-entidade-atualizar', self.base(id=p1['id'], anterior_sha256=p1['sha256'],
                                                     nome='João da Silva Sintético'))
        relation = self.ok('mapa-relacao-criar', self.base(origem=p1['id'], destino=p2['id'], tipo='socio',
                                                           evidencias=[self.link(self.ia())]))
        self.ok('mapa-relacao-atualizar', self.base(id=relation['id'], anterior_sha256=relation['sha256'],
                                                    tipo='socio', evidencias=[self.link(self.ia())]))
        board = self.ok('mapa-ver', {'caso': 'alpha'})
        self.assertIn(relation['id'], json.dumps(board))
        self.ok('mapa-homonimos', {'caso': 'alpha'})

    def test_recusa_sem_sessao_ou_com_token_errado(self):
        for token in (False, 'token-errado'):
            for op in rotas_evidencia.OPERACOES:
                status, body = self.post(op, {'caso': 'alpha'}, token=token)
                self.assertIn(status, (401, 403), (op, token, body))
                self.assertNotIn('hipoteses', body)
        status, _ = self.post('hipoteses-listar', {'caso': 'alpha'}, origin='https://outro.example')
        self.assertEqual(status, 403)

    def test_recusa_referencia_de_outro_caso(self):
        created = self.ok('hipoteses-criar', self.base(enunciado='Só em alpha', evidencias=[self.link(self.ia())]))
        self.erro('hipoteses-detalhe', {'caso': 'beta', 'id': created['id']}, 'registro_inexistente')
        status, body = self.post('comparar-evidencias', {'caso': 'beta', 'a': self.ia(), 'b': self.ia('E002')})
        self.assertEqual(status, 400, body)
        self.assertEqual(body['codigo'], 'evidencia_outro_caso')
        status, body = self.post('hipoteses-criar', self.base(caso='beta', enunciado='Mistura',
                                                              evidencias=[self.link(self.ia())]))
        self.assertEqual((status, body['codigo']), (400, 'evidencia_outro_caso'))
        self.assertNotIn(created['id'], json.dumps(self.ok('hipoteses-listar', {'caso': 'beta'})))

    def test_validacao_legivel_de_caso_e_campos(self):
        self.erro('mapa-ver', {}, 'quadro_sem_caso')
        self.erro('mapa-ver', {'caso': '../alpha'}, 'quadro_sem_caso')
        self.erro('hipoteses-listar', {'caso': 'alpha', 'caminho': '../x'}, 'quadro_campos_invalidos')
        self.erro('hipoteses-detalhe', {'caso': 'alpha', 'id': 'H' + '0' * 32}, 'registro_inexistente')
        status, body = self.post('mapa-ver', {'caso': 'inexistente'})
        self.assertEqual(status, 400, body)
        self.assertTrue(body.get('codigo'))


class RotasEvidenciaContasTest(autorizacao.Http):
    """Hosted mode: no session → 401 before the case is read; guests never reach the boards."""

    def test_sem_sessao_401_e_convidado_403(self):
        for op in rotas_evidencia.OPERACOES:
            status, headers, body = self.request('POST', '/api/' + op, json.dumps({'caso': 'alpha'}),
                                                 {'Content-Type': 'application/json', 'Origin': autorizacao.ORIGEM})
            self.assertEqual(status, 401, (op, body))
            status, body = self.post(self.ana, op, {'caso': 'alpha'})
            self.assertEqual((status, body.get('codigo')), (403, 'operacao_proibida'), op)

    def test_admin_alcanca_os_quadros(self):
        status, body = self.post(self.admin, 'hipoteses-listar', {'caso': 'alpha'})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['hipoteses'], [])


if __name__ == '__main__':
    unittest.main()
