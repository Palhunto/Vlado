"""Browser acceptance with synthetic corpus and simulated API adapter. No inference."""
import argparse
import os
from pathlib import Path
import subprocess
import threading
import time
from unittest.mock import patch

from test_codex_integracao import CodexIntegrationTest, FakeServer
from interface_pesquisa import Servidor
from agente_fluxo_fixture import entrega


class BrowserFake(FakeServer):
    def call(self, method, params=None):
        result = super().call(method, params)
        if method == 'turn/start':
            text = params['input'][0]['text']
            if 'AGUARDAR' not in text:
                threading.Thread(target=self.drive, args=(text, result['turn']['id']), daemon=True).start()
        return result

    def drive(self, text, turn_id):
        time.sleep(.1)
        if 'LIMITE' in text:
            self.emit('turn/completed', {'turn': {'id': turn_id, 'status': 'failed',
                      'error': {'message': 'Limite de uso sintético atingido. Tente mais tarde.',
                                'codexErrorInfo': 'limite'}}})
            return
        number = time.time_ns()

        def tool(args):
            nonlocal number
            number += 1
            self.emit('item/tool/call', {'tool': 'consultar_acervo', 'arguments': args,
                      'callId': str(number), 'turnId': 'turn-fixture'}, request=number)
            import json
            result = self.answer(number)['result']
            if not result['success']:
                raise ValueError(result)
            return json.loads(result['contentItems'][0]['text'])

        import re
        stage = re.search(r'Etapa obrigatória atual: (\w+)\.', text)[1]
        if stage == 'inventario': self.fixture_refs = {}
        answer = ('Documentado: o arquivo sintético contém o valor 123.'
                  '\nInferência: nenhuma.\nNão localizado: confirmação externa, fora deste corpus.'
                  '\n<script>window.INJETADO_CODEX=true</script>')
        raw = entrega(stage, tool, self.fixture_refs, answer)
        tool({'acao': 'guardar', 'etapa': stage, 'texto': raw})
        item = 'msg-' + str(number)
        self.emit('item/agentMessage/delta', {'itemId': item, 'delta': 'Etapa entregue.'})
        self.emit('item/completed', {'item': {'type': 'agentMessage', 'id': item, 'phase': 'final_answer', 'text': 'Etapa entregue.'}})
        self.emit('turn/completed', {'turn': {'id': turn_id, 'status': 'completed'}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--modulos-node', required=True)
    parser.add_argument('--saida', required=True)
    parser.add_argument('--chrome', default='')
    args = parser.parse_args()
    fx = CodexIntegrationTest()
    fx.setUp()
    fx.manager.factory = BrowserFake
    server = Servidor(('127.0.0.1', 0), fx.root)
    server.conversas = fx.manager
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {**os.environ, 'NODE_PATH': args.modulos_node}
        with patch('codex_apuracao.webbrowser.open', return_value=False):
            return subprocess.run(['node', str(Path(__file__).with_suffix('.cjs')), server.origin,
                                   str(Path(args.saida).resolve()), args.chrome], env=env).returncode
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        fx.doCleanups()


if __name__ == '__main__':
    raise SystemExit(main())
