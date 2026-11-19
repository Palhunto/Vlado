"""Autoria pela conta autenticada da Mesa e espaço de escrita do Caderno (apuracao por nota)."""
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_caderno as notebook_fixture
from fixture_achados import Ambiente
import apuracao
import caderno
import diligencias
import exportar_apuracao
import revisao_humana as human
from indice_sqlite import pesquisar

CONTA = {'id': 'convite-123', 'nome': 'Marina Autenticada'}
OUTRA = {'id': 'convite-999', 'nome': 'Outra Pessoa'}
FALSO = 'Nome Falsificado Pelo Cliente'


class AutoriaCadernoDiligenciasTest(unittest.TestCase):
    def setUp(self):
        self.fx = notebook_fixture.CadernoTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.root

    def test_caderno_com_conta_ignora_autor_do_cliente_e_marca_origem(self):
        saved = caderno.salvar(self.root, self.fx.request(autor=FALSO), CONTA)
        entry = saved['registro']
        self.assertEqual(entry['autor'], CONTA['nome'])
        self.assertEqual(entry['conta_id'], CONTA['id'])
        self.assertEqual(entry['origem_autoria'], caderno.AUTORIA_CONTA)
        self.assertNotIn(FALSO, str(entry))
        again = caderno.detalhe(self.root, 'alpha', entry['id'])['registro']
        self.assertEqual(again['autor'], CONTA['nome'])
        self.assertEqual(caderno.listar(self.root, 'alpha')['total'], 1)

    def test_caderno_com_conta_nao_exige_autor_e_sem_conta_continua_declarado(self):
        body = self.fx.request(); body.pop('autor')
        self.assertEqual(caderno.salvar(self.root, body, CONTA)['registro']['autor'], CONTA['nome'])
        with self.assertRaises(ValueError):
            caderno.salvar(self.root, {**body, 'requisicao_id': uuid.uuid4().hex})
        declared = caderno.salvar(self.root, self.fx.request(autor='Repórter local'))['registro']
        self.assertEqual(declared['origem_autoria'], 'humana_declarada_na_interface')
        self.assertNotIn('conta_id', declared)

    def test_caderno_idempotencia_amarrada_a_conta_e_conta_invalida(self):
        body = self.fx.request()
        first = caderno.salvar(self.root, body, CONTA)
        self.assertEqual(caderno.salvar(self.root, body, CONTA)['sha256'], first['sha256'])
        with self.assertRaisesRegex(ValueError, 'tentativa de salvamento'):
            caderno.salvar(self.root, body, OUTRA)
        for bad in ({'id': 'x'}, {'nome': 'x'}, {'id': '', 'nome': 'x'}, 'texto', {'id': 'x', 'nome': ''}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                caderno.salvar(self.root, self.fx.request(), bad)

    def test_cruzamento_com_conta_registra_autoria_autenticada(self):
        one = caderno.salvar(self.root, self.fx.request(), CONTA)
        two = caderno.salvar(self.root, self.fx.request(autor='Repórter local'))
        cross = caderno.cruzar(self.root, {'caso': 'alpha', 'selecoes': [self.fx.choice(one), self.fx.choice(two)],
            'titulo': 'Cruzamento', 'anotacao': 'Conferir.', 'autor': FALSO, 'requisicao_id': uuid.uuid4().hex}, OUTRA)
        entry = cross['registro']
        self.assertEqual((entry['autor'], entry['conta_id'], entry['origem_autoria']),
                         (OUTRA['nome'], OUTRA['id'], caderno.AUTORIA_CONTA))
        self.assertEqual([p['autor'] for p in entry['vinculos']], [CONTA['nome'], 'Repórter local'])

    def create(self, **changes):
        note = caderno.salvar(self.root, self.fx.request())
        return {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': FALSO,
                'origem': {'tipo': 'humana', **self.fx.choice(note)}, 'acao': 'Pedir contrato',
                'responsavel': 'Repórter B', 'prazo': None, 'observacao': 'Pendência.', **changes}

    def test_diligencia_com_conta_registra_autor_no_evento_e_ignora_cliente(self):
        item = diligencias.salvar(self.root, self.create(), 'criar', CONTA)
        event = item['historico'][0]
        self.assertEqual((event['autor'], event['conta_id'], event['origem_autoria']),
                         (CONTA['nome'], CONTA['id'], caderno.AUTORIA_CONTA))
        self.assertEqual(item['diligencia']['origem_autoria'], caderno.AUTORIA_CONTA)
        self.assertNotIn(FALSO, str(item))
        update = {'caso': 'alpha', 'diligencia_id': item['id'], 'anterior_sha256': item['sha256'],
                  'requisicao_id': uuid.uuid4().hex, 'autor': FALSO, 'acao': 'Pedir contrato',
                  'responsavel': 'Repórter B', 'prazo': None, 'estado': 'em_andamento', 'observacao': 'Andamento.'}
        updated = diligencias.salvar(self.root, update, 'atualizar', OUTRA)
        self.assertEqual(updated['historico'][1]['autor'], OUTRA['nome'])
        self.assertEqual(updated['historico'][0]['autor'], CONTA['nome'])
        self.assertEqual(diligencias.listar(self.root, 'alpha')['total'], 1)

    def test_diligencia_sem_conta_mantem_autoria_declarada(self):
        item = diligencias.salvar(self.root, self.create(autor='Editora A'))
        self.assertEqual(item['historico'][0]['autor'], 'Editora A')
        self.assertEqual(item['historico'][0]['origem_autoria'], 'humana_declarada_na_interface')
        self.assertNotIn('conta_id', item['historico'][0])
        with self.assertRaises(ValueError):
            diligencias.salvar(self.root, self.create(autor=''))
        body = self.create(autor='Editora A')
        diligencias.salvar(self.root, body, 'criar', CONTA)
        with self.assertRaisesRegex(ValueError, 'tentativa'):
            diligencias.salvar(self.root, body, 'criar', OUTRA)


class AutoriaRevisaoHumanaTest(unittest.TestCase):
    def setUp(self):
        self.fx, _ = Ambiente.copia_completa(quantidade=4); self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root

    def save(self, identifier='A001', **kwargs):
        detail = human.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', identifier)
        item = detail['achado']
        values = dict(achado_id=identifier, achado_versao=item['versao'], registros_sha256=detail['registros_sha256'],
                      estado='precisa_de_ajuste', observacao='Ajustar valor.',
                      anterior=item['revisao_humana']['evento_id'])
        return human.salvar(self.root, 'alpha', 'R001', 'r2', **{**values, **kwargs})

    def test_revisao_com_conta_registra_responsavel_autenticado(self):
        result = self.save(conta=CONTA)
        mark = result['revisao_humana']
        self.assertEqual((mark['responsavel'], mark['origem']), (CONTA['nome'], human.ORIGEM_CONTA))
        self.assertEqual(mark['historico'][0]['conta_id'], CONTA['id'])
        again = human.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', 'A001')['achado']['revisao_humana']
        self.assertEqual(again['responsavel'], CONTA['nome'])
        # Nova marcação por outra conta: histórico preserva quem fez cada uma.
        second = self.save(estado='conferida_no_original', observacao='Conferido.', conta=OUTRA)['revisao_humana']
        self.assertEqual([e['responsavel'] for e in second['historico']], [CONTA['nome'], OUTRA['nome']])

    def test_revisao_sem_conta_continua_declaracao_do_usuario(self):
        mark = self.save()['revisao_humana']
        self.assertEqual(mark['origem'], 'declaracao_do_usuario_na_interface')
        self.assertIsNone(mark['responsavel'])
        self.assertNotIn('conta_id', mark['historico'][0])

    def test_conta_invalida_e_recusada_sem_gravar(self):
        with self.assertRaises(ValueError):
            self.save(conta={'id': 'x'})
        self.assertEqual(human.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', 'A001')['achado']['revisao_humana']['estado'], 'pendente')


class ApuracaoNotasTest(unittest.TestCase):
    def setUp(self):
        self.fx, _ = Ambiente.copia_completa(); self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root

    def op(self, operation, conta=None, **data):
        return apuracao.executar(self.root, operation, {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, **data}, conta)

    def origin(self, **changes):
        hit = pesquisar(self.root, 'alpha', 'R001', 'declara')['resultados'][0]
        return {'tipo': 'pesquisa', 'rodada': 'R001', 'geracao': 'v1', 'referencia': hit['referencia'],
                'texto': 'valor 12.', **changes}

    def test_nota_com_conta_registra_autoria_e_ignora_autor_do_cliente(self):
        result = self.op('apuracao-nota-salvar', CONTA, titulo='Minha nota', texto='Texto', autor=FALSO)
        note = result['nota']
        self.assertEqual(result['estado'], 'salvo')
        self.assertEqual(note['criado_por']['nome'], CONTA['nome'])
        self.assertEqual(note['criado_por']['origem'], apuracao.AUTORIA_CONTA)
        self.assertEqual(note['atualizado_por']['conta_id'], CONTA['id'])
        self.assertNotIn(FALSO, str(apuracao.listar(self.root, 'alpha')))
        edited = self.op('apuracao-nota-salvar', OUTRA, nota_id=note['id'], revisao_nota=note['revisao'],
                         titulo='Minha nota', texto='Texto 2')['nota']
        self.assertEqual((edited['criado_por']['nome'], edited['atualizado_por']['nome']), (CONTA['nome'], OUTRA['nome']))
        self.assertIn(OUTRA['nome'], exportar_apuracao.markdown(apuracao.listar(self.root, 'alpha')))

    def test_alterar_legado_sem_conta_nao_acrescenta_autoria_e_com_conta_registra(self):
        state = apuracao.alterar(self.root, 'apuracao-salvar', {'caso': 'alpha', 'revisao': 0,
            'requisicao_id': uuid.uuid4().hex, 'titulo': 'Local', 'texto': 'x'})
        self.assertNotIn('criado_por', state['notas'][0])
        state = apuracao.alterar(self.root, 'apuracao-salvar', {'caso': 'alpha', 'revisao': 1,
            'requisicao_id': uuid.uuid4().hex, 'titulo': 'Hospedada', 'texto': 'y'}, CONTA)
        self.assertEqual(state['notas'][1]['criado_por']['nome'], CONTA['nome'])

    def test_conflito_de_revisao_por_nota_nao_sobrescreve(self):
        note = self.op('apuracao-nota-salvar', titulo='N', texto='base')['nota']
        self.assertEqual(note['revisao'], 1)
        saved = self.op('apuracao-nota-salvar', nota_id=note['id'], revisao_nota=1, titulo='N', texto='aba A')['nota']
        self.assertEqual(saved['revisao'], 2)
        with self.assertRaises(apuracao.ConflitoNota) as ctx:
            self.op('apuracao-nota-salvar', nota_id=note['id'], revisao_nota=1, titulo='N', texto='aba B')
        self.assertIn('alterada em outra aba', str(ctx.exception))
        self.assertEqual(ctx.exception.atual['revisao'], 2)
        self.assertEqual(apuracao.listar(self.root, 'alpha')['notas'][0]['texto'], 'aba A')
        for bad in (None, '2', True):
            with self.subTest(bad=bad), self.assertRaises(apuracao.ConflitoNota):
                self.op('apuracao-nota-salvar', nota_id=note['id'], revisao_nota=bad, titulo='N', texto='z')

    def test_outra_nota_nao_gera_conflito_e_reenvio_e_idempotente(self):
        a = self.op('apuracao-nota-salvar', titulo='A', texto='a')['nota']
        body = {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'titulo': 'B', 'texto': 'b'}
        b = apuracao.alterar_nota(self.root, 'apuracao-salvar', body)
        again = apuracao.alterar_nota(self.root, 'apuracao-salvar', body)
        self.assertEqual((again['estado'], again['nota_id']), ('ja_registrado', b['nota_id']))
        ok = self.op('apuracao-nota-salvar', nota_id=a['id'], revisao_nota=a['revisao'], titulo='A', texto='a2')
        self.assertEqual(ok['nota']['texto'], 'a2')
        self.assertEqual(len(apuracao.listar(self.root, 'alpha')['notas']), 2)
        with self.assertRaisesRegex(ValueError, 'outro conteúdo'):
            apuracao.alterar_nota(self.root, 'apuracao-salvar', {**body, 'texto': 'diferente'})
        with self.assertRaisesRegex(ValueError, 'outro conteúdo'):
            apuracao.alterar_nota(self.root, 'apuracao-salvar', body, CONTA)

    def test_excluir_exige_revisao_da_nota(self):
        note = self.op('apuracao-nota-salvar', titulo='N', texto='x')['nota']
        self.op('apuracao-nota-salvar', nota_id=note['id'], revisao_nota=1, titulo='N', texto='y')
        with self.assertRaises(apuracao.ConflitoNota):
            self.op('apuracao-nota-excluir', nota_id=note['id'], revisao_nota=1)
        result = self.op('apuracao-nota-excluir', nota_id=note['id'], revisao_nota=2)
        self.assertIsNone(result['nota'])
        self.assertEqual(apuracao.listar(self.root, 'alpha')['notas'], [])

    def test_lista_leve_e_nota_com_fontes_resolvidas(self):
        note = self.op('apuracao-nota-salvar', CONTA, titulo='Com fontes', texto='Hipótese.')['nota']
        inserted = self.op('apuracao-nota-inserir', CONTA, nota_id=note['id'], revisao_nota=1, origem=self.origin())['nota']
        self.assertEqual((inserted['revisao'], len(inserted['fontes'])), (2, 1))
        self.assertIn('[Fonte 1]', inserted['texto'])
        self.op('apuracao-nota-salvar', titulo='Outra', texto='vazia')
        listing = self.op('apuracao-notas')
        self.assertEqual({n['titulo'] for n in listing['notas']}, {'Com fontes', 'Outra'})
        row = next(n for n in listing['notas'] if n['titulo'] == 'Com fontes')
        self.assertEqual((row['fontes'], row['revisao'], row['autor']), (1, 2, CONTA['nome']))
        self.assertTrue(row['atualizado_em_utc'])
        self.assertNotIn('texto', row)
        self.assertNotIn('documentos', str(listing))
        full = self.op('apuracao-nota', nota_id=note['id'])
        self.assertEqual(full['nota']['revisao'], 2)
        source = full['fontes'][0]
        self.assertEqual((source['numero'], source['marcador'], source['rodada']), (1, '[Fonte 1]', 'R001'))
        self.assertEqual(source['texto_selecionado'], 'valor 12.')
        self.assertEqual(source['adicionada_por'], CONTA['nome'])
        doc = source['documentos'][0]
        self.assertEqual((doc['documento_id'], doc['indice']), ('D001', 0))
        self.assertTrue(doc['disponivel'])
        self.assertEqual(doc['abrir'], {'operacao': 'apuracao-original', 'caso': 'alpha', 'nota_id': note['id'],
                                         'fonte_id': source['id'], 'documento_indice': 0})
        opened = apuracao.original(self.root, {k: v for k, v in doc['abrir'].items() if k != 'operacao'})
        self.assertTrue(opened.is_file())

    def test_fonte_ia_traz_pagina_pdf(self):
        note = self.op('apuracao-nota-salvar', titulo='IA', texto='t')['nota']
        self.op('apuracao-nota-inserir', nota_id=note['id'], revisao_nota=1, origem={
            'tipo': 'ia', 'rodada': 'R001', 'revisao': 'r2', 'geracao_achados': 'g2', 'achado_id': 'A001',
            'achado_versao': 2, 'texto': 'A fonte declara'})
        source = self.op('apuracao-nota', nota_id=note['id'])['fontes'][0]
        self.assertEqual(source['tipo'], 'ia')
        self.assertTrue(any(d['pagina_pdf'] == 1 for d in source['documentos']))

    def test_inserir_trecho_cria_nota_nova_e_nota_inexistente_falha(self):
        created = self.op('apuracao-nota-inserir', CONTA, origem=self.origin())
        self.assertEqual(created['nota']['revisao'], 1)
        self.assertEqual(created['nota']['criado_por']['nome'], CONTA['nome'])
        with self.assertRaises(ValueError):
            self.op('apuracao-nota', nota_id='Einexistente')
        with self.assertRaises(ValueError):
            self.op('apuracao-desconhecida')


if __name__ == '__main__':
    unittest.main()
