"""Synthetic PDF ingestion, provenance, failure and snapshot integration tests."""
import importlib.util
import json
from pathlib import Path, PureWindowsPath
import shutil
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cadastrar_documentos as cadastro
import codex_apuracao
import nova_rodada
from agente_fluxo_fixture import completar, esperar
from comum import escrever_json, ler_json, sha256
from criar_caso import criar_caso
from extrair_pdf import extrair_pdf
from indice_sqlite import cobertura, pesquisar, ler_passagem
from nova_rodada import criar_rodada
from selecionar_caso import selecionar
from test_codex_integracao import FakeServer
import test_registros as fixtures

HAS_PYPDF = importlib.util.find_spec('pypdf') is not None


def pdf_sintetico(path, pages=('Marcador exclusivo do PDF sintetico.', None), *, password=None):
    """Create an actual PDF with standard-font text and optional blank pages."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    font_ref = writer._add_object(font)
    for text in pages:
        page = writer.add_blank_page(width=300, height=300)
        if text is not None:
            page[NameObject('/Resources')] = DictionaryObject({
                NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref})})
            stream = DecodedStreamObject()
            literal = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            stream.set_data(f'BT /F1 12 Tf 20 200 Td ({literal}) Tj ET'.encode('ascii'))
            page[NameObject('/Contents')] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    writer.write(path)
    return path


class ExtracaoCadastroPDFTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RegistrosTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        selecionar(self.root, None)

    def register(self, sources, **kwargs):
        return cadastro.cadastrar(self.root, 'alpha', sources, **kwargs)

    def start(self, sources):
        return self.register(sources, novo=True, titulo='PDF sintetico', natureza='sinteticos')

    def manifest(self):
        return ler_json(self.root / 'casos/alpha/manifesto.json')

    @unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extracao real')
    def test_pdf_preparado_no_cadastro_e_pesquisavel_com_pagina_e_original(self):
        source = pdf_sintetico(self.root / 'fonte.pdf')
        original = source.read_bytes()
        result = self.start([source, source])
        self.assertEqual((result['novos'], result['duplicados']), (1, 1))
        self.assertEqual(result['extracao_pdf_resumo']['processados_agora'], 1)
        doc = self.manifest()['documentos'][0]
        self.assertEqual(doc['paginas_pdf'], 2)
        self.assertEqual(doc['extracao_pdf']['paginas_sem_texto'], [2])
        self.assertEqual(doc['extracao_pdf']['estado'], 'parcial')
        derivative = doc['derivados'][0]
        self.assertEqual(derivative['origem_sha256'], doc['sha256'])
        self.assertEqual(sha256(self.root / derivative['arquivo']), derivative['sha256'])
        self.assertEqual((self.root / doc['arquivo']).read_bytes(), original)
        self.assertFalse((self.root / 'execucoes').exists())
        self.assertIsNone(ler_json(self.root / 'configuracao.json')['caso_ativo'])
        selecionar(self.root, 'alpha')
        run = criar_rodada(self.root, 'R001', 'Pergunta sintetica de localizacao.', indice=True)
        response = pesquisar(self.root, 'alpha', 'R001', 'exclusivo', pagina=1)
        hit = response['resultados'][0]
        self.assertEqual(hit['pagina_pdf'], 1)
        self.assertEqual((run / hit['original']).read_bytes(), original)
        context = ler_passagem(self.root, 'alpha', 'R001', hit['referencia'])
        self.assertIn('exclusivo', json.dumps(context, ensure_ascii=False))
        units = [u for f in cobertura(self.root, 'alpha', 'R001')['cobertura']['documentos'][0]['fontes'] for u in f['unidades']]
        self.assertTrue(any(u['pagina_pdf'] == 2 and u['estado'] == 'sem_texto' for u in units))
        self.assertEqual(pesquisar(self.root, 'alpha', 'R001', 'EXTRAIVEL')['retornados'], 0)

    @unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extracao real')
    def test_primeira_pergunta_e_complemento_com_limite_de_caminho_do_windows(self):
        raiz_windows = PureWindowsPath(r'C:\Users\teste\AppData\Local\Vlado')

        def conferir_caminho_win32(destino, limite):
            caminho = str(raiz_windows / destino.relative_to(self.root))
            if len(caminho.encode('utf-16-le')) // 2 > limite:
                raise FileNotFoundError(2, 'Caminho acima do limite Win32 tradicional', caminho)

        def copiar_com_limite_win32(origem, destino):
            conferir_caminho_win32(destino.parent, 248)
            conferir_caminho_win32(destino, 259)
            return shutil.copyfile(origem, destino)

        def copiar_arvore_com_limite_win32(origem, destino):
            for item in origem.rglob('*'):
                alvo = destino / item.relative_to(origem)
                conferir_caminho_win32(alvo, 248 if item.is_dir() else 259)
            return shutil.copytree(origem, destino)

        for sufixo, nome_pdf in (('a', 'a.pdf'), ('b', 'B02_braskem_comunicado_2023-12-04.pdf')):
            with self.subTest(nome_pdf=nome_pdf):
                manager = codex_apuracao.Conversas(self.root, FakeServer)
                self.addCleanup(manager.close)
                caso = 'apuracao_' + sufixo * 32
                source = pdf_sintetico(self.root / nome_pdf, ('Alfabeto sintetico. Valor 123.',))
                cadastro.cadastrar(self.root, caso, [source], novo=True,
                                   titulo='PDF sintetico', natureza='sinteticos')
                doc = ler_json(self.root / 'casos' / caso / 'manifesto.json')['documentos'][0]
                derivado, = doc['derivados']
                with (patch.object(nova_rodada, 'shutil') as arquivos,
                      patch.object(codex_apuracao, 'shutil') as arvore):
                    arquivos.copyfile.side_effect = copiar_com_limite_win32
                    arvore.copytree.side_effect = copiar_arvore_com_limite_win32
                    dados = {'caso': caso, 'pergunta': 'Pergunta sintetica.'}
                    for rodada in ('R001', 'R002'):
                        conversa = manager.perguntar(dados)['conversa']
                        ctx = manager.contexts[conversa]
                        esperar(lambda: not ctx['busy'] or
                                (ctx['meta']['rodada_pergunta'] == rodada and ctx['meta'].get('turn_id')))
                        self.assertEqual(ctx['meta']['estado'], 'executando', ctx['meta']['situacao'])
                        completar(manager, conversa)
                        self.assertEqual(ctx['meta']['estado'], 'concluido', ctx['meta']['situacao'])
                        dados = {'caso': caso, 'pergunta': 'Complemento sintetico.', 'conversa': conversa}
                        if rodada == 'R001':
                            primeira = ctx['run']
                            arquivos_iniciais = {p.relative_to(primeira): sha256(p)
                                                 for p in primeira.rglob('*') if p.is_file()}
                self.assertEqual(ctx['meta']['rodadas'], ['R001', 'R002'])
                self.assertEqual(ctx['run'], self.root / 'execucoes' / caso / 'R002')
                self.assertEqual(ler_json(ctx['run'] / 'registro.json')['complemento_de'], 'R001')
                self.assertEqual({p.relative_to(primeira): sha256(p)
                                  for p in primeira.rglob('*') if p.is_file()}, arquivos_iniciais)
                for entrada in (doc, derivado):
                    self.assertEqual(sha256(ctx['run'] / 'entradas' / entrada['arquivo']), entrada['sha256'])
                self.assertEqual(pesquisar(self.root, caso, 'R002', 'Alfabeto')['retornados'], 1)
                self.assertEqual(list((self.root / 'execucoes').glob('.r_*')), [])

    @unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extracao real')
    def test_duplicata_preparada_nao_reextrai_nem_muda_versao_ou_aprovacao(self):
        source = pdf_sintetico(self.root / 'fonte.pdf', ['Texto completo sintetico.'])
        self.start([source])
        path = self.root / 'casos/alpha/manifesto.json'
        manifest = self.manifest()
        manifest['protocolo'] = {'piloto_estabilizado': True, 'teste_principal_autorizado': True}
        escrever_json(path, manifest)
        before = manifest['documentos']
        with patch.object(cadastro, 'extrair_pdf', side_effect=AssertionError('Nao repetir extracao')):
            result = self.register([source])
        self.assertEqual(result['corpus_id'], 'alpha_v1')
        self.assertEqual(self.manifest()['documentos'], before)
        self.assertTrue(self.manifest()['protocolo']['piloto_estabilizado'])

    def test_dependencia_ausente_preserva_original_e_explica_falha(self):
        source = self.root / 'sem_dependencia.pdf'
        source.write_bytes(b'Synthetic bytes to test missing dependency only.')
        with patch.dict(sys.modules, {'pypdf': None}):
            result = self.start([source])
        doc = self.manifest()['documentos'][0]
        self.assertEqual(doc['extracao_pdf']['estado'], 'erro')
        self.assertIn('pypdf indisponivel', doc['extracao_pdf']['mensagem'])
        self.assertEqual(doc['derivados'], [])
        self.assertEqual((self.root / doc['arquivo']).read_bytes(), source.read_bytes())
        self.assertEqual(result['extracao_pdf_resumo']['erro'], 1)

    @unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extracao real')
    def test_protegido_invalido_e_paginas_sem_texto_nao_somem_do_recibo(self):
        locked = pdf_sintetico(self.root / 'senha.pdf', ['Texto protegido.'], password='sintetica')
        blank = pdf_sintetico(self.root / 'digitalizado.pdf', [None])
        invalid = self.root / 'invalido.pdf'
        invalid.write_bytes(b'%PDF-1.4\nInvalid synthetic fixture.')
        image = self.root / 'imagem.png'
        image.write_bytes(b'Synthetic image placeholder: no OCR expected.')
        result = self.start([locked, blank, invalid, image])
        self.assertEqual(result['recebidos'], 4)
        self.assertEqual(result['extracao_pdf_resumo']['erro'], 2)
        self.assertEqual(result['extracao_pdf_resumo']['sem_texto'], 1)
        self.assertNotIn('extracao_pdf', self.manifest()['documentos'][3])
        self.assertEqual([d['extracao_pdf']['estado'] for d in self.manifest()['documentos'][:3]],
                         ['erro', 'sem_texto', 'erro'])
        self.assertEqual(len(result['arquivos']), 4)

    @unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extracao real')
    def test_erro_em_uma_pagina_tem_localizador_e_nao_indexa_aviso(self):
        source = pdf_sintetico(self.root / 'parcial.pdf')
        class Page:
            def __init__(self, value): self.value = value
            def extract_text(self):
                if isinstance(self.value, Exception): raise self.value
                return self.value
        class Reader:
            is_encrypted = False
            pages = [Page('Marcador recuperavel.'), Page(ValueError('Erro sintetico')), Page('')]
        with patch('pypdf.PdfReader', return_value=Reader()):
            result = self.start([source])
        info = result['arquivos'][0]['extracao_pdf']
        self.assertEqual(info['paginas_com_erro'][0]['pagina_pdf'], 2)
        self.assertEqual(info['estado'], 'parcial')
        selecionar(self.root, 'alpha')
        criar_rodada(self.root, 'R001', 'Pergunta sintetica de cobertura.', indice=True)
        report = cobertura(self.root, 'alpha', 'R001')['cobertura']
        units = [u for f in report['documentos'][0]['fontes'] for u in f['unidades']]
        self.assertTrue(any(u['pagina_pdf'] == 2 and u['estado'] == 'erro_leitura' for u in units))
        self.assertEqual(pesquisar(self.root, 'alpha', 'R001', 'EXTRACAO')['retornados'], 0)
        self.assertEqual(pesquisar(self.root, 'alpha', 'R001', 'recuperavel')['retornados'], 1)

    @unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extracao real')
    def test_preparacao_de_caso_existente_versiona_derivados_sem_alterar_rodada(self):
        source = pdf_sintetico(self.root / 'legado.pdf', ['Marcador retroativo exclusivo.'])
        with patch.dict(sys.modules, {'pypdf': None}):
            self.start([source])
        # Simulate a pre-extraction manifest with no preparation metadata.
        path = self.root / 'casos/alpha/manifesto.json'
        manifest = self.manifest()
        manifest['documentos'][0].pop('extracao_pdf')
        manifest['protocolo']['piloto_estabilizado'] = True
        escrever_json(path, manifest)
        original = manifest['documentos'][0].copy()
        selecionar(self.root, 'alpha')
        old = criar_rodada(self.root, 'R001', 'Pergunta sintetica anterior.', indice=True)
        old_hashes = {p.relative_to(old): sha256(p) for p in old.rglob('*') if p.is_file()}
        result = cadastro.preparar_pdfs(self.root, 'alpha')
        self.assertEqual(result['corpus_id'], 'alpha_v2')
        self.assertEqual(result['operacao'], 'preparacao_pdfs_cadastrados')
        self.assertEqual(result['novos'], 0)
        self.assertEqual(result['arquivos'][0]['nome_recebido'], 'legado.pdf')
        doc = self.manifest()['documentos'][0]
        self.assertEqual((doc['id'], doc['arquivo'], doc['sha256']),
                         (original['id'], original['arquivo'], original['sha256']))
        self.assertFalse(self.manifest()['protocolo']['piloto_estabilizado'])
        self.assertEqual(old_hashes, {p.relative_to(old): sha256(p) for p in old.rglob('*') if p.is_file()})
        self.assertFalse((self.root / 'execucoes/alpha/R002').exists())
        self.assertEqual(cobertura(self.root, 'alpha', 'R001')['cobertura']['documentos_pesquisaveis'], 0)
        criar_rodada(self.root, 'R002', 'Pergunta sintetica posterior.', indice=True)
        self.assertEqual(pesquisar(self.root, 'alpha', 'R002', 'retroativo')['retornados'], 1)

    @unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extracao real')
    def test_cli_legada_tambem_prepara_pdf_com_recibo(self):
        source = pdf_sintetico(self.root / 'legado.pdf', ['Texto sintetico legado.'])
        criar_caso(self.root, 'alpha', 'Legado', [source], 'sinteticos')
        doc = self.manifest()['documentos'][0]
        self.assertEqual(doc['extracao_pdf']['estado'], 'extraido')
        self.assertEqual(len(doc['derivados']), 1)
        self.assertEqual(len(self.manifest()['registros_cadastro']), 1)

    def test_falha_de_gravacao_na_extracao_nao_publica_caso_parcial(self):
        source = self.root / 'pdf.pdf'
        source.write_bytes(b'Synthetic fixture for storage failure.')
        with patch.object(cadastro, 'extrair_pdf', side_effect=OSError('Disco sintetico cheio')):
            with self.assertRaises(OSError):
                self.start([source])
        self.assertFalse((self.root / 'casos/alpha').exists())
        self.assertFalse((self.root / 'casos/.cadastro.lock').exists())

    @unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extracao real')
    def test_extracao_avulsa_nao_sobrescreve_e_preserva_origem(self):
        source = pdf_sintetico(self.root / 'fonte.pdf', ['Texto sintetico.'])
        target = self.root / 'texto.md'
        before = sha256(source)
        self.assertEqual(extrair_pdf(source, 'D001', target)['estado'], 'extraido')
        with self.assertRaises(FileExistsError):
            extrair_pdf(source, 'D001', target)
        self.assertEqual(sha256(source), before)


if __name__ == '__main__':
    unittest.main()
