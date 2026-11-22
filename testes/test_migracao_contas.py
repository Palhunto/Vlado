"""Migração do ``acesso.json`` (versão 2) para o armazenamento novo (contrato de contas, seção 6).

Sempre sobre um ``acesso.json`` sintético numa pasta temporária; nunca sobre ``acesso/`` de verdade. As garantias do
contrato, uma por teste: não ampliação de acesso, autoria (os mesmos ids), reversão, repetição e ensaio.
"""
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import autorizacao
import interface_pesquisa
import rotas_equipe
from test_acesso import RAPIDO, SENHA, hasher_rapido

ADMIN, ADMIN2, ANA, BIA, PENDENTE, DESATIVADA = ('a' * 16, 'b' * 16, 'c' * 16, 'd' * 16, 'e' * 16, 'f' * 16)
# Operations that did not exist before the migration and reach no case the account did not reach: the own account
# (`conta-*`, every role), and, for the dono only, the team (`equipe-*`) and who takes part in a case (`caso-*`).
DA_PROPRIA_CONTA = set(interface_pesquisa.CONTA_PROPRIA)
NOVAS_SEM_APURACAO_ALHEIA = DA_PROPRIA_CONTA | set(rotas_equipe.OPERACOES)
CATALOGO = ('alpha', 'beta', 'gama')


def v2(senha_hash, token_pendente='token-de-ativacao-pendente-0123456789'):
    """A v2 store as the Mesa wrote it: two admins, guests, a pending activation, sessions, events."""
    conta = lambda nome, login, papel, casos=None, cota=None, **extra: {  # noqa: E731
        'nome': nome, 'login': login, 'papel': papel, 'casos': casos, 'cota_diaria': cota, 'ativa': True,
        'senha_hash': senha_hash, 'senha_definida_em': '2026-11-01T10:00:00Z', 'criada_em': '2026-11-01T09:00:00Z',
        'criada_por': 'cli', **extra}
    dia = acesso.agora().strftime('%Y-%m-%d')
    return {'versao': 2, 'primeiro_admin_em': '2026-11-01T09:00:00Z', 'contas': {
        ADMIN: conta('Editora', 'editora', 'admin'),
        ADMIN2: conta('Chefe', 'chefe', 'admin'),
        ANA: conta('Ana', 'ana', 'convidado', ['alpha'], 5),
        BIA: conta('Bia', 'bia', 'convidado', ['beta', 'apagado_ha_tempos'], 7),
        PENDENTE: conta('Caio', 'caio', 'convidado', ['alpha', 'beta'], 3, senha_hash=None, senha_definida_em=None,
                        ativacao={'token_sha256': acesso._hash(token_pendente), 'expira_em': '2099-01-01T00:00:00Z',
                                  'motivo': 'criacao'}),
        DESATIVADA: conta('Duda', 'duda', 'convidado', ['gama'], 2, ativa=False)},
        'sessoes': {'9' * 64: {'conta': ADMIN, 'csrf': 'x', 'criada_em': '2026-11-22T10:00:00Z',
                               'expira_em': '2099-01-01T00:00:00Z', 'ultimo_uso': '2026-11-22T10:00:00Z', 'cliente': 'web'}},
        'tentativas': {'ana|198.51.100.1': {'falhas': 3, 'bloqueado_ate': None, 'em': '2026-11-22T10:00:00Z'}},
        'uso': {ANA: {dia: 4}, BIA: {'2020-01-01': 9}},
        'eventos': [{'em': '2026-11-01T09:00:00Z', 'tipo': 'primeiro_admin', 'conta': ADMIN, 'por': 'primeiro_acesso'},
                    {'em': '2026-11-02T09:00:00Z', 'tipo': 'conta_criada', 'conta': ANA, 'por': ADMIN}]}


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_REDACAO_NOME': ''})
        env.start()
        self.addCleanup(env.stop)
        hasher_rapido(self)
        acesso.limpar_limites()
        (self.root / 'casos').mkdir()
        (self.root / 'casos/catalogo.json').write_text(json.dumps({'casos': [{'id': c, 'titulo': c} for c in CATALOGO]}),
                                                       encoding='utf-8')
        (self.root / 'acesso').mkdir()
        self.antigo = self.root / 'acesso/acesso.json'
        self.original = json.dumps(v2(RAPIDO.hash(SENHA)), ensure_ascii=False, indent=2)
        self.antigo.write_text(self.original, encoding='utf-8')

    def linhas(self, sql, *args):
        con = sqlite3.connect(acesso.caminho_bd(self.root))
        con.row_factory = sqlite3.Row
        try:
            return [dict(linha) for linha in con.execute(sql, args)]
        finally:
            con.close()


class MigracaoTest(Base):
    def test_instalacao_vira_uma_redacao_admin_vira_dono_e_convidado_fica_convidado_com_os_mesmos_ids(self):
        contas = {c['id']: c for c in acesso.listar(self.root)}
        self.assertEqual(set(contas), {ADMIN, ADMIN2, ANA, BIA, PENDENTE, DESATIVADA})
        self.assertEqual({cid: c['papel'] for cid, c in contas.items()},
                         {ADMIN: 'dono', ADMIN2: 'dono', ANA: 'convidado', BIA: 'convidado', PENDENTE: 'convidado',
                          DESATIVADA: 'convidado'})
        self.assertEqual(len({c['organizacao'] for c in contas.values()}), 1)
        redacao = acesso.listar_redacoes(self.root)
        self.assertEqual([(r['nome'], r['pessoas'], r['apuracoes']) for r in redacao], [('Redação', 6, 3)])
        self.assertEqual(acesso.organizacao_inicial(self.root), redacao[0]['id'])
        self.assertEqual((contas[ANA]['login'], contas[ANA]['cota_diaria'], contas[ANA]['casos']), ('ana', 5, ['alpha']))
        self.assertEqual(contas[DESATIVADA]['situacao'], 'desativada')
        self.assertIsNone(contas[ADMIN]['email'])

    def test_toda_apuracao_do_catalogo_ganha_posse_sem_responsavel_e_os_donos_alcancam_todas(self):
        posses = self.linhas('SELECT caso, responsavel, origem FROM casos ORDER BY caso') if acesso.listar(self.root) else []
        self.assertEqual([(p['caso'], p['responsavel'], p['origem']) for p in posses],
                         [(c, None, 'migracao') for c in CATALOGO])
        for dono in (ADMIN, ADMIN2):
            self.assertEqual(acesso.alcance(self.root, dono), (frozenset(CATALOGO), frozenset()))

    def test_participacao_em_apuracao_que_nao_existe_mais_e_descartada_e_anotada(self):
        self.assertEqual(acesso.alcance(self.root, BIA)[0], frozenset({'beta'}))
        relatorio = acesso.relatorio_migracao(self.root)
        self.assertEqual(relatorio['participacoes_descartadas'], [{'conta': BIA, 'caso': 'apagado_ha_tempos'}])
        self.assertEqual(relatorio['resumo'], {'donos': 2, 'convidados': 4, 'apuracoes': 3, 'participacoes': 5,
                                               'participacoes_descartadas': 1, 'contas_sem_email': 6, 'sessoes_encerradas': 1})
        self.assertIsNone(acesso.posse(self.root, 'apagado_ha_tempos'))

    def test_senha_continua_valendo_e_o_link_de_ativacao_pendente_tambem(self):
        sid, _, publica = acesso.entrar(self.root, 'editora', SENHA)
        self.assertEqual((publica['id'], acesso.sessao(self.root, sid)['papel']), (ADMIN, 'dono'))
        self.assertEqual(acesso.consultar_ativacao(self.root, 'token-de-ativacao-pendente-0123456789')['login'], 'caio')
        acesso.ativar(self.root, 'token-de-ativacao-pendente-0123456789', SENHA)
        self.assertEqual(acesso.entrar(self.root, 'caio', SENHA)[2]['id'], PENDENTE)
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'duda', SENHA)

    def test_sessoes_e_tentativas_sao_descartadas_uso_de_hoje_e_eventos_ficam(self):
        acesso.listar(self.root)
        self.assertEqual(self.linhas('SELECT * FROM sessoes'), [])
        self.assertEqual(self.linhas('SELECT * FROM tentativas'), [])
        self.assertEqual([(u['conta'], u['feitas']) for u in self.linhas('SELECT * FROM uso_diario')], [(ANA, 4)])
        with self.assertRaisesRegex(ValueError, 'Limite diário'):  # 4 of 5 already asked today: one more, then the limit
            acesso.registrar_consulta(self.root, ANA)
            acesso.registrar_consulta(self.root, ANA)
        tipos = [e['tipo'] for e in self.linhas('SELECT tipo FROM eventos ORDER BY n')]
        self.assertEqual(tipos, ['primeiro_admin', 'conta_criada', 'migracao_contas'])
        self.assertFalse(acesso.primeiro_acesso_disponivel(self.root))

    def test_arquivo_antigo_fica_guardado_como_v2_e_nao_e_mais_lido(self):
        acesso.listar(self.root)
        self.assertFalse(self.antigo.exists())
        self.assertEqual((self.root / 'acesso/acesso.v2.json').read_text(encoding='utf-8'), self.original)
        self.assertTrue(acesso.caminho_bd(self.root).is_file())

    def test_repetir_nao_duplica_nada(self):
        primeira = acesso.listar(self.root)
        acesso._PRONTOS.clear()  # as another process would see it
        self.assertEqual(acesso.listar(self.root), primeira)
        self.assertEqual(len(acesso.listar_redacoes(self.root)), 1)
        self.assertEqual(len(list((self.root / 'acesso').glob('acesso.v2*.json'))), 1)

    def test_queda_no_meio_deixa_o_arquivo_antigo_como_estava_e_nenhum_armazenamento_pela_metade(self):
        with patch.object(acesso, '_povoar_de_v2', side_effect=sqlite3.OperationalError('disco cheio')):
            with self.assertRaises(acesso.RegistroIlegivel):
                acesso.listar(self.root)
        self.assertEqual(self.antigo.read_text(encoding='utf-8'), self.original)
        self.assertEqual([p.name for p in (self.root / 'acesso').iterdir() if p.name.startswith('contas.sqlite')], [])
        self.assertEqual(len(acesso.listar(self.root)), 6)  # and the next attempt migrates

    def test_queda_entre_as_duas_trocas_de_nome_e_concluida_na_proxima_partida(self):
        with patch.object(acesso, '_guardar_antigo', side_effect=OSError('queda')):
            with self.assertRaises(OSError):
                acesso.listar(self.root)
        self.assertTrue(self.antigo.exists() and acesso.caminho_bd(self.root).is_file())
        acesso._PRONTOS.clear()
        self.assertEqual(len(acesso.listar(self.root)), 6)  # the store was whole: no second migration
        self.assertFalse(self.antigo.exists())
        self.assertTrue((self.root / 'acesso/acesso.v2.json').is_file())

    def test_catalogo_ilegivel_nao_migra_com_as_apuracoes_invisiveis(self):
        (self.root / 'casos/catalogo.json').write_text('{quebrado', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Catálogo'):
            acesso.listar(self.root)
        self.assertTrue(self.antigo.exists())
        self.assertFalse(acesso.caminho_bd(self.root).exists())

    def test_nome_da_redacao_inicial_vem_da_variavel(self):
        with patch.dict(os.environ, {'VLADO_REDACAO_NOME': 'Redação do Vale'}):
            self.assertEqual(acesso.listar_redacoes(self.root)[0]['nome'], 'Redação do Vale')


class EnsaioTest(Base):
    def cli(self, *args):
        saida = io.StringIO()
        with patch.object(acesso, 'ROOT', self.root), patch.object(sys, 'argv', ['acesso.py', *args]), redirect_stdout(saida):
            codigo = acesso._principal()
        return codigo, saida.getvalue()

    def test_simular_mostra_o_relatorio_sem_gravar_e_sem_segredos(self):
        antes = sorted(p.name for p in (self.root / 'acesso').iterdir())
        codigo, saida = self.cli('migrar', '--simular')
        relatorio = json.loads(saida)
        self.assertEqual((codigo, relatorio['estado'], relatorio['origem']), (0, 'a_migrar', 'acesso.json v2'))
        self.assertEqual(relatorio['resumo']['donos'], 2)
        self.assertEqual(relatorio['participacoes_descartadas'], [{'conta': BIA, 'caso': 'apagado_ha_tempos'}])
        self.assertEqual(sorted(p.name for p in (self.root / 'acesso').iterdir() if not p.name.endswith('.lock')), antes)
        self.assertEqual(self.antigo.read_text(encoding='utf-8'), self.original)
        for segredo in ('$argon2', 'editora', 'Editora', 'token'):
            self.assertNotIn(segredo, saida)

    def test_migrar_pelo_terminal_e_simular_depois_diz_que_ja_migrou(self):
        codigo, saida = self.cli('migrar')
        self.assertEqual((codigo, json.loads(saida)['estado'], json.loads(saida)['origem']), (0, 'migrado', 'acesso.json v2'))
        self.assertEqual(json.loads(self.cli('migrar', '--simular')[1])['estado'], 'ja_migrado')
        self.assertEqual(len(json.loads(self.cli('redacao-listar')[1])), 1)

    def test_sem_registro_antigo_nao_ha_o_que_migrar(self):
        self.antigo.unlink()
        self.assertEqual(json.loads(self.cli('migrar', '--simular')[1]), {'estado': 'sem_registro_antigo'})

    def test_caso_atribuir_da_posse_a_apuracao_criada_pelo_terminal(self):
        acesso.listar(self.root)
        redacao = acesso.listar_redacoes(self.root)[0]['id']
        catalogo = json.loads((self.root / 'casos/catalogo.json').read_text(encoding='utf-8'))
        catalogo['casos'].append({'id': 'do_terminal', 'titulo': 'Do terminal'})
        (self.root / 'casos/catalogo.json').write_text(json.dumps(catalogo), encoding='utf-8')
        self.assertNotIn('do_terminal', acesso.alcance(self.root, ADMIN)[0])  # created after: nobody reaches it
        with self.assertRaisesRegex(ValueError, 'catálogo'):
            self.cli('caso-atribuir', '--caso', 'nao_existe', '--redacao', redacao)
        codigo, saida = self.cli('caso-atribuir', '--caso', 'do_terminal', '--redacao', redacao)
        self.assertEqual((codigo, json.loads(saida)['organizacao']), (0, redacao))
        self.assertIn('do_terminal', acesso.alcance(self.root, ADMIN)[0])
        self.assertNotIn('do_terminal', acesso.alcance(self.root, ANA)[0])


class NaoAmpliacaoTest(Base):
    """No account leaves the migration reaching what it did not reach before (contrato, princípio 9)."""

    def test_nenhuma_conta_alcanca_depois_apuracao_ou_operacao_que_nao_alcancava_antes(self):
        antes = json.loads(self.original)
        operacoes_de_antes = set(interface_pesquisa.OPERACOES_API) - NOVAS_SEM_APURACAO_ALHEIA
        for cid, conta in antes['contas'].items():
            with self.subTest(conta=conta['login']):
                admin = conta['papel'] == 'admin'
                # Before: the administrator reached every case and operation; the guest, its cases and its operations.
                casos_antes = set(CATALOGO) if admin else set(conta['casos'])
                ops_antes = operacoes_de_antes if admin else set(interface_pesquisa.OPERACOES_CONVIDADO)
                registro = {c['id']: c for c in acesso.listar(self.root)}[cid]
                casos_depois = set(acesso.alcance(self.root, cid)[0])
                ops_depois = set(autorizacao.capacidades({'papel': registro['papel']}))
                if not conta['ativa']:
                    self.assertEqual(casos_depois, set())
                self.assertLessEqual(casos_depois, casos_antes)
                self.assertLessEqual(ops_depois - NOVAS_SEM_APURACAO_ALHEIA, ops_antes)
                if not admin:  # the legacy profile: exactly what a guest could call, on its own cases only
                    self.assertEqual(ops_depois - DA_PROPRIA_CONTA, set(interface_pesquisa.OPERACOES_CONVIDADO))

    def test_o_portao_recusa_ao_convidado_migrado_o_que_ele_nao_alcancava(self):
        sid = acesso.entrar(self.root, 'ana', SENHA)[0]
        principal = acesso.sessao(self.root, sid)
        self.assertEqual((principal['papel'], principal['casos']), ('convidado', ['alpha']))
        autorizacao.conferir(self.root, 'piloto', principal, 'codex-listar', {'caso': 'alpha'})
        for operacao, dados, codigo in (('codex-listar', {'caso': 'beta'}, 'caso_indisponivel'),
                                        ('apuracao-notas', {'caso': 'alpha'}, 'operacao_proibida'),
                                        ('achados-catalogo', {'caso': 'alpha'}, 'operacao_proibida'),
                                        ('equipe-listar', {}, 'operacao_proibida'),
                                        ('equipe-convidar', {'email': 'x@exemplo.test', 'papel': 'dono'}, 'operacao_proibida'),
                                        ('contas-listar', {}, 'operacao_inexistente'),  # withdrawn with the invitation
                                        ('cadastrar', {'novo': True}, 'operacao_proibida')):
            with self.subTest(operacao=operacao), self.assertRaises(autorizacao.Recusa) as recusa:
                autorizacao.conferir(self.root, 'piloto', principal, operacao, dados)
            self.assertEqual(recusa.exception.codigo, codigo)

    def test_autoria_continua_resolvendo_pelo_mesmo_id(self):
        # What notes, reviews and conversations store is the account id: it must name the same person after.
        nomes_antes = {cid: c['nome'] for cid, c in json.loads(self.original)['contas'].items()}
        nomes_depois = {c['id']: c['nome'] for c in acesso.listar(self.root)}
        self.assertEqual(nomes_depois, nomes_antes)
        principal = acesso.sessao(self.root, acesso.entrar(self.root, 'ana', SENHA)[0])
        self.assertEqual((principal['conta'], principal['nome']), (ANA, 'Ana'))


if __name__ == '__main__':
    unittest.main()
