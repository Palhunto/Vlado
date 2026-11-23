"""Cenário de duas redações para os testes da matriz e do isolamento (contrato de contas, seção 5.17, item 5).

Não é um arquivo de teste: ``test_matriz_contas.py`` e ``test_isolamento_redacoes.py`` herdam de ``DuasRedacoes``.
Um servidor em modo ``piloto`` por classe, sobre uma pasta temporária com dados sintéticos; sem modelo e sem rede.

Redação Alfa: dona, editor, dois repórteres, leitor e convidado legado, com três apurações.

| Apuração | Responsável | Participam também            |
|----------|-------------|------------------------------|
| alpha    | repórter 1  | editor, leitor, convidado    |
| gama     | repórter 2  | repórter 1                   |
| delta    | repórter 2  | ninguém                      |

Assim cada papel tem as situações da seção 2.6: própria (P), de colega com inclusão (I), de colega sem inclusão (N).
Redação Beta Sentinela: dono e repórter, com a apuração ``beta`` (situação X para toda conta de Alfa). ``gama`` e
``beta`` têm o MESMO título, e todas têm os mesmos ids internos (D001). Cada apuração tem uma conversa da equipe
(``dono`` vazio); ``alpha`` e ``gama`` têm uma conversa de autor restrito do leitor, e ``alpha`` uma do convidado.
"""
from contextlib import ExitStack
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import fator_de_teste
import lixeira
import test_codex_integracao as integracao  # module import: its TestCase is not re-collected here
from agente_fluxo_fixture import encerrar_gerenciador
from codex_apuracao import Conversas
from comum import escrever_json
from criar_caso import criar_caso
from interface_pesquisa import Servidor
from modelo_pasta import copiar
from test_acesso import RAPIDO, SENHA

ORIGEM = 'https://vlado.test'
REDACAO_B = 'Redação Beta Sentinela'
CASOS_A, CASO_B = ('alpha', 'gama', 'delta'), 'beta'
# Onde cada papel de Alfa encontra cada situação (para a dona, P, I e N são iguais: ela alcança todas).
SITUACOES = {'dono': {'P': 'alpha', 'I': 'gama', 'N': 'delta', 'X': 'beta'},
             'editor': {'I': 'alpha', 'N': 'gama', 'X': 'beta'},
             'reporter': {'P': 'alpha', 'I': 'gama', 'N': 'delta', 'X': 'beta'},
             'leitor': {'I': 'alpha', 'N': 'gama', 'X': 'beta'},
             'convidado': {'I': 'alpha', 'N': 'gama', 'X': 'beta'}}
PASTAS_DE_DADOS = ('casos', 'execucoes', 'conversas', 'lixeira')
TABELAS_DE_CONTAS = ('organizacoes', 'contas', 'casos', 'participacoes', 'eventos', 'uso_diario')


def montar(root):
    """alpha e beta (do cenário de integração), mais gama, com o título de beta, e delta."""
    integracao.CodexIntegrationTest.montar(root)
    for caso, palavra, titulo in (('gama', 'Gamagamico', 'Caso sintético beta'), ('delta', 'Deltadeltico', 'Caso sintético delta')):
        arquivo = root / f'{caso}.txt'
        arquivo.write_text(f'{palavra} sintético. Valor 456.\n', encoding='utf-8')
        criar_caso(root, caso, titulo, [arquivo], 'sinteticos')


class DuasRedacoes(unittest.TestCase):
    """Server, newsrooms, accounts, conversations and one signed-in session per account, once per class."""

    @classmethod
    def setUpClass(cls):
        cls._pilha = ExitStack()
        cls.addClassCleanup(cls._pilha.close)
        temp, cls.root, _ = copiar('DuasRedacoes', montar)
        cls._pilha.callback(temp.cleanup)
        cls._pilha.enter_context(patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': '',
                                                         'VLADO_SEGREDOS': ''}))
        cls._pilha.enter_context(patch.object(acesso, '_HASHER', RAPIDO))
        acesso.limpar_limites()
        cls.manager = Conversas(cls.root, integracao.FakeServer)
        cls._pilha.callback(encerrar_gerenciador, cls.manager)
        cls.server = Servidor(('127.0.0.1', 0), cls.root, modo='piloto', origem=ORIGEM)
        cls.server.conversas.close()
        cls.server.conversas = cls.manager
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        cls._pilha.callback(lambda: (cls.server.shutdown(), cls.server.server_close(), thread.join(3)))
        cls.a = acesso.criar_redacao(cls.root, 'Redação Alfa')['id']
        cls.b = acesso.criar_redacao(cls.root, REDACAO_B)['id']
        for caso in CASOS_A:
            acesso.atribuir_caso(cls.root, caso, cls.a)
        acesso.atribuir_caso(cls.root, CASO_B, cls.b)
        cls.ids, cls.logins = {}, {}
        cls._pilha.callback(fator_de_teste.esquecer, cls.root)
        for chave, nome, login, papel, redacao, casos in (
                ('dono', 'Dona Alfa', 'dona.alfa', 'dono', cls.a, ()),
                ('editor', 'Edu Editor', 'edu.editor', 'editor', cls.a, ('alpha',)),
                ('reporter', 'Rita Reporter', 'rita.reporter', 'reporter', cls.a, ('alpha', 'gama')),
                ('reporter2', 'Rui Reporter', 'rui.reporter', 'reporter', cls.a, ('gama', 'delta')),
                ('leitor', 'Leo Leitor', 'leo.leitor', 'leitor', cls.a, ('alpha',)),
                ('convidado', 'Cora Convidada', 'cora.convidada', 'convidado', cls.a, ('alpha',)),
                ('dono_b', 'Dono Sentinela', 'dono.sentinela', 'dono', cls.b, ()),
                ('reporter_b', 'Reporter Sentinela', 'rep.sentinela', 'reporter', cls.b, ('beta',))):
            cls.ids[chave] = cls.conta(nome, login, papel, casos, redacao)
        for caso, responsavel, redacao in (('alpha', 'reporter', cls.a), ('gama', 'reporter2', cls.a),
                                           ('delta', 'reporter2', cls.a), ('beta', 'reporter_b', cls.b)):
            acesso.definir_responsavel(cls.root, caso, cls.ids[responsavel], 'operador', redacao)
        # Conversations: of the team in every case; of a restricted author (reader, guest) where they take part.
        cls.conversas = {}
        for caso in (*CASOS_A, CASO_B):
            cls.conversas['equipe', caso] = cls._conversa(caso, None)
        cls.conversas['leitor', 'alpha'] = cls._conversa('alpha', cls.ids['leitor'])
        cls.conversas['leitor', 'gama'] = cls._conversa('gama', cls.ids['leitor'])
        cls.conversas['convidado', 'alpha'] = cls._conversa('alpha', cls.ids['convidado'])
        cls.sessoes = {chave: cls._entrar(login) for chave, login in (
            ('dono', 'dona.alfa'), ('editor', 'edu.editor'), ('reporter', 'rita.reporter'), ('reporter2', 'rui.reporter'),
            ('leitor', 'leo.leitor'), ('convidado', 'cora.convidada'), ('dono_b', 'dono.sentinela'),
            ('reporter_b', 'rep.sentinela'))}
        # What must never reach an account of Alfa: names, logins, ids and content of the other newsroom.
        cls.sentinelas = (REDACAO_B, 'Betabetico', 'beta.txt', 'Dono Sentinela', 'dono.sentinela', 'Reporter Sentinela',
                          'rep.sentinela', cls.b, cls.ids['dono_b'], cls.ids['reporter_b'], cls.conversas['equipe', 'beta'])

    @classmethod
    def conta(cls, nome, login, papel, casos=(), redacao=None):
        """A new account with its password set; returns its id. Contract, 8.2: in the hosted mode dono and editor
        must have a second factor, or their session only reaches its enrolment. They enrol it here, as a person
        does, and `_entrar` signs them in in two steps."""
        conta, token = acesso.criar_conta(cls.root, nome, login, papel=papel, casos=list(casos),
                                          organizacao=redacao or cls.a, por='operador')
        acesso.ativar(cls.root, token, SENHA)
        cls.logins[login] = conta['id']
        if papel in acesso.FATOR_OBRIGATORIO:
            fator_de_teste.cadastrar(cls.root, conta['id'], SENHA)
        return conta['id']

    @classmethod
    def _conversa(cls, caso, dono):
        """A conversation that is not running, written as the manager writes it (identity only, no answer)."""
        identificador = uuid.uuid4().hex
        pasta = cls.root / 'conversas' / identificador
        (pasta / 'workspace').mkdir(parents=True)
        escrever_json(pasta / 'conversa.json', {
            'id': identificador, 'caso': caso, 'titulo': f'Conversa sintética de {caso}', 'corpus_id': f'{caso}_v1',
            'criada_em_utc': '2026-11-22T10:00:00+00:00', 'estado': 'pronto', 'thread_id': None, 'rodadas': [],
            'turn_id': None, 'modelo': None, 'dono': dono, 'politica': 'read-only; on-request; sem web/conectores/shell'})
        return identificador

    @classmethod
    def _entrar(cls, login):
        return fator_de_teste.entrar(cls.pedir, cls.root, cls.logins.get(login), login, SENHA, ORIGEM)

    @classmethod
    def pedir(cls, metodo, caminho, corpo=None, cabecalhos=None):
        con = http.client.HTTPConnection('127.0.0.1', cls.server.server_port, timeout=30)
        try:
            con.request(metodo, caminho, corpo, {'Host': 'vlado.test', **(cabecalhos or {})})
            resposta = con.getresponse()
            return resposta.status, dict(resposta.getheaders()), resposta.read()
        finally:
            con.close()

    def post(self, quem, operacao, dados):
        """(status, parsed body, raw body) of an operation called with the session of ``quem``."""
        cookie, csrf = self.sessoes[quem] if isinstance(quem, str) else quem
        status, _, corpo = self.pedir('POST', '/api/' + operacao, json.dumps(dados), {
            'Content-Type': 'application/json', 'Cookie': cookie, 'X-Session-Token': csrf, 'Origin': ORIGEM})
        try:
            return status, json.loads(corpo or b'{}'), corpo
        except ValueError:
            return status, {}, corpo

    def get(self, quem, caminho):
        cookie, _ = self.sessoes[quem] if isinstance(quem, str) else quem
        status, _, corpo = self.pedir('GET', caminho, cabecalhos={'Cookie': cookie})
        try:
            return status, json.loads(corpo or b'{}'), corpo
        except ValueError:
            return status, {}, corpo

    def cadastrar_fator(self, sessao):
        """The person of this session enrols her second factor through the server, as the page of the pending item
        does (contract, 8.2): what a test does for somebody it has just promoted to editor or to dono."""
        status, inicio, bruto = self.post(sessao, 'conta-fator-iniciar', {'senha': SENHA})
        assert status == 200, bruto[:200]
        status, _, bruto = self.post(sessao, 'conta-fator-confirmar', {'codigo': fator_de_teste.do_aplicativo(inicio['segredo'])})
        assert status == 200, bruto[:200]

    def item_na_lixeira(self, caso):
        """A fresh trash item of a case (a round that never ran: nothing of the case is hidden by it)."""
        return lixeira.adicionar(self.root, 'rodada', caso, 'R999', rodada='R999')['id']

    def retrato(self):
        """Hash of everything a refused request must leave alone: case data on disk and the accounts store."""
        resumo = hashlib.sha256()
        for pasta in PASTAS_DE_DADOS:
            base = self.root / pasta
            for arquivo in sorted(p for p in base.rglob('*') if p.is_file()) if base.is_dir() else []:
                resumo.update(arquivo.relative_to(self.root).as_posix().encode('utf-8'))
                resumo.update(arquivo.read_bytes())
        con = sqlite3.connect(acesso.caminho_bd(self.root))
        try:
            for tabela in TABELAS_DE_CONTAS:
                for linha in con.execute(f'SELECT * FROM {tabela} ORDER BY 1, 2'):
                    resumo.update(repr(tuple(linha)).encode('utf-8'))
        finally:
            con.close()
        return resumo.hexdigest()

    def sem_sentinela(self, corpo, onde=''):
        texto = corpo.decode('utf-8', 'replace')
        for sentinela in self.sentinelas:
            self.assertNotIn(sentinela, texto, f'vazou {sentinela!r} {onde}')
