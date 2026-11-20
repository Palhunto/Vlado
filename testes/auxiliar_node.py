"""Localiza o Node.js para os testes que dependem dele (A14).

Sem Node o teste é pulado, não falha. Na integração contínua, `VLADO_EXIGIR_NODE=1`
transforma a ausência em falha, para que a suíte nunca passe sem ter rodado o Node.
"""
import os
import shutil


def localizar_node(teste):
    node = shutil.which('node')
    if node is None:
        if os.environ.get('VLADO_EXIGIR_NODE') == '1':
            teste.fail('Node.js é necessário e VLADO_EXIGIR_NODE=1 está definido.')
        teste.skipTest('Node.js não encontrado no PATH.')
    return node
