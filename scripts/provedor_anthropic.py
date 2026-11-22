"""Anthropic Messages API provider for the neutral conversation history."""
from __future__ import annotations

from inferencia_api import ErroIA, Resposta, mapear_erro

NOME = 'anthropic'
TIMEOUT = 600
# A truncated or paused stage must not reach the pipeline as if it were complete.
PARADAS_COM_ERRO = {
    'refusal': ('O modelo recusou a solicitação nesta etapa.', 'recusa'),
    'max_tokens': ('Resposta truncada pelo limite max_tokens_saida. Aumente max_tokens_saida em '
                   'configuracao.json.', 'max_tokens'),
    'model_context_window_exceeded': ('A conversa excedeu a janela de contexto do modelo. Abra uma nova '
                                      'conversa.', 'contexto'),
    'pause_turn': ('A API pausou a resposta antes do fim; a etapa não foi concluída.', 'incompleta'),
}


def _bloco_texto(texto):
    return {'type': 'text', 'text': texto}


def _preenchido(texto):
    """The API rejects empty or whitespace-only text blocks."""
    return bool(texto and texto.strip())


def _resultado(mensagem):
    texto = mensagem.get('texto')
    conteudo = [_bloco_texto(texto if _preenchido(texto) else '(sem conteúdo)')]
    conteudo += [{'type': 'image', 'source': {'type': 'base64', 'media_type': imagem['mime'], 'data': imagem['dados']}}
                 for imagem in mensagem.get('imagens') or []]
    return {'type': 'tool_result', 'tool_use_id': mensagem['id'], 'is_error': bool(mensagem.get('erro')),
            'content': conteudo}


def converter(historico):
    """Neutral history -> Messages API turns, merging consecutive roles and dropping empty turns."""
    mensagens = []
    for mensagem in historico:
        papel = mensagem.get('papel')
        if papel == 'usuario':
            texto = mensagem.get('texto')
            role, conteudo = 'user', [_bloco_texto(texto if _preenchido(texto) else '(vazio)')]
        elif papel == 'ferramenta':
            role, conteudo = 'user', [_resultado(mensagem)]
        elif papel == 'assistente':
            role = 'assistant'
            conteudo = [item['item'] for item in mensagem.get('opaco') or [] if item.get('provedor') == NOME]
            if _preenchido(mensagem.get('texto')):
                conteudo.append(_bloco_texto(mensagem['texto']))
            conteudo += [{'type': 'tool_use', 'id': c['id'], 'name': c['nome'], 'input': c['argumentos']}
                         for c in mensagem.get('chamadas') or []]
        else:
            continue
        if not conteudo:
            continue
        if mensagens and mensagens[-1]['role'] == role:
            mensagens[-1]['content'].extend(conteudo)
        else:
            mensagens.append({'role': role, 'content': conteudo})
    return mensagens


class ProvedorAnthropic:
    def __init__(self, chave: str, cliente=None):
        if cliente is None:
            import anthropic
            cliente = anthropic.Anthropic(api_key=chave, max_retries=2, timeout=TIMEOUT)
        self.cliente = cliente

    def gerar(self, *, modelo, instrucoes, historico, ferramentas, max_tokens, ao_texto, cancelado):
        pedido = {'model': modelo, 'max_tokens': max_tokens, 'messages': converter(historico),
                  'cache_control': {'type': 'ephemeral'},
                  'tools': [{'name': f['name'], 'description': f['description'], 'input_schema': f['parameters']}
                            for f in ferramentas]}
        if instrucoes:
            pedido['system'] = instrucoes
        interrompido = False
        try:
            with self.cliente.messages.stream(**pedido) as stream:
                for evento in stream:
                    if cancelado():
                        interrompido = True
                        break
                    if getattr(evento, 'type', None) == 'text':
                        ao_texto(evento.text)
                final = stream.current_message_snapshot if interrompido else stream.get_final_message()
        except Exception as exc:
            raise mapear_erro(exc) from exc
        return self._resposta(final, interrompido)

    @staticmethod
    def _resposta(final, interrompido):
        texto = ''.join(b.text for b in final.content if getattr(b, 'type', None) == 'text')
        chamadas = () if interrompido else tuple(
            {'id': b.id, 'nome': b.name, 'argumentos': dict(b.input or {})}
            for b in final.content if getattr(b, 'type', None) == 'tool_use')
        if not interrompido and final.stop_reason in PARADAS_COM_ERRO:
            mensagem, codigo = PARADAS_COM_ERRO[final.stop_reason]
            raise ErroIA(mensagem, codigo=codigo)
        return Resposta(texto, chamadas, uso_da_resposta(final.usage), final.model)


def uso_da_resposta(uso) -> dict:
    """Usage in the priced kinds (custo.TIPOS). Here ``input_tokens`` excludes the cache, which
    comes apart: reads, and writes split by validity (5 minutes, the TTL these requests use, or 1 hour)."""
    entrada = getattr(uso, 'input_tokens', None) or 0
    escrita = getattr(uso, 'cache_creation_input_tokens', None) or 0
    criacao = getattr(uso, 'cache_creation', None)
    escrita_1h = (getattr(criacao, 'ephemeral_1h_input_tokens', None) or 0) if criacao is not None else 0
    return {'entrada': entrada, 'saida': getattr(uso, 'output_tokens', None) or 0,
            'cache_leitura': getattr(uso, 'cache_read_input_tokens', None) or 0, 'cache_escrita': escrita,
            'entrada_sem_cache': entrada, 'cache_escrita_5m': max(0, escrita - escrita_1h),
            'cache_escrita_1h': min(escrita_1h, escrita) if escrita else escrita_1h}
