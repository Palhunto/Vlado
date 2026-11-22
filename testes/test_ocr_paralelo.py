"""Páginas de OCR em paralelo só dentro da fila de extração (CONF-02, ressalva 27).

Dentro de ``ocr.execucao(paralelo=N, progresso=f)``: até N páginas ao mesmo tempo na conferência
de orientação e no Tesseract direto, ``--jobs N`` no OCRmyPDF e andamento por página. Fora do
bloco tudo continua como antes: uma página por vez, sem ``--jobs``, sem andamento. O bloco vale
só para a thread que o abriu. Sem Tesseract nem OCRmyPDF: a leitura da página e o subprocesso
são simulados; o PDF é sintético.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import ocr  # noqa: E402
from test_extracao_cadastro_pdf import HAS_PYPDF, pdf_sintetico  # noqa: E402

CONFIG = {'habilitado': True, 'idiomas': 'por+eng', 'tesseract': None, 'tessdata': None, 'motor': 'auto',
          'timeout_pagina': 30}


class Medidor:
    """``ler(n)`` that sleeps a moment and records how many calls ran at the same time."""

    def __init__(self, pausa=0.15):
        self.pausa, self.agora, self.maximo = pausa, 0, 0
        self.trava = threading.Lock()
        self.threads = set()

    def __call__(self, numero):
        with self.trava:
            self.agora += 1
            self.maximo = max(self.maximo, self.agora)
            self.threads.add(threading.get_ident())
        try:
            time.sleep(self.pausa)
            return numero * 10
        finally:
            with self.trava:
                self.agora -= 1


class PorPaginaTest(unittest.TestCase):
    def test_fora_da_fila_uma_pagina_por_vez_sem_andamento(self):
        medidor = Medidor(0.02)
        self.assertEqual(ocr._por_pagina([1, 2, 3, 4], medidor, 'paginas'), [10, 20, 30, 40])
        self.assertEqual(medidor.maximo, 1)
        self.assertEqual(medidor.threads, {threading.get_ident()})
        self.assertIsNone(ocr._paralelo())

    def test_dentro_da_fila_ate_n_paginas_na_ordem_com_andamento(self):
        medidor, andamento = Medidor(), []
        with ocr.execucao(paralelo=3, progresso=lambda *a: andamento.append(a)):
            self.assertEqual(ocr._paralelo(), 3)
            resultado = ocr._por_pagina(list(range(1, 9)), medidor, 'orientacao')
        self.assertEqual(resultado, [n * 10 for n in range(1, 9)])
        self.assertEqual(medidor.maximo, 3)
        self.assertEqual(sorted(andamento), [('orientacao', n, 8) for n in range(1, 9)])
        self.assertIsNone(ocr._paralelo())  # the block ended

    def test_bloco_vale_so_para_a_thread_que_o_abriu(self):
        medidor, fora = Medidor(0.05), {}
        with ocr.execucao(paralelo=4):
            outra = threading.Thread(target=lambda: fora.update(p=ocr._paralelo(),
                                                                r=ocr._por_pagina([1, 2, 3], medidor, 'paginas')))
            outra.start()
            outra.join(10)
        self.assertEqual((fora['p'], fora['r'], medidor.maximo), (None, [10, 20, 30], 1))

    def test_erro_no_andamento_nao_interrompe_a_leitura(self):
        def quebra(*_):
            raise RuntimeError('andamento quebrado')
        with ocr.execucao(paralelo=2, progresso=quebra):
            self.assertEqual(ocr._por_pagina([1, 2], Medidor(0.01), 'paginas'), [10, 20])

    def test_paralelo_minimo_e_um(self):
        with ocr.execucao(paralelo=0):
            self.assertIsNone(ocr._paralelo())
        with ocr.execucao(paralelo=-3):
            self.assertEqual(ocr._paralelo(), 1)


class OcrmypdfJobsTest(unittest.TestCase):
    def rodar(self):
        chamadas = []

        def executar(args, *, timeout, env=None):
            chamadas.append(args)
            Path(args[args.index('--sidecar') + 1]).write_text('pagina um\fpagina dois', encoding='utf-8')
            return subprocess.CompletedProcess(args, 0, b'', b'')
        with mock.patch.object(ocr, '_executar', executar):
            paginas = ocr._sidecar_ocrmypdf(Path('sintetico.pdf'), [1, 2], 2, CONFIG)
        self.assertEqual(paginas, {1: 'pagina um', 2: 'pagina dois'})
        (args,) = chamadas
        return args

    def test_jobs_so_dentro_da_fila(self):
        self.assertNotIn('--jobs', self.rodar())
        andamento = []
        with ocr.execucao(paralelo=3, progresso=lambda *a: andamento.append(a)):
            args = self.rodar()
        self.assertEqual(args[args.index('--jobs') + 1], '3')
        self.assertLess(args.index('--jobs'), args.index('--sidecar'))
        self.assertEqual(andamento, [('reconhecimento', 0, 2), ('reconhecimento', 2, 2)])


@unittest.skipUnless(HAS_PYPDF and ocr._pymupdf_disponivel(), 'pypdf e PyMuPDF são necessários')
class MotoresTest(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pdf = pdf_sintetico(Path(pasta.name) / 'paginas.pdf', [f'Pagina sintetica {n}.' for n in range(1, 7)])

    def lendo(self, medidor):
        def pagina_orientada(pagina, numero, config, *, motor_direto):
            medidor(numero)
            return (f'texto {numero}' if motor_direto else None), None
        return mock.patch.object(ocr, '_pagina_orientada', pagina_orientada)

    def test_tesseract_direto_le_paginas_em_paralelo_so_na_fila(self):
        medidor = Medidor()
        with self.lendo(medidor):
            serial = ocr._motor_tesseract(self.pdf, [1, 2, 3, 4], CONFIG)
        self.assertEqual(medidor.maximo, 1)
        medidor, andamento = Medidor(), []
        with self.lendo(medidor), ocr.execucao(paralelo=4, progresso=lambda *a: andamento.append(a)):
            paralelo = ocr._motor_tesseract(self.pdf, [1, 2, 3, 4, 5, 6, 9], CONFIG)
        self.assertGreater(medidor.maximo, 1)
        self.assertLessEqual(medidor.maximo, 4)
        self.assertEqual(serial['paginas'], {n: {'texto': f'texto {n}'} for n in (1, 2, 3, 4)})
        self.assertEqual(list(paralelo['paginas']), [1, 2, 3, 4, 5, 6, 9])
        self.assertIn('inexistente', paralelo['paginas'][9]['erro'])
        self.assertEqual(sorted(a[1] for a in andamento), list(range(1, 8)))
        self.assertEqual({a[0] for a in andamento}, {'paginas'})

    def test_conferencia_de_orientacao_antes_do_ocrmypdf_em_paralelo(self):
        medidor = Medidor()
        with self.lendo(medidor), ocr.execucao(paralelo=3):
            diretas, registros, avisos = ocr._orientar_antes(self.pdf, [1, 2, 3, 4, 5, 6], CONFIG)
        self.assertEqual((diretas, registros, avisos), ({}, {}, {}))
        self.assertEqual(medidor.maximo, 3)


if __name__ == '__main__':
    unittest.main()
