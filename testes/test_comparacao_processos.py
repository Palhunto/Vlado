"""L9: a comparação entre processos com campos estruturados (contrato CONTRATO_QUADROS_ONDA4, seção 5).

A revisão do modo mesa (MESA.md 1.3.0) aceita ``comparacoes``; cada uma é conferida contra a revisão publicada, a
inválida é recusada sozinha, e o arquivo é gravado antes de publicar a revisão. ``comparar-processos`` devolve os
dois lados resolvidos, as seis conferências da IA, a identidade por hash e a pendência. Sem modelo e sem rede.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import ler_json
from fixture_achados import Ambiente
from registros_achados import carregar
import comparacao_processos as cp
import erros
import rotas_evidencia
import test_candidatos_quadros as candidatos

MESMO = dict.fromkeys(cp.CONFERENCIAS, 'mesmo')
COMPARACAO = {'achado_id': 'A001',
              'chave': {'identificador': 'Parecer jurídico nº 12/2025', 'data': '2025-02-10',
                        'emissor': 'Procuradoria de Vila Serena', 'versao': 'única'},
              'lados': [{'processo': 'Processo 2025/118 · Contrato 041/2025', 'fundamento': 'E001', 'questao': 'Validade da dispensa',
                         'fase': 'primeira instância', 'desfecho': 'Dispensa considerada regular', 'desfecho_evidencia': None},
                        {'processo': 'Processo 2025/201 · Contrato 052/2025', 'fundamento': 'E002', 'questao': 'Validade da dispensa',
                         'fase': 'recurso', 'desfecho': 'Dispensa anulada', 'desfecho_evidencia': 'E003'}],
              'conferencias': MESMO}


class ComparacaoProcessosTest(unittest.TestCase):
    def setUp(self):
        self.env, _ = Ambiente.copia_completa(); self.addCleanup(self.env.cleanup)
        self.root = self.env.root
        self.data, self.manifest = carregar(self.root, 'alpha', 'R001', 'r2')

    def gravar(self, lista):
        record = cp.gravar(self.env.run(), self.data, lista, '1.3.0')
        self.assertEqual(record['registros_sha256'], self.manifest['registros_sha256'])
        return record

    def ler(self, **data):
        return rotas_evidencia.executar(self.root, 'comparar-processos', {'caso': 'alpha', **data})

    def test_le_os_dois_lados_as_conferencias_e_a_identidade(self):
        self.gravar([COMPARACAO])
        found = self.ler()
        self.assertEqual((found['estruturada'], found['analise']['revisao'], len(found['comparacoes'])), (True, 'r2', 1))
        item = found['comparacoes'][0]
        self.assertEqual((item['achado']['id'], item['achado']['suporte_ia'], item['achado']['destino']),
                         ('A001', 'sustentado', 'incluido'))
        a, b = item['lados']
        self.assertEqual((a['fundamento']['estado'], a['fundamento']['trecho'], a['desfecho_evidencia']),
                         ('conferida', 'A fonte declara valor 12.', None))
        self.assertEqual((b['fundamento']['trecho'], b['desfecho_evidencia']['documento']['documento_id']),
                         ('Outra versão declara valor 14.', 'D002'))
        self.assertEqual(item['chave']['emissor'], 'Procuradoria de Vila Serena')
        self.assertEqual((item['conferencias'], item['mesmo_arquivo'], item['pendente']), (MESMO, True, False))
        self.assertEqual(item['revisao_ia']['achado_id'], 'A001')

    def test_conferencia_que_nao_e_mesmo_deixa_pendente(self):
        self.gravar([{**COMPARACAO, 'conferencias': {**MESMO, 'fase': 'diferente'}},
                     {**COMPARACAO, 'conferencias': {**MESMO, 'trecho': 'a_conferir'}}])
        self.assertEqual([c['pendente'] for c in self.ler()['comparacoes']], [True, True])

    def test_comparacao_invalida_e_recusada_sozinha(self):
        cases = [({**COMPARACAO, 'achado_id': 'A999'}, 'achado_inexistente'),
                 ({**COMPARACAO, 'lados': [COMPARACAO['lados'][0], {**COMPARACAO['lados'][1], 'fundamento': 'E001'}]}, 'lados_iguais'),
                 ({**COMPARACAO, 'achado_id': 'A002'}, 'evidencia_fora_do_achado'),
                 ({**COMPARACAO, 'lados': COMPARACAO['lados'][:1]}, 'campos_invalidos'),
                 ({**COMPARACAO, 'conferencias': {**MESMO, 'fase': 'talvez'}}, 'conferencias_invalidas'),
                 ({**COMPARACAO, 'chave': {'identificador': 'x'}}, 'campos_invalidos'),
                 ({**COMPARACAO, 'extra': 1}, 'campos_invalidos')]
        record = self.gravar([COMPARACAO] + [c for c, _ in cases])
        self.assertEqual(len(record['comparacoes']), 1)
        self.assertEqual([r['codigo'] for r in record['recusados']], [code for _, code in cases])
        with self.assertRaisesRegex(ValueError, '^Comparações entre processos'):
            cp.estrutura([COMPARACAO] * 21)

    def test_sem_arquivo_a_vista_nao_reconstroi_do_texto(self):
        found = self.ler()
        self.assertEqual((found['estruturada'], found['comparacoes']), (False, []))
        for rodada in ('R999', '../R001'):
            with self.assertRaises(ValueError) as caught:
                self.ler(rodada=rodada)
            self.assertEqual(erros.codigo_de(str(caught.exception))[0], 'rodada_sem_achados')

    def test_arquivo_de_outra_revisao_nao_aparece(self):
        self.gravar([COMPARACAO])
        path = cp.caminho(self.env.run(), 'r2')
        record = ler_json(path)
        record['registros_sha256'] = '0' * 64
        path.write_text(json.dumps(record), encoding='utf-8')
        self.assertEqual(self.ler()['estruturada'], False)


class ComparacoesNaRevisaoTest(candidatos.CandidatosNaSinteseTest):
    """The review of the mesa mode takes ``comparacoes``; the legacy one still refuses the key."""

    def revisao(self, comparacoes):
        for etapa in ('inventario', 'plano', 'busca'):
            self.step(etapa)
        self.step('geracao_inicial', {'texto': 'Geração inicial sintética.', 'achados': [
            {'subquestao': 'Qual valor a fonte declara?', 'redacao': 'A fonte sintética declara valor 123.',
             'natureza': 'alegacao_atribuida', 'limitacoes': 'Sintético.', 'evidencias': [self.evidencia(0), self.evidencia(1)]}]})
        self.wait_stage('revisao')
        self.tool({'acao': 'ler', 'referencia': self.refs['hit']['referencia']})
        payload = {'texto': 'Revisão sintética pela mesma IA.', 'revisoes': [
            {'achado_id': 'A001', 'suporte': 'sustentado', 'motivo': 'Literal.', 'limitacoes': 'Sintético.', 'acao': 'manter'}],
            'comparacoes': comparacoes}
        return self.tool({'acao': 'guardar', 'etapa': 'revisao', 'texto': json.dumps(payload, ensure_ascii=False)})

    def test_candidatos_aceitos_e_recusados_ficam_registrados_presos_a_revisao(self):
        no_outcome = {**COMPARACAO, 'lados': [COMPARACAO['lados'][0], {**COMPARACAO['lados'][1], 'desfecho_evidencia': None}]}
        self.revisao([no_outcome, {**no_outcome, 'achado_id': 'A002'}])
        record = ler_json(self.ctx['run'] / 'saidas/achados/comparacoes/r2_revisao.json')
        _, manifest = carregar(self.root, 'alpha', 'R001', 'r2_revisao')
        self.assertEqual(record['registros_sha256'], manifest['registros_sha256'])
        self.assertEqual(([c['achado_id'] for c in record['comparacoes']], [r['codigo'] for r in record['recusados']]),
                         (['A001'], ['achado_inexistente']))
        self.manager.cancelar(self.identifier)
        self.terminal()

    def test_lista_malformada_recusa_a_sintese_e_a_mesma_etapa_aceita_a_correcao(self):
        with self.assertRaisesRegex(ValueError, '^Comparações entre processos'):
            self.revisao({'A001': COMPARACAO})
        self.assertFalse((self.ctx['run'] / 'saidas/achados/revisoes/r2_revisao').exists())
        self.manager.cancelar(self.identifier)
        self.terminal()

    test_falha_ao_gravar_os_candidatos_nao_publica_a_sintese_e_a_nova_tentativa_sai = None
    test_sem_candidatos_nao_ha_arquivo = None


class ComparacoesNoLegadoTest(ComparacoesNaRevisaoTest):
    mesa = False

    def test_candidatos_aceitos_e_recusados_ficam_registrados_presos_a_revisao(self):
        with self.assertRaisesRegex(ValueError, 'Campos não autorizados na entrega estruturada: comparacoes'):
            self.revisao([COMPARACAO])
        self.manager.cancelar(self.identifier)
        self.terminal()

    test_lista_malformada_recusa_a_sintese_e_a_mesma_etapa_aceita_a_correcao = None


if __name__ == '__main__':
    unittest.main()
