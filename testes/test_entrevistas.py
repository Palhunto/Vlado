"""Preparação de entrevistas e pedidos de informação (scripts/entrevistas.py e a extensão de scripts/diligencias.py).

Lacuna do quadro de hipóteses ou afirmação sem suporte vira pergunta por modelo fixo, com a
evidência que a motiva; cada pergunta liga-se a uma diligência de contato; a resposta entra
como fonte do caderno, citável pelo contrato do Core, e fecha a lacuna; pauta e pedido saem
em Markdown. Fontes sintéticas; sem modelo nem rede.
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
from fixture_achados import Ambiente
from interface_pesquisa import Servidor
import caderno
import conferencia_redacao as redacao
import diligencias
import entrevistas
import evidencias as ev
import hipoteses
import rotas_redacao


class Base:
    def preparar_caso(self, env, second):
        self.env, self.root = env, env.root
        self.registros = second['manifesto']['registros_sha256']
        self.docs = caderno.documentos(self.root, 'alpha')

    def ia(self, eid='E001'):
        return {'tipo': 'ia', 'caso_id': 'alpha', 'rodada': 'R001', 'revisao': 'r2',
                'registros_sha256': self.registros, 'evidencia_id': eid}

    def base(self, **fields):
        return {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Repórter A', **fields}

    def hipotese(self, lacuna='Ordem bancária do pagamento.'):
        return hipoteses.salvar(self.root, self.base(
            enunciado='O valor declarado foi pago.', evidencias=[
                {'referencia': self.ia(), 'papel': 'suporte', 'justificativa': 'Declara o valor.'}],
            lacunas=[{'descricao': lacuna}]))

    def lacuna(self, **match):
        rows = entrevistas.lacunas(self.root, 'alpha')['lacunas']
        return next(r for r in rows if all(r['origem'].get(k) == v or r['motivo'].get(k) == v for k, v in match.items()))

    def pergunta(self, row, tipo='entrevista', destinatario='Secretaria de Obras', **extra):
        return entrevistas.preparar(self.root, self.base(origem=row['origem'], tipo=tipo, destinatario=destinatario,
                                                         responsavel='Repórter A', prazo='2026-12-01', **extra))

    def resposta(self, trecho='Outra versão declara valor 14.', localizador='Linha 2'):
        doc = self.docs['documentos'][0]
        return {'origem_id': self.docs['origem_id'], 'documento_id': doc['documento_id'], 'documento_sha256': doc['sha256'],
                'pagina_pdf': None, 'localizador': localizador, 'trecho': trecho, 'transcricao_manual': False}


class EntrevistasTest(Base, unittest.TestCase):
    def setUp(self):
        env, (_, _, _, second) = Ambiente.copia_completa(); self.addCleanup(env.cleanup)
        self.preparar_caso(env, second)

    def test_lacuna_vira_pergunta_com_a_evidencia_que_a_motiva(self):
        self.hipotese()
        row = self.lacuna(lacuna='Ordem bancária do pagamento.')
        self.assertEqual((row['motivo']['origem_lacuna'], row['pergunta_id']), ('registrada', None))
        self.assertEqual(row['evidencias'][0]['referencia']['evidencia_id'], 'E001')
        body = self.base(origem=row['origem'], tipo='entrevista', destinatario='Secretaria de Obras',
                         responsavel='Repórter A', prazo='2026-12-01')
        record = entrevistas.preparar(self.root, body)
        self.assertEqual(entrevistas.preparar(self.root, body)['id'], record['id'])  # repetir não duplica
        view = entrevistas.detalhe(self.root, 'alpha', record['id'])
        self.assertEqual(view['pergunta'], 'A respeito de “O valor declarado foi pago”: pode informar e, se possível, '
                                           'documentar o seguinte ponto: Ordem bancária do pagamento?')
        self.assertEqual((view['situacao'], view['evidencias'][0]['estado']), ('aberta', 'conferida'))
        self.assertEqual(view['evidencias'][0]['evidencia']['trecho'], 'A fonte declara valor 12.')
        self.assertEqual(self.lacuna(lacuna='Ordem bancária do pagamento.')['pergunta_id'], record['id'])
        # Lacuna automática e afirmação sem suporte também viram pergunta, cada uma com seu modelo fixo.
        automatic = self.lacuna(origem_lacuna='automatica')
        self.assertIn('Há documento ou registro', entrevistas.rascunho(automatic['motivo']))
        text = redacao.criar(self.root, self.base(titulo='Reportagem', texto='O valor foi pago em 2021.'))
        claim_row = self.lacuna(tipo='afirmacao')
        self.assertEqual(claim_row['origem']['afirmacao_id'], text['estado']['afirmacoes'][0]['id'])
        claim_question = self.pergunta(claim_row, tipo='pedido_lai', destinatario='Prefeitura')
        self.assertEqual(claim_question['estado']['pergunta'], 'Pode confirmar ou corrigir a seguinte informação e indicar '
                                                              'o documento que a registra: “O valor foi pago em 2021”?')
        # A pessoa reescreve o rascunho; o histórico guarda o texto anterior.
        edited = entrevistas.editar(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'],
                                                        pergunta='Quando a ordem bancária foi emitida?'))
        self.assertEqual([e['estado']['pergunta'] for e in edited['historico']][-1], 'Quando a ordem bancária foi emitida?')
        self.assertEqual(len(edited['historico']), 2)

    def test_origem_alterada_ou_inexistente_e_recusada(self):
        hypothesis = self.hipotese()
        row = self.lacuna(lacuna='Ordem bancária do pagamento.')
        hipoteses.salvar(self.root, self.base(id=hypothesis['id'], anterior_sha256=hypothesis['sha256'],
                                              lacunas=[{'descricao': 'Contrato assinado.'}]), 'atualizar')
        with self.assertRaisesRegex(ValueError, 'lacuna de origem mudou'):
            self.pergunta(row)
        with self.assertRaisesRegex(ValueError, 'Origem da pergunta inválida'):
            self.pergunta({'origem': {'tipo': 'livre', 'texto': 'qualquer coisa'}})
        with self.assertRaisesRegex(ValueError, 'tipo de contato'):
            self.pergunta(self.lacuna(lacuna='Contrato assinado.'), tipo='telefonema')

    def test_pergunta_liga_se_a_diligencia_sem_quebrar_o_formato_antigo(self):
        self.hipotese()
        record = self.pergunta(self.lacuna(lacuna='Ordem bancária do pagamento.'))
        followup = diligencias.detalhe(self.root, 'alpha', record['estado']['diligencia_id'])['diligencia']
        self.assertEqual((followup['tipo'], followup['destinatario'], followup['pergunta_id'], followup['prazo']),
                         ('entrevista', 'Secretaria de Obras', record['id'], '2026-12-01'))
        self.assertTrue(followup['acao'].startswith('Entrevista: A respeito de'))
        self.assertEqual(followup['estado'], 'a_solicitar')
        # Diligência no formato anterior continua válida, sem os campos de contato.
        old = diligencias.salvar(self.root, self.base(origem=None, acao='Pedir cópia do contrato.', responsavel='Repórter B'))
        self.assertNotIn('tipo', old['diligencia'])
        updated = diligencias.salvar(self.root, self.base(diligencia_id=old['id'], anterior_sha256=old['sha256'],
                                                          estado='em_andamento', acao='Pedir cópia do contrato.',
                                                          responsavel='Repórter B', prazo=None,
                                                          observacao='Contato iniciado.'), 'atualizar')
        self.assertEqual(updated['diligencia']['estado'], 'em_andamento')
        self.assertEqual(diligencias.listar(self.root, 'alpha', texto='Secretaria de Obras')['total'], 1)
        with self.assertRaisesRegex(ValueError, 'tipo de contato'):
            diligencias.salvar(self.root, self.base(origem=None, acao='Contato.', responsavel='A', destinatario='X'))
        # O vínculo com a pergunta não muda depois de criado.
        with self.assertRaisesRegex(ValueError, 'Campos inválidos'):
            diligencias.salvar(self.root, self.base(diligencia_id=old['id'], anterior_sha256=updated['sha256'],
                                                    estado='em_andamento', acao='x', responsavel='y', tipo='entrevista'),
                               'atualizar')

    def test_resposta_registrada_vira_fonte_citavel_e_fecha_a_lacuna(self):
        self.hipotese()
        record = self.pergunta(self.lacuna(lacuna='Ordem bancária do pagamento.'))
        with self.assertRaisesRegex(ValueError, 'precisa da fonte'):
            entrevistas.responder(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'], situacao='respondida'))
        body = self.base(id=record['id'], anterior_sha256=record['sha256'], situacao='respondida',
                         resposta=self.resposta(), observacao_resposta='Resposta por e-mail.')
        answered = entrevistas.responder(self.root, body)
        self.assertEqual(entrevistas.responder(self.root, body)['sha256'], answered['sha256'])  # repetir não duplica
        view = entrevistas.detalhe(self.root, 'alpha', record['id'])
        answer = view['respostas'][0]
        self.assertEqual((view['situacao'], answer['situacao'], answer['fonte']['estado']), ('respondida', 'respondida', 'conferida'))
        self.assertEqual(answer['fonte']['evidencia']['trecho'], 'Outra versão declara valor 14.')
        self.assertEqual(answer['observacao'], 'Resposta por e-mail.')
        # A fonte é citável pelo contrato do Core: resolve e entra como vínculo de outro quadro.
        ref = answer['referencia']
        self.assertEqual(ev.resolver(self.root, 'alpha', ref)['origem'], 'humana')
        hipoteses.salvar(self.root, self.base(enunciado='Outra hipótese.', evidencias=[
            {'referencia': ref, 'papel': 'contradicao', 'justificativa': 'Resposta recebida.'}]))
        followup = diligencias.detalhe(self.root, 'alpha', view['diligencia']['id'])['diligencia']
        self.assertEqual(followup['estado'], 'resposta_recebida')
        self.assertEqual(followup['respostas'][0]['documentos'][0]['documento_id'], 'D001')
        self.assertEqual(self.lacuna(lacuna='Ordem bancária do pagamento.')['situacao'], 'respondida')
        # Sem resposta: a lacuna fica marcada, sem fonte e sem resposta na diligência.
        other = self.pergunta(self.lacuna(origem_lacuna='automatica'), tipo='pedido_informacao', destinatario='Câmara')
        with self.assertRaisesRegex(ValueError, 'sem resposta não leva fonte'):
            entrevistas.responder(self.root, self.base(id=other['id'], anterior_sha256=other['sha256'],
                                                       situacao='sem_resposta', resposta=self.resposta()))
        silent = entrevistas.responder(self.root, self.base(id=other['id'], anterior_sha256=other['sha256'],
                                                            situacao='sem_resposta'))
        self.assertEqual((silent['estado']['situacao'], silent['estado']['respostas'][0]['referencia']), ('sem_resposta', None))
        partial = entrevistas.responder(self.root, self.base(id=other['id'], anterior_sha256=silent['sha256'],
                                                             situacao='parcial', resposta=self.resposta()))
        self.assertEqual([a['situacao'] for a in partial['estado']['respostas']], ['sem_resposta', 'parcial'])

    def test_exporta_pauta_e_pedido_em_markdown(self):
        self.hipotese(lacuna='Pagamento *integral* em # parcela única.')
        interview = self.pergunta(self.lacuna(origem_lacuna='registrada'))
        text = redacao.criar(self.root, self.base(titulo='Reportagem', texto='O valor foi pago em 2021.'))
        lai = self.pergunta(self.lacuna(tipo='afirmacao'), tipo='pedido_lai', destinatario='Prefeitura de Exemplo')
        agenda = entrevistas.exportar(self.root, 'alpha', [interview['id'], lai['id']], 'pauta')
        markdown = agenda['markdown']
        self.assertTrue(markdown.startswith('# Pauta de entrevista e pedidos'))
        self.assertIn('Documento interno', markdown)
        self.assertIn('Secretaria de Obras', markdown)
        self.assertIn('“A fonte declara valor 12.”', markdown)
        self.assertIn(r'Pagamento \*integral\* em \# parcela única', markdown)  # texto do usuário não vira marcação
        self.assertTrue(agenda['nome_arquivo'].startswith('pauta_alpha_'))
        request = entrevistas.exportar(self.root, 'alpha', [lai['id']], 'pedido')['markdown']
        self.assertTrue(request.startswith('# Pedido via LAI'))
        self.assertIn('Lei nº 12.527/2011', request)
        self.assertIn('**Destinatário:** Prefeitura de Exemplo', request)
        self.assertIn('1. Pode confirmar ou corrigir', request)
        self.assertIn('resposta até 2026-12-01', request)
        self.assertNotIn('A fonte declara valor 12.', request)  # o pedido não leva evidências internas
        self.assertNotIn(text['id'], request)
        with self.assertRaisesRegex(ValueError, 'mesmo destinatário'):
            entrevistas.exportar(self.root, 'alpha', [interview['id'], lai['id']], 'pedido')
        with self.assertRaisesRegex(ValueError, 'Formato de exportação inválido'):
            entrevistas.exportar(self.root, 'alpha', [lai['id']], 'docx')


class RotasEntrevistasTest(Base, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ambiente, (_, _, _, second) = Ambiente.copia_completa()
        cls.ambiente.caso('beta', indice=False)
        cls.registros_classe = second

    @classmethod
    def tearDownClass(cls):
        cls.ambiente.cleanup()

    def setUp(self):
        self.preparar_caso(self.ambiente, self.registros_classe)
        self.server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def post(self, op, data):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request('POST', '/api/' + op, body=json.dumps(data), headers={
            'Content-Type': 'application/json', 'Origin': self.server.origin, 'X-Session-Token': self.server.token})
        response = con.getresponse()
        result = response.status, json.loads(response.read() or b'{}')
        con.close()
        return result

    def test_fluxo_pela_mesa_e_outro_caso(self):
        self.hipotese(lacuna='Nota fiscal da entrega.')
        status, gaps = self.post('entrevistas-lacunas', {'caso': 'alpha'})
        self.assertEqual(status, 200, gaps)
        row = next(r for r in gaps['lacunas'] if r['motivo']['lacuna'] == 'Nota fiscal da entrega.')
        status, created = self.post('entrevistas-preparar', self.base(origem=row['origem'], tipo='pedido_informacao',
                                                                      destinatario='Empresa X', responsavel='Repórter A'))
        self.assertEqual(status, 200, created)
        self.assertEqual((created['situacao'], created['diligencia']['tipo']), ('aberta', 'pedido_informacao'))
        status, listed = self.post('entrevistas-listar', {'caso': 'alpha'})
        self.assertIn(created['id'], [q['id'] for q in listed['perguntas']])
        status, exported = self.post('entrevistas-exportar', {'caso': 'alpha', 'ids': [created['id']], 'formato': 'pedido'})
        self.assertEqual(status, 200, exported)
        self.assertTrue(exported['markdown'].startswith('# Pedido de informação'))
        status, body = self.post('entrevistas-detalhe', {'caso': 'beta', 'id': created['id']})
        self.assertEqual((status, body.get('codigo')), (400, 'registro_inexistente'), body)
        status, body = self.post('entrevistas-preparar', self.base(caso='beta', origem=row['origem'], tipo='entrevista',
                                                                   destinatario='Empresa X', responsavel='Repórter A'))
        self.assertEqual((status, body.get('codigo')), (400, 'lacuna_origem_mudou'), body)
        status, body = self.post('entrevistas-exportar', {'caso': 'alpha', 'ids': [created['id']], 'formato': 'pdf'})
        self.assertEqual((status, body.get('codigo')), (400, 'exportacao_formato_invalido'), body)
        self.assertTrue(set(rotas_redacao.OPERACOES) >= {'entrevistas-preparar', 'entrevistas-responder'})


if __name__ == '__main__':
    unittest.main()
