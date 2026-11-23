"""itens_da_conta: what the account itself created, one function per module, for its own data export (E4b-2b).

Each gives ``[{tipo, caso, criado_em, id}]``, only in the cases passed, only what that account created, never a
title, a text or a name, without what is in the trash. Synthetic data, through the real writers of each module.
"""
from pathlib import Path
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import ler_json  # noqa: E402
from fixture_achados import Ambiente  # noqa: E402
import apuracao  # noqa: E402
import caderno  # noqa: E402
import codex_apuracao  # noqa: E402
import conferencia_redacao as redacao  # noqa: E402
import diligencias  # noqa: E402
import evidencias  # noqa: E402
import hipoteses  # noqa: E402
import lixeira  # noqa: E402
import revisao_humana as human  # noqa: E402
import test_caderno as notebook_fixture  # module imports: their TestCases are not re-collected here
import test_conferencia_redacao as conferencia_fixture
import test_custo_redacoes as redacoes
import test_diligencias as diligencias_fixture

CONTA = {'id': '0123456789abcdef', 'nome': 'Marina Sintética'}
OUTRA = {'id': 'fedcba9876543210', 'nome': 'Outra Pessoa Sintética'}
CHAVES = {'tipo', 'caso', 'criado_em', 'id'}


class Comum:
    def conferir_forma(self, itens, tipo):
        for item in itens:
            self.assertEqual(set(item), CHAVES)
            self.assertEqual((item['tipo'], item['caso']), (tipo, 'alpha'))
            self.assertIsInstance(item['criado_em'], str)
        self.assertNotIn(CONTA['nome'], str(itens))
        self.assertNotIn(OUTRA['nome'], str(itens))

    def conferir_entradas(self, funcao):
        for conta, casos in ((None, ['alpha']), ('convite-123', ['alpha']), (CONTA['id'], 'alpha'),
                             (CONTA['id'], ['../alpha'])):
            with self.subTest(conta=conta, casos=casos), self.assertRaises(ValueError):
                funcao(self.root, conta, casos)
        self.assertEqual(funcao(self.root, CONTA['id'], ['inexistente']), [])  # a case that does not exist
        self.assertEqual(funcao(self.root, CONTA['id'], []), [])


class NotasTest(Comum, unittest.TestCase):
    def setUp(self):
        self.fx, _ = Ambiente.copia_completa(); self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root

    def nota(self, conta, **data):
        return apuracao.executar(self.root, 'apuracao-nota-salvar', {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex,
                                                                     'titulo': 'Nota sintética', 'texto': 'Texto', **data},
                                 conta)['nota']

    def test_so_as_notas_que_a_conta_criou(self):
        minha = self.nota(CONTA)
        editada = self.nota(OUTRA, nota_id=minha['id'], revisao_nota=minha['revisao'], texto='Editada por outra')
        alheia = self.nota(OUTRA)
        self.nota(None)  # local, without an account
        itens = apuracao.itens_da_conta(self.root, CONTA['id'], ['alpha'])
        # edited by someone else, still created by this account
        self.assertEqual(itens, [{'tipo': 'nota', 'caso': 'alpha', 'criado_em': minha['criado_em_utc'], 'id': minha['id']}])
        self.conferir_forma(itens, 'nota')
        self.assertEqual([i['id'] for i in apuracao.itens_da_conta(self.root, OUTRA['id'], ['alpha'])], [alheia['id']])
        self.assertEqual(apuracao.itens_da_conta(self.root, CONTA['id'], []), [])  # only the cases passed
        apuracao.executar(self.root, 'apuracao-nota-excluir', {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex,
                                                               'nota_id': minha['id'], 'revisao_nota': editada['revisao']},
                          CONTA)
        self.assertEqual(apuracao.itens_da_conta(self.root, CONTA['id'], ['alpha']), [])  # deleted: out

    def test_apuracao_na_lixeira_fica_de_fora(self):
        self.nota(CONTA)
        lixeira.adicionar(self.root, 'caso', 'alpha', 'Alpha')
        self.assertEqual(apuracao.itens_da_conta(self.root, CONTA['id'], ['alpha']), [])

    def test_entradas_invalidas(self):
        self.conferir_entradas(apuracao.itens_da_conta)


class CadernoTest(Comum, unittest.TestCase):
    def setUp(self):
        self.fx = notebook_fixture.CadernoTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.root

    def test_so_os_registros_da_conta(self):
        meu = caderno.salvar(self.root, self.fx.request(), CONTA)['registro']
        caderno.salvar(self.root, self.fx.request(titulo='De outra pessoa'), OUTRA)
        caderno.salvar(self.root, self.fx.request(titulo='Declarado no modo local'))
        itens = caderno.itens_da_conta(self.root, CONTA['id'], ['alpha'])
        self.assertEqual(itens, [{'tipo': 'registro_caderno', 'caso': 'alpha', 'criado_em': meu['criado_em_utc'],
                                  'id': meu['id']}])
        self.conferir_forma(itens, 'registro_caderno')
        self.assertNotIn('HIPOTESE_JORNALISTA_X', str(itens))
        lixeira.adicionar(self.root, 'caso', 'alpha', 'Alpha')
        self.assertEqual(caderno.itens_da_conta(self.root, CONTA['id'], ['alpha']), [])

    def test_registro_ilegivel_levanta(self):
        meu = caderno.salvar(self.root, self.fx.request(), CONTA)['registro']
        (self.root / f'casos/alpha/caderno/registros/{meu["id"]}.json').write_bytes(b'{ilegivel')
        with self.assertRaises(ValueError):
            caderno.itens_da_conta(self.root, CONTA['id'], ['alpha'])

    def test_entradas_invalidas(self):
        self.conferir_entradas(caderno.itens_da_conta)


class RevisaoHumanaTest(Comum, unittest.TestCase):
    def setUp(self):
        self.fx, _ = Ambiente.copia_completa(quantidade=4); self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root

    def marcar(self, conta, estado, identifier='A001'):
        detail = human.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', identifier)
        item = detail['achado']
        return human.salvar(self.root, 'alpha', 'R001', 'r2', achado_id=identifier, achado_versao=item['versao'],
                            registros_sha256=detail['registros_sha256'], estado=estado,
                            observacao='Observação sintética.', anterior=item['revisao_humana']['evento_id'],
                            conta=conta)['revisao_humana']

    def test_so_as_marcas_da_conta_fora_da_lixeira(self):
        minha = self.marcar(CONTA, 'precisa_de_ajuste')
        self.marcar(OUTRA, 'sem_suporte_suficiente')
        itens = human.itens_da_conta(self.root, CONTA['id'], ['alpha'])
        self.assertEqual([i['id'] for i in itens], [minha['evento_id']])
        self.conferir_forma(itens, 'revisao')
        self.assertNotIn('Observação sintética', str(itens))
        self.assertEqual(len(human.itens_da_conta(self.root, OUTRA['id'], ['alpha'])), 1)
        lixeira.adicionar(self.root, 'rodada', 'alpha', 'R001', rodada='R001')
        self.assertEqual(human.itens_da_conta(self.root, CONTA['id'], ['alpha']), [])

    def test_rodada_de_uma_conversa_na_lixeira_fica_de_fora(self):
        self.marcar(CONTA, 'precisa_de_ajuste')
        lixeira.adicionar(self.root, 'conversa', 'alpha', 'Conversa', conversa=uuid.uuid4().hex, rodadas=['R001'])
        self.assertEqual(human.itens_da_conta(self.root, CONTA['id'], ['alpha']), [])

    def test_entradas_invalidas(self):
        self.conferir_entradas(human.itens_da_conta)


class ConferenciaRedacaoTest(conferencia_fixture.Fontes, Comum, unittest.TestCase):
    def setUp(self):
        env, (_, _, _, second) = Ambiente.copia_completa(); self.addCleanup(env.cleanup)
        self.preparar(env, second)

    def test_registro_criado_e_revisoes_da_conta(self):
        meu = redacao.criar(self.root, self.base(titulo='Texto sintético', texto='A fonte declara valor 12. A obra parou.'),
                            CONTA)
        revisto = self.revisar(meu, 0, decisao='sem_suporte_suficiente', conta=OUTRA)
        revisto = self.revisar(revisto, 1, decisao='sem_suporte_suficiente', conta=CONTA)
        alheio = redacao.criar(self.root, self.base(titulo='De outra', texto='A fonte declara valor 14.'), OUTRA)
        self.revisar(alheio, 0, decisao='sem_suporte_suficiente', conta=CONTA)
        self.criar('Sem conta: o valor foi pago.')
        itens = redacao.itens_da_conta(self.root, CONTA['id'], ['alpha'])
        self.conferir_forma([i for i in itens if i['tipo'] == 'conferencia'], 'conferencia')
        self.conferir_forma([i for i in itens if i['tipo'] == 'revisao_afirmacao'], 'revisao_afirmacao')
        self.assertEqual(sorted((i['tipo'], i['id']) for i in itens),
                         sorted([('conferencia', meu['id']), ('revisao_afirmacao', f"{meu['id']}:3"),
                                 ('revisao_afirmacao', f"{alheio['id']}:2")]))
        self.assertNotIn('valor 12', str(itens))
        self.assertEqual(sorted((i['tipo'], i['id']) for i in redacao.itens_da_conta(self.root, OUTRA['id'], ['alpha'])),
                         sorted([('conferencia', alheio['id']), ('revisao_afirmacao', f"{meu['id']}:2")]))

    def test_registro_divergente_levanta(self):
        with mock.patch.object(redacao, 'listar', return_value=[{'id': 'C' + 'a' * 32, 'divergente': True,
                                                                          'historico': [], 'estado': None}]):
            with self.assertRaises(ValueError):
                redacao.itens_da_conta(self.root, CONTA['id'], ['alpha'])

    def test_entradas_invalidas(self):
        self.conferir_entradas(redacao.itens_da_conta)


class DiligenciasTest(Comum, unittest.TestCase):
    def setUp(self):
        self.fx = diligencias_fixture.DiligenciasTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.root

    def test_criadas_e_respostas_da_conta_nunca_o_responsavel(self):
        minha = diligencias.salvar(self.root, self.fx.create(responsavel=OUTRA['nome']), 'criar', CONTA)
        alheia = diligencias.salvar(self.root, self.fx.create(acao='De outra pessoa', responsavel=CONTA['nome']),
                                    'criar', OUTRA)
        corpo, _ = self.fx.response(alheia)
        respondida = diligencias.salvar(self.root, corpo, 'responder', CONTA)
        diligencias.salvar(self.root, self.fx.update(minha), 'atualizar', OUTRA)  # an update is not an item
        diligencias.salvar(self.root, self.fx.create(acao='Sem conta'))
        itens = diligencias.itens_da_conta(self.root, CONTA['id'], ['alpha'])
        self.assertEqual(sorted((i['tipo'], i['id']) for i in itens),
                         sorted([('diligencia', minha['id']), ('resposta_diligencia', f"{alheia['id']}:2")]))
        self.conferir_forma([i for i in itens if i['tipo'] == 'diligencia'], 'diligencia')
        self.conferir_forma([i for i in itens if i['tipo'] == 'resposta_diligencia'], 'resposta_diligencia')
        self.assertEqual(respondida['historico'][1]['em_utc'],
                         next(i['criado_em'] for i in itens if i['tipo'] == 'resposta_diligencia'))
        self.assertNotIn('RESPOSTA_DILIGENCIA', str(itens))
        self.assertEqual([(i['tipo'], i['id']) for i in diligencias.itens_da_conta(self.root, OUTRA['id'], ['alpha'])],
                         [('diligencia', alheia['id'])])
        lixeira.adicionar(self.root, 'caso', 'alpha', 'Alpha')
        self.assertEqual(diligencias.itens_da_conta(self.root, CONTA['id'], ['alpha']), [])

    def test_entradas_invalidas(self):
        self.conferir_entradas(diligencias.itens_da_conta)


class QuadrosTest(Comum, unittest.TestCase):
    def setUp(self):
        self.fx, _ = Ambiente.copia_completa(); self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root

    def base(self, **fields):
        return {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Nome do cliente', **fields}

    def test_registros_que_a_conta_criou_nos_quadros(self):
        minha = hipoteses.salvar(self.root, self.base(enunciado='Hipótese sintética H'), conta=CONTA)
        alheia = hipoteses.salvar(self.root, self.base(enunciado='Hipótese de outra pessoa'), conta=OUTRA)
        hipoteses.salvar(self.root, self.base(id=alheia['id'], anterior_sha256=alheia['sha256'],
                                              enunciado='Editada pela conta'), 'atualizar', CONTA)  # still not hers
        hipoteses.salvar(self.root, self.base(enunciado='Sem conta'))
        itens = evidencias.itens_da_conta(self.root, CONTA['id'], ['alpha'])
        self.assertEqual(itens, [{'tipo': 'hipoteses', 'caso': 'alpha', 'criado_em': minha['historico'][0]['em_utc'],
                                  'id': minha['id']}])
        self.conferir_forma(itens, 'hipoteses')
        self.assertNotIn('Hipótese', str(itens))
        self.assertEqual([i['id'] for i in evidencias.itens_da_conta(self.root, OUTRA['id'], ['alpha'])], [alheia['id']])
        lixeira.adicionar(self.root, 'caso', 'alpha', 'Alpha')
        self.assertEqual(evidencias.itens_da_conta(self.root, CONTA['id'], ['alpha']), [])

    def test_todos_os_quadros_sem_a_conferencia_da_redacao(self):
        import importlib
        nomes = {v.nome for n in evidencias.QUADROS for v in vars(importlib.import_module(n)).values()
                 if isinstance(v, evidencias.Colecao)}
        self.assertEqual(nomes, {'perguntas', 'hipoteses', 'linha_do_tempo', 'entidades', 'relacoes', 'tabelas'})

    def test_registro_divergente_levanta(self):
        with mock.patch.object(hipoteses.COLECAO, 'listar', return_value=[{'id': 'H' + 'a' * 32, 'divergente': True,
                                                                           'historico': [], 'estado': None}]):
            with self.assertRaises(ValueError):
                evidencias.itens_da_conta(self.root, CONTA['id'], ['alpha'])

    def test_entradas_invalidas(self):
        self.conferir_entradas(evidencias.itens_da_conta)


class ConversasTest(redacoes.Redacoes, unittest.TestCase):
    """Through Conversas with the simulated provider: criada_por written once, at creation."""
    setUp = redacoes.PerguntaNaRedacaoTest.setUp
    pergunta = redacoes.PerguntaNaRedacaoTest.pergunta

    def test_criada_por_so_na_criacao_e_so_as_da_conta(self):
        identificador = self.manager.perguntar(self.pergunta(), conta=self.bia)['conversa']
        redacoes.esperar(lambda: self.manager.contexts[identificador]['meta'].get('turn_id'))
        self.manager.cancelar(identificador)
        redacoes.aguardar_fim(self.manager, identificador)
        meta = ler_json(self.root / f'conversas/{identificador}/conversa.json')
        self.assertEqual((meta['criada_por'], meta['conta']), (self.bia, self.bia))
        itens = codex_apuracao.itens_da_conta(self.root, self.bia, ['alpha'])
        self.assertEqual(itens, [{'tipo': 'conversa', 'caso': 'alpha', 'criado_em': meta['criada_em_utc'],
                                  'id': identificador}])
        self.assertNotIn('Pergunta técnica', str(itens))
        self.assertEqual(codex_apuracao.itens_da_conta(self.root, self.dona, ['alpha']), [])
        self.assertEqual(codex_apuracao.itens_da_conta(self.root, self.bia, ['outra']), [])  # only the cases passed
        lixeira.adicionar(self.root, 'conversa', 'alpha', 'Conversa', conversa=identificador)
        self.assertEqual(codex_apuracao.itens_da_conta(self.root, self.bia, ['alpha']), [])

    def test_sem_criada_por_a_antiga_fica_de_fora(self):
        identificador = self.manager.perguntar(self.pergunta(), conta=self.bia)['conversa']
        redacoes.esperar(lambda: self.manager.contexts[identificador]['meta'].get('turn_id'))
        self.manager.cancelar(identificador)
        redacoes.aguardar_fim(self.manager, identificador)
        caminho = self.root / f'conversas/{identificador}/conversa.json'
        meta = ler_json(caminho)
        self.assertIsNone(codex_apuracao.conversas_sem_criador(self.root, ['alpha']))  # all of them have it
        del meta['criada_por']  # as written before this change: meta['conta'] alone is never taken as the creator
        caminho.write_text(__import__('json').dumps(meta), encoding='utf-8')
        self.assertEqual(codex_apuracao.itens_da_conta(self.root, self.bia, ['alpha']), [])
        # The export says from when its conversations are complete: after the most recent one without a creator.
        self.assertEqual(codex_apuracao.conversas_sem_criador(self.root, ['alpha']), meta['criada_em_utc'])
        self.assertIsNone(codex_apuracao.conversas_sem_criador(self.root, ['outra']))  # only the cases passed
        with self.assertRaises(ValueError):
            codex_apuracao.conversas_sem_criador(self.root, 'alpha')
        lixeira.adicionar(self.root, 'conversa', 'alpha', 'Conversa', conversa=identificador)
        self.assertIsNone(codex_apuracao.conversas_sem_criador(self.root, ['alpha']))  # in the trash: not counted

    def test_conversa_ilegivel_levanta(self):
        pasta = self.root / f'conversas/{uuid.uuid4().hex}'
        pasta.mkdir(parents=True)
        (pasta / 'conversa.json').write_bytes(b'{ilegivel')
        with self.assertRaises(ValueError):
            codex_apuracao.itens_da_conta(self.root, self.bia, ['alpha'])


if __name__ == '__main__':
    unittest.main()
