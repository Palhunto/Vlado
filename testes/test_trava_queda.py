"""Queda e encerramento da Mesa com a trava de cadastro presa (CONF-01, portão da Onda 1).

A Mesa roda em outro processo (``apoio_trava_processo.py servidor``), com provedor simulado e
dados sintéticos. Cada teste para uma operação dentro da trava, com a pasta de preparo criada,
e então mata o processo (TerminateProcess no Windows, SIGKILL no Linux) ou pede o encerramento
(SIGTERM no Linux, Ctrl+Break no Windows). Depois sobe outra Mesa na mesma pasta, como faz a
política de reinício do Compose, e confere que ela volta sozinha: trava livre, preparo limpo,
cadastro e pergunta funcionando, nenhum dado do cadastro perdido ou corrompido.
"""
import base64
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import unittest

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import test_codex_integracao as integracao  # noqa: E402
from modelo_pasta import copiar  # noqa: E402
import trava_cadastro  # noqa: E402

AUXILIAR = TESTES / 'apoio_trava_processo.py'


def esperar(condicao, prazo=30, mensagem='condição não atingida'):
    limite = time.monotonic() + prazo
    while not condicao():
        if time.monotonic() > limite:
            raise AssertionError(mensagem)
        time.sleep(0.05)


def lote(nome='novo.txt', texto='Documento novo sintético para o teste de queda.'):
    return {'caso': 'alpha', 'natureza': 'sinteticos',
            'arquivos': [{'nome': nome, 'base64': base64.b64encode(texto.encode('utf-8')).decode('ascii')}]}


class Mesa:
    """A Mesa in another process. Its output is drained in threads (never a full pipe)."""

    def __init__(self, teste, raiz, *opcoes, grupo=False):
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if grupo and os.name == 'nt' else 0
        self.proc = subprocess.Popen([sys.executable, str(AUXILIAR), 'servidor', str(raiz), *opcoes],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                     encoding='utf-8', creationflags=flags)
        teste.addCleanup(self.matar)
        linha = self.proc.stdout.readline()
        if not linha:
            self.proc.wait(10)
            teste.fail('a Mesa auxiliar não subiu: ' + self.proc.stderr.read())
        info = json.loads(linha)
        self.porta, self.token, self.pid = info['porta'], info['token'], info['pid']
        self.saida, self.erros = [], []
        self._leitores = [threading.Thread(target=self._ler, args=(fluxo, destino), daemon=True)
                          for fluxo, destino in ((self.proc.stdout, self.saida), (self.proc.stderr, self.erros))]
        for leitor in self._leitores:
            leitor.start()
        # The port is printed before servir(); it answers only after the start-up cleanup ran.
        teste.assertEqual(self.saude(), 200)

    @staticmethod
    def _ler(fluxo, destino):
        for linha in fluxo:
            destino.append(linha)

    def texto(self):
        for leitor in self._leitores:
            leitor.join(5)
        return ''.join(self.saida), ''.join(self.erros)

    def post(self, operacao, dados, prazo=30):
        con = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=prazo)
        try:
            con.request('POST', '/api/' + operacao, json.dumps(dados),
                        {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{self.porta}',
                         'X-Session-Token': self.token})
            resposta = con.getresponse()
            return resposta.status, json.loads(resposta.read())
        finally:
            con.close()

    def saude(self):
        con = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=10)
        try:
            con.request('GET', '/saude')
            resposta = con.getresponse()
            resposta.read()
            return resposta.status
        finally:
            con.close()

    def desligar(self, teste):
        """"Encerrar Mesa" (codex-desligar): the orderly path of servir()."""
        teste.assertEqual(self.post('codex-desligar', {})[0], 200)
        teste.assertEqual(self.proc.wait(20), 0)

    def sinal(self):
        if os.name == 'nt':
            self.proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            self.proc.send_signal(signal.SIGTERM)

    def matar(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(20)
        self.texto()
        for fluxo in (self.proc.stdout, self.proc.stderr):
            fluxo.close()


class QuedaTest(unittest.TestCase):
    def setUp(self):
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)  # registered first: runs after every Mesa was stopped
        self.marca = self.root / 'marca_pausa.txt'

    def preparo(self, pasta, prefixo):
        base = self.root / pasta
        return sorted(p.name for p in base.iterdir() if p.name.startswith(prefixo)) if base.is_dir() else []

    def enviar_em_segundo_plano(self, mesa, operacao, dados):
        resultado = {}

        def alvo():
            try:
                resultado['resposta'] = mesa.post(operacao, dados, prazo=60)
            except (OSError, http.client.HTTPException) as exc:  # the process died mid-request
                resultado['erro'] = exc
        thread = threading.Thread(target=alvo, daemon=True)
        thread.start()
        return thread, resultado

    def test_morte_no_meio_do_cadastro_e_a_mesa_volta_sozinha(self):
        protegidos = ('casos/alpha/manifesto.json', 'casos/catalogo.json')
        antes = {p: (self.root / p).read_bytes() for p in protegidos}
        mesa = Mesa(self, self.root, '--pausa-cadastro', str(self.marca))
        envio, _ = self.enviar_em_segundo_plano(mesa, 'cadastrar', lote())
        esperar(self.marca.exists, mensagem='o cadastro não chegou à pausa dentro da trava')
        dono = trava_cadastro.ler_dono(self.root)
        self.assertEqual((dono['estado'], dono['pid'], dono['operacao']), ('ocupada', mesa.pid, 'cadastro'))
        self.assertEqual(len(self.preparo('casos', '.lote_')), 1)
        mesa.matar()
        envio.join(10)
        # Nothing of the interrupted batch was published, nothing was corrupted.
        self.assertEqual({p: (self.root / p).read_bytes() for p in protegidos}, antes)
        self.assertEqual(len(list((self.root / 'casos/alpha/cadastros').iterdir())), 1)
        self.marca.unlink()
        nova = Mesa(self, self.root)
        self.assertEqual(nova.saude(), 200)
        self.assertEqual(self.preparo('casos', '.lote_'), [])
        status, recibo = nova.post('cadastrar', lote())
        self.assertEqual(status, 200, recibo)
        self.assertEqual((recibo['novos'], recibo['corpus_id']), (1, 'alpha_v2'))
        status, inventario = nova.post('inventario', {'caso': 'alpha'})
        self.assertEqual((status, inventario['total_documentos']), (200, 2))
        nova.desligar(self)
        saida, erros = nova.texto()
        self.assertIn(f'abandonada pelo processo {mesa.pid}', erros)
        self.assertIn('Partida: trava de cadastro recuperada', saida)
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')

    def test_morte_no_meio_da_pergunta_e_a_mesa_volta_sozinha(self):
        mesa = Mesa(self, self.root, '--pausa-congelamento', str(self.marca))
        status, resposta = mesa.post('codex-perguntar', {'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'})
        self.assertEqual(status, 200, resposta)
        conversa = resposta['conversa']
        esperar(self.marca.exists, mensagem='o congelamento não chegou à pausa dentro da trava')
        dono = trava_cadastro.ler_dono(self.root)
        self.assertEqual((dono['estado'], dono['pid'], dono['operacao']), ('ocupada', mesa.pid, 'congelamento'))
        self.assertEqual(len(self.preparo('execucoes', '.r_')), 1)
        mesa.matar()
        self.assertFalse((self.root / 'execucoes/alpha/R001').exists())
        self.marca.unlink()

        nova = Mesa(self, self.root)
        self.assertEqual(self.preparo('execucoes', '.r_'), [])
        status, lista = nova.post('codex-listar', {'caso': 'alpha'})
        self.assertEqual(status, 200, lista)
        self.assertEqual([c['estado'] for c in lista['conversas'] if c['id'] == conversa], ['interrompido'])
        # The lock is free: the same conversation freezes a new question and runs it.
        status, resposta = nova.post('codex-perguntar', {'caso': 'alpha', 'conversa': conversa,
                                                         'pergunta': 'Pergunta técnica sintética, de novo.'})
        self.assertEqual(status, 200, resposta)
        esperar(lambda: nova.post('codex-eventos', {'conversa': conversa})[1]['conversa']['estado'] == 'executando',
                mensagem='a pergunta não voltou a executar depois da queda')
        self.assertTrue((self.root / 'execucoes/alpha/R001/snapshot.json').is_file())
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')

        # Killed again while the stages run (no lock held): back again, interrupted and resumable.
        nova.matar()
        terceira = Mesa(self, self.root)
        status, lista = terceira.post('codex-listar', {'caso': 'alpha'})
        item = next(c for c in lista['conversas'] if c['id'] == conversa)
        self.assertEqual((item['estado'], item['rodada']), ('interrompido', 'R001'))
        status, resposta = terceira.post('codex-retomar', {'conversa': conversa})
        self.assertEqual((status, resposta.get('rodada')), (200, 'R001'), resposta)
        status, recibo = terceira.post('cadastrar', lote())
        self.assertEqual((status, recibo.get('novos')), (200, 1), recibo)
        terceira.desligar(self)

    def test_pedido_de_encerramento_espera_o_cadastro_em_curso(self):
        mesa = Mesa(self, self.root, '--pausa-cadastro', str(self.marca), '--segundos', '1.5', grupo=True)
        envio, resultado = self.enviar_em_segundo_plano(mesa, 'cadastrar', lote())
        esperar(self.marca.exists, mensagem='o cadastro não chegou à pausa dentro da trava')
        try:
            mesa.sinal()
        except OSError as exc:  # no console to receive Ctrl+Break (Windows service runner)
            self.skipTest(f'sinal de encerramento indisponível neste ambiente: {exc}')
        self.assertEqual(mesa.proc.wait(20), 0)
        envio.join(10)
        # The cadastro in progress finished and its answer reached the client before the exit.
        self.assertNotIn('erro', resultado)
        status, recibo = resultado['resposta']
        self.assertEqual((status, recibo['novos'], recibo['corpus_id']), (200, 1, 'alpha_v2'))
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'livre')  # released, not abandoned
        self.assertEqual(self.preparo('casos', '.lote_'), [])
        saida, _ = mesa.texto()
        self.assertIn('Mesa encerrada.', saida)
        with self.assertRaises(OSError):  # no longer listening
            http.client.HTTPConnection('127.0.0.1', mesa.porta, timeout=2).connect()

    def test_encerramento_alem_do_prazo_deixa_trava_que_a_partida_recupera(self):
        antes = (self.root / 'casos/alpha/manifesto.json').read_bytes()
        mesa = Mesa(self, self.root, '--pausa-cadastro', str(self.marca), '--prazo', '0.5')
        envio, _ = self.enviar_em_segundo_plano(mesa, 'cadastrar', lote())
        esperar(self.marca.exists, mensagem='o cadastro não chegou à pausa dentro da trava')
        mesa.post('codex-desligar', {})
        self.assertEqual(mesa.proc.wait(20), 0)
        envio.join(10)
        saida, _ = mesa.texto()
        self.assertIn('Mesa encerrada antes do fim de uma operação', saida)
        self.assertEqual((self.root / 'casos/alpha/manifesto.json').read_bytes(), antes)
        self.assertEqual(trava_cadastro.ler_dono(self.root)['estado'], 'ocupada')
        self.marca.unlink()
        nova = Mesa(self, self.root)
        status, recibo = nova.post('cadastrar', lote())
        self.assertEqual((status, recibo.get('novos')), (200, 1), recibo)
        self.assertEqual(self.preparo('casos', '.lote_'), [])
        nova.desligar(self)


if __name__ == '__main__':
    unittest.main()
