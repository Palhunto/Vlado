"""Backup and restore of the pilot's data folders; no network."""
import io
import json
import os
from pathlib import Path
import sqlite3
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

    def contas(self):
        """The accounts module on a store of its own in ``self.root`` (no JSON store left), with the fast hasher."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        import acesso
        from test_acesso import RAPIDO
        for ativo in (patch.dict('os.environ', {'VLADO_ACESSO': ''}), patch.object(acesso, '_HASHER', RAPIDO)):
            ativo.start()
            self.addCleanup(ativo.stop)
        (self.root / 'acesso/acesso.json').unlink()
        return acesso

    def test_contas_voltam_com_a_restauracao_e_as_sessoes_do_backup_nao_voltam_vivas(self):
        acesso = self.contas()
        conta, token = acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        acesso.ativar(self.root, token, 'senha-longa-de-teste-1')
        arquivo = backup.criar(self.root, self.base / 'copias')
        destino = self.base / 'destino'
        backup.restaurar(destino, arquivo)
        sid, _, _ = acesso.entrar(self.root, 'ana', 'senha-longa-de-teste-1')
        self.assertIsNotNone(acesso.sessao(self.root, sid))
        arquivo = backup.criar(self.root, self.base / 'copias2')
        with tarfile.open(arquivo) as pacote:  # the session was in the store that went into the backup
            copia = self.base / 'conferencia.sqlite'
            copia.write_bytes(pacote.extractfile('acesso/contas.sqlite').read())
        ligacao = sqlite3.connect(copia)
        try:
            self.assertEqual(ligacao.execute('SELECT COUNT(*) FROM sessoes').fetchone()[0], 1)
        finally:
            ligacao.close()
        destino = self.base / 'destino2'
        backup.restaurar(destino, arquivo)
        self.assertIsNone(acesso.sessao(destino, sid))  # sessions in a backup do not survive the restore
        self.assertIsNotNone(acesso.sessao(self.root, sid))  # and the one in use where the backup was made goes on
        _, _, publica = acesso.entrar(destino, 'ana', 'senha-longa-de-teste-1')
        self.assertEqual(publica['id'], conta['id'])
        if os.name != 'nt':
            self.assertEqual((destino / 'acesso/contas.sqlite').stat().st_mode & 0o777, 0o600)

    def test_restaurar_por_cima_de_contas_em_uso_tambem_encerra_as_sessoes_do_backup(self):
        acesso = self.contas()
        _, token = acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        acesso.ativar(self.root, token, 'senha-longa-de-teste-1')
        do_backup, _, _ = acesso.entrar(self.root, 'ana', 'senha-longa-de-teste-1')
        arquivo = backup.criar(self.root, self.base / 'copias')
        acesso.encerrar(self.root, do_backup)  # ended after the backup: the backup still holds it
        backup.restaurar(self.root, arquivo, substituir=True)
        acesso._PRONTOS.clear()  # the store on disk is another one now
        self.assertIsNone(acesso.sessao(self.root, do_backup))
        self.assertEqual(acesso.encerrar_todas_as_sessoes(self.root), 0)

    def test_backup_das_contas_e_uma_copia_consistente_com_o_que_ainda_esta_no_diario(self):
        acesso = self.contas()
        acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        banco = acesso.caminho_bd(self.root)
        self.assertEqual(banco.name, backup.BANCO_DE_CONTAS)  # the names this script uses are the store's
        aberta = sqlite3.connect(banco)  # a connection kept open: later writes stay in the write-ahead log
        try:
            self.assertEqual(aberta.execute(f'SELECT COUNT(*) FROM {backup.TABELA_DE_SESSOES}').fetchone()[0], 0)
            bia, _ = acesso.criar_conta(self.root, 'Bia', 'bia', casos=['alpha'])
            diario = banco.with_name(banco.name + '-wal')
            self.assertGreater(diario.stat().st_size, 0)
            sozinho = self.base / 'so-o-arquivo.sqlite'  # the file alone does not have Bia yet
            sozinho.write_bytes(banco.read_bytes())
            so_arquivo = sqlite3.connect(sozinho.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
            try:
                self.assertEqual(so_arquivo.execute("SELECT COUNT(*) FROM contas WHERE login = 'bia'").fetchone()[0], 0)
            finally:
                so_arquivo.close()
            arquivo = backup.criar(self.root, self.base / 'copias')
        finally:
            aberta.close()
        with tarfile.open(arquivo) as pacote:
            nomes = [n for n in pacote.getnames() if n.startswith('acesso/')]
            manifesto = json.loads(pacote.extractfile('manifesto_backup.json').read())
        self.assertEqual(nomes, ['acesso/contas.sqlite'])  # no log, no index, no lock file
        self.assertEqual(manifesto['avisos'], [])
        destino = self.base / 'destino'
        backup.restaurar(destino, arquivo)
        self.assertEqual({c['login'] for c in acesso.listar(destino)}, {'ana', 'bia'})
        self.assertIn(bia['id'], {c['id'] for c in acesso.listar(destino)})

    def test_sem_abrir_o_banco_pela_api_o_backup_copia_o_arquivo_e_avisa_se_havia_diario(self):
        acesso = self.contas()
        acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        with patch.object(backup, '_copia_do_banco', return_value=None):
            arquivo = backup.criar(self.root, self.base / 'copias')
            with tarfile.open(arquivo) as pacote:
                self.assertEqual(json.loads(pacote.extractfile('manifesto_backup.json').read())['avisos'], [])
            aberta = sqlite3.connect(acesso.caminho_bd(self.root))
            try:
                aberta.execute('SELECT 1 FROM contas').fetchall()
                acesso.criar_conta(self.root, 'Bia', 'bia', casos=['alpha'])
                arquivo = backup.criar(self.root, self.base / 'copias2')
            finally:
                aberta.close()
        with tarfile.open(arquivo) as pacote:
            avisos = json.loads(pacote.extractfile('manifesto_backup.json').read())['avisos']
            self.assertEqual([n for n in pacote.getnames() if n.startswith('acesso/')], ['acesso/contas.sqlite'])
        self.assertEqual(len(avisos), 1)
        self.assertIn('acesso/contas.sqlite: copiado sem o diário de escrita', avisos[0])
        destino = self.base / 'destino'
        backup.restaurar(destino, arquivo)
        self.assertEqual([c['login'] for c in acesso.listar(destino)], ['ana'])  # whole, and older

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
