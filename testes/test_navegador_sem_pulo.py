"""Regra: nenhum teste de navegador pula em silêncio no CI.

Em 623a620 o `test_dados_conta_navegador` falhava e o CI não acusou: ele pulava sem o Playwright do Node em
`.ferramentas/node`, que o CI não instalava. A regra tem três partes:

1. o decorador `auxiliar_node.requer_navegador_node` pula na máquina de quem desenvolve e FALHA com
   `VLADO_EXIGIR_PLAYWRIGHT=1` (o CI, como no portão de contraste);
2. todo módulo de teste que abre um navegador usa esse decorador (ou `VLADO_EXIGIR_PLAYWRIGHT` por conta própria);
   um teste novo que pule por outro caminho reprova aqui, antes de chegar ao CI;
3. `executar_suite.py`, com `VLADO_EXIGIR_PLAYWRIGHT=1`, reprova a execução se qualquer teste pular citando
   Playwright ou Chromium.

Sem navegador, sem rede e sem modelo.
"""
from pathlib import Path
import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auxiliar_node
import executar_suite

TESTES = Path(__file__).resolve().parent
# Sinais de que o módulo dirige um navegador: roteiro Node, Playwright do Node ou do Python.
SINAIS = re.compile(r"qa_\w+\.cjs|['\"]\.ferramentas['\"]|sync_playwright|from playwright|import playwright")
EXIGENCIA = ('requer_navegador_node', 'VLADO_EXIGIR_PLAYWRIGHT')
# Pulo condicional que testa o navegador sem a exigência do CI.
PULO_SOLTO = re.compile(r"skipUnless\([^\n]*(node|playwright|chromium|ferramentas)", re.I)


def modulos_de_navegador():
    for caminho in sorted(TESTES.glob('test_*.py')):
        if caminho.name == Path(__file__).name:
            continue
        texto = caminho.read_text(encoding='utf-8')
        if SINAIS.search(texto):
            yield caminho.name, texto


class RegraNoCodigoTest(unittest.TestCase):
    def test_todo_modulo_de_navegador_exige_o_navegador_no_ci(self):
        modulos = list(modulos_de_navegador())
        self.assertGreaterEqual(len(modulos), 8, 'a busca não achou os módulos de navegador conhecidos')
        sem_exigencia = [nome for nome, texto in modulos if not any(marca in texto for marca in EXIGENCIA)]
        self.assertEqual(sem_exigencia, [], 'módulo que abre um navegador sem exigir o Playwright no CI: '
                         'use @requer_navegador_node (testes/auxiliar_node.py)')

    def test_nenhum_pulo_solto_de_node_ou_navegador(self):
        soltos = [nome for nome, texto in modulos_de_navegador() if PULO_SOLTO.search(texto)]
        self.assertEqual(soltos, [], 'use @requer_navegador_node em vez de skipUnless de Node/Playwright')


class DecoradorTest(unittest.TestCase):
    """O comportamento do decorador, com a disponibilidade simulada (não depende do navegador desta máquina)."""

    def aplicar(self, disponivel, exigir):
        ambiente = {'VLADO_EXIGIR_PLAYWRIGHT': '1'} if exigir else {}
        with patch.dict(os.environ, ambiente):
            if not exigir:
                os.environ.pop('VLADO_EXIGIR_PLAYWRIGHT', None)
            decorador = auxiliar_node._pular_ou_exigir(disponivel, 'sem navegador', 'VLADO_EXIGIR_PLAYWRIGHT')

        class Alvo(unittest.TestCase):
            def test_x(self):
                pass
        return decorador(Alvo)

    def executar(self, classe):
        resultado = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(classe).run(resultado)
        return resultado

    def test_disponivel_roda_o_teste(self):
        resultado = self.executar(self.aplicar(True, exigir=True))
        self.assertEqual((resultado.testsRun, len(resultado.skipped), len(resultado.errors)), (1, 0, 0))

    def test_indisponivel_pula_fora_do_ci(self):
        resultado = self.executar(self.aplicar(False, exigir=False))
        self.assertEqual((len(resultado.skipped), len(resultado.errors), len(resultado.failures)), (1, 0, 0))

    def test_indisponivel_falha_no_ci(self):
        resultado = self.executar(self.aplicar(False, exigir=True))
        self.assertEqual(len(resultado.skipped), 0)
        self.assertEqual(len(resultado.errors) + len(resultado.failures), 1)
        mensagem = (resultado.errors + resultado.failures)[0][1]
        self.assertIn('VLADO_EXIGIR_PLAYWRIGHT=1', mensagem)

    def test_decorador_dos_testes_de_navegador_usa_o_caminho_do_cjs(self):
        # O .cjs faz `require` deste mesmo caminho: se divergirem, o teste roda e o roteiro quebra.
        cjs = (TESTES / 'qa_dados_conta.cjs').read_text(encoding='utf-8')
        self.assertIn("'.ferramentas', 'node', 'node_modules', 'playwright'", cjs)
        self.assertEqual(auxiliar_node.PLAYWRIGHT_NODE.parts[-4:], ('.ferramentas', 'node', 'node_modules', 'playwright')[-4:])


class RedeDeSegurancaTest(unittest.TestCase):
    def um_pulado(self, motivo):
        class Alvo(unittest.TestCase):
            def test_x(self):
                pass
        return Alvo('test_x'), motivo

    def test_pulo_por_falta_de_navegador_e_apontado(self):
        pulados = [self.um_pulado('precisa do Node e do Playwright em .ferramentas/node'),
                   self.um_pulado('Chromium não instalado'),
                   self.um_pulado('sem linha de base'),
                   self.um_pulado('Tesseract ausente')]
        apontados = executar_suite.pulos_de_navegador(pulados)
        self.assertEqual([motivo for _, motivo in apontados],
                         ['precisa do Node e do Playwright em .ferramentas/node', 'Chromium não instalado'])


if __name__ == '__main__':
    unittest.main()
