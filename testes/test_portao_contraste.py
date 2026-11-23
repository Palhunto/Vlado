"""Portão do WCAG AA nos dois temas (Onda 3): "WCAG AA comprovado por captura".

Roda o medidor de `contraste_wcag.py` nas 14 telas da linha de base da regressão visual, em 375 e 1440 px, nos temas claro e escuro, contra a
Mesa real com dados sintéticos (mesmos servidores da regressão visual; nada de rede externa). Reprova se qualquer texto visível ficar abaixo de
4,5:1 (3:1 se grande), se algum contorno de foco ficar abaixo de 3:1 ou se algum campo ficar sem contorno de 3:1. A única exceção é a declarada em
`contraste_wcag.EXCECOES_CAMPO` (P34: o seletor de apuração do topo não tem caixa; mede-se o texto e a seta). Controles desativados são isentos.

É um módulo da suíte lenta (cerca de 15 minutos: 56 páginas, com o percurso por Tab em cada uma). Precisa de Playwright e do Chromium
(`testes/requirements-teste.txt`, fora da imagem da Mesa): sem eles o teste PULA, a menos que `VLADO_EXIGIR_PLAYWRIGHT=1` (como no CI), quando
FALHA. O relatório fica em tmp/contraste_wcag/relatorio.md; a mesma medição à mão: `python testes/contraste_wcag.py medir`.
"""
import argparse
import os
import unittest

import contraste_wcag as cw

try:
    import playwright  # noqa: F401
    SEM_PLAYWRIGHT = ''
except ImportError:   # pragma: no cover - depende do ambiente
    SEM_PLAYWRIGHT = 'Playwright não instalado (testes/requirements-teste.txt)'

EXIGIR = os.environ.get('VLADO_EXIGIR_PLAYWRIGHT') == '1'
RELATORIO = cw.RAIZ / 'tmp' / 'contraste_wcag'
LINHAS_NA_MENSAGEM = 60


class PortaoContrasteTest(unittest.TestCase):
    def test_telas_da_linha_de_base_cumprem_o_aa_nos_dois_temas(self):
        if SEM_PLAYWRIGHT:
            if EXIGIR:
                self.fail(SEM_PLAYWRIGHT + ' e VLADO_EXIGIR_PLAYWRIGHT=1')
            self.skipTest(SEM_PLAYWRIGHT)
        try:
            dados = cw.medir_tudo(argparse.Namespace(telas=None, larguras=None, temas=None, python_servidor=None))
        except Exception as exc:   # noqa: BLE001 - Chromium ausente ou servidor que não subiu
            if 'Executable doesn' in str(exc) and not EXIGIR:
                self.skipTest('Chromium do Playwright não instalado: ' + str(exc)[:120])
            raise
        relatorio = cw.escrever_relatorio(dados, RELATORIO)
        self.assertEqual(dados['problemas'], [], 'a rodada de medição falhou; veja ' + str(relatorio))
        resumo = cw.resumir(dados)
        linhas = [f'{nome}: {cw._linha_falha(g)}' for nome, r in resumo['por_tela'].items() for g in r['falhas']]
        mostradas = '\n'.join(linhas[:LINHAS_NA_MENSAGEM]) + (f'\n… e mais {len(linhas) - LINHAS_NA_MENSAGEM}' if len(linhas) > LINHAS_NA_MENSAGEM else '')
        self.assertEqual(resumo['totais']['reprovadas'], 0,
                         f"{resumo['totais']['reprovadas']} medidas abaixo do AA (relatório: {relatorio}):\n{mostradas}")
        self.assertGreater(resumo['totais']['medidas'], 3000, 'poucas medidas: o medidor não percorreu as telas')
        self.assertEqual(len(dados['resultados']), 56, 'esperadas 14 telas x 2 larguras x 2 temas')


if __name__ == '__main__':
    unittest.main()
