"""\"Virar pergunta ou pedido\" contra o servidor de verdade (interface/formularios.js, testes/virar_pedido.cjs).

O teste do navegador usa um servidor simulado; aqui os corpos que a tela envia (diligencias-criar com origem nula, texto da lacuna como ação e o tipo de
contato; hipoteses-atualizar só com as lacunas, uma delas já com o diligencia_id) passam por ``diligencias`` e ``hipoteses`` de verdade. Dados sintéticos.
"""
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente
import diligencias
import hipoteses
from test_tabelas_apuracao import Fontes


class VirarPedidoTest(Fontes, unittest.TestCase):
    def setUp(self):
        env, (_, _, _, second) = Ambiente.copia_completa(); self.addCleanup(env.cleanup)
        self.preparar(env, second)

    def pedido(self, **campos):
        return {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Editora B', **campos}

    def test_diligencia_de_contato_ligada_a_lacuna_registrada(self):
        criada = hipoteses.salvar(self.root, self.pedido(enunciado='A dispensa seguiu o rito legal.', situacao='em_aberto', evidencias=[],
                                                          lacunas=[{'descricao': 'Parecer jurídico da dispensa.', 'diligencia_id': None}]), 'criar')
        # o que a tela envia
        d = diligencias.salvar(self.root, self.pedido(origem=None, acao='Parecer jurídico da dispensa.', responsavel='Ana Lima', prazo='2026-12-15',
                                                      tipo='entrevista', destinatario='Comissão de licitação'), 'criar')
        self.assertEqual(d['diligencia']['tipo'], 'entrevista'); self.assertEqual(d['diligencia']['acao'], 'Parecer jurídico da dispensa.')
        detalhe = hipoteses.detalhe(self.root, 'alpha', criada['id'])
        lacunas = [{'descricao': l['descricao'], 'diligencia_id': l.get('diligencia_id') or None} for l in detalhe['estado']['lacunas']]
        lacunas[0]['diligencia_id'] = d['id']
        hipoteses.salvar(self.root, self.pedido(id=criada['id'], anterior_sha256=detalhe['sha256'], lacunas=lacunas), 'atualizar')
        depois = hipoteses.quadro(self.root, 'alpha')['hipoteses'][0]
        self.assertEqual(depois['faltam'][0]['diligencia_id'], d['id'])
        self.assertEqual(depois['faltam'][0]['diligencia_estado'], 'a_solicitar')

    def test_pedido_via_lai_e_sem_prazo(self):
        d = diligencias.salvar(self.root, self.pedido(origem=None, acao='Ata da comissão.', responsavel='Ana Lima', prazo=None, tipo='pedido_lai',
                                                      destinatario='Prefeitura (e-SIC)'), 'criar')
        self.assertEqual((d['diligencia']['tipo'], d['diligencia']['prazo']), ('pedido_lai', None))


if __name__ == '__main__':
    unittest.main()
