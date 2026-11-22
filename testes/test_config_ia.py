"""Provider choice and API keys saved by the UI; no network or model calls."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import ROOT, escrever_json
import segredos
from inferencia_api import ErroIA, ServidorAPI, ler_inferencia, resumo_inferencia, salvar_inferencia, seguro

CHAVE_A = 'sk-ant-sintetica-0123456789abcdefWXYZ'
CHAVE_O = 'sk-proj-sintetica-0123456789abcdef9876'
SEM_CHAVES = {'ANTHROPIC_API_KEY': '', 'OPENAI_API_KEY': '', 'VLADO_SEGREDOS': ''}


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        escrever_json(self.root / 'configuracao.json', {'provedor': 'anthropic', 'modelo_preferido': None,
                                                         'max_tokens_saida': 4096})
        env = patch.dict(os.environ, SEM_CHAVES)
        env.start()
        self.addCleanup(env.stop)


class SegredosTest(Base):
    def test_chave_salva_fica_em_pasta_propria_e_resumo_mostra_so_o_final(self):
        segredos.salvar_chave(self.root, 'anthropic', CHAVE_A)
        arquivo = self.root / 'segredos/chaves.json'
        self.assertTrue(arquivo.is_file())
        self.assertEqual(segredos.ler_chave(self.root, 'anthropic'), CHAVE_A)
        resumo = segredos.resumo(self.root)
        self.assertEqual(resumo['anthropic'], {'configurada': True, 'origem': 'salva', 'final': 'WXYZ'})
        self.assertEqual(resumo['openai'], {'configurada': False, 'origem': None, 'final': None})
        self.assertNotIn(CHAVE_A, json.dumps(resumo))

    def test_variavel_de_ambiente_tem_prioridade_sobre_chave_salva(self):
        segredos.salvar_chave(self.root, 'anthropic', CHAVE_A)
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-do-ambiente-0123456789abcd'}):
            self.assertEqual(segredos.ler_chave(self.root, 'anthropic'), 'sk-ant-do-ambiente-0123456789abcd')
            self.assertEqual(segredos.resumo(self.root)['anthropic']['origem'], 'ambiente')

    def test_caminho_configuravel_para_volume(self):
        destino = self.root / 'volume' / 'chaves.json'
        with patch.dict(os.environ, {'VLADO_SEGREDOS': str(destino)}):
            segredos.salvar_chave(self.root, 'openai', CHAVE_O)
            self.assertTrue(destino.is_file())
            self.assertFalse((self.root / 'segredos').exists())

    def test_formatos_invalidos_sao_recusados_sem_ecoar_a_chave(self):
        for invalida in (None, 123, '', 'curta', 'sk-ant- com espaço 0123456789', 'sk-ant-\n0123456789abcdef', 'x' * 400):
            with self.subTest(invalida=invalida):
                with self.assertRaises(ValueError) as ctx:
                    segredos.salvar_chave(self.root, 'anthropic', invalida)
                if isinstance(invalida, str) and len(invalida) > 6:
                    self.assertNotIn(invalida, str(ctx.exception))
        with self.assertRaises(ValueError):
            segredos.salvar_chave(self.root, 'outro', CHAVE_A)

    def test_remover_chave(self):
        segredos.salvar_chave(self.root, 'anthropic', CHAVE_A)
        segredos.salvar_chave(self.root, 'openai', CHAVE_O)
        segredos.remover_chave(self.root, 'anthropic')
        self.assertIsNone(segredos.ler_chave(self.root, 'anthropic'))
        self.assertEqual(segredos.ler_chave(self.root, 'openai'), CHAVE_O)

    def test_chave_salva_e_omitida_por_seguro(self):
        segredos.salvar_chave(self.root, 'openai', CHAVE_O)
        self.assertNotIn(CHAVE_O, seguro(f'erro do proxy: {CHAVE_O}'))


class InferenciaAjustadaTest(Base):
    def setUp(self):
        super().setUp()
        # CUS-03: only models of the installation's list, each with a price, can be saved. These tests
        # switch to OpenAI and to Opus, so this test installation allows them (synthetic OpenAI price).
        config = json.loads((self.root / 'configuracao.json').read_text(encoding='utf-8'))
        config['orcamento'] = {'modelos_permitidos': ['claude-sonnet-5-5', 'claude-opus-5-5', 'gpt-6.1-sol']}
        escrever_json(self.root / 'configuracao.json', config)
        tabela = json.loads((ROOT / 'precos_modelos.json').read_text(encoding='utf-8'))
        tabela['modelos'].setdefault('openai', {})['gpt-6.1-sol'] = {
            'entrada': 1.0, 'cache_leitura': 0.1, 'cache_escrita_5m': 0.0, 'cache_escrita_1h': 0.0, 'saida': 8.0}
        escrever_json(self.root / 'precos_modelos.json', tabela)

    def test_ajuste_pela_interface_sobrepoe_configuracao_sem_alterar_arquivo_versionado(self):
        antes = (self.root / 'configuracao.json').read_bytes()
        salvar_inferencia(self.root, {'provedor': 'openai', 'modelo_preferido': None})
        self.assertEqual(antes, (self.root / 'configuracao.json').read_bytes())
        inferencia = ler_inferencia(self.root)
        self.assertEqual((inferencia.provedor, inferencia.modelo, inferencia.max_tokens), ('openai', 'gpt-6.1-sol', 4096))
        salvar_inferencia(self.root, {'provedor': 'anthropic', 'modelo_preferido': '  claude-opus-5-5 '})
        self.assertEqual(ler_inferencia(self.root).modelo, 'claude-opus-5-5')

    def test_salvar_com_chave_registra_chave_e_resumo_nao_a_devolve(self):
        resultado = salvar_inferencia(self.root, {'provedor': 'openai', 'modelo_preferido': None, 'chave': CHAVE_O})
        self.assertNotIn(CHAVE_O, json.dumps(resultado))
        self.assertTrue(resultado['chaves']['openai']['configurada'])
        self.assertEqual(resultado['provedor'], 'openai')
        self.assertEqual(resultado['modelo'], 'gpt-6.1-sol')
        self.assertEqual(resultado['modelos_padrao'], {'anthropic': 'claude-sonnet-5-5', 'openai': 'gpt-6.1-sol'})

    def test_entradas_invalidas_nao_gravam_nada(self):
        for dados in ({'provedor': 'outro'}, {'provedor': 'openai', 'modelo_preferido': '   '},
                      {'provedor': 'openai', 'modelo_preferido': 5}, {'provedor': 'openai', 'chave': 'curta'},
                      {'provedor': 'openai', 'extra': 1}):
            with self.subTest(dados=dados):
                with self.assertRaises(ValueError):
                    salvar_inferencia(self.root, dados)
        self.assertFalse((self.root / 'ajustes').exists())
        self.assertFalse((self.root / 'segredos').exists())

    def test_remover_chave_pelo_ajuste(self):
        salvar_inferencia(self.root, {'provedor': 'anthropic', 'chave': CHAVE_A})
        resultado = salvar_inferencia(self.root, {'provedor': 'anthropic', 'remover_chave': True})
        self.assertFalse(resultado['chaves']['anthropic']['configurada'])

    def test_servidor_api_autentica_com_chave_salva(self):
        servidor = ServidorAPI(self.root, lambda message: None, criar_provedor=lambda inf, chave: None)
        self.addCleanup(servidor.close)
        self.assertIsNone(servidor.call('account/read', {})['account'])
        salvar_inferencia(self.root, {'provedor': 'anthropic', 'chave': CHAVE_A})
        self.assertEqual(servidor.call('account/read', {})['account']['type'], 'api')
        self.assertEqual(resumo_inferencia(self.root)['chaves']['anthropic']['origem'], 'salva')

    def test_ajuste_ilegivel_falha_com_mensagem_clara(self):
        (self.root / 'ajustes').mkdir()
        (self.root / 'ajustes/inferencia.json').write_text('[1]', encoding='utf-8')
        with self.assertRaisesRegex(ErroIA, 'ajustes'):
            ler_inferencia(self.root)


class HttpConfigTest(Base):
    def test_operacoes_http_salvam_e_nunca_devolvem_a_chave(self):
        from interface_pesquisa import Servidor
        server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(3)))

        def post(operation, data):
            con = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            con.request('POST', '/api/' + operation, json.dumps(data),
                        {'Content-Type': 'application/json', 'Origin': server.origin, 'X-Session-Token': server.token})
            response = con.getresponse()
            status, body = response.status, response.read().decode('utf-8')
            con.close()
            return status, body

        status, body = post('ia-config-salvar', {'provedor': 'anthropic', 'modelo_preferido': None, 'chave': CHAVE_A})
        self.assertEqual(status, 200, body)
        self.assertNotIn(CHAVE_A, body)
        status, body = post('ia-config', {})
        self.assertEqual(status, 200)
        self.assertNotIn(CHAVE_A, body)
        self.assertEqual(json.loads(body)['chaves']['anthropic']['final'], 'WXYZ')
        status, body = post('codex-status', {})
        self.assertTrue(json.loads(body)['autenticado'])
        status, body = post('ia-config-salvar', {'provedor': 'anthropic', 'chave': 'curta'})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
