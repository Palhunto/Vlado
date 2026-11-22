"""Cota de IA por redação (Onda 2, P1; contrato de contas, 8.5), só com provedor simulado.

Cobre: ``chaves_orcamento`` devolve a redação da conta, lida do armazenamento de contas (a redação
inicial, uma conta desconhecida e o modo sem contas ficam em ``instalacao``, e a consulta nunca cria
o banco); o gasto cai na pessoa e na redação dela, e o da instalação é a soma das redações; os três
tetos (pessoa, redação, instalação), com o da pessoa nunca acima do da redação; quem vê número na
recusa (a pessoa, o próprio; o da redação, só quem a rota diz que vê; o da instalação, ninguém); e a
barra da cota sem o total da instalação. Os tetos são gravados direto no banco de contas, porque as
operações que os definem (``equipe-teto``, ``redacao-cota``) ainda não existem.
"""
from decimal import Decimal
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
sys.path.insert(0, str(TESTES))
import acesso  # noqa: E402
import cenario_redacoes as cenario  # noqa: E402
from comum import escrever_json, ler_json  # noqa: E402
import custo  # noqa: E402
import erros  # noqa: E402
import test_codex_integracao as integracao  # noqa: E402

SONNET = 'claude-sonnet-5-5'


class Redacoes:
    """Two newsrooms in the account store of ``self.root``: the initial one and another."""

    def montar_redacoes(self):
        self.inicial = acesso.criar_redacao(self.root, 'Redação Inicial Sintética')['id']
        self.outra = acesso.criar_redacao(self.root, 'Outra Redação Sintética')['id']
        self.ana = acesso.criar_conta(self.root, 'Ana', 'ana', papel='reporter', organizacao=self.inicial)[0]['id']
        self.bia = acesso.criar_conta(self.root, 'Bia', 'bia', papel='reporter', organizacao=self.outra)[0]['id']
        self.dona = acesso.criar_conta(self.root, 'Dora', 'dora', papel='dono', organizacao=self.outra)[0]['id']

    def no_banco(self, sql, *args):
        con = sqlite3.connect(str(acesso.caminho_bd(self.root)))
        try:
            with con:  # commits; closing is explicit (Windows keeps an open file from being removed)
                con.execute(sql, args)
        finally:
            con.close()

    def gastar(self, conta, reais):
        return custo.somar_gasto(self.root, conta, int(Decimal(str(reais)) * custo.MICRO))

    def orcamento(self, **valores):
        config = ler_json(self.root / 'configuracao.json')
        escrever_json(self.root / 'configuracao.json', {**config, 'orcamento': valores})


class CotaPorRedacaoTest(Redacoes, unittest.TestCase):
    def setUp(self):
        sem_variavel = {k: v for k, v in os.environ.items() if k != 'VLADO_ACESSO'}
        ambiente = mock.patch.dict(os.environ, sem_variavel, clear=True)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        escrever_json(self.root / 'configuracao.json', {'provedor': 'anthropic', 'modelo_preferido': None})
        self.montar_redacoes()

    def test_chaves_trazem_a_redacao_da_conta(self):
        self.assertEqual(custo.chaves_orcamento(self.bia, self.root), {'conta': self.bia, 'organizacao': self.outra})
        # The first newsroom inherited the installation's spend: its ledger key never changes.
        self.assertEqual(custo.chaves_orcamento(self.ana, self.root)['organizacao'], custo.ORGANIZACAO)
        self.assertEqual(custo.chaves_orcamento('0' * 16, self.root)['organizacao'], custo.ORGANIZACAO)
        self.assertEqual(custo.chaves_orcamento(None, self.root), {'conta': custo.CONTA_LOCAL, 'organizacao': custo.ORGANIZACAO})
        self.assertEqual(custo.chaves_orcamento(self.bia)['organizacao'], custo.ORGANIZACAO)  # without root, as before

    def test_sem_armazenamento_de_contas_nada_e_criado(self):
        with tempfile.TemporaryDirectory() as outra:
            raiz = Path(outra)
            self.assertEqual(custo.chaves_orcamento(self.bia, raiz)['organizacao'], custo.ORGANIZACAO)
            self.assertEqual(custo.tetos(raiz, self.bia, custo.ler_orcamento(self.root))['conta'], Decimal('50.0'))
            self.assertFalse((raiz / 'acesso').exists(), 'a consulta do custo criou o banco de contas')

    def test_gasto_cai_na_pessoa_e_na_redacao_e_a_instalacao_soma_todas(self):
        with mock.patch.object(custo, 'mes', return_value='2026-11'):
            self.gastar(self.ana, 3)
            self.gastar(self.bia, 2)
            totais = self.gastar(self.dona, 1.5)
            self.assertEqual(totais, {'conta': 1_500_000, 'organizacao': 3_500_000, 'instalacao': 6_500_000})
            registro = ler_json(self.root / 'ajustes/gasto_mensal.json')['meses']['2026-11']
        self.assertEqual(registro['organizacoes'], {custo.ORGANIZACAO: 3_000_000, self.outra: 3_500_000})
        self.assertEqual(registro['contas'], {self.ana: 3_000_000, self.bia: 2_000_000, self.dona: 1_500_000})

    def test_tres_tetos_e_o_da_pessoa_nunca_acima_do_da_redacao(self):
        orcamento = custo.ler_orcamento(self.root)
        self.assertEqual(custo.tetos(self.root, self.ana, orcamento),
                         {'conta': Decimal('50.0'), 'pessoa': Decimal('50.0'), 'organizacao': Decimal('500.0'),
                          'instalacao': None})
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ?, teto_por_pessoa_brl = ? WHERE id = ?',
                      '20.00', '5.00', self.outra)
        self.no_banco('UPDATE contas SET teto_mensal_brl = ? WHERE id = ?', '8.00', self.dona)
        self.assertEqual(custo.tetos(self.root, self.bia)['conta'], Decimal('5.00'))  # the newsroom's per person
        self.assertEqual(custo.tetos(self.root, self.dona)['conta'], Decimal('8.00'))  # the account's own
        self.assertEqual(custo.tetos(self.root, self.dona)['organizacao'], Decimal('20.00'))
        self.no_banco('UPDATE contas SET teto_mensal_brl = ? WHERE id = ?', '30.00', self.dona)
        self.assertEqual(custo.tetos(self.root, self.dona)['conta'], Decimal('20.00'))
        self.orcamento(mensal_instalacao_brl=40)
        self.assertEqual(custo.tetos(self.root, self.ana)['instalacao'], Decimal('40'))

    def test_recusa_pela_pessoa_com_o_proprio_numero(self):
        self.no_banco('UPDATE organizacoes SET teto_por_pessoa_brl = ? WHERE id = ?', '5.00', self.outra)
        self.gastar(self.bia, 4.5)  # the minimum estimate of a short question does not fit in R$ 0,50
        with self.assertRaises(custo.CotaEsgotada) as recusa:
            custo.conferir_antes(self.root, self.bia, SONNET, ve_redacao=False)
        self.assertTrue(str(recusa.exception).startswith('Sua cota do mês acabou. Você usou R$ 4,50 de R$ 5,00.'))
        custo.conferir_antes(self.root, self.dona, SONNET)  # another person of the same newsroom still asks

    def test_teto_proprio_acima_do_da_redacao_nao_mostra_o_da_redacao(self):
        # The operator lowered the newsroom below a person's own ceiling: the reporter is stopped by the
        # newsroom's, and neither the refusal nor the quota bar tells the reporter that number.
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ? WHERE id = ?', '20.00', self.outra)
        self.no_banco('UPDATE contas SET teto_mensal_brl = ? WHERE id IN (?, ?)', '30.00', self.bia, self.dona)
        self.gastar(self.bia, 19.5)
        with self.assertRaises(custo.CotaEsgotada) as recusa:
            custo.conferir_antes(self.root, self.bia, SONNET, ve_redacao=False)
        self.assertTrue(str(recusa.exception).startswith('A cota do mês da redação acabou.'), str(recusa.exception))
        self.assertNotRegex(str(recusa.exception), r'\d')
        barra = custo.situacao(self.root, self.bia)
        self.assertEqual(barra['conta']['teto_brl'], '30.00')
        self.assertNotIn('20.00', str(barra))
        with self.assertRaises(custo.CotaEsgotada) as recusa:  # the dono sees it: the own capped at the newsroom's
            custo.conferir_antes(self.root, self.dona, SONNET, ve_redacao=True)
        self.assertIn('R$ 20,00', str(recusa.exception))
        self.assertEqual(custo.situacao(self.root, self.dona, administrador=True)['conta']['teto_brl'], '20.00')

    def test_recusa_pela_redacao_numero_so_para_quem_ve_a_redacao(self):
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ? WHERE id = ?', '20.00', self.outra)
        self.gastar(self.dona, 10)
        self.gastar(self.bia, 9.5)
        with self.assertRaises(custo.CotaEsgotada) as recusa:
            custo.conferir_antes(self.root, self.dona, SONNET, ve_redacao=True)
        self.assertTrue(str(recusa.exception).startswith(
            'A cota do mês da redação acabou. Foram usados R$ 19,50 de R$ 20,00.'), str(recusa.exception))
        self.assertEqual(erros.codigo_de(str(recusa.exception))[0], 'cota_mensal_redacao')
        for ve in (False, None):  # a reporter, and a caller that does not say
            with self.subTest(ve_redacao=ve), self.assertRaises(custo.CotaEsgotada) as recusa:
                custo.conferir_antes(self.root, self.bia, SONNET, convidado=ve is None, ve_redacao=ve)
            self.assertTrue(str(recusa.exception).startswith('A cota do mês da redação acabou.'))
            self.assertNotRegex(str(recusa.exception), r'\d')
        custo.conferir_antes(self.root, self.ana, SONNET)  # the other newsroom is untouched

    def test_recusa_pela_instalacao_sem_numero_para_ninguem(self):
        self.orcamento(mensal_instalacao_brl=10)
        self.gastar(self.bia, 5)
        self.gastar(self.ana, 4.5)  # each within its newsroom; together, at the installation's
        for conta in (self.ana, self.dona):
            with self.subTest(conta=conta), self.assertRaises(custo.CotaEsgotada) as recusa:
                custo.conferir_antes(self.root, conta, SONNET, ve_redacao=True)
            self.assertEqual(str(recusa.exception), custo.mensagem_cota_instalacao())
            self.assertNotRegex(str(recusa.exception), r'\d')
            self.assertEqual(erros.codigo_de(str(recusa.exception))[0], 'cota_mensal_instalacao')

    def test_estouro_no_meio_da_pergunta_pelos_tres_tetos(self):
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ?, teto_por_pessoa_brl = ? WHERE id = ?',
                      '20.00', '15.00', self.outra)
        self.assertEqual(custo.estouro(self.root, self.gastar(self.bia, 15), conta=self.bia)[0], 'limite_cota_conta')
        causa, mensagem = custo.estouro(self.root, self.gastar(self.dona, 6), conta=self.dona, ve_redacao=False)
        self.assertEqual(causa, 'limite_cota_organizacao')
        self.assertNotRegex(mensagem, r'\d')
        self.orcamento(mensal_instalacao_brl=22)
        self.assertEqual(custo.estouro(self.root, self.gastar(self.ana, 1), conta=self.ana)[0], 'limite_cota_instalacao')

    def test_barra_da_cota_sem_o_total_da_instalacao(self):
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ?, teto_por_pessoa_brl = ? WHERE id = ?',
                      '20.00', '5.00', self.outra)
        self.gastar(self.bia, 2)
        self.gastar(self.ana, 7)
        reporter = custo.situacao(self.root, self.bia)
        self.assertEqual((reporter['conta']['gasto_brl'], reporter['conta']['teto_brl']), ('2.00', '5.00'))
        self.assertNotIn('organizacao', reporter)
        dona = custo.situacao(self.root, self.dona, administrador=True)
        self.assertEqual((dona['organizacao']['gasto_brl'], dona['organizacao']['teto_brl']), ('2.00', '20.00'))
        self.assertNotIn('instalacao', reporter)
        self.assertNotIn('instalacao', dona)


class PerguntaNaRedacaoTest(Redacoes, unittest.TestCase):
    """Through Conversas with the simulated provider: the route's flag decides the newsroom's numbers."""

    def setUp(self):
        integracao.CodexIntegrationTest.setUp(self)
        self.montar_redacoes()

    def pergunta(self):
        return {'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}

    def test_recusa_da_redacao_com_numero_so_com_a_bandeira_da_rota(self):
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ? WHERE id = ?', '10.00', self.outra)
        self.gastar(self.dona, 9.5)
        antes = set(self.manager.contexts)
        with self.assertRaises(ValueError) as recusa:
            self.manager.perguntar(self.pergunta(), conta=self.dona, ve_gasto_da_redacao=True)
        self.assertIn('R$ 9,50 de R$ 10,00', str(recusa.exception))
        with self.assertRaises(ValueError) as recusa:
            self.manager.perguntar(self.pergunta(), conta=self.bia)  # the route did not say: no number
        self.assertTrue(str(recusa.exception).startswith('A cota do mês da redação acabou.'))
        self.assertNotRegex(str(recusa.exception), r'\d')
        self.assertEqual(set(self.manager.contexts), antes)  # nothing was started
        self.assertTrue(self.manager.perguntar(self.pergunta(), conta=self.ana)['conversa'])  # the other newsroom

    def test_execucao_guarda_de_quem_e_o_gasto(self):
        identificador = self.manager.perguntar(self.pergunta(), conta=self.bia)['conversa']
        ctx = self.manager.contexts[identificador]
        self.assertEqual(ctx['orcamento'], {'conta': self.bia, 'organizacao': self.outra})
        self.assertFalse(ctx['ve_gasto_da_redacao'])
        self.manager.cancelar(identificador)


class RotaPassaABandeiraTest(cenario.DuasRedacoes):
    """The server gives ``perguntar`` and ``retomar`` the flag of ``autorizacao.gasto_da_redacao`` (rota da Tranca, com
    o aval dela): True only for the dono of the newsroom."""

    def test_so_o_dono_recebe_a_bandeira_da_redacao(self):
        recebidas = []

        def guardar(nome):
            def chamada(*args, **kwargs):
                recebidas.append((nome, kwargs.get('ve_gasto_da_redacao')))
                return {'conversa': 'sintetica'}
            return chamada
        with mock.patch.object(self.manager, 'perguntar', guardar('perguntar')),                 mock.patch.object(self.manager, 'retomar', guardar('retomar')):
            for quem, esperado in (('dono', True), ('editor', False), ('reporter', False)):
                with self.subTest(quem=quem):
                    del recebidas[:]
                    status, _, bruto = self.post(quem, 'codex-perguntar', {'caso': 'alpha', 'pergunta': 'Pergunta sintética.'})
                    self.assertEqual(status, 200, bruto[:200])
                    status, _, bruto = self.post(quem, 'codex-retomar', {'conversa': self.conversas['equipe', 'alpha']})
                    self.assertEqual(status, 200, bruto[:200])
                    self.assertEqual(recebidas, [('perguntar', esperado), ('retomar', esperado)])


if __name__ == '__main__':
    unittest.main()
