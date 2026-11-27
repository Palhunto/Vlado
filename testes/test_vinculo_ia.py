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
from registros_achados import carregar, publicar
import caderno
import conferencia_redacao as redacao
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
        self.assertEqual(vinculo_ia.preenchimento(None), {'papel': 'suporte', 'suporte': 'nao_revisado', 'natureza': None,
                                                          'destino': None})

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

    def test_justificativa_vazia_diz_qual_evidencia(self):
        with self.assertRaises(ValueError) as caught:
            self.hipotese([self.link(self.ia()), {**self.link(self.ia('E002'), papel='contradicao'), 'justificativa': '  '}])
        self.assertEqual(erros.codigo_de(str(caught.exception)), ('vinculo_sem_justificativa', {'posicao': 2, 'evidencia': 'E002'}))
        with self.assertRaises(ValueError) as caught:
            self.hipotese([{**self.link(self.humana(), suporte='nao_revisado', natureza='declaracao_documental'), 'justificativa': ''}])
        self.assertEqual(erros.codigo_de(str(caught.exception)),
                         ('vinculo_sem_justificativa', {'posicao': 1, 'evidencia': self.nota['registro']['id']}))

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


def publicar_r3_com_e_id_compartilhada(env, contexto=False):
    """r3 over r2: A003 (retirado, não sustentado) also links E001, the support of A001 (incluído), and E004 has no
    link at all. The findings validator lets both through (B1 and R3 of the Coruja on adffc2e)."""
    data, manifest = carregar(env.root, 'alpha', 'R001', 'r2')
    r3 = env.sucessora(data, {'manifesto': manifest}, 'r3')
    r3['achados'].append({'id': 'A003', 'subquestao': 'Outra leitura?', 'versoes': [
        {'versao': 1, 'redacao': 'A fonte declara valor 12 como pago.', 'natureza': 'declaracao_documental',
         'limitacoes': 'Sintético.'}]})
    r3['vinculos'].append({'achado_id': 'A003', 'versao': 1, 'evidencia_id': 'E001', 'papel': 'suporte',
                           'justificativa': 'Mesma linha, outra afirmação.'})
    if contexto:  # R2 of the Coruja on 446bfc6: the same E-ID in two roles of the same finding
        r3['vinculos'].append({'achado_id': 'A001', 'versao': 2, 'evidencia_id': 'E001', 'papel': 'contexto',
                               'justificativa': 'A mesma linha dá o contexto.'})
    r3['revisoes_assistidas'].append({'achado_id': 'A003', 'versao': 1, 'suporte': 'nao_sustentado',
                                      'motivo': 'Pagamento não consta.', 'fontes_reabertas': ['E001'],
                                      'limitacoes': 'Revisão pela IA.', 'acao': 'retirar'})
    r3['destinos'].append({'achado_id': 'A003', 'versao': 1, 'destino': 'retirado', 'motivo': 'Não sustentado.',
                           'briefing': None, 'revisao_suporte': None})
    orphan = deepcopy(r3['evidencias'][0]); orphan['id'] = 'E004'; r3['evidencias'].append(orphan)
    r3['procedencia'].append({'etapa': 'busca', 'artefatos': [], 'ferramentas': ['fixture'], 'modelo_informado_ou_observado': None})
    env.relatorio(r3, 'saidas/04b_evidencias.md', 'evidencias', 'E004 · fonte sintética.', -1)
    env.relatorio(r3, 'saidas/05b_cruzamentos.md', 'cruzamentos', 'A003@v1 · redação sintética.', -1)
    r3['procedencia'].append({'etapa': 'sintese', 'artefatos': [], 'ferramentas': ['fixture'], 'modelo_informado_ou_observado': None})
    env.relatorio(r3, 'saidas/08b_briefing.md', 'briefing', 'Briefing sintético da terceira revisão.', -1)
    return publicar(env.root, 'alpha', 'R001', r3)['manifesto']['registros_sha256']


class EvidenciaEmDoisAchadosTest(unittest.TestCase):
    """B1, R1, R2 e R3 da Coruja sobre adffc2e."""

    setUp_base = VinculoIaTest.setUp
    link, hipotese = VinculoIaTest.link, VinculoIaTest.hipotese

    def setUp(self):
        self.setUp_base()
        self.r3 = publicar_r3_com_e_id_compartilhada(self.env)

    def ref(self, eid='E001'):
        return {'tipo': 'ia', 'caso_id': 'alpha', 'rodada': 'R001', 'revisao': 'r3', 'registros_sha256': self.r3,
                'evidencia_id': eid}

    def codigo(self, links):
        with self.assertRaises(ValueError) as caught:
            self.hipotese(links)
        return erros.codigo_de(str(caught.exception))[0]

    def test_seletor_da_a_cada_achado_os_valores_dele(self):
        found = rotas_evidencia.executar(self.root, 'evidencia-buscar', {'caso': 'alpha', 'origem': 'ia'})
        self.assertEqual(found['analise']['revisao'], 'r3')
        e001 = {r['achado']['id']: r for r in found['resultados'] if r['vinculo_sugerido']['referencia']['evidencia_id'] == 'E001'}
        self.assertEqual(set(e001), {'A001', 'A003'})
        retirado = e001['A003']
        self.assertEqual((retirado['revisao_ia']['achado_id'], retirado['revisao_ia']['suporte'], retirado['revisao_ia']['destino']),
                         ('A003', 'nao_sustentado', 'retirado'))
        self.assertEqual((retirado['vinculo_sugerido']['suporte'], retirado['vinculo_sugerido']['achado_id']),
                         ('nao_revisado', 'A003'))
        incluido = e001['A001']
        self.assertEqual((incluido['revisao_ia']['achado_id'], incluido['revisao_ia']['suporte'], incluido['vinculo_sugerido']['suporte']),
                         ('A001', 'sustentado', 'sustentado'))
        # What the picker suggests is saved as is, with the chosen finding's review and no mark.
        item = self.hipotese([retirado['vinculo_sugerido']])
        saved = item['estado']['evidencias'][0]
        self.assertEqual((saved['revisao_ia']['achado_id'], saved['revisao_ia']['destino']), ('A003', 'retirado'))
        self.assertNotIn('alteracoes', saved)
        self.assertNotIn('achado_id', saved)

    def test_ligar_e_id_de_dois_achados_pede_a_escolha(self):
        self.assertEqual(self.codigo([self.link(self.ref())]), 'vinculo_achado_ambiguo')
        self.assertEqual(self.codigo([{**self.link(self.ref()), 'achado_id': 'A002'}]), 'vinculo_achado_invalido')
        self.assertEqual(self.codigo([{**self.link(self.ref()), 'achado_id': 'X1'}]), 'vinculo_achado_invalido')
        self.assertEqual(self.codigo([{**self.link(self.humana()), 'achado_id': 'A001'}]), 'vinculo_achado_invalido')
        # Choosing A003 with the support the person picks: marked against A003's review, never A001's.
        item = self.hipotese([{**self.link(self.ref()), 'achado_id': 'A003'}])
        saved = item['estado']['evidencias'][0]
        self.assertEqual(saved['revisao_ia']['achado_id'], 'A003')
        self.assertEqual((saved['alteracoes']['suporte']['anterior'], saved['alteracoes']['suporte']['valor']),
                         ('nao_revisado', 'sustentado'))
        # Resent in the saved form (no choice needed: the link keeps its review), and re-chosen as A001.
        again = VinculoIaTest.atualizar(self, item, deepcopy(item['estado']['evidencias']))
        self.assertEqual(again['estado']['evidencias'][0]['revisao_ia']['achado_id'], 'A003')
        other = VinculoIaTest.atualizar(self, again, [{**deepcopy(again['estado']['evidencias'][0]), 'achado_id': 'A001'}])
        relinked = other['estado']['evidencias'][0]
        self.assertEqual((relinked['revisao_ia']['achado_id'], 'alteracoes' in relinked), ('A001', False))

    def test_e_id_sem_achado_e_recusada_ao_ligar(self):
        self.assertEqual(self.codigo([self.link(self.ref('E004'))]), 'evidencia_sem_achado')

    def test_rodada_na_lixeira_nao_alimenta_a_leitura(self):
        item = self.hipotese([{**self.link(self.ia('E001', 'r1'), papel='suporte', suporte='nao_revisado'), 'achado_id': 'A001'}])
        link = ev.conferir_vinculos(self.root, 'alpha', item['estado']['evidencias'])[0]
        self.assertIsNotNone(link['versao_nova'])
        with patch.object(vinculo_ia.lixeira, 'excluido', return_value=True):
            link = ev.conferir_vinculos(self.root, 'alpha', item['estado']['evidencias'])[0]
        self.assertEqual((link['estado'], link['destino_atual'], link['versao_nova'], link['conferencia_humana'],
                          link['suporte_so_da_ia']), ('indisponivel', None, None, None, False))
        self.assertEqual(link['revisao_ia']['achado_id'], 'A001')  # what was saved still comes back

    def test_busca_valida_cada_revisao_uma_vez_so(self):
        calls = []
        real = vinculo_ia.carregar

        def counted(*args, **kwargs):
            calls.append(args[1:4])
            return real(*args, **kwargs)
        with patch.object(vinculo_ia, 'carregar', counted), patch.object(ev, 'carregar', counted):
            rotas_evidencia.executar(self.root, 'evidencia-buscar', {'caso': 'alpha'})
        self.assertEqual(calls, [('alpha', 'R001', 'r3')])

    def test_a_escolha_do_achado_nao_viaja_dentro_do_vinculo(self):
        # R1 of the Coruja on 446bfc6: links built outside a board (the story claims) carry nothing extra.
        links = ev.vinculos(self.root, 'alpha', [{**self.link(self.ref()), 'achado_id': 'A003'}])
        self.assertEqual(set(links[0]), ev.CAMPOS_SALVOS)
        ev.validar_vinculo_salvo(links[0])
        # The claim panel of the story check sends what the picker suggests, with achado_id (the Coruja saw it fail).
        story = redacao.criar(self.root, {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Ana Lima',
                                          'titulo': 'Reportagem sintética', 'texto': 'A fonte declara valor 12. O valor foi pago.'})
        found = rotas_evidencia.executar(self.root, 'evidencia-buscar', {'caso': 'alpha', 'origem': 'ia'})
        picked = next(r['vinculo_sugerido'] for r in found['resultados'] if r['achado']['id'] == 'A003')
        linked = redacao.vincular(self.root, {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Ana Lima',
                                              'id': story['id'], 'anterior_sha256': story['sha256'],
                                              'afirmacao_id': story['estado']['afirmacoes'][0]['id'], 'evidencias': [picked]})
        self.assertEqual(set(linked['estado']['afirmacoes'][0]['evidencias'][0]), ev.CAMPOS_SALVOS)

    def test_ligar_a_versao_nova_e_voltar_ao_da_ia_com_o_preenchimento_nao_marcam_a_pessoa(self):
        # B1 of the Coruja on the forms (3c1b363): the fill the server sends is never a person's change.
        item = self.hipotese([{**self.link(self.ia('E001', 'r1'), suporte='nao_revisado'), 'achado_id': 'A001'}])
        read = ev.conferir_vinculos(self.root, 'alpha', item['estado']['evidencias'])[0]
        self.assertEqual(read['preenchimento_ia'], {'papel': 'suporte', 'suporte': 'nao_revisado',
                                                    'natureza': 'alegacao_atribuida', 'destino': None})
        new = read['versao_nova']
        self.assertEqual(new['preenchimento'], {'papel': 'suporte', 'suporte': 'sustentado',
                                                'natureza': 'alegacao_atribuida', 'destino': 'incluido'})
        fill = {k: new['preenchimento'][k] for k in ('papel', 'suporte', 'natureza')}
        moved = VinculoIaTest.atualizar(self, item, [{'referencia': new['referencia'], **fill, 'achado_id': new['achado_id'],
                                                       'justificativa': 'Versão nova.'}])
        self.assertNotIn('alteracoes', moved['estado']['evidencias'][0])
        # Two changes by people, then "Voltar ao da IA" with the fill (not the mark's "anterior").
        once = VinculoIaTest.atualizar(self, moved, [{**self.link(self.ref()), 'achado_id': 'A001', 'suporte': 'parcial'}])
        twice = VinculoIaTest.atualizar(self, once, [{**self.link(self.ref()), 'achado_id': 'A001', 'suporte': 'ilegivel'}])
        mark = twice['estado']['evidencias'][0]['alteracoes']['suporte']
        self.assertEqual((mark['anterior'], mark['valor']), ('parcial', 'ilegivel'))
        read = ev.conferir_vinculos(self.root, 'alpha', twice['estado']['evidencias'])[0]
        back = VinculoIaTest.atualizar(self, twice, [{**self.link(self.ref()), 'achado_id': 'A001',
                                                      'suporte': read['preenchimento_ia']['suporte']}])
        self.assertNotIn('alteracoes', back['estado']['evidencias'][0])

    def test_versao_nova_retirada_vem_com_o_preenchimento_nao_revisado(self):
        item = self.hipotese([{**self.link(self.ia('E001', 'r1'), suporte='nao_revisado'), 'achado_id': 'A001'}])
        retirada = {**vinculo_ia.revisao_ia(self.root, 'alpha', self.ref(), {}, 'A001'), 'destino': 'retirado'}
        with patch.object(vinculo_ia, '_valores', side_effect=lambda *a, **k: {**retirada, 'versao': 2}):
            new = ev.conferir_vinculos(self.root, 'alpha', item['estado']['evidencias'])[0]['versao_nova']
        self.assertEqual((new['revisao_ia']['suporte'], new['preenchimento']['suporte'], new['preenchimento']['destino']),
                         ('sustentado', 'nao_revisado', 'retirado'))

    ia, humana = VinculoIaTest.ia, VinculoIaTest.humana


class EvidenciaEmDoisPapeisTest(EvidenciaEmDoisAchadosTest):
    """R2 of the Coruja on 446bfc6: E001 is support and context of A001: one picker result per role."""

    def setUp(self):
        self.setUp_base()
        self.r3 = publicar_r3_com_e_id_compartilhada(self.env, contexto=True)

    test_seletor_da_a_cada_achado_os_valores_dele = None  # one result per role here: the test below covers it

    def test_seletor_da_a_cada_papel_a_revisao_dele(self):
        found = rotas_evidencia.executar(self.root, 'evidencia-buscar', {'caso': 'alpha', 'origem': 'ia'})
        e001 = [r for r in found['resultados'] if r['vinculo_sugerido']['referencia']['evidencia_id'] == 'E001'
                and r['achado']['id'] == 'A001']
        self.assertEqual(sorted((r['revisao_ia']['papel'], r['vinculo_sugerido']['papel'], r['vinculo_sugerido']['suporte'])
                                for r in e001),
                         [('contexto', 'contexto', 'nao_revisado'), ('suporte', 'suporte', 'sustentado')])
        item = self.hipotese([r['vinculo_sugerido'] for r in e001])
        self.assertEqual(sorted((x['papel'], x['revisao_ia']['papel'], 'alteracoes' in x) for x in item['estado']['evidencias']),
                         [('contexto', 'contexto', False), ('suporte', 'suporte', False)])


if __name__ == '__main__':
    unittest.main()
