"""Isolamento da extração (SEG-01): tetos de páginas, pixels, memória, CPU, núcleos e rede.

PDFs hostis sintéticos (muitas páginas, contagem de páginas mentirosa, página gigante em
pixels, imagem bomba de descompressão em XObject e embutida no conteúdo, PNG bomba, PDF com
link e ação para a rede) e o processo de extração com os tetos do sistema. Cada teto é
conferido de verdade: o arquivo que o estoura fica em falha com o motivo, o original é
cadastrado, a fila e a Mesa seguem, e o arquivo seguinte é lido normalmente. Sem rede externa
(só um socket local do próprio teste) nem modelo.
"""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import zlib

TESTES = Path(__file__).resolve().parent
SCRIPTS = TESTES.parent / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import cadastrar_documentos as cadastro  # noqa: E402
from comum import ler_json, sha256  # noqa: E402
from extrair_pdf import extrair_pdf  # noqa: E402
import fila_extracao  # noqa: E402
import tetos_extracao as tetos  # noqa: E402
from test_extracao_cadastro_pdf import HAS_PYPDF, pdf_sintetico  # noqa: E402
import test_fila_extracao as base_fila  # noqa: E402

LINUX = sys.platform.startswith('linux')
LADO_BOMBA = 20000  # 400 megapixels of gray: about 400 MB decoded, a few hundred KB compressed


def zeros_comprimidos(quantidade, linha=None):
    comprimir = zlib.compressobj(9)
    partes, bloco = [], linha or b'\0' * (1 << 20)
    restante = quantidade
    while restante > 0:
        pedaco = bloco if restante >= len(bloco) else bloco[:restante]
        partes.append(comprimir.compress(pedaco))
        restante -= len(pedaco)
    partes.append(comprimir.flush())
    return b''.join(partes)


def pdf_muitas_paginas(caminho, paginas):
    return pdf_sintetico(caminho, [f'Pagina sintetica {n}.' for n in range(1, paginas + 1)])


def pdf_contagem_mentirosa(caminho, declaradas=10_000_000):
    """One page, but the page tree says ``declaradas``: a reader that walked it would never end."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, NumberObject
    pdf_sintetico(caminho, ['Pagina sintetica unica.'])
    escritor = PdfWriter(clone_from=PdfReader(str(caminho)))
    escritor._root_object['/Pages'].get_object()[NameObject('/Count')] = NumberObject(declaradas)
    with open(caminho, 'wb') as saida:
        escritor.write(saida)
    return caminho


def pdf_pagina_gigante(caminho):
    """A blank page of 200 x 200 inches (the largest a PDF allows): 3600 megapixels at 300 dpi."""
    from pypdf import PdfWriter
    escritor = PdfWriter()
    escritor.add_blank_page(width=14400, height=14400)
    with open(caminho, 'wb') as saida:
        escritor.write(saida)
    return caminho


def pdf_imagem_bomba(caminho, embutida=False, lado=LADO_BOMBA):
    """A page with only an image of ``lado`` x ``lado`` gray zeros, Flate-compressed (a decompression bomb)."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, EncodedStreamObject, NameObject, NumberObject
    escritor = PdfWriter()
    pagina = escritor.add_blank_page(width=612, height=792)
    dados = zeros_comprimidos(lado * lado)
    if embutida:
        conteudo = (f'q 612 0 0 792 0 0 cm BI /W {lado} /H {lado} /BPC 8 /CS /G /F [/AHx /Fl] ID '
                    + dados.hex().upper() + '> EI Q').encode('ascii')
    else:
        imagem = EncodedStreamObject()
        imagem._data = dados
        imagem.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                       NameObject('/Width'): NumberObject(lado), NameObject('/Height'): NumberObject(lado),
                       NameObject('/BitsPerComponent'): NumberObject(8),
                       NameObject('/ColorSpace'): NameObject('/DeviceGray'),
                       NameObject('/Filter'): NameObject('/FlateDecode')})
        pagina[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): DictionaryObject(
            {NameObject('/Im0'): escritor._add_object(imagem)})})
        conteudo = b'q 612 0 0 792 0 0 cm /Im0 Do Q'
    fluxo = DecodedStreamObject()
    fluxo.set_data(conteudo)
    pagina[NameObject('/Contents')] = escritor._add_object(fluxo)
    with open(caminho, 'wb') as saida:
        escritor.write(saida)
    return caminho


def pdf_com_rede(caminho, url):
    """Text page with a link annotation, an open action (URI) and JavaScript, all pointing at ``url``."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Link
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject
    pdf_sintetico(caminho, ['Pagina sintetica com link para a rede.'])
    escritor = PdfWriter(clone_from=PdfReader(str(caminho)))
    escritor.add_annotation(0, Link(rect=(10, 10, 200, 40), url=url))
    escritor._root_object[NameObject('/OpenAction')] = DictionaryObject({
        NameObject('/S'): NameObject('/URI'), NameObject('/URI'): TextStringObject(url)})
    escritor.add_js(f'app.launchURL("{url}", true);')
    with open(caminho, 'wb') as saida:
        escritor.write(saida)
    return caminho


def png_bomba(caminho, lado=LADO_BOMBA):
    linhas = zeros_comprimidos(lado * (lado + 1), linha=b'\0' * (lado + 1) * 50)

    def pedaco(tipo, dados):
        return struct.pack('>I', len(dados)) + tipo + dados + struct.pack('>I', zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    Path(caminho).write_bytes(b'\x89PNG\r\n\x1a\n' + pedaco(b'IHDR', struct.pack('>IIBBBBB', lado, lado, 8, 0, 0, 0, 0))
                              + pedaco(b'IDAT', linhas) + pedaco(b'IEND', b''))
    return caminho


def em_processo(codigo, *argumentos, env=None, prazo=60, grupo=False):
    """Run ``codigo`` in a new Python with the scripts on the path; (returncode, stdout, stderr)."""
    opcoes = {'start_new_session': True} if grupo and os.name != 'nt' else {}
    processo = subprocess.run([sys.executable, '-c', codigo, *argumentos], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=prazo, cwd=str(SCRIPTS),
                              env={**os.environ, **(env or {})}, **opcoes)
    return processo.returncode, processo.stdout, processo.stderr


class Escuta:
    """A local TCP server of the test that counts connections (the 'network' a hostile file wants)."""

    def __init__(self, teste):
        self.servidor = socket.socket()
        self.servidor.bind(('127.0.0.1', 0))
        self.servidor.listen(16)
        self.servidor.settimeout(0.2)
        self.porta = self.servidor.getsockname()[1]
        self.conexoes = 0
        self._fim = threading.Event()
        self._thread = threading.Thread(target=self._aceitar, daemon=True)
        self._thread.start()
        teste.addCleanup(self.fechar)

    def _aceitar(self):
        while not self._fim.is_set():
            try:
                conexao, _ = self.servidor.accept()
            except OSError:
                continue
            self.conexoes += 1
            conexao.close()

    def fechar(self):
        self._fim.set()
        self._thread.join(5)
        self.servidor.close()


class TetosTest(unittest.TestCase):
    def test_padroes_para_4_vcpu_e_8_gb_e_variaveis_validadas(self):
        with mock.patch.dict(os.environ, {v: '' for v in tetos.VARIAVEIS.values()}):
            config = tetos.configuracao()
        self.assertEqual({k: config[k] for k in tetos.PADROES}, tetos.PADROES)
        self.assertEqual(config['nucleos'], max(1, (os.cpu_count() or 1) - 1))
        with mock.patch.dict(os.environ, {'VLADO_EXTRACAO_TETO_PAGINAS': 'muitas'}):
            with self.assertRaisesRegex(ValueError, 'VLADO_EXTRACAO_TETO_PAGINAS'):
                fila_extracao.Fila(tempfile.gettempdir())  # a bad cap stops the Mesa's start
        with mock.patch.dict(os.environ, {'VLADO_EXTRACAO_TETO_MEMORIA_MB': '1'}):
            self.assertEqual(tetos.configuracao()['memoria_mb'], 64)

    def test_motivo_da_saida_do_processo(self):
        self.assertIn('teto de CPU', fila_extracao.motivo_da_saida(-24))
        self.assertIn('falta de memória', fila_extracao.motivo_da_saida(-9))
        self.assertIn('violação de acesso', fila_extracao.motivo_da_saida(3221225477))
        self.assertIn('código 7', fila_extracao.motivo_da_saida(7))


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class ArquivosHostisTest(unittest.TestCase):
    """The caps inside the extraction (any mode): checked before any walk, render or OCR."""

    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def extrair(self, origem):
        return extrair_pdf(origem, 'D001', self.pasta / f'{origem.stem}.md')

    def test_muitas_paginas_recusadas_com_motivo_sem_copia(self):
        with mock.patch.dict(os.environ, {'VLADO_EXTRACAO_TETO_PAGINAS': '50'}):
            resultado = self.extrair(pdf_muitas_paginas(self.pasta / 'muitas.pdf', 60))
            normal = self.extrair(pdf_muitas_paginas(self.pasta / 'normal.pdf', 50))
        self.assertEqual((resultado['estado'], resultado['paginas_pdf']), ('erro', 60))
        self.assertIn('60 páginas, acima do teto de 50 páginas', resultado['teto'])
        self.assertEqual(resultado['mensagem'], resultado['teto'])
        self.assertFalse((self.pasta / 'muitas.md').exists())
        self.assertEqual(normal['estado'], 'extraido')

    def test_contagem_declarada_mentirosa_recusada_sem_percorrer_a_arvore(self):
        inicio = time.monotonic()
        resultado = self.extrair(pdf_contagem_mentirosa(self.pasta / 'mentira.pdf'))
        self.assertLess(time.monotonic() - inicio, 5)
        self.assertEqual(resultado['paginas_pdf'], 10_000_000)
        self.assertIn('10000000 páginas', resultado['teto'])

    def test_pagina_gigante_e_imagens_bomba_nao_vao_ao_ocr(self):
        casos = {'gigante': pdf_pagina_gigante(self.pasta / 'gigante.pdf'),
                 'xobject': pdf_imagem_bomba(self.pasta / 'xobject.pdf'),
                 'embutida': pdf_imagem_bomba(self.pasta / 'embutida.pdf', embutida=True)}
        esperado = {'gigante': 'Página 1 a 300 dpi com 60000 x 60000 pixels',
                    'xobject': 'Imagem na página 1 com 20000 x 20000 pixels',
                    'embutida': 'Imagem embutida na página 1 com 20000 x 20000 pixels'}
        motor = mock.Mock(side_effect=AssertionError('página acima do teto enviada ao OCR'))
        with mock.patch('ocr.reconhecer', motor), mock.patch('ocr.diagnostico', return_value={'disponivel': True}):
            for nome, caminho in casos.items():
                with self.subTest(nome):
                    self.assertLess(caminho.stat().st_size, 2_000_000)  # small file, huge when decoded
                    resultado = self.extrair(caminho)
                    self.assertEqual(resultado['estado'], 'erro')
                    self.assertEqual(resultado['paginas_acima_do_teto'], [1])
                    (erro,) = resultado['paginas_com_erro']
                    self.assertIn(esperado[nome], erro['erro'])
                    self.assertIn('não foi enviada ao OCR', erro['erro'])
                    self.assertNotIn('teto', resultado)  # a page cap, not the whole file's
        motor.assert_not_called()

    def test_pagina_normal_ao_lado_da_gigante_segue_para_o_ocr(self):
        from pypdf import PdfReader, PdfWriter
        escritor = PdfWriter()
        escritor.add_blank_page(width=612, height=792)
        for pagina in PdfReader(str(pdf_pagina_gigante(self.pasta / 'g.pdf'))).pages:
            escritor.add_page(pagina)
        mista = self.pasta / 'mista.pdf'
        with open(mista, 'wb') as saida:
            escritor.write(saida)
        lidas = []

        def reconhecer(pdf, paginas):
            lidas.append(list(paginas))
            return {'motor': 'simulado', 'versoes': {}, 'idiomas': 'por', 'paginas': {1: {'texto': 'Texto sintetico OCR'}}}
        with mock.patch('ocr.reconhecer', reconhecer), mock.patch('ocr.diagnostico', return_value={'disponivel': True}):
            resultado = self.extrair(mista)
        self.assertEqual(lidas, [[1]])
        self.assertEqual((resultado['estado'], resultado['paginas_ocr']), ('parcial', [1]))
        self.assertEqual([e['pagina_pdf'] for e in resultado['paginas_com_erro']], [2])

    def test_png_bomba_recusada_antes_do_tesseract(self):
        import ocr
        origem = png_bomba(self.pasta / 'bomba.png')
        self.assertLess(origem.stat().st_size, 2_000_000)
        with mock.patch.object(ocr, 'reconhecer_imagem', side_effect=AssertionError('imagem bomba enviada ao OCR')):
            resultado = ocr.ocr_imagem(origem, 'D001', self.pasta / 'bomba.md')
        self.assertEqual(resultado['estado'], 'erro')
        self.assertIn('Imagem com 20000 x 20000 pixels (400 megapixels), acima do teto de 150', resultado['teto'])
        self.assertFalse((self.pasta / 'bomba.md').exists())

    def test_leitura_visual_da_pagina_dentro_dos_tetos(self):
        try:
            import fitz  # noqa: F401
        except ImportError:
            self.skipTest('PyMuPDF opcional ausente')
        png = tetos.renderizar_png(pdf_muitas_paginas(self.pasta / 'a.pdf', 1), 1)
        largura, altura = struct.unpack('>II', png[16:24])
        self.assertLessEqual(max(largura, altura), tetos.LADO_VISUAL)
        for nome, caminho in (('gigante', pdf_pagina_gigante(self.pasta / 'g.pdf')),
                              ('bomba', pdf_imagem_bomba(self.pasta / 'b.pdf'))):
            with self.subTest(nome), self.assertRaisesRegex(ValueError, 'acima do teto de 150 megapixels'):
                tetos.renderizar_png(caminho, 1)
        with self.assertRaisesRegex(ValueError, 'Página fora do PDF'):
            tetos.renderizar_png(pdf_contagem_mentirosa(self.pasta / 'm.pdf', 3), 3)

    def test_memoria_esgotada_vira_teto_do_arquivo(self):
        origem = pdf_muitas_paginas(self.pasta / 'a.pdf', 1)
        tarefa = {'lote': '0' * 32, 'indice': 0, 'tipo': 'pdf', 'origem': str(origem),
                  'destino': str(self.pasta / 'derivados/0/D001_texto_pdf.md'), 'identificador': 'D001'}
        with mock.patch.object(cadastro, 'extrair_pdf', side_effect=MemoryError):
            saida = cadastro.extrair_item(tarefa, base=self.pasta)
        self.assertIn('teto de memória', saida['teto'])
        self.assertEqual((saida['resultado']['estado'], saida['derivado']), ('erro', None))


class ProcessoIsoladoTest(unittest.TestCase):
    """The operating-system caps of the extraction process (trabalhador_extracao.aplicar_limites)."""

    APLICAR = ('import json, sys, trabalhador_extracao as t; aplicado = t.aplicar_limites(); '
               'print(json.dumps(aplicado, ensure_ascii=False), flush=True); ')

    def test_teto_de_memoria_vale(self):
        alocar = 'b = bytearray(256 * 1024 * 1024); print("alocou", flush=True)'
        codigo, saida, _ = em_processo(alocar)
        self.assertEqual((codigo, saida.strip()), (0, 'alocou'))  # without the caps it fits
        codigo, saida, erro = em_processo(self.APLICAR + alocar, env={'VLADO_EXTRACAO_TETO_MEMORIA_MB': '128'})
        self.assertNotEqual(codigo, 0)
        self.assertNotIn('alocou', saida)
        self.assertIn('MemoryError', erro)
        aplicado = json.loads(saida.splitlines()[0])
        self.assertIn('128 MB', aplicado['memoria'])

    def test_teto_de_cpu_encerra_com_motivo(self):
        vigiar = ('t.vigiar_cpu(t.tetos.configuracao(), lambda m: print(json.dumps(m, ensure_ascii=False), flush=True))\n'
                  'while True: sum(range(10000))')
        inicio = time.monotonic()
        codigo, saida, _ = em_processo(self.APLICAR + vigiar, env={'VLADO_EXTRACAO_TETO_CPU_S': '1'}, grupo=True)
        self.assertLess(time.monotonic() - inicio, 30)
        self.assertIn(codigo, (5, -9))  # POSIX ends its own group with signal 9
        mensagem = json.loads(saida.splitlines()[-1])
        self.assertEqual(mensagem['tipo'], 'limite')
        self.assertIn('teto de 1 s de CPU', mensagem['mensagem'])

    def test_nucleos_e_prioridade(self):
        codigo, saida, _ = em_processo(self.APLICAR)
        self.assertEqual(codigo, 0)
        aplicado = json.loads(saida.splitlines()[0])
        self.assertTrue(aplicado['prioridade'])
        if (os.cpu_count() or 1) > 1:
            self.assertTrue(aplicado['nucleos'])
            self.assertNotIn(0, aplicado['nucleos'])  # core 0 stays for the Mesa
            self.assertLessEqual(len(aplicado['nucleos']), tetos.configuracao()['nucleos'])

    def test_rede_recusada_no_processo(self):
        escuta = Escuta(self)
        conectar = ('import socket\n'
                    'for como in ("socket", "_socket"):\n'
                    '    try:\n'
                    '        if como == "socket":\n'
                    '            socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=3).close()\n'
                    '        else:\n'
                    '            import _socket\n'
                    '            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM); s.settimeout(3)\n'
                    '            s.connect(("127.0.0.1", int(sys.argv[1]))); s.close()\n'
                    '        print(como, "conectou", flush=True)\n'
                    '    except OSError as exc:\n'
                    '        print(como, "recusada", exc, flush=True)\n')
        codigo, saida, _ = em_processo('import sys\n' + conectar, str(escuta.porta))
        self.assertIn('socket conectou', saida)  # control: the test's server accepts
        codigo, saida, erro = em_processo(self.APLICAR + '\n' + conectar, str(escuta.porta))
        self.assertEqual(codigo, 0, erro)
        self.assertIn('socket recusada', saida)
        self.assertIn('_socket recusada', saida)
        aplicado = json.loads(saida.splitlines()[0])
        if LINUX:
            self.assertTrue(aplicado['rede'][0].startswith('seccomp'), aplicado)

    @unittest.skipUnless(LINUX, 'No Windows o bloqueio de rede é só do Python do processo (declarado)')
    def test_rede_recusada_tambem_nos_filhos_no_linux(self):
        escuta = Escuta(self)
        filho = ('import subprocess\n'
                 'r = subprocess.run([sys.executable, "-c", "import socket, sys; '
                 'socket.create_connection((\'127.0.0.1\', int(sys.argv[1])), timeout=3)", sys.argv[1]], '
                 'capture_output=True, text=True)\n'
                 'print("filho", r.returncode, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "", flush=True)')
        codigo, saida, erro = em_processo(self.APLICAR + '\n' + filho, str(escuta.porta))
        self.assertEqual(codigo, 0, erro)
        self.assertIn('Permission', saida)  # EACCES from the kernel filter, not from Python
        self.assertEqual(escuta.conexoes, 0)

    def test_filhos_morrem_com_o_processo_de_extracao(self):
        neto = ('import subprocess\n'
                'p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])\n'
                'print(p.pid, flush=True)\n'
                't._encerrar_tudo(3)')
        codigo, saida, _ = em_processo(self.APLICAR + '\n' + neto, grupo=True)
        pid = int(saida.splitlines()[-1])
        base_fila.esperar(lambda: not base_fila.vivo(pid), 10, 'o filho sobreviveu ao processo de extração')


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class FilaComArquivosHostisTest(base_fila.Base):
    """The queue in 'processos' mode: a hostile file fails with its reason; the rest goes on."""
    modo = 'processos'

    def lote(self, arquivos, fila=None, **opcoes):
        fila = fila or self.fila
        lote = fila.receber('alpha', base_fila.gravador(*[(Path(c).name, Path(c).read_bytes()) for c in arquivos]),
                            natureza='sinteticos', **opcoes)
        return lote, fila.aguardar(lote, 180), fila.consultar(lote=lote)['lote']['arquivos']

    def test_teto_de_paginas_e_pixels_sem_derrubar_o_lote(self):
        pasta = self.arquivos
        with mock.patch.dict(os.environ, {'VLADO_EXTRACAO_TETO_PAGINAS': '50'}):
            fila = self.nova_fila()
            lote, resposta, arquivos = self.lote([
                pdf_muitas_paginas(pasta / 'muitas.pdf', 60), pdf_imagem_bomba(pasta / 'bomba.pdf'),
                pdf_pagina_gigante(pasta / 'gigante.pdf'), pdf_muitas_paginas(pasta / 'normal.pdf', 3)], fila)
        estados = {a['nome']: (a['estado'], a['extracao'], a['tentativas']) for a in arquivos}
        self.assertEqual(estados['muitas.pdf'], ('falha', 'erro', 0))  # whole file: no retry
        self.assertIn('acima do teto de 50 páginas', arquivos[0]['motivo'])
        self.assertEqual(estados['bomba.pdf'], ('pronto', 'erro', 0))  # its only page refused, reason in the receipt
        self.assertEqual(estados['gigante.pdf'], ('pronto', 'erro', 0))
        self.assertEqual(estados['normal.pdf'], ('pronto', 'extraido', 0))
        self.assertEqual((resposta['novos'], resposta['corpus_id']), (4, 'alpha_v2'))
        documentos = {d['nome_recebido']: d for d in self.documentos()}
        self.assertIn('acima do teto de 50 páginas', documentos['muitas.pdf']['extracao_pdf']['mensagem'])
        self.assertEqual(sha256(self.root / documentos['muitas.pdf']['arquivo']), sha256(pasta / 'muitas.pdf'))
        self.assertIn('não foi enviada ao OCR', documentos['bomba.pdf']['extracao_pdf']['paginas_com_erro'][0]['erro'])
        self.assertEqual(documentos['normal.pdf']['extracao_pdf']['paginas_pdf'], 3)

    def test_png_bomba_fica_em_falha_com_motivo(self):
        lote, resposta, arquivos = self.lote([png_bomba(self.arquivos / 'bomba.png')], ocr_imagens=True)
        self.assertEqual((arquivos[0]['estado'], arquivos[0]['extracao']), ('falha', 'erro'))
        self.assertIn('400 megapixels', arquivos[0]['motivo'])
        self.assertEqual(resposta['novos'], 1)

    def test_teto_de_cpu_falha_o_arquivo_e_a_fila_segue(self):
        with mock.patch.dict(os.environ, {'VLADO_EXTRACAO_TETO_CPU_S': '2'}):
            fila = self.nova_fila()
            pesado = base_fila.pdf_pesado(self.arquivos / 'pesado.pdf')  # about 15 s of CPU
            lote, resposta, arquivos = self.lote([pesado, pdf_muitas_paginas(self.arquivos / 'leve.pdf', 2)], fila)
            self.assertEqual((arquivos[0]['estado'], arquivos[0]['extracao'], arquivos[0]['tentativas']), ('falha', 'erro', 0))
            self.assertIn('teto de 2 s de CPU', arquivos[0]['motivo'])
            self.assertEqual(arquivos[1]['estado'], 'pronto')
            self.assertEqual(resposta['novos'], 2)
            # The next batch is read normally by a new process.
            lote, resposta, arquivos = self.lote([pdf_muitas_paginas(self.arquivos / 'depois.pdf', 3)], fila)  # not a duplicate
        self.assertEqual((arquivos[0]['estado'], arquivos[0]['extracao']), ('pronto', 'extraido'))

    def test_um_processo_por_arquivo(self):
        lote = self.fila.receber('alpha', base_fila.gravador(*[(f'{n}.pdf', base_fila.pdf(self.arquivos, f'{n}.pdf', marca=str(n)))
                                                               for n in range(3)]), natureza='sinteticos')
        processos = set()
        limite = time.monotonic() + 120
        while time.monotonic() < limite:
            estado = base_fila.interno(self.root, lote)
            processos.update(a.get('processo') for a in estado.get('arquivos', []) if a.get('processo'))
            if estado.get('estado') == 'publicado':
                break
            time.sleep(0.01)
        self.assertEqual(self.fila.aguardar(lote, 5)['novos'], 3)
        self.assertEqual(len(processos), 3, processos)

    def test_pdf_com_link_para_a_rede_nao_abre_conexao(self):
        escuta = Escuta(self)
        url = f'http://127.0.0.1:{escuta.porta}/sintetico'
        lote, resposta, arquivos = self.lote([pdf_com_rede(self.arquivos / 'link.pdf', url)])
        self.assertEqual((arquivos[0]['estado'], arquivos[0]['extracao']), ('pronto', 'extraido'))
        time.sleep(0.5)
        self.assertEqual(escuta.conexoes, 0)

    def test_leitura_visual_no_processo_isolado(self):
        try:
            import fitz  # noqa: F401
        except ImportError:
            self.skipTest('PyMuPDF opcional ausente')
        png = self.fila.renderizar_pagina(pdf_muitas_paginas(self.arquivos / 'a.pdf', 2), 2)
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        with self.assertRaisesRegex(ValueError, 'acima do teto de 150 megapixels'):
            self.fila.renderizar_pagina(pdf_imagem_bomba(self.arquivos / 'b.pdf'), 1)
        aqui = mock.Mock(side_effect=AssertionError('renderizado no processo da Mesa'))
        with mock.patch.object(tetos, 'renderizar_png', aqui):
            self.fila.renderizar_pagina(self.arquivos / 'a.pdf', 1)
        aqui.assert_not_called()

    def test_mesa_liga_a_leitura_visual_da_apuracao_ao_processo_isolado(self):
        from interface_pesquisa import Servidor
        server = Servidor(('127.0.0.1', 0), self.root, extracao='processos')
        self.addCleanup(server.server_close)
        self.assertEqual(server.conversas.renderizar_pagina, server.fila.renderizar_pagina)


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class MesaComArquivosHostisTest(base_fila.Base):
    def test_mesa_segue_de_pe_depois_de_um_lote_hostil(self):
        import base64
        from test_trava_queda import Mesa
        self.fila.encerrar(0)
        pasta = self.arquivos
        hostis = [pdf_contagem_mentirosa(pasta / 'mentira.pdf'), pdf_imagem_bomba(pasta / 'embutida.pdf', embutida=True),
                  pdf_pagina_gigante(pasta / 'gigante.pdf')]
        with mock.patch.dict(os.environ, {'VLADO_EXTRACAO_TETO_CPU_S': '30'}):
            mesa = Mesa(self, self.root, '--extracao', 'processos')
        arquivos = [{'nome': c.name, 'base64': base64.b64encode(c.read_bytes()).decode('ascii')} for c in hostis]
        status, recibo = mesa.post('cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos', 'arquivos': arquivos}, prazo=180)
        self.assertEqual((status, recibo.get('novos')), (200, 3), recibo)
        estados = {a['nome']: a['estado'] for a in mesa.fila()[0]['arquivos']}
        self.assertEqual(estados, {'mentira.pdf': 'falha', 'embutida.pdf': 'pronto', 'gigante.pdf': 'pronto'})
        self.assertEqual(mesa.saude(), 200)
        texto = base64.b64encode(b'Documento sintetico depois do lote hostil.').decode('ascii')
        status, recibo = mesa.post('cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos',
                                                 'arquivos': [{'nome': 'depois.txt', 'base64': texto}]})
        self.assertEqual((status, recibo.get('novos')), (200, 1), recibo)
        self.assertEqual(ler_json(self.root / 'casos/alpha/manifesto.json')['corpus_id'], 'alpha_v3')
        mesa.desligar(self)


if __name__ == '__main__':
    unittest.main()
