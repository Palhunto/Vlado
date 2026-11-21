"""Trava de cadastro com dono, espera e recuperação (CONF-01), com dados sintéticos.

Cobre: dono gravado e solto; operações concorrentes que esperam em vez de falhar; prazo que
recusa dizendo desde quando; trava viva de outro processo que nunca é tomada (nem pela
limpeza da partida); processo morto segurando a trava, que se solta sozinha; a pasta antiga
``casos/.cadastro.lock``; encerramento que faz as esperas desistirem. Roda igual no Windows
(msvcrt) e no Linux (flock). Sem rede nem modelo.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import cadastrar_documentos as cadastro  # noqa: E402
from nova_rodada import criar_rodada  # noqa: E402
from selecionar_caso import selecionar  # noqa: E402
import test_registros as fixtures  # noqa: E402
import trava_cadastro  # noqa: E402

AUXILIAR = TESTES / 'apoio_trava_processo.py'
HEX = '0123456789abcdef' * 2


def segurar_em_outro_processo(teste, raiz):
    """Start a process that holds the lock; returns (process, pid). Cleanup kills it."""
    proc = subprocess.Popen([sys.executable, str(AUXILIAR), 'segurar', str(raiz)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    teste.addCleanup(lambda: (proc.poll() is None and proc.kill(), proc.wait(10),
                              proc.stdin.close(), proc.stdout.close(), proc.stderr.close()))
    linha = proc.stdout.readline()
    if not linha:
        teste.fail('processo auxiliar não pegou a trava: ' + proc.stderr.read())
    return proc, json.loads(linha)['pid']


class TravaCadastroTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RegistrosTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        selecionar(self.root, None)
        self.fonte = self.root / 'fonte.txt'
        self.outra = self.root / 'outra.txt'
        self.outra.write_text('Outra fonte sintética exclusiva.', encoding='utf-8')
        cadastro.cadastrar(self.root, 'alpha', [self.fonte], novo=True, titulo='Caso sintético', natureza='sinteticos')
        self.manifesto = self.root / 'casos/alpha/manifesto.json'

    def segurar_em_thread(self, segundos):
        dentro, fim = threading.Event(), threading.Event()

        def alvo():
            with cadastro._trava(self.root, operacao='teste'):
                dentro.set()
                fim.wait(segundos)
        thread = threading.Thread(target=alvo, daemon=True)
        thread.start()
        self.assertTrue(dentro.wait(5))
        self.addCleanup(lambda: (fim.set(), thread.join(5)))
        return fim, thread

    def test_dono_gravado_enquanto_segura_e_livre_ao_soltar(self):
        with cadastro._trava(self.root, operacao='cadastro') as registro:
            dono = trava_cadastro.ler_dono(self.root)
            self.assertEqual(dono['estado'], 'ocupada')
            self.assertEqual((dono['pid'], dono['operacao']), (os.getpid(), 'cadastro'))
            self.assertTrue(dono['host'])
            self.assertRegex(dono['desde_utc'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$')
            self.assertEqual(dono['token'], registro['token'])
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')
        # The mkdir lock of earlier versions is never created again.
        self.assertFalse((self.root / 'casos/.cadastro.lock').exists())

    def test_cadastro_concorrente_espera_e_conclui(self):
        fim, _ = self.segurar_em_thread(5)
        threading.Timer(0.6, fim.set).start()
        inicio = time.monotonic()
        resultado = cadastro.cadastrar(self.root, 'alpha', [self.outra], natureza='sinteticos')
        self.assertGreaterEqual(time.monotonic() - inicio, 0.5)
        self.assertEqual((resultado['novos'], resultado['corpus_id']), (1, 'alpha_v2'))

    def test_congelamento_espera_cadastro_em_curso_e_ve_o_lote_inteiro(self):
        dentro, seguir = threading.Event(), threading.Event()
        original = cadastro._resumo_pdfs

        def pausa(*args):
            dentro.set()
            seguir.wait(5)
            return original(*args)
        erros = []

        def cadastrar():
            try:
                cadastro.cadastrar(self.root, 'alpha', [self.outra], natureza='sinteticos')
            except Exception as exc:  # reported by the main thread
                erros.append(exc)
        selecionar(self.root, 'alpha')
        with mock.patch.object(cadastro, '_resumo_pdfs', pausa):
            thread = threading.Thread(target=cadastrar, daemon=True)
            thread.start()
            self.assertTrue(dentro.wait(5))
            threading.Timer(0.5, seguir.set).start()
            rodada = criar_rodada(self.root, 'R001', 'Pergunta sintética durante cadastro.')
            thread.join(5)
        self.assertEqual(erros, [])
        congelado = json.loads((rodada / 'entradas/casos/alpha/manifesto.json').read_text(encoding='utf-8'))
        self.assertEqual(len(congelado['documentos']), 2)  # waited for the batch, never saw half of it

    def test_prazo_esgotado_recusa_com_o_horario_de_quem_segura(self):
        self.segurar_em_thread(5)
        inicio = time.monotonic()
        with self.assertLogs('vlado.trava_cadastro', 'WARNING'):
            with self.assertRaisesRegex(ValueError, r'em andamento desde \d\d:\d\d \(UTC\); tente novamente') as erro:
                with cadastro._trava(self.root, espera=0.4):
                    pass
        self.assertLess(time.monotonic() - inicio, 3)
        self.assertEqual(erro.exception.dono['operacao'], 'teste')
        self.assertNotIn(str(os.getpid()), str(erro.exception))  # pid and host stay in the server log

    def test_mesma_thread_pedindo_de_novo_recusa_na_hora(self):
        inicio = time.monotonic()
        with cadastro._trava(self.root):
            with self.assertRaisesRegex(ValueError, 'andamento nesta mesma operação'):
                with cadastro._trava(self.root, espera=30):
                    pass
        self.assertLess(time.monotonic() - inicio, 2)

    def test_trava_viva_de_outro_processo_nao_e_roubada(self):
        lote = self.root / f'casos/.lote_{HEX}'
        (lote / 'lote').mkdir(parents=True)
        proc, pid = segurar_em_outro_processo(self, self.root)
        with self.assertLogs('vlado.trava_cadastro', 'WARNING'):
            with self.assertRaisesRegex(ValueError, 'em andamento desde'):
                with cadastro._trava(self.root, espera=0.5):
                    pass
            resumo = trava_cadastro.recuperar(self.root)
        self.assertEqual(resumo['estado'], 'em_uso')
        self.assertEqual(resumo['dono']['pid'], pid)
        self.assertTrue(lote.is_dir(), 'a partida limpou preparo com a trava viva em outro processo')
        self.assertEqual(trava_cadastro.ler_dono(self.root)['pid'], pid)
        self.assertIsNone(proc.poll())
        proc.stdin.write('soltar\n')
        proc.stdin.flush()
        self.assertEqual(proc.wait(10), 0)
        resultado = cadastro.cadastrar(self.root, 'alpha', [self.outra], natureza='sinteticos')
        self.assertEqual(resultado['novos'], 1)
        self.assertTrue(lote.is_dir(), 'preparo só é limpo na partida ou depois de trava abandonada')

    def test_processo_morto_segurando_a_trava_e_recuperado_sem_intervencao(self):
        proc, pid = segurar_em_outro_processo(self, self.root)
        lote = self.root / f'casos/.lote_{HEX}'
        (lote / 'lote/originais').mkdir(parents=True)
        (lote / 'lote/originais/D002_x.txt').write_text('cópia pela metade', encoding='utf-8')
        antes = self.manifesto.read_bytes()
        proc.kill()
        proc.wait(10)
        inicio = time.monotonic()
        with self.assertLogs('vlado.trava_cadastro', 'WARNING') as registro:
            resultado = cadastro.cadastrar(self.root, 'alpha', [self.outra], natureza='sinteticos')
        self.assertLess(time.monotonic() - inicio, 5)
        self.assertIn(f'abandonada recuperada: processo {pid}', '\n'.join(registro.output))
        self.assertFalse(lote.exists())
        self.assertEqual(resultado['corpus_id'], 'alpha_v2')
        self.assertNotEqual(self.manifesto.read_bytes(), antes)
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')

    def test_partida_recupera_abandonada_e_limpa_so_o_preparo_da_trava(self):
        proc, pid = segurar_em_outro_processo(self, self.root)
        proc.kill()
        proc.wait(10)
        lote = self.root / f'casos/.lote_{HEX}'
        rodada = self.root / f'execucoes/.r_{HEX}'
        web = self.root / f'casos/.web_{HEX}'  # web captures stage outside the lock
        outra = self.root / 'casos/.lote_nao_e_uuid'
        for pasta in (lote / 'lote', rodada / 'R001', web, outra):
            pasta.mkdir(parents=True)
        with self.assertLogs('vlado.trava_cadastro', 'WARNING'):
            resumo = trava_cadastro.recuperar(self.root)
        self.assertEqual(resumo['estado'], 'livre')
        self.assertEqual(resumo['abandonada']['pid'], pid)
        self.assertEqual(sorted(resumo['preparo_removido']), [f'casos/.lote_{HEX}', f'execucoes/.r_{HEX}'])
        self.assertFalse(lote.exists() or rodada.exists())
        self.assertTrue(web.is_dir() and outra.is_dir())
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')
        self.assertIsNone(trava_cadastro.recuperar(self.root)['abandonada'])

    def test_trava_antiga_recusa_na_hora_e_a_partida_a_remove(self):
        antiga = self.root / 'casos/.cadastro.lock'
        antiga.mkdir()
        inicio = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'andamento.*trava antiga'):
            cadastro.cadastrar(self.root, 'alpha', [self.outra], natureza='sinteticos')
        self.assertLess(time.monotonic() - inicio, 2)
        with self.assertLogs('vlado.trava_cadastro', 'WARNING'):
            self.assertTrue(trava_cadastro.recuperar(self.root)['antiga_removida'])
        self.assertFalse(antiga.exists())
        self.assertEqual(cadastro.cadastrar(self.root, 'alpha', [self.outra], natureza='sinteticos')['novos'], 1)

    def test_encerrar_faz_esperas_desistirem_e_aguarda_quem_segura(self):
        fim, thread = self.segurar_em_thread(10)
        erros = []

        def esperar():
            try:
                with cadastro._trava(self.root, espera=10):
                    pass
            except ValueError as exc:
                erros.append(exc)
        espera = threading.Thread(target=esperar, daemon=True)
        espera.start()
        time.sleep(0.3)
        inicio = time.monotonic()
        trava_cadastro.encerrar(self.root)
        espera.join(3)
        self.assertLess(time.monotonic() - inicio, 2)
        self.assertIsInstance(erros[0], trava_cadastro.TravaInterrompida)
        self.assertIn('encerrada', str(erros[0]))
        self.assertFalse(trava_cadastro.aguardar_livre(self.root, 0.2))
        threading.Timer(0.3, fim.set).start()
        self.assertTrue(trava_cadastro.aguardar_livre(self.root, 5))
        with self.assertRaises(trava_cadastro.TravaInterrompida):
            with cadastro._trava(self.root):
                pass
        trava_cadastro.recuperar(self.root)  # the next start accepts operations again
        with cadastro._trava(self.root):
            pass

    def test_publicacao_interrompida_por_ctrl_c_desfaz_o_lote(self):
        antes = self.manifesto.read_bytes()
        catalogo = (self.root / 'casos/catalogo.json').read_bytes()
        original = cadastro._atomico
        interrompido = []

        def interromper(alvo, dados):
            if alvo.name == 'catalogo.json' and not interrompido:  # once: the rollback writes it again
                interrompido.append(True)
                raise KeyboardInterrupt
            return original(alvo, dados)
        with mock.patch.object(cadastro, '_atomico', interromper), self.assertRaises(KeyboardInterrupt):
            cadastro.cadastrar(self.root, 'alpha', [self.outra], natureza='sinteticos')
        self.assertEqual(self.manifesto.read_bytes(), antes)
        self.assertEqual((self.root / 'casos/catalogo.json').read_bytes(), catalogo)
        self.assertEqual(len(list((self.root / 'casos/alpha/cadastros').iterdir())), 1)
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')


if __name__ == '__main__':
    unittest.main()
