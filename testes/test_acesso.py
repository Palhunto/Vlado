"""Contas individuais com senha (acesso v2): armazenamento, ativação, sessões, bloqueio e migração.

Sem rede nem chamadas de modelo. O hash argon2id usa parâmetros leves nos testes (velocidade);
o servidor usa os parâmetros padrão do argon2-cffi.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from unittest.mock import MagicMock, patch

from argon2 import PasswordHasher

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import acesso

SENHA = 'senha-longa-de-teste-1'
RAPIDO = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


def hasher_rapido(testcase):
    """Lighter argon2id parameters for the suite; production keeps the library defaults."""
    p = patch.object(acesso, '_HASHER', RAPIDO)
    p.start()
    testcase.addCleanup(p.stop)


def ativar_conta(root, nome='Ana Silva', login='ana.silva', papel='convidado', casos=('alpha',), cota=20, senha=SENHA):
    conta, token = acesso.criar_conta(root, nome, login, papel=papel, casos=list(casos), cota_diaria=cota)
    acesso.ativar(root, token, senha)
    return conta


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {'VLADO_ACESSO': ''})
        env.start()
        self.addCleanup(env.stop)
        hasher_rapido(self)
        acesso.limpar_limites()

    def bruto(self):
        return (self.root / 'acesso/acesso.json').read_text(encoding='utf-8')

    def dados(self):
        return json.loads(self.bruto())

    def depois(self, **delta):
        return patch('acesso.agora', return_value=acesso.agora() + timedelta(**delta))


class ContasTest(Base):
    def test_criar_conta_guarda_so_hash_do_token_e_exige_ativacao(self):
        conta, token = acesso.criar_conta(self.root, 'Ana Silva', 'Ana.Silva', casos=['alpha'], cota_diaria=3)
        self.assertEqual((conta['login'], conta['situacao'], conta['casos']), ('ana.silva', 'aguardando_senha', ['alpha']))
        self.assertNotIn(token, self.bruto())
        dados = self.dados()
        self.assertEqual(dados['versao'], 2)
        registro = dados['contas'][conta['id']]
        self.assertIsNone(registro['senha_hash'])
        self.assertEqual(registro['ativacao']['motivo'], 'criacao')
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'ana.silva', SENHA)

    def test_ativar_define_senha_argon2id_e_permite_entrar(self):
        conta, token = acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        self.assertEqual(acesso.consultar_ativacao(self.root, token)['login'], 'ana')
        acesso.ativar(self.root, token, SENHA)
        registro = self.dados()['contas'][conta['id']]
        self.assertTrue(registro['senha_hash'].startswith('$argon2id$'))
        self.assertNotIn('ativacao', registro)
        self.assertNotIn(SENHA, self.bruto())
        sid, csrf, publica = acesso.entrar(self.root, 'ANA', SENHA)
        self.assertEqual(publica['id'], conta['id'])
        self.assertNotIn(sid, self.bruto())
        principal = acesso.sessao(self.root, sid)
        self.assertEqual((principal['conta'], principal['papel'], principal['casos'], principal['csrf']),
                         (conta['id'], 'convidado', ['alpha'], csrf))

    def test_ativacao_reutilizada_ou_expirada_e_recusada(self):
        _, token = acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        acesso.ativar(self.root, token, SENHA)
        with self.assertRaises(acesso.AtivacaoInvalida):
            acesso.ativar(self.root, token, 'outra-senha-longa-2')
        _, vencido = acesso.criar_conta(self.root, 'Bia', 'bia', casos=['alpha'], horas=1)
        with self.depois(hours=2), self.assertRaises(acesso.AtivacaoInvalida):
            acesso.ativar(self.root, vencido, SENHA)
        with self.assertRaises(acesso.AtivacaoInvalida):
            acesso.consultar_ativacao(self.root, 'x' * 43)

    def test_senha_fora_dos_limites_e_recusada(self):
        _, token = acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        for senha in ('curta', 'x' * 11, 'x' * 257, None):
            with self.subTest(senha=senha), self.assertRaises(ValueError):
                acesso.ativar(self.root, token, senha)
        acesso.ativar(self.root, token, 'x' * 12)

    def test_entradas_invalidas_na_criacao(self):
        casos = (
            {'nome': '', 'login': 'ana'}, {'nome': 'x', 'login': 'A'}, {'nome': 'x', 'login': '-ana'},
            {'nome': 'x', 'login': 'ana', 'papel': 'root'}, {'nome': 'x', 'login': 'ana', 'casos': ['../a']},
            {'nome': 'x', 'login': 'ana', 'casos': []}, {'nome': 'x', 'login': 'ana', 'cota_diaria': 0},
            {'nome': 'x', 'login': 'ana', 'horas': 0}, {'nome': 'x', 'login': 'ana', 'horas': 169},
            {'nome': 'x', 'login': 'a b c'}, {'nome': 'x', 'login': 'a' * 65})
        for kwargs in casos:
            kwargs.setdefault('casos', ['alpha'])
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                acesso.criar_conta(self.root, **kwargs)

    def test_login_e_unico_sem_diferenciar_maiusculas(self):
        acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        with self.assertRaisesRegex(ValueError, 'já existe'):
            acesso.criar_conta(self.root, 'Outra Ana', 'ANA', casos=['alpha'])

    def test_listar_mostra_situacao_sem_segredos(self):
        ativa = ativar_conta(self.root)
        acesso.criar_conta(self.root, 'Bia', 'bia', casos=['alpha'])
        desativada = ativar_conta(self.root, 'Caio', 'caio')
        acesso.criar_conta(self.root, 'Admin', 'admin', papel='admin')
        acesso.desativar(self.root, desativada['id'], por='cli')
        contas = {c['login']: c for c in acesso.listar(self.root)}
        self.assertEqual({k: c['situacao'] for k, c in contas.items()},
                         {'ana.silva': 'ativa', 'bia': 'aguardando_senha', 'caio': 'desativada', 'admin': 'aguardando_senha'})
        texto = json.dumps(contas)
        for segredo in ('senha_hash', 'token_sha256', '$argon2'):
            self.assertNotIn(segredo, texto)
        self.assertEqual(contas['ana.silva']['id'], ativa['id'])


class SessaoTest(Base):
    def setUp(self):
        super().setUp()
        self.conta = ativar_conta(self.root)

    def test_credencial_errada_conta_sem_senha_ou_inexistente_tem_a_mesma_recusa(self):
        acesso.criar_conta(self.root, 'Sem senha', 'semsenha', casos=['alpha'])
        for login, senha in (('ana.silva', 'errada-mas-longa'), ('ninguem', SENHA), ('semsenha', SENHA)):
            with self.subTest(login=login), self.assertRaises(acesso.CredenciaisInvalidas) as erro:
                acesso.entrar(self.root, login, senha)
            self.assertEqual(str(erro.exception), 'Login ou senha incorretos.')

    def test_login_inexistente_tambem_verifica_um_hash(self):
        espiao = MagicMock(wraps=RAPIDO)
        with patch.object(acesso, '_HASHER', espiao), patch.dict(acesso._FICTICIO, {id(espiao): RAPIDO.hash('x')}):
            with self.assertRaises(acesso.CredenciaisInvalidas):
                acesso.entrar(self.root, 'ninguem', SENHA)
        self.assertEqual(espiao.verify.call_count, 1)

    def test_cinco_falhas_bloqueiam_o_login_por_quinze_minutos(self):
        for _ in range(4):
            with self.assertRaises(acesso.CredenciaisInvalidas):
                acesso.entrar(self.root, 'ana.silva', 'errada-mas-longa')
        with self.assertRaises(acesso.Bloqueado):
            acesso.entrar(self.root, 'ana.silva', 'errada-mas-longa')
        with self.assertRaises(acesso.Bloqueado):
            acesso.entrar(self.root, 'ana.silva', SENHA)  # even the right password waits
        with self.depois(minutes=16):
            acesso.entrar(self.root, 'ana.silva', SENHA)
        tipos = [e['tipo'] for e in self.dados()['eventos']]
        self.assertIn('login_bloqueado', tipos)
        self.assertNotIn('login_falhou', tipos)  # single failures are not audited (keeps the 1000-event window)

    def test_bloqueio_vale_para_o_login_naquele_endereco(self):
        for _ in range(5):
            with self.assertRaises((acesso.CredenciaisInvalidas, acesso.Bloqueado)):
                acesso.entrar(self.root, 'ana.silva', 'errada-mas-longa', ip='198.51.100.1')
        with self.assertRaises(acesso.Bloqueado):
            acesso.entrar(self.root, 'ana.silva', SENHA, ip='198.51.100.1')
        acesso.entrar(self.root, 'ana.silva', SENHA, ip='198.51.100.2')  # the owner elsewhere still signs in

    def test_bloqueio_ativo_nao_e_descartado_pela_poda(self):
        for _ in range(5):
            with self.assertRaises((acesso.CredenciaisInvalidas, acesso.Bloqueado)):
                acesso.entrar(self.root, 'ana.silva', 'errada-mas-longa')
        with patch.object(acesso, 'MAX_TENTATIVAS_GUARDADAS', 3):
            for numero in range(6):
                with self.assertRaises(acesso.CredenciaisInvalidas):
                    acesso.entrar(self.root, f'outro{numero}', SENHA)
        with self.assertRaises(acesso.Bloqueado):
            acesso.entrar(self.root, 'ana.silva', SENHA)

    def test_sucesso_zera_as_falhas(self):
        for _ in range(4):
            with self.assertRaises(acesso.CredenciaisInvalidas):
                acesso.entrar(self.root, 'ana.silva', 'errada-mas-longa')
        acesso.entrar(self.root, 'ana.silva', SENHA)
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'ana.silva', 'errada-mas-longa')

    def test_limite_por_ip(self):
        for numero in range(20):
            with self.assertRaises(acesso.CredenciaisInvalidas):
                acesso.entrar(self.root, f'ninguem{numero}', SENHA, ip='203.0.113.9')
        with self.assertRaises(acesso.Bloqueado):
            acesso.entrar(self.root, 'ana.silva', SENHA, ip='203.0.113.9')
        acesso.entrar(self.root, 'ana.silva', SENHA, ip='203.0.113.10')
        with self.depois(seconds=61):
            acesso.entrar(self.root, 'ana.silva', SENHA, ip='203.0.113.9')

    def test_endereco_ipv4_conta_por_endereco_sem_erro(self):
        # Regression: IPv4Address has no ipv4_mapped; every IPv4 sign-in used to fail with AttributeError.
        self.assertEqual(acesso._rede('127.0.0.1'), '127.0.0.1')
        self.assertEqual(acesso._rede('::ffff:127.0.0.1'), '127.0.0.1')
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA, ip='127.0.0.1')
        self.assertIsNotNone(acesso.sessao(self.root, sid))

    def test_sessao_expira_por_inatividade_e_pelo_limite_absoluto(self):
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA)
        with self.depois(hours=1, minutes=59):
            self.assertIsNotNone(acesso.sessao(self.root, sid))  # renews last use
        with self.depois(hours=3, minutes=50):
            self.assertIsNotNone(acesso.sessao(self.root, sid))
        with self.depois(hours=6):
            self.assertIsNone(acesso.sessao(self.root, sid))  # more than 2 h idle
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA)
        for horas in range(1, 12):
            with self.depois(hours=horas):
                self.assertIsNotNone(acesso.sessao(self.root, sid))
        with self.depois(hours=12, seconds=1):
            self.assertIsNone(acesso.sessao(self.root, sid))

    def test_ultimo_uso_e_gravado_no_maximo_a_cada_minuto(self):
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA)
        antes = self.bruto()
        with self.depois(seconds=30):
            acesso.sessao(self.root, sid)
        self.assertEqual(antes, self.bruto())
        with self.depois(seconds=90):
            acesso.sessao(self.root, sid)
        self.assertNotEqual(antes, self.bruto())

    def test_logout_encerra_a_sessao(self):
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA)
        acesso.encerrar(self.root, sid)
        self.assertIsNone(acesso.sessao(self.root, sid))
        self.assertIn('sessao_encerrada', [e['tipo'] for e in self.dados()['eventos']])

    def test_desativar_derruba_sessoes_e_reativar_permite_entrar(self):
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA)
        acesso.desativar(self.root, self.conta['id'], por='cli')
        self.assertIsNone(acesso.sessao(self.root, sid))
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'ana.silva', SENHA)
        acesso.reativar(self.root, self.conta['id'], por='cli')
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA)
        self.assertIsNotNone(acesso.sessao(self.root, sid))

    def test_alterar_casos_e_cota_vale_na_requisicao_seguinte(self):
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA)
        acesso.atualizar(self.root, self.conta['id'], por='cli', casos=['beta'], cota_diaria=5)
        principal = acesso.sessao(self.root, sid)
        self.assertEqual((principal['casos'], principal['cota_diaria']), (['beta'], 5))

    def test_recuperacao_encerra_sessoes_zera_senha_e_emite_novo_link(self):
        sid, _, _ = acesso.entrar(self.root, 'ana.silva', SENHA)
        conta, token = acesso.recuperar(self.root, self.conta['id'], por='cli')
        self.assertEqual(conta['situacao'], 'aguardando_senha')
        self.assertIsNone(acesso.sessao(self.root, sid))
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'ana.silva', SENHA)
        self.assertEqual(self.dados()['contas'][self.conta['id']]['ativacao']['motivo'], 'recuperacao')
        acesso.ativar(self.root, token, 'nova-senha-longa-9')
        acesso.entrar(self.root, 'ana.silva', 'nova-senha-longa-9')

    def test_hash_antigo_e_atualizado_no_login(self):
        forte = PasswordHasher()
        with patch.object(acesso, '_HASHER', forte):
            acesso.entrar(self.root, 'ana.silva', SENHA)
        self.assertTrue(forte.verify(self.dados()['contas'][self.conta['id']]['senha_hash'], SENHA))
        self.assertFalse(forte.check_needs_rehash(self.dados()['contas'][self.conta['id']]['senha_hash']))

    def test_sessao_com_identificador_estranho_e_ignorada(self):
        for sid in (None, '', 'x', 'y' * 500, 123):
            self.assertIsNone(acesso.sessao(self.root, sid))


class AdministracaoTest(Base):
    def test_ultimo_admin_ativo_nao_pode_ser_desativado_nem_rebaixado(self):
        admin = ativar_conta(self.root, 'Editora', 'editora', papel='admin', casos=())
        with self.assertRaisesRegex(ValueError, 'último'):
            acesso.desativar(self.root, admin['id'], por='cli')
        with self.assertRaisesRegex(ValueError, 'último'):
            acesso.atualizar(self.root, admin['id'], por='cli', papel='convidado', casos=['alpha'])
        segunda = ativar_conta(self.root, 'Chefe', 'chefe', papel='admin', casos=())
        acesso.desativar(self.root, admin['id'], por=segunda['id'])
        with self.assertRaisesRegex(ValueError, 'último'):
            acesso.desativar(self.root, segunda['id'], por=segunda['id'])

    def test_eventos_nao_contem_segredos_e_sao_limitados(self):
        conta, token = acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        acesso.ativar(self.root, token, SENHA)
        sid, csrf, _ = acesso.entrar(self.root, 'ana', SENHA)
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'ana', 'outra-senha-errada')
        _, token2 = acesso.recuperar(self.root, conta['id'], por='cli')
        eventos = json.dumps(self.dados()['eventos'])
        for segredo in (token, token2, sid, csrf, SENHA, 'outra-senha-errada', '$argon2'):
            self.assertNotIn(segredo, eventos)
        self.assertTrue({'conta_criada', 'senha_definida', 'recuperacao_emitida'}
                        <= {e['tipo'] for e in self.dados()['eventos']})
        dados = self.dados()
        dados['eventos'] = [{'em': '2026-01-01T00:00:00Z', 'tipo': 'conta_criada', 'conta': 'x', 'por': 'cli'}] * 1200
        (self.root / 'acesso/acesso.json').write_text(json.dumps(dados), encoding='utf-8')
        acesso.desativar(self.root, conta['id'], por='cli')
        self.assertEqual(len(self.dados()['eventos']), 1000)
        self.assertEqual(self.dados()['eventos'][-1]['tipo'], 'conta_desativada')

    def test_atualizar_valida_campos(self):
        conta = ativar_conta(self.root)
        for kwargs in ({'casos': []}, {'casos': ['../x']}, {'cota_diaria': 0}, {'papel': 'root'}, {'nome': ''}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                acesso.atualizar(self.root, conta['id'], por='cli', **kwargs)
        with self.assertRaises(ValueError):
            acesso.atualizar(self.root, 'inexistente', por='cli', casos=['alpha'])


class CotaTest(Base):
    def test_cota_diaria_por_conta_e_admin_sem_cota(self):
        conta = ativar_conta(self.root, cota=2)
        acesso.registrar_consulta(self.root, conta['id'])
        acesso.registrar_consulta(self.root, conta['id'])
        with self.assertRaisesRegex(ValueError, 'Limite diário'):
            acesso.registrar_consulta(self.root, conta['id'])
        admin = ativar_conta(self.root, 'Grupo', 'grupo', papel='admin', casos=())
        for _ in range(5):
            acesso.registrar_consulta(self.root, admin['id'])

    def test_consulta_devolvida_volta_para_a_cota(self):
        conta = ativar_conta(self.root, cota=1)
        acesso.registrar_consulta(self.root, conta['id'])
        acesso.devolver_consulta(self.root, conta['id'])
        acesso.registrar_consulta(self.root, conta['id'])

    def test_conta_desativada_nao_consome_cota(self):
        conta = ativar_conta(self.root, cota=5)
        acesso.desativar(self.root, conta['id'], por='cli')
        with self.assertRaises(ValueError):
            acesso.registrar_consulta(self.root, conta['id'])

    def test_registros_simultaneos_nao_perdem_contagem(self):
        conta = ativar_conta(self.root, cota=500)
        threads = [threading.Thread(target=acesso.registrar_consulta, args=(self.root, conta['id'])) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(acesso.registrar_consulta(self.root, conta['id']), 21)

    def test_arquivo_de_acesso_corrompido_gera_erro_claro(self):
        (self.root / 'acesso').mkdir()
        (self.root / 'acesso/acesso.json').write_text('[]', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'ilegível'):
            acesso.listar(self.root)


class MigracaoTest(Base):
    def v1(self):
        dados = {'versao': 1, 'convites': {
            'aaaa000011112222': {'nome': 'Grupo VLADO', 'papel': 'admin', 'casos': None, 'cota_diaria': None,
                                 'expira_em': '2099-01-01T00:00:00Z', 'criado_em': '2026-01-01T00:00:00Z',
                                 'revogado': False, 'token_sha256': 'a' * 64},
            'bbbb000011112222': {'nome': 'Ana Sílvia', 'papel': 'convidado', 'casos': ['alpha'], 'cota_diaria': 7,
                                 'expira_em': '2026-01-02T00:00:00Z', 'criado_em': '2026-01-01T00:00:01Z',
                                 'revogado': False, 'token_sha256': 'b' * 64},
            'cccc000011112222': {'nome': 'Ana Sílvia', 'papel': 'convidado', 'casos': ['beta'], 'cota_diaria': 3,
                                 'expira_em': '2099-01-01T00:00:00Z', 'criado_em': '2026-01-01T00:00:02Z',
                                 'revogado': True, 'token_sha256': 'c' * 64},
            'dddd000011112222': {'nome': 'X', 'papel': 'convidado', 'casos': ['alpha'], 'cota_diaria': 1,
                                 'expira_em': '2099-01-01T00:00:00Z', 'criado_em': '2026-01-01T00:00:03Z',
                                 'revogado': False, 'token_sha256': 'd' * 64}},
            'sessoes': {'e' * 64: {'convite': 'aaaa000011112222', 'csrf': 'z', 'criada_em': '2026-01-01T00:00:00Z',
                                   'expira_em': '2099-01-01T00:00:00Z'}},
            'uso': {'bbbb000011112222': {'2026-01-01': 2}}}
        (self.root / 'acesso').mkdir()
        texto = json.dumps(dados)
        (self.root / 'acesso/acesso.json').write_text(texto, encoding='utf-8')
        return texto

    def test_migracao_preserva_ids_descarta_sessoes_e_guarda_copia_v1(self):
        original = self.v1()
        contas = {c['id']: c for c in acesso.listar(self.root)}
        self.assertEqual(set(contas), {'aaaa000011112222', 'bbbb000011112222', 'cccc000011112222', 'dddd000011112222'})
        self.assertEqual((self.root / 'acesso/acesso.v1.json').read_text(encoding='utf-8'), original)
        dados = self.dados()
        self.assertEqual(dados['versao'], 2)
        self.assertEqual(dados['sessoes'], {})
        self.assertNotIn('convites', dados)
        admin, ana, revogada, curta = (contas[k] for k in sorted(contas))
        self.assertEqual((admin['papel'], admin['login'], admin['situacao']), ('admin', 'grupo.vlado', 'aguardando_senha'))
        self.assertEqual((ana['login'], ana['casos'], ana['cota_diaria'], ana['situacao']),
                         ('ana.silvia', ['alpha'], 7, 'aguardando_senha'))  # expired invitation: active, no password
        self.assertEqual((revogada['login'], revogada['situacao']), ('ana.silvia-2', 'desativada'))
        self.assertTrue(acesso.LOGIN.fullmatch(curta['login']))
        self.assertTrue(all(c.get('migrada_de_convite') for c in dados['contas'].values()))
        self.assertEqual(dados['uso'], {'bbbb000011112222': {'2026-01-01': 2}})
        self.assertIn('migracao_v1', {e['tipo'] for e in dados['eventos']})

    def test_conta_migrada_entra_depois_da_recuperacao_e_mantem_o_id(self):
        self.v1()
        conta, token = acesso.recuperar(self.root, 'bbbb000011112222', por='cli')
        acesso.ativar(self.root, token, SENHA)
        sid, _, publica = acesso.entrar(self.root, 'ana.silvia', SENHA)
        self.assertEqual(publica['id'], 'bbbb000011112222')
        self.assertEqual(acesso.sessao(self.root, sid)['conta'], 'bbbb000011112222')

    def test_registro_de_versao_desconhecida_nao_e_migrado_por_cima(self):
        (self.root / 'acesso').mkdir()
        for conteudo in ({}, {'versao': 3, 'contas': {}}, {'versao': '2'}):
            (self.root / 'acesso/acesso.json').write_text(json.dumps(conteudo), encoding='utf-8')
            with self.subTest(conteudo=conteudo), self.assertRaisesRegex(ValueError, 'ilegível'):
                acesso.listar(self.root)
        self.assertFalse((self.root / 'acesso/acesso.v1.json').exists())

    def test_migracao_nao_sobrescreve_copia_v1_existente(self):
        self.v1()
        (self.root / 'acesso/acesso.v1.json').write_text('anterior', encoding='utf-8')
        acesso.listar(self.root)
        self.assertEqual((self.root / 'acesso/acesso.v1.json').read_text(encoding='utf-8'), 'anterior')
        self.assertTrue(any(p.name.startswith('acesso.v1.') and p.name != 'acesso.v1.json'
                            for p in (self.root / 'acesso').iterdir()))


class CliTest(Base):
    def cli(self, *args):
        saida = io.StringIO()
        with patch.object(acesso, 'ROOT', self.root), patch.object(sys, 'argv', ['acesso.py', *args]), redirect_stdout(saida):
            codigo = acesso._principal()
        return codigo, saida.getvalue()

    def test_criar_admin_imprime_link_uma_vez_e_listar_nao_mostra_segredos(self):
        codigo, saida = self.cli('criar-admin', '--nome', 'Grupo', '--login', 'grupo', '--origem', 'https://vlado.test/')
        self.assertEqual(codigo, 0)
        link = next(linha for linha in saida.splitlines() if 'https://vlado.test/ativar/' in linha)
        token = link.rsplit('/ativar/', 1)[1].strip()
        self.assertEqual(acesso.consultar_ativacao(self.root, token)['login'], 'grupo')
        _, listagem = self.cli('listar')
        self.assertNotIn(token, listagem)
        self.assertIn('grupo', listagem)
        self.assertNotIn(token, self.bruto())

    def test_saida_em_arquivo_nao_imprime_o_link(self):
        destino = self.root / 'link.txt'
        _, saida = self.cli('criar-conta', '--nome', 'Ana', '--login', 'ana', '--casos', 'alpha,beta', '--cota', '5',
                            '--origem', 'https://vlado.test', '--horas', '24', '--saida', str(destino))
        self.assertNotIn('/ativar/', saida)
        self.assertIn('https://vlado.test/ativar/', destino.read_text(encoding='utf-8'))
        if os.name != 'nt':
            self.assertEqual(destino.stat().st_mode & 0o777, 0o600)
        conta = acesso.listar(self.root)[0]
        self.assertEqual((conta['casos'], conta['cota_diaria']), (['alpha', 'beta'], 5))

    def test_desativar_reativar_recuperar_e_casos(self):
        conta = ativar_conta(self.root)
        self.cli('desativar', conta['id'])
        self.assertEqual(acesso.listar(self.root)[0]['situacao'], 'desativada')
        self.cli('reativar', conta['id'])
        self.cli('casos', conta['id'], '--casos', 'beta')
        self.assertEqual(acesso.listar(self.root)[0]['casos'], ['beta'])
        _, saida = self.cli('recuperar', conta['id'], '--origem', 'https://vlado.test')
        self.assertIn('https://vlado.test/ativar/', saida)
        self.assertEqual(acesso.listar(self.root)[0]['situacao'], 'aguardando_senha')
        self.assertTrue(all(e['por'] == 'cli' for e in self.dados()['eventos'] if e['tipo'] != 'senha_definida'))

    def test_cli_recusa_erro_com_codigo_1(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/acesso.py'
        resultado = subprocess.run([sys.executable, str(script), 'desativar', 'inexistente'], capture_output=True,
                                   text=True, env={**os.environ, 'VLADO_ACESSO': str(self.root / 'acesso/acesso.json')},
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(resultado.returncode, 1)
        self.assertIn('Erro:', resultado.stderr)


if __name__ == '__main__':
    unittest.main()
