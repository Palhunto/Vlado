"""Fila de extração da Mesa (CONF-02), com dados sintéticos; sem rede nem modelo.

Cobre: lote publicado com IDs finais e cópia de trabalho igual à extração direta (nenhum
identificador provisório sobra); estado por arquivo e envio assíncrono sem prender a trava de
cadastro; caso levado à lixeira durante a leitura; lotes concorrentes que recalculam IDs e
duplicatas na publicação; queda do coordenador (o arquivo volta à fila uma vez e, na segunda,
fica em falha com o original cadastrado); publicação cortada concluída sem duplicar; lote órfão
publicado de novo; lote ilegível recusado sem parar a fila; encerramento que devolve o arquivo
sem contar tentativa; primeira pergunta recusada e pergunta seguinte esperando o lote; rota
assíncrona e ``GET /api/fila``. No modo
``processos``: a extração roda em outro processo; processo morto duas vezes; prazo estourado;
Mesa morta no meio, com o processo de extração saindo pelo vigia e a partida retomando o lote.
"""
import base64
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import cadastrar_documentos as cadastro  # noqa: E402
import erros  # noqa: E402
from comum import ler_json, sha256  # noqa: E402
from extrair_pdf import extrair_pdf  # noqa: E402
import fila_extracao  # noqa: E402
import lixeira  # noqa: E402
from selecionar_caso import selecionar  # noqa: E402
import test_registros as fixtures  # noqa: E402
from test_extracao_cadastro_pdf import HAS_PYPDF, pdf_sintetico  # noqa: E402
import trava_cadastro  # noqa: E402

AUXILIAR = TESTES / 'apoio_trava_processo.py'


def esperar(condicao, prazo=30, mensagem='condição não atingida'):
    limite = time.monotonic() + prazo
    while True:
        valor = condicao()
        if valor:
            return valor
        if time.monotonic() > limite:
            raise AssertionError(mensagem)
        time.sleep(0.02)


def gravador(*arquivos):
    """``gravar(pasta)`` for ``Fila.receber``: writes ``(nome, bytes)`` pairs, one folder each."""
    def gravar(pasta):
        caminhos = []
        for numero, (nome, conteudo) in enumerate(arquivos):
            destino = Path(pasta) / str(numero) / nome
            destino.parent.mkdir(parents=True)
            destino.write_bytes(conteudo)
            caminhos.append(destino)
        return caminhos
    return gravar


def pdf(pasta, nome, paginas=1, marca='Marcador'):
    """Synthetic PDF with native text on every page (no OCR is ever needed)."""
    return pdf_sintetico(Path(pasta) / nome, [f'{marca} sintetico, pagina {n}.' for n in range(1, paginas + 1)]).read_bytes()


def pdf_pesado(caminho, paginas=60, linhas=2000):
    """Synthetic PDF that pypdf reads slowly: ``linhas`` text operators per page, compressed.

    60 pages of 2000 operators: about 15 s of extraction on one core, 630 KB. Every page says it
    is synthetic; no OCR is needed.
    """
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    fonte = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                                 NameObject('/Subtype'): NameObject('/Type1'),
                                                 NameObject('/BaseFont'): NameObject('/Helvetica')}))
    corpo = ''.join(f'BT /F1 2 Tf 5 {i % 290 + 5} Td (Linha sintetica {i} do documento pesado.) Tj ET\n'
                    for i in range(linhas)).encode('ascii')
    for numero in range(1, paginas + 1):
        pagina = writer.add_blank_page(width=300, height=300)
        pagina[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): fonte})})
        conteudo = DecodedStreamObject()
        conteudo.set_data(corpo + f'BT /F1 12 Tf 20 200 Td (Pagina sintetica {numero}) Tj ET'.encode('ascii'))
        pagina[NameObject('/Contents')] = writer._add_object(conteudo)
        pagina.compress_content_streams()
    writer.write(caminho)
    return Path(caminho)


def interno(root, lote):
    """The queue's own state file (``processo`` and paths included, unlike the public state)."""
    return fila_extracao._ler(fila_extracao.pasta_fila(root) / lote / 'estado.json') or {}


def vivo(pid):
    if os.name == 'nt':
        import ctypes
        alca = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not alca:
            return False
        try:
            codigo = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(alca, ctypes.byref(codigo))
            return codigo.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(alca)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a dead child not yet reaped is not running
        with open(f'/proc/{pid}/stat', encoding='ascii') as estado:
            return estado.read().split(')')[-1].split()[0] != 'Z'
    except OSError:
        return True


def matar(pid):
    if os.name == 'nt':
        os.kill(pid, 9)  # TerminateProcess
    else:
        os.kill(pid, 9)


class Bloqueio:
    """Replaces ``cadastrar_documentos.extrair_item`` (local mode): each call reports progress,
    signals ``dentro`` and waits for ``soltar`` before extracting for real."""

    def __init__(self):
        self.dentro, self.soltar = threading.Event(), threading.Event()
        self.chamadas = 0
        self.original = cadastro.extrair_item

    def __call__(self, tarefa, **kwargs):
        self.chamadas += 1
        if kwargs.get('progresso'):
            kwargs['progresso']('texto', 1, 3)
        self.dentro.set()
        if not self.soltar.wait(30):
            raise AssertionError('extração bloqueada além do prazo do teste')
        return self.original(tarefa, **kwargs)


class Base(unittest.TestCase):
    modo = 'local'

    def setUp(self):
        self.fixture = fixtures.RegistrosTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        selecionar(self.root, None)
        cadastro.cadastrar(self.root, 'alpha', [self.root / 'fonte.txt'], novo=True, titulo='Caso sintético',
                           natureza='sinteticos')
        self.manifesto = self.root / 'casos/alpha/manifesto.json'
        self.arquivos = Path(tempfile.mkdtemp(prefix='fila_fontes_'))
        self.addCleanup(shutil.rmtree, self.arquivos, True)
        self.fila = self.nova_fila()

    def nova_fila(self, **config):
        fila = fila_extracao.Fila(self.root, self.modo, **config)
        self.addCleanup(fila.encerrar, 15)  # before the folder is removed (LIFO)
        return fila

    @contextmanager
    def bloqueado(self):
        bloqueio = Bloqueio()
        with mock.patch.object(cadastro, 'extrair_item', bloqueio):
            try:
                yield bloqueio
            finally:
                bloqueio.soltar.set()

    def publico(self, lote, fila=None):
        return (fila or self.fila).consultar(lote=lote)['lote']

    def esperar_estado(self, lote, condicao, prazo=30, mensagem='estado do lote não atingido'):
        return esperar(lambda: (lambda e: e if condicao(e) else None)(interno(self.root, lote)), prazo,
                       mensagem)

    def documentos(self):
        return ler_json(self.manifesto)['documentos']

    def sem_provisorio(self):
        """No provisional identifier left in names or bytes of the case."""
        for caminho in (self.root / 'casos').rglob('*'):
            if fila_extracao.PASTA in caminho.parts:
                continue
            self.assertNotIn('PROVISORIO', caminho.name)
            if caminho.is_file():
                self.assertNotIn(b'PROVISORIO', caminho.read_bytes(), caminho)


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class FilaLocalTest(Base):
    def test_lote_publicado_tem_ids_finais_e_copia_igual_a_extracao_direta(self):
        conteudo = pdf(self.arquivos, 'relatorio.pdf', 2)
        texto = 'Nota sintética da fila.'.encode('utf-8')
        lote = self.fila.receber('alpha', gravador(('relatorio.pdf', conteudo), ('nota.txt', texto)),
                                 natureza='sinteticos')
        resposta = self.fila.aguardar(lote, 60)
        self.assertEqual((resposta['novos'], resposta['duplicados'], resposta['corpus_id']), (2, 0, 'alpha_v2'))
        self.assertEqual(resposta['arquivo_recibo'], f'casos/alpha/cadastros/{lote}/recibo.json')
        self.assertEqual([a['documento_id'] for a in resposta['arquivos']], ['D002', 'D003'])
        doc = next(d for d in self.documentos() if d['id'] == 'D002')
        # The working copy has exactly the bytes of a direct extraction with the final identifier,
        # as before the queue (the original was read already named D002_<name>).
        direta, original = self.arquivos / 'direta.md', self.arquivos / 'D002_relatorio.pdf'
        original.write_bytes(conteudo)
        esperado = extrair_pdf(original, 'D002', direta)
        self.assertEqual(doc['extracao_pdf'], json.loads(json.dumps(esperado)))
        (derivado,) = doc['derivados']
        self.assertEqual(derivado['arquivo'], f'casos/alpha/cadastros/{lote}/derivados/D002_texto_pdf.md')
        self.assertEqual(sha256(self.root / derivado['arquivo']), sha256(direta))
        self.assertEqual(sha256(self.root / doc['arquivo']), sha256(original))
        self.sem_provisorio()
        # The batch keeps only its record in the queue; the published batch has its own files.
        pasta = fila_extracao.pasta_fila(self.root) / lote
        esperar(lambda: sorted(p.name for p in pasta.iterdir()) == ['estado.json', 'pedido.json', 'resposta.json'],
                10, 'as cópias do lote publicado ficaram na fila')
        estado = self.publico(lote)
        self.assertEqual((estado['estado'], estado['total'], estado['prontos']), ('publicado', 2, 2))
        self.assertEqual([a['extracao'] for a in estado['arquivos']], ['extraido', 'nao_necessaria'])
        self.assertEqual(estado['recibo']['corpus_id'], 'alpha_v2')
        self.assertEqual(fila_extracao.pendentes(self.root), [])
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')

    def test_envio_assincrono_mostra_estado_por_arquivo_e_nao_prende_as_travas(self):
        with self.bloqueado() as bloqueio:
            lote = self.fila.receber('alpha', gravador(('longo.pdf', pdf(self.arquivos, 'longo.pdf', 3)),
                                                       ('nota.txt', b'Nota sintetica.')), natureza='sinteticos')
            self.assertTrue(bloqueio.dentro.wait(10))
            self.esperar_estado(lote, lambda e: e['arquivos'][0].get('pagina') == 1)
            estado = self.publico(lote)
            self.assertEqual((estado['estado'], estado['total'], estado['prontos']), ('processando', 2, 1))
            self.assertEqual({k: estado['arquivos'][0][k] for k in ('nome', 'estado', 'etapa', 'pagina', 'paginas')},
                             {'nome': 'longo.pdf', 'estado': 'extraindo', 'etapa': 'texto', 'pagina': 1, 'paginas': 3})
            self.assertEqual((estado['arquivos'][1]['estado'], estado['arquivos'][1]['extracao']), ('pronto', 'nao_necessaria'))
            self.assertNotIn('processo', estado['arquivos'][0])  # internal only
            self.assertNotIn(str(self.root), json.dumps(estado, ensure_ascii=False))
            self.assertEqual(fila_extracao.pendentes(self.root, 'alpha'), [lote])
            self.assertEqual(fila_extracao.pendentes(self.root, 'beta'), [])
            # While the file is read nobody holds the cadastro lock: another cadastro goes through.
            self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')
            inicio = time.monotonic()
            outro = self.arquivos / 'outro.txt'
            outro.write_text('Outro documento sintético, cadastrado durante a leitura.', encoding='utf-8')
            recibo = cadastro.cadastrar(self.root, 'alpha', [outro], natureza='sinteticos')
            self.assertLess(time.monotonic() - inicio, 5)
            self.assertEqual((recibo['novos'], recibo['corpus_id'], recibo['arquivos'][0]['documento_id']),
                             (1, 'alpha_v2', 'D002'))
            bloqueio.soltar.set()
            resposta = self.fila.aguardar(lote, 60)
        # Published against the manifest of that moment: the IDs follow the other cadastro.
        self.assertEqual([a['documento_id'] for a in resposta['arquivos']], ['D003', 'D004'])
        self.assertEqual(resposta['corpus_id'], 'alpha_v3')
        self.sem_provisorio()

    def test_caso_na_lixeira_durante_a_leitura_recusa_o_lote_sem_publicar(self):
        antes = self.manifesto.read_bytes()
        with self.bloqueado() as bloqueio:
            lote = self.fila.receber('alpha', gravador(('a.pdf', pdf(self.arquivos, 'a.pdf'))), natureza='sinteticos')
            self.assertTrue(bloqueio.dentro.wait(10))
            lixeira.adicionar(self.root, 'caso', 'alpha', 'Caso sintético')
            bloqueio.soltar.set()
            with self.assertRaisesRegex(ValueError, 'lixeira'):
                self.fila.aguardar(lote, 60)
        estado = self.publico(lote)
        self.assertEqual(estado['estado'], 'falha')
        self.assertIn('lixeira', estado['motivo'])
        self.assertIsNone(estado['recibo'])
        self.assertEqual(self.manifesto.read_bytes(), antes)
        self.assertEqual(len(list((self.root / 'casos/alpha/cadastros').iterdir())), 1)
        pasta = fila_extracao.pasta_fila(self.root) / lote
        esperar(lambda: not ((pasta / 'originais').exists() or (pasta / 'derivados').exists()), 10)
        self.assertEqual(fila_extracao.pendentes(self.root), [])

    def test_lotes_concorrentes_recalculam_ids_e_duplicatas(self):
        comum = pdf(self.arquivos, 'comum.pdf', marca='Comum')
        with self.bloqueado() as bloqueio:
            primeiro = self.fila.receber('alpha', gravador(('x.pdf', pdf(self.arquivos, 'x.pdf', marca='X')),
                                                           ('comum.pdf', comum)), natureza='sinteticos')
            segundo = self.fila.receber('alpha', gravador(('y.pdf', pdf(self.arquivos, 'y.pdf', marca='Y')),
                                                          ('comum.pdf', comum)), natureza='sinteticos')
            # Both were planned against the same manifest: each thinks it brings comum.pdf.
            for lote in (primeiro, segundo):
                pedido = ler_json(fila_extracao.pasta_fila(self.root) / lote / 'pedido.json')
                self.assertEqual([i['novo'] for i in pedido['itens']], [True, True])
            bloqueio.soltar.set()
            r1, r2 = self.fila.aguardar(primeiro, 60), self.fila.aguardar(segundo, 60)
        self.assertEqual([(a['documento_id'], a['estado']) for a in r1['arquivos']],
                         [('D002', 'cadastrado'), ('D003', 'cadastrado')])
        self.assertEqual([(a['documento_id'], a['estado']) for a in r2['arquivos']],
                         [('D004', 'cadastrado'), ('D003', 'duplicado')])
        self.assertEqual((r1['corpus_id'], r2['corpus_id'], r2['novos'], r2['duplicados']), ('alpha_v2', 'alpha_v3', 1, 1))
        documentos = {d['id']: d for d in self.documentos()}
        self.assertEqual(sorted(documentos), ['D001', 'D002', 'D003', 'D004'])
        # The duplicate kept the copy of its first batch; the second batch's copy was not used.
        self.assertEqual([Path(d['arquivo']).parent.parent.name for d in documentos['D003']['derivados']], [primeiro])
        self.assertFalse((self.root / f'casos/alpha/cadastros/{segundo}/originais/D003_comum.pdf').exists())
        self.sem_provisorio()

    def test_queda_do_coordenador_le_de_novo_e_na_segunda_vez_fica_em_falha(self):
        def deixado_por_coordenador_morto(nome, tentativas):
            with mock.patch.object(fila_extracao.Fila, 'iniciar'):  # nobody coordinates
                lote = self.fila.receber('alpha', gravador((nome, pdf(self.arquivos, nome, marca=nome))),
                                         natureza='sinteticos')
            caminho = fila_extracao.pasta_fila(self.root) / lote / 'estado.json'
            estado = ler_json(caminho)
            estado['estado'] = 'processando'
            estado['arquivos'][0].update(estado='extraindo', etapa='texto', pagina=1, paginas=1, processo=999999,
                                         tentativas=tentativas)
            caminho.write_text(json.dumps(estado), encoding='utf-8')
            return lote

        uma = deixado_por_coordenador_morto('uma.pdf', 0)
        duas = deixado_por_coordenador_morto('duas.pdf', 1)
        self.assertEqual(sorted(fila_extracao.pendentes(self.root)), sorted([uma, duas]))
        nova = self.nova_fila()
        nova.iniciar()
        r1, r2 = nova.aguardar(uma, 60), nova.aguardar(duas, 60)
        # First loss: read again, published with its copy.
        estado = self.publico(uma, nova)['arquivos'][0]
        self.assertEqual((estado['estado'], estado['tentativas'], estado['extracao']), ('pronto', 1, 'extraido'))
        # Second loss: the file fails, the original is registered with the extraction in error.
        estado = self.publico(duas, nova)['arquivos'][0]
        self.assertEqual((estado['estado'], estado['tentativas'], estado['extracao']), ('falha', 2, 'erro'))
        self.assertIn('interrompido por uma queda', estado['motivo'])
        documentos = {d['nome_recebido']: d for d in self.documentos()}
        self.assertEqual(documentos['uma.pdf']['extracao_pdf']['estado'], 'extraido')
        falha = documentos['duas.pdf']
        self.assertEqual((falha['extracao_pdf']['estado'], falha['derivados']), ('erro', []))
        self.assertIn('Tentativas: 2', falha['extracao_pdf']['mensagem'])
        self.assertTrue((self.root / falha['arquivo']).is_file())
        self.assertEqual(r2['novos'], 1)
        self.sem_provisorio()

    def test_publicacao_interrompida_e_concluida_sem_duplicar(self):
        catalogo = self.root / 'casos/catalogo.json'
        antes = catalogo.read_bytes()
        original = fila_extracao.publicar_lote

        def queda(*args, **kwargs):
            original(*args, **kwargs)
            catalogo.write_bytes(antes)  # cut between the manifest and the catalog
            raise SystemExit  # the coordinator dies here, as in a crash
        with mock.patch.object(fila_extracao, 'publicar_lote', queda):
            lote = self.fila.receber('alpha', gravador(('a.pdf', pdf(self.arquivos, 'a.pdf'))), natureza='sinteticos')
            self.esperar_estado(lote, lambda e: e['estado'] == 'publicando' and
                                not self.fila._thread.is_alive())
        self.fila._dono.soltar()  # the system releases a dead process's lock
        registros = ler_json(self.manifesto)['registros_cadastro']
        self.assertEqual(registros[-1]['arquivo'], f'casos/alpha/cadastros/{lote}/recibo.json')
        self.assertEqual(catalogo.read_bytes(), antes)
        nova = self.nova_fila()
        nova.iniciar()
        resposta = nova.aguardar(lote, 60)
        self.assertEqual((resposta['novos'], resposta['corpus_id']), (1, 'alpha_v2'))
        self.assertEqual(ler_json(self.manifesto)['registros_cadastro'], registros)  # not published twice
        entrada = next(c for c in ler_json(catalogo)['casos'] if c['id'] == 'alpha')
        self.assertEqual(entrada['documentos'], 2)
        self.assertEqual(len(list((self.root / 'casos/alpha/cadastros').iterdir())), 2)
        self.assertEqual(self.publico(lote, nova)['estado'], 'publicado')

    def test_lote_orfao_e_publicado_de_novo(self):
        def queda(root, plano, base, resultados):
            orfao = Path(root) / f'casos/{plano["caso"]}/cadastros/{plano["lote"]}'
            orfao.mkdir(parents=True)
            (orfao / 'recibo.json').write_text('{"cortado": true}', encoding='utf-8')
            raise SystemExit  # renamed into place, then cut before the manifest named it
        antes = self.manifesto.read_bytes()
        with mock.patch.object(fila_extracao, 'publicar_lote', queda):
            lote = self.fila.receber('alpha', gravador(('a.pdf', pdf(self.arquivos, 'a.pdf'))), natureza='sinteticos')
            self.esperar_estado(lote, lambda e: e['estado'] == 'publicando' and not self.fila._thread.is_alive())
        self.fila._dono.soltar()
        self.assertEqual(self.manifesto.read_bytes(), antes)
        nova = self.nova_fila()
        nova.iniciar()
        resposta = nova.aguardar(lote, 60)
        self.assertEqual((resposta['novos'], resposta['corpus_id']), (1, 'alpha_v2'))
        recibo = ler_json(self.root / f'casos/alpha/cadastros/{lote}/recibo.json')
        self.assertEqual(recibo['lote_id'], lote)
        self.assertNotIn('cortado', recibo)
        self.assertTrue((self.root / f'casos/alpha/cadastros/{lote}/derivados/D002_texto_pdf.md').is_file())

    def test_lote_ilegivel_e_recusado_sozinho_e_a_fila_segue(self):
        with mock.patch.object(fila_extracao.Fila, 'iniciar'):  # nobody coordinates yet
            ruim = self.fila.receber('alpha', gravador(('ruim.pdf', pdf(self.arquivos, 'ruim.pdf', marca='R'))),
                                     natureza='sinteticos')
            bom = self.fila.receber('alpha', gravador(('bom.pdf', pdf(self.arquivos, 'bom.pdf', marca='B'))),
                                    natureza='sinteticos')
        caminho = fila_extracao.pasta_fila(self.root) / ruim / 'pedido.json'
        pedido = ler_json(caminho)
        del pedido['itens'][0]['indice']  # damaged on disk
        caminho.write_text(json.dumps(pedido), encoding='utf-8')
        nova = self.nova_fila()
        with self.assertLogs('vlado.fila_extracao', 'WARNING') as registro:
            nova.iniciar()
            resposta = nova.aguardar(bom, 60)
        self.assertIn(f'lote {ruim} ilegível', '\n'.join(registro.output))
        self.assertEqual((resposta['novos'], resposta['corpus_id']), (1, 'alpha_v2'))
        with self.assertRaisesRegex(ValueError, 'ficou ilegível'):
            nova.aguardar(ruim, 5)
        self.assertFalse((fila_extracao.pasta_fila(self.root) / ruim / 'originais').exists())
        self.assertEqual(fila_extracao.pendentes(self.root), [])

    def test_encerramento_devolve_o_arquivo_em_leitura_sem_contar_tentativa(self):
        with self.bloqueado() as bloqueio:
            lote = self.fila.receber('alpha', gravador(('a.pdf', pdf(self.arquivos, 'a.pdf'))), natureza='sinteticos')
            self.assertTrue(bloqueio.dentro.wait(10))
            esperando = {}
            espera = threading.Thread(target=lambda: esperando.update(r=self._aguardar(lote)), daemon=True)
            espera.start()
            extracoes = list(self.fila._locais)  # local threads cannot be stopped: joined below
            self.fila.encerrar(0.5)
            espera.join(10)
            self.assertIsInstance(esperando['r'], trava_cadastro.TravaInterrompida)
            arquivo = interno(self.root, lote)['arquivos'][0]
            self.assertEqual((arquivo['estado'], arquivo['tentativas']), ('enfileirado', 0))
            self.assertIn('encerramento', arquivo['motivo'])
            bloqueio.soltar.set()
            for extracao in extracoes:
                extracao.join(30)  # its late result is ignored; the next start reads the file again
        nova = self.nova_fila()
        nova.iniciar()
        resposta = nova.aguardar(lote, 60)
        self.assertEqual(resposta['novos'], 1)
        self.assertEqual(self.publico(lote, nova)['arquivos'][0]['tentativas'], 0)

    def _aguardar(self, lote):
        try:
            return self.fila.aguardar(lote, 20)
        except Exception as exc:  # noqa: BLE001 - the test looks at it
            return exc


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class RevisaoCorujaTest(Base):
    """C1 (lote publicado sem estado final), C4 (teto da fila), C5 (motivo sem caminho), C8 (recuo)."""

    def publicado(self, nome='a.pdf'):
        lote = self.fila.receber('alpha', gravador((nome, pdf(self.arquivos, nome, marca=nome))), natureza='sinteticos')
        resposta = self.fila.aguardar(lote, 60)
        self.fila.encerrar(15)
        return lote, resposta

    def test_lote_publicado_sem_estado_final_e_concluido_na_partida(self):
        for variante in ('arquivos_prontos', 'arquivos_devolvidos_a_fila'):
            with self.subTest(variante):
                lote, resposta = self.publicado(f'{variante}.pdf')
                registros = ler_json(self.manifesto)['registros_cadastro']
                pasta = fila_extracao.pasta_fila(self.root) / lote
                # What the cut left: published, copies already removed, state still 'publicando'.
                estado = ler_json(pasta / 'estado.json')
                estado.update(estado='publicando', recibo=None)
                for arquivo in estado['arquivos']:
                    if variante == 'arquivos_devolvidos_a_fila':  # the earlier start had sent it back
                        arquivo.update(estado='enfileirado', extracao=None)
                (pasta / 'estado.json').write_text(json.dumps(estado), encoding='utf-8')
                (pasta / 'resposta.json').unlink()
                self.assertFalse((pasta / 'originais').exists())
                self.assertEqual(fila_extracao.pendentes(self.root, 'alpha'), [lote])
                self.fila = self.nova_fila()
                self.fila.iniciar()
                concluido = self.fila.aguardar(lote, 30)
                self.assertEqual((concluido['arquivo_recibo'], concluido['corpus_id']),
                                 (resposta['arquivo_recibo'], resposta['corpus_id']))
                publico = self.publico(lote)
                self.assertEqual((publico['estado'], publico['recibo']['novos']), ('publicado', 1))
                self.assertEqual([(a['estado'], a['extracao']) for a in publico['arquivos']], [('pronto', 'extraido')])
                self.assertEqual(fila_extracao.pendentes(self.root), [])  # a first question is accepted again
                self.assertEqual(ler_json(self.manifesto)['registros_cadastro'], registros)  # once only

    def test_queda_na_limpeza_depois_do_estado_final(self):
        with mock.patch.object(fila_extracao.Fila, '_limpar_partes', side_effect=SystemExit):
            lote = self.fila.receber('alpha', gravador(('a.pdf', pdf(self.arquivos, 'a.pdf'))), natureza='sinteticos')
            resposta = self.fila.aguardar(lote, 60)  # the final state was written before the cut
            esperar(lambda: not self.fila._thread.is_alive(), 10)
        self.fila._dono.soltar()
        pasta = fila_extracao.pasta_fila(self.root) / lote
        self.assertEqual(interno(self.root, lote)['estado'], 'publicado')
        self.assertTrue((pasta / 'originais').exists())  # left by the cut
        nova = self.nova_fila()
        segundo = nova.receber('alpha', gravador(('b.txt', b'Outro documento sintetico.')), natureza='sinteticos')
        esperar(lambda: not (pasta / 'originais').exists() and not (pasta / 'derivados').exists(), 30,
                'a partida não removeu as cópias deixadas pela queda')
        self.assertEqual((resposta['novos'], nova.aguardar(segundo, 30)['novos']), (1, 1))
        self.assertEqual(fila_extracao.pendentes(self.root, 'alpha'), [])

    def segurar_a_fila(self):
        patcher = mock.patch.object(fila_extracao.Fila, 'iniciar')  # batches stay queued
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_teto_de_lotes_por_apuracao_e_na_mesa(self):
        cadastro.cadastrar(self.root, 'beta', [self.root / 'fonte.txt'], novo=True, titulo='Outro caso', natureza='sinteticos')
        with mock.patch.dict(os.environ, {'VLADO_FILA_LOTES_POR_CASO': '2', 'VLADO_FILA_LOTES': '3'}):
            fila = self.nova_fila()
        self.segurar_a_fila()

        def enviar(caso, nome):
            return fila.receber(caso, gravador((nome, f'Documento sintetico {nome}.'.encode('utf-8'))), natureza='sinteticos')
        enviar('alpha', 'a1.txt'), enviar('alpha', 'a2.txt')
        with self.assertRaises(ValueError) as recusa:
            enviar('alpha', 'a3.txt')
        mensagem = str(recusa.exception)
        self.assertTrue(mensagem.startswith('Limite de envios em processamento. Há 2 arquivos desta apuração sendo lidos.'))
        self.assertIn('Os arquivos já enviados estão guardados', mensagem)
        self.assertIn('Documentos, perguntas e caderno seguem funcionando', mensagem)
        self.assertEqual(erros.codigo_de(mensagem), ('fila_limite_envios', {'arquivos': 2, 'onde': 'desta apuração'}))
        enviar('beta', 'b1.txt')  # another case still has room
        with self.assertRaises(ValueError) as recusa:
            enviar('beta', 'b2.txt')
        self.assertEqual(erros.codigo_de(str(recusa.exception)), ('fila_limite_envios', {'arquivos': 3, 'onde': 'na Mesa'}))
        self.assertEqual([p.name for p in fila.pasta.iterdir() if p.name.startswith('.novo_')], [])
        self.assertEqual(fila._reservas, {})

    def test_teto_de_bytes_recusa_depois_de_gravar_e_nao_deixa_sobra(self):
        with mock.patch.dict(os.environ, {'VLADO_FILA_MB_POR_CASO': '1'}):
            fila = self.nova_fila()
        self.segurar_a_fila()
        metade = os.urandom(600 * 1024)
        fila.receber('alpha', gravador(('a.txt', metade)), natureza='sinteticos')
        with self.assertRaisesRegex(ValueError, '^Limite de envios em processamento. Há 1 arquivo desta apuração sendo lido.'):
            fila.receber('alpha', gravador(('b.txt', os.urandom(600 * 1024))), natureza='sinteticos')
        self.assertEqual([p.name for p in fila.pasta.iterdir() if p.name.startswith('.novo_')], [])

    def test_envio_em_curso_conta_no_teto(self):
        with mock.patch.dict(os.environ, {'VLADO_FILA_LOTES_POR_CASO': '1'}):
            fila = self.nova_fila()
        self.segurar_a_fila()
        dentro, seguir, resultado = threading.Event(), threading.Event(), {}

        def lento(pasta):
            dentro.set()
            seguir.wait(10)
            return gravador(('lento.txt', b'Documento sintetico lento.'))(pasta)
        primeiro = threading.Thread(target=lambda: resultado.update(lote=fila.receber('alpha', lento, natureza='sinteticos')))
        primeiro.start()
        self.assertTrue(dentro.wait(10))
        with self.assertRaisesRegex(ValueError, '^Limite de envios em processamento'):
            fila.receber('alpha', gravador(('rapido.txt', b'Documento sintetico rapido.')), natureza='sinteticos')
        seguir.set()
        primeiro.join(10)
        self.assertTrue(resultado['lote'])

    def test_motivo_publico_sem_caminho_do_servidor(self):
        caminho = str(self.root / 'casos' / '.fila' / 'segredo_interno.pdf')

        def quebra(tarefa, **_):
            raise OSError(f'falha sintética ao abrir {caminho}')
        with mock.patch.object(cadastro, 'extrair_item', quebra), self.assertLogs('vlado.fila_extracao', 'WARNING') as registro:
            lote = self.fila.receber('alpha', gravador(('a.pdf', pdf(self.arquivos, 'a.pdf'))), natureza='sinteticos')
            with self.assertRaises(ValueError) as recusa:
                self.fila.aguardar(lote, 60)
        publico = json.dumps(self.publico(lote), ensure_ascii=False)
        self.assertNotIn(str(self.root), publico)
        self.assertNotIn(str(self.root), str(recusa.exception))
        self.assertIn('registro do servidor', str(recusa.exception))
        self.assertIn(caminho, '\n'.join(registro.output))  # the detail stays in the server log

    def test_coordenador_com_erro_repetido_recua(self):
        chamadas = []

        def quebra(_self):
            chamadas.append(time.monotonic())
            raise RuntimeError('falha sintética do coordenador')
        with mock.patch.object(fila_extracao.Fila, '_passo', quebra), \
                self.assertLogs('vlado.fila_extracao', 'ERROR') as registro:
            self.fila.iniciar()
            time.sleep(3.6)
            inicio = time.monotonic()
            self.fila.encerrar(5)
            self.assertLess(time.monotonic() - inicio, 1.5, 'o recuo não notou o encerramento')
        self.assertLessEqual(len(chamadas), 5)  # 0.5, 1, 2 s apart (it was every 0.5 s)
        self.assertGreaterEqual(len(chamadas), 3)
        self.assertEqual(len(registro.output), 1)  # the trace once, not every turn


class VigiaTest(unittest.TestCase):
    """C2 and C3: the extraction process ends with the Mesa and takes its children along."""

    PREPARO = ('import os, subprocess, sys, time\n'
               'sys.path.insert(0, sys.argv[1])\n'
               'import trabalhador_extracao as t\n')

    def processo(self, codigo, *argumentos, grupo=True):
        opcoes = {'start_new_session': True} if grupo and os.name != 'nt' else {}
        proc = subprocess.Popen([sys.executable, '-c', codigo, str(TESTES.parent / 'scripts'), *argumentos],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, **opcoes)
        self.addCleanup(lambda: (proc.poll() is None and proc.kill(), proc.wait(10), proc.stdin.close(), proc.stdout.close()))
        return proc

    def test_mesa_ja_morta_antes_da_partida_encerra_na_hora(self):
        morta = subprocess.Popen([sys.executable, '-c', 'pass'])
        morta.wait(10)
        inicio = time.monotonic()
        proc = self.processo(self.PREPARO + 't.vigiar_pai(int(sys.argv[2]))\ntime.sleep(60)', str(morta.pid))
        self.assertIn(proc.wait(15), (3, -9))  # POSIX: its own group ends with signal 9
        self.assertLess(time.monotonic() - inicio, 10)

    def test_vigia_leva_os_filhos_quando_a_mesa_morre(self):
        trabalhador = (self.PREPARO + 't.juntar_filhos()\n'
                       't.vigiar_pai(int(sys.argv[2]))\n'
                       'filho = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])\n'
                       'print(filho.pid, flush=True)\n'
                       'time.sleep(120)\n')
        mesa = ('import os, subprocess, sys, time\n'
                'opcoes = {} if os.name == "nt" else {"start_new_session": True}\n'
                'p = subprocess.Popen([sys.executable, "-c", sys.argv[2], sys.argv[1], str(os.getpid())], '
                'stdout=subprocess.PIPE, text=True, **opcoes)\n'
                'print(p.pid, p.stdout.readline().strip(), flush=True)\n'
                'time.sleep(120)\n')
        proc = self.processo(mesa, trabalhador, grupo=False)
        pid_trabalhador, pid_filho = map(int, proc.stdout.readline().split())
        self.assertTrue(vivo(pid_trabalhador) and vivo(pid_filho))
        proc.kill()  # the Mesa dies
        esperar(lambda: not vivo(pid_trabalhador) and not vivo(pid_filho), 15,
                'o processo de extração ou o filho dele sobreviveu à Mesa')

    def test_processo_morto_pela_fila_leva_os_filhos(self):
        trabalhador = (self.PREPARO + 't.juntar_filhos()\n'
                       'filho = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])\n'
                       'print(filho.pid, flush=True)\n'
                       'time.sleep(120)\n')
        proc = self.processo(trabalhador)
        pid_filho = int(proc.stdout.readline())
        executor = fila_extracao._ExecutorProcesso.__new__(fila_extracao._ExecutorProcesso)
        executor.proc = proc
        executor.matar()  # as the queue does on a deadline or a refused batch
        proc.wait(10)
        esperar(lambda: not vivo(pid_filho), 15, 'o filho sobreviveu ao processo de extração')


class PerguntaComLoteNaFilaTest(unittest.TestCase):
    def setUp(self):
        import test_codex_integracao as integracao
        integracao.CodexIntegrationTest.setUp(self)
        self.start = lambda: integracao.CodexIntegrationTest.start(self)

    def test_primeira_pergunta_recusada_e_pergunta_seguinte_espera_o_lote(self):
        from agente_fluxo_fixture import completar
        conversa = self.start()
        completar(self.manager, conversa)
        fila = fila_extracao.Fila(self.root, 'local')
        self.addCleanup(fila.encerrar, 15)
        with mock.patch.object(fila_extracao.Fila, 'iniciar'):  # stays queued until the test starts it
            lote = fila.receber('alpha', gravador(('novo.txt', b'Documento novo sintetico.')), natureza='sinteticos')
        with self.assertRaisesRegex(ValueError, 'documentos desta apuração em processamento'):
            self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Primeira pergunta sintética.'})
        outra = self.manager.perguntar({'caso': 'beta', 'pergunta': 'Pergunta sintética de outra apuração.'})
        self.assertTrue(outra['conversa'])
        # A question in a conversation with a round waits for the batch, then freezes.
        self.manager.perguntar({'caso': 'alpha', 'conversa': conversa, 'pergunta': 'Pergunta seguinte sintética.'})
        ctx = self.manager.contexts[conversa]
        esperar(lambda: any(e['tipo'] == 'aviso' and 'processamento dos documentos' in e['dados']['mensagem']
                            for e in ctx['events']), 10)
        time.sleep(0.5)
        self.assertFalse((self.root / 'execucoes/alpha/R002').exists())
        fila.iniciar()
        self.assertEqual(fila.aguardar(lote, 30)['corpus_id'], 'alpha_v2')
        esperar(lambda: (self.root / 'execucoes/alpha/R002/snapshot.json').is_file(), 15,
                'a pergunta seguinte não congelou depois do lote')
        # With the batch published, a first question goes through again.
        nova = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Primeira pergunta, depois do lote.'})
        self.assertTrue(nova['conversa'])


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class RotaDaFilaTest(Base):
    def test_cadastro_assincrono_e_estado_por_get_api_fila(self):
        from interface_pesquisa import Servidor
        server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(5)))

        def pedir(metodo, caminho, dados=None):
            con = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=30)
            try:
                con.request(metodo, caminho, json.dumps(dados) if dados is not None else None,
                            {'Content-Type': 'application/json', 'Origin': server.origin, 'X-Session-Token': server.token})
                resposta = con.getresponse()
                return resposta.status, json.loads(resposta.read())
            finally:
                con.close()
        conteudo = base64.b64encode(pdf(self.arquivos, 'a.pdf', 2)).decode('ascii')
        lote_http = {'caso': 'alpha', 'natureza': 'sinteticos', 'assincrono': True,
                     'arquivos': [{'nome': 'a.pdf', 'base64': conteudo}]}
        with self.bloqueado() as bloqueio:
            inicio = time.monotonic()
            status, corpo = pedir('POST', '/api/cadastrar', lote_http)
            self.assertLess(time.monotonic() - inicio, 5)
            self.assertEqual(status, 200, corpo)
            self.assertEqual(corpo['estado'], 'enfileirado')
            lote = corpo['lote']['lote']
            self.assertEqual(corpo['lote']['arquivos'][0]['nome'], 'a.pdf')
            self.assertTrue(bloqueio.dentro.wait(10))
            status, corpo = pedir('GET', f'/api/fila?lote={lote}')
            self.assertEqual((status, corpo['lote']['estado']), (200, 'processando'))
            status, corpo = pedir('GET', '/api/fila?caso=alpha')
            self.assertEqual((status, [l['lote'] for l in corpo['lotes']]), (200, [lote]))
            self.assertEqual(pedir('GET', '/api/fila?caso=beta'), (200, {'lotes': []}))
            self.assertEqual(pedir('GET', '/api/fila?lote=invalido')[0], 400)
            self.assertEqual(pedir('GET', '/api/fila?lote=' + '0' * 32)[0], 400)
            self.assertEqual(pedir('POST', '/api/cadastrar', {**lote_http, 'assincrono': 'sim'})[0], 400)
            bloqueio.soltar.set()
            esperar(lambda: pedir('GET', f'/api/fila?lote={lote}')[1]['lote']['estado'] == 'publicado', 30)
        status, corpo = pedir('GET', f'/api/fila?lote={lote}')
        self.assertEqual((corpo['lote']['recibo']['novos'], corpo['lote']['recibo']['corpus_id']), (1, 'alpha_v2'))
        # Synchronous by default: the receipt, as always.
        status, recibo = pedir('POST', '/api/cadastrar', {**lote_http, 'assincrono': False, 'arquivos': [
            {'nome': 'b.txt', 'base64': base64.b64encode(b'Documento sintetico b.').decode('ascii')}]})
        self.assertEqual((status, recibo['novos'], recibo['corpus_id']), (200, 1, 'alpha_v3'), recibo)


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class FilaProcessosTest(Base):
    """Separate extraction processes (``trabalhador_extracao``), as the Mesa runs from the command line."""
    modo = 'processos'

    def pesado(self, nome='pesado.pdf'):
        """About 15 s of reading on one core (``pdf_pesado``): far longer than every check below."""
        caminho = self.arquivos / nome
        if not caminho.exists():
            pdf_pesado(caminho)
        return caminho.read_bytes()

    def lendo(self, lote, tentativas=0, exceto=None, pagina=True):
        """Wait until an extraction process has the file (and reads its pages); returns its pid."""
        estado = self.esperar_estado(
            lote, lambda e: e['arquivos'][0]['estado'] == 'extraindo' and e['arquivos'][0].get('processo')
            and (e['arquivos'][0].get('pagina') or not pagina) and e['arquivos'][0]['tentativas'] == tentativas
            and e['arquivos'][0]['processo'] != exceto, 60, 'o processo de extração não começou a ler')
        return estado['arquivos'][0]['processo']

    def test_extracao_roda_em_outro_processo(self):
        aqui = mock.Mock(side_effect=AssertionError('extração no processo da Mesa'))
        with mock.patch.object(cadastro, 'extrair_item', aqui):
            lote = self.fila.receber('alpha', gravador(('a.pdf', pdf(self.arquivos, 'a.pdf', 2))), natureza='sinteticos')
            resposta = self.fila.aguardar(lote, 120)
        aqui.assert_not_called()
        self.assertEqual((resposta['novos'], resposta['corpus_id']), (1, 'alpha_v2'))
        doc = next(d for d in self.documentos() if d['id'] == 'D002')
        self.assertEqual(doc['extracao_pdf']['estado'], 'extraido')
        self.assertIn('pagina 2', (self.root / doc['derivados'][0]['arquivo']).read_text(encoding='utf-8'))
        self.sem_provisorio()

    def test_processo_morto_duas_vezes_fica_em_falha_e_o_original_e_cadastrado(self):
        conteudo = self.pesado()
        lote = self.fila.receber('alpha', gravador(('pesado.pdf', conteudo)), natureza='sinteticos')
        primeiro = self.lendo(lote)
        self.assertNotEqual(primeiro, os.getpid())
        matar(primeiro)
        segundo = self.lendo(lote, tentativas=1, exceto=primeiro)
        matar(segundo)
        resposta = self.fila.aguardar(lote, 120)
        arquivo = self.publico(lote)['arquivos'][0]
        self.assertEqual((arquivo['estado'], arquivo['extracao'], arquivo['tentativas']), ('falha', 'erro', 2))
        self.assertIn('terminou sem resposta', arquivo['motivo'])
        self.assertEqual((resposta['novos'], resposta['corpus_id']), (1, 'alpha_v2'))
        doc = next(d for d in self.documentos() if d['id'] == 'D002')
        self.assertEqual((doc['extracao_pdf']['estado'], doc['derivados']), ('erro', []))
        self.assertIn('Tentativas: 2', doc['extracao_pdf']['mensagem'])
        self.assertEqual(sha256(self.root / doc['arquivo']), sha256(self.arquivos / 'pesado.pdf'))
        esperar(lambda: not vivo(primeiro) and not vivo(segundo), 10)

    def test_prazo_estourado_mata_o_processo_e_o_arquivo_fica_em_falha(self):
        fila = self.nova_fila(tempo_maximo=1)
        lote = fila.receber('alpha', gravador(('pesado.pdf', self.pesado())), natureza='sinteticos')
        pid = self.lendo(lote, pagina=False)  # the deadline may come before the first page
        resposta = fila.aguardar(lote, 120)
        arquivo = fila.consultar(lote=lote)['lote']['arquivos'][0]
        self.assertEqual((arquivo['estado'], arquivo['extracao']), ('falha', 'erro'))
        self.assertIn('Tempo máximo de extração excedido (1 s)', arquivo['motivo'])
        self.assertEqual(resposta['novos'], 1)
        esperar(lambda: not vivo(pid), 10, 'o processo de extração sobreviveu ao prazo')

    def test_mesa_morta_no_meio_o_processo_de_extracao_sai_e_a_partida_retoma(self):
        from test_trava_queda import Mesa
        self.fila.encerrar(0)  # the Mesa in another process coordinates this folder
        mesa = Mesa(self, self.root, '--extracao', 'processos')
        conteudo = base64.b64encode(self.pesado()).decode('ascii')
        status, corpo = mesa.post('cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos', 'assincrono': True,
                                                'arquivos': [{'nome': 'pesado.pdf', 'base64': conteudo}]}, prazo=60)
        self.assertEqual(status, 200, corpo)
        lote = corpo['lote']['lote']
        trabalhador = self.lendo(lote)
        self.assertNotEqual(trabalhador, mesa.pid)
        inicio = time.monotonic()
        mesa.matar()
        # The extraction process ends with the Mesa (vigia), long before the file would be read
        # (about 15 s): not because its input closed, which it only reads between files.
        esperar(lambda: not vivo(trabalhador), 10, 'o processo de extração sobreviveu à Mesa')
        self.assertLess(time.monotonic() - inicio, 4, 'o processo de extração saiu só ao terminar a leitura')
        self.assertEqual(interno(self.root, lote)['arquivos'][0]['estado'], 'extraindo')
        # The next start reads the file again (one attempt counted) and publishes it.
        nova = Mesa(self, self.root, '--extracao', 'processos')
        esperar(lambda: interno(self.root, lote).get('estado') == 'publicado', 120,
                'a Mesa reiniciada não concluiu o lote')
        arquivo = nova.fila()[0]['arquivos'][0]
        self.assertEqual((arquivo['estado'], arquivo['extracao'], arquivo['tentativas']), ('pronto', 'extraido', 1))
        nova.desligar(self)


if __name__ == '__main__':
    unittest.main()
