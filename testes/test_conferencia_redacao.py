"""Conferência da redação por afirmação (scripts/conferencia_redacao.py e scripts/rotas_redacao.py).

Divisão em afirmações com posição, sinais determinísticos de exagero, estados a partir de
vínculos conferidos pelo contrato do Core, revisão humana só por conta autenticada, nova
versão que reabre afirmações alteradas e rotas HTTP da Mesa. Fontes sintéticas; sem modelo
nem rede.
"""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente
from interface_pesquisa import Servidor
import caderno
import conferencia_redacao as redacao
import rotas_redacao
import test_autorizacao as autorizacao  # module import: its TestCases are not re-collected here

CONTA = {'id': 'conta-revisora', 'nome': 'Editora C'}


class Fontes:
    def preparar(self, env, second):
        self.env, self.root = env, env.root
        self.registros = second['manifesto']['registros_sha256']

    def ia(self, eid='E001'):
        return {'tipo': 'ia', 'caso_id': 'alpha', 'rodada': 'R001', 'revisao': 'r2',
                'registros_sha256': self.registros, 'evidencia_id': eid}

    def link(self, ref, papel='suporte', suporte='sustentado', natureza='declaracao_documental'):
        return {'referencia': ref, 'papel': papel, 'suporte': suporte, 'natureza': natureza,
                'justificativa': 'Vínculo sintético.'}

    def base(self, **fields):
        return {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Repórter A', **fields}

    def criar(self, texto, titulo='Reportagem sintética'):
        return redacao.criar(self.root, self.base(titulo=titulo, texto=texto))

    def vincular(self, record, indice, links):
        claim = record['estado']['afirmacoes'][indice]
        return redacao.vincular(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'],
                                                     afirmacao_id=claim['id'], evidencias=links))

    def revisar(self, record, indice, decisao='conferida_no_original', conta=CONTA, **extra):
        claim = record['estado']['afirmacoes'][indice]
        return redacao.revisar(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'],
                                                    afirmacao_id=claim['id'], decisao=decisao, **extra), conta)

    def ver(self, record):
        return redacao.conferencia(self.root, 'alpha', record['id'])


class DivisaoESinaisTest(unittest.TestCase):
    def test_divide_em_frases_e_oracoes_preservando_a_posicao(self):
        text = ('O Sr. Silva assinou o contrato em 12/03/2021. A obra custou R$ 1.234,56; o prazo era de 30 dias.\n'
                'Quem pagou a obra? Fim.\nA empresa J. Prates Ltda. recebeu o valor!')
        claims = redacao.dividir(text)
        self.assertEqual([c['texto'] for c in claims], [
            'O Sr. Silva assinou o contrato em 12/03/2021.', 'A obra custou R$ 1.234,56;', 'o prazo era de 30 dias.',
            'A empresa J. Prates Ltda. recebeu o valor!'])
        self.assertEqual([c['tipo'] for c in claims], ['frase', 'oracao', 'oracao', 'frase'])
        for claim in claims:
            self.assertEqual(text[claim['inicio']:claim['fim']], claim['texto'])
        self.assertEqual(redacao.dividir(''), [])

    def test_cada_sinal_de_exagero(self):
        tipos = lambda claim, sources, **kw: [s['tipo'] for s in redacao.sinais(claim, sources, **kw)]
        self.assertEqual(tipos('A fonte declara valor 13.', ['A fonte declara valor 12.']), ['numero_divergente'])
        self.assertEqual(tipos('A fonte declara R$ 12 em 12/03/2021.', ['A fonte declara R$ 12,00 em 12/03/2021.']), [])
        self.assertEqual(tipos('A fonte declara valor de 12 kg.', ['A fonte declara valor de 12 t.']), ['numero_divergente'])
        self.assertEqual(tipos('Todos os contratos declaram valor 12.', ['O contrato declara valor 12.']),
                         ['quantificador_mais_forte'])
        self.assertEqual(tipos('Segundo a ata, a obra nunca parou.', ['Segundo a ata, a obra nunca parou.']), [])
        self.assertEqual(tipos('A ata declara que o atraso provocou a multa.', ['A ata declara atraso e multa.']),
                         ['causalidade_sem_suporte'])
        self.assertEqual(tipos('O valor é 12.', ['Segundo a prefeitura, o valor é 12.']), ['certeza_sem_atribuicao'])
        self.assertEqual(tipos('O valor é 12.', ['O valor é 12.'], atribuida=True), ['certeza_sem_atribuicao'])
        self.assertEqual(tipos('Segundo a prefeitura, o valor é 12.', ['Segundo a prefeitura, o valor é 12.']), [])
        self.assertEqual(tipos('Todos sempre pagaram 99.', ['']), [])  # sem trecho textual não há comparação
        signal = redacao.sinais('A fonte declara valor 13.', ['A fonte declara valor 12.'])[0]
        self.assertEqual((signal['trecho'], signal['posicao']), ('13', 22))


class ConferenciaRedacaoTest(Fontes, unittest.TestCase):
    def setUp(self):
        env, (_, _, _, second) = Ambiente.copia_completa(); self.addCleanup(env.cleanup)
        self.preparar(env, second)

    def test_afirmacao_sem_evidencia_fica_sem_suporte_e_vinculo_conferido_define_o_estado(self):
        record = self.criar('A fonte declara valor 12. O valor foi pago. Segundo a fonte, o valor é 14.')
        view = self.ver(record)
        self.assertEqual([c['estado'] for c in view['afirmacoes']], ['sem_suporte'] * 3)
        self.assertEqual(view['resumo']['por_estado']['sem_suporte'], 3)
        record = self.vincular(record, 0, [self.link(self.ia('E001'))])
        record = self.vincular(record, 1, [self.link(self.ia('E001'), suporte='parcial')])
        record = self.vincular(record, 2, [self.link(self.ia('E001'))])
        view = self.ver(record)
        first, second, third = view['afirmacoes']
        self.assertEqual((first['estado'], first['sinais']), ('suportada', []))
        self.assertEqual(first['evidencias'][0]['evidencia']['trecho'], 'A fonte declara valor 12.')
        self.assertEqual(second['estado'], 'suporte_parcial')
        self.assertEqual((third['estado'], [s['tipo'] for s in third['sinais']]), ('suporte_parcial', ['numero_divergente']))
        with self.assertRaisesRegex(ValueError, 'Nada mudou'):
            self.vincular(record, 0, [self.link(self.ia('E001'))])
        record = self.vincular(record, 0, [self.link(self.ia('E001'), natureza='alegacao_atribuida')])
        self.assertEqual(self.ver(record)['afirmacoes'][0]['estado'], 'suportada')
        # Evidência só de contexto não sustenta a afirmação.
        record = self.vincular(record, 0, [self.link(self.ia('E003'), papel='contexto', suporte='nao_revisado',
                                                     natureza='pendencia')])
        self.assertEqual(self.ver(record)['afirmacoes'][0]['estado'], 'sem_suporte')

    def test_revisao_humana_so_com_conta_autenticada(self):
        record = self.vincular(self.criar('A fonte declara valor 12. O valor foi pago.'), 0, [self.link(self.ia())])
        for conta in (None, {'id': '', 'nome': 'Sem id'}):
            with self.subTest(conta=conta), self.assertRaisesRegex(ValueError, '(?i)conta autenticada'):
                self.revisar(record, 0, conta=conta)
        self.assertEqual(len(redacao.detalhe(self.root, 'alpha', record['id'])['historico']), 2)
        with self.assertRaisesRegex(ValueError, 'não tem evidência de suporte'):
            self.revisar(record, 1)
        claim = record['estado']['afirmacoes'][0]
        body = self.base(id=record['id'], anterior_sha256=record['sha256'], afirmacao_id=claim['id'],
                         decisao='conferida_no_original', observacao_revisao='Conferi a linha 1 do original.')
        reviewed = redacao.revisar(self.root, body, CONTA)
        self.assertEqual(redacao.revisar(self.root, body, CONTA)['sha256'], reviewed['sha256'])  # idempotente
        event = reviewed['historico'][-1]
        self.assertEqual((event['conta_id'], event['autor'], event['origem_autoria']),
                         ('conta-revisora', 'Editora C', caderno.AUTORIA_CONTA))
        view = self.ver(reviewed)
        mark = view['afirmacoes'][0]['revisao_humana']
        self.assertEqual(view['afirmacoes'][0]['estado'], 'revisada_por_humano')
        self.assertEqual(view['afirmacoes'][0]['estado_automatico'], 'suportada')
        self.assertEqual((mark['conta_id'], mark['responsavel'], mark['decisao'], mark['em_utc']),
                         ('conta-revisora', 'Editora C', 'conferida_no_original', event['em_utc']))
        self.assertEqual(mark['observacao'], 'Conferi a linha 1 do original.')
        # O nome enviado pelo navegador não substitui o da conta.
        changed = self.revisar(reviewed, 1, decisao='sem_suporte_suficiente', autor='Outro nome')
        self.assertEqual(changed['historico'][-1]['autor'], 'Editora C')
        with self.assertRaisesRegex(ValueError, 'decisão'):
            self.revisar(changed, 0, decisao='pendente')

    def test_revisao_humana_forjada_e_recusada(self):
        record = self.vincular(self.criar('A fonte declara valor 12.'), 0, [self.link(self.ia())])
        claim = record['estado']['afirmacoes'][0]
        forged = {'afirmacao_id': claim['id'], 'decisao': 'conferida_no_original', 'observacao': '',
                  'conta_id': 'conta-revisora', 'responsavel': 'Editora C', 'sequencia': 3}
        # Sem conta, o próprio armazenamento recusa gravar o evento com revisão.
        with self.assertRaisesRegex(ValueError, 'conta autenticada'):
            redacao.COLECAO.salvar(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'], revisao=forged),
                                   'atualizar', None)
        # Com outra conta, a revisão que declara outra conta não sobrevive à leitura.
        redacao.COLECAO.salvar(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'], revisao=forged),
                               'atualizar', {'id': 'outra-conta', 'nome': 'Outra'})
        with self.assertRaisesRegex(ValueError, 'revisão humana sem ação de conta'):
            redacao.detalhe(self.root, 'alpha', record['id'])
        self.assertTrue(redacao.listar(self.root, 'alpha')[0]['divergente'])
        # As funções públicas não aceitam campos internos do cliente.
        with self.assertRaisesRegex(ValueError, 'Campos inválidos'):
            redacao.vincular(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'], revisao=forged))

    def test_nova_versao_preserva_historico_e_reabre_afirmacao_alterada(self):
        record = self.criar('A fonte declara valor 12. O valor foi pago em 2021. A obra parou.')
        record = self.vincular(record, 0, [self.link(self.ia())])
        record = self.vincular(record, 1, [self.link(self.ia('E002'), suporte='parcial')])
        record = self.revisar(record, 0)
        old = record['estado']['afirmacoes']
        new = redacao.nova_versao(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'],
                                                       texto='Nova abertura do texto. A fonte declara valor 12. '
                                                             'O valor foi pago em 2022.'))
        claims = new['estado']['afirmacoes']
        self.assertEqual(new['estado']['versao'], 2)
        self.assertEqual([c['texto'] for c in claims], ['Nova abertura do texto.', 'A fonte declara valor 12.',
                                                         'O valor foi pago em 2022.'])
        same, changed = claims[1], claims[2]
        self.assertEqual((same['id'], same['reaberta'], same['revisao_humana']['decisao']),
                         (old[0]['id'], False, 'conferida_no_original'))
        self.assertEqual(new['estado']['texto'][same['inicio']:same['fim']], same['texto'])
        self.assertNotEqual(changed['id'], old[1]['id'])
        self.assertEqual((changed['anterior_id'], changed['reaberta'], changed['revisao_humana'], changed['desde_versao']),
                         (old[1]['id'], True, None, 2))
        self.assertEqual(changed['evidencias'][0]['referencia']['evidencia_id'], 'E002')  # vínculo segue para conferência
        view = self.ver(new)
        self.assertEqual([c['estado'] for c in view['afirmacoes']], ['sem_suporte', 'revisada_por_humano', 'suporte_parcial'])
        self.assertEqual([v['versao'] for v in view['versoes']], [1, 2])
        self.assertEqual(view['resumo']['reabertas'], 1)
        history = redacao.detalhe(self.root, 'alpha', record['id'])['historico']
        self.assertEqual(history[0]['estado']['texto'], 'A fonte declara valor 12. O valor foi pago em 2021. A obra parou.')
        # Trocar a evidência de uma afirmação revisada também a reabre.
        relinked = self.vincular(new, 1, [self.link(self.ia(), suporte='parcial')])
        claim = relinked['estado']['afirmacoes'][1]
        self.assertEqual((claim['revisao_humana'], claim['reaberta']), (None, True))
        with self.assertRaisesRegex(ValueError, 'Nada mudou'):
            redacao.nova_versao(self.root, self.base(id=relinked['id'], anterior_sha256=relinked['sha256'],
                                                     texto=relinked['estado']['texto']))

    def test_outro_caso_nao_alcanca_o_texto(self):
        record = self.criar('A fonte declara valor 12.')
        self.env.caso('beta', indice=False)
        with self.assertRaisesRegex(ValueError, 'Registro não encontrado'):
            redacao.conferencia(self.root, 'beta', record['id'])
        beta = redacao.criar(self.root, self.base(caso='beta', titulo='Outro caso', texto='Texto de outro caso aqui.'))
        with self.assertRaisesRegex(ValueError, 'outra apuração'):
            redacao.vincular(self.root, {**self.base(caso='beta'), 'id': beta['id'], 'anterior_sha256': beta['sha256'],
                                         'afirmacao_id': beta['estado']['afirmacoes'][0]['id'],
                                         'evidencias': [self.link(self.ia())]})


class RotasRedacaoTest(Fontes, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ambiente, (_, _, _, second) = Ambiente.copia_completa()
        cls.ambiente.caso('beta', indice=False)
        cls.registros_classe = second

    @classmethod
    def tearDownClass(cls):
        cls.ambiente.cleanup()

    def setUp(self):
        self.preparar(self.ambiente, self.registros_classe)
        self.server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def post(self, op, data, token=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        headers = {'Content-Type': 'application/json', 'Origin': self.server.origin}
        if token is not False:
            headers['X-Session-Token'] = token or self.server.token
        con.request('POST', '/api/' + op, body=json.dumps(data), headers=headers)
        response = con.getresponse()
        result = response.status, json.loads(response.read() or b'{}')
        con.close()
        return result

    def ok(self, op, data):
        status, body = self.post(op, data)
        self.assertEqual(status, 200, (op, body))
        return body

    def erro(self, op, data, codigo):
        status, body = self.post(op, data)
        self.assertEqual((status, body.get('codigo')), (400, codigo), body)

    def test_fluxo_pela_mesa_e_revisao_recusada_sem_conta(self):
        created = self.ok('redacao-criar', self.base(titulo='Texto pela Mesa', texto='A fonte declara valor 12. O valor foi pago.'))
        claim = created['afirmacoes'][0]
        self.assertEqual((created['versao'], claim['estado']), (1, 'sem_suporte'))
        linked = self.ok('redacao-vincular', self.base(id=created['id'], anterior_sha256=created['sha256'],
                                                       afirmacao_id=claim['id'], evidencias=[self.link(self.ia())]))
        self.assertEqual(linked['afirmacoes'][0]['estado'], 'suportada')
        # Modo local: não há conta autenticada, então a Mesa não registra revisão humana.
        self.erro('redacao-revisar', self.base(id=linked['id'], anterior_sha256=linked['sha256'], afirmacao_id=claim['id'],
                                               decisao='conferida_no_original'), 'revisao_humana_sem_conta')
        listed = self.ok('redacao-listar', {'caso': 'alpha'})
        self.assertIn(created['id'], [t['id'] for t in listed['textos']])
        split = self.ok('redacao-dividir', {'caso': 'alpha', 'texto': 'Primeira frase aqui. Segunda frase também.'})
        self.assertEqual(len(split['afirmacoes']), 2)
        self.erro('redacao-conferir', {'caso': 'alpha', 'id': created['id'], 'caminho': '../x'}, 'quadro_campos_invalidos')
        self.erro('redacao-vincular', self.base(id=linked['id'], anterior_sha256=linked['sha256'], afirmacao_id='F' + '0' * 32,
                                                evidencias=[]), 'afirmacao_inexistente')

    def test_rota_recusa_outro_caso(self):
        created = self.ok('redacao-criar', self.base(titulo='Texto alpha', texto='A fonte declara valor 12.'))
        self.erro('redacao-conferir', {'caso': 'beta', 'id': created['id']}, 'registro_inexistente')
        self.erro('redacao-nova-versao', self.base(caso='beta', id=created['id'], anterior_sha256=created['sha256'],
                                                   texto='Outro texto qualquer aqui.'), 'registro_inexistente')
        self.assertNotIn(created['id'], json.dumps(self.ok('redacao-listar', {'caso': 'beta'})))
        self.erro('redacao-listar', {'caso': '../alpha'}, 'quadro_sem_caso')

    def test_recusa_sem_token(self):
        for op in rotas_redacao.OPERACOES:
            status, _ = self.post(op, {'caso': 'alpha'}, token=False)
            self.assertIn(status, (401, 403), op)


class RotasRedacaoContasTest(autorizacao.Http):
    """Modo hospedado: convidado nunca alcança a conferência; a conta de administrador registra a revisão."""

    def test_convidado_403_e_admin_revisa_com_a_propria_conta(self):
        for op in rotas_redacao.OPERACOES:
            status, body = self.post(self.ana, op, {'caso': 'alpha'})
            self.assertEqual((status, body.get('codigo')), (403, 'operacao_proibida'), op)
        status, created = self.post(self.admin, 'redacao-criar', {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex,
                                                                  'autor': 'Nome do navegador', 'titulo': 'Texto',
                                                                  'texto': 'O valor foi pago em 2021.'})
        self.assertEqual(status, 200, created)
        status, reviewed = self.post(self.admin, 'redacao-revisar', {
            'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Nome do navegador', 'id': created['id'],
            'anterior_sha256': created['sha256'], 'afirmacao_id': created['afirmacoes'][0]['id'],
            'decisao': 'precisa_de_ajuste', 'observacao_revisao': 'Falta a fonte do pagamento.'})
        self.assertEqual(status, 200, reviewed)
        mark = reviewed['afirmacoes'][0]['revisao_humana']
        self.assertEqual((reviewed['afirmacoes'][0]['estado'], mark['conta_id'], mark['responsavel'], mark['decisao']),
                         ('revisada_por_humano', self.admin_id, 'Editora', 'precisa_de_ajuste'))


if __name__ == '__main__':
    unittest.main()
