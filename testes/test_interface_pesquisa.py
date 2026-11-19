"""HTTP integration with temporary synthetic cases; no editorial evaluation."""
import http.client
import base64
import json
from pathlib import Path
import sys
import threading
import unittest
import importlib.util
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import PARTES, escrever_json, fluxo_esperado, manifesto_prompts, sha256
from criar_caso import criar_caso
from selecionar_caso import selecionar
from nova_rodada import criar_rodada
from interface_pesquisa import Servidor
from modelo_pasta import copiar


class InterfaceTest(unittest.TestCase):
    @staticmethod
    def montar(root):
        (root / 'prompts').mkdir()
        for name in PARTES:
            (root / 'prompts' / name).write_text('# Fixture sintética\n', encoding='utf-8')
        (root / 'prompts/FLUXO_COMPLETO.md').write_bytes(fluxo_esperado(root))
        escrever_json(root / 'prompts/manifesto_prompts.json', manifesto_prompts(root))
        (root / 'AGENTS.md').write_text('Fixture técnica.', encoding='utf-8')
        escrever_json(root / 'configuracao.json', {'caso_ativo': None, 'manifesto_ativo': None,
                       'maximo_documentos_inicial': 20, 'indice_sqlite': True})
        for case, word in [('alpha', 'Alfabeto'), ('beta', 'Betabetico')]:
            source = root / f'{case}.txt'
            source.write_text(f'{word} sintético. Código AB-123. <script>alert(1)</script>\n' * 80,
                              encoding='utf-8')
            criar_caso(root, case, 'Caso sintético ' + case, [source], 'sinteticos')
            selecionar(root, case)
            criar_rodada(root, 'R001', 'Pergunta de teste técnico sintético.')
        selecionar(root, None)

    def setUp(self):
        # Dois casos com rodada e índice, construídos uma vez por processo e copiados para cada teste.
        temp, self.root, _ = copiar('InterfaceTest', InterfaceTest.montar)
        self.addCleanup(temp.cleanup)
        self.server = Servidor(('127.0.0.1', 0), self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, path, data=None, headers=None, raw=False):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        defaults = {'Content-Type': 'application/json', 'X-Session-Token': self.server.token,
                    'Origin': self.server.origin}
        defaults.update(headers or {})
        connection.request('GET' if data is None else 'POST', path,
                           body=None if data is None else json.dumps(data), headers=defaults)
        response = connection.getresponse()
        content = response.read()
        result = (response.status, dict(response.getheaders()), content if raw else json.loads(content))
        connection.close()
        return result

    def query(self, **kwargs):
        return {'caso': 'alpha', 'rodada': 'R001', 'geracao': 'v1', 'consulta': 'Alfabeto', **kwargs}

    def test_vditor_local_integridade_e_rotas_fechadas(self):
        vendor = Path(__file__).resolve().parents[1] / 'interface/vendor/vditor'
        manifest = json.loads((vendor / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '4.0.1')
        for name, digest in manifest['files'].items():
            self.assertEqual(sha256(vendor / name), digest, name)
            if name.startswith('dist/'):
                status, headers, raw = self.request('/vendor/vditor/' + name, raw=True)
                self.assertEqual(status, 200, name)
                self.assertEqual(raw, (vendor / name).read_bytes())
                self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
                self.assertNotIn('unsafe-inline', headers['Content-Security-Policy'])
        for path in ('/vendor/vditor/manifesto.json', '/vendor/vditor/LICENSE',
                     '/vendor/vditor/../../configuracao.json'):
            self.assertEqual(self.request(path)[0], 404)

    def conversa_sintetica(self, identifier='a' * 32, caso='alpha', rodadas=None, estado='concluido'):
        meta = {'id': identifier, 'caso': caso, 'titulo': 'Pergunta sintética',
                'estado': estado, 'rodadas': rodadas or ['R001'], 'criada_em_utc': '2026-01-01T00:00:00Z'}
        escrever_json(self.root / f'conversas/{identifier}/conversa.json', meta)
        (self.root / f'conversas/{identifier}/eventos.jsonl').write_text('', encoding='utf-8')
        return meta

    def test_titulos_editoriais_somente_da_apuracao_solicitada(self):
        # Metadata names a frozen question; it does not execute or approve it.
        from interface_pesquisa import ler_json as read_json
        reads = []
        def observe(path):
            reads.append(Path(path))
            return read_json(path)
        with patch('interface_pesquisa.ler_json', side_effect=observe):
            status, _, result = self.request('/api/analises', {'caso': 'alpha'})
        self.assertEqual(status, 200)
        self.assertEqual(result['analises'][0]['pergunta'], 'Pergunta de teste técnico sintético.')
        self.assertTrue(result['analises'][0]['data'])
        self.assertFalse(any('execucoes/beta' in str(p).replace('\\', '/') for p in reads))
        self.assertIsNone(self.server.conversas.rpc)
        question = self.root / 'execucoes/alpha/R001/00_pergunta_original.md'
        question.write_text('Alteração sintética', encoding='utf-8')
        item = self.request('/api/analises', {'caso': 'alpha'})[2]['analises'][0]
        self.assertIn('divergente', item['aviso'])
        self.assertNotIn('pergunta', item)
        self.assertEqual(self.request('/api/analises', {'caso': '../beta'})[0], 400)

    def test_excluir_e_restaurar_apuracao_preserva_todos_os_arquivos_e_selecao_global(self):
        before = {p.relative_to(self.root): sha256(p) for p in self.root.rglob('*') if p.is_file()}
        status, _, result = self.request('/api/excluir', {'tipo': 'caso', 'caso': 'alpha'})
        self.assertEqual(status, 200)
        self.assertEqual([c['id'] for c in self.request('/api/catalogo')[2]['casos']], ['beta'])
        for operation in ('inventario', 'cobertura', 'achados-catalogo', 'codex-listar'):
            self.assertEqual(self.request('/api/' + operation, self.query())[0], 400)
        self.assertEqual(self.request('/api/cadastrar', self.upload(caso='alpha', novo=False))[0], 400)
        self.assertEqual(self.request('/api/codex-perguntar', {'caso': 'alpha', 'pergunta': 'Teste sintético.'})[0], 400)
        self.assertIsNone(self.server.conversas.rpc)
        self.assertEqual(before, {p: sha256(self.root / p) for p in before})
        self.assertEqual(self.request('/api/restaurar', {'item': result['item']['id']})[0], 200)
        self.assertEqual([c['id'] for c in self.request('/api/catalogo')[2]['casos']], ['alpha', 'beta'])
        self.assertEqual(before, {p: sha256(self.root / p) for p in before})
        # Restoration is idempotent in effect, but duplicate requests report a missing item.
        self.assertEqual(self.request('/api/restaurar', {'item': result['item']['id']})[0], 400)

    def test_excluir_conversa_oculta_suas_rodadas_e_preserva_complementos_na_restauracao(self):
        criar_rodada(self.root, 'R002', 'Complemento sintético.', caso='alpha')
        meta = self.conversa_sintetica(rodadas=['R001', 'R002'])
        before = (self.root / f'conversas/{meta["id"]}/conversa.json').read_bytes()
        payload = {'tipo': 'conversa', 'caso': 'alpha', 'conversa': meta['id']}
        self.assertEqual(self.request('/api/excluir', {**payload, 'caso': 'beta'})[0], 400)
        self.assertEqual(self.request('/api/excluir', {'tipo': 'rodada', 'caso': 'alpha', 'rodada': 'R001'})[0], 400)
        status, _, removed = self.request('/api/excluir', payload)
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/codex-listar', {'caso': 'alpha'})[2]['conversas'], [])
        self.assertEqual(self.request('/api/catalogo')[2]['casos'][0]['rodadas'], [])
        for round_id in ('R001', 'R002'):
            self.assertEqual(self.request('/api/cobertura', self.query(rodada=round_id))[0], 400)
        self.assertEqual(self.request('/api/codex-eventos', {'conversa': meta['id']})[0], 400)
        self.assertEqual(self.request('/api/excluir', payload)[0], 400)
        self.assertEqual(self.request('/api/restaurar', {'item': removed['item']['id']})[0], 200)
        self.assertEqual(len(self.request('/api/catalogo')[2]['casos'][0]['rodadas']), 2)
        self.assertEqual(self.request('/api/codex-listar', {'caso': 'alpha'})[2]['conversas'][0]['id'], meta['id'])
        self.assertEqual(before, (self.root / f'conversas/{meta["id"]}/conversa.json').read_bytes())

    def test_exclusoes_independentes_e_restauracao_da_apuracao_nao_restauram_itens_ja_excluidos(self):
        meta = self.conversa_sintetica()
        chat = self.request('/api/excluir', {'tipo': 'conversa', 'caso': 'alpha', 'conversa': meta['id']})[2]['item']
        case = self.request('/api/excluir', {'tipo': 'caso', 'caso': 'alpha'})[2]['item']
        self.assertEqual(self.request('/api/restaurar', {'item': chat['id']})[0], 400)
        self.assertEqual(self.request('/api/restaurar', {'item': case['id']})[0], 200)
        self.assertEqual(self.request('/api/catalogo')[2]['casos'][0]['rodadas'], [])
        self.assertEqual(self.request('/api/restaurar', {'item': chat['id']})[0], 200)
        self.assertEqual(len(self.request('/api/catalogo')[2]['casos'][0]['rodadas']), 1)

    def test_rodada_avulsa_e_lixeira_persistem_apos_reabrir_gerenciador(self):
        from codex_apuracao import Conversas
        status, _, removed = self.request('/api/excluir', {'tipo': 'rodada', 'caso': 'alpha', 'rodada': 'R001'})
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/catalogo')[2]['casos'][0]['rodadas'], [])
        self.assertEqual(len(self.request('/api/catalogo')[2]['casos'][1]['rodadas']), 1)
        manager = Conversas(self.root)
        try:
            manager.gerenciar('restaurar', {'item': removed['item']['id']})
        finally:
            manager.close()
        self.assertEqual(len(self.request('/api/catalogo')[2]['casos'][0]['rodadas']), 1)

    def test_exclusao_bloqueada_durante_execucao_inclusive_outro_cliente(self):
        meta = self.conversa_sintetica(estado='executando')
        self.server.conversas.contexts[meta['id']] = {'meta': meta, 'busy': True, 'events': []}
        for scope in ({'tipo': 'caso'}, {'tipo': 'conversa', 'conversa': meta['id']},
                      {'tipo': 'rodada', 'rodada': 'R001'}):
            self.assertEqual(self.request('/api/excluir', {'caso': 'alpha', **scope})[0], 400)
        self.assertEqual(self.request('/api/gerenciar-listar', {'caso': 'alpha'})[2]['lixeira'], [])
        self.server.conversas.contexts[meta['id']]['busy'] = False
        self.server.conversas.contexts[meta['id']]['meta']['estado'] = 'interrompido'
        self.assertEqual(self.request('/api/excluir', {'tipo': 'caso', 'caso': 'alpha'})[0], 200)

    def test_gerenciar_le_somente_metadados_e_nao_trava_com_estado_antigo_de_execucao(self):
        meta = self.conversa_sintetica(estado='executando')
        original = Path.read_text

        def read(path, *args, **kwargs):
            self.assertNotIn('originais', path.parts)
            self.assertNotIn('entradas', path.parts)
            self.assertNotEqual(path.name, 'eventos.jsonl')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'read_text', read):
            status, _, result = self.request('/api/gerenciar-listar', {'caso': 'alpha'})
            self.assertEqual(status, 200)
            self.assertEqual(result['conversas'][0]['estado'], 'interrompido')
            self.assertEqual(self.request('/api/excluir', {'tipo': 'conversa', 'caso': 'alpha', 'conversa': meta['id']})[0], 200)
        self.assertIsNone(self.server.conversas.rpc)

    def test_exclusao_e_restauracao_recusam_ids_caminhos_e_sessoes_invalidos(self):
        for values in ({'tipo': 'caso', 'caso': '../beta'}, {'tipo': 'desconhecido', 'caso': 'alpha'},
                       {'tipo': 'conversa', 'caso': 'alpha', 'conversa': '../a'},
                       {'tipo': 'rodada', 'caso': 'alpha', 'rodada': 'R001/..'},
                       {'tipo': 'caso', 'caso': 'inexistente'}):
            self.assertEqual(self.request('/api/excluir', values)[0], 400)
        for operation, scope in (('excluir', {'tipo': 'caso', 'caso': 'alpha'}), ('restaurar', {'item': 'a' * 32})):
            self.assertEqual(self.request('/api/' + operation, scope, {'X-Session-Token': 'invalido'})[0], 403)
            self.assertEqual(self.request('/api/' + operation, scope, {'Origin': 'https://example.test'})[0], 403)
        self.assertEqual(len(self.request('/api/catalogo')[2]['casos']), 2)

    def test_tela_catalogo_sem_selecao_automatica_ou_logs(self):
        before = (self.root / 'configuracao.json').read_bytes()
        status, headers, page = self.request('/', raw=True)
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), page)
        self.assertIn('frame-ancestors', headers['Content-Security-Policy'])
        status, _, result = self.request('/api/catalogo')
        self.assertEqual([c['id'] for c in result['casos']], ['alpha', 'beta'])
        self.assertEqual(result['casos'][0]['rodadas'], [{'id': 'R001', 'geracoes': ['v1']}])
        self.assertEqual(before, (self.root / 'configuracao.json').read_bytes())
        self.assertFalse(list(self.root.glob('execucoes/*/*/saidas/consultas_sqlite/*.json')))

    def test_indice_sem_permissao_nao_bloqueia_catalogo_de_outros_casos(self):
        original = Path.iterdir
        denied = self.root / 'execucoes/alpha/R001/indice'

        def listar(path):
            if path == denied:
                raise PermissionError('Índice de fixture sem permissão')
            return original(path)

        with patch.object(Path, 'iterdir', listar):
            status, _, result = self.request('/api/catalogo')
        self.assertEqual(status, 200)
        alpha, beta = result['casos']
        self.assertEqual(alpha['rodadas'][0]['geracoes'], [])
        self.assertIn('permissão', alpha['rodadas'][0]['aviso'])
        self.assertEqual(beta['rodadas'], [{'id': 'R001', 'geracoes': ['v1']}])

    def test_busca_paginacao_contexto_original_e_logs(self):
        run = self.root / 'execucoes/alpha/R001'
        before = sha256(run / 'indice/v1/apuracao.sqlite')
        status, _, result = self.request('/api/buscar', self.query(limite=1))
        self.assertEqual(status, 200)
        self.assertGreater(result['total_correspondencias'], 1)
        self.assertEqual(result['proximo_deslocamento'], 1)
        self.assertEqual(json.loads((run / result['arquivo_log']).read_text(encoding='utf-8')), result)
        hit = result['resultados'][0]
        self.assertIn('<script>', hit['trecho'])  # JSON data, rendered via textContent in the client.
        status, _, next_page = self.request('/api/buscar', self.query(limite=1, deslocamento=1))
        self.assertNotEqual(hit['referencia'], next_page['resultados'][0]['referencia'])
        status, _, context = self.request('/api/ler', self.query(referencia=hit['referencia']))
        self.assertEqual(len(context['unidade_completa']), 80)
        status, headers, original = self.request('/api/original', self.query(referencia=hit['referencia']), raw=True)
        self.assertEqual(status, 200)
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(original, (run / hit['original']).read_bytes())
        self.assertEqual(sha256(run / 'indice/v1/apuracao.sqlite'), before)

    def test_isolamento_filtros_consulta_invalida_e_cobertura(self):
        self.assertEqual(self.request('/api/buscar', self.query(consulta='Betabetico'))[2]['retornados'], 0)
        status, _, result = self.request('/api/buscar', self.query(consulta='AB-123', modo='literal', documentos=['D001']))
        self.assertEqual(status, 200)
        self.assertGreater(result['retornados'], 0)
        status, _, result = self.request('/api/buscar', self.query(documentos=['OUTRO']))
        self.assertEqual(status, 400)
        self.assertEqual(result['estado'], 'erro_consulta')
        self.assertIn('arquivo_log', result)
        self.assertEqual(self.request('/api/buscar', self.query(pagina=1))[2]['retornados'], 0)
        status, _, result = self.request('/api/buscar', self.query(consulta='NEAR(', modo='fts'))
        self.assertEqual(status, 400)
        self.assertEqual(result['estado'], 'erro_consulta')
        status, _, result = self.request('/api/cobertura', self.query())
        self.assertEqual(status, 200)
        self.assertEqual(result['cobertura']['documentos_pesquisaveis'], 1)

    def test_arquivos_arbitrarios_origens_e_payloads_recusados(self):
        for path in ('/configuracao.json', '/scripts/comum.py', '/../README.md'):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request('/api/buscar', self.query(), {'Host': 'example.test'})[0], 403)
        self.assertEqual(self.request('/api/buscar', self.query(), {'Origin': 'https://example.test'})[0], 403)
        self.assertEqual(self.request('/api/buscar', self.query(), {'X-Session-Token': 'errado'})[0], 403)
        for data in ([], self.query(caso='../beta'), self.query(documentos=[{}]), self.query(limite='10')):
            self.assertEqual(self.request('/api/buscar', data)[0], 400)
        self.assertEqual(self.request('/api/original', self.query(referencia='../../AGENTS.md'))[0], 400)

    def test_falha_de_integridade_e_indice_ausente_nao_sao_ausencia(self):
        status, _, result = self.request('/api/buscar', self.query(geracao='v2'))
        self.assertEqual(status, 400)
        self.assertIn('inexistente', result['erro'])
        database = self.root / 'execucoes/alpha/R001/indice/v1/apuracao.sqlite'
        with database.open('ab') as stream:
            stream.write(b'changed')
        status, _, result = self.request('/api/buscar', self.query())
        self.assertEqual(status, 400)
        self.assertIn('Hash', result['erro'])

    def upload(self, **kwargs):
        return {'caso': 'gamma', 'novo': True, 'titulo': 'Caso de cadastro sintético',
                'natureza': 'sinteticos', 'arquivos': [
                    {'nome': 'doc.txt', 'base64': base64.b64encode(b'Texto sintetico recebido.').decode()}], **kwargs}

    def test_upload_persiste_antes_da_pergunta_e_inventario_acumula_lotes(self):
        config = (self.root / 'configuracao.json').read_bytes()
        status, _, first = self.request('/api/cadastrar', self.upload())
        self.assertEqual(status, 200)
        self.assertEqual(first['recebidos'], 1)
        self.assertFalse((self.root / 'execucoes/gamma').exists())
        files = [*self.upload()['arquivos'], {'nome': 'doc.txt', 'base64': base64.b64encode(b'Outro texto sintetico.').decode()}]
        status, _, second = self.request('/api/cadastrar', self.upload(novo=False, arquivos=files))
        self.assertEqual(status, 200)
        self.assertEqual((second['recebidos'], second['novos'], second['duplicados']), (2, 1, 1))
        status, _, inventory = self.request('/api/inventario', {'caso': 'gamma'})
        self.assertEqual(status, 200)
        self.assertEqual(inventory['total_documentos'], 2)
        self.assertEqual((self.root / 'configuracao.json').read_bytes(), config)

    def test_cadastro_gera_id_interno_sem_exigir_slug_ou_misturar_nomes_iguais(self):
        config = (self.root / 'configuracao.json').read_bytes()
        results = []
        for _ in range(2):
            status, _, receipt = self.request('/api/cadastrar', self.upload(caso=None, titulo='Americanas — fatos relevantes'))
            self.assertEqual(status, 200)
            self.assertRegex(receipt['caso_id'], r'^apuracao_[a-f0-9]{32}$')
            self.assertEqual(receipt['inventario']['titulo'], 'Americanas — fatos relevantes')
            self.assertFalse((self.root / 'execucoes' / receipt['caso_id']).exists())
            results.append(receipt['caso_id'])
        self.assertNotEqual(*results)
        self.assertEqual(config, (self.root / 'configuracao.json').read_bytes())

    def test_eventos_apresentam_nomes_e_limitacoes_do_corpus_congelado(self):
        meta = self.conversa_sintetica()
        self.assertEqual(self.request('/api/cadastrar', self.upload(caso='alpha', novo=False))[0], 200)
        status, _, result = self.request('/api/codex-eventos', {'conversa': meta['id']})
        self.assertEqual(status, 200)
        frozen = result['acervos']['R001']
        self.assertEqual(len(frozen['documentos']), 1)
        self.assertEqual(frozen['documentos'][0]['nome_recebido'], 'alpha.txt')
        self.assertEqual(frozen['corpus_id'], 'alpha_v1')
        self.assertEqual(self.request('/api/inventario', {'caso': 'alpha'})[2]['total_documentos'], 2)
        self.assertNotIn('beta', result['acervos'])
        self.assertIsNone(self.server.conversas.rpc)

    def test_upload_invalido_nao_cria_caso_e_nao_recebe_caminhos(self):
        for files in ([], [{'nome': '../fora.txt', 'base64': ''}], [{'nome': 'a.txt', 'base64': '??'}],
                      [*self.upload()['arquivos'], {'nome': 'b.exe', 'base64': ''}]):
            status, _, result = self.request('/api/cadastrar', self.upload(arquivos=files))
            self.assertEqual(status, 400)
            self.assertFalse((self.root / 'casos/gamma').exists())
        self.assertEqual(self.request('/api/cadastrar', self.upload(), {'X-Session-Token': 'incorreto'})[0], 403)
        self.assertFalse((self.root / 'casos/gamma').exists())

    def test_upload_maior_que_limite_antigo_32kb_e_aceito(self):
        content = b'X' * 40000
        files = [{'nome': 'grande.txt', 'base64': base64.b64encode(content).decode()}]
        status, _, result = self.request('/api/cadastrar', self.upload(arquivos=files))
        self.assertEqual(status, 200)
        self.assertEqual(result['arquivos'][0]['bytes'], len(content))

    @unittest.skipUnless(importlib.util.find_spec('pypdf'), 'Instalar requirements.txt para extracao real')
    def test_upload_pdf_prepara_derivado_e_expoe_estado_no_recibo_e_inventario(self):
        from test_extracao_cadastro_pdf import pdf_sintetico
        source = pdf_sintetico(self.root / 'envio.pdf', ['Texto sintetico pela interface.'])
        files = [{'nome': 'envio.pdf', 'base64': base64.b64encode(source.read_bytes()).decode()}]
        status, _, result = self.request('/api/cadastrar', self.upload(arquivos=files))
        self.assertEqual(status, 200)
        self.assertEqual(result['arquivos'][0]['extracao_pdf']['estado'], 'extraido')
        self.assertEqual(result['extracao_pdf_resumo']['extraido'], 1)
        status, _, inventory = self.request('/api/inventario', {'caso': 'gamma'})
        self.assertEqual(status, 200)
        self.assertEqual(inventory['documentos'][0]['derivados'], 1)
        self.assertEqual(inventory['documentos'][0]['extracao_pdf']['paginas_com_texto'], 1)
        self.assertFalse((self.root / 'execucoes/gamma').exists())

    def test_ambiente_diagnostica_extrator_sem_abrir_modelo_e_protege_detalhes(self):
        status, _, result = self.request('/api/ambiente', {})
        self.assertEqual(status, 200)
        self.assertIn('disponivel', result['extracao_pdf'])
        self.assertEqual(result['python'], sys.executable)
        self.assertEqual(self.request('/api/ambiente', {}, {'X-Session-Token': 'invalido'})[0], 403)
        self.assertIsNone(self.server.conversas.rpc)

    @unittest.skipUnless(importlib.util.find_spec('pypdf'), 'Extrator PDF necessário')
    def test_preparar_pdfs_recupera_falha_de_dependencia_sem_reenvio_ou_alterar_rodada(self):
        from test_extracao_cadastro_pdf import pdf_sintetico
        pdf = pdf_sintetico(self.root / 'envio.pdf', ['Texto sintetico recuperado.'])
        files = [{'nome': 'envio.pdf', 'base64': base64.b64encode(pdf.read_bytes()).decode()}]
        failure = {'estado': 'erro', 'paginas_pdf': None, 'paginas_com_texto': 0,
                   'paginas_sem_texto': [], 'paginas_com_erro': [], 'ocr': False,
                   'metodo': None, 'mensagem': 'pypdf indisponivel neste Python'}
        with patch('cadastrar_documentos.extrair_pdf', return_value=failure):
            status, _, registered = self.request('/api/cadastrar', self.upload(arquivos=files))
        self.assertEqual(status, 200)
        original = self.root / registered['inventario']['documentos'][0]['arquivo']
        original_hash = sha256(original)
        receipt = self.root / registered['arquivo_recibo']
        receipt_hash = sha256(receipt)
        run = criar_rodada(self.root, 'R001', 'Fixture congelada antes da recuperação.', caso='gamma')
        frozen = {p.relative_to(run): sha256(p) for p in run.rglob('*') if p.is_file()}
        config = (self.root / 'configuracao.json').read_bytes()
        status, _, prepared = self.request('/api/preparar-pdfs', {'caso': 'gamma'})
        self.assertEqual(status, 200)
        self.assertEqual(prepared['corpus_id'], 'gamma_v2')
        self.assertEqual(prepared['extracao_pdf_resumo']['extraido'], 1)
        self.assertEqual(prepared['inventario']['documentos'][0]['extracao_pdf']['paginas_com_texto'], 1)
        self.assertEqual(prepared['inventario']['documentos'][0]['id'], 'D001')
        self.assertEqual(sha256(original), original_hash)
        self.assertEqual(sha256(receipt), receipt_hash)
        self.assertEqual(frozen, {p: sha256(run / p) for p in frozen})
        self.assertEqual(config, (self.root / 'configuracao.json').read_bytes())
        self.assertEqual([p.name for p in (self.root / 'execucoes/gamma').iterdir()], ['R001'])

    def test_preparacao_recusa_sem_extrator_lixeira_e_sessao_invalida(self):
        before = (self.root / 'casos/alpha/manifesto.json').read_bytes()
        with patch('interface_pesquisa.diagnostico', return_value={'extracao_pdf': {'disponivel': False}}):
            status, _, result = self.request('/api/preparar-pdfs', {'caso': 'alpha'})
        self.assertEqual(status, 400)
        self.assertIn('extrator', result['erro'])
        self.assertEqual(before, (self.root / 'casos/alpha/manifesto.json').read_bytes())
        self.assertEqual(self.request('/api/preparar-pdfs', {'caso': 'alpha'}, {'X-Session-Token': 'invalido'})[0], 403)
        self.assertEqual(self.request('/api/preparar-pdfs', {'caso': '../fora'})[0], 400)
        self.request('/api/excluir', {'tipo': 'caso', 'caso': 'alpha'})
        status, _, result = self.request('/api/preparar-pdfs', {'caso': 'alpha'})
        self.assertEqual(status, 400)
        self.assertIn('lixeira', result['erro'])
        self.assertEqual(before, (self.root / 'casos/alpha/manifesto.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
