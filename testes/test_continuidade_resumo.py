"""Resumo de retomada da apuração ativa (continuidade.resumo_caso) e sua rota na Mesa.

Pasta temporária com apurações sintéticas; nenhuma chamada de modelo ou de rede externa.
Cobre documentos cadastrados e pendentes, rodada e etapa concluída, quadros com pendências,
rascunhos abertos da própria conta (sem o texto), conversas interrompidas, recusa de campos,
caso na lixeira, isolamento entre contas e apurações e a recusa da rota para convidados.
"""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import escrever_json
import continuidade
import erros
from fluxo_codex import ETAPAS
import hipoteses
import lixeira
import rascunhos
from fixture_achados import Ambiente
from interface_pesquisa import Servidor
import test_autorizacao as autorizacao  # module import: its TestCases are not re-collected here

ANA = {'id': 'a1b2c3d4e5f60708', 'nome': 'Ana'}
BIA = {'id': '0807f6e5d4c3b2a1', 'nome': 'Bia'}
SEGREDO_DO_RASCUNHO = 'Texto que nunca sai do módulo de rascunhos'


class ResumoCasoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = Ambiente()
        cls.root = cls.env.root
        cls.env.caso('beta')

    @classmethod
    def tearDownClass(cls):
        cls.env.cleanup()

    def tearDown(self):
        estado = self.root / 'execucoes/alpha/R001/saidas/codex_fluxo_estado.json'
        estado.unlink(missing_ok=True)
        for pasta in (self.root / 'casos/alpha/rascunhos', self.root / 'casos/beta/rascunhos'):
            for arquivo in sorted(pasta.rglob('*.json')) if pasta.is_dir() else []:
                arquivo.unlink()

    def test_documentos_rodada_quadros_e_pendencias(self):
        resumo = continuidade.resumo_caso(self.root, 'alpha')
        self.assertEqual(resumo['caso'], 'alpha')
        self.assertEqual(resumo['documentos']['cadastrados'], 3)
        pendentes = resumo['documentos']['pendentes']
        self.assertEqual([d['nome'] for d in pendentes], ['visual.pdf'], 'o PDF em branco não tem texto extraível')
        self.assertIn(pendentes[0]['motivo'], ('paginas_sem_texto', 'falha_extracao', 'sem_extracao'))
        rodada = resumo['rodada']
        self.assertEqual((rodada['id'], rodada['concluida'], rodada['etapa_concluida'], rodada['proxima_etapa']),
                         ('R001', False, None, ETAPAS[0]))
        self.assertEqual([q['quadro'] for q in resumo['quadros']], ['hipoteses', 'diligencias', 'tabelas'])
        self.assertTrue(all(q['erro'] is None and q['pendentes'] == 0 for q in resumo['quadros']), resumo['quadros'])
        tipos = [(p['tipo'], p['area']) for p in resumo['pendencias']]
        self.assertEqual(tipos, [('documento', 'documentos'), ('rodada', 'codex')])
        self.assertEqual(resumo['rascunhos'], [])

    def test_etapas_aceitas_mostram_o_que_foi_concluido(self):
        estado = self.root / 'execucoes/alpha/R001/saidas/codex_fluxo_estado.json'
        estado.parent.mkdir(parents=True, exist_ok=True)
        escrever_json(estado, {'etapas': {e: {} for e in ETAPAS[:3]}})
        rodada = continuidade.resumo_caso(self.root, 'alpha')['rodada']
        self.assertEqual((rodada['etapa_concluida'], rodada['proxima_etapa'], rodada['concluida']),
                         (ETAPAS[2], ETAPAS[3], False))
        escrever_json(estado, {'etapas': {e: {} for e in ETAPAS}})
        resumo = continuidade.resumo_caso(self.root, 'alpha')
        self.assertTrue(resumo['rodada']['concluida'])
        self.assertNotIn('rodada', [p['tipo'] for p in resumo['pendencias']])
        estado.write_text('{quebrado', encoding='utf-8')
        rodada = continuidade.resumo_caso(self.root, 'alpha')['rodada']
        self.assertEqual((rodada['estado_legivel'], rodada['aceitas']), (False, []))

    def test_rascunhos_da_conta_sem_texto_e_isolados(self):
        rascunhos.salvar(self.root, 'alpha', ANA, 'pergunta', 0, {'pergunta': SEGREDO_DO_RASCUNHO})
        rascunhos.salvar(self.root, 'alpha', ANA, 'quadro-diligencias', 0, {'diligencias_acao': 'Pedir contrato'})
        rascunhos.salvar(self.root, 'beta', ANA, 'caderno/N0001', 0, {'texto': 'Outra apuração'})
        rascunhos.salvar(self.root, 'alpha', BIA, 'caderno/N0002', 0, {'texto': 'Nota da Bia'})
        resumo = continuidade.resumo_caso(self.root, 'alpha', ANA)
        self.assertEqual(sorted((r['tela'], r['area']) for r in resumo['rascunhos']),
                         [('pergunta', 'codex'), ('quadro-diligencias', 'diligencias')])
        bruto = json.dumps(resumo, ensure_ascii=False)
        for texto in (SEGREDO_DO_RASCUNHO, 'Pedir contrato', 'Outra apuração', 'Nota da Bia'):
            self.assertNotIn(texto, bruto)
        self.assertEqual([r['tela'] for r in continuidade.resumo_caso(self.root, 'alpha', BIA)['rascunhos']],
                         ['caderno/N0002'])
        self.assertEqual(continuidade.resumo_caso(self.root, 'alpha')['rascunhos'], [], 'modo local: dono próprio')
        self.assertEqual(sum(p['tipo'] == 'rascunho' for p in resumo['pendencias']), 2)

    def test_area_de_cada_tela_de_rascunho(self):
        casos = {'pergunta': 'codex', 'pergunta/' + 'a' * 32: 'codex', 'quadro-diligencias/0123abcd': 'diligencias',
                 'quadro-diligencias-resposta/0123abcd': 'diligencias', 'quadro-revisao/0123abcd': 'achados',
                 'quadro-caderno': 'apuracao', 'caderno/N0001': 'apuracao'}
        self.assertEqual({tela: continuidade._area_rascunho(tela) for tela in casos}, casos)

    def test_conversas_interrompidas_viram_pendencia(self):
        conversas = [{'id': 'a' * 32, 'titulo': 'Primeira', 'rodada': 'R001', 'retomavel': True},
                     {'id': 'b' * 32, 'titulo': 'Concluída', 'rodada': 'R001', 'retomavel': False}]
        resumo = continuidade.resumo_caso(self.root, 'alpha', conversas=conversas)
        self.assertEqual([c['id'] for c in resumo['conversas_interrompidas']], ['a' * 32])
        self.assertIn(('conversa', 'a' * 32, 'codex'), [(p['tipo'], p['id'], p['area']) for p in resumo['pendencias']])

    def test_quadro_ilegivel_nao_esconde_os_demais(self):
        with patch.object(hipoteses, 'listar', side_effect=ValueError('Histórico divergente.')):
            resumo = continuidade.resumo_caso(self.root, 'alpha')
        quadros = {q['quadro']: q for q in resumo['quadros']}
        self.assertEqual(quadros['hipoteses']['erro'], 'ilegivel', 'código fixo, sem o texto da exceção')
        self.assertEqual((quadros['diligencias']['erro'], quadros['tabelas']['erro']), (None, None))
        self.assertIn(('quadro', 'hipoteses', 'erro'), [(p['tipo'], p['id'], p['motivo']) for p in resumo['pendencias']])

    def test_pedido_invalido_e_caso_na_lixeira(self):
        chamadas = []
        listar = lambda caso: chamadas.append(caso) or []
        for pedido, codigo in (({'caso': 'alpha', 'conteudo': 1}, 'resumo_campos_invalidos'),
                               ({'caso': '../alpha'}, 'resumo_sem_caso'), ({}, 'resumo_sem_caso'), ([], 'resumo_campos_invalidos')):
            with self.assertRaises(ValueError) as ctx:
                continuidade.executar_resumo(self.root, pedido, listar_conversas=listar)
            self.assertEqual(erros.codigo_de(str(ctx.exception))[0], codigo, pedido)
        self.assertEqual(chamadas, [], 'as conversas só são listadas depois de validar o pedido')
        self.assertEqual(continuidade.executar_resumo(self.root, {'caso': 'alpha'}, listar_conversas=listar)['caso'], 'alpha')
        self.assertEqual(chamadas, ['alpha'])
        with patch.object(lixeira, 'excluido', side_effect=lambda root, caso, **kw: caso == 'beta'):
            with self.assertRaises(ValueError):
                continuidade.executar_resumo(self.root, {'caso': 'beta'})
            with self.assertRaises(ValueError):
                continuidade.resumo_caso(self.root, 'beta')


class ResumoRotaTest(unittest.TestCase):
    """Modo local: a rota devolve o resumo e recusa campos fora do pedido."""

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

    def post(self, op, data):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request('POST', '/api/' + op, body=json.dumps(data), headers={
            'Content-Type': 'application/json', 'Origin': self.server.origin, 'X-Session-Token': self.server.token})
        response = con.getresponse()
        body = json.loads(response.read() or b'{}')
        con.close()
        return response.status, body

    def test_rota_devolve_resumo_e_recusa_campos(self):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request('GET', '/api/integracao', headers={'Origin': self.server.origin, 'X-Session-Token': self.server.token})
        integracao = json.loads(con.getresponse().read())
        con.close()
        self.assertIs(integracao.get('continuidade_resumo'), True, 'a Interface detecta a rota pela integração')
        status, body = self.post('continuidade-resumo', {'caso': 'alpha'})
        self.assertEqual(status, 200, body)
        bruto = json.dumps(body).lower()
        for proibido in ('chave', 'api_key', 'token', 'segredo', 'sk-'):
            self.assertNotIn(proibido, bruto, 'o resumo não leva nenhum dado de chave')
        self.assertEqual((body['caso'], body['documentos']['cadastrados'], body['rodada']['id']), ('alpha', 3, 'R001'))
        self.assertEqual(body['conversas_interrompidas'], [])
        status, body = self.post('continuidade-resumo', {'caso': 'alpha', 'tela': 'pergunta'})
        self.assertEqual((status, body['codigo']), (400, 'resumo_campos_invalidos'), body)


class ResumoContasTest(autorizacao.Http):
    """Modo hospedado: sem sessão 401; convidado não alcança o resumo; cada conta vê os próprios rascunhos."""

    def test_convidado_recusado_e_rascunhos_da_conta(self):
        status, _, _ = self.request('POST', '/api/continuidade-resumo', json.dumps({'caso': 'alpha'}),
                                    {'Content-Type': 'application/json', 'Origin': autorizacao.ORIGEM})
        self.assertEqual(status, 401)
        status, body = self.post(self.ana, 'continuidade-resumo', {'caso': 'alpha'})
        self.assertEqual((status, body['codigo']), (403, 'operacao_proibida'), body)
        pedido = {'caso': 'alpha', 'tela': 'pergunta', 'versao': 0, 'conteudo': {'texto': 'Pergunta da Ana?'}}
        self.assertEqual(self.post(self.ana, 'rascunhos-salvar', pedido)[0], 200)
        status, body = self.post(self.admin, 'continuidade-resumo', {'caso': 'alpha'})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['rascunhos'], [], 'a editora não vê o rascunho da Ana')


if __name__ == '__main__':
    unittest.main()
