"""Testes sem navegador de regressao_visual_custo.py: o julgamento e o relatório da medida de custo da faixa que rola."""
import unittest

import regressao_visual_custo as custo


def observador(nomes, faixa, chamadas, ms=1.0):
    return {'alvos': [{'nome': n, 'faixa': faixa} for n in nomes], 'chamadas': chamadas, 'registros': chamadas, 'nos': chamadas * 12, 'ms': ms}


def medida(*observadores, novas=200):
    return {'total_ms': 50.0, 'consultas_de_faixa': 7, 'quadros_pedidos': 3, 'estilos_de_faixa': 2, 'novas': novas, 'observadores': list(observadores)}


class JulgarCustoTest(unittest.TestCase):
    def test_observador_so_de_faixa_que_acorda_com_mensagem_reprova(self):
        reprovacoes = custo.julgar_custo('todas de uma vez', medida(observador(['#mesa-etapas', '.quadros-abas'], True, 3)))
        self.assertEqual(len(reprovacoes), 1)
        self.assertIn('#mesa-etapas', reprovacoes[0])
        self.assertIn('3 vez(es)', reprovacoes[0])

    def test_observador_do_corpo_e_custo_nao_reprovacao(self):
        self.assertEqual(custo.julgar_custo('uma por tarefa', medida(observador(['body'], False, 200))), [])

    def test_observador_com_um_alvo_que_nao_e_faixa_nao_reprova(self):
        misto = {'alvos': [{'nome': '#mesa-etapas', 'faixa': True}, {'nome': 'body', 'faixa': False}], 'chamadas': 5, 'registros': 5, 'nos': 5, 'ms': 1}
        self.assertEqual(custo.julgar_custo('x', medida(misto)), [])

    def test_sem_observador_acordado_passa(self):
        self.assertEqual(custo.julgar_custo('uma por tarefa', medida()), [])

    def test_observador_sem_alvo_nao_e_faixa(self):
        self.assertEqual(custo.julgar_custo('x', medida({'alvos': [], 'chamadas': 1, 'registros': 1, 'nos': 1, 'ms': 0})), [])

    def test_medida_sem_mensagem_nova_nao_vale(self):
        reprovacoes = custo.julgar_custo('x', medida(novas=0))
        self.assertEqual(len(reprovacoes), 1)
        self.assertIn('nenhuma mensagem', reprovacoes[0])


class RelatorioTest(unittest.TestCase):
    def test_relatorio_traz_os_numeros_e_marca_as_faixas(self):
        linhas = custo.relatorio('todas de uma vez', 200, medida(observador(['body'], False, 1, ms=4.2), observador(['#mesa-etapas'], True, 0, ms=0.0)))
        self.assertIn('200 mensagens, todas de uma vez', linhas[0])
        self.assertIn('7 consulta(s)', linhas[0])
        self.assertIn('3 quadro(s) pedido(s)', linhas[0])
        self.assertIn('2 leitura(s) de estilo de faixa', linhas[0])
        self.assertTrue(any('[body] 1 chamada(s)' in l and '4.2 ms' in l for l in linhas))
        self.assertTrue(any('#mesa-etapas*' in l for l in linhas))

    def test_o_instrumento_e_o_seletor_cobrem_as_quatro_faixas(self):
        for faixa in ('mesa-etapas', 'quadros-abas', 'mesa-tabs', 'notebook-tabs'):
            self.assertIn(faixa, custo.FAIXAS)
            self.assertIn(faixa, custo.JS_INSTRUMENTO)


if __name__ == '__main__':
    unittest.main()
