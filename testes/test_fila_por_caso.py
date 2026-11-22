"""Estado da fila de extração por caso para quem vê o caso (UX-05, barra de envio por arquivo).

``GET /api/fila?caso=<id>`` e ``?lote=<id>``: o administrador vê todos os lotes; o convidado vê os
lotes dos casos liberados a ele, com os mesmos campos por arquivo, e o recibo sem o caminho do
arquivo. Lote de outro caso lê como inexistente (não diz que existe); caso não liberado é proibido.
Modo piloto com contas sintéticas; extração real de um texto sintético pela fila.
"""
import json
from pathlib import Path
import sys
import unittest

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
from test_autorizacao import Http  # noqa: E402
from test_fila_extracao import gravador  # noqa: E402


class FilaPorCasoTest(Http):
    def setUp(self):
        super().setUp()
        self.lote = self.server.fila.receber('alpha', gravador(('novo.txt', b'Documento novo sintetico.\n')),
                                             natureza='sinteticos')
        self.server.fila.aguardar(self.lote, 60)  # published: its receipt is in the state

    def fila(self, sessao, consulta):
        status, _, corpo = self.get(sessao, '/api/fila?' + consulta)
        return status, json.loads(corpo or b'{}')

    def test_convidado_ve_os_lotes_do_caso_liberado_com_os_campos_por_arquivo(self):
        status, corpo = self.fila(self.ana, 'caso=alpha')
        self.assertEqual(status, 200, corpo)
        lote = next(item for item in corpo['lotes'] if item['lote'] == self.lote)
        self.assertEqual((lote['caso'], lote['estado'], lote['total'], lote['prontos']), ('alpha', 'publicado', 1, 1))
        arquivo = lote['arquivos'][0]
        self.assertEqual(set(arquivo), {'indice', 'nome', 'bytes', 'estado', 'etapa', 'pagina', 'paginas', 'extracao',
                                        'tentativas', 'motivo'})
        self.assertEqual((arquivo['nome'], arquivo['estado']), ('novo.txt', 'pronto'))
        self.assertNotIn('arquivo_recibo', lote['recibo'])  # the receipt without its file path
        self.assertEqual(lote['recibo']['corpus_id'], 'alpha_v2')
        status, corpo = self.fila(self.ana, 'lote=' + self.lote)
        self.assertEqual((status, corpo['lote']['lote']), (200, self.lote))
        self.assertNotIn('arquivo_recibo', corpo['lote']['recibo'])

    def test_outro_caso_e_proibido_e_lote_de_outro_caso_nao_existe_para_ele(self):
        self.assertEqual(self.fila(self.bia, 'caso=alpha')[0], 403)
        status, corpo = self.fila(self.bia, 'lote=' + self.lote)
        self.assertEqual((status, corpo['erro']), (400, 'Lote não encontrado na fila.'))  # same as a missing one
        status, inexistente = self.fila(self.bia, 'lote=' + 'f' * 32)
        self.assertEqual((status, inexistente), (400, corpo))  # word for word the answer for a missing batch
        self.assertEqual(self.fila(self.ana, 'caso=beta')[0], 403)
        self.assertEqual(self.fila(self.ana, '')[0], 403)  # a guest always names a case or a batch

    def test_administrador_ve_tudo_e_sem_sessao_nao_entra(self):
        status, corpo = self.fila(self.admin, 'caso=alpha')
        self.assertEqual(status, 200, corpo)
        lote = next(item for item in corpo['lotes'] if item['lote'] == self.lote)
        self.assertIn('arquivo_recibo', lote['recibo'])
        self.assertEqual(self.fila(self.admin, '')[0], 200)  # every batch
        self.assertNotEqual(self.fila(None, 'caso=alpha')[0], 200)


if __name__ == '__main__':
    unittest.main()
