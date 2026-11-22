"""OpenAI Responses API provider for the neutral conversation history (stateless, store=False)."""
from __future__ import annotations

import json

from inferencia_api import ErroIA, Resposta, mapear_erro, seguro

NOME = 'openai'
TIMEOUT = 600
CODIGOS_LIMITE = ('rate_limit_exceeded', 'insufficient_quota')
LIMITE_ARGUMENTOS = 8000


def _saida_ferramenta(mensagem):
    texto = mensagem.get('texto') or '(sem conteúdo)'
    if mensagem.get('erro'):
        texto = 'ERRO: ' + texto
    imagens = mensagem.get('imagens') or []
    if not imagens:
        return texto
    return [{'type': 'input_text', 'text': texto}] + [
        {'type': 'input_image', 'image_url': f'data:{i["mime"]};base64,{i["dados"]}'} for i in imagens]


def converter(historico):
    itens = []
    for mensagem in historico:
        papel = mensagem.get('papel')
        if papel == 'usuario':
            itens.append({'role': 'user', 'content': [{'type': 'input_text', 'text': mensagem.get('texto') or '(vazio)'}]})
        elif papel == 'assistente':
            if mensagem.get('texto') or mensagem.get('chamadas'):
                # A reasoning item is rejected by the API without the item that followed it.
                itens += [item['item'] for item in mensagem.get('opaco') or [] if item.get('provedor') == NOME]
            if mensagem.get('texto'):
                itens.append({'role': 'assistant', 'content': mensagem['texto']})
            itens += [{'type': 'function_call', 'call_id': c['id'], 'name': c['nome'],
                       'arguments': json.dumps(c['argumentos'], ensure_ascii=False)}
                      for c in mensagem.get('chamadas') or []]
        elif papel == 'ferramenta':
            itens.append({'type': 'function_call_output', 'call_id': mensagem['id'],
                          'output': _saida_ferramenta(mensagem)})
    return itens


def _argumentos(bruto):
    """Invalid JSON goes to the backend validator, truncated so it cannot bloat records."""
    try:
        valor = json.loads(bruto or '{}')
    except ValueError:
        return {'argumentos_invalidos': (bruto or '')[:LIMITE_ARGUMENTOS]}
    return valor if isinstance(valor, dict) else {'argumentos_invalidos': str(bruto)[:LIMITE_ARGUMENTOS]}


def _falha(erro):
    codigo = getattr(erro, 'code', None)
    mensagem = seguro(getattr(erro, 'message', None) or 'Falha informada pela API.')
    return ErroIA('Falha na API: ' + mensagem, codigo='limite' if codigo in CODIGOS_LIMITE else None)


class ProvedorOpenAI:
    def __init__(self, chave: str, cliente=None):
        if cliente is None:
            import openai
            cliente = openai.OpenAI(api_key=chave, max_retries=2, timeout=TIMEOUT)
        self.cliente = cliente

    def gerar(self, *, modelo, instrucoes, historico, ferramentas, max_tokens, ao_texto, cancelado):
        pedido = {'model': modelo, 'input': converter(historico), 'max_output_tokens': max_tokens,
                  'store': False, 'stream': True, 'include': ['reasoning.encrypted_content'],
                  'tools': [{'type': 'function', 'name': f['name'], 'description': f['description'],
                             'parameters': f['parameters'], 'strict': False} for f in ferramentas]}
        if instrucoes:
            pedido['instructions'] = instrucoes
        final = None
        try:
            eventos = self.cliente.responses.create(**pedido)
            for evento in eventos:
                if cancelado():
                    eventos.close()
                    return Resposta('', (), {}, modelo)
                tipo = getattr(evento, 'type', None)
                if tipo == 'response.output_text.delta':
                    ao_texto(evento.delta)
                elif tipo in ('response.completed', 'response.incomplete'):
                    final = evento.response
                elif tipo == 'response.failed':
                    raise _falha(evento.response.error)
                elif tipo == 'error':
                    raise _falha(evento)
        except Exception as exc:
            raise mapear_erro(exc) from exc
        if final is None:
            raise ErroIA('A API encerrou o streaming sem resposta final.', codigo='incompleta')
        return self._resposta(final)

    @staticmethod
    def _resposta(final):
        textos, chamadas, opaco = [], [], []
        for item in final.output or []:
            tipo = getattr(item, 'type', None)
            if tipo == 'message':
                textos += [c.text for c in item.content if getattr(c, 'type', None) == 'output_text']
            elif tipo == 'function_call':
                chamadas.append({'id': item.call_id, 'nome': item.name, 'argumentos': _argumentos(item.arguments)})
            elif tipo == 'reasoning':
                opaco.append({'provedor': NOME, 'item': item.model_dump(exclude_none=True)})
        motivo = getattr(getattr(final, 'incomplete_details', None), 'reason', None)
        if motivo == 'max_output_tokens':
            raise ErroIA('Resposta truncada pelo limite max_tokens_saida. Aumente max_tokens_saida em '
                         'configuracao.json.', codigo='max_tokens')
        if motivo == 'content_filter':
            raise ErroIA('A resposta foi interrompida pelo filtro de conteúdo do provedor.', codigo='filtro')
        if motivo:
            raise ErroIA(f'A API devolveu uma resposta incompleta ({seguro(motivo)}).', codigo='incompleta')
        return Resposta(''.join(textos), tuple(chamadas), uso_da_resposta(final.usage), final.model, tuple(opaco))


def uso_da_resposta(uso) -> dict:
    """Usage in the priced kinds (custo). Here ``input_tokens_details`` breaks ``input_tokens`` down:
    the cache reads and writes are inside it, and the uncached part is the rest. Writes come by
    retention (30 minutes, 12 hours); without the breakdown they count as 30 minutes, recorded in
    ``cache_escrita_30m_suposto``. Reasoning is part of the output."""
    entrada = getattr(uso, 'input_tokens', None) or 0
    detalhes = getattr(uso, 'input_tokens_details', None)
    lidos = getattr(detalhes, 'cached_tokens', 0) or 0
    escritos = getattr(detalhes, 'cache_write_tokens', 0) or 0
    validades = getattr(detalhes, 'cache_write_tokens_details', None)
    resultado = {'entrada': entrada, 'saida': getattr(uso, 'output_tokens', None) or 0, 'cache_leitura': lidos,
                 'raciocinio': getattr(getattr(uso, 'output_tokens_details', None), 'reasoning_tokens', 0) or 0,
                 'entrada_sem_cache': max(0, entrada - lidos - escritos), 'cache_escrita': escritos}
    if validades is not None:
        doze = getattr(validades, 'ttl_12h_tokens', 0) or 0
        resultado.update(cache_escrita_12h=doze, cache_escrita_30m=max(0, escritos - doze))
    else:
        resultado.update(cache_escrita_30m=escritos, cache_escrita_12h=0, cache_escrita_30m_suposto=escritos)
    return resultado
