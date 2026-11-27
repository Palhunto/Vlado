"""Localiza o Node.js para os testes que dependem dele (A14).

Sem Node o teste é pulado, não falha. Na integração contínua, `VLADO_EXIGIR_NODE=1`
transforma a ausência em falha, para que a suíte nunca passe sem ter rodado o Node.
"""
import os
from pathlib import Path
import shutil


def localizar_node(teste):
    node = shutil.which('node')
    if node is None:
        if os.environ.get('VLADO_EXIGIR_NODE') == '1':
            teste.fail('Node.js é necessário e VLADO_EXIGIR_NODE=1 está definido.')
        teste.skipTest('Node.js não encontrado no PATH.')
    return node


def _pular_ou_exigir(disponivel, motivo, variavel):
    """Como `unittest.skipUnless`, mas com `variavel=1` a falta vira falha: o CI não fica verde sem ter rodado.

    Serve a métodos e a classes."""
    import functools
    import unittest
    if disponivel:
        return lambda alvo: alvo
    if os.environ.get(variavel) != '1':
        return unittest.skip(motivo)
    mensagem = f'{motivo}, e {variavel}=1 exige que o teste rode.'

    def decorador(alvo):
        if isinstance(alvo, type):
            def preparar(cls):
                raise AssertionError(mensagem)
            alvo.setUpClass = classmethod(preparar)
            return alvo

        @functools.wraps(alvo)
        def falhar(self, *args, **kwargs):
            self.fail(mensagem)
        return falhar
    return decorador


def pular_sem_ocr(disponivel, motivo):
    """`unittest.skipUnless` do OCR; com `VLADO_EXIGIR_OCR=1` a falta do OCR vira falha (Q1).

    No CI o job precisa de Tesseract (por, eng, osd), Ghostscript, pngquant e unpaper, como no Dockerfile.
    """
    return _pular_ou_exigir(disponivel, motivo, 'VLADO_EXIGIR_OCR')


# Playwright do Node, onde os roteiros `qa_*.cjs` o procuram (`require` por este caminho). Fica fora do git.
PLAYWRIGHT_NODE = Path(__file__).resolve().parents[1] / '.ferramentas' / 'node' / 'node_modules' / 'playwright'


def navegador_node_disponivel():
    return bool(shutil.which('node')) and PLAYWRIGHT_NODE.is_dir()


def requer_navegador_node(alvo):
    """Decorador dos testes que dirigem um Chromium pelo Playwright do Node (`*_navegador.py`).

    Sem Node ou sem o Playwright em `.ferramentas/node` o teste é pulado na máquina de quem desenvolve; com
    `VLADO_EXIGIR_PLAYWRIGHT=1` (o CI, o mesmo do portão de contraste) ele FALHA. Teste de navegador nenhum pode
    pular em silêncio no CI: um que falhava em 623a620 passou despercebido por isso. Todo módulo de teste que
    abre um navegador usa este decorador ou `VLADO_EXIGIR_PLAYWRIGHT` (conferido por test_navegador_sem_pulo).
    """
    return _pular_ou_exigir(navegador_node_disponivel(), 'precisa do Node e do Playwright em .ferramentas/node',
                            'VLADO_EXIGIR_PLAYWRIGHT')(alvo)


def pular_ou_falhar(teste, variavel, motivo):
    """Pula o teste, ou o reprova quando `variavel=1` (CI): evita job verde sem ter rodado o teste."""
    if os.environ.get(variavel) == '1':
        teste.fail(f'{motivo}, e {variavel}=1 exige que o teste rode.')
    teste.skipTest(motivo)
