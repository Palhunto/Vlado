"""Termos de uso com versão (contrato de contas, seção 8.4 e entrega 4b-1).

A versão vigente e o endereço do texto vêm de quem opera (``VLADO_TERMOS_VERSAO`` e ``VLADO_TERMOS_ENDERECO``), só no
modo ``piloto``. O convite mostra a versão e o aceite a grava com a conta; versão nova gera a pendência ``termos``,
que vem antes da do segundo fator e é resolvida por ``conta-termos-aceitar``. Quem não aceita ainda alcança o próprio
perfil e as saídas (exportar e excluir, ressalva B2). Na exclusão, o aceite fica só com id, versão e data (P41 b).
Sem modelo e sem rede.
"""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import autorizacao
import cenario_redacoes as cenario
from cenario_redacoes import SENHA
import rotas_contas

ENDERECO = 'https://vlado.test/termos'


def com_termos(versao='2026-12-01', endereco=ENDERECO):
    return patch.dict(os.environ, {'VLADO_TERMOS_VERSAO': versao, 'VLADO_TERMOS_ENDERECO': endereco})


class VigentesTest(unittest.TestCase):
    def test_sem_versao_nao_ha_termos_e_configuracao_torta_nao_sobe(self):
        with com_termos('', ''):
            self.assertIsNone(acesso.termos_vigentes())
        with com_termos('v1.0'):
            self.assertEqual(acesso.termos_vigentes(), {'versao': 'v1.0', 'endereco': ENDERECO})
        for versao, endereco in (('', ENDERECO), ('v1', ''), ('v1', 'http://vlado.test/termos'), ('v1', 'https://x y'),
                                 ('com espaço', ENDERECO), ('-v1', ENDERECO), ('v' * 33, ENDERECO), ('v1', 'javascript:x')):
            with self.subTest(versao=versao, endereco=endereco), com_termos(versao, endereco):
                with self.assertRaises(ValueError):
                    acesso.termos_vigentes()

    def test_sem_termos_vigentes_qualquer_versao_e_desatualizada(self):
        with self.assertRaises(acesso.TermosDesatualizados):  # refused before the store is touched
            acesso.aceitar_termos(Path(tempfile.gettempdir()) / 'nao-existe', 'c' * 16, 'v1', None)

    def test_so_o_piloto_tem_termos(self):
        with com_termos():
            for modo, esperado in (('piloto', '2026-12-01'), ('local-contas', None), ('local', None)):
                rotas = SimpleNamespace(server=SimpleNamespace(modo=modo))
                termos = rotas_contas.RotasContas._termos(rotas)
                self.assertEqual(termos and termos['versao'], esperado, modo)
        # The installed Mesa: refused by the rule of the mode, and so never offered; the hosted service offers it.
        raiz, principal = Path(tempfile.gettempdir()), {'papel': 'leitor', 'conta': 'c' * 16, 'pendencias': []}
        self.assertEqual(autorizacao._recusa_do_modo(raiz, 'local-contas', 'leitor', 'conta-termos-aceitar').codigo,
                         'operacao_proibida')
        self.assertIsNone(autorizacao._recusa_do_modo(raiz, 'piloto', 'leitor', 'conta-termos-aceitar'))
        self.assertNotIn('conta-termos-aceitar', autorizacao.capacidades(raiz, 'local-contas', principal))


class TermosTest(cenario.DuasRedacoes):
    """In the hosted mode, with two newsrooms."""

    _n = 0

    def nova(self, papel='leitor'):
        TermosTest._n += 1
        login = f'pessoa.termos{TermosTest._n}'
        cid = self.conta(f'Pessoa Termos {TermosTest._n}', login, papel, casos=['alpha'] if papel != 'dono' else ())
        return self._entrar(login), cid

    def publico(self, operacao, dados):
        status, cabecalhos, corpo = self.pedir('POST', '/api/' + operacao, json.dumps(dados),
                                               {'Content-Type': 'application/json', 'Origin': cenario.ORIGEM})
        return status, json.loads(corpo or b'{}'), cabecalhos

    def aceites(self, cid):
        con = sqlite3.connect(acesso.caminho_bd(self.root))
        try:
            return con.execute('SELECT versao, ip IS NOT NULL FROM termos_aceites WHERE conta = ? ORDER BY rowid', (cid,)).fetchall()
        finally:
            con.close()

    def pendencias(self, sessao):
        return self.get(sessao, '/api/sessao')[1]['pendencias']

    def test_versao_nova_pede_o_aceite_antes_de_qualquer_coisa(self):
        sessao, cid = self.nova()
        self.assertEqual(self.pendencias(sessao), [])  # no terms in force: nothing pending
        with com_termos('v1'):
            self.assertEqual(self.pendencias(sessao), ['termos'])
            status, corpo, _ = self.post(sessao, 'codex-status', {})
            self.assertEqual((status, corpo.get('codigo'), corpo.get('pendencias')), (403, 'pendencia_de_conta', ['termos']))
            status, cabecalhos, _ = self.pedir('GET', '/', cabecalhos={'Cookie': sessao[0]})
            self.assertEqual((status, cabecalhos.get('Location')), (303, '/conta/termos'))
            self.assertEqual(self.pedir('GET', '/conta/termos')[0], 200)
            perfil = self.post(sessao, 'conta-ver', {})[1]
            self.assertEqual((perfil['termos'], perfil['termos_vigente']), (None, {'versao': 'v1', 'endereco': ENDERECO}))
            # Another version than the one in force is refused, and nothing is written.
            for corpo in ({'versao': 'v0'}, {}, {'versao': 7}):
                status, resposta, _ = self.post(sessao, 'conta-termos-aceitar', corpo)
                self.assertEqual((status, resposta.get('codigo')), (400, 'termos_desatualizados'), corpo)
            self.assertEqual(self.aceites(cid), [])
            status, resposta, bruto = self.post(sessao, 'conta-termos-aceitar', {'versao': 'v1'})
            self.assertEqual((status, resposta['estado'], resposta['termos']['versao']), (200, 'termos_aceitos', 'v1'), bruto[:200])
            self.assertEqual(self.pendencias(sessao), [])
            self.assertEqual(self.post(sessao, 'codex-status', {})[0], 200)
            self.assertEqual(self.post(sessao, 'conta-termos-aceitar', {'versao': 'v1'})[0], 200)  # again: no second row
            self.assertEqual(self.aceites(cid), [('v1', 1)])
        with com_termos('v2'):
            self.assertEqual(self.pendencias(sessao), ['termos'])  # a new version: asked again at the next request
            self.assertEqual(self.post(sessao, 'conta-ver', {})[1]['termos']['versao'], 'v1')

    def test_quem_nao_aceita_ainda_sai_e_leva_os_proprios_dados(self):
        # Ressalva B2: with the terms pending, exporting and deleting the own account are not refused by the pending
        # item (until their deliveries they answer as operations that do not exist yet); with the second factor
        # pending, they are.
        sessao, _ = self.nova()
        with com_termos('v1'):
            for operacao in ('conta-exportar', 'conta-excluir'):
                status, corpo, _ = self.post(sessao, operacao, {})
                self.assertNotEqual(corpo.get('codigo'), 'pendencia_de_conta', operacao)
            self.assertEqual(self.post(sessao, 'sessao-sair', {})[0], 200)
        principal = {'papel': 'editor', 'conta': 'c' * 16, 'pendencias': ['segundo_fator']}
        for operacao in ('conta-exportar', 'conta-excluir', 'conta-termos-aceitar'):
            self.assertTrue(autorizacao._barrada_pela_pendencia(principal, operacao), operacao)
            self.assertFalse(autorizacao._barrada_pela_pendencia({**principal, 'pendencias': ['termos']}, operacao), operacao)

    def test_com_as_duas_pendencias_os_termos_vem_primeiro(self):
        sessao, cid = self.nova('editor')
        with com_termos('v1'):
            acesso.remover_fator(self.root, cid, SENHA)  # an editor of the hosted service without the second factor
            self.assertEqual(self.pendencias(sessao), ['termos', 'segundo_fator'])
            status, cabecalhos, _ = self.pedir('GET', '/', cabecalhos={'Cookie': sessao[0]})
            self.assertEqual(cabecalhos.get('Location'), '/conta/termos')
            self.assertEqual(self.post(sessao, 'conta-termos-aceitar', {'versao': 'v1'})[0], 200)
            self.assertEqual(self.pendencias(sessao), ['segundo_fator'])

    def test_o_convite_mostra_a_versao_e_o_aceite_a_grava_com_a_conta(self):
        with com_termos('v1'):
            email = f'termos{TermosTest._n}@exemplo.test'
            TermosTest._n += 1
            self.assertEqual(self.post('dono', 'conta-termos-aceitar', {'versao': 'v1'})[0], 200)  # the dono too
            status, corpo, bruto = self.post('dono', 'equipe-convidar', {'email': email, 'papel': 'reporter', 'casos': ['alpha']})
            self.assertEqual(status, 200, bruto[:200])
            token = corpo['link'].rsplit('/', 1)[1]
            consulta = self.publico('convite-consultar', {'token': token})[1]
            self.assertEqual((consulta['termos_versao'], consulta['termos_endereco']), ('v1', ENDERECO))
            for versao in (None, 'v0'):
                status, resposta, _ = self.publico('convite-aceitar', {'token': token, 'nome': 'Pessoa Nova', 'senha': SENHA,
                                                                       'termos_versao': versao})
                self.assertEqual((status, resposta.get('codigo')), (400, 'termos_desatualizados'), versao)
            status, resposta, cabecalhos = self.publico('convite-aceitar', {'token': token, 'nome': 'Pessoa Nova', 'senha': SENHA,
                                                                            'termos_versao': 'v1'})
            self.assertEqual(status, 200, resposta)
            cid = resposta['conta']['id']
            self.assertEqual(self.aceites(cid), [('v1', 1)])
            sessao = (cabecalhos['Set-Cookie'].split(';')[0], resposta['csrf'])
            self.assertEqual(self.pendencias(sessao), [])

    def test_na_exclusao_o_aceite_fica_so_com_id_versao_e_data(self):
        # P41 (b): the proof of the acceptance stays, without the address; name and e-mail were never in it.
        sessao, cid = self.nova()
        with com_termos('v1'):
            self.assertEqual(self.post(sessao, 'conta-termos-aceitar', {'versao': 'v1'})[0], 200)
        self.assertEqual(self.aceites(cid), [('v1', 1)])
        status, _, bruto = self.post('dono', 'equipe-remover', {'conta': cid, 'senha': SENHA})
        self.assertEqual(status, 200, bruto[:200])
        self.assertEqual(self.aceites(cid), [('v1', 0)])


class MigracaoTest(unittest.TestCase):
    def test_banco_da_versao_7_ganha_a_tabela_dos_aceites(self):
        with tempfile.TemporaryDirectory() as pasta:
            root = Path(pasta)
            acesso.criar_redacao(root, 'Redação')  # a fresh store, then taken back to version 7
            con = sqlite3.connect(acesso.caminho_bd(root))
            try:
                con.executescript('DROP INDEX termos_por_conta; DROP TABLE termos_aceites; PRAGMA user_version = 7;')
            finally:
                con.close()
            self.assertEqual(acesso.listar_redacoes(root)[0]['nome'], 'Redação')
            con = sqlite3.connect(acesso.caminho_bd(root))
            try:
                self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], acesso.ESQUEMA)
                colunas = [linha[1] for linha in con.execute('PRAGMA table_info(termos_aceites)')]
            finally:
                con.close()
            self.assertEqual(colunas, ['conta', 'versao', 'aceito_em', 'ip'])


if __name__ == '__main__':
    unittest.main()
