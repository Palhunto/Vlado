"""Executor dos testes Node (`node:test`) que nenhum outro `test_*.py` chamava (QUAL-02).

Descobre os `.cjs` de `testes/` que usam `node:test` e não são citados em outro `test_*.py`,
e roda cada um em `node --test` como um subteste. Os `qa_*.cjs` dirigem o navegador e
continuam manuais; `dom_minimo`, `tokens_tema` e `editor_notas` são auxiliares.
"""
from pathlib import Path
import subprocess
import unittest

from auxiliar_node import localizar_node

TESTES = Path(__file__).resolve().parent
RAIZ = TESTES.parent


def orfaos():
    citados = ''.join(p.read_text(encoding='utf-8') for p in TESTES.glob('test_*.py') if p.name != Path(__file__).name)
    return sorted(p for p in TESTES.glob('*.cjs')
                  if not p.name.startswith('qa_') and 'node:test' in p.read_text(encoding='utf-8')
                  and p.name not in citados)


class NodeOrfaosTest(unittest.TestCase):
    def test_cjs_sem_outro_executor(self):
        node = localizar_node(self)
        arquivos = orfaos()
        self.assertTrue(arquivos, 'Nenhum .cjs órfão encontrado; o descobridor quebrou.')
        for arquivo in arquivos:
            with self.subTest(arquivo=arquivo.name):
                resultado = subprocess.run([node, '--test', str(arquivo)], cwd=RAIZ, capture_output=True,
                                           text=True, encoding='utf-8', timeout=120)
                self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == '__main__':
    unittest.main()
