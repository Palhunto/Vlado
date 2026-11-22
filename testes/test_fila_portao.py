"""Portão da Onda 1 (CONF-02): dez sessões ao mesmo tempo com uma extração longa em curso.

A Mesa roda com a fila em modo ``processos`` (o de ``main``) e recebe um PDF pesado, lido
por cerca de 15 s num processo de extração. Enquanto ele é lido:

- um cadastro de outro documento na mesma apuração responde em menos de ``LIMITE`` segundos;
- dez sessões simultâneas leem o catálogo e o inventário, gravam e listam notas e perguntam em
  outra apuração (provedor simulado; na apuração com lote na fila a primeira pergunta é recusada
  de propósito): cada pedido responde em menos de ``LIMITE`` segundos;
- as mesmas dez sessões cadastram, cada uma, outro documento: todos publicados sem esperar o
  arquivo longo. Dez publicações e dez congelamentos de pergunta dividem a trava de cadastro do
  projeto (CONF-01) e passam um por vez, por isso o limite próprio.

O lote longo continua em processamento até o fim: essa é a prova de que ninguém o esperou, e ela
é sempre exigida.

**Carga da máquina.** Antes do PDF longo, as dez sessões cadastram um documento cada ao mesmo tempo,
sem extração nenhuma em curso: o tempo do mais lento é ``T_ref``, medido na mesma máquina e no mesmo
minuto. Só cadastros, que terminam: uma rodada inteira de referência deixaria dez perguntas em curso
no provedor simulado e mudaria o que se mede. Com a extração longa, os dez cadastros têm até ``max(LIMITE_CADASTROS, 2·T_ref)``: se a fila
travasse a Mesa, o tempo saltaria para perto do tempo do arquivo longo (15 s ou mais), enquanto
``T_ref`` fica perto de 3 s numa máquina livre; numa máquina carregada os dois sobem juntos. Os dois
tempos saem na saída do teste. Só quando ``T_ref`` passa de ``SATURADA`` o teste pula, com o motivo
explícito ("máquina saturada: T_ref = X s"): aí a máquina não deixa medir, e o processo de extração,
que roda abaixo da prioridade normal (SEG-01), pode nem receber CPU para começar. Fora disso, a
falha é falha, a de começar a ler o arquivo longo (linha do prazo de 60 s) inclusive. Medido no
Windows de 4 núcleos (22/11): ``T_ref`` de 0,9 a 1,7 s com nenhum, dois ou os quatro núcleos ocupados
por outros processos; os dez cadastros com a extração longa, de 1,6 a 5,9 s.

Dados sintéticos; sem rede nem modelo.
"""
import base64
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import uuid

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import fila_extracao  # noqa: E402
from interface_pesquisa import Servidor  # noqa: E402
from modelo_pasta import copiar  # noqa: E402
import test_codex_integracao as integracao  # noqa: E402
from test_extracao_cadastro_pdf import HAS_PYPDF  # noqa: E402
from test_fila_extracao import pdf_pesado  # noqa: E402

SESSOES = 10
LIMITE = 2.0
LIMITE_CADASTROS = 12.0
SATURADA = 6.0  # T_ref above this (measured 0.9 to 1.7 s, even with all 4 cores busy): too loaded to judge


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class PortaoFilaTest(unittest.TestCase):
    def setUp(self):
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
        # The gate measures that the queue never blocks the Mesa: the ceilings of questions at the same
        # time (CUS-01, tested in test_custo) are opened for its ten simultaneous questions.
        config = json.loads((self.root / 'configuracao.json').read_text(encoding='utf-8'))
        config['orcamento'] = {'execucoes_simultaneas_por_conta': SESSOES, 'execucoes_simultaneas': SESSOES}
        config['maximo_documentos_inicial'] = 50  # the reference uploads go into the same case
        (self.root / 'configuracao.json').write_text(json.dumps(config), encoding='utf-8')
        self.server = Servidor(('127.0.0.1', 0), self.root, extracao='processos')
        self.server.conversas.factory = integracao.FakeServer
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.encerrar(10), self.server.server_close(),
                                 thread.join(10)))

    def pedir(self, metodo, caminho, dados=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        try:
            con.request(metodo, caminho, json.dumps(dados) if dados is not None else None,
                        {'Content-Type': 'application/json', 'Origin': self.server.origin,
                         'X-Session-Token': self.server.token})
            resposta = con.getresponse()
            return resposta.status, json.loads(resposta.read())
        finally:
            con.close()

    def sessao(self, numero, tempos, erros):
        texto = f'Documento sintético da sessão {numero}.'.encode('utf-8')
        pedidos = [
            ('catalogo', 'GET', '/api/catalogo', None),
            ('inventario', 'POST', '/api/inventario', {'caso': 'alpha'}),
            ('nota', 'POST', '/api/apuracao-nota-salvar', {'caso': 'alpha', 'titulo': f'Nota {numero}',
                                                           'texto': 'Nota sintética.', 'requisicao_id': uuid.uuid4().hex}),
            ('notas', 'POST', '/api/apuracao-notas', {'caso': 'alpha'}),
            ('pergunta', 'POST', '/api/codex-perguntar', {'caso': 'beta', 'pergunta': f'Pergunta sintética {numero}.'}),
            # Into the case whose long file is being read: published without waiting for it.
            ('cadastro', 'POST', '/api/cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos', 'arquivos': [
                {'nome': f'sessao_{numero}.txt', 'base64': base64.b64encode(texto).decode('ascii')}]}),
        ]
        for nome, metodo, caminho, dados in pedidos:
            inicio = time.monotonic()
            try:
                status, corpo = self.pedir(metodo, caminho, dados)
            except Exception as exc:  # noqa: BLE001 - reported by the test
                erros.append((numero, nome, repr(exc)))
                continue
            tempos.append((round(time.monotonic() - inicio, 2), numero, nome))
            if status != 200:
                erros.append((numero, nome, status, corpo))

    def cadastros_simultaneos(self, prefixo):
        """Seconds of the slowest of SESSOES simultaneous uploads (one small file each, into alpha)."""
        tempos, erros = [], []

        def cadastrar(numero):
            texto = f'Documento sintético de referência {numero}.'.encode('utf-8')
            inicio = time.monotonic()
            try:
                status, corpo = self.pedir('POST', '/api/cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos', 'arquivos': [
                    {'nome': f'{prefixo}_{numero}.txt', 'base64': base64.b64encode(texto).decode('ascii')}]})
            except Exception as exc:  # noqa: BLE001 - reported by the test
                erros.append((numero, repr(exc)))
                return
            tempos.append(time.monotonic() - inicio)
            if status != 200:
                erros.append((numero, status, corpo))
        threads = [threading.Thread(target=cadastrar, args=(n,), daemon=True) for n in range(SESSOES)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(120)
        self.assertEqual(erros, [])
        self.assertEqual(len(tempos), SESSOES)
        return max(tempos)

    def test_dez_sessoes_com_extracao_longa_em_curso(self):
        # The same ten uploads with no extraction in course: the reference of this machine, this minute.
        referencia = self.cadastros_simultaneos('referencia')
        if referencia > SATURADA:
            self.skipTest(f'máquina saturada: T_ref = {referencia:.2f} s (normal perto de 3 s; acima de '
                          f'{SATURADA:.0f} s o portão não mede)')
        limite_cadastros = max(LIMITE_CADASTROS, 2 * referencia)
        with tempfile.TemporaryDirectory() as pasta:
            pesado = pdf_pesado(Path(pasta) / 'pesado.pdf')  # about 15 s of reading on one core
            conteudo = base64.b64encode(pesado.read_bytes()).decode('ascii')
        status, corpo = self.pedir('POST', '/api/cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos', 'assincrono': True,
                                                             'arquivos': [{'nome': 'pesado.pdf', 'base64': conteudo}]})
        self.assertEqual(status, 200, corpo)
        lote = corpo['lote']['lote']
        limite = time.monotonic() + 60
        while not (fila_extracao._ler(fila_extracao.pasta_fila(self.root) / lote / 'estado.json') or {}).get(
                'arquivos', [{}])[0].get('pagina'):
            self.assertLess(time.monotonic(), limite, f'o processo de extração não começou a ler (T_ref = {referencia:.2f} s)')
            time.sleep(0.05)
        texto = base64.b64encode('Documento sintético avulso.'.encode('utf-8')).decode('ascii')
        inicio = time.monotonic()
        status, recibo = self.pedir('POST', '/api/cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos',
                                                               'arquivos': [{'nome': 'avulso.txt', 'base64': texto}]})
        avulso = time.monotonic() - inicio
        self.assertEqual((status, recibo.get('novos')), (200, 1), recibo)
        self.assertLess(avulso, LIMITE, 'o cadastro esperou a extração longa')
        tempos, erros = [], []
        sessoes = [threading.Thread(target=self.sessao, args=(n, tempos, erros), daemon=True) for n in range(SESSOES)]
        for sessao in sessoes:
            sessao.start()
        for sessao in sessoes:
            sessao.join(120)
        self.assertEqual(erros, [])
        self.assertEqual(len(tempos), SESSOES * 6)
        lentos = sorted((t for t in tempos if t[0] >= (limite_cadastros if t[2] == 'cadastro' else LIMITE)), reverse=True)
        self.assertEqual(lentos, [], f'pedidos acima do limite com a extração longa em curso (T_ref = {referencia:.2f} s, '
                                     f'limite dos cadastros {limite_cadastros:.2f} s)')
        # The long file was still being read the whole time (otherwise the check proves nothing).
        estado = self.pedir('GET', f'/api/fila?lote={lote}')[1]['lote']
        self.assertEqual((estado['estado'], estado['arquivos'][0]['estado']), ('processando', 'extraindo'),
                         'a extração longa terminou antes das sessões; usar um PDF mais pesado')
        inventario = self.pedir('POST', '/api/inventario', {'caso': 'alpha'})[1]
        self.assertEqual(inventario['total_documentos'], 2 + 2 * SESSOES)  # the reference uploads too
        outros = max(t for t in tempos if t[2] != 'cadastro')
        cadastros = max(t for t in tempos if t[2] == 'cadastro')
        print(f' [cadastro avulso {avulso:.2f} s; leitura, notas e perguntas até {outros[0]:.2f} s ({outros[2]}); '
              f'dez cadastros simultâneos até {cadastros[0]:.2f} s, sem extração (T_ref) {referencia:.2f} s]',
              end=' ', file=sys.stderr)


if __name__ == '__main__':
    unittest.main()
