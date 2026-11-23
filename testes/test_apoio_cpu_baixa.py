"""A regra das esperas pela extração (apoio_cpu_baixa): falha quando houve CPU e a leitura não aconteceu, pula só
quando a sonda da mesma janela não teve CPU. Sondas falsas com números escolhidos; uma real só para ver que mede e
para. Sem Mesa nem rede."""
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apoio_cpu_baixa as apoio  # noqa: E402


def sonda_falsa(cpu, janela=60.0):
    class Falsa:
        criadas = []

        def __init__(self, limite):
            self.limite = limite
            self.paradas = 0
            Falsa.criadas.append(self)

        def parar(self):
            self.paradas += 1
            return janela, cpu

        def __enter__(self):
            return self

        def __exit__(self, *erro):
            pass
    return Falsa


class RegraTest(unittest.TestCase):
    def falha(self, *args, **kwargs):
        """The AssertionError of esperar_com_cpu; a skip there is a failure of the rule, never a skipped test."""
        try:
            apoio.esperar_com_cpu(self, *args, **kwargs)
        except AssertionError as erro:
            return str(erro)
        except unittest.SkipTest as pulo:
            self.fail(f'a regra pulou onde devia falhar: {pulo}')
        self.fail('a regra não decidiu')

    def pulo(self, *args, **kwargs):
        try:
            apoio.esperar_com_cpu(self, *args, **kwargs)
        except unittest.SkipTest as pulo:
            return str(pulo)
        except AssertionError as erro:
            self.fail(f'a regra falhou onde devia pular: {erro}')
        self.fail('a regra não decidiu')

    def test_condicao_atendida_volta_o_valor_sem_decidir(self):
        falsa = sonda_falsa(cpu=0.0)
        self.assertEqual(apoio.esperar_com_cpu(self, lambda: 'lido', 0.2, 2.0, 'não leu', sonda=falsa), 'lido')
        self.assertEqual(falsa.criadas[0].limite, 30.2)  # the probe outlives the wait, then is stopped by the caller

    def test_com_cpu_e_sem_leitura_falha(self):
        texto = self.falha(lambda: None, 0.2, 2.0, 'o processo de extração não começou a ler',
                           sonda=sonda_falsa(cpu=5.5, janela=60.4))
        self.assertIn('o processo de extração não começou a ler em 0 s, com CPU disponível', texto)
        self.assertIn('teve 5.50 s de CPU em 60.4 s (necessário 2 s)', texto)

    def test_exatamente_o_necessario_ja_falha(self):
        self.falha(lambda: None, 0.1, 2.0, 'não leu', sonda=sonda_falsa(cpu=2.0))

    def test_sem_cpu_na_janela_pula_com_os_numeros(self):
        texto = self.pulo(lambda: None, 0.2, 60.0, 'a Mesa reiniciada não concluiu o lote',
                          sonda=sonda_falsa(cpu=0.28, janela=40.0))
        self.assertTrue(texto.startswith('máquina saturada para prioridade baixa: '), texto)
        self.assertIn('teve 0.28 s de CPU em 40.0 s (necessário 60 s)', texto)
        self.assertIn('a Mesa reiniciada não concluiu o lote', texto)


class OciosaTest(unittest.TestCase):
    """The rule for the Mesa's own times (T_ref of the gate): idle CPU of the machine in the same window."""

    def decidir(self, ociosa, gasto):
        try:
            apoio.decidir_por_ociosa(self, ociosa, gasto, 'T_ref = 6.20 s, acima de 6 s')
        except AssertionError as erro:
            return 'falha', str(erro)
        except unittest.SkipTest as pulo:
            return 'pula', str(pulo)
        self.fail('a regra não decidiu')

    def test_com_ociosa_suficiente_falha(self):
        decisao, texto = self.decidir(ociosa=9.0, gasto=2.0)  # 4 x 2.0 = 8.0 needed
        self.assertEqual(decisao, 'falha', texto)
        self.assertIn('com CPU disponível: na mesma janela a máquina deixou 9.00 s de CPU ociosa; a Mesa gastou 2.00 s '
                      '(necessário 8.00 s ociosos)', texto)

    def test_sem_ociosa_suficiente_pula_com_os_numeros(self):
        decisao, texto = self.decidir(ociosa=7.9, gasto=2.0)
        self.assertEqual(decisao, 'pula', texto)
        self.assertTrue(texto.startswith('máquina saturada para prioridade normal: '), texto)
        self.assertIn('T_ref = 6.20 s, acima de 6 s', texto)

    def test_minimo_de_um_segundo(self):
        self.assertEqual(self.decidir(ociosa=0.9, gasto=0.1)[0], 'pula')  # 4 x 0.1 < 1 s: the minimum counts
        self.assertEqual(self.decidir(ociosa=1.0, gasto=0.1)[0], 'falha')

    def test_ociosa_ilegivel_falha(self):
        decisao, texto = self.decidir(ociosa=None, gasto=2.0)
        self.assertEqual(decisao, 'falha', texto)
        self.assertIn('ilegível', texto)

    def test_cpu_ociosa_da_maquina_cresce(self):
        antes = apoio.cpu_ociosa_s()
        if antes is None:
            self.skipTest('CPU ociosa ilegível nesta plataforma')
        time.sleep(0.3)
        self.assertGreaterEqual(apoio.cpu_ociosa_s(), antes)


class SondaRealTest(unittest.TestCase):
    def test_mede_e_para_na_hora(self):
        # Stopped at once even when the machine gives it no CPU (it is killed, not asked).
        with apoio.SondaBaixa(600) as sonda:  # its own limit far away: only being killed ends it soon
            time.sleep(0.5)
            antes = time.monotonic()
            janela, cpu = sonda.parar()
        self.assertLess(time.monotonic() - antes, 300, 'a sonda só parou no próprio limite')
        self.assertGreaterEqual(janela, 0.5)
        self.assertGreaterEqual(cpu, 0.0)
        self.assertLessEqual(cpu, janela * 64)  # never more CPU than its cores could give
        self.assertEqual(sonda.parar(), (janela, cpu))  # stopping again reads the same numbers


if __name__ == '__main__':
    unittest.main()
