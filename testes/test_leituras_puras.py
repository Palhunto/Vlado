"""Leituras puras fora da exclusividade da trava da Mesa (Maestro, 27/11, pensando em produção).

Toda operação genérica, inclusive as leituras dos quadros, passava uma de cada vez por ``cadastro_lock``: uma busca
lenta num caso grande segurava a Mesa de todas as redações (o mapa de Paranaíta, 8 ms no processo, levou 83 s pelo
servidor). Agora ``cadastro_lock`` é uma ``trava_cadastro.TravaDaMesa``: as escritas a pegam sozinhas, como antes; as
leituras de ``interface_pesquisa.LEITURAS_PURAS`` a pegam juntas e só esperam uma escrita. Aqui: (1) cada leitura da
lista não grava nada (a pasta de dados inteira é comparada antes e depois, também quando a leitura recusa); (2) a
trava, com threads; (3) pelo servidor, uma leitura presa não segura outra, e uma escrita continua sozinha.
Dados sintéticos (``fixture_achados``).
"""
import http.client
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente  # noqa: E402
import caderno  # noqa: E402
import comum  # noqa: E402
import continuidade  # noqa: E402
import hipoteses  # noqa: E402
import interface_pesquisa  # noqa: E402
from trava_cadastro import TravaDaMesa  # noqa: E402


def retrato(root):
    """Every file and folder under the data root, with size and modification time."""
    result = {}
    for path in root.rglob('*'):
        info = path.stat()
        result[path.relative_to(root).as_posix()] = (path.is_dir(), info.st_size, info.st_mtime_ns)
    return result


class NenhumaLeituraGravaTest(unittest.TestCase):
    def setUp(self):
        self.env, (_, _, first, second) = Ambiente.copia_completa()
        self.addCleanup(self.env.cleanup)
        self.root = self.env.root
        docs = caderno.documentos(self.root, 'alpha')
        doc = docs['documentos'][0]
        nota = caderno.salvar(self.root, {
            'caso': 'alpha', 'origem_id': docs['origem_id'], 'documento_id': doc['documento_id'],
            'documento_sha256': doc['sha256'], 'pagina_pdf': None, 'localizador': 'Linha 2',
            'trecho': 'Outra versão declara valor 14.', 'titulo': 'Trecho sintético', 'anotacao': '',
            'autor': 'Ana Lima', 'tipo': 'trecho', 'transcricao_manual': False, 'requisicao_id': uuid.uuid4().hex})
        r2 = second['manifesto']['registros_sha256']
        self.ia = lambda eid: {'tipo': 'ia', 'caso_id': 'alpha', 'rodada': 'R001', 'revisao': 'r2',
                               'registros_sha256': r2, 'evidencia_id': eid}
        humana = {'tipo': 'humana', 'caso_id': 'alpha', 'registro_id': nota['registro']['id'],
                  'sha256': nota['sha256'], 'fonte': 0}
        links = [{'referencia': self.ia('E001'), 'achado_id': 'A001', 'papel': 'suporte', 'suporte': 'sustentado',
                  'natureza': 'alegacao_atribuida', 'justificativa': 'Vínculo sintético.'},
                 {'referencia': humana, 'papel': 'contexto', 'suporte': 'nao_revisado',
                  'natureza': 'declaracao_documental', 'justificativa': 'Vínculo sintético.'}]
        with comum.pedido():
            self.hipotese = hipoteses.salvar(self.root, {
                'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Ana Lima',
                'enunciado': 'A Construtora Alfa declarou valor 12.', 'evidencias': links})

    def pedido(self, operation):
        caso = {'caso': 'alpha'}
        return {'hipoteses-detalhe': {**caso, 'id': self.hipotese['id']},
                'linha-tempo-detalhe': {**caso, 'id': 'T' + '0' * 32},
                'comparar-evidencias': {**caso, 'a': self.ia('E001'), 'b': self.ia('E002')},
                'comparar-documentos': {**caso, 'rodada': 'R001', 'documento_a': 'D001', 'documento_b': 'D002'},
                'mapa-entidade-detalhe': {**caso, 'id': 'P' + '0' * 32},
                'evidencia-buscar': {**caso, 'origem': 'tudo', 'texto': '', 'limite': 50},
                'sugestoes-listar': {**caso, 'quadro': 'mapa'},
                'comparar-processos': {**caso, 'rodada': 'R001'},
                'tabelas-detalhe': {**caso, 'id': 'Q' + '0' * 32},
                'tabelas-historico-celula': {**caso, 'id': 'Q' + '0' * 32, 'linha': 'l1', 'coluna': 'c1'},
                'tabelas-calcular': {**caso, 'id': 'Q' + '0' * 32},
                'entrevistas-detalhe': {**caso, 'id': 'J' + '0' * 32},
                }.get(operation, caso)

    def test_nenhuma_leitura_pura_grava(self):
        self.assertIn('evidencia-buscar', interface_pesquisa.LEITURAS_PURAS)
        respondidas = []
        for operation in sorted(interface_pesquisa.LEITURAS_PURAS):
            antes = retrato(self.root)
            try:
                if operation == 'continuidade-resumo':
                    continuidade.executar_resumo(self.root, {'caso': 'alpha'}, None, lambda caso: [])
                else:
                    interface_pesquisa.executar(self.root, operation, self.pedido(operation))
                respondidas.append(operation)
            except ValueError:
                pass  # a refusal must not write either
            self.assertEqual(retrato(self.root), antes, operation)
        # The reads that matter answered for real, not only refused.
        for operation in ('evidencia-buscar', 'hipoteses-quadro', 'hipoteses-detalhe', 'mapa-ver',
                          'linha-tempo-listar', 'tabelas-listar', 'sugestoes-listar', 'diligencias-listar',
                          'entrevistas-listar', 'continuidade-resumo', 'comparar-evidencias'):
            self.assertIn(operation, respondidas)

    def test_so_leituras_na_lista(self):
        import rotas_evidencia
        import rotas_tabelas
        escritas = {*rotas_evidencia.SALVAR, *rotas_evidencia.SUGESTOES, *rotas_tabelas.OPERACOES} - set(rotas_tabelas.LEITURA)
        self.assertFalse(interface_pesquisa.LEITURAS_PURAS & escritas)
        self.assertFalse({op for op in interface_pesquisa.LEITURAS_PURAS
                          if any(op.endswith(s) for s in ('-criar', '-atualizar', '-salvar', '-excluir', '-exportar'))})


class TravaDaMesaTest(unittest.TestCase):
    def esperar(self, condicao, prazo=5.0):
        fim = time.monotonic() + prazo
        while not condicao():
            if time.monotonic() > fim:
                self.fail('condição não chegou no prazo')
            time.sleep(0.005)

    def em_thread(self, alvo):
        thread = threading.Thread(target=alvo, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        return thread

    def test_leituras_correm_juntas(self):
        trava, dentro, soltar = TravaDaMesa(), [], threading.Event()

        def ler():
            with trava.leitura():
                dentro.append(1)
                soltar.wait(5)
        threads = [self.em_thread(ler) for _ in range(3)]
        self.esperar(lambda: len(dentro) == 3)  # three at once
        self.assertFalse(trava.locked())
        self.assertFalse(trava.acquire(blocking=False))  # a write does not get in while they read
        soltar.set()
        for t in threads:
            t.join(5)
        self.assertTrue(trava.acquire(timeout=1))
        trava.release()

    def test_escrita_sozinha_e_leitura_espera(self):
        trava, ordem = TravaDaMesa(), []
        trava.acquire()
        self.assertTrue(trava.locked())

        def ler():
            with trava.leitura():
                ordem.append('leu')
        thread = self.em_thread(ler)
        time.sleep(0.1)
        self.assertEqual(ordem, [])  # waiting for the write
        ordem.append('escreveu')
        trava.release()
        thread.join(5)
        self.assertEqual(ordem, ['escreveu', 'leu'])

    def test_escrita_esperando_barra_leitura_nova(self):
        trava, ordem, soltar = TravaDaMesa(), [], threading.Event()
        lendo = threading.Event()

        def primeira():
            with trava.leitura():
                lendo.set()
                soltar.wait(5)
            ordem.append('primeira leitura saiu')

        def escrever():
            with trava:
                ordem.append('escrita')

        def segunda():
            with trava.leitura():
                ordem.append('segunda leitura')
        self.em_thread(primeira)
        lendo.wait(5)
        escrita = self.em_thread(escrever)
        self.esperar(lambda: trava._escritas_esperando == 1)
        leitura = self.em_thread(segunda)
        time.sleep(0.1)
        self.assertEqual(ordem, [])  # the new read waits behind the waiting write
        soltar.set()
        escrita.join(5)
        leitura.join(5)
        self.assertEqual(ordem, ['primeira leitura saiu', 'escrita', 'segunda leitura'])

    def test_prazo_e_soltar_sem_prender(self):
        trava = TravaDaMesa()
        with trava.leitura():
            inicio = time.monotonic()
            self.assertFalse(trava.acquire(timeout=0.1))
            self.assertGreaterEqual(time.monotonic() - inicio, 0.09)
        self.assertEqual(trava._escritas_esperando, 0)
        with self.assertRaises(RuntimeError):
            trava.release()


class TravaPeloServidorTest(unittest.TestCase):
    """Prova pelo servidor: uma leitura pura presa no meio não segura outra leitura; uma escrita espera por ela."""

    def setUp(self):
        from interface_pesquisa import Servidor
        self.env, _ = Ambiente.copia_completa()
        self.addCleanup(self.env.cleanup)
        self.server = Servidor(('127.0.0.1', 0), self.env.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def post(self, operation, data, respostas=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request('POST', '/api/' + operation, json.dumps(data),
                    {'Content-Type': 'application/json', 'Origin': self.server.origin,
                     'X-Session-Token': self.server.token})
        response = con.getresponse()
        result = (response.status, json.loads(response.read() or b'{}'))
        con.close()
        if respostas is not None:
            respostas.append((operation, time.monotonic()))
        return result

    def test_leitura_presa_nao_segura_outra_e_a_escrita_espera(self):
        import hipoteses as modulo
        presa, soltar = threading.Event(), threading.Event()
        original = modulo.quadro

        def quadro_lento(root, case):
            presa.set()
            soltar.wait(10)
            return original(root, case)
        respostas = []
        with patch.object(modulo, 'quadro', side_effect=quadro_lento):
            lenta = threading.Thread(target=self.post, args=('hipoteses-quadro', {'caso': 'alpha'}, respostas))
            lenta.start()
            self.assertTrue(presa.wait(10))
            self.assertTrue(self.server.cadastro_lock._leitores == 1 and not self.server.cadastro_lock.locked())
            # Another read answers while the first is held.
            status, body = self.post('mapa-ver', {'caso': 'alpha'})
            self.assertEqual(status, 200, body)
            self.assertEqual(respostas, [])
            # A write waits for the read in course.
            escrita = threading.Thread(target=self.post, args=('hipoteses-criar', {
                'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Ana Lima',
                'enunciado': 'Hipótese sintética.', 'evidencias': []}, respostas))
            escrita.start()
            self.esperar_escrita()
            time.sleep(0.2)
            self.assertEqual(respostas, [])
            soltar.set()
            lenta.join(10)
            escrita.join(10)
        self.assertEqual([op for op, _ in respostas], ['hipoteses-quadro', 'hipoteses-criar'])

    def esperar_escrita(self):
        fim = time.monotonic() + 5
        while self.server.cadastro_lock._escritas_esperando != 1:
            if time.monotonic() > fim:
                self.fail('a escrita não chegou a esperar a trava')
            time.sleep(0.005)


if __name__ == '__main__':
    unittest.main()
