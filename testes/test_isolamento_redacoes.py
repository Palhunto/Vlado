"""Travessia entre redações: o que a matriz não expressa (contrato de contas, seção 5.17, itens 6 e 7).

Duas redações no mesmo servidor (``cenario_redacoes``). As contas de Alfa usam os ids de verdade da Beta Sentinela
(apuração, conversa, item da lixeira, lote, conta) e precisam receber, byte a byte, a resposta de um id que não
existe; nenhuma listagem pode trazer nome, título, arquivo ou id da outra redação. Mais as invariantes: fora do modo
local ninguém tem "todas as apurações", apuração sem posse não é alcançada por ninguém e nenhuma rota lê o papel.
Sem modelo e sem rede.
"""
import base64
import json
from pathlib import Path
import re
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import autorizacao
import cenario_redacoes as cenario
import interface_pesquisa
from comum import escrever_json
from criar_caso import criar_caso
from test_acesso import SENHA

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
CONTAS_DE_ALFA = ('dono', 'editor', 'reporter', 'reporter2', 'leitor', 'convidado')
INEXISTENTE = 'apuracao_' + 'e' * 32


def do_cenario(ids):
    """Without the cases another test of this class created in the Mesa (their ids are chosen by the server)."""
    return sorted(i for i in ids if not i.startswith('apuracao_'))


class TravessiaTest(cenario.DuasRedacoes):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lotes = {caso: cls._lote(caso) for caso in ('alpha', 'beta')}
        cls.sentinelas = (*cls.sentinelas, cls.lotes['beta'])

    @classmethod
    def _lote(cls, caso):
        """A finished batch of the extraction queue, written as the queue writes it (state only, no file)."""
        lote = uuid.uuid4().hex
        pasta = cls.root / 'casos' / '.fila' / lote
        escrever_json(pasta / 'pedido.json', {'caso': caso, 'operacao': 'cadastrar', 'recebido_em_utc': '2026-11-22T10:00:00+00:00'})
        escrever_json(pasta / 'estado.json', {'lote': lote, 'estado': 'publicado', 'arquivos': [],
                                              'atualizado_em_utc': '2026-11-22T10:00:01+00:00',
                                              'recibo': {'arquivo_recibo': f'casos/{caso}/recibo.json', 'recebidos': 1}})
        return lote

    def igual_ao_inexistente(self, quem, operacao, com_id, com_inexistente):
        real, falso = self.post(quem, operacao, com_id), self.post(quem, operacao, com_inexistente)
        self.assertEqual((real[0], real[2]), (falso[0], falso[2]), f'{operacao} distingue o que existe em outra redação')
        self.assertGreaterEqual(real[0], 400)
        self.sem_sentinela(real[2], operacao)
        return real

    # --- listagens ------------------------------------------------------------------------------

    def test_catalogo_so_traz_o_alcance_de_cada_conta_mesmo_com_titulo_igual_na_outra_redacao(self):
        esperado = {'dono': ['alpha', 'delta', 'gama'], 'editor': ['alpha'], 'reporter': ['alpha', 'gama'],
                    'reporter2': ['delta', 'gama'], 'leitor': ['alpha'], 'convidado': ['alpha'], 'dono_b': ['beta'],
                    'reporter_b': ['beta']}
        for quem, casos in esperado.items():
            with self.subTest(quem=quem):
                status, corpo, bruto = self.get(quem, '/api/catalogo')
                self.assertEqual((status, do_cenario(c['id'] for c in corpo['casos'])), (200, casos))
                if quem in CONTAS_DE_ALFA:
                    self.sem_sentinela(bruto)
        titulos = {c['id']: c['titulo'] for c in self.get('dono', '/api/catalogo')[1]['casos']}
        self.assertEqual(titulos['gama'], self.get('dono_b', '/api/catalogo')[1]['casos'][0]['titulo'])  # same title, two newsrooms

    def test_gerenciar_listar_nao_traz_lixeira_nem_apuracao_da_outra_redacao(self):
        de_alfa, de_beta = self.item_na_lixeira('alpha'), self.item_na_lixeira('beta')
        status, corpo, bruto = self.post('dono', 'gerenciar-listar', {})
        self.assertEqual(status, 200, bruto[:200])
        self.assertEqual(do_cenario(c['id'] for c in corpo['casos']), ['alpha', 'delta', 'gama'])
        ids = {i['id'] for i in corpo['lixeira']}
        self.assertIn(de_alfa, ids)
        self.assertNotIn(de_beta, ids)
        self.assertTrue(all(i['caso'] in cenario.CASOS_A for i in corpo['lixeira']))
        self.sem_sentinela(bruto)
        self.assertNotIn(de_beta, bruto.decode('utf-8'))
        self.assertEqual({i['caso'] for i in self.post('dono_b', 'gerenciar-listar', {})[1]['lixeira']}, {'beta'})
        # The reporter who does not take part in alpha does not see alpha's trash either.
        self.assertNotIn(de_alfa, {i['id'] for i in self.post('reporter2', 'gerenciar-listar', {})[1]['lixeira']})

    def test_fila_so_mostra_lotes_ao_alcance_e_lote_de_outra_redacao_responde_como_inexistente(self):
        status, corpo, bruto = self.get('dono', '/api/fila')
        self.assertEqual((status, [l['lote'] for l in corpo['lotes'] if l['caso'] in cenario.CASOS_A]), (200, [self.lotes['alpha']]))
        self.assertTrue(all(l['caso'] != 'beta' for l in corpo['lotes']))
        self.assertNotIn('arquivo_recibo', bruto.decode('utf-8'))  # no path of the server in the receipt
        self.sem_sentinela(bruto)
        self.assertEqual(self.get('leitor', f'/api/fila?lote={self.lotes["alpha"]}')[1]['lote']['caso'], 'alpha')
        nao_existe = self.get('dono', '/api/fila?lote=' + 'e' * 32)
        for quem, lote in (('dono', 'beta'), ('reporter2', 'alpha'), ('convidado', 'beta')):
            with self.subTest(quem=quem, lote=lote):
                real = self.get(quem, f'/api/fila?lote={self.lotes[lote]}')
                self.assertEqual((real[0], real[2]), (nao_existe[0], nao_existe[2]))
                self.assertEqual(real[0], 400)
        self.assertEqual(self.get('dono', '/api/fila?caso=beta')[0], 404)
        self.assertEqual(self.get('dono', '/api/fila?caso=beta')[2], self.get('dono', f'/api/fila?caso={INEXISTENTE}')[2])
        self.assertEqual([l['lote'] for l in self.get('dono_b', '/api/fila')[1]['lotes']], [self.lotes['beta']])

    def test_contas_e_eventos_listados_sao_so_os_da_propria_redacao(self):
        status, corpo, bruto = self.post('dono', 'equipe-listar', {})
        self.assertEqual(status, 200)
        self.assertEqual({c['login'] for c in corpo['pessoas']},
                         {'dona.alfa', 'edu.editor', 'rita.reporter', 'rui.reporter', 'leo.leitor', 'cora.convidada'})
        self.assertEqual({c['papel'] for c in corpo['pessoas']}, {'dono', 'editor', 'reporter', 'leitor', 'convidado'})
        self.sem_sentinela(bruto)
        status, atividade, bruto = self.post('dono', 'equipe-atividade', {'limite': 200})
        self.assertEqual(status, 200)
        self.assertFalse({self.ids['dono_b'], self.ids['reporter_b']} & {e['conta'] for e in atividade['eventos']})
        self.sem_sentinela(bruto)
        self.assertEqual({c['login'] for c in self.post('dono_b', 'equipe-listar', {})[1]['pessoas']},
                         {'dono.sentinela', 'rep.sentinela'})

    # --- cada resolvedor com id da outra redação -------------------------------------------------

    def test_as_cinco_causas_de_caso_indisponivel_respondem_igual_byte_a_byte(self):
        arquivo = self.root / 'orfa.txt'
        arquivo.write_text('Orfanato sintético.\n', encoding='utf-8')
        criar_caso(self.root, 'orfa', 'Caso sem posse', [arquivo], 'sinteticos')  # created at the terminal: no ownership
        self.assertIsNone(acesso.posse(self.root, 'orfa'))
        referencia = self.post('editor', 'analises', {'caso': INEXISTENTE})
        self.assertEqual((referencia[0], referencia[1]),
                         (404, {'estado': 'indisponivel', 'codigo': 'caso_indisponivel',
                                'erro': 'Apuração indisponível para esta conta.'}))
        causas = {'outra redação': 'beta', 'sem participação': 'gama', 'sem posse': 'orfa', 'id malformado': '../beta',
                  'id que não é texto': 123, 'id vazio': '', 'sem id': None}
        for operacao in ('analises', 'apuracao-notas', 'original', 'achados-revisao-salvar', 'caso-participantes',
                         'rascunhos-listar', 'codex-listar', 'codex-perguntar'):
            for causa, caso in causas.items():
                with self.subTest(operacao=operacao, causa=causa):
                    resposta = self.post('editor', operacao, {'caso': caso, 'pergunta': 'x'} if operacao == 'codex-perguntar'
                                         else {'caso': caso})
                    self.assertEqual((resposta[0], resposta[2]), (referencia[0], referencia[2]))
        for quem in CONTAS_DE_ALFA:  # nobody reaches the case without ownership, not even the dono
            self.assertEqual(self.post(quem, 'codex-listar', {'caso': 'orfa'})[2], referencia[2], quem)
        self.assertEqual(self.post('dono_b', 'codex-listar', {'caso': 'orfa'})[2], referencia[2])

    def test_conversa_de_outra_redacao_responde_como_conversa_inexistente(self):
        de_beta = self.conversas['equipe', 'beta']
        for quem in ('dono', 'reporter', 'leitor', 'convidado'):
            for operacao in ('codex-eventos', 'codex-cancelar', 'codex-retomar', 'codex-original'):
                with self.subTest(quem=quem, operacao=operacao):
                    extra = {} if operacao == 'codex-retomar' else {'referencia': '0' * 64} if operacao == 'codex-original' else {}
                    real = self.igual_ao_inexistente(quem, operacao, {'conversa': de_beta, **extra}, {'conversa': 'e' * 32, **extra})
                    self.assertEqual((real[0], real[1]['codigo']), (400, 'conversa_indisponivel'))

    def test_conversa_de_uma_apuracao_nao_serve_em_outra_nem_para_mandar_a_lixeira(self):
        de_gama, de_beta = self.conversas['equipe', 'gama'], self.conversas['equipe', 'beta']
        for conversa in (de_gama, de_beta, 'e' * 32):
            with self.subTest(conversa=conversa[:6]):
                excluir = self.post('dono', 'excluir', {'tipo': 'conversa', 'caso': 'alpha', 'conversa': conversa})
                self.assertEqual((excluir[0], excluir[1]['codigo']), (400, 'conversa_indisponivel'))
                perguntar = self.post('dono', 'codex-perguntar', {'caso': 'alpha', 'pergunta': 'x', 'conversa': conversa})
                self.assertEqual((perguntar[0], perguntar[2]), (excluir[0], excluir[2]))
        self.assertTrue((self.root / 'conversas' / de_beta / 'conversa.json').is_file())
        self.assertEqual(self.get('dono_b', '/api/catalogo')[0], 200)

    def test_item_da_lixeira_de_outra_redacao_responde_como_item_inexistente_e_continua_la(self):
        de_beta = self.item_na_lixeira('beta')
        for operacao, extra in (('restaurar', {}), ('lixeira-alcance', {}), ('lixeira-apagar', {'nome': 'R999', 'confirmacao': 'x'})):
            with self.subTest(operacao=operacao):
                self.igual_ao_inexistente('dono', operacao, {'item': de_beta, **extra}, {'item': 'e' * 32, **extra})
        self.assertIn(de_beta, {i['id'] for i in self.post('dono_b', 'gerenciar-listar', {})[1]['lixeira']})
        self.assertEqual(self.post('dono_b', 'restaurar', {'item': de_beta})[0], 200)  # and its owner still restores it

    def test_referencia_de_evidencia_de_outra_apuracao_dentro_de_um_corpo_valido_e_recusada(self):
        referencia = {'tipo': 'humana', 'caso_id': 'beta', 'registro_id': 'N' + '0' * 32, 'sha256': '0' * 64, 'fonte': 0}
        status, corpo, bruto = self.post('dono', 'comparar-evidencias', {'caso': 'alpha', 'a': referencia, 'b': referencia})
        self.assertEqual(status, 400, bruto[:200])
        self.sem_sentinela(bruto)
        status, _, bruto = self.post('dono', 'comparar-documentos', {'caso': 'alpha', 'rodada': 'R001', 'documento_a': 'D001',
                                                                     'documento_b': 'D001'})
        self.sem_sentinela(bruto)

    def test_conta_de_outra_redacao_responde_como_conta_inexistente_na_equipe(self):
        de_beta, nao_existe = self.ids['reporter_b'], '0123456789abcdef'
        antes = self.post('dono', 'caso-participantes', {'caso': 'alpha'})[1]
        for operacao in ('caso-incluir', 'caso-retirar', 'caso-responsavel'):
            with self.subTest(operacao=operacao):
                real = self.igual_ao_inexistente('dono', operacao, {'caso': 'alpha', 'conta': de_beta},
                                                 {'caso': 'alpha', 'conta': nao_existe})
                self.assertEqual(real[1]['erro'], 'Conta não encontrada.')
        for operacao, extra in (('equipe-papel', {'papel': 'leitor'}), ('equipe-desativar', {}), ('equipe-reativar', {}),
                                ('equipe-teto', {'teto_brl': '10'}), ('equipe-remover', {'senha': SENHA})):
            with self.subTest(operacao=operacao):
                real = self.igual_ao_inexistente('dono', operacao, {'conta': de_beta, **extra}, {'conta': nao_existe, **extra})
                self.assertEqual(real[1]['erro'], 'Conta não encontrada.')
        self.assertEqual(self.post('dono', 'caso-participantes', {'caso': 'alpha'})[1], antes)
        self.assertEqual(self.post('reporter_b', 'codex-status', {})[0], 200)  # still active, same session, same name
        self.assertEqual(self.get('reporter_b', '/api/sessao')[1]['conta']['nome'], 'Reporter Sentinela')
        # Cases of the other newsroom cannot be given to anybody, and the refusal is the one of a case that does not exist.
        self.igual_ao_inexistente('dono', 'equipe-convidar', {'email': 'nova@exemplo.test', 'papel': 'leitor', 'casos': ['beta']},
                                  {'email': 'nova@exemplo.test', 'papel': 'leitor', 'casos': [INEXISTENTE]})
        self.igual_ao_inexistente('dono', 'caso-incluir', {'caso': 'beta', 'conta': self.ids['leitor']},
                                  {'caso': INEXISTENTE, 'conta': self.ids['leitor']})
        self.assertEqual(self.post('dono', 'equipe-listar', {})[1]['convites'], [])

    def test_email_de_outra_redacao_nao_e_confirmado_por_nenhuma_operacao_de_contas(self):
        # The e-mail is unique in the installation: "this address already has an account" would tell Alfa that Beta
        # has it. An invitation and a change of the own e-mail answer the same for an address of Beta and a free one.
        _, token, _ = acesso.convidar(self.root, self.b, self.ids['dono_b'], 'pessoa@sentinela.example', 'leitor', ['beta'])
        acesso.aceitar_convite(self.root, token, 'Pessoa Sentinela', SENHA)
        respostas = {}
        for rotulo, email in (('de Beta', 'pessoa@sentinela.example'), ('livre', 'livre@exemplo.test')):
            convite = self.post('dono', 'equipe-convidar', {'email': email, 'papel': 'leitor', 'casos': ['alpha']})
            self.sem_sentinela(convite[2].replace(email.encode('utf-8'), b''), f'equipe-convidar {rotulo}')
            respostas[rotulo] = (convite[0], set(convite[1]), set(convite[1]['convite']),
                                 {k: v for k, v in convite[1]['convite'].items() if k in ('papel', 'casos', 'estado', 'envio')})
        self.assertEqual(respostas['de Beta'], respostas['livre'], 'a resposta do convite depende de o e-mail ter conta em outra redação')
        self.assertEqual(respostas['livre'][0], 200)
        pendentes = {c['email'] for c in self.post('dono', 'equipe-listar', {})[1]['convites']}
        self.assertLessEqual({'pessoa@sentinela.example', 'livre@exemplo.test'}, pendentes)  # both listed alike
        trocas = {rotulo: self.post('leitor' if rotulo == 'de Beta' else 'editor', 'conta-email-trocar', {'email': email, 'senha': SENHA})
                  for rotulo, email in (('de Beta', 'pessoa@sentinela.example'), ('livre', 'outro.livre@exemplo.test'))}
        self.assertEqual({r: (t[0], set(t[1]), t[1]['estado']) for r, t in trocas.items()}['de Beta'],
                         (trocas['livre'][0], set(trocas['livre'][1]), trocas['livre'][1]['estado']))
        self.assertEqual(acesso.organizacao_da_conta(self.root, self.ids['dono_b']), self.b)
        for convite in self.post('dono', 'equipe-listar', {})[1]['convites']:  # leave the scenario as it was
            self.post('dono', 'equipe-convite-cancelar', {'convite': convite['id']})
        self.assertEqual(self.post('dono_b', 'codex-status', {})[0], 200)

    def test_mesmos_ids_internos_nas_duas_redacoes_nao_se_misturam(self):
        nota = {'requisicao_id': 'a' * 32, 'titulo': 'Nota', 'texto': 'Texto.'}
        de_beta = self.post('dono_b', 'apuracao-nota-salvar', {'caso': 'beta', **nota, 'texto': 'Anotação Betabetico reservada.'})
        de_alfa = self.post('dono', 'apuracao-nota-salvar', {'caso': 'alpha', **nota, 'texto': 'Anotação de Alfa.'})
        self.assertEqual((de_beta[0], de_alfa[0]), (200, 200), (de_beta[2][:200], de_alfa[2][:200]))
        self.assertEqual(de_alfa[1]['nota']['id'], de_beta[1]['nota']['id'])  # the same internal id in two cases
        lida = self.post('editor', 'apuracao-nota', {'caso': 'alpha', 'nota_id': de_alfa[1]['nota']['id']})
        self.sem_sentinela(lida[2])
        self.sem_sentinela(self.post('editor', 'apuracao-notas', {'caso': 'alpha'})[2])
        da_dona = self.post('dono', 'apuracao-nota', {'caso': 'alpha', 'nota_id': de_alfa[1]['nota']['id']})[2].decode('utf-8')
        self.assertIn('Anotação de Alfa.', da_dona)
        do_dono_b = self.post('dono_b', 'apuracao-nota', {'caso': 'beta', 'nota_id': de_beta[1]['nota']['id']})[2].decode('utf-8')
        self.assertIn('Betabetico', do_dono_b)  # each one reads its own, under the same id
        self.assertEqual(de_alfa[1]['nota']['criado_por']['nome'], 'Dona Alfa')

    # --- criação, lixeira, suspensão -------------------------------------------------------------

    def test_apuracao_nova_tem_id_do_servidor_e_posse_de_quem_cria(self):
        arquivo = {'nome': 'novo.txt', 'base64': base64.b64encode('Texto sintético novo.\n'.encode('utf-8')).decode('ascii')}
        pedido = {'novo': True, 'titulo': 'Apuração nova sintética', 'natureza': 'sinteticos', 'arquivos': [arquivo]}
        posses = lambda: len(acesso.listar_redacoes(self.root)) and sum(r['apuracoes'] for r in acesso.listar_redacoes(self.root))  # noqa: E731
        antes = posses()
        escolhido = self.post('reporter', 'cadastrar', {**pedido, 'caso': 'beta'})
        self.assertEqual((escolhido[0], escolhido[1]['codigo']), (403, 'campos_nao_permitidos'))
        self.assertEqual(self.post('reporter', 'cadastrar', {**pedido, 'caso': 'meu_id'})[2], escolhido[2])  # no oracle
        self.assertEqual(self.post('reporter', 'cadastrar', {'novo': True})[0], 400)  # refused by the route: nothing left
        self.assertEqual(posses(), antes)
        for quem in ('editor', 'leitor', 'convidado'):
            self.assertEqual(self.post(quem, 'cadastrar', pedido)[0], 403, quem)
        conhecidas = {c['id'] for c in self.get('reporter', '/api/catalogo')[1]['casos']}
        status, _, bruto = self.post('reporter', 'cadastrar', pedido)
        self.assertEqual(status, 200, bruto[:300])
        (nova,) = {c['id'] for c in self.get('reporter', '/api/catalogo')[1]['casos']} - conhecidas
        self.assertIn(nova, bruto.decode('utf-8'))  # the receipt names the case the server created
        self.assertRegex(nova, r'^apuracao_[0-9a-f]{32}$')
        registro = acesso.posse(self.root, nova)
        self.assertEqual((registro['organizacao'], registro['responsavel'], registro['origem']), (self.a, self.ids['reporter'], 'mesa'))
        self.assertIn(nova, {c['id'] for c in self.get('reporter', '/api/catalogo')[1]['casos']})
        self.assertIn(nova, {c['id'] for c in self.get('dono', '/api/catalogo')[1]['casos']})
        for quem in ('editor', 'reporter2', 'dono_b'):
            self.assertNotIn(nova, {c['id'] for c in self.get(quem, '/api/catalogo')[1]['casos']}, quem)
            self.assertEqual(self.post(quem, 'analises', {'caso': nova})[0], 404, quem)
        self.assertEqual(self.post('reporter', 'analises', {'caso': nova})[0], 200)

    def test_na_lixeira_posse_e_alcance_continuam_e_quem_nao_alcanca_nao_percebe_nada(self):
        fora = self.post('editor', 'analises', {'caso': INEXISTENTE})
        excluido = self.post('reporter2', 'excluir', {'tipo': 'caso', 'caso': 'delta'})
        self.assertEqual(excluido[0], 200, excluido[2][:200])
        item = excluido[1]['item']['id']
        try:
            self.assertEqual(acesso.posse(self.root, 'delta')['responsavel'], self.ids['reporter2'])
            self.assertIn('delta', self.get('reporter2', '/api/sessao')[1]['conta']['casos'])  # still within reach
            self.assertNotIn('delta', {c['id'] for c in self.get('dono', '/api/catalogo')[1]['casos']})
            for operacao in ('analises', 'apuracao-notas', 'caso-participantes', 'codex-listar', 'rascunhos-listar'):
                with self.subTest(operacao=operacao):
                    dentro = self.post('reporter2', operacao, {'caso': 'delta'})  # reaches it: told it is in the trash
                    self.assertEqual(dentro[0], 400, dentro[2][:200])
                    self.assertIn('lixeira', dentro[1]['erro'])
                    for quem in ('editor', 'reporter', 'dono_b'):  # does not reach it: the answer of always
                        resposta = self.post(quem, operacao, {'caso': 'delta'})
                        self.assertEqual((resposta[0], resposta[2]), (fora[0], fora[2]), quem)
            self.assertIn(item, {i['id'] for i in self.post('dono', 'gerenciar-listar', {})[1]['lixeira']})
            self.assertIn(item, {i['id'] for i in self.post('reporter2', 'gerenciar-listar', {})[1]['lixeira']})
            self.assertNotIn(item, {i['id'] for i in self.post('reporter', 'gerenciar-listar', {})[1]['lixeira']})
            nao_existe = self.post('reporter', 'restaurar', {'item': 'e' * 32})
            self.assertEqual(self.post('reporter', 'restaurar', {'item': item})[2], nao_existe[2])  # a colleague out of the case
            self.assertEqual(self.post('editor', 'restaurar', {'item': item})[0], 403)
        finally:
            self.assertEqual(self.post('reporter2', 'restaurar', {'item': item})[0], 200)  # who answers for it restores
        self.assertEqual(self.post('reporter2', 'analises', {'caso': 'delta'})[0], 200)

    def test_redacao_suspensa_nao_opera_e_a_outra_nem_percebe(self):
        acesso.definir_situacao_redacao(self.root, self.b, 'suspensa')
        try:
            for operacao, dados in (('codex-status', {}), ('analises', {'caso': 'beta'}), ('equipe-listar', {})):
                status, corpo, _ = self.post('dono_b', operacao, dados)
                self.assertEqual((status, corpo.get('codigo')), (403, 'redacao_suspensa'), operacao)
            self.assertEqual(self.get('dono_b', '/api/catalogo')[0], 403)
            # Nor the page, the session or the server's capabilities: nobody of a suspended newsroom operates.
            for caminho in ('/api/sessao', '/api/integracao', '/api/cota', '/api/fila'):
                status, corpo, _ = self.get('reporter_b', caminho)
                self.assertEqual((status, corpo.get('codigo')), (403, 'redacao_suspensa'), caminho)
            status, cabecalhos, pagina = self.pedir('GET', '/', cabecalhos={'Cookie': self.sessoes['dono_b'][0]})
            self.assertEqual((status, cabecalhos['Content-Type']), (403, 'text/html; charset=utf-8'))
            self.assertIn('suspensa', pagina.decode('utf-8'))
            for segredo in (self.sessoes['dono_b'][1], cenario.REDACAO_B, 'Dono Sentinela', 'data-papel'):
                self.assertNotIn(segredo, pagina.decode('utf-8'))  # a plain notice: no token, no name, no application
            acesso.limpar_limites()
            descartavel = self._entrar('rep.sentinela')  # signing in still works, and so does signing out
            self.assertEqual(self.post(descartavel, 'sessao-sair', {})[0], 200)
            self.assertEqual(self.get('dono', '/api/sessao')[0], 200)  # the other newsroom goes on
            self.assertEqual(self.pedir('GET', '/', cabecalhos={'Cookie': self.sessoes['dono'][0]})[0], 200)
            self.assertEqual(self.post('dono', 'analises', {'caso': 'alpha'})[0], 200)
            self.assertEqual(self.post('dono', 'analises', {'caso': 'beta'})[2], self.post('dono', 'analises', {'caso': INEXISTENTE})[2])
        finally:
            acesso.definir_situacao_redacao(self.root, self.b, 'ativa')
        self.assertEqual(self.post('dono_b', 'analises', {'caso': 'beta'})[0], 200)
        self.assertEqual((self.get('dono_b', '/api/sessao')[0], self.get('dono_b', '/api/integracao')[0]), (200, 200))

    def test_configuracao_do_servidor_nao_vai_com_caminhos(self):
        status, corpo, bruto = self.post('dono', 'ambiente', {})
        self.assertEqual(status, 200)
        self.assertNotIn('python', corpo)
        self.assertNotIn(str(self.root), bruto.decode('utf-8'))

    # --- invariantes -----------------------------------------------------------------------------

    def test_fora_do_modo_local_ninguem_tem_todas_as_apuracoes(self):
        for quem in self.sessoes:
            sid = self.sessoes[quem][0].split('=', 1)[1]
            principal = acesso.sessao(self.root, sid)
            self.assertIsInstance(principal['casos'], list, quem)
            self.assertIsNotNone(principal['organizacao'], quem)
            self.assertLessEqual(set(principal['responsavel_de']), set(principal['casos']), quem)
        principal = acesso.sessao(self.root, self.sessoes['dono'][0].split('=', 1)[1])
        for defeituoso in ({**principal, 'casos': None}, {**principal, 'papel': 'admin'}, {**principal, 'conta': None}):
            with self.assertRaises(autorizacao.Recusa) as recusa:  # a principal like this is a defect: it does not pass
                autorizacao.conferir(self.root, 'piloto', defeituoso, 'analises', {'caso': 'alpha'})
            self.assertEqual(recusa.exception.status, 503)

    def test_se_o_portao_falhar_a_segunda_conferencia_ainda_recusa(self):
        with self.assertRaisesRegex(ValueError, 'não liberada'):
            interface_pesquisa.executar(self.root, 'analises', {'caso': 'beta'}, casos=['alpha'])
        with self.assertRaisesRegex(ValueError, 'não liberada'):
            interface_pesquisa.executar(self.root, 'apuracao-notas', {'caso': 'beta'}, casos=['alpha', 'gama'])
        with self.assertRaises(ValueError):
            self.manager.eventos(self.conversas['equipe', 'beta'], casos=['alpha'])

    def test_operacao_que_nao_esta_na_matriz_nao_existe(self):
        self.assertEqual(self.post('dono', 'acesso-listar', {})[0], 404)
        self.assertEqual(self.post('dono', 'conta-excluir', {})[0], 404)  # defined by the contract, not delivered yet
        with self.assertRaises(autorizacao.Recusa) as recusa:
            autorizacao.conferir(self.root, 'piloto', acesso.sessao(self.root, self.sessoes['dono'][0].split('=', 1)[1]),
                                 'operacao-nova-sem-linha', {})
        self.assertEqual(recusa.exception.status, 404)


class RotasNaoLeemOPapelTest(unittest.TestCase):
    """Static check: the routes ask the gate; they never decide by the role of who calls."""

    LEITURA_DO_PAPEL = re.compile(r"""(principal|conta|sessao)\s*(\[\s*['"]papel['"]\s*\]|\.get\(\s*['"]papel['"])""")

    def test_nenhum_modulo_de_rota_le_o_papel_de_quem_chama(self):
        arquivos = [*sorted(SCRIPTS.glob('rotas_*.py')), SCRIPTS / 'interface_pesquisa.py']
        self.assertGreaterEqual(len(arquivos), 12)
        for arquivo in arquivos:
            for numero, linha in enumerate(arquivo.read_text(encoding='utf-8').splitlines(), 1):
                self.assertIsNone(self.LEITURA_DO_PAPEL.search(linha), f'{arquivo.name}:{numero}: {linha.strip()}')

    def test_o_local_e_o_unico_modo_em_que_casos_pode_ser_nenhum(self):
        fonte = (SCRIPTS / 'rotas_contas.py').read_text(encoding='utf-8')
        self.assertEqual(fonte.count("'casos': None"), 1)  # the single operator of the local mode
        local = {'papel': 'dono', 'conta': None, 'casos': None, 'organizacao': None}
        concedido = autorizacao.conferir(Path('.'), 'local', local, 'analises', {'caso': 'qualquer'})
        self.assertEqual((concedido.caso, concedido.restrito, concedido.dono), ('qualquer', False, None))
        for operacao in ('caso-participantes', 'conta-ver', 'conta-senha-trocar', 'equipe-listar',
                         'equipe-remover'):  # accounts, newsrooms and teams do not exist in the local mode
            with self.assertRaises(autorizacao.Recusa):
                autorizacao.conferir(Path('.'), 'local', local, operacao, {})


if __name__ == '__main__':
    unittest.main()
