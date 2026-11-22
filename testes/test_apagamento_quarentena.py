"""Apagamento definitivo com quarentena: a Mesa segue respondendo e uma queda não deixa lixo à vista.

- Sob as travas (cadastro e conversas) só a conferência e a renomeação das raízes do item para
  ``<volume>/.apagando/<item>/<n>``; os arquivos saem depois, fora delas, em segundo plano na Mesa.
  Durante um apagamento grande e lento, a Mesa responde outras operações que pegam as mesmas travas.
- Queda na renomeação: na partida, as raízes voltam e o item fica inteiro na lixeira.
- Queda na remoção (simulada e com o processo morto de verdade): na partida, o apagamento é
  concluído, sem repetir o registro; nada do item fica em lugar nenhum.
- Falha persistente ao remover (arquivo em uso): o item já não aparece; a próxima partida conclui.
Casos sintéticos; sem modelo, rede ou navegador.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
from agente_fluxo_fixture import esperar  # noqa: E402
from comum import escrever_json, ler_json  # noqa: E402
from fixture_achados import Ambiente  # noqa: E402
import apagamento  # noqa: E402
import lixeira  # noqa: E402

AUXILIAR = TESTES / 'apoio_apagamento_queda.py'
CHAT = 'c' * 32


class Queda(BaseException):
    """The process dies here: nothing after it runs (no except, no cleanup of the module)."""


def na_quarentena(caminho):
    partes = Path(caminho).parts
    return apagamento.QUARENTENA in partes and 'lixeira' not in partes


class Base(unittest.TestCase):
    def setUp(self):
        self.fx = Ambiente()
        self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root
        meta = {'id': CHAT, 'caso': 'alpha', 'titulo': 'Pergunta sintética', 'estado': 'concluido',
                'rodadas': ['R001'], 'criada_em_utc': '2026-01-01T00:00:00Z'}
        escrever_json(self.root / f'conversas/{CHAT}/conversa.json', meta)
        (self.root / f'conversas/{CHAT}/eventos.jsonl').write_text('{}\n', encoding='utf-8')
        extras = self.root / 'casos/alpha/derivados_extra'
        extras.mkdir(parents=True)
        for numero in range(40):
            (extras / f'pagina_{numero:03}.md').write_text(f'Página sintética {numero}.\n', encoding='utf-8')
        self.item = lixeira.adicionar(self.root, 'caso', 'alpha', 'Título alpha')
        self.antes = self.retrato()

    def retrato(self):
        """{rel path: sha256} of everything the item has (cases, runs, conversations)."""
        tudo = {}
        for base in ('casos/alpha', 'execucoes/alpha', f'conversas/{CHAT}'):
            for caminho in (self.root / base).rglob('*') if (self.root / base).exists() else []:
                if caminho.is_file():
                    tudo[caminho.relative_to(self.root).as_posix()] = hashlib.sha256(caminho.read_bytes()).hexdigest()
        return tudo

    def token(self):
        return lixeira.alcance(self.root, self.item['id'])['confirmacao']

    def quarentena(self):
        return [p for volume in apagamento.VOLUMES for p in (self.root / volume / apagamento.QUARENTENA).rglob('*')
                if (self.root / volume / apagamento.QUARENTENA).exists()]

    def manifestos(self):
        pasta = self.root / apagamento.MANIFESTOS
        return [ler_json(p) for p in pasta.glob('*.json')] if pasta.is_dir() else []

    def registros(self):
        caminho = self.root / apagamento.REGISTRO_APAGAMENTOS
        return [json.loads(l) for l in caminho.read_text(encoding='utf-8').splitlines()] if caminho.exists() else []

    def no_catalogo(self):
        return 'alpha' in [c['id'] for c in ler_json(self.root / 'casos/catalogo.json')['casos']]

    def assert_inteiro_na_lixeira(self):
        self.assertEqual(self.retrato(), self.antes)
        self.assertEqual([i['id'] for i in lixeira.ativos(self.root)], [self.item['id']])
        self.assertTrue(self.no_catalogo())
        self.assertEqual((self.quarentena(), self.manifestos(), self.registros()), ([], [], []))

    def assert_apagado_sem_sobra(self):
        self.assertEqual(self.retrato(), {})
        self.assertEqual(lixeira.ativos(self.root), [])
        self.assertFalse(self.no_catalogo())
        self.assertEqual((self.quarentena(), self.manifestos()), ([], []))
        self.assertEqual([r['item_id'] for r in self.registros()], [self.item['id']])  # recorded once


class QuedaTest(Base):
    def test_queda_na_renomeacao_volta_o_item_inteiro_para_a_lixeira(self):
        real, vezes = os.rename, [0]

        def cai_na_segunda(origem, destino):
            vezes[0] += 1
            if vezes[0] == 2:
                raise Queda()
            return real(origem, destino)
        with mock.patch('apagamento.os.rename', side_effect=cai_na_segunda), self.assertRaises(Queda):
            apagamento.apagar(self.root, self.item['id'], self.token(), quem='admin')
        self.assertEqual([m['fase'] for m in self.manifestos()], ['renomeando'])
        self.assertNotIn('Título alpha', json.dumps(self.manifestos(), ensure_ascii=False))  # identities only
        self.assertFalse((self.root / 'casos/alpha').exists())  # the first root was in the quarantine
        self.assertEqual(apagamento.retomar(self.root)['desfeitos'], 1)
        self.assert_inteiro_na_lixeira()

    def test_queda_na_remocao_conclui_na_partida_sem_repetir_o_registro(self):
        real, removidos = os.unlink, [0]

        def cai_no_quarto(caminho, *args, **kwargs):
            if na_quarentena(caminho):
                removidos[0] += 1
                if removidos[0] == 4:
                    raise Queda()
            return real(caminho, *args, **kwargs)
        with mock.patch('apagamento.os.unlink', side_effect=cai_no_quarto), self.assertRaises(Queda):
            apagamento.apagar(self.root, self.item['id'], self.token(), quem='admin')
        # Past the point of no return: nothing of the item is visible, its files wait in the quarantine.
        self.assertEqual(self.retrato(), {})
        self.assertEqual((lixeira.ativos(self.root), self.no_catalogo()), ([], False))
        self.assertTrue(self.quarentena())
        self.assertEqual([m['fase'] for m in self.manifestos()], ['removendo'])
        self.assertEqual(apagamento.retomar(self.root)['concluidos'], 1)
        self.assert_apagado_sem_sobra()

    def test_queda_real_do_processo_no_meio_da_remocao(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        marca = Path(pasta.name) / 'marca'
        processo = subprocess.Popen([sys.executable, str(AUXILIAR), str(self.root), self.item['id'], self.token(),
                                     str(marca)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: processo.poll() is None and (processo.kill(), processo.communicate(timeout=15)))
        esperar(lambda: marca.exists() or processo.poll() is not None, 60, 'a remoção não começou')
        self.assertIsNone(processo.poll(), processo.communicate()[1] if processo.poll() is not None else '')
        processo.kill()  # TerminateProcess / SIGKILL in the middle of the removal
        processo.communicate(timeout=15)
        self.assertEqual(self.retrato(), {})  # already out of sight
        self.assertEqual(lixeira.ativos(self.root), [])
        self.assertTrue(self.quarentena())
        apagamento.retomar(self.root)
        self.assert_apagado_sem_sobra()

    def test_falha_persistente_ao_remover_fica_para_a_proxima_partida(self):
        real = os.unlink

        def em_uso(caminho, *args, **kwargs):
            if na_quarentena(caminho):
                raise PermissionError(13, 'arquivo em uso')
            return real(caminho, *args, **kwargs)
        with mock.patch('apagamento.ESPERA_S', 0), mock.patch('apagamento.os.unlink', side_effect=em_uso), \
                self.assertLogs('vlado.apagamento', 'WARNING'):
            resultado = apagamento.apagar(self.root, self.item['id'], self.token(), quem='admin')
        self.assertEqual(resultado['estado'], 'apagado')
        self.assertEqual((self.retrato(), lixeira.ativos(self.root)), ({}, []))  # out of sight already
        self.assertTrue(self.quarentena())
        apagamento.retomar(self.root)  # the next start: the file is free now
        self.assert_apagado_sem_sobra()

    def test_renomeacao_e_desfazer_que_falham_dizem_a_verdade_e_a_partida_devolve(self):
        real, feitas = os.rename, [0]

        def em_uso(origem, destino):
            if apagamento.QUARENTENA in Path(origem).parts:  # putting a root back: in use too
                raise PermissionError(13, 'arquivo em uso')
            feitas[0] += 1
            if feitas[0] > 1:  # the second root is in use
                raise PermissionError(13, 'arquivo em uso')
            return real(origem, destino)
        with mock.patch('apagamento.ESPERA_S', 0), mock.patch('apagamento.os.rename', side_effect=em_uso), \
                self.assertLogs('vlado.apagamento', 'WARNING'):
            with self.assertRaisesRegex(ValueError, 'volta à lixeira na próxima partida') as recusa:
                apagamento.apagar(self.root, self.item['id'], self.token(), quem='admin')
        self.assertNotIn('continua na lixeira', str(recusa.exception))  # not the whole truth any more
        self.assertEqual([m['fase'] for m in self.manifestos()], ['renomeando'])
        apagamento.retomar(self.root)  # the next start
        self.assert_inteiro_na_lixeira()

    def test_manifesto_ilegivel_conclui_o_apagamento_confirmado_pela_lixeira(self):
        real, vezes = os.rename, [0]

        def cai_na_segunda(origem, destino):
            vezes[0] += 1
            if vezes[0] == 2:
                raise Queda()
            return real(origem, destino)
        with mock.patch('apagamento.os.rename', side_effect=cai_na_segunda), self.assertRaises(Queda):
            apagamento.apagar(self.root, self.item['id'], self.token(), quem='admin')
        manifesto = self.root / apagamento.MANIFESTOS / f'{self.item["id"]}.json'
        manifesto.write_text('{quebrado', encoding='utf-8')  # unreadable, with a root in the quarantine
        with self.assertLogs('vlado.apagamento', 'WARNING') as aviso:
            self.assertEqual(apagamento.retomar(self.root)['ilegiveis'], 1)
        self.assertIn('manifesto ilegível', '\n'.join(aviso.output))
        self.assertEqual(self.retrato(), {})  # the quarantined root and the ones still in place: all gone
        self.assertEqual((lixeira.ativos(self.root), self.no_catalogo()), ([], False))
        self.assertEqual((self.quarentena(), self.manifestos()), ([], []))
        self.assertEqual([(r['item_id'], r['confirmacao']) for r in self.registros()],
                         [(self.item['id'], 'manifesto_ilegivel')])

    def test_remocao_de_um_ilegivel_fica_fora_da_trava(self):
        # The Coruja's proof: with an unreadable manifest the files were removed inside the cadastro lock.
        from cadastrar_documentos import _trava
        real, vezes = os.rename, [0]

        def cai_na_segunda(origem, destino):
            vezes[0] += 1
            if vezes[0] == 2:
                raise Queda()
            return real(origem, destino)
        with mock.patch('apagamento.os.rename', side_effect=cai_na_segunda), self.assertRaises(Queda):
            apagamento.apagar(self.root, self.item['id'], self.token(), quem='admin')
        (self.root / apagamento.MANIFESTOS / f'{self.item["id"]}.json').write_text('{quebrado', encoding='utf-8')
        desfeito = os.unlink

        def devagar(caminho, *args, **kwargs):  # about 70 files at 50 ms: some seconds of removal
            if na_quarentena(caminho):
                time.sleep(0.05)
            return desfeito(caminho, *args, **kwargs)
        self.addCleanup(apagamento.aguardar, 60)
        with mock.patch('apagamento.os.unlink', side_effect=devagar), self.assertLogs('vlado.apagamento', 'WARNING'):
            self.assertEqual(apagamento.retomar(self.root, segundo_plano=True)['ilegiveis'], 1)
            self.assertTrue(self.quarentena())  # still being removed
            inicio = time.monotonic()
            with _trava(self.root, espera=1.0):  # another taking of the lock gets it
                pass
            self.assertLess(time.monotonic() - inicio, 1.0)
            self.assertTrue(self.quarentena(), 'a remoção terminou antes da conferência: o teste não mediu nada')
            self.assertTrue(apagamento.aguardar(60))
        self.assertEqual(self.retrato(), {})
        self.assertEqual((lixeira.ativos(self.root), self.no_catalogo()), ([], False))
        self.assertEqual((self.quarentena(), self.manifestos()), ([], []))
        self.assertEqual([(r['item_id'], r['confirmacao']) for r in self.registros()],
                         [(self.item['id'], 'manifesto_ilegivel')])

    def test_partida_nunca_cai_e_tenta_de_novo_em_segundo_plano(self):
        import trava_cadastro
        chamadas, feito = [], threading.Event()

        def ocupada_na_primeira(root, **opcoes):
            chamadas.append(opcoes)
            if len(chamadas) == 1:
                raise trava_cadastro.TravaOcupada('trava de cadastro ocupada por outro processo')
            feito.set()
            return {'desfeitos': 0, 'concluidos': 0, 'orfas': 0, 'ilegiveis': 0}
        with mock.patch.object(apagamento, 'retomar', side_effect=ocupada_na_primeira), \
                self.assertLogs('vlado.apagamento', 'WARNING'):
            self.assertIsNone(apagamento.retomar_na_partida(self.root, intervalo=0.05))  # no exception
            self.assertTrue(feito.wait(5), 'a retomada não foi tentada de novo')
        self.assertEqual(chamadas[0].get('espera'), 2.0)  # the start waits little for the lock

    def test_quarentena_sem_manifesto_e_removida_e_o_resto_fica(self):
        orfa = self.root / 'casos' / apagamento.QUARENTENA / ('d' * 32) / '0'
        orfa.mkdir(parents=True)
        (orfa / 'sobra.txt').write_text('sobra sintética', encoding='utf-8')
        alheia = self.root / 'casos' / apagamento.QUARENTENA / 'nao-e-um-item'
        alheia.mkdir()
        with self.assertLogs('vlado.apagamento', 'WARNING'):
            self.assertEqual(apagamento.retomar(self.root)['orfas'], 1)
        self.assertFalse(orfa.parent.exists())
        self.assertTrue(alheia.exists())  # not a name this module writes: left alone
        self.assertEqual(self.retrato(), self.antes)
        self.assertEqual((self.manifestos(), self.registros()), ([], []))  # nothing to record

    def test_remocao_de_quarentena_sem_manifesto_fica_fora_da_trava(self):
        # The Coruja's second proof: a leftover with no manifest was removed inside the cadastro lock.
        from cadastrar_documentos import _trava
        sobra = self.root / 'conversas' / apagamento.QUARENTENA / ('e' * 32) / '0'
        sobra.mkdir(parents=True)
        for numero in range(70):
            (sobra / f'sobra_{numero:02}.txt').write_text('sobra sintética', encoding='utf-8')
        desfeito = os.unlink

        def devagar(caminho, *args, **kwargs):  # 70 files at 50 ms: about 3.5 s of removal
            if na_quarentena(caminho):
                time.sleep(0.05)
            return desfeito(caminho, *args, **kwargs)
        self.addCleanup(apagamento.aguardar, 60)
        with mock.patch('apagamento.os.unlink', side_effect=devagar), self.assertLogs('vlado.apagamento', 'WARNING'):
            self.assertEqual(apagamento.retomar(self.root, segundo_plano=True)['orfas'], 1)
            self.assertTrue(self.quarentena())  # still being removed
            inicio = time.monotonic()
            with _trava(self.root, espera=1.0):  # another taking of the lock gets it
                pass
            self.assertLess(time.monotonic() - inicio, 1.0)
            self.assertTrue(self.quarentena(), 'a remoção terminou antes da conferência: o teste não mediu nada')
            self.assertTrue(apagamento.aguardar(60))
        self.assertFalse(sobra.parent.exists())
        self.assertEqual((self.quarentena(), self.manifestos(), self.registros()), ([], [], []))
        self.assertEqual(self.retrato(), self.antes)  # the item in the trash untouched


class ComMesa(Base):
    def subir_mesa(self):
        import http.client
        from interface_pesquisa import Servidor
        self.http = http.client
        self.server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))
        self.addCleanup(apagamento.aguardar, 60)

    def post(self, operation, data):
        con = self.http.HTTPConnection('127.0.0.1', self.server.server_port, timeout=60)
        try:
            con.request('POST', '/api/' + operation, json.dumps(data),
                        {'Content-Type': 'application/json', 'Origin': self.server.origin,
                         'X-Session-Token': self.server.token})
            resposta = con.getresponse()
            return resposta.status, json.loads(resposta.read() or b'{}')
        finally:
            con.close()


class PendenteTest(ComMesa):
    """The Coruja's remark: after a rename undone only in part, the trash kept offering Restore and Delete for
    the item while the refusal said not to. Now it flags the item and refuses both until the next start."""

    def pela_metade(self):
        real, feitas = os.rename, [0]

        def em_uso(origem, destino):
            if apagamento.QUARENTENA in Path(origem).parts:  # putting a root back: in use too
                raise PermissionError(13, 'arquivo em uso')
            feitas[0] += 1
            if feitas[0] > 1:  # the second root is in use
                raise PermissionError(13, 'arquivo em uso')
            return real(origem, destino)
        with mock.patch('apagamento.ESPERA_S', 0), mock.patch('apagamento.os.rename', side_effect=em_uso), \
                self.assertLogs('vlado.apagamento', 'WARNING'), \
                self.assertRaisesRegex(ValueError, 'volta à lixeira na próxima partida'):
            apagamento.apagar(self.root, self.item['id'], self.token(), quem='admin')
        self.assertEqual([m['fase'] for m in self.manifestos()], ['renomeando'])

    def pendentes(self):
        return {i['id']: i['apagamento_pendente'] for i in apagamento.marcar_pendentes(self.root, lixeira.ativos(self.root))}

    def test_item_pela_metade_sinalizado_e_recusado_ate_a_partida(self):
        self.assertFalse(lixeira.alcance(self.root, self.item['id'])['apagamento_pendente'])
        self.pela_metade()
        manifestos = self.manifestos()
        self.assertTrue(lixeira.alcance(self.root, self.item['id'])['apagamento_pendente'])
        self.assertEqual(self.pendentes(), {self.item['id']: True})
        with self.assertRaises(ValueError) as recusa:
            lixeira.restaurar(self.root, self.item['id'])
        self.assertEqual(str(recusa.exception), apagamento.PENDENTE)
        with self.assertRaises(ValueError) as recusa:
            apagamento.apagar(self.root, self.item['id'], self.token(), quem='admin')
        self.assertEqual(str(recusa.exception), apagamento.PENDENTE)
        self.assertEqual(self.manifestos(), manifestos)  # what the next start needs is untouched
        self.assertEqual([i['id'] for i in lixeira.ativos(self.root)], [self.item['id']])
        apagamento.retomar(self.root)  # the next start
        self.assert_inteiro_na_lixeira()
        self.assertEqual(self.pendentes(), {self.item['id']: False})
        self.assertFalse(lixeira.alcance(self.root, self.item['id'])['apagamento_pendente'])
        lixeira.restaurar(self.root, self.item['id'])  # now it can
        self.assertEqual(lixeira.ativos(self.root), [])

    def test_item_da_mesma_apuracao_tambem_espera_e_o_de_outra_nao(self):
        # A conversation of the case may have its folder in that quarantine: deleting it now would be
        # undone by the next start (the folder comes back), so it waits too. Another case does not.
        conversa = lixeira.adicionar(self.root, 'conversa', 'alpha', 'Pergunta sintética', conversa=CHAT, rodadas=['R001'])
        outra = lixeira.adicionar(self.root, 'caso', 'beta', 'Título beta')
        self.pela_metade()
        self.assertEqual(self.pendentes(), {self.item['id']: True, conversa['id']: True, outra['id']: False})
        token = lixeira.alcance(self.root, conversa['id'])['confirmacao']
        with self.assertRaises(ValueError) as recusa:
            apagamento.apagar(self.root, conversa['id'], token, quem='admin')
        self.assertEqual(str(recusa.exception), apagamento.PENDENTE)
        with self.assertRaises(ValueError) as recusa:
            lixeira.restaurar(self.root, conversa['id'])
        self.assertEqual(str(recusa.exception), apagamento.PENDENTE)
        apagamento.retomar(self.root)
        self.assertEqual(self.pendentes(), {self.item['id']: False, conversa['id']: False, outra['id']: False})
        self.assertEqual(self.retrato(), self.antes)

    def test_pela_mesa_o_sinal_e_as_recusas_com_codigo(self):
        self.subir_mesa()
        self.pela_metade()
        status, lista = self.post('gerenciar-listar', {})
        self.assertEqual((status, [(i['id'], i['apagamento_pendente']) for i in lista['lixeira']]),
                         (200, [(self.item['id'], True)]))
        status, alcance = self.post('lixeira-alcance', {'item': self.item['id']})
        self.assertEqual((status, alcance['apagamento_pendente']), (200, True))
        esperado = (400, apagamento.PENDENTE, 'apagamento_pendente')
        status, recusa = self.post('restaurar', {'item': self.item['id']})
        self.assertEqual((status, recusa.get('erro'), recusa.get('codigo')), esperado)
        status, recusa = self.post('lixeira-apagar', {'item': self.item['id'], 'confirmacao': alcance['confirmacao'],
                                                      'nome': 'Título alpha'})
        self.assertEqual((status, recusa.get('erro'), recusa.get('codigo')), esperado)
        apagamento.retomar(self.root)
        self.assert_inteiro_na_lixeira()


class MesaRespondeTest(ComMesa):
    """Through the server: the deletion's answer comes back at once and other operations that take
    the cadastro lock and the conversations' lock answer while the files are still being removed."""

    def setUp(self):
        super().setUp()
        grande = self.root / 'casos/alpha/derivados_grandes'
        grande.mkdir()
        for numero in range(1500):
            (grande / f'f{numero:05}.txt').write_bytes(b'x' * 64)
        self.antes = self.retrato()
        self.subir_mesa()

    def test_mesa_responde_durante_um_apagamento_grande(self):
        real = os.unlink

        def devagar(caminho, *args, **kwargs):  # 1500+ files at 4 ms: about 6 s of removal
            if na_quarentena(caminho):
                time.sleep(0.004)
            return real(caminho, *args, **kwargs)
        status, alcance = self.post('lixeira-alcance', {'item': self.item['id']})
        self.assertEqual(status, 200, alcance)
        with mock.patch('apagamento.os.unlink', side_effect=devagar):
            inicio = time.monotonic()
            status, feito = self.post('lixeira-apagar', {'item': self.item['id'], 'confirmacao': alcance['confirmacao'],
                                                         'nome': 'Título alpha'})
            self.assertEqual((status, feito.get('estado')), (200, 'apagado'), feito)
            self.assertLess(time.monotonic() - inicio, 3)  # the answer does not wait for the files
            self.assertTrue(self.quarentena())  # still being removed
            inicio = time.monotonic()
            status, lista = self.post('gerenciar-listar', {})  # takes the cadastro lock and the conversations' lock
            self.assertEqual(status, 200, lista)
            self.assertLess(time.monotonic() - inicio, 1.5)
            self.assertEqual(lista['lixeira'], [])
            self.assertTrue(self.quarentena(), 'a remoção terminou antes da conferência: o teste não mediu nada')
            self.assertTrue(apagamento.aguardar(60))
        self.assert_apagado_sem_sobra()


if __name__ == '__main__':
    unittest.main()
