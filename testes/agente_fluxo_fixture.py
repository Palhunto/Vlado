"""Synthetic agent deliveries; exercises real stage/publication code, no model."""
import json
import time


def esperar(predicate, timeout=30, mensagem='Estado esperado não foi atingido pela fixture.'):
    """Wait for a condition with a deadline; the condition is checked once more at the deadline."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(mensagem)
        time.sleep(.01)


def aguardar_fim(manager, identifier, timeout=30):
    """Wait until the conversation's current execution has ended and return its final state.

    Conversas._finish sets estado and busy=False first and only then writes
    saidas/codex_execucao.json and the round checkpoint, all under manager.lock. Reading
    estado or busy without that lock can therefore see the end before the record exists.
    eventos() takes the lock, so an inactive estado read through it means _finish has
    returned. It uses the interface's long poll, which wakes on each new event."""
    from codex_apuracao import ACTIVE  # scripts/ is on sys.path once a test module is loaded
    deadline = time.monotonic() + timeout
    cursor = 0
    while True:
        resposta = manager.eventos(identifier, after=cursor, wait=1)
        conversa = resposta['conversa']
        if conversa['estado'] not in ACTIVE:
            break
        if time.monotonic() >= deadline:
            raise AssertionError(f'A execução não terminou em {timeout} s '
                                 f'(estado {conversa["estado"]}, etapa {conversa.get("etapa")}).')
        cursor = resposta['cursor']
    run = manager.contexts[identifier].get('run')
    if run is not None and not (run / 'saidas/codex_execucao.json').is_file():
        raise AssertionError('Execução encerrada sem saidas/codex_execucao.json na rodada atual.')
    return conversa


def aguardar_threads(manager, timeout=30):
    """Wait until every execution thread started by the manager has returned."""
    esperar(lambda: not any(worker.is_alive() for worker in manager.workers), timeout,
            'Thread de execução ainda ativa.')


def encerrar_gerenciador(manager, timeout=30):
    """Test cleanup: close the manager and wait for its threads, which could otherwise still
    be writing into the temporary folder that the next cleanup removes."""
    manager.close()
    aguardar_threads(manager, timeout)


def entrega(stage, tool, refs, answer='Resposta técnica sintética.', *, valor='123'):
    if stage == 'inventario':
        tool({'acao': 'cobertura'})
        return 'Inventário sintético: uma fonte textual; sem validação humana.'
    if stage == 'plano':
        return 'Plano sintético: localizar a declaração e conferir seu contexto.'
    if stage == 'busca':
        hit = tool({'acao': 'buscar', 'consulta': 'Alfabeto'})['resultados'][0]
        tool({'acao': 'ler', 'referencia': hit['referencia']})
        refs['hit'] = hit
        return 'Busca sintética executada: Alfabeto; contexto lido e fonte atribuída.'
    hit = refs['hit']
    if stage == 'geracao_inicial':
        return json.dumps({'texto': 'Geração inicial sintética preservada.', 'achados': [{
            'subquestao': 'O que declara a fonte sintética?', 'redacao': f'A fonte sintética declara valor {valor}.',
            'natureza': 'alegacao_atribuida', 'limitacoes': 'Declaração sintética, sem verificação externa.',
            'evidencias': [{'referencia': hit['referencia'], 'trecho': hit['trecho'].splitlines()[0],
                'papel': 'suporte', 'justificativa': 'A declaração é literal.', 'atribuicao': 'Fonte sintética',
                'contexto': 'Fixture técnica de integração.', 'limitacoes': 'Não é documento real.'}]}]}, ensure_ascii=False)
    if stage == 'revisao':
        tool({'acao': 'ler', 'referencia': hit['referencia']})
        return json.dumps({'texto': 'Revisão sintética pela mesma IA; sem aprovação humana.', 'revisoes': [{
            'achado_id': 'A001', 'suporte': 'sustentado', 'motivo': 'Redação atribuída compatível com a fonte reaberta.',
            'limitacoes': 'Teste técnico sintético.', 'acao': 'manter'}]}, ensure_ascii=False)
    return json.dumps({'texto': answer + f'\n[A001@v1] A fonte sintética declara valor {valor}. [fonte:' + hit['referencia'] + ']',
        'destinos': [{'achado_id': 'A001', 'destino': 'incluido', 'motivo': 'Alegação atribuída revisada.'}]}, ensure_ascii=False)


def completar(manager, identifier, answer='Resposta técnica sintética.'):
    refs = {}
    for stage in ('inventario', 'plano', 'busca', 'geracao_inicial', 'revisao', 'sintese'):
        esperar(lambda: manager.contexts[identifier]['meta'].get('etapa') == stage and
                manager.contexts[identifier]['meta'].get('turn_id'))
        tool = lambda args: manager.ferramenta(identifier, args)[0]
        raw = entrega(stage, tool, refs, answer)
        tool({'acao': 'guardar', 'etapa': stage, 'texto': raw})
        turn = manager.contexts[identifier]['meta']['turn_id']
        manager.rpc.emit('item/completed', {'item': {'id': 'msg-' + turn, 'type': 'agentMessage',
                         'phase': 'final_answer', 'text': 'Etapa sintética entregue.'}})
        manager.rpc.emit('turn/completed', {'turn': {'id': turn, 'status': 'completed'}})
    aguardar_fim(manager, identifier)
