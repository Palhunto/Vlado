"""Human annotations remain independent of AI text, revisions and source indexes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import sha256, ler_json, escrever_json
from fixture_achados import Ambiente
import indice_achados
import revisao_humana as human


class RevisaoHumanaTest(unittest.TestCase):
    def setUp(self):
        self.fx, _ = Ambiente.copia_completa(quantidade=4); self.addCleanup(self.fx.cleanup)
        self.root, self.run = self.fx.root, self.fx.run()

    def query(self, **kwargs):
        return human.consultar(self.root, 'alpha', 'R001', 'r2', 'g2', **kwargs)

    def save(self, identifier='A001', state='precisa_de_ajuste', note='Valor correto, mas refere-se ao total do contrato.', **kwargs):
        detail = human.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', identifier)
        item = detail['achado']
        values = dict(achado_id=identifier, achado_versao=item['versao'], registros_sha256=detail['registros_sha256'],
                      estado=state, observacao=note, anterior=item['revisao_humana']['evento_id'])
        return human.salvar(self.root, 'alpha', 'R001', 'r2', **{**values, **kwargs})

    def test_padrao_pendente_e_leitura_nao_registram_aprovacao(self):
        result = self.query()
        self.assertEqual(result['progresso_revisao_humana']['revisados'], 0)
        self.assertEqual(result['progresso_revisao_humana']['total'], 4)
        self.assertTrue(all(row['revisao_humana']['estado'] == 'pendente' for row in result['resultados']))
        human.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', 'A001')
        self.assertFalse((self.run / 'saidas/revisao_humana').exists())
        self.assertNotIn('revisao_humana', indice_achados.consultar(self.root, 'alpha', 'R001', 'r2', 'g2')['resultados'][0])

    def test_marcacao_e_historico_preservam_ia_snapshot_e_bancos(self):
        before = {p: sha256(p) for p in self.run.rglob('*') if p.is_file()}
        result = self.save(state='conferida_no_original')
        self.assertEqual(result['revisao_humana']['estado'], 'conferida_no_original')
        first_files = list((self.run / 'saidas/revisao_humana').rglob('*.json'))
        self.assertEqual(len(first_files), 1)
        first_hash = sha256(first_files[0])
        self.save(state='precisa_de_ajuste', note='<script>texto literal</script>')
        final = self.query()['resultados'][0]
        self.assertEqual(final['revisao_humana']['observacao'], '<script>texto literal</script>')
        self.assertEqual(len(final['revisao_humana']['historico']), 2)
        self.assertEqual(final['conferencia_humana'], 'nao_realizada')
        self.assertEqual(sha256(first_files[0]), first_hash)
        self.assertEqual(before, {p: sha256(p) for p in before})

    def test_pendencias_filtradas_antes_da_paginacao_exportam_marcacoes(self):
        self.save(state='conferida_no_original')
        self.save('A003', state='sem_suporte_suficiente', note='Sem documento que sustente a afirmação.')
        result = self.query(filtros={'revisao_humana': 'pendente'}, limite=1)
        self.assertEqual(result['total_correspondencias'], 2)
        self.assertEqual(result['resultados'][0]['id'], 'A002')
        self.assertEqual(self.query(filtros={'revisao_humana': 'pendente'}, limite=1, deslocamento=1)['resultados'][0]['id'], 'A004')
        self.assertEqual(result['progresso_revisao_humana']['revisados'], 2)
        self.assertEqual(result['progresso_revisao_humana']['total'], 4)
        exported = self.query(completa=True, limite=1, deslocamento=3)
        self.assertEqual(exported['retornados'], 4)
        self.assertEqual(exported['resultados'][0]['revisao_humana']['observacao'], 'Valor correto, mas refere-se ao total do contrato.')
        self.assertTrue(exported['resultados'][0]['revisao_humana']['historico'])
        self.assertEqual(exported['resultados'][2]['revisao_humana']['estado'], 'sem_suporte_suficiente')
        self.assertEqual(ler_json(self.run / exported['arquivo_recibo']), exported)

    def test_concorrencia_idempotencia_e_retorno_a_pendente(self):
        first = self.save()
        count = len(list((self.run / 'saidas/revisao_humana').rglob('*.json')))
        retry = self.save(anterior=None)
        self.assertEqual(retry['estado'], 'sem_alteracao')
        self.assertEqual(len(list((self.run / 'saidas/revisao_humana').rglob('*.json'))), count)
        with self.assertRaisesRegex(ValueError, 'outra janela'):
            self.save(state='sem_suporte_suficiente', note='Outra observação.', anterior=None)
        current = self.save(state='pendente', note='Reabrir a conferência.')
        self.assertEqual(current['progresso']['revisados'], 0)
        self.assertEqual(len(current['revisao_humana']['historico']), 2)
        self.assertNotEqual(first['revisao_humana']['evento_id'], current['revisao_humana']['evento_id'])

    def test_revisoes_e_casos_nao_herdam_marcacao_geracoes_da_mesma_revisao_compartilham(self):
        self.save('A002', state='sem_suporte_suficiente')
        old = human.consultar(self.root, 'alpha', 'R001', 'r1', 'g1')
        self.assertEqual(old['progresso_revisao_humana']['revisados'], 0)
        indice_achados.construir(self.root, 'alpha', 'R001', 'r2', 'g3')
        rebuilt = human.consultar(self.root, 'alpha', 'R001', 'r2', 'g3')
        self.assertEqual(rebuilt['progresso_revisao_humana']['revisados'], 1)
        self.fx.caso('beta')
        from registros_achados import publicar
        publicar(self.root, 'beta', 'R001', self.fx.dados('beta'))
        indice_achados.construir(self.root, 'beta', 'R001', 'r1', 'g1')
        other = human.consultar(self.root, 'beta', 'R001', 'r1', 'g1')
        self.assertEqual(other['progresso_revisao_humana']['revisados'], 0)

    def test_identidades_estados_e_observacoes_invalidas_nao_gravam(self):
        for changes in ({'estado': 'aprovado'}, {'observacao': 'X' * 501}, {'observacao': None},
                        {'achado_versao': True}, {'achado_versao': 1}, {'registros_sha256': '0' * 64},
                        {'achado_id': '../A001'}, {'anterior': '../fora'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.save(**changes)
        with self.assertRaisesRegex(ValueError, 'não tem fontes'):
            self.save('A002', state='conferida_no_original')
        self.assertFalse(list((self.run / 'saidas/revisao_humana').rglob('*.json')))

    def test_historico_danificado_nao_vira_pendente_silenciosamente(self):
        self.save()
        file = next((self.run / 'saidas/revisao_humana').rglob('*.json'))
        item = ler_json(file); item['estado'] = 'inventado'; escrever_json(file, item)
        with self.assertRaisesRegex(ValueError, 'Histórico'):
            self.query()
        original = Path.iterdir
        def denied(path):
            if 'revisao_humana' in path.parts:
                raise PermissionError('Histórico sem permissão de leitura.')
            return original(path)
        with patch.object(Path, 'iterdir', denied), self.assertRaises(PermissionError):
            self.query()

    def test_selecao_explicita_recupera_marcacao_fontes_e_versao_sem_alterar_registros(self):
        saved = self.save()
        detail = human.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', 'A001')
        before = {p: sha256(p) for p in self.run.rglob('*') if p.is_file()}
        choice = {'achado_id':'A001', 'achado_versao':2,
                  'evento_id':saved['revisao_humana']['evento_id'], 'registros_sha256':detail['registros_sha256']}
        result = human.selecionar(self.root, 'alpha', 'R001', 'r2', 'g2', [choice])
        selected = result['observacoes'][0]
        self.assertIn('total do contrato', selected['observacao'])
        self.assertEqual(selected['redacao_anterior'], detail['achado']['redacao'])
        self.assertEqual(selected['fontes'], detail['achado']['evidencias'])
        self.assertEqual(selected['vinculos'], detail['achado']['vinculos'])
        self.assertTrue(all(sha256(p) == digest for p,digest in before.items()))

    def test_selecao_recusa_marcacao_alterada_duplicada_sem_salvamento_e_identidades_trocadas(self):
        saved = self.save()
        detail = human.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', 'A001')
        choice = {'achado_id':'A001', 'achado_versao':2,
                  'evento_id':saved['revisao_humana']['evento_id'], 'registros_sha256':detail['registros_sha256']}
        for selections in ([], [choice]*21, [choice,choice], [None],
                [{**choice,'achado_versao':True}], [{**choice,'achado_versao':1}],
                [{**choice,'registros_sha256':'0'*64}], [{**choice,'evento_id':'0'*32}],
                [{**choice,'achado_id':'A002','achado_versao':1}],
                [{**choice,'observacao':'Texto forjado no cliente'}]):
            with self.subTest(selections=selections), self.assertRaises(ValueError):
                human.selecionar(self.root, 'alpha', 'R001', 'r2', 'g2', selections)
        self.save(note='Observação alterada em outra janela.')
        with self.assertRaisesRegex(ValueError, 'marcação mudou'):
            human.selecionar(self.root, 'alpha', 'R001', 'r2', 'g2', [choice])
