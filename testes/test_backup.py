"""Backup and restore of the pilot's data folders; no network."""
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import backup


class BackupTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'origem'
        for relativo, conteudo in {'casos/catalogo.json': '{"casos": []}', 'conversas/a/conversa.json': '{}',
                                   'execucoes/c/R001/registro.json': '{}', 'acesso/acesso.json': '{"convites": {}}',
                                   'ajustes/inferencia.json': '{}', 'segredos/chaves.json': '{"anthropic": "sk-ant-x"}'}.items():
            arquivo = self.root / relativo
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(conteudo, encoding='utf-8')

    def test_backup_restaura_dados_e_omite_chaves_por_padrao(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        self.assertTrue(arquivo.name.startswith('vlado-dados-') and arquivo.name.endswith('.tar.gz'))
        with tarfile.open(arquivo) as pacote:
            nomes = pacote.getnames()
        self.assertIn('conversas/a/conversa.json', nomes)
        self.assertIn('manifesto_backup.json', nomes)
        self.assertFalse(any(n.startswith('segredos') for n in nomes))
        destino = self.base / 'destino'
        backup.restaurar(destino, arquivo)
        self.assertEqual((destino / 'acesso/acesso.json').read_text(encoding='utf-8'), '{"convites": {}}')
        self.assertFalse((destino / 'segredos').exists())

    def test_backup_com_chaves_somente_quando_pedido(self):
        arquivo = backup.criar(self.root, self.base / 'copias', incluir_segredos=True)
        with tarfile.open(arquivo) as pacote:
            self.assertIn('segredos/chaves.json', pacote.getnames())

    def test_restaurar_recusa_sobrescrever_dados_existentes_sem_confirmacao(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        with self.assertRaisesRegex(ValueError, 'já contém dados'):
            backup.restaurar(self.root, arquivo)
        backup.restaurar(self.root, arquivo, substituir=True)

    def test_falha_no_meio_da_restauracao_preserva_os_dados_atuais(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        (self.root / 'conversas/a/conversa.json').write_text('{"atual": true}', encoding='utf-8')
        chamadas = {'n': 0}
        original = backup.shutil.copyfileobj

        def falha_no_segundo(origem, destino, *args):
            chamadas['n'] += 1
            if chamadas['n'] == 2:
                raise OSError('disco cheio (simulado)')
            return original(origem, destino, *args)

        with patch('backup.shutil.copyfileobj', side_effect=falha_no_segundo):
            with self.assertRaises(OSError):
                backup.restaurar(self.root, arquivo, substituir=True)
        self.assertEqual((self.root / 'conversas/a/conversa.json').read_text(encoding='utf-8'), '{"atual": true}')
        self.assertTrue((self.root / 'casos/catalogo.json').is_file())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith('.')], [])

    def test_contas_de_acesso_v2_voltam_com_a_restauracao(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        import acesso
        from test_acesso import RAPIDO
        with patch.dict('os.environ', {'VLADO_ACESSO': ''}), patch.object(acesso, '_HASHER', RAPIDO):
            (self.root / 'acesso/acesso.json').unlink()
            conta, token = acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
            acesso.ativar(self.root, token, 'senha-longa-de-teste-1')
            arquivo = backup.criar(self.root, self.base / 'copias')
            destino = self.base / 'destino'
            backup.restaurar(destino, arquivo)
            sid, _, _ = acesso.entrar(self.root, 'ana', 'senha-longa-de-teste-1')
            arquivo = backup.criar(self.root, self.base / 'copias2')
            destino = self.base / 'destino2'
            backup.restaurar(destino, arquivo)
            self.assertIsNone(acesso.sessao(destino, sid))  # sessions in a backup do not survive the restore
            _, _, publica = acesso.entrar(destino, 'ana', 'senha-longa-de-teste-1')
        self.assertEqual(publica['id'], conta['id'])
        if os.name != 'nt':
            self.assertEqual((destino / 'acesso/acesso.json').stat().st_mode & 0o777, 0o600)

    def test_restauracao_grava_dentro_de_volumes_sem_renomear_os_pontos_de_montagem(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        destino = self.base / 'volumes'
        for pasta in backup.PASTAS:  # mount points of fresh Docker volumes: may exist, empty, never renamed
            (destino / pasta).mkdir(parents=True)
        (destino / 'casos/antigo.json').write_text('{}', encoding='utf-8')
        identidade = {p: (destino / p).stat().st_ino for p in backup.PASTAS}
        montagens = {str((destino / p).resolve()) for p in backup.PASTAS}
        original_rename, original_replace = Path.rename, Path.replace

        def recusa_ponto_de_montagem(original):
            def chamar(origem, alvo):
                if str(Path(origem).resolve()) in montagens or str(Path(alvo).resolve()) in montagens:
                    raise OSError(16, 'Device or resource busy (ponto de montagem simulado)')
                return original(origem, alvo)
            return chamar

        with patch.object(Path, 'rename', recusa_ponto_de_montagem(original_rename)), \
                patch.object(Path, 'replace', recusa_ponto_de_montagem(original_replace)):
            backup.restaurar(destino, arquivo, substituir=True)
        self.assertEqual({p: (destino / p).stat().st_ino for p in backup.PASTAS}, identidade)
        self.assertEqual((destino / 'conversas/a/conversa.json').read_text(encoding='utf-8'), '{}')
        self.assertFalse((destino / 'casos/antigo.json').exists())
        self.assertEqual([p.name for p in destino.rglob('.*')], [])

    def test_falha_com_volumes_preserva_o_conteudo_anterior(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        (self.root / 'conversas/a/conversa.json').write_text('{"atual": true}', encoding='utf-8')
        original = backup.shutil.move
        chamadas = {'n': 0}

        def falha_no_meio(origem, alvo, *args, **kwargs):
            chamadas['n'] += 1
            if chamadas['n'] == 9:
                raise OSError('disco cheio (simulado)')
            return original(origem, alvo, *args, **kwargs)

        with patch('backup.shutil.move', side_effect=falha_no_meio):
            with self.assertRaises(OSError):
                backup.restaurar(self.root, arquivo, substituir=True)
        self.assertEqual((self.root / 'conversas/a/conversa.json').read_text(encoding='utf-8'), '{"atual": true}')
        self.assertTrue((self.root / 'casos/catalogo.json').is_file())
        self.assertEqual([p.name for p in self.root.rglob('.*')], [])

    def test_restaurar_recusa_caminhos_fora_das_pastas_de_dados(self):
        malicioso = self.base / 'malicioso.tar.gz'
        with tarfile.open(malicioso, 'w:gz') as pacote:
            for nome in ('../fora.txt', 'scripts/acesso.py', 'casos/../../fora.txt', 'casos/..\\..\\fora.txt', 'casos/C:fora'):
                dados = b'x'
                info = tarfile.TarInfo(nome)
                info.size = len(dados)
                pacote.addfile(info, io.BytesIO(dados))
        with self.assertRaisesRegex(ValueError, 'fora das pastas de dados'):
            backup.restaurar(self.base / 'novo', malicioso)
        self.assertFalse((self.base / 'fora.txt').exists())


if __name__ == '__main__':
    unittest.main()
