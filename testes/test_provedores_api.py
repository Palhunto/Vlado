"""Provider translations with fake SDK clients; no network, keys or model calls."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inferencia_api import ErroIA, mapear_erro
from provedor_anthropic import ProvedorAnthropic
from provedor_openai import ProvedorOpenAI

FERRAMENTAS = [{'name': 'consultar_acervo', 'description': 'Sintética.',
                'parameters': {'type': 'object', 'properties': {'acao': {'type': 'string'}}}}]
HISTORICO = [
    {'papel': 'usuario', 'texto': 'Pergunta.'},
    {'papel': 'assistente', 'texto': 'Vou buscar.', 'chamadas': [
        {'id': 'call-1', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'buscar'}}]},
    {'papel': 'ferramenta', 'id': 'call-1', 'texto': '{"ok": 1}', 'erro': False,
     'imagens': [{'mime': 'image/png', 'dados': 'QUJD'}]},
    {'papel': 'usuario', 'texto': 'Complemento.'},
]


def gerar(provedor, historico=HISTORICO, cancelado=lambda: False):
    deltas = []
    resposta = provedor.gerar(modelo='m', instrucoes='Regras.', historico=historico, ferramentas=FERRAMENTAS,
                              max_tokens=100, ao_texto=deltas.append, cancelado=cancelado)
    return resposta, deltas


# -- Anthropic fakes -----------------------------------------------------------
class StreamAnthropic:
    def __init__(self, eventos, final):
        self.eventos, self.final = eventos, final
        self.current_message_snapshot = final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for evento in self.eventos:
            if isinstance(evento, Exception):
                raise evento
            yield evento

    def get_final_message(self):
        return self.final


class ClienteAnthropic:
    def __init__(self, stream):
        self.stream_obj, self.kwargs = stream, None
        self.messages = NS(stream=self._stream)

    def _stream(self, **kwargs):
        self.kwargs = kwargs
        return self.stream_obj


def mensagem_anthropic(content, stop='end_turn'):
    return NS(content=content, model='claude-sintetico', stop_reason=stop,
              usage=NS(input_tokens=11, output_tokens=7, cache_read_input_tokens=5, cache_creation_input_tokens=None))


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class APITimeoutError(APIConnectionError):
    pass


class AnthropicTest(unittest.TestCase):
    def test_converte_historico_ferramentas_e_cache(self):
        final = mensagem_anthropic([NS(type='text', text='Pronto.')])
        cliente = ClienteAnthropic(StreamAnthropic([NS(type='text', text='Pronto.')], final))
        resposta, deltas = gerar(ProvedorAnthropic('k', cliente=cliente))
        kw = cliente.kwargs
        self.assertEqual((kw['model'], kw['max_tokens'], kw['system']), ('m', 100, 'Regras.'))
        self.assertEqual(kw['cache_control'], {'type': 'ephemeral'})
        self.assertEqual(kw['tools'], [{'name': 'consultar_acervo', 'description': 'Sintética.',
                                        'input_schema': FERRAMENTAS[0]['parameters']}])
        msgs = kw['messages']
        self.assertEqual([m['role'] for m in msgs], ['user', 'assistant', 'user'])
        self.assertEqual(msgs[1]['content'], [{'type': 'text', 'text': 'Vou buscar.'},
                         {'type': 'tool_use', 'id': 'call-1', 'name': 'consultar_acervo', 'input': {'acao': 'buscar'}}])
        resultado, complemento = msgs[2]['content']
        self.assertEqual((resultado['type'], resultado['tool_use_id'], resultado['is_error']),
                         ('tool_result', 'call-1', False))
        self.assertEqual(resultado['content'][1], {'type': 'image', 'source': {
            'type': 'base64', 'media_type': 'image/png', 'data': 'QUJD'}})
        self.assertEqual(complemento, {'type': 'text', 'text': 'Complemento.'})
        self.assertEqual(deltas, ['Pronto.'])
        self.assertEqual((resposta.texto, resposta.chamadas, resposta.modelo), ('Pronto.', (), 'claude-sintetico'))
        # CUS-01: the priced kinds too (here input_tokens excludes the cache; no write, so no validity).
        self.assertEqual(resposta.uso, {'entrada': 11, 'saida': 7, 'cache_leitura': 5, 'cache_escrita': 0,
                                        'entrada_sem_cache': 11, 'cache_escrita_5m': 0, 'cache_escrita_1h': 0})

    def test_tool_use_vira_chamada_neutra(self):
        final = mensagem_anthropic([NS(type='text', text='Busco.'),
                                    NS(type='tool_use', id='tu-1', name='consultar_acervo', input={'acao': 'cobertura'})],
                                   stop='tool_use')
        resposta, _ = gerar(ProvedorAnthropic('k', cliente=ClienteAnthropic(StreamAnthropic([], final))))
        self.assertEqual(resposta.chamadas, ({'id': 'tu-1', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'cobertura'}},))

    def test_mensagens_vazias_sao_omitidas_e_papeis_consecutivos_unidos(self):
        historico = [{'papel': 'usuario', 'texto': 'A'}, {'papel': 'assistente', 'texto': ''},
                     {'papel': 'usuario', 'texto': 'B'}]
        cliente = ClienteAnthropic(StreamAnthropic([], mensagem_anthropic([NS(type='text', text='C')])))
        gerar(ProvedorAnthropic('k', cliente=cliente), historico)
        self.assertEqual(cliente.kwargs['messages'], [{'role': 'user', 'content': [
            {'type': 'text', 'text': 'A'}, {'type': 'text', 'text': 'B'}]}])

    def test_cancelamento_descarta_chamadas_incompletas(self):
        final = mensagem_anthropic([NS(type='text', text='Par'),
                                    NS(type='tool_use', id='x', name='consultar_acervo', input={})], stop=None)
        eventos = [NS(type='text', text='Par'), NS(type='text', text='cial')]
        resposta, deltas = gerar(ProvedorAnthropic('k', cliente=ClienteAnthropic(StreamAnthropic(eventos, final))),
                                 cancelado=lambda: True)
        self.assertEqual((deltas, resposta.chamadas), ([], ()))

    def test_truncamento_com_ferramenta_e_recusa_viram_erro(self):
        for stop, codigo in (('max_tokens', 'max_tokens'), ('refusal', 'recusa')):
            with self.subTest(stop=stop):
                final = mensagem_anthropic([NS(type='tool_use', id='x', name='consultar_acervo', input={})], stop=stop)
                with self.assertRaises(ErroIA) as ctx:
                    gerar(ProvedorAnthropic('k', cliente=ClienteAnthropic(StreamAnthropic([], final))))
                self.assertEqual(ctx.exception.codigo, codigo)

    def test_texto_truncado_ou_parada_anormal_vira_erro(self):
        for stop, codigo in (('max_tokens', 'max_tokens'), ('model_context_window_exceeded', 'contexto'),
                             ('pause_turn', 'incompleta')):
            with self.subTest(stop=stop):
                final = mensagem_anthropic([NS(type='text', text='Corta')], stop=stop)
                with self.assertRaises(ErroIA) as ctx:
                    gerar(ProvedorAnthropic('k', cliente=ClienteAnthropic(StreamAnthropic([], final))))
                self.assertEqual(ctx.exception.codigo, codigo)

    def test_texto_so_com_espacos_nao_vira_bloco_vazio(self):
        historico = [{'papel': 'usuario', 'texto': 'P'},
                     {'papel': 'assistente', 'texto': '\n ', 'chamadas': [{'id': 'c', 'nome': 'consultar_acervo', 'argumentos': {}}]},
                     {'papel': 'ferramenta', 'id': 'c', 'texto': '  ', 'erro': False, 'imagens': []}]
        cliente = ClienteAnthropic(StreamAnthropic([], mensagem_anthropic([NS(type='text', text='Ok')])))
        gerar(ProvedorAnthropic('k', cliente=cliente), historico)
        assistente, resultado = cliente.kwargs['messages'][1], cliente.kwargs['messages'][2]
        self.assertEqual([b['type'] for b in assistente['content']], ['tool_use'])
        self.assertEqual(resultado['content'][0]['content'][0]['text'], '(sem conteúdo)')

    def test_erros_de_servidor_e_prazo_sao_classificados(self):
        GatewayTimeoutError = type('GatewayTimeoutError', (Exception,), {})
        InternalServerError = type('InternalServerError', (Exception,), {})
        self.assertEqual(mapear_erro(GatewayTimeoutError('504')).codigo, 'conexao')
        self.assertEqual(mapear_erro(InternalServerError('500')).codigo, 'servidor')

    def test_erros_do_sdk_sao_classificados_sem_vazar_chave(self):
        final = mensagem_anthropic([])
        for erro, codigo in ((RateLimitError('429 sk-ant-segredo'), 'limite'),
                             (AuthenticationError('401'), 'autenticacao'),
                             (APITimeoutError('lento'), 'conexao')):
            with self.subTest(erro=type(erro).__name__):
                cliente = ClienteAnthropic(StreamAnthropic([erro], final))
                with self.assertRaises(ErroIA) as ctx:
                    gerar(ProvedorAnthropic('k', cliente=cliente))
                self.assertEqual(ctx.exception.codigo, codigo)
                self.assertNotIn('sk-ant-segredo', str(ctx.exception))


# -- OpenAI fakes --------------------------------------------------------------
class EventosOpenAI(list):
    closed = False

    def close(self):
        self.closed = True


class ClienteOpenAI:
    def __init__(self, eventos):
        self.eventos, self.kwargs = eventos, None
        self.responses = NS(create=self._create)

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return self.eventos


def resposta_openai(output, status='completed', motivo=None):
    return NS(output=output, model='gpt-sintetico', status=status,
              incomplete_details=NS(reason=motivo) if motivo else None,
              usage=NS(input_tokens=20, output_tokens=9, input_tokens_details=NS(cached_tokens=4),
                       output_tokens_details=NS(reasoning_tokens=3)))


class Raciocinio(NS):
    def model_dump(self, **kwargs):
        return {'type': 'reasoning', 'id': self.id, 'encrypted_content': self.encrypted_content, 'summary': []}


class OpenAITest(unittest.TestCase):
    def test_converte_historico_ferramentas_e_streaming(self):
        final = resposta_openai([NS(type='message', content=[NS(type='output_text', text='Pronto.')])])
        eventos = EventosOpenAI([NS(type='response.output_text.delta', delta='Pron'),
                                 NS(type='response.output_text.delta', delta='to.'),
                                 NS(type='response.completed', response=final)])
        cliente = ClienteOpenAI(eventos)
        resposta, deltas = gerar(ProvedorOpenAI('k', cliente=cliente))
        kw = cliente.kwargs
        self.assertEqual((kw['model'], kw['instructions'], kw['max_output_tokens'], kw['store'], kw['stream']),
                         ('m', 'Regras.', 100, False, True))
        self.assertIn('reasoning.encrypted_content', kw['include'])
        self.assertEqual(kw['tools'], [{'type': 'function', 'name': 'consultar_acervo', 'description': 'Sintética.',
                                        'parameters': FERRAMENTAS[0]['parameters'], 'strict': False}])
        entrada = kw['input']
        self.assertEqual(entrada[0], {'role': 'user', 'content': [{'type': 'input_text', 'text': 'Pergunta.'}]})
        self.assertEqual(entrada[1], {'role': 'assistant', 'content': 'Vou buscar.'})
        self.assertEqual(entrada[2], {'type': 'function_call', 'call_id': 'call-1', 'name': 'consultar_acervo',
                                      'arguments': json.dumps({'acao': 'buscar'}, ensure_ascii=False)})
        self.assertEqual(entrada[3]['type'], 'function_call_output')
        self.assertEqual(entrada[3]['output'], [{'type': 'input_text', 'text': '{"ok": 1}'},
                         {'type': 'input_image', 'image_url': 'data:image/png;base64,QUJD'}])
        self.assertEqual(entrada[4]['content'][0]['text'], 'Complemento.')
        self.assertEqual(deltas, ['Pron', 'to.'])
        self.assertEqual((resposta.texto, resposta.modelo), ('Pronto.', 'gpt-sintetico'))
        # CUS-01: the priced kinds too (here input_tokens includes the 4 cached tokens; no write).
        self.assertEqual(resposta.uso, {'entrada': 20, 'saida': 9, 'cache_leitura': 4, 'raciocinio': 3,
                                        'entrada_sem_cache': 16, 'cache_escrita': 0, 'cache_escrita_30m': 0,
                                        'cache_escrita_12h': 0})

    def test_function_call_vira_chamada_e_raciocinio_e_preservado_para_reenvio(self):
        final = resposta_openai([Raciocinio(type='reasoning', id='rs_1', encrypted_content='cifrado'),
                                 NS(type='function_call', call_id='fc-1', name='consultar_acervo',
                                    arguments='{"acao": "cobertura"}')])
        cliente = ClienteOpenAI(EventosOpenAI([NS(type='response.completed', response=final)]))
        provedor = ProvedorOpenAI('k', cliente=cliente)
        resposta, _ = gerar(provedor)
        self.assertEqual(resposta.chamadas, ({'id': 'fc-1', 'nome': 'consultar_acervo', 'argumentos': {'acao': 'cobertura'}},))
        self.assertEqual(resposta.opaco, ({'provedor': 'openai', 'item': {
            'type': 'reasoning', 'id': 'rs_1', 'encrypted_content': 'cifrado', 'summary': []}},))
        historico = [{'papel': 'usuario', 'texto': 'P'},
                     {'papel': 'assistente', 'texto': '', 'chamadas': list(resposta.chamadas), 'opaco': list(resposta.opaco)},
                     {'papel': 'ferramenta', 'id': 'fc-1', 'texto': 'r', 'erro': True, 'imagens': []}]
        cliente.eventos = EventosOpenAI([NS(type='response.completed', response=resposta_openai([]))])
        gerar(provedor, historico)
        entrada = cliente.kwargs['input']
        self.assertEqual([i.get('type') for i in entrada[1:]], ['reasoning', 'function_call', 'function_call_output'])
        self.assertTrue(entrada[3]['output'].startswith('ERRO'))

    def test_raciocinio_sem_texto_nem_chamada_nao_e_reenviado(self):
        historico = [{'papel': 'usuario', 'texto': 'P'},
                     {'papel': 'assistente', 'texto': '', 'opaco': [{'provedor': 'openai', 'item': {'type': 'reasoning', 'id': 'r'}}]},
                     {'papel': 'usuario', 'texto': 'Q'}]
        cliente = ClienteOpenAI(EventosOpenAI([NS(type='response.completed', response=resposta_openai([]))]))
        gerar(ProvedorOpenAI('k', cliente=cliente), historico)
        self.assertNotIn('reasoning', [i.get('type') for i in cliente.kwargs['input']])

    def test_resposta_incompleta_sem_chamada_vira_erro(self):
        for motivo, codigo in (('max_output_tokens', 'max_tokens'), ('content_filter', 'filtro')):
            with self.subTest(motivo=motivo):
                final = resposta_openai([NS(type='message', content=[NS(type='output_text', text='Cort')])],
                                        status='incomplete', motivo=motivo)
                with self.assertRaises(ErroIA) as ctx:
                    gerar(ProvedorOpenAI('k', cliente=ClienteOpenAI(EventosOpenAI([NS(type='response.incomplete', response=final)]))))
                self.assertEqual(ctx.exception.codigo, codigo)

    def test_itens_opacos_de_outro_provedor_sao_ignorados(self):
        historico = [{'papel': 'usuario', 'texto': 'P'},
                     {'papel': 'assistente', 'texto': 'R', 'opaco': [{'provedor': 'anthropic', 'item': {'type': 'thinking'}}]}]
        cliente = ClienteOpenAI(EventosOpenAI([NS(type='response.completed', response=resposta_openai([]))]))
        gerar(ProvedorOpenAI('k', cliente=cliente), historico)
        self.assertEqual(cliente.kwargs['input'][1], {'role': 'assistant', 'content': 'R'})

    def test_argumentos_json_invalidos_seguem_para_validacao_do_backend(self):
        final = resposta_openai([NS(type='function_call', call_id='fc', name='consultar_acervo', arguments='{quebrado')])
        resposta, _ = gerar(ProvedorOpenAI('k', cliente=ClienteOpenAI(EventosOpenAI([NS(type='response.completed', response=final)]))))
        self.assertEqual(resposta.chamadas[0]['argumentos'], {'argumentos_invalidos': '{quebrado'})

    def test_argumentos_invalidos_enormes_sao_truncados(self):
        bruto = '{' + 'x' * 50000
        final = resposta_openai([NS(type='function_call', call_id='fc', name='consultar_acervo', arguments=bruto)])
        resposta, _ = gerar(ProvedorOpenAI('k', cliente=ClienteOpenAI(EventosOpenAI([NS(type='response.completed', response=final)]))))
        self.assertLessEqual(len(resposta.chamadas[0]['argumentos']['argumentos_invalidos']), 8000)

    def test_cancelamento_fecha_stream(self):
        eventos = EventosOpenAI([NS(type='response.output_text.delta', delta='x')])
        resposta, deltas = gerar(ProvedorOpenAI('k', cliente=ClienteOpenAI(eventos)), cancelado=lambda: True)
        self.assertTrue(eventos.closed)
        self.assertEqual((deltas, resposta.chamadas), ([], ()))

    def test_falhas_e_truncamento_viram_erro(self):
        casos = [
            (EventosOpenAI([NS(type='response.failed', response=NS(error=NS(message='quota sk-proj-x', code='rate_limit_exceeded')))]), 'limite'),
            (EventosOpenAI([NS(type='error', message='Falha', code=None)]), None),
            (EventosOpenAI([NS(type='response.incomplete', response=resposta_openai(
                [NS(type='function_call', call_id='f', name='consultar_acervo', arguments='{')],
                status='incomplete', motivo='max_output_tokens'))]), 'max_tokens'),
            (EventosOpenAI([]), 'incompleta'),
        ]
        for eventos, codigo in casos:
            with self.subTest(codigo=codigo):
                with self.assertRaises(ErroIA) as ctx:
                    gerar(ProvedorOpenAI('k', cliente=ClienteOpenAI(eventos)))
                self.assertEqual(ctx.exception.codigo, codigo)
                self.assertNotIn('sk-proj-x', str(ctx.exception))


class MapearErroTest(unittest.TestCase):
    def test_classifica_por_hierarquia_de_nomes_do_sdk(self):
        self.assertEqual(mapear_erro(APITimeoutError('t')).codigo, 'conexao')
        self.assertEqual(mapear_erro(RateLimitError('r')).codigo, 'limite')
        self.assertIsNone(mapear_erro(ValueError('v')).codigo)
        self.assertIs(type(mapear_erro(ErroIA('x', codigo='y'))), ErroIA)


if __name__ == '__main__':
    unittest.main()
