"""A própria conta pelo servidor (``POST /api/conta-*``; contrato de contas, seções 5.4, 5.15 e 8.3).

Cada pessoa, em qualquer papel, vê o próprio perfil, muda nome e idioma, troca a senha (que pede a atual e encerra
as outras sessões) e vê e encerra as próprias sessões. Nada aqui aceita o id de outra conta, e a sessão de outra
conta responde como a que não existe. Duas redações no mesmo servidor em modo ``piloto`` (``cenario_redacoes``); as
regras do armazenamento estão em ``test_acesso.py``. Sem modelo e sem rede.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import autorizacao
import cenario_redacoes as cenario
import rotas_contas
from test_acesso import SENHA

ERRADA = 'senha-errada-de-teste'
FIREFOX_LINUX = 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0'
EDGE_WINDOWS = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 '
                'Safari/537.36 Edg/126.0.0.0')
HOSTIL = '<script>alert(1)</script> "Dono Sentinela"'


class ContaPropriaTest(cenario.DuasRedacoes):
    numero = 0

    def nova(self, papel='reporter', casos=('alpha',)):
        """A fresh account of Alfa: (id, login)."""
        type(self).numero += 1
        login = f'conta.nova{self.numero}'
        conta, token = acesso.criar_conta(self.root, f'Conta Nova {self.numero}', login, papel=papel, casos=list(casos),
                                          organizacao=self.a, por='operador')
        acesso.ativar(self.root, token, SENHA)
        return conta['id'], login

    def entrar(self, login, senha=SENHA, agente=None):
        """(status, session or None) of a sign-in with a browser header."""
        acesso.limpar_limites()
        status, headers, corpo = self.pedir('POST', '/api/entrar', json.dumps({'login': login, 'senha': senha}),
                                            {'Content-Type': 'application/json', 'Origin': cenario.ORIGEM,
                                             **({'User-Agent': agente} if agente else {})})
        return status, ((headers['Set-Cookie'].split(';')[0], json.loads(corpo)['csrf']) if status == 200 else None)

    def recusa(self, quem, operacao, dados, status, codigo):
        resposta = self.post(quem, operacao, dados)
        self.assertEqual((resposta[0], resposta[1].get('codigo')), (status, codigo), resposta[2][:200])
        return resposta

    # --- perfil ---------------------------------------------------------------------------------

    def test_cada_papel_ve_o_proprio_perfil_e_a_propria_redacao(self):
        for papel, nome in (('dono', 'Dona Alfa'), ('editor', 'Edu Editor'), ('reporter', 'Rita Reporter'),
                            ('leitor', 'Leo Leitor'), ('convidado', 'Cora Convidada')):
            with self.subTest(papel=papel):
                status, corpo, bruto = self.post(papel, 'conta-ver', {})
                self.assertEqual(status, 200, bruto[:200])
                self.assertEqual((corpo['conta']['id'], corpo['conta']['nome'], corpo['conta']['papel'], corpo['conta']['idioma']),
                                 (self.ids[papel], nome, papel, 'pt'))
                self.assertEqual(corpo['organizacao'], {'id': self.a, 'nome': 'Redação Alfa'})
                if papel in acesso.FATOR_OBRIGATORIO:
                    # Contract, 8.2: mandatory for dono and editor in the hosted mode; the scenario enrols it.
                    self.assertTrue(corpo['segundo_fator']['ativo'] and corpo['segundo_fator']['ativado_em'])
                    self.assertIn(corpo['segundo_fator']['codigos_restantes'], range(1, 11))
                else:
                    self.assertEqual(corpo['segundo_fator'], {'ativo': False, 'ativado_em': None, 'codigos_restantes': 0})
                self.assertRegex(corpo['sessao'], r'^[0-9a-f]{16}$')
                self.sem_sentinela(bruto)
                for segredo in ('senha_hash', '$argon2', self.sessoes[papel][0].split('=', 1)[1], self.sessoes[papel][1]):
                    self.assertNotIn(segredo, bruto.decode('utf-8'))
        self.assertEqual(self.post('dono_b', 'conta-ver', {})[1]['organizacao']['nome'], cenario.REDACAO_B)

    def test_a_pessoa_muda_so_o_proprio_nome_e_idioma(self):
        cid, login = self.nova('leitor')
        sessao = self.entrar(login)[1]
        status, corpo, _ = self.post(sessao, 'conta-atualizar', {'nome': 'Nome Trocado', 'idioma': 'en'})
        self.assertEqual((status, corpo['conta']['nome'], corpo['conta']['idioma']), (200, 'Nome Trocado', 'en'))
        self.assertEqual(self.get(sessao, '/api/sessao')[1]['conta']['nome'], 'Nome Trocado')
        vizinho = self.post('leitor', 'conta-ver', {})[1]['conta']
        for dados in ({'nome': 'Outro', 'papel': 'dono'}, {'nome': 'Outro', 'id': self.ids['leitor']},
                      {'nome': 'Outro', 'conta': self.ids['leitor']}, {'email': 'x@exemplo.org'}, {'organizacao': self.b},
                      {'nome': ''}, {'idioma': 'fr'}, {}):
            self.assertEqual(self.post(sessao, 'conta-atualizar', dados)[0], 400, dados)
        depois = self.post(sessao, 'conta-ver', {})[1]['conta']
        self.assertEqual((depois['id'], depois['nome'], depois['papel'], depois['email']), (cid, 'Nome Trocado', 'leitor', None))
        self.assertEqual(self.post('leitor', 'conta-ver', {})[1]['conta'], vizinho)  # nobody else was touched

    # --- senha ----------------------------------------------------------------------------------

    def test_trocar_a_senha_pede_a_atual_e_encerra_as_outras_sessoes(self):
        _, login = self.nova()
        aqui, outra = self.entrar(login)[1], self.entrar(login)[1]
        nova = 'outra-senha-longa-2'
        self.recusa(aqui, 'conta-senha-trocar', {'senha_nova': nova}, 403, 'senha_necessaria')
        self.recusa(aqui, 'conta-senha-trocar', {'senha_atual': ERRADA, 'senha_nova': nova}, 403, 'senha_atual_incorreta')
        self.assertEqual(self.post(aqui, 'conta-senha-trocar', {'senha_atual': SENHA, 'senha_nova': 'curta'})[0], 400)
        self.assertEqual(self.post(aqui, 'conta-senha-trocar', {'senha_atual': SENHA, 'senha_nova': nova, 'conta': self.ids['dono']})[0], 400)
        self.assertEqual(self.post(outra, 'codex-status', {})[0], 200)
        status, corpo, bruto = self.post(aqui, 'conta-senha-trocar', {'senha_atual': SENHA, 'senha_nova': nova})
        self.assertEqual((status, corpo), (200, {'estado': 'senha_trocada', 'sessoes_encerradas': 1}), bruto[:200])
        self.assertEqual(self.post(aqui, 'codex-status', {})[0], 200)   # the session that asked goes on
        self.assertEqual(self.post(outra, 'codex-status', {})[0], 401)  # the others ended
        self.assertEqual(self.entrar(login, SENHA)[0], 401)
        self.assertEqual(self.entrar(login, nova)[0], 200)
        self.assertEqual(self.post('dono', 'codex-status', {})[0], 200)  # and nobody else's

    def test_cinco_senhas_atuais_erradas_bloqueiam_a_troca(self):
        _, login = self.nova()
        sessao = self.entrar(login)[1]
        pedido = {'senha_atual': ERRADA, 'senha_nova': 'outra-senha-longa-2'}
        for _ in range(acesso.FALHAS_BLOQUEIO):
            self.recusa(sessao, 'conta-senha-trocar', pedido, 403, 'senha_atual_incorreta')
        self.recusa(sessao, 'conta-senha-trocar', {**pedido, 'senha_atual': SENHA}, 429, 'bloqueado')
        self.assertEqual(self.post(sessao, 'conta-ver', {})[0], 200)
        self.assertEqual(self.entrar(login, SENHA)[0], 200)  # the password was not changed, and signing in is another counter

    # --- sessões --------------------------------------------------------------------------------

    def test_lista_de_sessoes_tem_aparelho_data_e_endereco_e_nenhum_segredo(self):
        _, login = self.nova()
        aqui = self.entrar(login, agente=FIREFOX_LINUX)[1]
        outra = self.entrar(login, agente=EDGE_WINDOWS)[1]
        hostil = self.entrar(login, agente=HOSTIL)[1]
        status, corpo, bruto = self.post(aqui, 'conta-sessoes', {})
        self.assertEqual(status, 200, bruto[:200])
        self.assertEqual(sorted((s['aparelho'], s['atual']) for s in corpo['sessoes']),
                         [('Edge · Windows', False), ('Firefox · Linux', True), ('Navegador', False)])
        for sessao in corpo['sessoes']:
            self.assertEqual(set(sessao), {'id', 'aparelho', 'cliente', 'criada_em', 'ultimo_uso', 'expira_em', 'ip', 'ip_criacao', 'atual'})
            self.assertEqual((sessao['ip'], sessao['cliente']), ('127.0.0.1', 'web'))
        texto = bruto.decode('utf-8')
        for segredo in (*(s[0].split('=', 1)[1] for s in (aqui, outra, hostil)), aqui[1], outra[1], 'script', 'Sentinela'):
            self.assertNotIn(segredo, texto)  # never the cookie, the token or the header as the browser sent it
        self.assertEqual(self.post(aqui, 'conta-ver', {})[1]['sessao'], next(s['id'] for s in corpo['sessoes'] if s['atual']))
        self.assertEqual(self.post(aqui, 'conta-sessoes', {'conta': self.ids['dono']})[0], 400)  # no account is ever named

    def test_aparelho_sai_de_listas_fechadas(self):
        self.assertEqual(rotas_contas.aparelho(FIREFOX_LINUX), 'Firefox · Linux')
        self.assertEqual(rotas_contas.aparelho(EDGE_WINDOWS), 'Edge · Windows')
        self.assertEqual(rotas_contas.aparelho('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Version/17.5 Mobile/15E148 Safari/604.1'),
                         'Safari · iOS')
        self.assertEqual(rotas_contas.aparelho('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36'),
                         'Chrome · Android')
        self.assertEqual(rotas_contas.aparelho('qualquer coisa', 'android'), 'Aplicativo Android')
        for estranho in (HOSTIL, '', None, 5, 'x' * 5000, 'curl/8.5.0'):
            self.assertEqual(rotas_contas.aparelho(estranho), 'Navegador')

    def test_encerrar_uma_sessao_e_todas_as_outras_so_da_propria_conta(self):
        _, login = self.nova()
        aqui, segunda, terceira = (self.entrar(login)[1] for _ in range(3))
        do_dono = self.post('dono', 'conta-ver', {})[1]['sessao']
        ids = {s['id']: s['atual'] for s in self.post(aqui, 'conta-sessoes', {})[1]['sessoes']}
        atual = next(i for i, e in ids.items() if e)
        da_segunda = self.post(segunda, 'conta-ver', {})[1]['sessao']
        # Another account's session, of this newsroom or of the other one, is the session that does not exist.
        nao_existe = self.post(aqui, 'conta-sessao-encerrar', {'sessao': '0123456789abcdef'})
        self.assertEqual((nao_existe[0], nao_existe[1]['erro']), (400, 'Sessão não encontrada.'))
        for alheia in (do_dono, self.post('dono_b', 'conta-ver', {})[1]['sessao']):
            resposta = self.post(aqui, 'conta-sessao-encerrar', {'sessao': alheia})
            self.assertEqual((resposta[0], resposta[2]), (nao_existe[0], nao_existe[2]))
        self.assertEqual(self.post('dono', 'codex-status', {})[0], 200)
        self.assertEqual(self.post('dono_b', 'codex-status', {})[0], 200)
        self.assertEqual(self.post(aqui, 'conta-sessao-encerrar', {'sessao': atual})[0], 400)  # the one in use: sign out
        status, corpo, _ = self.post(aqui, 'conta-sessao-encerrar', {'sessao': da_segunda})
        self.assertEqual((status, len(corpo['sessoes'])), (200, 2))
        self.assertEqual(self.post(segunda, 'codex-status', {})[0], 401)  # ended on its next request
        self.assertEqual(self.post(terceira, 'codex-status', {})[0], 200)
        status, corpo, _ = self.post(aqui, 'conta-sessoes-encerrar-outras', {})
        self.assertEqual((status, corpo['encerradas'], [s['atual'] for s in corpo['sessoes']]), (200, 1, [True]))
        self.assertEqual(self.post(terceira, 'codex-status', {})[0], 401)
        self.assertEqual(self.post(aqui, 'codex-status', {})[0], 200)

    def test_quem_so_pergunta_tambem_cuida_da_propria_conta_e_de_mais_nada(self):
        for papel in ('leitor', 'convidado'):
            self.assertEqual(self.post(papel, 'conta-sessoes', {})[0], 200, papel)
            self.assertEqual(self.post(papel, 'equipe-listar', {})[0], 403, papel)
            self.assertEqual(set(autorizacao.capacidades(self.root, 'piloto', {'papel': papel}))
                             & {'equipe-listar', 'equipe-papel', 'contas-listar'}, set())


if __name__ == '__main__':
    unittest.main()
