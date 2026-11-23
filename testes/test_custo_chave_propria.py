"""A chave de IA da redação na chamada (Onda 2, P3; contrato de contas, 8.5), só com provedor simulado.

Cobre: a chamada ao provedor usa a chave própria da redação de quem pergunta quando ela existe, e a do serviço
quando não existe ou sem redação; cada chamada diz qual chave pagou (``chavePropria``); com a chave própria o
gasto cai na pessoa e num lançamento separado da redação (``chaves_proprias``), fora da cota paga pelo serviço e
da soma da instalação; com ela só o teto da pessoa vale. Chaves sintéticas; nenhuma chamada real.
"""
from decimal import Decimal
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
sys.path.insert(0, str(TESTES))
import acesso  # noqa: E402
from comum import escrever_json, ler_json  # noqa: E402
import cenario_redacoes as cenario  # noqa: E402
import custo  # noqa: E402
import limites  # noqa: E402
import erros  # noqa: E402
import inferencia_api  # noqa: E402
from inferencia_api import ErroIA, Resposta, ServidorAPI  # noqa: E402
import segredos  # noqa: E402
import test_custo_redacoes as redacoes  # noqa: E402
import test_inferencia_api as base_inferencia  # noqa: E402

SONNET = 'claude-sonnet-5-5'
PROPRIA = 'sk-ant-chave-propria-sintetica-da-redacao'
A, B = 'org' + 'a' * 16, 'org' + 'b' * 16


class ComChaves(base_inferencia.Base):
    """ServidorAPI with the service's key and the own key of newsroom A; records the keys the provider got."""

    def setUp(self):
        self.chaves = []
        super().setUp()
        segredos.salvar_chave(self.root, 'anthropic', PROPRIA, A)

    def novo_servidor(self):
        def criar(inferencia, chave):
            self.chaves.append(chave)
            return self.provedor
        servidor = ServidorAPI(self.root, self.mensagens.put, criar_provedor=criar)
        self.addCleanup(servidor.close)
        return servidor

    def perguntar(self, redacao):
        self.provedor.roteiro = [Resposta('Resposta sintética.', (), {'entrada': 10, 'saida': 4}, 'modelo-sintetico')]
        thread = self.iniciar_thread()
        params = {'threadId': thread, 'input': [{'type': 'text', 'text': 'Pergunta sintética.'}]}
        if redacao:
            params['redacao'] = redacao
        self.servidor.call('turn/start', params)
        uso = self.proxima('item/usage')['params']
        self.proxima('turn/completed')
        return self.chaves[-1], uso['chavePropria']


class ChaveNaChamadaTest(ComChaves):
    """Which key reaches the provider, and which the usage event says paid."""

    def test_a_redacao_com_chave_propria_paga_com_ela(self):
        self.assertEqual(self.perguntar(A), (PROPRIA, True))

    def test_sem_chave_propria_ou_sem_redacao_paga_o_servico(self):
        self.assertEqual(self.perguntar(B), ('sk-ant-sintetica', False))
        self.assertEqual(self.perguntar(None), ('sk-ant-sintetica', False))

    def test_so_com_a_chave_propria_a_conta_autentica_para_aquela_redacao(self):
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': ''}):
            self.assertEqual(self.servidor.call('account/read', {'redacao': A})['account']['chave_propria'], True)
            self.assertIsNone(self.servidor.call('account/read', {'redacao': B})['account'])
            self.assertIsNone(self.servidor.call('account/read', {})['account'])
        self.assertFalse(self.servidor.call('account/read', {'redacao': B})['account']['chave_propria'])


class ChavesIlegiveisTest(ComChaves):
    """C3: the newsrooms' keys file unreadable refuses only the question, and no other key stands in."""

    def estragar(self):
        segredos.caminho_das_redacoes(self.root).write_text('{ilegível', encoding='utf-8')

    def test_recusa_a_pergunta_sem_cair_na_chave_do_servico(self):
        self.estragar()
        with self.assertRaises(ErroIA) as recusa:
            self.servidor.call('account/read', {'redacao': A})
        self.assertEqual((str(recusa.exception), recusa.exception.codigo),
                         (inferencia_api.CHAVE_REDACAO_ILEGIVEL, 'chave_redacao_ilegivel'))
        self.assertEqual(erros.codigo_de(str(recusa.exception))[0], 'chave_redacao_ilegivel')
        self.provedor.roteiro = [Resposta('Não deveria responder.', (), {}, 'modelo-sintetico')]
        thread = self.iniciar_thread()
        self.servidor.call('turn/start', {'threadId': thread, 'redacao': A,
                                          'input': [{'type': 'text', 'text': 'Pergunta sintética.'}]})
        fim = self.proxima('turn/completed')['params']['turn']
        self.assertEqual((fim['status'], fim['error']['codexErrorInfo']), ('failed', 'chave_redacao_ilegivel'))
        self.assertEqual(self.chaves, [])  # the provider was never created: no key at all, not the service's
        self.assertEqual(self.provedor.chamadas, [])

    def test_sem_redacao_a_chave_do_servico_segue(self):
        self.estragar()  # the service's key never reads the newsrooms' file
        self.assertEqual(self.perguntar(None), ('sk-ant-sintetica', False))


class LancamentoSeparadoTest(redacoes.Redacoes, unittest.TestCase):
    setUp = redacoes.CotaPorRedacaoTest.setUp

    def gastar(self, conta, reais, chave_propria=False):
        return custo.somar_gasto(self.root, conta, int(Decimal(str(reais)) * custo.MICRO), chave_propria=chave_propria)

    def test_chave_propria_cai_na_pessoa_e_fora_da_cota_do_servico(self):
        with mock.patch.object(custo, 'mes', return_value='2026-11'):
            self.gastar(self.bia, 2)
            totais = self.gastar(self.dona, 3, chave_propria=True)
            self.assertEqual(totais, {'conta': 3_000_000, 'organizacao': 2_000_000, 'instalacao': 2_000_000})
            self.assertEqual(custo.gasto_chave_propria(self.root, self.dona), {'conta': 3_000_000, 'organizacao': 3_000_000})
            self.assertEqual(custo.gasto_chave_propria(self.root, self.bia), {'conta': 0, 'organizacao': 3_000_000})
            registro = ler_json(self.root / 'ajustes/gasto_mensal.json')['meses']['2026-11']
        self.assertEqual(registro['organizacoes'], {self.outra: 2_000_000})
        self.assertEqual(registro['chaves_proprias'], {self.outra: 3_000_000})
        self.assertEqual(registro['contas'], {self.bia: 2_000_000, self.dona: 3_000_000})
        self.assertEqual(registro['chaves_proprias_contas'], {self.dona: 3_000_000})

    def test_barra_da_cota_mostra_a_chave_propria_a_parte(self):
        # P40: the person sees what the own key paid for it; the dono also the newsroom's; never in the service's quota.
        with mock.patch.object(custo, 'mes', return_value='2026-11'):
            self.gastar(self.bia, 3, chave_propria=True)
            self.gastar(self.bia, 1)
            reporter = custo.situacao(self.root, self.bia, piloto=True)
            self.assertEqual(reporter['chave_propria'], {'conta_brl': '3.00'})
            self.assertEqual(reporter['conta']['gasto_brl'], '4.00')  # the person's ceiling counts both keys
            dona = custo.situacao(self.root, self.dona, administrador=True, piloto=True)
            self.assertEqual(dona['chave_propria'], {'conta_brl': '0.00', 'organizacao_brl': '3.00'})
            # Outside the piloto the own key never counts (P3c): no part at all, the rest of the bar as before.
            fora = custo.situacao(self.root, self.dona, administrador=True)
            self.assertNotIn('chave_propria', fora)
            self.assertEqual({k: fora[k] for k in ('conta', 'organizacao')}, {k: dona[k] for k in ('conta', 'organizacao')})
            self.assertEqual(dona['organizacao']['gasto_brl'], '1.00')  # the service's quota: without the own key
            self.assertEqual(custo.gasto_chave_propria_brl(self.root, self.bia), '3.00')
            self.assertEqual(custo.gasto_chave_propria_brl(self.root, self.dona, da_redacao=True), '3.00')

    def test_sem_chave_propria_a_parte_some(self):
        # Coruja on the bar (Maestro's option a): without an own key and without spend with it, no 'R$ 0,00' part.
        caio = acesso.criar_conta(self.root, 'Caio', 'caio', papel='reporter', organizacao=self.outra)[0]['id']
        with mock.patch.object(custo, 'mes', return_value='2026-11'):
            self.gastar(self.bia, 2)  # the service's key only
            for conta, administrador in ((self.bia, False), (self.dona, True), (caio, False)):
                with self.subTest(conta=conta):
                    self.assertNotIn('chave_propria', custo.situacao(self.root, conta, administrador=administrador,
                                                                     piloto=True))
            self.gastar(self.bia, 3, chave_propria=True)  # spend with it this month: whoever it concerns sees it
            self.assertNotIn('chave_propria', custo.situacao(self.root, caio, piloto=True))  # not the others
            self.assertEqual(custo.situacao(self.root, self.dona, administrador=True, piloto=True)['chave_propria'],
                             {'conta_brl': '0.00', 'organizacao_brl': '3.00'})
            segredos.salvar_chave(self.root, 'anthropic', PROPRIA, self.outra)  # an own key now: all of it see it
            self.assertEqual(custo.situacao(self.root, caio, piloto=True)['chave_propria'], {'conta_brl': '0.00'})
            segredos.caminho_das_redacoes(self.root).write_text('{ilegível', encoding='utf-8')
            self.assertNotIn('chave_propria', custo.situacao(self.root, caio, piloto=True))  # unreadable: no key
            self.assertEqual(custo.situacao(self.root, self.bia, piloto=True)['chave_propria'], {'conta_brl': '3.00'})

    def test_com_a_chave_propria_so_o_teto_da_pessoa_vale(self):
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ? WHERE id = ?', '10.00', self.outra)
        self.no_banco('UPDATE contas SET teto_mensal_brl = ? WHERE id = ?', '30.00', self.dona)
        self.gastar(self.bia, 9.9)  # the service's quota of the newsroom is used up
        with self.assertRaises(custo.CotaEsgotada):
            custo.conferir_antes(self.root, self.dona, SONNET, ve_redacao=True)  # with the service's key: refused
        custo.conferir_antes(self.root, self.dona, SONNET, ve_redacao=True, chave_propria=True)  # its own key pays
        self.gastar(self.dona, 29.9, chave_propria=True)
        with self.assertRaises(custo.CotaEsgotada) as recusa:
            custo.conferir_antes(self.root, self.dona, SONNET, ve_redacao=True, chave_propria=True)
        # The person's ceiling as set (R$ 30), not capped by the service's quota of the newsroom (R$ 10).
        self.assertTrue(str(recusa.exception).startswith('Sua cota do mês acabou. Você usou R$ 29,90 de R$ 30,00.'))

    def test_estouro_no_meio_com_a_chave_propria(self):
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ? WHERE id = ?', '10.00', self.outra)
        self.no_banco('UPDATE contas SET teto_mensal_brl = ? WHERE id = ?', '30.00', self.dona)
        self.gastar(self.bia, 9.9)
        self.assertIsNone(custo.estouro(self.root, self.gastar(self.dona, 5, chave_propria=True), conta=self.dona,
                                        chave_propria=True))
        causa, mensagem = custo.estouro(self.root, self.gastar(self.dona, 30, chave_propria=True), conta=self.dona,
                                        chave_propria=True)
        self.assertEqual((causa, mensagem), ('limite_cota_conta', custo.mensagem_cota_pessoa()))

    def test_mes_com_lancamento_separado_danificado_e_ilegivel(self):
        self.gastar(self.dona, 1, chave_propria=True)
        caminho = self.root / 'ajustes/gasto_mensal.json'
        dados = ler_json(caminho)
        dados['meses'][custo.mes()]['chaves_proprias'] = {self.outra: -5}
        escrever_json(caminho, dados)
        with self.assertRaisesRegex(ValueError, 'danificado'):
            custo._registro(caminho)  # a damaged month: the ledger is treated as unreadable, never as smaller


class LimiteDiarioTest(redacoes.Redacoes, unittest.TestCase):
    """P40 (a): the own key's tokens count in its newsroom's day, not in the installation's total."""
    setUp = redacoes.CotaPorRedacaoTest.setUp

    def limites(self, **valores):
        config = ler_json(self.root / 'configuracao.json')
        escrever_json(self.root / 'configuracao.json', {**config, 'limites': {'tokens_por_consulta': None, **valores}})

    def test_somar_e_conferir_o_dia_com_a_chave_propria(self):
        self.limites(tokens_por_dia=100, tokens_por_dia_por_organizacao=50)
        self.assertEqual(limites.somar_dia(self.root, 40, self.outra, instalacao=False), 0)  # the installation's: 0
        self.assertEqual(limites.dia_da_organizacao(self.root, self.outra), 40)
        limites.somar_dia(self.root, 100, custo.ORGANIZACAO)  # another newsroom fills the installation's day
        with self.assertRaisesRegex(ValueError, 'instalação'):
            limites.conferir_dia(self.root, self.outra)
        limites.conferir_dia(self.root, self.outra, instalacao=False)  # its own key: only its own day holds
        limites.somar_dia(self.root, 10, self.outra, instalacao=False)
        with self.assertRaisesRegex(ValueError, 'redação'):
            limites.conferir_dia(self.root, self.outra, instalacao=False)


class ConversaNaRedacaoTest(redacoes.Redacoes, unittest.TestCase):
    """Through Conversas with the simulated provider (piloto): the turn carries the newsroom; the usage says who paid."""

    def setUp(self):
        redacoes.PerguntaNaRedacaoTest.setUp(self)
        self.manager.chave_da_redacao = True  # what the server sets in the piloto mode
    pergunta = redacoes.PerguntaNaRedacaoTest.pergunta
    estourar = redacoes.PerguntaNaRedacaoTest.estourar

    def test_o_turno_leva_a_redacao_e_o_uso_da_chave_propria_cai_no_lancamento_separado(self):
        identificador = self.manager.perguntar(self.pergunta(), conta=self.dona)['conversa']
        meta = lambda: self.manager.contexts[identificador]['meta']  # noqa: E731
        redacoes.esperar(lambda: meta().get('turn_id'))
        turnos = [p for m, p in self.manager.rpc.calls if m == 'turn/start']
        self.assertEqual(turnos[0]['redacao'], self.outra)
        uso = redacoes.test_custo.uso_anthropic()
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso, 'chavePropria': True})
        redacoes.esperar(lambda: meta().get('custo_micro_brl'))
        self.manager.cancelar(identificador)
        registro = ler_json(self.root / 'ajustes/gasto_mensal.json')['meses'][custo.mes()]
        self.assertEqual(registro['chaves_proprias'].get(self.outra), meta()['custo_micro_brl'])
        self.assertEqual(registro['organizacoes'].get(self.outra, 0), 0)  # the check before the question writes 0
        self.assertEqual(registro['contas'][self.dona], meta()['custo_micro_brl'])
        run = self.manager.contexts[identificador]['run']
        self.assertEqual(ler_json(run / 'saidas/api_uso_0001.json')['chave'], 'redacao')

    def test_chamada_com_a_chave_propria_fora_do_dia_da_instalacao(self):
        config = ler_json(self.root / 'configuracao.json')
        escrever_json(self.root / 'configuracao.json', {**config, 'limites': {'tokens_por_dia': 1000}})
        identificador = self.manager.perguntar(self.pergunta(), conta=self.dona)['conversa']
        meta = lambda: self.manager.contexts[identificador]['meta']  # noqa: E731
        redacoes.esperar(lambda: meta().get('turn_id'))
        uso = redacoes.test_custo.uso_anthropic()  # far over the installation's 1000 tokens of the day
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso, 'chavePropria': True})
        redacoes.esperar(lambda: meta().get('custo_micro_brl'))
        self.assertFalse(self.manager.contexts[identificador].get('cancel'))  # not stopped by the installation's day
        self.assertEqual(limites._hoje(self.root)['tokens'], 0)
        self.assertEqual(limites.dia_da_organizacao(self.root, self.outra), custo.tokens_totais(uso))
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso})  # the service's key
        redacoes.aguardar_fim(self.manager, identificador)
        self.assertEqual(meta()['situacao']['causa'], 'limite_dia')

    def test_com_a_chave_propria_a_cota_do_servico_nao_recusa(self):
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ? WHERE id = ?', '10.00', self.outra)
        self.gastar(self.bia, 9.9)  # the service's quota of the newsroom is used up
        with self.assertRaises(ValueError):
            self.manager.perguntar(self.pergunta(), conta=self.dona, ve_gasto_da_redacao=True)
        status = self.manager.status
        with mock.patch.object(self.manager, 'status', lambda redacao=None: {**status(redacao), 'chave_propria': True}):
            self.assertTrue(self.manager.perguntar(self.pergunta(), conta=self.dona)['conversa'])


class LocalContasTest(redacoes.Redacoes, unittest.TestCase):
    """P3c: outside piloto (local-contas) the newsroom's keys file is never read: the service's key pays, valid file
    or unreadable, and the question is not refused."""

    def setUp(self):
        redacoes.PerguntaNaRedacaoTest.setUp(self)
        self.assertFalse(self.manager.chave_da_redacao)  # the default: only the piloto server turns it on

    def pergunta_sem_redacao(self):
        identificador = self.manager.perguntar(redacoes.PerguntaNaRedacaoTest.pergunta(self), conta=self.dona)['conversa']
        meta = lambda: self.manager.contexts[identificador]['meta']  # noqa: E731
        redacoes.esperar(lambda: meta().get('turn_id'))
        self.manager.cancelar(identificador)
        leituras = [p for m, p in self.manager.rpc.calls if m == 'account/read']
        turnos = [p for m, p in self.manager.rpc.calls if m == 'turn/start']
        self.assertTrue(leituras and turnos)
        self.assertFalse(any('redacao' in p for p in leituras + turnos))

    def test_arquivo_valido_de_um_piloto_nao_vale(self):
        segredos.salvar_chave(self.root, 'anthropic', PROPRIA, self.outra)
        self.pergunta_sem_redacao()

    def test_arquivo_ilegivel_nao_recusa(self):
        segredos.caminho_das_redacoes(self.root).parent.mkdir(parents=True, exist_ok=True)
        segredos.caminho_das_redacoes(self.root).write_text('{ilegível', encoding='utf-8')
        self.pergunta_sem_redacao()

    def test_o_servidor_liga_so_no_piloto(self):
        from interface_pesquisa import Servidor
        for modo, esperado in (('local', False), ('local-contas', False), ('piloto', True)):
            with self.subTest(modo=modo):
                servidor = Servidor(('127.0.0.1', 0), self.root, modo=modo,
                                    origem='https://vlado.example.org' if modo == 'piloto' else None)
                try:
                    self.assertIs(servidor.conversas.chave_da_redacao, esperado)
                finally:
                    servidor.server_close()


class TelaDaEquipeTest(cenario.DuasRedacoes):
    """P40 (b) through the server: equipe-listar and GET /api/cota, with two newsrooms (rota da Tranca, com o aval
    dela): each dono sees only its own newsroom's own-key spend, each person only its own."""

    def test_cada_um_ve_so_o_que_lhe_cabe_da_chave_propria(self):
        with mock.patch.object(custo, 'mes', return_value='2031-02'):  # a month of its own: nothing else spent in it
            custo.somar_gasto(self.root, self.ids['reporter'], 3_250_000, chave_propria=True)
            custo.somar_gasto(self.root, self.ids['reporter_b'], 7_750_000, chave_propria=True)
            for dono, reporter, proprio, alheio in (('dono', 'reporter', '3.25', '7.75'),
                                                    ('dono_b', 'reporter_b', '7.75', '3.25')):
                with self.subTest(dono=dono):
                    corpo = self.post(dono, 'equipe-listar', {})[1]
                    self.assertEqual(corpo['gasto_chave_propria_brl'], proprio)
                    por_pessoa = {p['id']: p['gasto_chave_propria_brl'] for p in corpo['pessoas']}
                    self.assertEqual(por_pessoa[self.ids[reporter]], proprio)
                    self.assertTrue(all(v == '0.00' for k, v in por_pessoa.items() if k != self.ids[reporter]))
                    self.assertNotIn(alheio, str(corpo))
                    self.assertEqual(set(corpo['pessoas'][0]['gasto']), {'mes', 'gasto_brl', 'teto_brl', 'saldo_brl',
                                                                          'esgotada'})
                    cota = self.get(dono, '/api/cota')[1]
                    self.assertEqual(cota['chave_propria'], {'conta_brl': '0.00', 'organizacao_brl': proprio})
                    cota = self.get(reporter, '/api/cota')[1]
                    self.assertEqual(cota['chave_propria'], {'conta_brl': proprio})  # its own; no newsroom number
            for quem in ('editor', 'leitor', 'convidado'):
                with self.subTest(quem=quem):  # no own key and no spend with it: the part is not sent at all
                    status, cota, _ = self.get(quem, '/api/cota')
                    self.assertEqual(status, 200)
                    self.assertNotIn('chave_propria', cota)
                    self.assertIn('gasto_brl', cota['conta'])
            # The newsroom saves its own key: from then on everyone in it gets the part, at R$ 0,00 until it spends.
            segredos.salvar_chave(self.root, 'anthropic', PROPRIA, self.a)
            self.addCleanup(segredos.remover_chave, self.root, 'anthropic', self.a)
            for quem in ('editor', 'reporter2'):
                self.assertEqual(self.get(quem, '/api/cota')[1]['chave_propria'], {'conta_brl': '0.00'})
            self.assertEqual(self.get('reporter_b', '/api/cota')[1]['chave_propria'], {'conta_brl': '7.75'})

    def test_razao_ilegivel_a_tela_da_equipe_abre(self):
        with mock.patch.object(custo, 'gasto_chave_propria_brl', side_effect=ValueError('razão ilegível')):
            status, corpo, _ = self.post('dono', 'equipe-listar', {})
        self.assertEqual(status, 200)
        self.assertIsNone(corpo['gasto_chave_propria_brl'])
        self.assertTrue(all(p['gasto_chave_propria_brl'] is None for p in corpo['pessoas']))


if __name__ == '__main__':
    unittest.main()
