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
from comum import escrever_json, ler_json  # noqa: E402
import custo  # noqa: E402
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
            self.assertEqual(custo.gasto_chave_propria(self.root, self.dona), 3_000_000)
            registro = ler_json(self.root / 'ajustes/gasto_mensal.json')['meses']['2026-11']
        self.assertEqual(registro['organizacoes'], {self.outra: 2_000_000})
        self.assertEqual(registro['chaves_proprias'], {self.outra: 3_000_000})
        self.assertEqual(registro['contas'], {self.bia: 2_000_000, self.dona: 3_000_000})

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


class ConversaNaRedacaoTest(redacoes.Redacoes, unittest.TestCase):
    """Through Conversas with the simulated provider: the turn carries the newsroom; the usage says who paid."""
    setUp = redacoes.PerguntaNaRedacaoTest.setUp
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

    def test_com_a_chave_propria_a_cota_do_servico_nao_recusa(self):
        self.no_banco('UPDATE organizacoes SET cota_mensal_brl = ? WHERE id = ?', '10.00', self.outra)
        self.gastar(self.bia, 9.9)  # the service's quota of the newsroom is used up
        with self.assertRaises(ValueError):
            self.manager.perguntar(self.pergunta(), conta=self.dona, ve_gasto_da_redacao=True)
        status = self.manager.status
        with mock.patch.object(self.manager, 'status', lambda redacao=None: {**status(redacao), 'chave_propria': True}):
            self.assertTrue(self.manager.perguntar(self.pergunta(), conta=self.dona)['conversa'])


if __name__ == '__main__':
    unittest.main()
