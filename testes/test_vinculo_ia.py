"""Registro do vínculo (revisao_ia, alteracoes e os campos de leitura) e o seletor comum de evidência (Onda 4, P47).

Contrato em ``.maestro/equipe/CONTRATO_QUADROS_ONDA4.md``, seções 3 e 4. Dados sintéticos (``fixture_achados``):
A001 v2 sustentado e incluído na revisão r2, com E001 (suporte), E002 (contradição) e E003 (contexto); A002 é
pendência sem evidência. Sem modelo e sem rede.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente
import caderno
import erros
import evidencias as ev
import hipoteses
import linha_tempo
import revisao_humana
import rotas_evidencia
import seletor_evidencia
import vinculo_ia


class VinculoIaTest(unittest.TestCase):
    def setUp(self):
        self.env, (_, _, first, second) = Ambiente.copia_completa(); self.addCleanup(self.env.cleanup)
        self.root = self.env.root
        self.r1 = first['manifesto']['registros_sha256']
        self.r2 = second['manifesto']['registros_sha256']
        docs = caderno.documentos(self.root, 'alpha'); doc = docs['documentos'][0]
        self.nota = caderno.salvar(self.root, {
            'caso': 'alpha', 'origem_id': docs['origem_id'], 'documento_id': doc['documento_id'],
            'documento_sha256': doc['sha256'], 'pagina_pdf': None, 'localizador': 'Linha 2',
            'trecho': 'Outra versão declara valor 14.', 'titulo': 'Trecho de Ana Lima', 'anotacao': '',
            'autor': 'Ana Lima', 'tipo': 'trecho', 'transcricao_manual': False, 'requisicao_id': uuid.uuid4().hex})

    def ia(self, eid='E001', revisao='r2'):
        return {'tipo': 'ia', 'caso_id': 'alpha', 'rodada': 'R001', 'revisao': revisao,
                'registros_sha256': self.r2 if revisao == 'r2' else self.r1, 'evidencia_id': eid}

    def humana(self):
        return {'tipo': 'humana', 'caso_id': 'alpha', 'registro_id': self.nota['registro']['id'],
                'sha256': self.nota['sha256'], 'fonte': 0}

    def link(self, ref, papel='suporte', suporte='sustentado', natureza='alegacao_atribuida'):
        return {'referencia': ref, 'papel': papel, 'suporte': suporte, 'natureza': natureza,
                'justificativa': 'Vínculo sintético.'}

    def hipotese(self, links, autor='Ana Lima'):
        return hipoteses.salvar(self.root, {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': autor,
                                            'enunciado': 'A Construtora Alfa declarou valor 12.', 'evidencias': links})

    def atualizar(self, item, links, autor='Carlos Prado'):
        return hipoteses.salvar(self.root, {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': autor,
                                            'id': item['id'], 'anterior_sha256': item['sha256'], 'evidencias': links},
                                'atualizar')

    # --- registro ao ligar -------------------------------------------------------------------------

    def test_ao_ligar_guarda_os_valores_da_revisao_da_ia_e_sem_marca_quando_a_pessoa_nao_muda(self):
        item = self.hipotese([self.link(self.ia())])
        saved = item['estado']['evidencias'][0]
        self.assertEqual(saved['revisao_ia'], {
            'rodada': 'R001', 'revisao': 'r2', 'registros_sha256': self.r2, 'achado_id': 'A001', 'versao': 2,
            'papel': 'suporte', 'suporte': 'sustentado', 'natureza': 'alegacao_atribuida', 'destino': 'incluido'})
        self.assertNotIn('alteracoes', saved)
        self.assertEqual(set(saved['referencia']), ev.CAMPOS_REF['ia'])  # the reference keeps its shape

    def test_campo_mudado_guarda_quem_quando_e_o_anterior_e_voltar_ao_da_ia_apaga_a_marca(self):
        item = self.hipotese([self.link(self.ia(), suporte='parcial')])
        mark = item['estado']['evidencias'][0]['alteracoes']['suporte']
        self.assertEqual((mark['anterior'], mark['valor'], mark['por'], mark['conta_id']),
                         ('sustentado', 'parcial', 'Ana Lima', None))
        # Saved again unchanged, by someone else: the mark stays with who made it.
        again = self.atualizar(item, deepcopy(item['estado']['evidencias']))
        self.assertEqual(again['estado']['evidencias'][0]['alteracoes']['suporte'], mark)
        # Changed again: the previous value is the person's, the AI's stays in revisao_ia.
        natureza = self.atualizar(again, [self.link(self.ia(), suporte='parcial', natureza='inferencia')])
        changes = natureza['estado']['evidencias'][0]['alteracoes']
        self.assertEqual(changes['suporte'], mark)
        self.assertEqual((changes['natureza']['anterior'], changes['natureza']['valor'], changes['natureza']['por']),
                         ('alegacao_atribuida', 'inferencia', 'Carlos Prado'))
        back = self.atualizar(natureza, [self.link(self.ia())])
        self.assertNotIn('alteracoes', back['estado']['evidencias'][0])
        self.assertEqual(back['estado']['evidencias'][0]['revisao_ia']['suporte'], 'sustentado')

    def test_o_cliente_nao_escreve_revisao_ia_nem_alteracoes(self):
        item = self.hipotese([self.link(self.ia(), suporte='parcial')])
        forged = deepcopy(item['estado']['evidencias'])
        forged[0]['revisao_ia']['suporte'] = 'parcial'
        forged[0]['alteracoes']['suporte']['por'] = 'Outra pessoa'
        kept = self.atualizar(item, forged)['estado']['evidencias'][0]
        self.assertEqual(kept['revisao_ia'], item['estado']['evidencias'][0]['revisao_ia'])
        self.assertEqual(kept['alteracoes']['suporte']['por'], 'Ana Lima')
        with self.assertRaisesRegex(ValueError, 'Vínculo de evidência inválido'):  # input form with the record fields
            self.hipotese([{**self.link(self.ia()), 'revisao_ia': None}])

    def test_no_caderno_guarda_quem_escolheu_o_suporte_e_quando(self):
        item = self.hipotese([self.link(self.humana(), suporte='nao_revisado', natureza='declaracao_documental')])
        self.assertNotIn('alteracoes', item['estado']['evidencias'][0])
        self.assertNotIn('revisao_ia', item['estado']['evidencias'][0])
        chosen = self.atualizar(item, [self.link(self.humana(), suporte='sustentado', natureza='declaracao_documental')])
        mark = chosen['estado']['evidencias'][0]['alteracoes']
        self.assertEqual(set(mark), {'suporte'})
        self.assertEqual((mark['suporte']['anterior'], mark['suporte']['valor'], mark['suporte']['por']),
                         ('nao_revisado', 'sustentado', 'Carlos Prado'))

    def test_vinculo_antigo_volta_como_estava_sem_registro_e_sem_marca(self):
        with patch.object(vinculo_ia, 'COLECOES', ()):  # saved as before this wave
            item = self.hipotese([self.link(self.ia(), suporte='parcial'),
                                  self.link(self.humana(), suporte='sustentado', natureza='declaracao_documental')])
        self.assertTrue(all(set(x) == ev.CAMPOS_SALVOS for x in item['estado']['evidencias']))
        again = self.atualizar(item, deepcopy(item['estado']['evidencias']))
        self.assertTrue(all(set(x) == ev.CAMPOS_SALVOS for x in again['estado']['evidencias']))
        read = ev.conferir_vinculos(self.root, 'alpha', again['estado']['evidencias'])
        self.assertEqual([(x['revisao_ia'], x['alteracoes'], x['suporte_so_da_ia']) for x in read],
                         [(None, {}, False), (None, {}, False)])
        self.assertEqual(hipoteses.detalhe(self.root, 'alpha', item['id'])['estado'], again['estado'])

    def test_quadros_fora_da_lista_nao_ganham_registro(self):
        self.assertEqual(vinculo_ia.COLECOES, ('hipoteses', 'linha_do_tempo', 'entidades', 'relacoes'))
        event = linha_tempo.salvar(self.root, {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Ana Lima',
                                               'descricao': 'Declaração do valor 12.', 'evidencias': [self.link(self.ia())],
                                               'datas': [{'tipo': 'declarada_por_fonte', 'valor': '2025', 'fonte': 0}]})
        self.assertIn('revisao_ia', event['estado']['evidencias'][0])

    # --- preenchimento P47 -------------------------------------------------------------------------

    def test_preenchimento_da_p47(self):
        base = {'papel': 'suporte', 'suporte': 'sustentado', 'natureza': 'declaracao_documental', 'destino': 'incluido'}
        cases = [(base, 'sustentado'), ({**base, 'destino': 'fora_do_briefing'}, 'sustentado'),
                 ({**base, 'destino': 'retirado'}, 'nao_revisado'), ({**base, 'papel': 'contexto'}, 'nao_revisado'),
                 ({**base, 'natureza': 'pendencia'}, 'nao_revisado'), ({**base, 'suporte': 'parcial'}, 'parcial'),
                 ({**base, 'destino': None, 'suporte': 'nao_revisado'}, 'nao_revisado')]
        for review, expected in cases:
            with self.subTest(review=review):
                fill = vinculo_ia.preenchimento(review)
                self.assertEqual((fill['papel'], fill['suporte'], fill['natureza']),
                                 (review['papel'], expected, review['natureza']))
        self.assertEqual(vinculo_ia.preenchimento(None), {'papel': 'suporte', 'suporte': 'nao_revisado', 'natureza': None})

    def test_achado_retirado_ligado_com_sustentado_fica_como_escolha_da_pessoa(self):
        review = {**vinculo_ia.revisao_ia(self.root, 'alpha', self.ia(), {}), 'destino': 'retirado'}
        with patch.object(vinculo_ia, 'revisao_ia', return_value=review):
            item = self.hipotese([self.link(self.ia())])
        mark = item['estado']['evidencias'][0]['alteracoes']['suporte']
        self.assertEqual((mark['anterior'], mark['valor']), ('nao_revisado', 'sustentado'))

    # --- leitura ------------------------------------------------------------------------------------

    def test_leitura_traz_suporte_so_da_ia_destino_atual_versao_nova_e_conferencia_humana(self):
        item = self.hipotese([self.link(self.ia()), self.link(self.ia('E001', 'r1'), papel='contexto',
                                                                 suporte='nao_revisado', natureza='alegacao_atribuida')])
        current, old = ev.conferir_vinculos(self.root, 'alpha', item['estado']['evidencias'])
        self.assertEqual((current['estado'], current['suporte_so_da_ia'], current['destino_atual'], current['versao_nova']),
                         ('conferida', True, 'incluido', None))
        self.assertIsNone(current['conferencia_humana'])
        # Linked from r1 (A001 v1, before the review): the newest version is v2 in r2.
        self.assertEqual(old['revisao_ia']['versao'], 1)
        self.assertEqual(old['versao_nova']['referencia'], self.ia())
        self.assertEqual((old['versao_nova']['versao'], old['versao_nova']['revisao_ia']['suporte']), (2, 'sustentado'))
        revisao_humana.salvar(self.root, 'alpha', 'R001', 'r2', achado_id='A001', achado_versao=2,
                              registros_sha256=self.r2, estado='precisa_de_ajuste')
        current = ev.conferir_vinculos(self.root, 'alpha', item['estado']['evidencias'])[0]
        self.assertEqual(current['conferencia_humana']['estado'], 'precisa_de_ajuste')
        self.assertTrue(current['suporte_so_da_ia'])
        changed = self.atualizar(item, [self.link(self.ia(), suporte='parcial')])
        self.assertFalse(ev.conferir_vinculos(self.root, 'alpha', changed['estado']['evidencias'])[0]['suporte_so_da_ia'])

    # --- códigos das regras do modelo -----------------------------------------------------------

    def test_regras_do_modelo_tem_codigo_proprio(self):
        cases = [([self.link(self.ia('E003'), papel='contexto', suporte='parcial')], 'vinculo_contexto_com_suporte'),
                 ([self.link(self.ia(), suporte='sustentado', natureza='pendencia')], 'vinculo_pendencia_sustentada'),
                 ([self.link(self.ia())] * 101, 'vinculos_demais')]
        for links, code in cases:
            with self.subTest(code=code), self.assertRaises(ValueError) as caught:
                self.hipotese(links)
            self.assertEqual(erros.codigo_de(str(caught.exception))[0], code)
        self.assertEqual(erros.codigo_de(str(caught.exception))[1], {'maximo': 100})
        with self.assertRaisesRegex(ValueError, '^Vincule de 1 a 100'):  # too few keeps its message
            linha_tempo.salvar(self.root, {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Ana Lima',
                                           'descricao': 'Sem fonte.', 'evidencias': [],
                                           'datas': [{'tipo': 'fato', 'valor': '2025', 'fonte': 0}]})

    # --- seletor -----------------------------------------------------------------------------------

    def buscar(self, **data):
        return rotas_evidencia.executar(self.root, 'evidencia-buscar', {'caso': 'alpha', **data})

    def test_seletor_busca_nos_achados_e_no_caderno_com_o_vinculo_preenchido(self):
        found = self.buscar()
        self.assertEqual((found['analise']['rodada'], found['analise']['revisao'], found['analise']['com_revisao']),
                         ('R001', 'r2', True))
        self.assertEqual([a['rodada'] for a in found['analises']], ['R001'])
        ia = [r for r in found['resultados'] if r['origem'] == 'ia']
        self.assertEqual([r['vinculo_sugerido']['referencia']['evidencia_id'] for r in ia], ['E001', 'E002', 'E003'])
        self.assertTrue(all(r['achado'] == {'id': 'A001', 'versao': 2, 'destino': 'incluido'} for r in ia))
        self.assertEqual([(r['vinculo_sugerido']['papel'], r['vinculo_sugerido']['suporte']) for r in ia],
                         [('suporte', 'sustentado'), ('contradicao', 'sustentado'), ('contexto', 'nao_revisado')])
        self.assertEqual(ia[0]['vinculo_sugerido']['justificativa'], 'Relação sintética atribuída.')
        self.assertEqual(ia[0]['localizador']['linha_inicio'], 1)
        note = [r for r in found['resultados'] if r['origem'] == 'caderno']
        self.assertEqual(len(note), 1)
        self.assertEqual((note[0]['tipo_fonte'], note[0]['conferencia_humana'], note[0]['conferencia_textual'],
                          note[0]['vinculo_sugerido']['natureza'], note[0]['vinculo_sugerido']['suporte']),
                         ('trecho', None, 'literal_localizado', None, 'nao_revisado'))
        self.assertEqual(note[0]['vinculo_sugerido']['referencia'], self.humana())
        # The suggested link is accepted as is by the boards (the notebook one once the person picks the nature).
        chosen = [r['vinculo_sugerido'] for r in ia] + [{**note[0]['vinculo_sugerido'], 'natureza': 'declaracao_documental',
                                                         'justificativa': 'Escolhido por Ana Lima.'}]
        item = self.hipotese(chosen)
        self.assertTrue(all('alteracoes' not in x for x in item['estado']['evidencias']))
        linked = self.buscar(item={'quadro': 'hipoteses', 'id': item['id']})
        self.assertTrue(all(r['ja_ligado'] for r in linked['resultados']))

    def test_seletor_filtra_por_texto_sem_acento_e_por_origem(self):
        self.assertEqual([r['texto'] for r in self.buscar(texto='versao', origem='caderno')['resultados']],
                         ['Trecho de Ana Lima'])
        ia = self.buscar(texto='14', origem='ia')['resultados']
        self.assertEqual([r['vinculo_sugerido']['referencia']['evidencia_id'] for r in ia], ['E002'])
        self.assertEqual(self.buscar(texto='Marta')['total'], 0)
        page = self.buscar(limite=2)
        self.assertEqual((len(page['resultados']), page['total'], page['proximo_deslocamento']), (2, 4, 2))
        self.assertEqual(self.buscar(limite=2, deslocamento=2)['proximo_deslocamento'], None)

    def test_seletor_recusa_com_codigo(self):
        cases = [({'texto': 'M'}, 'busca_curta'), ({'item': {'quadro': 'hipoteses', 'id': 'H' + 'e' * 32}}, 'item_selecionado_invalido'),
                 ({'item': {'quadro': 'tabelas', 'id': 'Q' + 'e' * 32}}, 'item_selecionado_invalido'),
                 ({'rodada': 'R999'}, 'rodada_sem_achados'), ({'rodada': '../R001'}, 'rodada_sem_achados'),
                 ({'origem': 'web'}, 'quadro_campos_invalidos'), ({'limite': 51}, 'quadro_campos_invalidos'),
                 ({'outro': 1}, 'quadro_campos_invalidos')]
        for data, code in cases:
            with self.subTest(data=data), self.assertRaises(ValueError) as caught:
                self.buscar(**data)
            self.assertEqual(erros.codigo_de(str(caught.exception))[0], code)

    def test_seletor_sem_achados_nem_caderno_devolve_vazio(self):
        self.env.caso('beta')
        found = rotas_evidencia.executar(self.root, 'evidencia-buscar', {'caso': 'beta'})
        self.assertEqual((found['analise'], found['analises'], found['resultados'], found['total']), (None, [], [], 0))
        self.assertEqual(seletor_evidencia.ORIGENS, ('tudo', 'ia', 'caderno'))


if __name__ == '__main__':
    unittest.main()
