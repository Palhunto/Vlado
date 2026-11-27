"""P45: os candidatos para os quadros na síntese (MESA.md 1.3.0; contrato CONTRATO_QUADROS_ONDA4, seção 1).

A síntese do modo mesa aceita ``candidatos``. A lista malformada recusa a síntese (o modelo corrige na mesma etapa);
um candidato sem referência válida é recusado sozinho e fica registrado; os aceitos e os recusados vão para
``saidas/achados/candidatos/r3_sintese.json``, preso ao hash da revisão. No modo legado a chave continua recusada.
Agente sintético e provedor simulado; sem rede e sem modelo. Nomes sintéticos (Vila Serena, Construtora Alfa).
"""
import copy
import json
import unittest

import test_codex_integracao as fixture
import test_fora_do_briefing as fora
import test_fluxo_codex as fluxo
from comum import VERSAO_MESA, ler_json
from modo_mesa_fixture import ligar_mesa
from registros_achados import carregar
import sugestoes_quadros as sq

PESSOA = {'chave': 'C1', 'tipo': 'pessoa', 'achado_id': 'A001', 'evidencias': ['E001'],
          'campos': {'nome': 'Marta Reis', 'variantes': ['M. Reis', 'M. Reis']}}
ORGANIZACAO = {'chave': 'C2', 'tipo': 'organizacao', 'achado_id': 'A001', 'evidencias': ['E001'],
               'campos': {'nome': 'Construtora Alfa Ltda.'}}
LIGACAO = {'chave': 'C3', 'tipo': 'ligacao', 'achado_id': 'A001', 'evidencias': ['E001'],
           'campos': {'de': 'C1', 'para': 'C2', 'tipo': 'sócia'}}
ACONTECIMENTO = {'chave': 'C4', 'tipo': 'acontecimento', 'achado_id': 'A001', 'evidencias': ['E001'],
                 'campos': {'descricao': 'Assinatura do Contrato 041/2025 em Vila Serena',
                            'datas': [{'tipo': 'assinatura', 'valor': '2025-03-03'}]}}
HIPOTESE = {'chave': 'C5', 'tipo': 'hipotese', 'achado_id': 'A002', 'evidencias': ['E002'],
            'campos': {'enunciado': 'A sócia da contratada assinou o contrato também como testemunha.'}}
BONS = [PESSOA, ORGANIZACAO, LIGACAO, ACONTECIMENTO, HIPOTESE]


class CandidatosNaSinteseTest(unittest.TestCase):
    start = fixture.CodexIntegrationTest.start
    tool, wait_stage, end, step, terminal = (getattr(fluxo.FluxoAutomaticoTest, n) for n in
                                             ('tool', 'wait_stage', 'end', 'step', 'terminal'))
    evidencia, ate_a_sintese, briefing, guardar = (getattr(fora.ForaDoBriefingTest, n) for n in
                                                   ('evidencia', 'ate_a_sintese', 'briefing', 'guardar'))
    mesa = True

    def setUp(self):
        fixture.CodexIntegrationTest.setUp(self)
        if self.mesa:
            ligar_mesa(self.root)
        self.fx = self
        self.identifier = self.start()
        self.ctx = self.manager.contexts[self.identifier]
        self.refs = {}

    def arquivo(self):
        return self.ctx['run'] / 'saidas/achados/candidatos/r3_sintese.json'

    def test_candidatos_aceitos_e_recusados_ficam_registrados_presos_a_revisao(self):
        self.ate_a_sintese()
        ruins = [{'chave': 'C6', 'tipo': 'pessoa', 'achado_id': 'A999', 'evidencias': ['E001'], 'campos': {'nome': 'Carlos Prado'}},
                 {'chave': 'C7', 'tipo': 'pessoa', 'achado_id': 'A001', 'evidencias': ['E002'], 'campos': {'nome': 'Carlos Prado'}},
                 {'chave': 'C8', 'tipo': 'ligacao', 'achado_id': 'A001', 'evidencias': ['E001'],
                  'campos': {'de': 'C1', 'para': 'C6', 'tipo': 'irmão'}},
                 {'chave': 'C9', 'tipo': 'tabela', 'achado_id': 'A001', 'evidencias': ['E001'], 'campos': {}},
                 {'chave': 'C10', 'tipo': 'pessoa', 'achado_id': 'A001', 'evidencias': ['E001'],
                  'campos': {'nome': 'Ana Lima', 'cpf': '00000000000'}}]
        self.step('sintese', {**self.briefing(), 'candidatos': BONS + ruins})
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido', self.ctx['meta'].get('situacao'))
        record = ler_json(self.arquivo())
        _, manifest = carregar(self.root, 'alpha', 'R001', 'r3_sintese')
        self.assertEqual((record['revisao'], record['registros_sha256'], record['versao_mesa']),
                         ('r3_sintese', manifest['registros_sha256'], VERSAO_MESA))
        self.assertEqual([c['chave'] for c in record['candidatos']], ['C1', 'C2', 'C3', 'C4', 'C5'])
        self.assertEqual([(r['chave'], r['codigo']) for r in record['recusados']],
                         [('C6', 'achado_inexistente'), ('C7', 'evidencia_fora_do_achado'), ('C8', 'ponta_invalida'),
                          ('C9', 'tipo_invalido'), ('C10', 'campos_invalidos')])
        self.assertEqual(record['candidatos'][0]['campos'], {'nome': 'Marta Reis', 'variantes': ['M. Reis']})
        self.assertEqual(record['candidatos'][3]['campos']['datas'],
                         [{'tipo': 'assinatura', 'valor': '2025-03-03', 'aproximada': False, 'fonte': 0, 'observacao': ''}])

    def test_lista_malformada_recusa_a_sintese_e_a_mesma_etapa_aceita_a_correcao(self):
        self.ate_a_sintese()
        for candidatos in ({'C1': PESSOA}, [PESSOA, PESSOA], [{**PESSOA, 'chave': 'X1'}], [PESSOA] * 41):
            with self.subTest(candidatos=str(candidatos)[:40]), self.assertRaisesRegex(ValueError, '^Candidatos para os quadros'):
                self.guardar({**self.briefing(), 'candidatos': candidatos})
        self.assertFalse(self.arquivo().exists())
        self.guardar({**self.briefing(), 'candidatos': []})
        self.end()
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido', self.ctx['meta'].get('situacao'))
        self.assertEqual(ler_json(self.arquivo())['candidatos'], [])

    def test_sem_candidatos_nao_ha_arquivo(self):
        self.ate_a_sintese()
        self.step('sintese', self.briefing())
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido', self.ctx['meta'].get('situacao'))
        self.assertFalse(self.arquivo().exists())


class CandidatosNoLegadoTest(CandidatosNaSinteseTest):
    mesa = False

    def test_candidatos_aceitos_e_recusados_ficam_registrados_presos_a_revisao(self):
        self.ate_a_sintese()
        with self.assertRaisesRegex(ValueError, 'Campos não autorizados na entrega estruturada: candidatos'):
            self.guardar({**self.briefing(), 'candidatos': BONS})
        self.assertFalse(self.arquivo().exists())
        self.manager.cancelar(self.identifier)
        self.terminal()

    test_lista_malformada_recusa_a_sintese_e_a_mesma_etapa_aceita_a_correcao = None


class RegrasDoCandidatoTest(unittest.TestCase):
    """``conferir`` sem o fluxo, contra uma revisão sintética (A001: E001 suporte, E002 contradição, E003 contexto)."""

    def setUp(self):
        self.data = {'achados': [{'id': 'A001', 'versoes': [{'versao': 1}, {'versao': 2}]}, {'id': 'A002', 'versoes': [{'versao': 1}]}],
                     'vinculos': [{'achado_id': 'A001', 'versao': v, 'evidencia_id': e, 'papel': p}
                                  for v in (1, 2) for e, p in (('E001', 'suporte'), ('E002', 'contradicao'), ('E003', 'contexto'))]}

    def um(self, item):
        aceitos, recusados = sq.conferir([item], self.data)
        return aceitos[0] if aceitos else recusados[0]['codigo']

    def test_fonte_da_data_e_suporte_ou_contexto_declarado(self):
        base = copy.deepcopy(ACONTECIMENTO)
        base['evidencias'] = ['E001', 'E002', 'E003']
        for fonte, tipo, esperado in ((0, 'assinatura', None), (1, 'assinatura', 'datas_invalidas'),
                                      (2, 'assinatura', 'datas_invalidas'), (2, 'declarada_por_fonte', None),
                                      (3, 'assinatura', 'datas_invalidas')):
            item = copy.deepcopy(base)
            item['campos']['datas'] = [{'tipo': tipo, 'valor': '2025-03', 'fonte': fonte}]
            with self.subTest(fonte=fonte, tipo=tipo):
                result = self.um(item)
                self.assertEqual(result if isinstance(result, str) else None, esperado)

    def test_datas_tipos_e_valores(self):
        for value, esperado in (('2025', None), ('2025-02-30', 'datas_invalidas'), ('03/03/2025', 'datas_invalidas')):
            item = copy.deepcopy(ACONTECIMENTO)
            item['campos']['datas'][0]['valor'] = value
            result = self.um(item)
            self.assertEqual(result if isinstance(result, str) else None, esperado, value)
        item = copy.deepcopy(ACONTECIMENTO)
        item['campos']['datas'][0]['tipo'] = 'vencimento'
        self.assertEqual(self.um(item), 'datas_invalidas')

    def test_ligacao_e_acontecimento_precisam_de_suporte(self):
        for item in (LIGACAO, ACONTECIMENTO):
            only_context = {**copy.deepcopy(item), 'evidencias': ['E003']}
            if item is ACONTECIMENTO:
                only_context['campos']['datas'][0]['tipo'] = 'declarada_por_fonte'
            aceitos, recusados = sq.conferir([PESSOA, ORGANIZACAO, only_context], self.data)
            self.assertEqual([r['codigo'] for r in recusados], ['sem_suporte'], item['tipo'])
        self.assertEqual(self.um({**HIPOTESE, 'achado_id': 'A001', 'evidencias': ['E003']})['tipo'], 'hipotese')

    def test_evidencias_e_campos(self):
        cases = [({**PESSOA, 'evidencias': []}, 'evidencias_invalidas'), ({**PESSOA, 'evidencias': ['E001', 'E001']}, 'evidencias_invalidas'),
                 ({**PESSOA, 'evidencias': ['E001'] * 6}, 'evidencias_invalidas'), ({**PESSOA, 'extra': 1}, 'campos_invalidos'),
                 ({**PESSOA, 'campos': {'nome': ''}}, 'campo_invalido'), ({**PESSOA, 'campos': {'nome': 'x' * 301}}, 'campo_invalido'),
                 ({**HIPOTESE, 'achado_id': 'A001', 'evidencias': ['E001'], 'campos': {'enunciado': 'H', 'situacao': 'sustentada'}},
                  'campos_invalidos'),
                 ({**PESSOA, 'campos': 'Marta Reis'}, 'campos_invalidos')]
        for item, code in cases:
            with self.subTest(code=code, item=str(item)[:60]):
                self.assertEqual(self.um(item), code)

    def test_ligacao_aponta_para_pessoa_ou_organizacao_aceita_e_diferente(self):
        hip = {**HIPOTESE, 'achado_id': 'A001', 'evidencias': ['E001']}
        for campos in ({'de': 'C1', 'para': 'C1', 'tipo': 'sócia'}, {'de': 'C1', 'para': 'C5', 'tipo': 'sócia'},
                       {'de': 'C1', 'para': 'C9', 'tipo': 'sócia'}):
            aceitos, recusados = sq.conferir([PESSOA, ORGANIZACAO, hip, {**LIGACAO, 'campos': campos}], self.data)
            self.assertEqual([r['codigo'] for r in recusados], ['ponta_invalida'], campos)
        # The link may come before its ends in the list.
        aceitos, recusados = sq.conferir([LIGACAO, PESSOA, ORGANIZACAO], self.data)
        self.assertEqual(([c['chave'] for c in aceitos], recusados), (['C3', 'C1', 'C2'], []))

    def test_aplica_so_no_modo_mesa_a_partir_da_1_3_0(self):
        for instrucoes, vale in (({'modo': 'mesa', 'versao': '1.3.0'}, True), ({'modo': 'mesa', 'versao': '2.0.0'}, True),
                                 ({'modo': 'mesa', 'versao': '1.2.0'}, False), ({'modo': 'legado', 'versao': None}, False),
                                 ({'modo': 'mesa', 'versao': 'x'}, False), (None, False)):
            self.assertEqual(sq.aplica(instrucoes), vale, instrucoes)


if __name__ == '__main__':
    unittest.main()
