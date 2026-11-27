"""Desempenho com caso real (Maestro, 27/11): a conferência das entradas congeladas de uma rodada vale por pedido.

Um evidencia-buscar refazia o hash de todas as entradas da rodada a cada evidência (86 s na Sinfra). Agora, dentro
de um pedido (``comum.pedido``, aberto por ``rotas_evidencia.executar``), cada conferência é feita uma vez, e o hash
de um arquivo é reaproveitado enquanto ele mantém a identidade (caminho, tamanho, mtime_ns, ctime_ns, inode). Aqui a
garantia que não pode mudar: o arquivo alterado continua recusado no pedido seguinte. Dados sintéticos
(``fixture_achados``).
"""
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente  # noqa: E402
import comum  # noqa: E402
from registros_achados import carregar  # noqa: E402
import rotas_evidencia  # noqa: E402
import seletor_evidencia  # noqa: E402

PEDIDO = {'caso': 'alpha', 'origem': 'ia', 'texto': '', 'limite': 50}


class ConferenciaPorPedidoTest(unittest.TestCase):
    def setUp(self):
        self.env, _ = Ambiente.copia_completa()
        self.addCleanup(self.env.cleanup)
        self.root = self.env.root
        # The files of a real case are old; a file written in the last seconds never has its hash kept.
        antes = time.time() - 3600
        for path in self.root.rglob('*'):
            if path.is_file():
                os.utime(path, (antes, antes))
        self.run_dir = self.env.run()
        data, _ = carregar(self.root, 'alpha', 'R001', 'r2')
        textual = [e for e in data['evidencias'] if e['fonte_textual']]
        self.assertTrue(textual)
        self.fonte = self.run_dir / textual[0]['fonte_textual']
        self.banco = self.run_dir / 'indice/v1/apuracao.sqlite'
        self.assertTrue(self.fonte.is_file() and self.banco.is_file())

    def buscar(self):
        return rotas_evidencia.executar(self.root, 'evidencia-buscar', dict(PEDIDO))

    def carregar_num_pedido(self):
        with comum.pedido():
            return carregar(self.root, 'alpha', 'R001', 'r2')

    def guardado(self, path):
        return os.fspath(path.resolve()) in comum._HASHES

    def test_mesma_resposta_com_e_sem_o_pedido(self):
        dentro_do_pedido = self.buscar()
        self.assertTrue(dentro_do_pedido['resultados'])
        self.assertEqual(dentro_do_pedido, seletor_evidencia.buscar(self.root, 'alpha', dict(PEDIDO)))

    def test_cada_arquivo_tem_o_hash_feito_uma_vez(self):
        chamadas = []
        original = comum._hash_do_arquivo

        def contar(path):
            chamadas.append(os.fspath(path))
            return original(path)
        with patch('comum._hash_do_arquivo', side_effect=contar):
            self.buscar()
            primeiro = list(chamadas)
            self.buscar()
        self.assertTrue(primeiro)
        self.assertEqual(len(primeiro), len(set(primeiro)))  # once per file in the first request
        self.assertEqual(chamadas, primeiro)  # none in the second: the files kept their identity
        self.assertTrue(self.guardado(self.fonte) and self.guardado(self.banco))

    def test_fonte_alterada_continua_recusada(self):
        self.buscar()
        self.assertTrue(self.guardado(self.fonte))
        with self.fonte.open('ab') as stream:  # another size
            stream.write(b' ')
        with self.assertRaisesRegex(ValueError, 'hash divergente'):
            self.carregar_num_pedido()
        self.assertEqual(self.buscar()['analises'], [])  # the round no longer loads: it offers nothing

    def test_fonte_alterada_com_o_mesmo_tamanho_continua_recusada(self):
        self.buscar()
        conteudo = self.fonte.read_bytes()
        self.fonte.write_bytes(bytes([conteudo[0] ^ 1]) + conteudo[1:])  # same size, new mtime
        with self.assertRaisesRegex(ValueError, 'hash divergente'):
            self.carregar_num_pedido()

    @unittest.skipIf(os.name == 'nt', 'No Windows o ctime é a data de criação: limite aceito, descrito em comum.py')
    def test_mtime_reposto_a_mao_continua_recusado_no_linux(self):
        self.buscar()
        info = self.fonte.stat()
        conteudo = self.fonte.read_bytes()
        self.fonte.write_bytes(bytes([conteudo[0] ^ 1]) + conteudo[1:])
        os.utime(self.fonte, ns=(info.st_atime_ns, info.st_mtime_ns))  # the ctime still changes
        with self.assertRaisesRegex(ValueError, 'hash divergente'):
            self.carregar_num_pedido()

    def test_banco_do_indice_alterado_continua_recusado(self):
        self.buscar()
        self.assertTrue(self.guardado(self.banco))
        with self.banco.open('ab') as stream:
            stream.write(b'\0')
        with self.assertRaisesRegex(ValueError, 'Hash do banco divergente'):
            self.carregar_num_pedido()

    def test_arquivo_recente_nao_tem_o_hash_guardado(self):
        novo = self.root / 'recente.txt'
        novo.write_bytes(b'abc')
        with comum.pedido():
            primeiro = comum.sha256(novo)
            novo.write_bytes(b'abd')  # same size, possibly the same mtime tick
            segundo = comum.sha256(novo)
        self.assertFalse(self.guardado(novo))
        self.assertNotEqual(primeiro, segundo)

    def test_fora_do_pedido_nada_e_lembrado(self):
        self.assertIsNone(comum.memo('dentro'))
        antes = dict(comum._HASHES)
        comum.sha256(self.fonte)
        self.assertEqual(comum._HASHES, antes)

    def test_caminho_fora_continua_recusado_no_pedido(self):
        with comum.pedido():
            comum.dentro(self.root, 'execucoes')
            for ruim in ('../fora', '/abs', ''):
                with self.assertRaises(ValueError):
                    comum.dentro(self.root, ruim)


if __name__ == '__main__':
    unittest.main()
