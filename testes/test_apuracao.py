"""Synthetic editable-notebook persistence, provenance and real-file exports."""
from io import BytesIO
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
import uuid
from zipfile import ZipFile
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fixture_achados import Ambiente
import apuracao
from comum import sha256
from exportar_apuracao import exportar
from indice_sqlite import pesquisar
from interface_pesquisa import Servidor


class ApuracaoTest(unittest.TestCase):
    def setUp(self):
        self.fx, _ = Ambiente.copia_completa(); self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root
        # Every preserved input/output must survive human mutations byte-for-byte.
        self.before = {p: sha256(p) for folder in ('casos/alpha/originais', 'execucoes/alpha/R001/entradas',
                                                  'execucoes/alpha/R001/saidas')
                       for p in (self.root / folder).rglob('*') if p.is_file()}

    def mutate(self, operation='salvar', **kwargs):
        return apuracao.alterar(self.root, 'apuracao-' + operation, {
            'caso': 'alpha', 'revisao': apuracao.listar(self.root, 'alpha')['revisao'],
            'requisicao_id': uuid.uuid4().hex, **kwargs})

    def origin(self, **changes):
        hit = pesquisar(self.root, 'alpha', 'R001', 'declara')['resultados'][0]
        return {'tipo': 'pesquisa', 'rodada': 'R001', 'geracao': 'v1',
                'referencia': hit['referencia'], 'texto': 'valor 12.', **changes}

    def test_crud_reabertura_historico_e_conflito_sem_alterar_fontes(self):
        state = self.mutate(titulo='Análise própria', texto='# Hipótese\n\n**123** e *áéí*\n')
        note = state['notas'][0]; first = self.root / 'casos/alpha/apuracao/revisoes/0000000001.json'
        digest = sha256(first)
        self.assertEqual(apuracao.listar(self.root, 'alpha'), state)
        self.mutate(nota_id=note['id'], titulo='Título revisado', texto='Novo texto')
        with self.assertRaisesRegex(ValueError, 'outra janela'):
            self.mutate(nota_id=note['id'], titulo='Perda de texto', texto='antigo', revisao=1)
        self.assertEqual(apuracao.listar(self.root, 'alpha')['notas'][0]['texto'], 'Novo texto')
        self.mutate('excluir', nota_id=note['id'])
        self.assertEqual(apuracao.listar(self.root, 'alpha')['notas'], [])
        self.assertEqual(sha256(first), digest)
        self.assertTrue(all(sha256(p) == digest for p, digest in self.before.items()))

    def test_adicionar_selecao_e_achado_versao_pagina_e_original(self):
        state = self.mutate(titulo='Caderno da repórter', texto='Minha hipótese.')
        note_id = state['notas'][0]['id']
        state = self.mutate('adicionar', nota_id=note_id, origem=self.origin())
        source = state['notas'][0]['fontes'][0]
        self.assertEqual(source['texto_selecionado'], 'valor 12.')
        self.assertEqual(source['documentos'][0]['documento_id'], 'D001')
        self.assertIn('Linhas', source['documentos'][0]['localizador'])
        self.assertIn('Minha hipótese.', state['notas'][0]['texto'])
        state = self.mutate('adicionar', nota_id=note_id, origem={'tipo': 'ia', 'rodada': 'R001',
            'revisao': 'r2', 'geracao_achados': 'g2', 'achado_id': 'A001', 'achado_versao': 2,
            'texto': 'A fonte declara'})
        source = state['notas'][0]['fontes'][1]
        self.assertEqual(source['achado_versao'], 2)
        self.assertTrue(any(d['pagina_pdf'] == 1 for d in source['documentos']))
        for index, doc in enumerate(source['documentos']):
            original = apuracao.original(self.root, {'caso': 'alpha', 'nota_id': note_id,
                'fonte_id': source['id'], 'documento_indice': index})
            self.assertEqual(sha256(original), doc['original_sha256'])
        self.mutate(nota_id=note_id, titulo='Edição livre', texto='Retirei a citação do texto.')
        saved = apuracao.listar(self.root, 'alpha')['notas'][0]
        self.assertEqual(saved['fontes'][1], source)
        self.assertTrue(all(sha256(p) == digest for p, digest in self.before.items()))

    def test_casos_separados_fontes_invalidas_e_reenvio_idempotente(self):
        self.fx.caso('beta')
        data = {'caso': 'alpha', 'revisao': 0, 'requisicao_id': uuid.uuid4().hex,
                'origem': self.origin()}
        state = apuracao.alterar(self.root, 'apuracao-adicionar', data)
        self.assertEqual(apuracao.alterar(self.root, 'apuracao-adicionar', data), state)
        self.assertEqual(apuracao.listar(self.root, 'beta')['notas'], [])
        with self.assertRaises(ValueError):
            self.mutate(nota_id=state['notas'][0]['id'], caso='beta', titulo='Fora', texto='Inválido')
        for changes in ({'texto': 'conteúdo inventado'}, {'referencia': '../fora'}, {'rodada': '../R001'}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, OSError)):
                self.mutate('adicionar', origem=self.origin(**changes))
        self.assertEqual(apuracao.listar(self.root, 'alpha')['revisao'], 1)

    def test_exportacoes_validas_conteudo_editavel_referencias_e_acentos(self):
        state = self.mutate('adicionar', origem=self.origin())
        state = self.mutate(nota_id=state['notas'][0]['id'], titulo='Apuração São Paulo',
            texto='# Título\n\n**Negrito** e *itálico*.\n- item\n> citação\n[fonte](https://example.org)\n' + 'texto longo ' * 1200)
        md, _ = exportar(state, 'md')
        self.assertIn('São Paulo', md.decode()); self.assertIn('SHA-256:', md.decode())
        docx, mime = exportar(state, 'docx')
        with ZipFile(BytesIO(docx)) as archive:
            self.assertIsNone(archive.testzip())
            xml = archive.read('word/document.xml')
            root = ElementTree.fromstring(xml)
            text = ''.join(root.itertext())
            self.assertIn('São Paulo', text); self.assertIn('Fonte 1', text)
            self.assertIn(b'<w:b', xml); self.assertIn(b'<w:i', xml)
            self.assertIn(b'https://example.org', archive.read('word/_rels/document.xml.rels'))
        from docx import Document
        document = Document(BytesIO(docx))
        document.paragraphs[0].text = 'Título alterado no Word'
        edited = BytesIO(); document.save(edited)
        self.assertIn('Título alterado', Document(BytesIO(edited.getvalue())).paragraphs[0].text)
        pdf, _ = exportar(state, 'pdf')
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf)); self.assertGreater(len(reader.pages), 1)
        text = '\n'.join(p.extract_text() for p in reader.pages)
        self.assertIn('São Paulo', text); self.assertIn('SHA-256:', text)
        self.assertIn('valor 12.', text)
        with self.assertRaises(ValueError): exportar(state, '../html')

    def test_http_protecao_exportacao_e_reinicio_do_servidor(self):
        def server():
            instance = Servidor(('127.0.0.1', 0), self.root)
            thread = threading.Thread(target=instance.serve_forever, daemon=True); thread.start()
            self.addCleanup(lambda: (instance.shutdown(), instance.server_close(), thread.join(3)))
            return instance
        first = server()
        def request(instance, op, body, token=None):
            con = http.client.HTTPConnection('127.0.0.1', instance.server_port, timeout=30)
            con.request('POST', '/api/' + op, json.dumps(body), {'Content-Type': 'application/json',
                'X-Session-Token': token or instance.token, 'Origin': instance.origin})
            response = con.getresponse(); raw = response.read(); con.close()
            return response.status, raw
        for op in apuracao.OPERACOES:
            self.assertEqual(request(first, op, {'caso': 'alpha'}, 'inválido')[0], 403)
        status, raw = request(first, 'apuracao-salvar', {'caso': 'alpha', 'revisao': 0,
            'titulo': 'Persistência', 'texto': 'Salvo no disco.', 'requisicao_id': uuid.uuid4().hex})
        self.assertEqual(status, 200)
        second = server()  # Fresh process state/server token, same persisted case.
        status, raw = request(second, 'apuracao-listar', {'caso': 'alpha'})
        self.assertEqual(json.loads(raw)['notas'][0]['texto'], 'Salvo no disco.')
        for format in ('md', 'pdf', 'docx'):
            status, raw = request(second, 'apuracao-exportar', {'caso': 'alpha', 'formato': format})
            self.assertEqual(status, 200); self.assertTrue(raw)


if __name__ == '__main__':
    unittest.main()
