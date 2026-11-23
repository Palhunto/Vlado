"""Nova apuração pela interface, no modo hospedado: o servidor escolhe o identificador e os lotes seguintes entram nele (contrato de contas, 4.4).

A tela manda o primeiro lote com ``novo: true`` e SEM ``caso`` (o portão recusa um identificador escolhido por ela) e usa o ``caso`` da resposta nos lotes
seguintes, com ``novo: false``. Aqui, contra o servidor de verdade e como o ``envio.js`` faz: o primeiro lote em fluxo cria a apuração e devolve o caso, o
segundo lote cai nela, e o resultado é uma apuração só, com os dois documentos, da pessoa que criou. O envio em JSON de antes faz o mesmo. Um identificador
escolhido junto com ``novo`` continua recusado. Dados sintéticos; sem modelo e sem rede.
"""
import base64
import http.client
import json
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
import rotas_documentos

TIPO = rotas_documentos.TIPO_LOTE


class NovaApuracaoEmLotesTest(cenario.DuasRedacoes):
    def lote_em_fluxo(self, quem, manifesto, arquivos):
        """Como envio.js: a linha do manifesto e depois os bytes, com o tipo do fluxo."""
        cookie, csrf = self.sessoes[quem]
        corpo = (json.dumps({**manifesto, 'assincrono': True, 'arquivos': [{'nome': n, 'tamanho': len(b)} for n, b in arquivos]}) + '\n').encode('utf-8')
        corpo += b''.join(b for _, b in arquivos)
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=60)
        try:
            con.request('POST', '/api/cadastrar', corpo, {'Host': 'vlado.test', 'Content-Type': TIPO, 'Cookie': cookie,
                                                             'X-Session-Token': csrf, 'Origin': cenario.ORIGEM})
            resposta = con.getresponse()
            return resposta.status, json.loads(resposta.read() or b'{}')
        finally:
            con.close()

    def esperar_publicado(self, quem, lote):
        for _ in range(240):
            status, corpo, _ = self.get_json(quem, f'/api/fila?lote={lote}')
            self.assertEqual(status, 200, corpo)
            if corpo['lote']['estado'] in ('publicado', 'falha'):
                return corpo['lote']
            time.sleep(0.25)
        self.fail('o lote não terminou')

    def get_json(self, quem, caminho):
        status, corpo = self.get(quem, caminho)[:2]
        return status, corpo, None

    def documentos(self, quem, caso):
        status, corpo, bruto = self.post(quem, 'inventario', {'caso': caso})
        self.assertEqual(status, 200, bruto[:200])
        return corpo['total_documentos']

    def test_o_primeiro_lote_cria_a_apuracao_e_o_segundo_cai_nela_pelo_caso_do_servidor(self):
        primeiro = self.lote_em_fluxo('reporter', {'novo': True, 'titulo': 'Apuração em dois lotes', 'natureza': 'sinteticos'},
                                      [('um.txt', 'Primeiro documento sintético.\n'.encode('utf-8'))])
        self.assertEqual(primeiro[0], 200, primeiro[1])
        caso = primeiro[1]['lote']['caso']
        self.assertRegex(caso, r'^apuracao_[0-9a-f]{32}$', 'o servidor escolheu o identificador e o devolveu na resposta do lote')
        self.assertEqual(self.esperar_publicado('reporter', primeiro[1]['lote']['lote'])['estado'], 'publicado')
        # O lote seguinte, como envio.js o monta: novo:false e o caso da resposta.
        segundo = self.lote_em_fluxo('reporter', {'novo': False, 'caso': caso, 'titulo': 'Apuração em dois lotes', 'natureza': 'sinteticos'},
                                     [('dois.txt', 'Segundo documento sintético.\n'.encode('utf-8'))])
        self.assertEqual(segundo[0], 200, segundo[1])
        self.assertEqual(segundo[1]['lote']['caso'], caso, 'o segundo lote caiu na mesma apuração')
        self.assertEqual(self.esperar_publicado('reporter', segundo[1]['lote']['lote'])['estado'], 'publicado')
        self.assertEqual(self.documentos('reporter', caso), 2)
        registro = acesso.posse(self.root, caso)
        self.assertEqual((registro['organizacao'], registro['responsavel']), (self.a, self.ids['reporter']))
        self.assertEqual(sum(c['id'].startswith('apuracao_') and c['titulo'] == 'Apuração em dois lotes'
                             for c in self.get('reporter', '/api/catalogo')[1]['casos']), 1, 'uma apuração só')

    def test_o_envio_em_json_de_antes_faz_o_mesmo_e_o_recibo_traz_o_caso(self):
        arquivo = lambda nome, texto: {'nome': nome, 'base64': base64.b64encode(texto.encode('utf-8')).decode('ascii')}  # noqa: E731
        primeiro = self.post('reporter', 'cadastrar', {'novo': True, 'titulo': 'Apuração em JSON', 'natureza': 'sinteticos',
                                                       'arquivos': [arquivo('a.txt', 'Texto A sintético.\n')]})
        self.assertEqual(primeiro[0], 200, primeiro[2][:300])
        caso = primeiro[1]['caso_id']
        self.assertRegex(caso, r'^apuracao_[0-9a-f]{32}$')
        segundo = self.post('reporter', 'cadastrar', {'novo': False, 'caso': caso, 'natureza': 'sinteticos',
                                                      'arquivos': [arquivo('b.txt', 'Texto B sintético.\n')]})
        self.assertEqual(segundo[0], 200, segundo[2][:300])
        self.assertEqual(segundo[1]['caso_id'], caso)
        self.assertEqual(self.documentos('reporter', caso), 2)

    def test_um_identificador_escolhido_junto_com_novo_continua_recusado(self):
        arquivo = {'nome': 'x.txt', 'base64': base64.b64encode(b'Texto.\n').decode('ascii')}
        recusa = self.post('reporter', 'cadastrar', {'novo': True, 'caso': 'apuracao_' + '0' * 32, 'titulo': 'T', 'arquivos': [arquivo]})
        self.assertEqual((recusa[0], recusa[1]['codigo']), (403, 'campos_nao_permitidos'))
        fluxo = self.lote_em_fluxo('reporter', {'novo': True, 'caso': 'apuracao_' + '1' * 32, 'titulo': 'T'}, [('y.txt', b'Texto.\n')])
        self.assertEqual((fluxo[0], fluxo[1].get('codigo')), (403, 'campos_nao_permitidos'))


if __name__ == '__main__':
    unittest.main()
