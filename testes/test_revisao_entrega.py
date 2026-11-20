"""Regressions for the integrated security review of the Intercept delivery."""
import json
import os
import stat
import sys
import tarfile
import tempfile
import unittest
from auxiliar_node import pular_ou_falhar
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import acesso  # noqa: E402
import backup  # noqa: E402
import empacotar_entrega  # noqa: E402
import semear_ambiente  # noqa: E402
import test_codex_integracao as base  # noqa: E402


class BackupAmbienteTest(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.root = Path(pasta.name) / 'origem'
        (self.root / 'casos').mkdir(parents=True)
        (self.root / 'casos/catalogo.json').write_text('{"casos": []}', encoding='utf-8')
        self.saida = Path(pasta.name) / 'backups'

    def _criar(self, ambiente):
        with mock.patch.dict(os.environ, {'VLADO_AMBIENTE': ambiente}):
            return backup.criar(self.root, self.saida)

    def test_manifesto_registra_ambiente_e_restauracao_recusa_outro(self):
        arquivo = self._criar('editorial')
        with tarfile.open(arquivo) as pacote:
            manifesto = json.loads(pacote.extractfile(backup.MANIFESTO).read())
        self.assertEqual(manifesto['ambiente'], 'editorial')
        destino = self.root.parent / 'demo'
        with mock.patch.dict(os.environ, {'VLADO_AMBIENTE': 'demonstracao'}):
            with self.assertRaisesRegex(ValueError, 'ambiente'):
                backup.restaurar(destino, arquivo)
            self.assertFalse((destino / 'casos').exists())
            self.assertEqual(backup.restaurar(destino, arquivo, outro_ambiente=True), ['casos'])

    @unittest.skipIf(os.name == 'nt', 'permissões POSIX')
    def test_arquivo_de_backup_so_do_dono(self):
        arquivo = self._criar('homologacao')
        self.assertEqual(stat.S_IMODE(arquivo.stat().st_mode), 0o600)


class AcessoRevisaoTest(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.root = Path(pasta.name)
        env = mock.patch.dict(os.environ, {'VLADO_ACESSO': str(self.root / 'acesso/acesso.json')})
        env.start()
        self.addCleanup(env.stop)
        acesso.limpar_limites()

    def test_desativar_invalida_link_de_ativacao_pendente(self):
        acesso.criar_conta(self.root, 'Admin', 'admin.um', papel='admin')
        registro, token = acesso.criar_conta(self.root, 'Ana', 'ana.silva', casos=['caso_a'])
        acesso.desativar(self.root, registro['id'])
        acesso.reativar(self.root, registro['id'])
        with self.assertRaises(ValueError):
            acesso.ativar(self.root, token, 'uma senha bem longa 123')

    def test_ipv6_conta_por_rede_64(self):
        self.assertEqual(acesso._rede('2001:db8:1:2:aaaa::1'), acesso._rede('2001:db8:1:2:bbbb::9'))
        self.assertNotEqual(acesso._rede('2001:db8:1:2::1'), acesso._rede('2001:db8:1:3::1'))
        self.assertEqual(acesso._rede('::ffff:10.0.0.7'), '10.0.0.7')
        self.assertEqual(acesso._chave_tentativa('ana', '2001:db8:1:2::5'), 'ana|2001:db8:1:2::/64')


class SemearRecusaTest(unittest.TestCase):
    def setUp(self):
        fixture = base.CodexIntegrationTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root  # holds cases 'alpha' and 'beta' registered as synthetic
        env = mock.patch.dict(os.environ, {'VLADO_ACESSO': str(self.root / 'acesso/acesso.json')})
        env.start()
        self.addCleanup(env.stop)

    def test_recusa_instalacao_com_conta_real_mesmo_com_ambiente_sintetico(self):
        acesso.criar_conta(self.root, 'Editora', 'editora.real', papel='admin')
        with self.assertRaisesRegex(SystemExit, 'contas'):
            semear_ambiente.semear(self.root, 'demonstracao', 'https://x.invalid', self.root / 'l.txt')

    def test_recusa_caso_nao_sintetico(self):
        manifesto = self.root / 'casos/alpha/manifesto.json'
        dados = json.loads(manifesto.read_text(encoding='utf-8'))
        dados['natureza_informada'] = 'publicos'
        manifesto.write_text(json.dumps(dados), encoding='utf-8')
        with self.assertRaisesRegex(SystemExit, 'alpha'):
            semear_ambiente.semear(self.root, 'homologacao', 'https://x.invalid', self.root / 'l.txt')


class EmpacotarRevisaoTest(unittest.TestCase):
    def test_novos_padroes_proibidos(self):
        ruins = ['referencia_original/a.pdf', 'transferencia/x', 'distribuicao/y.zip', '.claude-flow/m.json',
                 'backups/v.tar', 'manifesto_distribuicao.json', 'docs/VLADO_HANDOFF.md', 'log/eventos.jsonl']
        self.assertEqual(empacotar_entrega.proibidos(ruins), ruins)

    def test_pastas_de_agentes_ficam_fora_e_o_contrato_entra(self):
        ruins = ['.claude/settings.local.json', '.claude/agents/x.md', '.maestri/roles/a/CLAUDE.md',
                 '.maestro/equipe/PLANO_LANCAMENTO.md', '.maestro/playbooks/p/Working/n.md',
                 '.maestro/CONTRATO_EVIDENCIA.md', '.maestro/equipe/CONTRATO_EVIDENCIA.md.orig',
                 '.maestro/equipe/sub/CONTRATO_X.md', 'android/.claude/x.json']
        self.assertEqual(empacotar_entrega.proibidos(ruins), ruins)
        bons = ['.maestro/equipe/CONTRATO_EVIDENCIA.md', '.maestro/equipe/CONTRATO_CONTAS.md',
                'docs/claude.md', 'docs/maestro.md', '.dockerignore']
        self.assertEqual(empacotar_entrega.proibidos(bons), [])

    def test_pastas_de_agentes_em_qualquer_caixa_e_contrato_so_na_raiz(self):
        ruins = ['.Maestro/equipe/PLANO.md', '.MAESTRO/x.md', '.Claude/settings.json', 'docs/.CLAUDE/a.md',
                 '.Maestri/roles/a.md', '.codex/config.toml', '.Codex/x', '.agents/a.md', 'sub/.agents/b.md',
                 '.cursor/rules/r.mdc', '.CURSOR/x',
                 # The contract exception holds only at the root and in the exact spelling of .gitignore.
                 'tmp/.maestro/equipe/CONTRATO_X.md', 'a/b/.maestro/equipe/CONTRATO_EVIDENCIA.md',
                 '.Maestro/equipe/CONTRATO_X.md', '.maestro/Equipe/CONTRATO_X.md',
                 '.maestro/equipe/contrato_x.md', '.maestro/equipe/CONTRATO_X.MD']
        self.assertEqual(empacotar_entrega.proibidos(ruins), ruins)
        bons = ['.maestro/equipe/CONTRATO_contas.md', '.maestro/equipe/CONTRATO_Contas-v2.md',
                '.maestro/equipe/CONTRATO_.md', 'docs/codex.md', 'scripts/codex_apuracao.py', 'agents.md',
                'docs/cursor.md', '.claude-flow-nao/x']
        self.assertEqual(empacotar_entrega.proibidos(bons), [])

    def test_contrato_versionado_pelo_gitignore_e_o_que_o_pacote_aceita(self):
        # Same names, exact case: git versions a file under .maestro/equipe/ exactly when the
        # package lets it in, so a tracked contract never makes the whole delivery refuse.
        import shutil
        import subprocess
        if shutil.which('git') is None:
            pular_ou_falhar(self, 'VLADO_EXIGIR_GIT', 'git indisponível')
        raiz = Path(__file__).resolve().parents[1]
        nomes = ['CONTRATO_EVIDENCIA.md', 'CONTRATO_contas.md', 'CONTRATO_Contas v2.md', 'CONTRATO_.md',
                 'CONTRATO_X.md.orig', 'CONTRATO_X.txt', 'PLANO_LANCAMENTO.md', 'sub/CONTRATO_X.md']
        for nome in nomes:
            caminho = f'.maestro/equipe/{nome}'
            codigo = subprocess.run(['git', '-C', str(raiz), 'check-ignore', '--no-index', '-q', caminho],
                                    capture_output=True).returncode
            if codigo not in (0, 1):
                # 128: no repository here (an extracted delivery package has no .git).
                pular_ou_falhar(self, 'VLADO_EXIGIR_GIT', f'git check-ignore indisponível aqui (código {codigo})')
            ignorado = codigo == 0
            barrado = bool(empacotar_entrega.proibidos([caminho]))
            self.assertEqual(ignorado, barrado, caminho)


if __name__ == '__main__':
    unittest.main()
