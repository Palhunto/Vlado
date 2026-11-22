"""O que a pessoa mandou apagar fica em quarentena em `<volume>/.apagando/<id>/` (casos, conversas e execucoes) até a Mesa terminar de
remover em segundo plano, e o manifesto de cada apagamento em curso em `lixeira/.apagando/<item>.json`. É dado apagado: o backup nunca o
leva, e não espera por ele. Fixture e dublês de test_backup_agendado."""
import json
from pathlib import Path
import sys
import tarfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup
from test_backup_agendado import Base

SEGREDO = 'conteudo que a pessoa mandou apagar'
VOLUMES = ('casos', 'conversas', 'execucoes', 'lixeira')  # a quarentena da Plataforma (apagamento.py, QUARENTENA)


class ApagandoFicaForaDoBackupTest(Base):
    def quarentena(self):
        for volume in VOLUMES:
            alvo = self.root / volume / '.apagando' / 'a1b2c3d4' / 'dado'
            alvo.mkdir(parents=True)
            (alvo / 'documento.txt').write_text(SEGREDO, encoding='utf-8')
            (alvo / 'manifesto.json').write_text('{"apagado": true}', encoding='utf-8')
            (self.root / volume / '.apagando' / 'leia-me.json').write_text('{}', encoding='utf-8')
        manifesto = self.root / 'lixeira' / '.apagando' / 'item-123.json'
        manifesto.write_text(json.dumps({'id': 'item-123', 'tipo': 'caso', 'caso': 'c1', 'fase': 'removendo',
                                         'caminhos': ['casos/.apagando/a1b2c3d4/dado']}), encoding='utf-8')

    def nomes(self, arquivo):
        with tarfile.open(arquivo) as pacote:
            return pacote.getnames()

    def test_as_tres_pastas_apagando_ficam_fora_do_arquivo_e_do_manifesto(self):
        self.quarentena()
        arquivo = backup.criar(self.root, self.base / 'copias')
        nomes = self.nomes(arquivo)
        self.assertFalse([n for n in nomes if '.apagando' in n], [n for n in nomes if '.apagando' in n])
        with tarfile.open(arquivo) as pacote:
            manifesto = json.loads(pacote.extractfile('manifesto_backup.json').read())
            bruto = b''.join(pacote.extractfile(m).read() for m in pacote.getmembers() if m.isfile())
        self.assertFalse([n for n in manifesto['arquivos'] if '.apagando' in n])
        self.assertNotIn(SEGREDO.encode(), bruto, 'o conteúdo apagado não está em lugar nenhum do arquivo')
        for volume in VOLUMES:
            self.assertIn(f'{volume}', nomes)  # a pasta em si continua no backup

    def test_o_resto_dos_dados_continua_entrando(self):
        self.quarentena()
        nomes = self.nomes(backup.criar(self.root, self.base / 'copias'))
        for esperado in ('casos/c1/originais/D001.txt', 'conversas/c1/conversa.json', 'execucoes/c1/R001/registro.json',
                         'lixeira/indice.json'):  # o índice dos itens que a pessoa ainda pode restaurar continua no backup
            self.assertIn(esperado, nomes)
        self.assertFalse([n for n in nomes if n.startswith('lixeira/.apagando')], 'o manifesto do apagamento em curso fica fora')

    def test_nao_faz_o_backup_esperar_nem_recusar(self):
        """Diferente de um marcador (.lote_*, .indice_*...), a quarentena não é operação em curso: o backup não espera por ela."""
        self.quarentena()
        self.assertEqual(backup._marcadores(self.root, backup.PASTAS), [])
        arquivo = backup.criar(self.root, self.base / 'copias')  # com espera 0, um marcador levantaria BackupOcupado
        self.assertTrue(arquivo.is_file())

    def test_a_restauracao_nao_traz_a_quarentena_de_volta(self):
        self.quarentena()
        arquivo = backup.criar(self.root, self.base / 'copias')
        destino = self.base / 'destino'
        backup.restaurar(destino, arquivo)
        for volume in VOLUMES:
            self.assertFalse((destino / volume / '.apagando').exists(), volume)
        self.assertEqual((destino / 'casos/c1/originais/D001.txt').read_text(encoding='utf-8'), 'documento sintético')

    def test_so_a_raiz_de_cada_volume_e_excluida(self):
        """O prefixo vale na raiz de casos/, conversas/ e execucoes/; uma pasta de mesmo nome mais fundo é dado do caso."""
        fundo = self.root / 'casos' / 'c1' / '.apagando'
        fundo.mkdir()
        (fundo / 'nota.txt').write_text('dado do caso', encoding='utf-8')
        nomes = self.nomes(backup.criar(self.root, self.base / 'copias'))
        self.assertIn('casos/c1/.apagando/nota.txt', nomes)

    def test_manifesto_do_apagamento_em_curso_na_lixeira_fica_fora_e_nao_faz_esperar(self):
        self.quarentena()
        nomes = self.nomes(backup.criar(self.root, self.base / 'copias'))
        self.assertNotIn('lixeira/.apagando/item-123.json', nomes)
        self.assertNotIn('lixeira/.apagando', nomes)
        self.assertIn('lixeira', nomes)

    def test_a_exclusao_vale_so_para_as_quatro_pastas_da_quarentena(self):
        """entrada/, acesso/ e ajustes/ não têm quarentena: um `.apagando` ali (improvável) seria dado e continua entrando."""
        self.assertEqual(backup.PASTAS_COM_QUARENTENA, ('casos', 'conversas', 'execucoes', 'lixeira'))
        for pasta in ('entrada', 'ajustes'):
            alvo = self.root / pasta / '.apagando'
            alvo.mkdir()
            (alvo / 'nota.txt').write_text('dado', encoding='utf-8')
        nomes = self.nomes(backup.criar(self.root, self.base / 'copias'))
        self.assertIn('entrada/.apagando/nota.txt', nomes)
        self.assertIn('ajustes/.apagando/nota.txt', nomes)

    def test_acesso_e_ajustes_nao_tem_o_que_excluir_e_nada_muda_para_eles(self):
        self.assertEqual(backup.EXCLUIDOS_NA_RAIZ, ('.apagando',))
        nomes = self.nomes(backup.criar(self.root, self.base / 'copias'))
        self.assertIn('acesso/acesso.json', nomes)
        self.assertIn('ajustes/inferencia.json', nomes)

    def test_o_backup_cifrado_decifrado_tambem_nao_tem_a_quarentena(self):
        """O serviço agendado cifra o mesmo conteúdo: decifrado e verificado, não há nada de .apagando."""
        from test_backup_agendado import PUBLICA
        self.quarentena()
        arquivo = backup.criar(self.root, self.base / 'copias', destinatarios=[PUBLICA])
        self.assertTrue(arquivo.name.endswith('.tar.gz.age'))
        destino = self.base / 'destino-cifrado'
        backup.restaurar(destino, arquivo, identidade=self.identidade(), trabalho=self.base / 'trab')
        for volume in VOLUMES:
            self.assertFalse((destino / volume / '.apagando').exists(), volume)


class DocumentacaoTest(unittest.TestCase):
    def test_backup_md_registra_a_exclusao(self):
        texto = (Path(__file__).resolve().parents[1] / 'deploy' / 'BACKUP.md').read_text(encoding='utf-8')
        for trecho in ('.apagando', 'quarentena', 'casos/.apagando', 'conversas/.apagando', 'execucoes/.apagando', 'lixeira/.apagando',
                       'apagamento.py', 'QUARENTENA', 'não serve sem os arquivos', 'não faz o backup esperar'):
            self.assertIn(trecho, texto, trecho)


if __name__ == '__main__':
    unittest.main()
