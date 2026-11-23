"""Excluir a própria conta (``conta-excluir``; contrato de contas, seção 8.4 e entrega 4b-3).

O mesmo efeito de ``equipe-remover``: fica só o id, com a situação ``excluida``. A ordem é a combinada com o
Frontend: o nome digitado, depois o último dono, depois a senha; nome errado e exclusão impossível não gastam
tentativa. O sucesso encerra todas as sessões da conta e apaga os cookies da sessão e do aparelho. Nas saídas de
Contas, o autor excluído aparece como "Conta excluída" (``acesso.nome_publico``). Sem modelo e sem rede.
"""
import http.client
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
from cenario_redacoes import SENHA


class ExcluirTest(cenario.DuasRedacoes):
    _n = 0

    def nova(self, papel='reporter', redacao=None, nome=None):
        ExcluirTest._n += 1
        login = f'pessoa.exclui{ExcluirTest._n}'
        cid = self.conta(nome or f'Pessoa Exclui {ExcluirTest._n}', login, papel,
                         casos=[] if redacao else ['alpha'], redacao=redacao)
        acesso.limpar_limites()  # the per-address ceiling of sign-ins: this class signs in many times a minute
        return self._entrar(login), cid, login

    def excluir(self, sessao, dados):
        """(status, body, the Set-Cookie headers, every one of them)."""
        cookie, csrf = sessao
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        try:
            con.request('POST', '/api/conta-excluir', json.dumps(dados), {
                'Host': 'vlado.test', 'Content-Type': 'application/json', 'Cookie': cookie, 'X-Session-Token': csrf,
                'Origin': cenario.ORIGEM})
            resposta = con.getresponse()
            return resposta.status, json.loads(resposta.read() or b'{}'), resposta.msg.get_all('Set-Cookie') or []
        finally:
            con.close()

    def banco(self, sql, *args):
        con = sqlite3.connect(acesso.caminho_bd(self.root))
        con.row_factory = sqlite3.Row
        try:
            return [dict(linha) for linha in con.execute(sql, args)]
        finally:
            con.close()

    def tentativas(self, cid):
        return self.banco('SELECT * FROM tentativas WHERE chave = ?', acesso.CHAVE_CONFIRMACAO + cid)

    def test_exclui_encerra_tudo_e_fica_so_o_id(self):
        sessao, cid, login = self.nova(nome='Pessoa Que Sai')
        outra = self._entrar(login)  # a second browser of the same person
        self.assertEqual(self.post('dono', 'caso-participantes', {'caso': 'alpha'})[0], 200)
        status, corpo, cookies = self.excluir(sessao, {'nome': '  pessoa que SAI ', 'senha': SENHA})
        self.assertEqual((status, corpo), (200, {'estado': 'conta_excluida'}))
        self.assertEqual(sorted(c.split('=', 1)[0] for c in cookies), ['vlado_aparelho', 'vlado_sessao'])
        for cookie in cookies:
            self.assertRegex(cookie, r'^vlado_\w+=; ')
            self.assertIn('Max-Age=0', cookie)
            self.assertIn('Secure', cookie)
        for qual in (sessao, outra):  # every session of the account ended
            self.assertEqual(self.get(qual, '/api/sessao')[0], 401)
        conta = self.banco('SELECT * FROM contas WHERE id = ?', cid)[0]
        self.assertEqual((conta['nome'], conta['login'], conta['email'], conta['senha_hash'], conta['ativa']),
                         ('', None, None, None, 0))
        self.assertTrue(conta['excluida_em'])
        for tabela in ('sessoes', 'participacoes', 'aparelhos', 'fatores', 'codigos_reserva', 'links', 'entradas'):
            self.assertEqual(self.banco(f'SELECT * FROM {tabela} WHERE conta = ?', cid), [], tabela)
        status, _, _ = self.pedir('POST', '/api/entrar', json.dumps({'login': login, 'senha': SENHA}), {
            'Content-Type': 'application/json', 'Origin': cenario.ORIGEM})
        self.assertNotEqual(status, 200)
        # The newsroom's activity: the deletion, by the person, both shown as "Conta excluída" (decision 10).
        eventos = self.post('dono', 'equipe-atividade', {})[1]['eventos']
        evento = next(e for e in eventos if e['tipo'] == 'conta_excluida' and e['conta'] == cid)
        self.assertEqual((evento['por'], evento['conta_nome'], evento['por_nome']), (cid, 'Conta excluída', 'Conta excluída'))
        self.assertNotIn(cid, [p['id'] for p in self.post('dono', 'caso-participantes', {'caso': 'alpha'})[1]['participantes']])

    def test_nome_errado_vem_antes_e_nao_conta_como_senha_errada(self):
        sessao, cid, _ = self.nova(nome='Nome Certo')
        for nome in (None, '', 'Nome Errado', 'Nome  Certo', 7, 'Nome Certo' * 50):
            with self.subTest(nome=nome):
                dados = {'senha': 'senha-errada'} if nome is None else {'nome': nome, 'senha': 'senha-errada'}
                status, corpo, cookies = self.excluir(sessao, dados)
                self.assertEqual((status, corpo.get('codigo')), (400, 'nome_confirmacao_divergente'))
                self.assertEqual(cookies, [])
        self.assertEqual(self.tentativas(cid), [])
        for _ in range(4):  # four wrong passwords: one short of the block, so the names never counted
            self.assertEqual(self.excluir(sessao, {'nome': 'Nome Certo', 'senha': 'senha-errada'})[1]['codigo'],
                             'senha_atual_incorreta')
        self.assertEqual(self.excluir(sessao, {'nome': 'Nome Certo', 'senha': SENHA})[0], 200)

    def test_senha_ausente_errada_e_bloqueio(self):
        sessao, cid, _ = self.nova(nome='Pessoa Senha')
        status, corpo, _ = self.excluir(sessao, {'nome': 'Pessoa Senha'})
        self.assertEqual((status, corpo.get('codigo')), (403, 'senha_necessaria'))
        for _ in range(5):
            status, corpo, _ = self.excluir(sessao, {'nome': 'Pessoa Senha', 'senha': 'senha-errada'})
            self.assertEqual((status, corpo.get('codigo')), (403, 'senha_atual_incorreta'))
        status, corpo, _ = self.excluir(sessao, {'nome': 'Pessoa Senha', 'senha': SENHA})
        self.assertEqual((status, corpo.get('codigo')), (429, 'bloqueado'))
        self.assertIsNone(self.banco('SELECT excluida_em FROM contas WHERE id = ?', cid)[0]['excluida_em'])
        self.assertEqual(self.post(sessao, 'conta-excluir', {'nome': 'Pessoa Senha', 'senha': SENHA, 'conta': cid})[0], 400)

    def test_o_ultimo_dono_nao_se_exclui_e_nao_gasta_tentativa(self):
        redacao = acesso.criar_redacao(self.root, 'Redação Solitária')['id']
        sessao, cid, _ = self.nova('dono', redacao=redacao, nome='Dona Sozinha')
        for senha in ('senha-errada', SENHA, None):
            dados = {'nome': 'Dona Sozinha', **({'senha': senha} if senha else {})}
            status, corpo, _ = self.excluir(sessao, dados)
            self.assertEqual((status, corpo.get('codigo')), (400, 'ultimo_dono'), senha)
        self.assertEqual(self.tentativas(cid), [])
        # With a second active dono, the first one leaves.
        self.nova('dono', redacao=redacao, nome='Dona Que Fica')
        self.assertEqual(self.excluir(sessao, {'nome': 'Dona Sozinha', 'senha': SENHA})[0], 200)

    def test_com_termos_pendentes_sai_e_o_aceite_fica_sem_ip(self):
        sessao, cid, _ = self.nova('editor', nome='Editora Termos')
        with patch.dict(os.environ, {'VLADO_TERMOS_VERSAO': 'v-um', 'VLADO_TERMOS_ENDERECO': 'https://vlado.test/termos'}):
            self.assertEqual(self.post(sessao, 'conta-termos-aceitar', {'versao': 'v-um'})[0], 200)
        self.assertTrue(self.banco('SELECT ip FROM termos_aceites WHERE conta = ?', cid)[0]['ip'])
        with patch.dict(os.environ, {'VLADO_TERMOS_VERSAO': 'v-dois', 'VLADO_TERMOS_ENDERECO': 'https://vlado.test/termos'}):
            self.assertEqual(self.get(sessao, '/api/sessao')[1]['pendencias'], ['termos'])
            self.assertEqual(self.excluir(sessao, {'nome': 'Editora Termos', 'senha': SENHA})[0], 200)  # ressalva B2
        aceites = self.banco('SELECT versao, aceito_em, ip FROM termos_aceites WHERE conta = ?', cid)
        self.assertEqual([(a['versao'], a['ip']) for a in aceites], [('v-um', None)])  # P41 (b): id, version, date
        self.assertTrue(aceites[0]['aceito_em'])

    def test_com_o_fator_pendente_nao_sai(self):
        sessao, cid, _ = self.nova('editor', nome='Editor Sem Fator')
        acesso.remover_fator(self.root, cid, SENHA)
        status, corpo, cookies = self.excluir(sessao, {'nome': 'Editor Sem Fator', 'senha': SENHA})
        self.assertEqual((status, corpo.get('codigo'), cookies), (403, 'pendencia_de_conta', []))
        self.assertIsNone(self.banco('SELECT excluida_em FROM contas WHERE id = ?', cid)[0]['excluida_em'])


class NomePublicoTest(cenario.DuasRedacoes):
    def test_nome_conta_excluida_e_nada_de_outra_redacao(self):
        dono, dono_b = self.ids['dono'], self.ids['dono_b']
        cid = self.conta('Pessoa Removida', 'pessoa.removida', 'reporter', ['alpha'])
        acesso.remover(self.root, cid, dono, self.a, SENHA)
        self.assertEqual(acesso.nome_publico(self.root, dono), 'Dona Alfa')
        self.assertEqual(acesso.nome_publico(self.root, cid), acesso.CONTA_EXCLUIDA)
        self.assertEqual(acesso.nome_publico(self.root, cid, self.a), 'Conta excluída')
        self.assertIsNone(acesso.nome_publico(self.root, dono_b, self.a))  # never a name of the other newsroom
        self.assertIsNone(acesso.nome_publico(self.root, cid, self.b))
        for valor in ('manutencao', 'admin', None, 7, 'f' * 16):
            self.assertIsNone(acesso.nome_publico(self.root, valor), valor)
        self.assertEqual(acesso.nomes_publicos(self.root, [dono, cid, dono_b, 'operador'], self.a),
                         {dono: 'Dona Alfa', cid: 'Conta excluída'})


if __name__ == '__main__':
    unittest.main()
