"""Rascunhos no servidor (scripts/rascunhos.py) e suas rotas na Mesa.

Pasta temporária com apurações sintéticas; nenhuma chamada de modelo ou de rede externa.
Cobre gravação e leitura, conflito de versão entre abas, limites de tamanho, isolamento entre
contas e apurações, a ida do rascunho para a lixeira com o caso e a recusa de campos de chave.
"""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import escrever_json
import erros
import limites
import lixeira
import rascunhos
from fixture_achados import Ambiente
from interface_pesquisa import Servidor
import test_autorizacao as autorizacao  # module import: its TestCases are not re-collected here

ANA = {'id': 'a1b2c3d4e5f60708', 'nome': 'Ana'}
BIA = {'id': '0807f6e5d4c3b2a1', 'nome': 'Bia'}


class RascunhosTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        escrever_json(self.root / 'configuracao.json', {})
        for caso in ('alpha', 'beta'):
            (self.root / 'casos' / caso).mkdir(parents=True)

    def salvar(self, versao, texto, conta=ANA, caso='alpha', tela='caderno/N0001', **extra):
        return rascunhos.salvar(self.root, caso, conta, tela, versao, {'texto': texto, **extra})

    def test_grava_le_e_lista_com_versao_crescente(self):
        vazio = rascunhos.ler(self.root, 'alpha', ANA, 'caderno/N0001')
        self.assertEqual((vazio['versao'], vazio['conteudo']), (0, None))
        primeiro = self.salvar(0, 'Primeira frase.', revisao_base=3)
        self.assertEqual(primeiro['versao'], 1)
        segundo = self.salvar(1, 'Primeira frase. Segunda.', revisao_base=3)
        self.assertEqual(segundo['versao'], 2)
        lido = rascunhos.ler(self.root, 'alpha', ANA, 'caderno/N0001')
        self.assertEqual(lido['conteudo'], {'texto': 'Primeira frase. Segunda.', 'revisao_base': 3})
        self.assertTrue(lido['atualizado_em_utc'])
        lista = rascunhos.listar(self.root, 'alpha', ANA)['rascunhos']
        self.assertEqual([(r['tela'], r['versao']) for r in lista], [('caderno/N0001', 2)])
        self.assertNotIn('conteudo', lista[0])
        arquivos = list((self.root / 'casos/alpha/rascunhos').rglob('*.json'))
        self.assertEqual(len(arquivos), 1)
        self.assertEqual(json.loads(arquivos[0].read_text(encoding='utf-8'))['versao'], 2)
        self.assertEqual([p.name for p in arquivos[0].parent.iterdir()], [arquivos[0].name], 'sem temporário')

    def test_aba_com_versao_antiga_nao_sobrescreve(self):
        self.salvar(0, 'Texto da aba A.')
        self.salvar(1, 'Texto da aba A, continuado.')
        with self.assertRaises(rascunhos.ConflitoRascunho) as ctx:
            self.salvar(1, 'Texto da aba B.')
        self.assertEqual(ctx.exception.atual['versao'], 2)
        self.assertEqual(ctx.exception.atual['conteudo']['texto'], 'Texto da aba A, continuado.')
        self.assertEqual(erros.codigo_de(str(ctx.exception))[0], 'rascunho_conflito')
        self.assertEqual(rascunhos.ler(self.root, 'alpha', ANA, 'caderno/N0001')['conteudo']['texto'],
                         'Texto da aba A, continuado.')
        with self.assertRaises(rascunhos.ConflitoRascunho):
            self.salvar(0, 'Rascunho novo numa terceira aba.')

    def test_reenvio_do_mesmo_conteudo_nao_e_conflito(self):
        self.salvar(0, 'Mesmo texto.')
        repetido = self.salvar(0, 'Mesmo texto.')  # a resposta do primeiro pedido se perdeu
        self.assertEqual(repetido['versao'], 1)

    def test_escritores_simultaneos_so_um_vence_cada_versao(self):
        resultados, conflitos = [], []

        def escrever(n):
            try:
                resultados.append(self.salvar(0, f'Aba {n}.'))
            except rascunhos.ConflitoRascunho as exc:
                conflitos.append(exc.atual)

        threads = [threading.Thread(target=escrever, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(resultados), 1)
        self.assertEqual(len(conflitos), 7)
        self.assertEqual(rascunhos.ler(self.root, 'alpha', ANA, 'caderno/N0001')['conteudo'],
                         resultados[0]['conteudo'])

    def test_descartar_mantem_a_versao_e_recusa_aba_antiga(self):
        self.salvar(0, 'Vai ser descartado.')
        with self.assertRaises(rascunhos.ConflitoRascunho):
            rascunhos.descartar(self.root, 'alpha', ANA, 'caderno/N0001', 0)
        descartado = rascunhos.descartar(self.root, 'alpha', ANA, 'caderno/N0001', 1)
        self.assertEqual((descartado['versao'], descartado['conteudo'], descartado['descartado']), (2, None, True))
        self.assertEqual(rascunhos.listar(self.root, 'alpha', ANA)['rascunhos'], [])
        arquivo = next((self.root / 'casos/alpha/rascunhos').rglob('*.json'))
        self.assertNotIn('Vai ser descartado', arquivo.read_text(encoding='utf-8'))
        with self.assertRaises(rascunhos.ConflitoRascunho):  # aba antiga não ressuscita o rascunho
            self.salvar(1, 'Texto antigo.')
        self.assertEqual(self.salvar(2, 'Recomeço.')['versao'], 3)

    def test_limites_por_rascunho_e_por_caso(self):
        with patch.dict(limites.RASCUNHOS, {'bytes_por_rascunho': 2048, 'bytes_rascunhos_por_caso': 3000,
                                            'rascunhos_por_caso': 3}):
            with self.assertRaises(ValueError) as ctx:
                self.salvar(0, 'x' * 3000)
            self.assertEqual(erros.codigo_de(str(ctx.exception)), ('rascunho_grande_demais', {'limite': 2}))
            self.assertEqual(rascunhos.ler(self.root, 'alpha', ANA, 'caderno/N0001')['versao'], 0)
            self.salvar(0, 'y' * 1400, tela='caderno/N0001')
            self.salvar(0, 'y' * 1400, conta=BIA, tela='caderno/N0002')  # o limite do caso soma todas as contas
            with self.assertRaises(ValueError) as ctx:
                self.salvar(0, 'y' * 1400, tela='caderno/N0003')
            self.assertEqual(erros.codigo_de(str(ctx.exception))[0], 'rascunhos_caso_cheio')
            self.salvar(1, 'y' * 1400, tela='caderno/N0001')  # substituir o próprio rascunho não soma duas vezes
            self.salvar(0, 'curto', tela='caderno/N0003')
            with self.assertRaises(ValueError) as ctx:
                self.salvar(0, 'curto', tela='caderno/N0004')
            self.assertEqual(erros.codigo_de(str(ctx.exception)), ('rascunhos_caso_limite', {'limite': 3}))
            self.salvar(0, 'outra apuração', tela='caderno/N0004', caso='beta')

    def test_isolamento_entre_contas_e_apuracoes(self):
        self.salvar(0, 'Rascunho da Ana em alpha.')
        self.assertEqual(rascunhos.ler(self.root, 'alpha', BIA, 'caderno/N0001')['conteudo'], None)
        self.assertEqual(rascunhos.ler(self.root, 'beta', ANA, 'caderno/N0001')['conteudo'], None)
        self.assertEqual(rascunhos.ler(self.root, 'alpha', None, 'caderno/N0001')['conteudo'], None)
        self.assertEqual(rascunhos.listar(self.root, 'alpha', BIA)['rascunhos'], [])
        self.assertEqual(self.salvar(0, 'Rascunho da Bia.', conta=BIA)['versao'], 1, 'versões independentes')
        self.assertEqual(rascunhos.ler(self.root, 'alpha', ANA, 'caderno/N0001')['conteudo']['texto'],
                         'Rascunho da Ana em alpha.')
        with self.assertRaises(ValueError):
            rascunhos.ler(self.root, 'gamma', ANA, 'caderno/N0001')
        with self.assertRaises(ValueError):
            rascunhos.ler(self.root, 'alpha', {'id': '../x'}, 'caderno/N0001')
        for tela in ('../segredos', 'Caderno', 'caderno/../x', '', 'a' * 41):
            with self.subTest(tela=tela), self.assertRaises(ValueError):
                rascunhos.ler(self.root, 'alpha', ANA, tela)

    def test_rascunho_vai_para_a_lixeira_com_o_caso(self):
        self.salvar(0, 'Rascunho que segue o caso.')
        item = lixeira.adicionar(self.root, 'caso', 'alpha', 'Caso alpha')
        for chamada in (lambda: rascunhos.ler(self.root, 'alpha', ANA, 'caderno/N0001'),
                        lambda: rascunhos.listar(self.root, 'alpha', ANA),
                        lambda: self.salvar(1, 'Na lixeira.'),
                        lambda: rascunhos.descartar(self.root, 'alpha', ANA, 'caderno/N0001', 1)):
            with self.assertRaises(ValueError) as ctx:
                chamada()
            self.assertIn('lixeira', str(ctx.exception))
        self.assertEqual(rascunhos.listar(self.root, 'beta', ANA)['rascunhos'], [])
        alcance = lixeira.alcance(self.root, item['id'])
        self.assertGreaterEqual(alcance['categorias']['rascunhos']['arquivos'], 1)  # o rascunho e a trava
        lixeira.restaurar(self.root, item['id'])
        self.assertEqual(rascunhos.ler(self.root, 'alpha', ANA, 'caderno/N0001')['conteudo']['texto'],
                         'Rascunho que segue o caso.')
        item = lixeira.adicionar(self.root, 'caso', 'alpha', 'Caso alpha')
        alcance = lixeira.alcance(self.root, item['id'])
        lixeira.apagar_definitivamente(self.root, item['id'], alcance['confirmacao'], quem='teste')
        self.assertFalse((self.root / 'casos/alpha/rascunhos').exists())

    def test_nenhum_campo_de_chave_e_aceito(self):
        for campo in ('chave', 'api_key', 'chave_api', 'openai_api_key', 'senha', 'token', 'segredo', 'secret'):
            with self.subTest(campo=campo), self.assertRaises(ValueError) as ctx:
                rascunhos.salvar(self.root, 'alpha', ANA, 'pergunta', 0, {'texto': 'oi', campo: 'valor'})
            self.assertEqual(erros.codigo_de(str(ctx.exception))[0], 'rascunho_com_chave')
        falsa = 'sk-ant-' + 'A1b2C3d4' * 4  # forma de chave, valor sintético
        for texto in (f'cole aqui {falsa}', 'sk-proj-' + 'x' * 30, 'export ANTHROPIC_API_KEY=algo'):
            with self.subTest(texto=texto[:12]), self.assertRaises(ValueError):
                rascunhos.salvar(self.root, 'alpha', ANA, 'pergunta', 0, {'texto': texto})
        with patch('segredos.conhecidas', return_value=frozenset({'valor-sintetico-conhecido-123'})):
            with self.assertRaises(ValueError):
                rascunhos.salvar(self.root, 'alpha', ANA, 'pergunta', 0, {'texto': 'xx valor-sintetico-conhecido-123'})
        self.assertFalse((self.root / 'casos/alpha/rascunhos').exists() and
                         list((self.root / 'casos/alpha/rascunhos').rglob('*.json')), 'nada foi gravado')

    def test_conteudo_invalido_e_recusado(self):
        for conteudo in (None, {}, [], 'texto', {'texto': {'aninhado': 1}}, {'Texto': 'x'}, {'texto': float('nan')},
                         {f'c{i}': 'x' for i in range(51)}):
            with self.subTest(conteudo=str(conteudo)[:30]), self.assertRaises(ValueError) as ctx:
                rascunhos.salvar(self.root, 'alpha', ANA, 'pergunta', 0, conteudo)
            self.assertEqual(erros.codigo_de(str(ctx.exception))[0], 'rascunho_invalido')
        for versao in (-1, '1', None, 1.0, True):
            with self.subTest(versao=versao), self.assertRaises(ValueError):
                rascunhos.salvar(self.root, 'alpha', ANA, 'pergunta', versao, {'texto': 'x'})

    def test_despacho_confere_campos_casos_e_convidado(self):
        with self.assertRaises(ValueError):
            rascunhos.executar(self.root, 'rascunhos-ler', {'caso': 'alpha', 'tela': 'pergunta', 'caminho': 'x'}, ANA)
        with self.assertRaises(ValueError) as ctx:
            rascunhos.executar(self.root, 'rascunhos-ler', {'caso': 'beta', 'tela': 'pergunta'}, ANA, casos=['alpha'])
        self.assertEqual(erros.codigo_de(str(ctx.exception))[0], 'caso_nao_liberado')
        with self.assertRaises(ValueError) as ctx:
            rascunhos.executar(self.root, 'rascunhos-salvar',
                               {'caso': 'alpha', 'tela': 'caderno/N0001', 'versao': 0, 'conteudo': {'texto': 'x'}},
                               ANA, casos=['alpha'], convidado=True)
        self.assertEqual(erros.codigo_de(str(ctx.exception))[0], 'rascunho_so_pergunta')
        salvo = rascunhos.executar(self.root, 'rascunhos-salvar',
                                   {'caso': 'alpha', 'tela': 'pergunta', 'versao': 0, 'conteudo': {'texto': 'Pergunta?'}},
                                   ANA, casos=['alpha'], convidado=True)
        self.assertEqual(salvo['versao'], 1)

    def test_convidado_tem_limite_proprio_e_nao_esgota_o_caso(self):
        def convidado(tela, conta=BIA):
            return rascunhos.executar(self.root, 'rascunhos-salvar',
                                      {'caso': 'alpha', 'tela': tela, 'versao': 0, 'conteudo': {'texto': 'x'}},
                                      conta, casos=['alpha'], convidado=True)
        with patch.dict(limites.RASCUNHOS, {'rascunhos_por_convidado': 2, 'rascunhos_por_caso': 5}):
            convidado('pergunta/a1')
            convidado('pergunta/a2')
            with self.assertRaises(ValueError) as ctx:
                convidado('pergunta/a3')
            self.assertEqual(erros.codigo_de(str(ctx.exception)), ('rascunhos_conta_limite', {'limite': 2}))
            convidado('pergunta/a3', conta=ANA)  # o limite é de cada conta
            self.salvar(0, 'A redação continua salvando.', tela='caderno/N0001')
            self.salvar(0, 'Administração sem o limite de convidado.', tela='caderno/N0002')


class RascunhosRotasTest(unittest.TestCase):
    """Modo local: as quatro rotas, o 409 com a versão atual e o código de cada recusa."""

    @classmethod
    def setUpClass(cls):
        cls.env = Ambiente()
        cls.root = cls.env.root
        (cls.root / 'casos/alpha').mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.env.cleanup()

    def setUp(self):
        self.server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def post(self, op, data, token=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request('POST', '/api/' + op, body=json.dumps(data), headers={
            'Content-Type': 'application/json', 'Origin': self.server.origin,
            'X-Session-Token': token or self.server.token})
        response = con.getresponse()
        body = json.loads(response.read() or b'{}')
        con.close()
        return response.status, body

    def test_salvar_ler_listar_conflito_e_descartar(self):
        tela = 'caderno/N0042'
        status, body = self.post('rascunhos-salvar', {'caso': 'alpha', 'tela': tela, 'versao': 0,
                                                      'conteudo': {'texto': 'Nota em preparo.'}})
        self.assertEqual((status, body['versao']), (200, 1), body)
        status, body = self.post('rascunhos-salvar', {'caso': 'alpha', 'tela': tela, 'versao': 0,
                                                      'conteudo': {'texto': 'Outra aba.'}})
        self.assertEqual((status, body['codigo']), (409, 'rascunho_conflito'), body)
        self.assertEqual(body['atual']['conteudo'], {'texto': 'Nota em preparo.'})
        status, body = self.post('rascunhos-ler', {'caso': 'alpha', 'tela': tela})
        self.assertEqual((status, body['versao']), (200, 1))
        status, body = self.post('rascunhos-listar', {'caso': 'alpha'})
        self.assertIn(tela, [r['tela'] for r in body['rascunhos']])
        status, body = self.post('rascunhos-descartar', {'caso': 'alpha', 'tela': tela, 'versao': 1})
        self.assertEqual((status, body['descartado']), (200, True))
        status, body = self.post('rascunhos-ler', {'caso': 'alpha', 'tela': tela, 'extra': 1})
        self.assertEqual((status, body['codigo']), (400, 'rascunho_invalido'), body)
        status, body = self.post('rascunhos-salvar', {'caso': 'alpha', 'tela': 'pergunta', 'versao': 0,
                                                      'conteudo': {'api_key': 'x'}})
        self.assertEqual((status, body['codigo']), (400, 'rascunho_com_chave'), body)
        status, body = self.post('rascunhos-ler', {'caso': 'alpha', 'tela': tela}, token='errado')
        self.assertEqual(status, 403)

    def test_rascunho_grande_cabe_no_corpo_aceito(self):
        texto = 'Parágrafo longo da nota. ' * 8000  # ~200 KB, como uma nota grande do Caderno
        status, body = self.post('rascunhos-salvar', {'caso': 'alpha', 'tela': 'caderno/N0099', 'versao': 0,
                                                      'conteudo': {'texto': texto}})
        self.assertEqual(status, 200, body.get('erro'))


class RascunhosContasTest(autorizacao.Http):
    """Modo hospedado: sem sessão 401; cada conta vê só os próprios rascunhos; convidado só a pergunta."""

    def test_contas_isoladas_e_convidado_limitado(self):
        for op in rascunhos.OPERACOES:
            status, _, _ = self.request('POST', '/api/' + op, json.dumps({'caso': 'alpha'}),
                                        {'Content-Type': 'application/json', 'Origin': autorizacao.ORIGEM})
            self.assertEqual(status, 401, op)
        pedido = {'caso': 'alpha', 'tela': 'pergunta', 'versao': 0, 'conteudo': {'texto': 'Pergunta da Ana?'}}
        status, body = self.post(self.ana, 'rascunhos-salvar', pedido)
        self.assertEqual((status, body['versao']), (200, 1), body)
        status, body = self.post(self.admin, 'rascunhos-ler', {'caso': 'alpha', 'tela': 'pergunta'})
        self.assertEqual((status, body['conteudo']), (200, None), 'a editora não vê o rascunho da Ana')
        status, body = self.post(self.admin, 'rascunhos-salvar', pedido)
        self.assertEqual((status, body['versao']), (200, 1), 'versão própria da conta')
        status, body = self.post(self.bia, 'rascunhos-ler', {'caso': 'alpha', 'tela': 'pergunta'})
        self.assertEqual((status, body['codigo']), (400, 'caso_nao_liberado'), body)
        status, body = self.post(self.ana, 'rascunhos-salvar', {**pedido, 'tela': 'caderno/N0001'})
        self.assertEqual((status, body['codigo']), (400, 'rascunho_so_pergunta'), body)
        status, body = self.post(self.ana, 'rascunhos-listar', {'caso': 'alpha'})
        self.assertEqual([r['tela'] for r in body['rascunhos']], ['pergunta'])


if __name__ == '__main__':
    unittest.main()
