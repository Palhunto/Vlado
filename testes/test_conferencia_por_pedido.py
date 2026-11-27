"""Desempenho com caso real (Maestro, 27/11): a conferência das entradas congeladas de uma rodada vale por pedido.

Um evidencia-buscar refazia o hash de todas as entradas da rodada a cada evidência (86 s na Sinfra). Agora, dentro
de um pedido (``comum.pedido``, aberto por ``rotas_evidencia.executar``), cada conferência é feita uma vez, e o hash
de um arquivo é reaproveitado enquanto ele mantém a identidade (caminho, tamanho, mtime_ns, ctime_ns, inode). Aqui a
garantia que não pode mudar: o arquivo alterado continua recusado no pedido seguinte, também quando a escrita é
por mmap (B1 da Coruja sobre 7f05beb: no NTFS ela não muda tamanho, mtime, ctime nem inode). Por isso, no Windows o
hash só é reaproveitado dentro do pedido; no Linux, entre pedidos. Dados sintéticos (``fixture_achados``).
"""
import mmap
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
        """The hash kept between requests (only where comum.GUARDA_ENTRE_PEDIDOS)."""
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
        segundo = chamadas[len(primeiro):]
        if comum.GUARDA_ENTRE_PEDIDOS:
            self.assertEqual(segundo, [])  # Linux: none in the second, the files kept their identity
            self.assertTrue(self.guardado(self.fonte) and self.guardado(self.banco))
        else:
            self.assertEqual(sorted(segundo), sorted(primeiro))  # Windows: each file again, once per request
            self.assertEqual(comum._HASHES, {})

    def test_fonte_alterada_continua_recusada(self):
        self.buscar()
        self.assertEqual(self.guardado(self.fonte), comum.GUARDA_ENTRE_PEDIDOS)
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

    def test_mtime_reposto_a_mao_continua_recusado(self):
        # Linux: the ctime changes. Windows: the hash is not kept between requests.
        self.buscar()
        info = self.fonte.stat()
        conteudo = self.fonte.read_bytes()
        self.fonte.write_bytes(bytes([conteudo[0] ^ 1]) + conteudo[1:])
        os.utime(self.fonte, ns=(info.st_atime_ns, info.st_mtime_ns))  # the ctime still changes
        with self.assertRaisesRegex(ValueError, 'hash divergente'):
            self.carregar_num_pedido()

    def test_banco_do_indice_alterado_continua_recusado(self):
        self.buscar()
        self.assertEqual(self.guardado(self.banco), comum.GUARDA_ENTRE_PEDIDOS)
        with self.banco.open('ab') as stream:
            stream.write(b'\0')
        with self.assertRaisesRegex(ValueError, 'Hash do banco divergente'):
            self.carregar_num_pedido()

    def test_escrita_por_mmap_entre_dois_pedidos_continua_recusada(self):
        """B1 da Coruja: no NTFS a escrita por mmap não muda tamanho, mtime, ctime nem inode."""
        self.buscar()
        antes = self.fonte.stat()
        with self.fonte.open('r+b') as stream, mmap.mmap(stream.fileno(), 0) as mapa:
            mapa[0] = mapa[0] ^ 1
            mapa.flush()
        if os.name == 'nt':  # the premise of B1, where it holds
            depois = self.fonte.stat()
            self.assertEqual((depois.st_size, depois.st_mtime_ns), (antes.st_size, antes.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'hash divergente'):
            self.carregar_num_pedido()
        self.assertEqual(self.buscar()['analises'], [])

    def test_dentro_do_pedido_cada_arquivo_e_lido_uma_vez_tambem_no_windows(self):
        chamadas = []
        original = comum._hash_do_arquivo
        with patch('comum._hash_do_arquivo', side_effect=lambda p: chamadas.append(os.fspath(p)) or original(p)):
            with comum.pedido():
                comum.sha256(self.fonte)
                comum.sha256(self.fonte)
        self.assertEqual(len(chamadas), 1)

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
