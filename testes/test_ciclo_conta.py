"""Ciclo de vida da conta (contrato de contas, seção 8.4): excluir a própria conta (``conta-excluir``, entrega 4b-3)
e as contas inativas da varredura diária (``acesso.manutencao``, entrega 4b-4).

O mesmo efeito de ``equipe-remover``: fica só o id, com a situação ``excluida``. A ordem é a combinada com o
Frontend: o nome digitado, depois o último dono, depois a senha; nome errado e exclusão impossível não gastam
tentativa. O sucesso encerra todas as sessões da conta e apaga os cookies da sessão e do aparelho. Nas saídas de
Contas, o autor excluído aparece como "Conta excluída" (``acesso.nome_publico``).

Inativas: 180 dias sem entrar geram um aviso por e-mail, que só conta quando o transporte ``smtp`` o entregou; 30 dias
depois do aviso, sem entrada nova, a conta é desativada, nunca o último dono ativo. Conta criada que nunca teve senha,
com a ativação vencida, é excluída; a que espera uma recuperação, não. Sem modelo e sem rede (o ``smtp`` é falso).
"""
import http.client
import json
import os
from pathlib import Path
import smtplib
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
from cenario_redacoes import SENHA
import correio
import test_acesso  # module import: its TestCases are not collected again here


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
        self.assertEqual(acesso.nome_publico(self.root, dono, self.a), 'Dona Alfa')
        self.assertEqual(acesso.nome_publico(self.root, cid, self.a), acesso.CONTA_EXCLUIDA)
        self.assertEqual(acesso.CONTA_EXCLUIDA, 'Conta excluída')
        for sem_redacao in ((), (None,), ('',)):  # Y1 of the review: who forgets the newsroom gets an error, no names
            with self.assertRaises(TypeError if not sem_redacao else ValueError):
                acesso.nome_publico(self.root, dono, *sem_redacao)
            with self.assertRaises(TypeError if not sem_redacao else ValueError):
                acesso.nomes_publicos(self.root, [dono, dono_b], *sem_redacao)
        self.assertIsNone(acesso.nome_publico(self.root, dono_b, self.a))  # never a name of the other newsroom
        self.assertIsNone(acesso.nome_publico(self.root, cid, self.b))
        for valor in ('manutencao', 'admin', None, 7, 'f' * 16):
            self.assertIsNone(acesso.nome_publico(self.root, valor, self.a), valor)
        self.assertEqual(acesso.nomes_publicos(self.root, [dono, cid, dono_b, 'operador'], self.a),
                         {dono: 'Dona Alfa', cid: 'Conta excluída'})


class InativasTest(test_acesso.DuasRedacoes):
    def setUp(self):
        super().setUp()
        self.enviadas = []
        enviar = patch.object(correio, '_smtp', side_effect=lambda para, assunto, corpo: self.enviadas.append(
            (para, assunto, corpo)))
        enviar.start()
        self.addCleanup(enviar.stop)

    def inativa(self, cid, dias=acesso.INATIVIDADE_DIAS, email=True):
        momento = acesso._iso(acesso.agora() - acesso.timedelta(days=dias, minutes=1))
        self.gravar('UPDATE contas SET ultimo_acesso = ?, email = ? WHERE id = ?', momento,
                    f'{cid}@exemplo.test' if email else None, cid)

    def conta(self, cid):
        return self.linhas('SELECT * FROM contas WHERE id = ?', cid)[0]

    def varrer(self, transporte='smtp', **delta):
        with correio.usar(transporte):
            if not delta:
                return acesso.manutencao(self.root)
            with self.depois(**delta):
                return acesso.manutencao(self.root)

    def test_aviso_entregue_e_desativacao_trinta_dias_depois(self):
        sid = acesso.entrar(self.root, 'rep.a', test_acesso.SENHA)[0]
        self.inativa(self.rep_a)
        self.inativa(self.dono_a, dias=acesso.INATIVIDADE_DIAS - 2)  # not yet
        resultado = self.varrer()
        self.assertEqual((resultado['contas_avisadas'], resultado['para_o_operador']), (1, []))
        (para, assunto, corpo), = self.enviadas
        self.assertEqual(para, f'{self.rep_a}@exemplo.test')
        self.assertIn('há mais de 180 dias', corpo)
        self.assertIn('por mais 30 dias, poderá ser desativada', corpo)  # Z2: with two donos, one of them is not
        self.assertIn('A única conta de dono ativa de uma redação nunca é desativada', corpo)
        self.assertNotIn('http', assunto + corpo)  # no link: the message never carries where to type the password
        self.assertTrue(self.conta(self.rep_a)['aviso_inatividade_em'])
        self.assertEqual(self.varrer()['contas_avisadas'], 0)  # warned once
        self.assertEqual(len(self.enviadas), 1)
        self.assertEqual(self.varrer(days=acesso.DESATIVACAO_DIAS - 1)['contas_desativadas'], 0)
        self.assertEqual(self.varrer(days=acesso.DESATIVACAO_DIAS, minutes=1)['contas_desativadas'], 1)
        conta = self.conta(self.rep_a)
        self.assertEqual((conta['ativa'], conta['excluida_em']), (0, None))  # deactivated, not deleted
        self.assertIsNone(acesso.sessao(self.root, sid))
        evento = self.linhas("SELECT * FROM eventos WHERE tipo = 'conta_desativada_por_inatividade'")
        self.assertEqual([(e['conta'], e['por'], e['organizacao']) for e in evento], [(self.rep_a, 'manutencao', self.a)])
        self.assertIsNone(self.linhas("SELECT responsavel FROM casos WHERE caso = 'caso_a'")[0]['responsavel'])
        # The dono reactivates it, and the count starts again: the next sweep does not deactivate it at once.
        acesso.reativar(self.root, self.rep_a, por=self.dono_a, organizacao=self.a)
        self.assertEqual(self.varrer(days=acesso.DESATIVACAO_DIAS, minutes=2)['contas_desativadas'], 0)
        self.assertEqual(self.conta(self.rep_a)['ativa'], 1)

    def test_entrar_de_novo_zera_tudo(self):
        self.inativa(self.rep_a)
        self.assertEqual(self.varrer()['contas_avisadas'], 1)
        acesso.entrar(self.root, 'rep.a', test_acesso.SENHA)
        conta = self.conta(self.rep_a)
        self.assertIsNone(conta['aviso_inatividade_em'])
        self.assertGreater(conta['ultimo_acesso'], acesso._iso(acesso.agora() - acesso.timedelta(minutes=1)))
        resultado = self.varrer(days=acesso.DESATIVACAO_DIAS + 1)
        self.assertEqual((resultado['contas_desativadas'], resultado['contas_avisadas']), (0, 0))

    def test_sem_smtp_sem_email_ou_com_falha_nada_conta_e_vai_ao_operador(self):
        self.inativa(self.rep_a)
        self.inativa(self.rep_b, email=False)
        for transporte in ('tela', 'simulado'):  # observation F1: the simulated one delivers only in memory
            resultado = self.varrer(transporte)
            self.assertEqual(resultado['contas_avisadas'], 0, transporte)
            self.assertCountEqual(resultado['para_o_operador'], [
                {'conta': self.rep_a, 'redacao': self.a, 'motivo': 'sem_envio'},
                {'conta': self.rep_b, 'redacao': self.b, 'motivo': 'sem_email'}])
        with patch.object(correio, '_smtp', side_effect=smtplib.SMTPException('recusado')):
            resultado = self.varrer()
        self.assertEqual(resultado['contas_avisadas'], 0)
        self.assertIn({'conta': self.rep_a, 'redacao': self.a, 'motivo': 'envio_falhou'}, resultado['para_o_operador'])
        for cid in (self.rep_a, self.rep_b):
            self.assertIsNone(self.conta(cid)['aviso_inatividade_em'])
        # Never warned, never deactivated: not even a year later.
        resultado = self.varrer('tela', days=400)
        self.assertEqual(resultado['contas_desativadas'], 0)
        self.assertEqual(self.conta(self.rep_a)['ativa'], 1)
        self.assertNotIn('Rep A', json.dumps(resultado))  # the operator's list: ids and reasons only
        self.assertNotIn('@', json.dumps(resultado))

    def test_servidor_de_email_fora_do_ar_nao_e_tentado_sem_fim(self):
        pessoas = [self.pessoa(f'Pessoa {n}', f'pessoa.{n}', 'reporter', self.a) for n in range(5)]
        for cid in pessoas:
            self.inativa(cid)
        with patch.object(correio, '_smtp', side_effect=OSError('sem rede')) as smtp:
            resultado = self.varrer()
        self.assertEqual(smtp.call_count, acesso.FALHAS_SEGUIDAS_DE_ENVIO)
        self.assertEqual([linha['motivo'] for linha in resultado['para_o_operador']], ['envio_falhou'] * 5)

    def test_o_ultimo_dono_e_avisado_e_nunca_desativado(self):
        self.inativa(self.dono_b)
        self.assertEqual(self.varrer()['contas_avisadas'], 1)
        corpo = self.enviadas[0][2]
        self.assertIn('única conta de dono ativa', corpo)
        self.assertIn('não será desativada', corpo)
        self.assertNotIn('por mais', corpo)  # no date to deactivate it: it never is
        resultado = self.varrer(days=acesso.DESATIVACAO_DIAS + 1)
        self.assertEqual(resultado['contas_desativadas'], 0)
        self.assertEqual(resultado['para_o_operador'], [{'conta': self.dono_b, 'redacao': self.b, 'motivo': 'ultimo_dono'}])
        self.assertEqual(self.conta(self.dono_b)['ativa'], 1)

    def test_dono_a_espera_de_recuperacao_nao_conta_como_dono(self):
        # Y2 of the review of 4b-3: two donos, one waiting for a recovery (no password). The other one is the last who
        # can run the newsroom: she does not delete herself, is not removed nor deactivated, and the sweep keeps her.
        dona2 = self.pessoa('Dona Dois', 'dona.dois', 'dono', self.a)
        _, token = acesso.recuperar(self.root, dona2, por='operador', organizacao=self.a)
        with self.assertRaises(acesso.UltimoDono):
            acesso.excluir_conta(self.root, self.dono_a, 'Dona A', test_acesso.SENHA)
        self.assertEqual(self.tentativas_de_senha(self.dono_a), [])  # refused before the password: no attempt spent
        with patch.object(acesso, 'confirmar_senha'):  # past the password, the lock of the deletion itself holds
            with self.assertRaises(acesso.UltimoDono):
                acesso.remover(self.root, self.dono_a, dona2, self.a, 'qualquer')
        with self.assertRaises(acesso.UltimoDono):
            acesso.desativar(self.root, self.dono_a, por=dona2, organizacao=self.a)
        self.inativa(self.dono_a)
        self.assertEqual(self.varrer()['contas_avisadas'], 1)
        self.assertIn('única conta de dono ativa da sua redação', self.enviadas[0][2])
        resultado = self.varrer(days=acesso.DESATIVACAO_DIAS + 1)
        self.assertEqual(resultado['contas_desativadas'], 0)
        self.assertIn({'conta': self.dono_a, 'redacao': self.a, 'motivo': 'ultimo_dono'}, resultado['para_o_operador'])
        conta = self.conta(self.dono_a)
        self.assertEqual((conta['ativa'], conta['excluida_em']), (1, None))
        # Once the other dono has a password again, the first one may leave.
        acesso.ativar(self.root, token, test_acesso.SENHA)
        self.assertEqual(acesso.excluir_conta(self.root, self.dono_a, 'Dona A', test_acesso.SENHA)['situacao'], 'excluida')

    def tentativas_de_senha(self, cid):
        return self.linhas('SELECT * FROM tentativas WHERE chave = ?', acesso.CHAVE_CONFIRMACAO + cid)

    def test_duas_varreduras_juntas_nao_avisam_duas_vezes(self):
        # Z3 of the review: the server's start and the daily job at the same time. The one that finds the lock taken
        # sends nothing; the warning is sent once.
        self.inativa(self.rep_a)
        with acesso._trinco_sem_espera(Path(str(acesso.caminho_bd(self.root)) + '.avisos')) as meu:
            self.assertTrue(meu)
            with correio.usar('smtp'):
                self.assertEqual(acesso.avisar_inativas(self.root), {'contas_avisadas': 0, 'para_o_operador': []})
            self.assertEqual(self.enviadas, [])
            self.assertIsNone(self.conta(self.rep_a)['aviso_inatividade_em'])
        self.assertEqual(self.varrer()['contas_avisadas'], 1)
        self.assertEqual(self.varrer()['contas_avisadas'], 0)
        self.assertEqual(len(self.enviadas), 1)

    def test_redacao_suspensa_nao_corre_prazo(self):
        acesso.definir_situacao_redacao(self.root, self.b, 'suspensa')
        self.inativa(self.rep_b)
        resultado = self.varrer()
        self.assertEqual((resultado['contas_avisadas'], resultado['para_o_operador'], self.enviadas), (0, [], []))

    def test_aviso_antes_da_suspensao_recomeca_na_volta(self):
        # B1 of the review: warned on day 0, suspended until day 60. The 30 days of the warning ran while nobody
        # could sign in; on the return the count starts again, as for a reactivated account.
        self.inativa(self.rep_b)
        self.assertEqual(self.varrer()['contas_avisadas'], 1)
        acesso.definir_situacao_redacao(self.root, self.b, 'suspensa')
        with self.depois(days=60):
            acesso.definir_situacao_redacao(self.root, self.b, 'ativa')
        conta = self.conta(self.rep_b)
        self.assertIsNone(conta['aviso_inatividade_em'])
        resultado = self.varrer(days=61)
        self.assertEqual((resultado['contas_desativadas'], resultado['contas_avisadas']), (0, 0))
        self.assertEqual(self.varrer(days=60 + acesso.INATIVIDADE_DIAS - 1)['contas_avisadas'], 0)
        self.assertEqual(self.varrer(days=60 + acesso.INATIVIDADE_DIAS, minutes=1)['contas_avisadas'], 1)
        self.assertEqual(len(self.enviadas), 2)

    def test_suspensao_longa_nao_conta_como_inatividade(self):
        # Suspended for 175 days after the last sign-in: on the return nobody is warned for those days.
        self.inativa(self.rep_b, dias=0)
        acesso.definir_situacao_redacao(self.root, self.b, 'suspensa')
        with self.depois(days=175):
            acesso.definir_situacao_redacao(self.root, self.b, 'ativa')
        self.assertEqual(self.varrer(days=181)['contas_avisadas'], 0)
        self.assertEqual(self.enviadas, [])
        self.assertEqual(self.varrer(days=175 + acesso.INATIVIDADE_DIAS, minutes=1)['contas_avisadas'], 1)
        # Suspending again, or an active newsroom set active again, does not move anybody's dates.
        antes = self.conta(self.rep_a)['ultimo_acesso']
        acesso.definir_situacao_redacao(self.root, self.a, 'ativa')
        self.assertEqual(self.conta(self.rep_a)['ultimo_acesso'], antes)

    def test_conta_sem_senha_de_redacao_suspensa_nao_sai(self):
        # Z1 of the review: the removal of the accounts that never had a password does not run in a suspended newsroom.
        nova, _ = acesso.criar_conta(self.root, 'Sem Senha B', 'sem.senha.b', papel='reporter', organizacao=self.b,
                                     por='operador')
        acesso.definir_situacao_redacao(self.root, self.b, 'suspensa')
        resultado = self.varrer('tela', hours=acesso.ATIVACAO_HORAS, minutes=1)
        self.assertEqual((resultado['contas_excluidas'], resultado['para_o_operador']), (0, []))
        self.assertIsNone(self.conta(nova['id'])['excluida_em'])

    def test_criada_sem_senha_e_vencida_sai_e_a_da_recuperacao_fica(self):
        nova, _ = acesso.criar_conta(self.root, 'Nunca Ativou', 'nunca.ativou', papel='reporter', organizacao=self.a,
                                     por='operador')
        acesso.recuperar(self.root, self.rep_b, por='operador', organizacao=self.b)  # waiting for a recovery
        sozinha = acesso.criar_redacao(self.root, 'Redação Só Convite')['id']
        dona, _ = acesso.criar_conta(self.root, 'Dona Sem Senha', 'dona.sem.senha', papel='dono', organizacao=sozinha,
                                     por='operador')
        self.assertEqual(self.varrer('tela', hours=acesso.ATIVACAO_HORAS - 1)['contas_excluidas'], 0)
        resultado = self.varrer('tela', hours=acesso.ATIVACAO_HORAS, minutes=1)
        self.assertEqual(resultado['contas_excluidas'], 1)
        self.assertIsNotNone(self.conta(nova['id'])['excluida_em'])
        evento = self.linhas("SELECT * FROM eventos WHERE tipo = 'conta_excluida' AND conta = ?", nova['id'])
        self.assertEqual([e['por'] for e in evento], ['manutencao'])
        self.assertIsNone(self.conta(self.rep_b)['excluida_em'])  # the recovery: it had a password and may come back
        self.assertIsNone(self.conta(dona['id'])['excluida_em'])  # the only dono of a newsroom: to the operator
        self.assertIn({'conta': dona['id'], 'redacao': sozinha, 'motivo': 'ultimo_dono'}, resultado['para_o_operador'])


if __name__ == '__main__':
    unittest.main()
