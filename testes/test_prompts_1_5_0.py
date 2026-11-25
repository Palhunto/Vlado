"""Correções de protocolo dos prompts 00, 05 e 06 na 1.5.0 (proposta do MESA.md, contradições I4b, I4c, S1 e S2).

- I4c: uma só fonte de versão, `comum.VERSAO_PROMPTS`, no cabeçalho do FLUXO_COMPLETO.md; os módulos e o README
  dos prompts não escrevem número de versão.
- I4b: o 06 deixa de dizer que não há formulário na tela: a Mesa tem conferência humana na tela, feita por pessoas.
- S1 e S2: o 05 publica a revisão final como `r3_sintese` e avisa que cada revisão tem uma só sucessora.
"""
from pathlib import Path
import re
import sys
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
from comum import PARTES, VERSAO_PROMPTS, conferir_prompts  # noqa: E402

PROMPTS = RAIZ / 'prompts'
VERSAO = re.compile(r'\bv?\d+\.\d+\.\d+\b')


def ler(nome):
    return (PROMPTS / nome).read_text(encoding='utf-8')


class VersaoUnicaTest(unittest.TestCase):
    def test_modulos_e_readme_nao_escrevem_versao(self):
        for nome in (*PARTES, 'README.md'):
            self.assertEqual(VERSAO.findall(ler(nome)), [], nome)

    def test_a_versao_esta_no_cabecalho_do_fluxo(self):
        conferir_prompts(RAIZ)
        self.assertEqual(VERSAO_PROMPTS, '1.5.0')
        self.assertTrue(ler('FLUXO_COMPLETO.md').startswith(f'# Apuracao v1 online - fluxo completo v{VERSAO_PROMPTS}\n'))


class ConferenciaHumanaNaTelaTest(unittest.TestCase):
    def test_06_reconhece_a_conferencia_na_tela_feita_por_pessoas(self):
        texto = ler('06_INCORPORAR_REVISAO_HUMANA.md')
        self.assertNotIn('sem formulários de alteração na tela', texto)
        self.assertIn('a conferência humana também é feita na tela, pelas pessoas da redação', texto)
        self.assertIn('nunca pelo modelo', texto)


class RevisaoFinalTest(unittest.TestCase):
    def test_05_publica_r3_sintese_com_uma_so_sucessora(self):
        texto = ler('05_SINTETIZAR.md')
        self.assertIn('revisão `r3_sintese`', texto)
        self.assertIn('--revisao r3_sintese', texto)
        self.assertIn('Cada revisão tem uma só sucessora', texto)
        # r3_briefing só aparece como o nome das rodadas antigas, que continuam válidas.
        self.assertEqual(texto.count('r3_briefing'), 1)
        self.assertIn('Rodadas antigas com a revisão `r3_briefing` continuam válidas', texto)

    def test_o_nome_e_o_do_fluxo_da_mesa(self):
        from fluxo_codex import REVISAO_DA_ETAPA
        self.assertEqual(REVISAO_DA_ETAPA['sintese'], 'r3_sintese')


if __name__ == '__main__':
    unittest.main()
