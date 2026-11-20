"""Atomic metadata writes must survive concurrent writers on Windows (os.replace races)."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cadastrar_documentos import _atomico


class GravacaoAtomicaTest(unittest.TestCase):
    def test_escritores_simultaneos_nao_falham_e_o_arquivo_fica_valido(self):
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / 'conversa.json'
            falhas = []

            def escrever(n):
                for i in range(40):
                    try:
                        _atomico(alvo, json.dumps({'escritor': n, 'versao': i}).encode('utf-8'))
                    except OSError as exc:
                        falhas.append(exc)

            threads = [threading.Thread(target=escrever, args=(n,)) for n in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(falhas, [])
            self.assertIn('escritor', json.loads(alvo.read_text(encoding='utf-8')))
            self.assertEqual([p.name for p in Path(pasta).iterdir()], ['conversa.json'])


if __name__ == '__main__':
    unittest.main()
