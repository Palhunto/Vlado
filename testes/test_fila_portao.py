"""Portão da Onda 1 (CONF-02): dez sessões ao mesmo tempo com uma extração longa em curso.

A Mesa roda com a fila em modo ``processos`` (o de ``main``) e recebe um PDF pesado, lido
por cerca de 15 s num processo de extração. Enquanto ele é lido:

- um cadastro de outro documento na mesma apuração responde em menos de ``LIMITE`` segundos;
- dez sessões simultâneas leem o catálogo e o inventário, gravam e listam notas e perguntam em
  outra apuração (provedor simulado; na apuração com lote na fila a primeira pergunta é recusada
  de propósito): cada pedido responde em menos de ``LIMITE`` segundos;
- as mesmas dez sessões cadastram, cada uma, outro documento: todos publicados sem esperar o
  arquivo longo, em menos de ``LIMITE_CADASTROS`` segundos. Dez publicações e dez congelamentos
  de pergunta dividem a trava de cadastro do projeto (CONF-01) e passam um por vez, por isso o
  limite próprio; o tempo do mais lento sai na saída do teste.

O lote longo continua em processamento até o fim. Dados sintéticos; sem rede nem modelo.
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


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class PortaoFilaTest(unittest.TestCase):
    def setUp(self):
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
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

    def test_dez_sessoes_com_extracao_longa_em_curso(self):
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
            self.assertLess(time.monotonic(), limite, 'o processo de extração não começou a ler')
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
        lentos = sorted((t for t in tempos if t[0] >= (LIMITE_CADASTROS if t[2] == 'cadastro' else LIMITE)), reverse=True)
        self.assertEqual(lentos, [], 'pedidos acima do limite com a extração longa em curso')
        # The long file was still being read the whole time (otherwise the check proves nothing).
        estado = self.pedir('GET', f'/api/fila?lote={lote}')[1]['lote']
        self.assertEqual((estado['estado'], estado['arquivos'][0]['estado']), ('processando', 'extraindo'),
                         'a extração longa terminou antes das sessões; usar um PDF mais pesado')
        inventario = self.pedir('POST', '/api/inventario', {'caso': 'alpha'})[1]
        self.assertEqual(inventario['total_documentos'], 2 + SESSOES)
        outros = max(t for t in tempos if t[2] != 'cadastro')
        cadastros = max(t for t in tempos if t[2] == 'cadastro')
        print(f' [cadastro avulso {avulso:.2f} s; leitura, notas e perguntas até {outros[0]:.2f} s ({outros[2]}); '
              f'dez cadastros simultâneos até {cadastros[0]:.2f} s]', end=' ', file=sys.stderr)


if __name__ == '__main__':
    unittest.main()
