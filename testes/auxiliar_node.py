"""Localiza o Node.js para os testes que dependem dele (A14).

Sem Node o teste é pulado, não falha. Na integração contínua, `VLADO_EXIGIR_NODE=1`
transforma a ausência em falha, para que a suíte nunca passe sem ter rodado o Node.
"""
import os
import shutil


def localizar_node(teste):
    node = shutil.which('node')
    if node is None:
        if os.environ.get('VLADO_EXIGIR_NODE') == '1':
            teste.fail('Node.js é necessário e VLADO_EXIGIR_NODE=1 está definido.')
        teste.skipTest('Node.js não encontrado no PATH.')
    return node


def pular_sem_ocr(disponivel, motivo):
    """Como `unittest.skipUnless`, mas com `VLADO_EXIGIR_OCR=1` a falta do OCR vira falha (Q1).

    Serve a métodos e a classes; no CI o job precisa de Tesseract (por, eng, osd), Ghostscript,
    pngquant e unpaper, como no Dockerfile.
    """
    import functools
    import unittest
    if disponivel:
        return lambda alvo: alvo
    if os.environ.get('VLADO_EXIGIR_OCR') != '1':
        return unittest.skip(motivo)
    mensagem = f'{motivo}, e VLADO_EXIGIR_OCR=1 exige o OCR instalado.'

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


def pular_ou_falhar(teste, variavel, motivo):
    """Pula o teste, ou o reprova quando `variavel=1` (CI): evita job verde sem ter rodado o teste."""
    if os.environ.get(variavel) == '1':
        teste.fail(f'{motivo}, e {variavel}=1 exige que o teste rode.')
    teste.skipTest(motivo)
