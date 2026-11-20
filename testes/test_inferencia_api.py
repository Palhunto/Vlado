"""API adapter contract with a scripted provider; no network, keys or model calls."""
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import escrever_json
from inferencia_api import ErroIA, Resposta, ServidorAPI, ler_inferencia, seguro

TOOLS = [{'type': 'function', 'name': 'consultar_acervo', 'description': 'Ferramenta sintética.',
          'inputSchema': {'type': 'object', 'properties': {'acao': {'type': 'string'}}, 'required': ['acao']}}]


class ProvedorRoteirizado:
    """Returns scripted answers; each item is a Resposta or an exception."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.chamadas = []
        self.bloqueio = None
        self.entrou = threading.Event()

    def gerar(self, *, modelo, instrucoes, historico, ferramentas, max_tokens, ao_texto, cancelado):
        self.entrou.set()
        self.chamadas.append({'modelo': modelo, 'instrucoes': instrucoes,
                              'historico': json.loads(json.dumps(historico)),
                              'ferramentas': ferramentas, 'max_tokens': max_tokens})
        if self.bloqueio is not None:
            self.bloqueio.wait(5)
        item = self.roteiro.pop(0)
        if isinstance(item, Exception):
            raise item
        for parte in item.texto.split(' '):
            if parte:
                ao_texto(parte + ' ')
        return item


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        escrever_json(self.root / 'configuracao.json', {'provedor': 'anthropic',
                      'modelo_preferido': 'modelo-sintetico', 'max_tokens_saida': 2048})
        self.workspace = self.root / 'conversas' / ('a' * 32) / 'workspace'
        self.workspace.mkdir(parents=True)
        self.mensagens = queue.Queue()
        self.provedor = ProvedorRoteirizado([])
        env = patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-sintetica'}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        self.servidor = self.novo_servidor()

    def novo_servidor(self):
        servidor = ServidorAPI(self.root, self.mensagens.put, criar_provedor=lambda inf, chave: self.provedor)
        self.addCleanup(servidor.close)
        return servidor

    def iniciar_thread(self, servidor=None):
        servidor = servidor or self.servidor
        result = servidor.call('thread/start', {'cwd': str(self.workspace), 'model': 'modelo-sintetico',
                               'developerInstructions': 'Instrução sintética.', 'dynamicTools': TOOLS})
        return result['thread']['id']

    def proxima(self, metodo, timeout=5):
        while True:
            message = self.mensagens.get(timeout=timeout)
            if message['method'] == metodo:
                return message

    def turno(self, thread, texto='Pergunta sintética.', servidor=None):
        servidor = servidor or self.servidor
        return servidor.call('turn/start', {'threadId': thread, 'input': [{'type': 'text', 'text': texto}]})


class ConfiguracaoTest(Base):
    def test_le_provedor_modelo_e_limite_de_saida(self):
        inferencia = ler_inferencia(self.root)
        self.assertEqual((inferencia.provedor, inferencia.modelo, inferencia.max_tokens),
                         ('anthropic', 'modelo-sintetico', 2048))

    def test_modelo_nulo_usa_padrao_documentado_do_provedor(self):
        escrever_json(self.root / 'configuracao.json', {'provedor': 'openai', 'modelo_preferido': None})
        inferencia = ler_inferencia(self.root)
        self.assertEqual((inferencia.provedor, inferencia.modelo), ('openai', 'gpt-6.1-sol'))
        self.assertGreater(inferencia.max_tokens, 0)

    def test_configuracao_invalida_falha_com_mensagem_clara(self):
        casos = [({'provedor': 'outro'}, 'provedor'), ({}, 'provedor'),
                 ({'provedor': 'anthropic', 'modelo_preferido': '  '}, 'modelo_preferido'),
                 ({'provedor': 'anthropic', 'max_tokens_saida': 0}, 'max_tokens_saida'),
                 ([1, 2], 'configuracao.json')]
        for valor, trecho in casos:
            with self.subTest(valor=valor):
                escrever_json(self.root / 'configuracao.json', valor)
                with self.assertRaisesRegex(ErroIA, trecho):
                    ler_inferencia(self.root)

    def test_conta_sem_chave_nao_autentica_e_nunca_expoe_a_chave(self):
        account = self.servidor.call('account/read', {})['account']
        self.assertEqual((account['type'], account['provedor'], account['modelo']),
                         ('api', 'anthropic', 'modelo-sintetico'))
        self.assertNotIn('sk-ant-sintetica', json.dumps(account))
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': ''}):
            self.assertIsNone(self.servidor.call('account/read', {})['account'])

    def test_catalogo_lista_somente_o_modelo_configurado(self):
        data = self.servidor.call('model/list', {})['data']
        self.assertEqual([m['model'] for m in data], ['modelo-sintetico'])
        self.assertTrue(data[0]['isDefault'])

    def test_seguro_omite_chaves_de_api(self):
        self.assertNotIn('sk-ant-123456', seguro('falha com sk-ant-123456 no texto'))
        self.assertNotIn('sk-proj-abc', seguro('Authorization: Bearer sk-proj-abc'))
        self.assertNotIn('sk-proj-colada', seguro('chave_sk-proj-colada'))

    def test_seguro_omite_valor_exato_da_chave_configurada_em_qualquer_formato(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'gateway-XYZ-123456789'}):
            self.assertNotIn('gateway-XYZ-123456789', seguro('erro do proxy: token=gateway-XYZ-123456789;'))


class TurnoTest(Base):
    def test_resposta_textual_emite_deltas_mensagem_uso_e_conclusao(self):
        self.provedor.roteiro = [Resposta('Resposta sintética final.', (), {'entrada': 10, 'saida': 4}, 'modelo-sintetico')]
        thread = self.iniciar_thread()
        turn = self.turno(thread)['turn']
        self.assertEqual(turn['status'], 'inProgress')
        delta = self.proxima('item/agentMessage/delta')
        self.assertEqual(delta['params']['threadId'], thread)
        item = self.proxima('item/completed')['params']['item']
        self.assertEqual((item['type'], item['text']), ('agentMessage', 'Resposta sintética final.'))
        uso = self.proxima('item/usage')['params']
        self.assertEqual((uso['uso']['entrada'], uso['modelo']), (10, 'modelo-sintetico'))
        done = self.proxima('turn/completed')['params']['turn']
        self.assertEqual((done['id'], done['status']), (turn['id'], 'completed'))
        chamada = self.provedor.chamadas[0]
        self.assertEqual((chamada['modelo'], chamada['instrucoes'], chamada['max_tokens']),
                         ('modelo-sintetico', 'Instrução sintética.', 2048))
        self.assertEqual(chamada['historico'], [{'papel': 'usuario', 'texto': 'Pergunta sintética.'}])
        self.assertEqual(chamada['ferramentas'][0]['name'], 'consultar_acervo')

    def test_chamada_de_ferramenta_vira_pedido_ao_backend_e_resultado_volta_ao_provedor(self):
        chamada = {'id': 'call-1', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'cobertura'}}
        self.provedor.roteiro = [Resposta('', (chamada,), {}, 'modelo-sintetico'),
                                 Resposta('Concluído.', (), {}, 'modelo-sintetico')]
        thread = self.iniciar_thread()
        self.turno(thread)
        pedido = self.proxima('item/tool/call')
        self.assertIn('id', pedido)
        self.assertEqual((pedido['params']['tool'], pedido['params']['arguments']),
                         ('consultar_acervo', {'acao': 'cobertura'}))
        imagem = 'data:image/png;base64,' + 'A' * 8
        self.servidor.send({'id': pedido['id'], 'result': {'success': True, 'contentItems': [
            {'type': 'inputText', 'text': '{"estado": "ok"}'}, {'type': 'inputImage', 'imageUrl': imagem}]}})
        self.assertEqual(self.proxima('turn/completed')['params']['turn']['status'], 'completed')
        historico = self.provedor.chamadas[1]['historico']
        self.assertEqual(historico[1], {'papel': 'assistente', 'texto': '', 'chamadas': [chamada]})
        self.assertEqual(historico[2], {'papel': 'ferramenta', 'id': 'call-1', 'texto': '{"estado": "ok"}',
                                        'erro': False, 'imagens': [{'mime': 'image/png', 'dados': 'A' * 8}]})

    def test_resultado_de_ferramenta_com_falha_e_marcado_como_erro(self):
        chamada = {'id': 'call-2', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'x'}}
        self.provedor.roteiro = [Resposta('', (chamada,), {}, 'm'), Resposta('Ok.', (), {}, 'm')]
        self.turno(self.iniciar_thread())
        pedido = self.proxima('item/tool/call')
        self.servidor.send({'id': pedido['id'], 'result': {'success': False,
                            'contentItems': [{'type': 'inputText', 'text': 'Ação inválida.'}]}})
        self.proxima('turn/completed')
        self.assertTrue(self.provedor.chamadas[1]['historico'][2]['erro'])

    def test_erro_do_provedor_encerra_turno_com_falha_e_codigo(self):
        self.provedor.roteiro = [ErroIA('Limite de uso da API atingido.', codigo='limite')]
        self.turno(self.iniciar_thread())
        turn = self.proxima('turn/completed')['params']['turn']
        self.assertEqual(turn['status'], 'failed')
        self.assertIn('Limite', turn['error']['message'])
        self.assertEqual(turn['error']['codexErrorInfo'], 'limite')

    def test_excecao_inesperada_do_provedor_tambem_encerra_turno(self):
        self.provedor.roteiro = [RuntimeError('falha com sk-ant-vazada')]
        self.turno(self.iniciar_thread())
        turn = self.proxima('turn/completed')['params']['turn']
        self.assertEqual(turn['status'], 'failed')
        self.assertNotIn('sk-ant-vazada', turn['error']['message'])

    def test_interromper_durante_ferramenta_fecha_chamadas_pendentes(self):
        chamada = {'id': 'call-3', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'cobertura'}}
        self.provedor.roteiro = [Resposta('', (chamada,), {}, 'm'), Resposta('Retomada.', (), {}, 'm')]
        thread = self.iniciar_thread()
        turn = self.turno(thread)['turn']
        self.proxima('item/tool/call')
        self.servidor.call('turn/interrupt', {'threadId': thread, 'turnId': turn['id']})
        self.assertEqual(self.proxima('turn/completed')['params']['turn']['status'], 'interrupted')
        self.turno(thread, 'Complemento.')
        self.proxima('turn/completed')
        historico = self.provedor.chamadas[1]['historico']
        self.assertEqual(historico[2]['id'], 'call-3')
        self.assertTrue(historico[2]['erro'])
        self.assertEqual(historico[3], {'papel': 'usuario', 'texto': 'Complemento.'})

    def test_limite_de_passos_encerra_turno_com_falha(self):
        chamada = {'id': 'c', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'cobertura'}}
        thread = self.iniciar_thread()
        with patch('inferencia_api.MAX_PASSOS', 2):
            self.provedor.roteiro = [Resposta('', (dict(chamada, id=f'c{i}'),), {}, 'm') for i in range(3)]
            self.turno(thread)
            for _ in range(2):
                pedido = self.proxima('item/tool/call')
                self.servidor.send({'id': pedido['id'], 'result': {'success': True, 'contentItems': []}})
            turn = self.proxima('turn/completed')['params']['turn']
        self.assertEqual(turn['status'], 'failed')
        self.assertIn('passos', turn['error']['message'])

    def test_segundo_turno_simultaneo_na_mesma_thread_e_recusado(self):
        self.provedor.bloqueio = threading.Event()
        self.provedor.roteiro = [Resposta('Ok.', (), {}, 'm')]
        thread = self.iniciar_thread()
        self.turno(thread)
        with self.assertRaisesRegex(ErroIA, 'andamento'):
            self.turno(thread)
        self.provedor.bloqueio.set()
        self.proxima('turn/completed')


class ImagensTest(Base):
    def test_historico_enviado_mantem_somente_as_imagens_mais_recentes(self):
        roteiro = [Resposta('', ({'id': f'c{i}', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'imagem'}},), {}, 'm')
                   for i in range(5)]
        self.provedor.roteiro = roteiro + [Resposta('Fim.', (), {}, 'm')]
        self.turno(self.iniciar_thread())
        for _ in range(5):
            pedido = self.proxima('item/tool/call')
            self.servidor.send({'id': pedido['id'], 'result': {'success': True, 'contentItems': [
                {'type': 'inputImage', 'imageUrl': 'data:image/png;base64,QUJD'}]}})
        self.proxima('turn/completed')
        ultima = self.provedor.chamadas[-1]['historico']
        com_imagem = [m['id'] for m in ultima if m.get('imagens')]
        self.assertEqual(com_imagem, ['c2', 'c3', 'c4'])


class PersistenciaTest(Base):
    def test_historico_persiste_sem_imagens_e_e_retomado_por_outro_processo(self):
        chamada = {'id': 'call-9', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'imagem'}}
        self.provedor.roteiro = [Resposta('', (chamada,), {}, 'm'), Resposta('Primeira.', (), {}, 'm')]
        thread = self.iniciar_thread()
        self.turno(thread)
        pedido = self.proxima('item/tool/call')
        self.servidor.send({'id': pedido['id'], 'result': {'success': True, 'contentItems': [
            {'type': 'inputImage', 'imageUrl': 'data:image/png;base64,QUJD'}]}})
        self.proxima('turn/completed')
        arquivo = self.workspace.parent / 'api_historico.json'
        self.assertNotIn('QUJD', arquivo.read_text(encoding='utf-8'))
        self.servidor.close()
        outro = self.novo_servidor()
        self.provedor.roteiro = [Resposta('Segunda.', (), {}, 'm')]
        result = outro.call('thread/resume', {'threadId': thread, 'cwd': str(self.workspace),
                            'model': 'modelo-sintetico', 'developerInstructions': 'Instrução retomada.'})
        self.assertEqual(result['thread']['id'], thread)
        self.turno(thread, 'Complemento.', servidor=outro)
        self.proxima('turn/completed')
        chamada_final = self.provedor.chamadas[-1]
        self.assertEqual(chamada_final['instrucoes'], 'Instrução retomada.')
        self.assertEqual(chamada_final['ferramentas'][0]['name'], 'consultar_acervo')
        textos = [m.get('texto') for m in chamada_final['historico']]
        self.assertEqual(textos[0], 'Pergunta sintética.')
        self.assertIn('Primeira.', textos)
        self.assertEqual(textos[-1], 'Complemento.')
        self.assertEqual(chamada_final['historico'][2]['imagens'], [])

    def test_retomar_apos_trocar_provedor_exige_nova_conversa(self):
        thread = self.iniciar_thread()
        escrever_json(self.root / 'configuracao.json', {'provedor': 'openai', 'modelo_preferido': None})
        with self.assertRaisesRegex(ErroIA, 'anthropic'):
            self.servidor.call('thread/resume', {'threadId': thread, 'cwd': str(self.workspace),
                               'model': 'modelo-sintetico', 'developerInstructions': ''})

    def test_workspace_fora_de_conversas_e_recusado(self):
        with self.assertRaisesRegex(ErroIA, 'conversas'):
            self.servidor.call('thread/start', {'cwd': str(self.root), 'model': 'm',
                               'developerInstructions': '', 'dynamicTools': TOOLS})

    def test_retomar_thread_inexistente_falha(self):
        with self.assertRaisesRegex(ErroIA, 'histórico'):
            self.servidor.call('thread/resume', {'threadId': 'b' * 32, 'cwd': str(self.workspace),
                               'model': 'm', 'developerInstructions': ''})

    def test_metodo_desconhecido_e_recusado(self):
        with self.assertRaisesRegex(ErroIA, 'não suportado'):
            self.servidor.call('account/login/start', {'type': 'chatgpt'})


class RobustezTest(Base):
    def test_retomar_reutiliza_thread_e_novo_turno_aguarda_turno_cancelado_encerrar(self):
        self.provedor.bloqueio = threading.Event()
        self.provedor.roteiro = [Resposta('Velha.', (), {}, 'm'), Resposta('Nova.', (), {}, 'm')]
        thread = self.iniciar_thread()
        antigo = self.turno(thread)['turn']['id']
        self.assertTrue(self.provedor.entrou.wait(5))
        self.servidor.call('turn/interrupt', {'threadId': thread, 'turnId': antigo})
        self.servidor.call('thread/resume', {'threadId': thread, 'cwd': str(self.workspace),
                           'model': 'modelo-sintetico', 'developerInstructions': 'Nova instrução.'})
        threading.Timer(0.3, self.provedor.bloqueio.set).start()
        self.turno(thread, 'Complemento.')
        encerrados = [self.proxima('turn/completed')['params']['turn'] for _ in range(2)]
        self.assertEqual([t['id'] == antigo for t in encerrados], [True, False])
        self.assertEqual(encerrados[1]['status'], 'completed')
        self.assertEqual(self.provedor.chamadas[-1]['historico'][-1], {'papel': 'usuario', 'texto': 'Complemento.'})
        self.assertEqual(self.provedor.chamadas[-1]['instrucoes'], 'Nova instrução.')
        salvo = json.loads((self.workspace.parent / 'api_historico.json').read_text(encoding='utf-8'))
        self.assertEqual(salvo['mensagens'][-1]['texto'], 'Nova.')

    def test_turno_cancelado_que_nao_encerra_bloqueia_novo_turno_com_mensagem(self):
        self.provedor.bloqueio = threading.Event()
        self.provedor.roteiro = [Resposta('Velha.', (), {}, 'm')]
        thread = self.iniciar_thread()
        registro = self.servidor.threads[thread]
        # Release the blocked worker and let it finish before the temporary folder is removed.
        self.addCleanup(lambda: (self.provedor.bloqueio.set(), registro.ocioso.wait(5)))
        antigo = self.turno(thread)['turn']['id']
        self.assertTrue(self.provedor.entrou.wait(5))
        self.servidor.call('turn/interrupt', {'threadId': thread, 'turnId': antigo})
        with patch('inferencia_api.ESPERA_ENCERRAMENTO', 0.2):
            with self.assertRaisesRegex(ErroIA, 'encerrado'):
                self.turno(thread, 'Complemento.')

    def test_interrupcao_de_outro_turno_e_ignorada(self):
        self.provedor.bloqueio = threading.Event()
        self.provedor.roteiro = [Resposta('Ok.', (), {}, 'm')]
        thread = self.iniciar_thread()
        self.turno(thread)
        self.servidor.call('turn/interrupt', {'threadId': thread, 'turnId': 'turno-antigo'})
        self.provedor.bloqueio.set()
        self.assertEqual(self.proxima('turn/completed')['params']['turn']['status'], 'completed')

    def test_falha_ao_persistir_ainda_encerra_turno_e_libera_thread(self):
        self.provedor.roteiro = [Resposta('Ok.', (), {}, 'm'), Resposta('Outro.', (), {}, 'm')]
        thread = self.iniciar_thread()
        with patch('inferencia_api._Thread.persistir', side_effect=TypeError('não serializável')):
            self.turno(thread)
            turn = self.proxima('turn/completed')['params']['turn']
        self.assertEqual(turn['status'], 'failed')
        self.assertIn('histórico', turn['error']['message'])
        self.turno(thread, 'De novo.')
        self.assertEqual(self.proxima('turn/completed')['params']['turn']['status'], 'completed')

    def test_excecao_no_callback_nao_impede_conclusao_do_turno(self):
        recebidas = queue.Queue()

        def callback(message):
            if message['method'] == 'item/completed':
                raise FileExistsError('artefato já existe')
            recebidas.put(message)

        self.mensagens = recebidas
        servidor = ServidorAPI(self.root, callback, criar_provedor=lambda inf, chave: self.provedor)
        self.addCleanup(servidor.close)
        self.provedor.roteiro = [Resposta('Ok.', (), {}, 'm')]
        thread = self.iniciar_thread(servidor)
        self.turno(thread, servidor=servidor)
        self.assertEqual(self.proxima('turn/completed')['params']['turn']['status'], 'completed')

    def test_fechar_durante_espera_de_ferramenta_libera_o_worker(self):
        chamada = {'id': 'c1', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'cobertura'}}
        self.provedor.roteiro = [Resposta('', (chamada,), {}, 'm')]
        thread = self.iniciar_thread()
        self.turno(thread)
        self.proxima('item/tool/call')
        self.servidor.close()
        registro = self.servidor.threads[thread]
        limite = threading.Event()
        for _ in range(100):
            if registro.turno is None:
                break
            limite.wait(0.02)
        self.assertIsNone(registro.turno)

    def test_conversa_da_integracao_anterior_pede_nova_conversa(self):
        with self.assertRaisesRegex(ErroIA, 'nova conversa'):
            self.servidor.call('thread/resume', {'threadId': 'c' * 32, 'cwd': str(self.workspace),
                               'model': 'gpt-5.6-sol', 'developerInstructions': ''})


if __name__ == '__main__':
    unittest.main()
