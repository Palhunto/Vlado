"""Backup agendado, cifrado e fora do servidor (SEG-03): consistência, cifra, envio, retenção, restauração e
saúde. Sem rede e sem chave real: `age` e `rclone` são trocados por dublês locais; o ensaio com os programas
de verdade (e com contêineres) fica no registro de verificação."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
import backup

PUBLICA = 'age1' + 'q' * 58
OUTRA = 'age1' + 'p' * 58
AGE_FALSO = '''import sys
args = sys.argv[1:]
if '-d' in args:
    identidade = open(args[args.index('-i') + 1], encoding='utf-8').read().strip()
    saida, origem = args[args.index('-o') + 1], args[-1]
    cabecalho, _, corpo = open(origem, 'rb').read().partition(b'\\n')
    if not cabecalho.startswith(b'FAKEAGE ') or ('ID:' + cabecalho.split()[1].decode()) != identidade:
        sys.stderr.write('no identity matched'); sys.exit(1)
    open(saida, 'wb').write(bytes(b ^ 0x5A for b in corpo))
else:
    chaves = [args[i + 1] for i, a in enumerate(args) if a == '-r']
    sys.stdout.buffer.write(b'FAKEAGE ' + chaves[0].encode() + b'\\n')
    sys.stdout.buffer.write(bytes(b ^ 0x5A for b in sys.stdin.buffer.read()))
'''


def rclone_falso(remoto: Path, falhas: dict | None = None):
    """Local stand-in for rclone: copyto, lsjson and deletefile over plain folders."""
    falhas = falhas if falhas is not None else {}

    def executar(argumentos, timeout=0):
        comando = argumentos[0]
        if falhas.get(comando):
            raise ValueError('rclone falhou: ' + falhas[comando])
        if comando == 'copyto':
            Path(argumentos[2]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(argumentos[1], argumentos[2])
            saida = b''
        elif comando == 'deletefile':
            Path(argumentos[1]).unlink()
            saida = b''
        else:  # lsjson
            filtro = argumentos[argumentos.index('--include') + 1] if '--include' in argumentos else None
            pasta = Path(argumentos[-1])
            itens = [{'Name': p.name, 'Size': p.stat().st_size} for p in sorted(pasta.glob('*'))
                     if p.is_file() and (filtro is None or p.name == filtro)] if pasta.is_dir() else []
            saida = json.dumps(itens).encode()
        return subprocess.CompletedProcess(argumentos, 0, saida, b'')
    return executar


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'dados'
        arquivos = {'casos/catalogo.json': '{"casos": [{"id": "c1"}]}', 'casos/c1/manifesto.json': '{"id": "c1"}',
                    'casos/c1/originais/D001.txt': 'documento sintético', 'conversas/c1/conversa.json': '{"m": []}',
                    'execucoes/c1/R001/registro.json': '{}', 'lixeira/indice.json': '{"itens": []}',
                    'acesso/acesso.json': '{"contas": {"u1": {"nome": "Ana"}}, "sessoes": {}}',
                    'ajustes/inferencia.json': '{}', 'segredos/chaves.json': '{"anthropic": "sk-ant-nao-sai"}'}
        for relativo, conteudo in arquivos.items():
            arquivo = self.root / relativo
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(conteudo, encoding='utf-8')
        (self.root / 'entrada').mkdir()
        self.ferramentas = self.base / 'ferramentas'
        self.ferramentas.mkdir()
        (self.ferramentas / 'age_falso.py').write_text(AGE_FALSO, encoding='utf-8')
        self.addCleanup(patch.stopall)

        def age(argumentos, **opcoes):
            return subprocess.Popen([sys.executable, str(self.ferramentas / 'age_falso.py'), *argumentos], **opcoes)
        patch.object(backup, '_age', age).start()
        patch.object(backup, 'ROOT', self.root).start()  # a rodada nunca lê os dados reais do repositório

    def identidade(self, chave=PUBLICA) -> Path:
        caminho = self.base / 'identidade.txt'
        caminho.write_text(f'ID:{chave}\n', encoding='utf-8')
        return caminho

    def configuracao(self, **mudancas) -> dict:
        ambiente = {'VLADO_AMBIENTE': 'homologacao', 'VLADO_BACKUP_DESTINO': str(self.base / 'fora'),
                    'VLADO_BACKUP_DESTINATARIOS': PUBLICA, 'VLADO_BACKUP_TRABALHO': str(self.base / 'trabalho'),
                    'VLADO_BACKUP_ESPERA_S': '0'}
        ambiente.update(mudancas)
        return backup._configuracao(ambiente)


class ConsistenciaTest(Base):
    def test_manifesto_traz_hash_de_cada_arquivo_e_a_restauracao_confere(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            manifesto = json.loads(pacote.extractfile('manifesto_backup.json').read())
        self.assertEqual(manifesto['versao_manifesto'], 2)
        self.assertIn('casos/c1/originais/D001.txt', manifesto['arquivos'])
        self.assertRegex(manifesto['arquivos']['acesso/acesso.json']['sha256'], r'^[0-9a-f]{64}$')
        destino = self.base / 'destino'
        backup.restaurar(destino, arquivo)
        self.assertEqual((destino / 'casos/c1/originais/D001.txt').read_text(encoding='utf-8'), 'documento sintético')
        self.assertTrue((destino / 'entrada').is_dir(), 'pasta vazia também volta')

    def test_arquivo_adulterado_no_backup_barra_a_restauracao_sem_tocar_nos_dados(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        adulterado = self.base / 'adulterado.tar.gz'
        with tarfile.open(arquivo) as origem, tarfile.open(adulterado, 'w:gz') as saida:
            for membro in origem.getmembers():
                dados = origem.extractfile(membro).read() if membro.isfile() else None
                if membro.name == 'casos/c1/originais/D001.txt':
                    dados = b'documento trocado!!!!'
                    membro.size = len(dados)
                saida.addfile(membro, __import__('io').BytesIO(dados) if dados is not None else None)
        destino = self.base / 'destino'
        (destino / 'casos').mkdir(parents=True)
        (destino / 'casos' / 'antigo.txt').write_text('mantido', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'hash.*não confere'):
            backup.restaurar(destino, adulterado, substituir=True)
        self.assertEqual((destino / 'casos' / 'antigo.txt').read_text(encoding='utf-8'), 'mantido')

    def test_arquivo_a_menos_ou_a_mais_barra_a_restauracao(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        incompleto = self.base / 'incompleto.tar.gz'
        with tarfile.open(arquivo) as origem, tarfile.open(incompleto, 'w:gz') as saida:
            for membro in origem.getmembers():
                if membro.name != 'ajustes/inferencia.json':
                    saida.addfile(membro, origem.extractfile(membro) if membro.isfile() else None)
        with self.assertRaisesRegex(ValueError, 'incompleto ou adulterado'):
            backup.restaurar(self.base / 'destino', incompleto)

    def test_operacao_em_andamento_e_esperada_e_depois_recusada(self):
        (self.root / 'casos' / '.cadastro.lock').mkdir()
        with self.assertRaises(backup.BackupOcupado):
            backup.criar(self.root, self.base / 'copias')
        self.assertEqual(list((self.base / 'copias').glob('*')) if (self.base / 'copias').exists() else [], [])

    def test_pastas_de_preparo_ficam_fora_e_travam_o_backup(self):
        for marcador in ('casos/.lote_abc', 'casos/c1/caderno/.trava', 'execucoes/c1/R001/.indice_x'):
            pasta = self.root / marcador
            pasta.mkdir(parents=True)
            (pasta / 'parcial.json').write_text('{', encoding='utf-8')
            with self.assertRaises(backup.BackupOcupado, msg=marcador):
                backup.criar(self.root, self.base / 'copias')
            shutil.rmtree(pasta)

    def test_marcador_que_aparece_durante_a_copia_descarta_o_arquivo_e_recomeca(self):
        original = backup._escrever_pacote
        chamadas = []

        def com_cadastro_no_meio(root, pacote, incluir_segredos, trabalho=None):
            resultado = original(root, pacote, incluir_segredos, trabalho)
            if not chamadas:
                (root / 'casos' / '.cadastro.lock').mkdir()
            chamadas.append(1)
            return resultado

        def termina_o_cadastro(*_):
            shutil.rmtree(self.root / 'casos' / '.cadastro.lock', ignore_errors=True)

        with patch.object(backup, '_escrever_pacote', com_cadastro_no_meio), \
                patch.object(backup, '_aguardar_ociosidade', side_effect=lambda r, p, e: termina_o_cadastro() if chamadas else None):
            arquivo = backup.criar(self.root, self.base / 'copias')
        self.assertEqual(len(chamadas), 2, 'a primeira cópia foi descartada e refeita')
        self.assertEqual(len(list((self.base / 'copias').glob('*'))), 1, 'só o backup bom sobrou')
        self.assertTrue(arquivo.is_file())

    def test_arquivo_que_muda_durante_a_leitura_e_relido(self):
        alvo = self.root / 'casos' / 'c1' / 'manifesto.json'
        original = backup._copiar
        estado = {'n': 0}

        def copiar(caminho, trabalho):
            destino, resumo, antes, depois = original(caminho, trabalho)
            if caminho == alvo and estado['n'] == 0:
                estado['n'] = 1
                alvo.write_text('{"id": "c1", "versao": 2}', encoding='utf-8')  # alguém grava no meio da leitura
                os.utime(alvo, ns=(1, 1))
                depois = os.stat(alvo)
            return destino, resumo, antes, depois
        with patch.object(backup, '_copiar', copiar), patch.object(backup.time, 'sleep'):
            arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            self.assertIn('"versao": 2', pacote.extractfile('casos/c1/manifesto.json').read().decode('utf-8'))

    def test_json_parcial_que_nao_se_recupera_vai_com_aviso_no_manifesto(self):
        (self.root / 'conversas' / 'c1' / 'quebrado.json').write_text('{"a": ', encoding='utf-8')
        with patch.object(backup.time, 'sleep'):
            arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            manifesto = json.loads(pacote.extractfile('manifesto_backup.json').read())
            self.assertIn('conversas/c1/quebrado.json', pacote.getnames())
        self.assertTrue(any('quebrado.json' in a and 'JSON' in a for a in manifesto['avisos']))

    def test_sqlite_integro_entra_e_danificado_gera_aviso(self):
        bom = self.root / 'execucoes' / 'c1' / 'R001' / 'apuracao.sqlite'
        ligacao = sqlite3.connect(bom)
        ligacao.execute('create table t (x)')
        ligacao.execute('insert into t values (1)')
        ligacao.commit()
        ligacao.close()
        ruim = self.root / 'execucoes' / 'c1' / 'R001' / 'outro.sqlite'
        ruim.write_bytes(b'isto nao e um banco sqlite' * 50)
        with patch.object(backup.time, 'sleep'):
            arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            manifesto = json.loads(pacote.extractfile('manifesto_backup.json').read())
        self.assertFalse(any('apuracao.sqlite' in a for a in manifesto['avisos']))
        self.assertTrue(any('outro.sqlite' in a for a in manifesto['avisos']))

    def test_o_backup_so_le_nunca_grava_nos_dados(self):
        antes = {p: p.stat().st_mtime_ns for p in self.root.rglob('*')}
        backup.criar(self.root, self.base / 'copias')
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.root.rglob('*')}, antes)
        self.assertEqual({p for p in self.root.rglob('*')}, set(antes))

    def test_links_simbolicos_nao_entram(self):
        alvo = self.base / 'fora.txt'
        alvo.write_text('nao deve entrar', encoding='utf-8')
        try:
            os.symlink(alvo, self.root / 'casos' / 'atalho.txt')
        except (OSError, NotImplementedError):
            self.skipTest('sem permissão para criar link simbólico')
        arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            self.assertNotIn('casos/atalho.txt', pacote.getnames())


class SegredosTest(Base):
    def test_chaves_de_api_ficam_de_fora_por_decisao_declarada(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            self.assertFalse(any(n.startswith('segredos') for n in pacote.getnames()))
            manifesto = json.loads(pacote.extractfile('manifesto_backup.json').read())
        self.assertIs(manifesto['segredos_incluidos'], False)
        self.assertIn('acesso', manifesto['pastas'])

    def test_manifesto_nao_afirma_segredos_que_nao_estavam_la(self):
        shutil.rmtree(self.root / 'segredos')
        arquivo = backup.criar(self.root, self.base / 'copias', incluir_segredos=True)
        with tarfile.open(arquivo) as pacote:
            self.assertIs(json.loads(pacote.extractfile('manifesto_backup.json').read())['segredos_incluidos'], False)

    def test_contas_casos_e_ajustes_estao_no_backup(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            nomes = set(pacote.getnames())
        for esperado in ('acesso/acesso.json', 'casos/catalogo.json', 'casos/c1/originais/D001.txt',
                         'execucoes/c1/R001/registro.json', 'conversas/c1/conversa.json', 'ajustes/inferencia.json',
                         'lixeira/indice.json'):
            self.assertIn(esperado, nomes)


class CifraTest(Base):
    def test_destinatarios_so_chave_publica(self):
        self.assertEqual(backup._destinatarios(f'{PUBLICA}, {OUTRA}'), [PUBLICA, OUTRA])
        self.assertEqual(backup._destinatarios(''), [])
        with self.assertRaisesRegex(ValueError, 'PRIVADA'):
            backup._destinatarios('AGE-SECRET-KEY-1' + 'Q' * 58)
        with self.assertRaisesRegex(ValueError, 'inválido'):
            backup._destinatarios('qualquer-coisa')
        arquivo = self.base / 'dest.txt'
        arquivo.write_text(f'# dono\n{PUBLICA}\n', encoding='utf-8')
        self.assertEqual(backup._destinatarios(str(arquivo)), [PUBLICA])
        arquivo.write_text('AGE-SECRET-KEY-1' + 'Q' * 58, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'PRIVADA'):
            backup._destinatarios(str(arquivo))

    def test_arquivo_cifrado_nao_expoe_o_conteudo_e_restaura_com_a_chave_certa(self):
        arquivo = backup.criar(self.root, self.base / 'copias', destinatarios=[PUBLICA])
        self.assertTrue(arquivo.name.endswith('.tar.gz.age'))
        bruto = arquivo.read_bytes()
        self.assertNotIn(b'documento', bruto)
        self.assertNotIn(b'\x1f\x8b', bruto[:40], 'não é um gzip em claro')
        destino = self.base / 'destino'
        backup.restaurar(destino, arquivo, identidade=self.identidade(), trabalho=self.base / 'trab')
        self.assertEqual((destino / 'acesso/acesso.json').read_text(encoding='utf-8').count('Ana'), 1)
        self.assertEqual(list((self.base / 'trab').glob('*')), [], 'o texto em claro não fica para trás')

    def test_sem_a_chave_privada_ou_com_chave_errada_nao_restaura(self):
        arquivo = backup.criar(self.root, self.base / 'copias', destinatarios=[PUBLICA])
        with self.assertRaisesRegex(ValueError, 'chave privada'):
            backup.restaurar(self.base / 'd1', arquivo)
        with self.assertRaisesRegex(ValueError, 'decifrar'):
            backup.restaurar(self.base / 'd2', arquivo, identidade=self.identidade(OUTRA))
        self.assertFalse((self.base / 'd2').exists() and any((self.base / 'd2').iterdir()))

    def test_falha_ao_decifrar_nao_deixa_pasta_em_trabalho_tmp(self):
        # J7: o __exit__ não roda quando o __enter__ falha; a pasta de decifragem era esquecida em /trabalho/tmp.
        arquivo = backup.criar(self.root, self.base / 'copias', destinatarios=[PUBLICA])
        trab = self.base / 'trab'
        with self.assertRaisesRegex(ValueError, 'decifrar'):
            backup.restaurar(self.base / 'd2', arquivo, identidade=self.identidade(OUTRA), trabalho=trab)
        with self.assertRaisesRegex(ValueError, 'decifrar'):
            backup.verificar(arquivo, self.identidade(OUTRA), trab)
        self.assertEqual(list(trab.glob('*')), [], 'sobrou pasta de decifragem')
        # Arquivo cifrado corrompido depois de decifrar (não é um gzip): também limpa.
        corrompido = self.base / 'copias' / 'vlado-corrompido.tar.gz.age'
        cabecalho = arquivo.read_bytes().partition(b'\n')[0]
        corrompido.write_bytes(cabecalho + b'\n' + bytes(b ^ 0x5A for b in b'isto nao e um gzip'))
        with self.assertRaises(Exception):
            backup.verificar(corrompido, self.identidade(), trab)
        self.assertEqual(list(trab.glob('*')), [], 'sobrou pasta de decifragem')

    def test_verificar_confere_hashes_sem_escrever_dados(self):
        arquivo = backup.criar(self.root, self.base / 'copias', destinatarios=[PUBLICA])
        resumo = backup.verificar(arquivo, self.identidade(), self.base / 'trab')
        self.assertTrue(resumo['hashes_conferidos'])
        self.assertGreaterEqual(resumo['arquivos'], 8)
        self.assertFalse((self.base / 'casos').exists())

    def test_o_arquivo_do_backup_nasce_0600(self):
        arquivo = backup.criar(self.root, self.base / 'copias', destinatarios=[PUBLICA])
        if os.name != 'nt':
            self.assertEqual(arquivo.stat().st_mode & 0o777, 0o600)

    def test_identidade_pelo_ambiente_vai_para_arquivo_privado_e_e_apagada(self):
        class Args:
            identidade = None
            identidade_env = 'CHAVE_TESTE'
        with patch.dict(os.environ, {'CHAVE_TESTE': f'ID:{PUBLICA}'}):
            caminho, apagar = backup._identidade(Args)
        self.assertEqual(caminho, apagar)
        self.assertEqual(caminho.read_text(encoding='utf-8').strip(), f'ID:{PUBLICA}')
        caminho.unlink()


class RestauracaoPelaEntradaPadraoTest(Base):
    """I6/J9: `restaurar -` não carrega o arquivo inteiro na memória; vai para disco em blocos, com teto."""

    class Fluxo:
        """Leitor que só aceita ler em blocos e guarda o maior pedido; read() sem tamanho é erro."""
        def __init__(self, dados: bytes):
            self.dados, self.pos, self.maior = dados, 0, 0

        def read(self, n=-1):
            if n is None or n < 0:
                raise AssertionError('leu o fluxo inteiro de uma vez')
            self.maior = max(self.maior, n)
            bloco = self.dados[self.pos:self.pos + n]
            self.pos += len(bloco)
            return bloco

    def test_restaura_em_fluxo_e_nao_deixa_arquivo_temporario(self):
        arquivo = backup.criar(self.root, self.base / 'copias')  # .tar.gz sem cifra
        fluxo = self.Fluxo(arquivo.read_bytes())
        entrada = type('E', (), {'buffer': fluxo})
        destino, trab = self.base / 'destino', self.base / 'trab'
        with patch.object(backup.sys, 'stdin', entrada):
            backup.restaurar(destino, '-', trabalho=trab)
        self.assertLessEqual(fluxo.maior, 1 << 20, 'blocos de no máximo 1 MiB')
        self.assertEqual((destino / 'casos/c1/originais/D001.txt').read_text(encoding='utf-8'), 'documento sintético')
        self.assertEqual(list(trab.glob('*')), [], 'o arquivo da entrada padrão não some')

    def test_acima_do_teto_recusa_com_mensagem_clara_e_limpa(self):
        trab = self.base / 'trab'
        fluxo = self.Fluxo(b'x' * (3 << 20))
        with patch.dict(os.environ, {'VLADO_BACKUP_STDIN_MAX_GB': '0.001'}):  # ~1 MiB
            with self.assertRaisesRegex(ValueError, r'passa de .* GB.*VLADO_BACKUP_STDIN_MAX_GB.*Nada foi restaurado'):
                with backup._entrada_em_disco(fluxo, trab):
                    self.fail('não deveria abrir')
        self.assertEqual(list(trab.glob('*')), [])
        self.assertLess(fluxo.pos, 3 << 20, 'parou de ler ao passar do teto')

    def test_teto_invalido_e_explicado_e_o_padrao_e_dez_gigas(self):
        with patch.dict(os.environ, {'VLADO_BACKUP_STDIN_MAX_GB': 'muito'}):
            with self.assertRaisesRegex(ValueError, 'VLADO_BACKUP_STDIN_MAX_GB'):
                backup._limite_stdin_bytes()
        with patch.dict(os.environ, {'VLADO_BACKUP_STDIN_MAX_GB': ''}):
            self.assertEqual(backup._limite_stdin_bytes(), 10 << 30)

    def test_entrada_que_nao_e_gzip_nao_deixa_rastro(self):
        trab = self.base / 'trab'
        entrada = type('E', (), {'buffer': self.Fluxo(b'isto nao e um gzip')})
        with patch.object(backup.sys, 'stdin', entrada):
            with self.assertRaises(Exception):
                backup.restaurar(self.base / 'destino', '-', trabalho=trab)
        self.assertEqual(list(trab.glob('*')), [])

    def test_o_codigo_nao_le_a_entrada_inteira_para_a_memoria(self):
        fonte = (RAIZ / 'scripts' / 'backup.py').read_text(encoding='utf-8')
        self.assertNotIn('sys.stdin.buffer.read()', fonte)
        self.assertNotRegex(fonte, r'BytesIO\(sys\.stdin')


class FilaDeExtracaoTest(Base):
    """C7: casos/.fila/ (CONF-02) guarda envios ainda não publicados. Decisão: ENTRA no backup, com o que a
    Mesa precisa para reprocessar o lote (pedido, estado, originais, derivados); fora ficam o `.coordenador` (trava
    de processo, não é dado) e `.novo_<id>` (lote em montagem, marcador); e ela é copiada antes dos casos."""

    LOTE = 'a1' * 16

    def monta_fila(self):
        fila = self.root / 'casos' / '.fila'
        lote = fila / self.LOTE
        arquivos = {'pedido.json': '{"caso": "c1", "lote": "%s"}' % self.LOTE,
                    'estado.json': '{"estado": "processando", "arquivos": [{"indice": 0, "estado": "extraindo"}]}',
                    'originais/0/relatorio.pdf': 'bytes do original recebido, ainda nao publicado',
                    'derivados/0/resultado.json': '{"extracao": "parcial"}'}
        for relativo, conteudo in arquivos.items():
            alvo = lote / relativo
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(conteudo, encoding='utf-8')
        (fila / '.coordenador').write_text('4242', encoding='utf-8')
        return fila, arquivos

    def membros(self, arquivo) -> list[str]:
        with tarfile.open(arquivo) as pacote:
            return [m.name for m in pacote.getmembers()]

    def test_lote_pendente_entra_no_backup_sem_a_trava_do_coordenador(self):
        fila, arquivos = self.monta_fila()
        nomes = self.membros(backup.criar(self.root, self.base / 'copias'))
        for relativo in arquivos:
            self.assertIn(f'casos/.fila/{self.LOTE}/{relativo}', nomes, relativo)
        self.assertNotIn('casos/.fila/.coordenador', nomes, 'trava de processo não é dado')
        self.assertFalse([n for n in nomes if n.endswith('.coordenador')])

    def test_restauracao_devolve_o_lote_pendente_igual_para_a_mesa_reprocessar(self):
        fila, arquivos = self.monta_fila()
        destino = self.base / 'destino'
        backup.restaurar(destino, backup.criar(self.root, self.base / 'copias'))
        for relativo, conteudo in arquivos.items():
            self.assertEqual((destino / 'casos/.fila' / self.LOTE / relativo).read_text(encoding='utf-8'), conteudo)
        self.assertFalse((destino / 'casos/.fila/.coordenador').exists(), 'o coordenador cria a própria trava ao partir')

    def test_lote_em_montagem_e_marcador_fica_fora_e_faz_o_backup_esperar(self):
        fila, _ = self.monta_fila()
        montagem = fila / ('.novo_' + 'b2' * 16)
        (montagem / 'originais').mkdir(parents=True)
        (montagem / 'pedido.json').write_text('{', encoding='utf-8')
        with self.assertRaises(backup.BackupOcupado):
            backup.criar(self.root, self.base / 'copias')
        # Abandonado (queda da Mesa, mais velho que o limite): fica fora e só vira aviso, sem travar o backup.
        antigo = backup.MARCADOR_IDADE_MAX_S + 60
        for caminho in (montagem, montagem / 'pedido.json', montagem / 'originais'):
            os.utime(caminho, (os.stat(caminho).st_atime - antigo, os.stat(caminho).st_mtime - antigo))
        nomes = self.membros(backup.criar(self.root, self.base / 'copias2'))
        self.assertFalse([n for n in nomes if '.novo_' in n], 'lote em montagem nunca entra')
        self.assertIn(f'casos/.fila/{self.LOTE}/pedido.json', nomes)

    def test_fila_e_copiada_antes_dos_casos_para_um_lote_publicado_no_meio_nunca_sumir(self):
        """Se a publicação mover um lote da fila para casos/<caso> durante a cópia, ele precisa estar em um dos dois:
        copiando a fila primeiro, no pior caso aparece nos dois (publicar de novo é idempotente), nunca em nenhum."""
        self.monta_fila()
        nomes = self.membros(backup.criar(self.root, self.base / 'copias'))
        da_fila = [i for i, n in enumerate(nomes) if n.startswith('casos/.fila')]
        dos_casos = [i for i, n in enumerate(nomes) if n.startswith('casos/c1/')]  # as pastas dos casos
        self.assertTrue(da_fila and dos_casos)
        self.assertLess(max(da_fila), min(dos_casos), 'casos/.fila precisa vir antes dos casos no pacote')

    def test_arquivo_da_fila_que_muda_durante_a_leitura_vira_aviso_nao_falha(self):
        fila, _ = self.monta_fila()
        arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            manifesto = json.loads(pacote.extractfile('manifesto_backup.json').read())
        self.assertIn(f'casos/.fila/{self.LOTE}/estado.json', manifesto['arquivos'])


class RetencaoTest(unittest.TestCase):
    AGORA = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)

    def lote(self, dias):
        return [(f'b{d}', self.AGORA - timedelta(days=d, hours=1)) for d in dias]

    def test_padrao_declarado(self):
        self.assertEqual(backup._parse_retencao(None), {'diarios': 7, 'semanais': 4, 'mensais': 6})
        self.assertEqual(backup.RETENCAO_PADRAO, 'diarios=7,semanais=4,mensais=6')

    def test_configuracao_invalida_e_recusada(self):
        for texto in ('diarios=0', 'diarios=x', 'anuais=3', 'diarios=7;semanais=1'):
            with self.assertRaises(ValueError, msg=texto):
                backup._parse_retencao(texto)

    def test_guarda_diarios_e_um_por_semana_e_por_mes_e_descarta_o_resto(self):
        itens = self.lote(range(0, 200))
        descartes = set(backup.selecionar_descartes(itens, self.AGORA, backup._parse_retencao(None)))
        mantidos = {n for n, _ in itens} - descartes
        self.assertTrue({f'b{d}' for d in range(7)} <= mantidos, 'os 7 dias mais recentes ficam todos')
        self.assertLessEqual(len(mantidos), 7 + 5 + 7)
        self.assertIn('b199', descartes)
        datas = {n: d for n, d in itens}
        semanas = {datas[n].isocalendar()[:2] for n in mantidos if 7 <= (self.AGORA - datas[n]).days <= 28}
        self.assertGreaterEqual(len(semanas), 3, 'uma por semana nas últimas quatro')

    def test_o_mais_novo_nunca_e_descartado_mesmo_com_tudo_vencido(self):
        itens = [('velho1', self.AGORA - timedelta(days=900)), ('velho2', self.AGORA - timedelta(days=800))]
        self.assertEqual(backup.selecionar_descartes(itens, self.AGORA, backup._parse_retencao('diarios=1,semanais=0,mensais=0')),
                         ['velho1'])

    def test_lista_vazia_nao_descarta_nada(self):
        self.assertEqual(backup.selecionar_descartes([], self.AGORA, backup._parse_retencao(None)), [])

    def test_so_nomes_do_proprio_ambiente_sao_considerados(self):
        self.assertIsNotNone(backup._data_do_nome('vlado-homologacao-20261121T060000000000Z.tar.gz.age', 'homologacao'))
        self.assertIsNone(backup._data_do_nome('vlado-editorial-20261121T060000000000Z.tar.gz.age', 'homologacao'))
        self.assertIsNone(backup._data_do_nome('vlado-homologacao-20261121T060000000000Z.tar.gz', 'homologacao'))
        self.assertIsNone(backup._data_do_nome('qualquer.txt', 'homologacao'))


class RodadaTest(Base):
    def setUp(self):
        super().setUp()
        self.remoto = self.base / 'fora'
        self.falhas = {}
        patch.object(backup, '_rclone', rclone_falso(self.remoto, self.falhas)).start()
        patch.object(backup, '_avisar', lambda cfg, ok: self.avisos.append(ok)).start()
        self.avisos = []

    def test_rodada_cifra_envia_confere_e_limpa_o_local(self):
        cfg = self.configuracao()
        self.assertTrue(backup._executar_rodada(cfg))
        enviados = list(self.remoto.glob('*'))
        self.assertEqual(len(enviados), 1)
        self.assertRegex(enviados[0].name, r'^vlado-homologacao-\d{8}T\d{12}Z\.tar\.gz\.age$')
        self.assertNotIn(b'sk-ant', enviados[0].read_bytes())
        self.assertEqual(list((self.base / 'trabalho' / 'spool').glob('*')), [], 'nada fica no servidor')
        estado = backup._ler_estado(cfg)
        self.assertIsNone(estado['erro'])
        self.assertEqual(estado['ultimo']['arquivo'], enviados[0].name)
        self.assertEqual(self.avisos, [True])
        self.assertNotIn('PRIVATE', json.dumps(estado))

    def test_ponta_a_ponta_o_enviado_restaura_com_a_chave_do_dono(self):
        cfg = self.configuracao()
        self.assertTrue(backup._executar_rodada(cfg))
        enviado = next(self.remoto.glob('*'))
        destino = self.base / 'novo'
        backup.restaurar(destino, enviado, identidade=self.identidade(), outro_ambiente=True)
        self.assertEqual((destino / 'casos/c1/originais/D001.txt').read_text(encoding='utf-8'), 'documento sintético')
        self.assertFalse((destino / 'segredos').exists())

    def test_falha_no_envio_vira_erro_registrado_alerta_e_nao_deixa_arquivo_local(self):
        self.falhas['copyto'] = 'sem rede'
        cfg = self.configuracao()
        self.assertFalse(backup._executar_rodada(cfg))
        estado = backup._ler_estado(cfg)
        self.assertIn('sem rede', estado['erro'])
        self.assertNotIn('ultimo_sucesso_utc', estado)
        self.assertEqual(self.avisos, [False])
        self.assertEqual(list((self.base / 'trabalho' / 'spool').glob('*')), [])

    def test_envio_com_tamanho_diferente_no_destino_e_falha(self):
        original = backup._rclone

        def corta(argumentos, timeout=0):
            if argumentos[0] == 'copyto':
                rclone_falso(self.remoto)(argumentos)
                Path(argumentos[2]).write_bytes(b'truncado')
                return subprocess.CompletedProcess(argumentos, 0, b'', b'')
            return original(argumentos, timeout)
        with patch.object(backup, '_rclone', corta):
            self.assertFalse(backup._executar_rodada(self.configuracao()))
        self.assertIn('não confere', backup._ler_estado(self.configuracao())['erro'])

    def test_retencao_apaga_so_os_antigos_do_proprio_ambiente_e_nunca_o_recem_enviado(self):
        self.remoto.mkdir()
        velhos = []
        for dias in (400, 300, 90):
            data = _agora() - timedelta(days=dias)
            nome = f'vlado-homologacao-{data.strftime("%Y%m%dT%H%M%S%f")}Z.tar.gz.age'
            (self.remoto / nome).write_bytes(b'x')
            velhos.append(nome)
        alheio = self.remoto / 'vlado-editorial-20200101T000000000000Z.tar.gz.age'
        alheio.write_bytes(b'x')
        estranho = self.remoto / 'anotacoes.txt'
        estranho.write_bytes(b'x')
        self.assertTrue(backup._executar_rodada(self.configuracao(VLADO_BACKUP_RETENCAO='diarios=1,semanais=0,mensais=6')))
        restantes = {p.name for p in self.remoto.glob('*')}
        self.assertTrue(alheio.exists() and estranho.exists(), 'não mexe no que não é deste ambiente')
        self.assertNotIn(velhos[0], restantes)
        self.assertNotIn(velhos[1], restantes)
        self.assertIn(velhos[2], restantes, 'o de 90 dias cabe nos 6 meses mensais')
        self.assertIn(backup._ler_estado(self.configuracao())['ultimo']['arquivo'], restantes)

    def test_falha_da_retencao_nao_derruba_o_backup_ja_enviado(self):
        self.falhas['deletefile'] = 'sem permissão de apagar'
        self.remoto.mkdir()
        (self.remoto / 'vlado-homologacao-20200101T000000000000Z.tar.gz.age').write_bytes(b'x')
        cfg = self.configuracao(VLADO_BACKUP_RETENCAO='diarios=1,semanais=0,mensais=0')
        self.assertTrue(backup._executar_rodada(cfg))
        self.assertTrue(any('permissão' in a for a in backup._ler_estado(cfg)['ultimo']['avisos']))

    def test_sem_configuracao_nao_ha_backup_e_o_motivo_aparece(self):
        cfg = self.configuracao(VLADO_BACKUP_DESTINO='', VLADO_BACKUP_DESTINATARIOS='')
        self.assertFalse(backup._executar_rodada(cfg))
        self.assertIn('VLADO_BACKUP_DESTINO', backup._ler_estado(cfg)['erro'])
        self.assertIn('DESTINATARIOS', backup._ler_estado(cfg)['erro'])

    def test_chave_privada_no_lugar_da_publica_e_recusada(self):
        cfg = self.configuracao(VLADO_BACKUP_DESTINATARIOS='AGE-SECRET-KEY-1' + 'Q' * 58)
        self.assertFalse(backup._executar_rodada(cfg))
        self.assertIn('PRIVADA', backup._ler_estado(cfg)['erro'])
        self.assertNotIn('AGE-SECRET-KEY-1Q', backup._ler_estado(cfg)['erro'])
        self.assertEqual(list(self.remoto.glob('*')), [])

    def test_baixar_o_ultimo_do_destino_e_verificar(self):
        cfg = self.configuracao()
        self.assertTrue(backup._executar_rodada(cfg))
        local = backup._resolver_origem(cfg, None, 'ultimo', self.base / 'baixado')
        resumo = backup.verificar(local, self.identidade(), self.base / 'trab')
        self.assertTrue(resumo['hashes_conferidos'])
        with self.assertRaisesRegex(ValueError, 'inválido'):
            backup._resolver_origem(cfg, None, '../fora.tar', self.base / 'baixado')


def _agora():
    return datetime.now(timezone.utc)


class AgendamentoESaudeTest(Base):
    def test_proxima_execucao_no_horario_utc(self):
        manha = datetime(2026, 11, 21, 5, 0, tzinfo=timezone.utc)
        self.assertEqual(backup._proxima(manha, '06:30'), datetime(2026, 11, 21, 6, 30, tzinfo=timezone.utc))
        self.assertEqual(backup._proxima(manha.replace(hour=7), '06:30'), datetime(2026, 11, 22, 6, 30, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            self.configuracao(VLADO_BACKUP_HORARIO_UTC='25:99')

    def test_saude_nao_configurado_e_nao_saudavel(self):
        cfg = self.configuracao(VLADO_BACKUP_DESTINO='')
        backup._gravar_estado(cfg, iniciado_em_utc=_agora().isoformat(), erro='backup NÃO configurado: x')
        self.assertEqual(backup.saude(cfg), 1)

    def test_saude_aguardando_o_primeiro_e_depois_do_sucesso(self):
        cfg = self.configuracao()
        self.assertEqual(backup.saude(cfg), 1, 'sem estado nenhum')
        backup._gravar_estado(cfg, iniciado_em_utc=_agora().isoformat(), destino_configurado=True)
        self.assertEqual(backup.saude(cfg), 0)
        backup._gravar_estado(cfg, ultimo_sucesso_utc=_agora().isoformat())
        self.assertEqual(backup.saude(cfg), 0)

    def test_saude_falha_quando_o_ultimo_sucesso_esta_velho(self):
        cfg = self.configuracao()
        velho = (_agora() - timedelta(hours=31)).isoformat()
        backup._gravar_estado(cfg, iniciado_em_utc=velho, ultimo_sucesso_utc=velho, destino_configurado=True)
        self.assertEqual(backup.saude(cfg), 1)

    def test_aviso_de_monitoramento_usa_o_endereco_de_falha(self):
        visitados = []

        class Resposta:
            def read(self, n):
                return b''
        cfg = self.configuracao(VLADO_BACKUP_PING_URL='https://ping.exemplo/abc/')
        with patch.object(backup.urllib.request, 'urlopen', lambda req, timeout: visitados.append(req.full_url) or Resposta()):
            backup._avisar(cfg, True)
            backup._avisar(cfg, False)
        self.assertEqual(visitados, ['https://ping.exemplo/abc/', 'https://ping.exemplo/abc/fail'])


class RestauracaoComMesaNoArTest(Base):
    """J1: a restauração troca o conteúdo das pastas de dados e não pode rodar com o app gravando."""

    def principal(self, *argumentos, resposta=None, erro=None):
        arquivo = backup.criar(self.root, self.base / 'copias')
        destino = self.base / 'destino'
        ambiente = {'VLADO_AMBIENTE': 'homologacao', 'VLADO_BACKUP_TRABALHO': str(self.base / 'trabalho')}

        def saude(url):
            if erro:
                raise erro
            return resposta
        with patch.object(backup, 'ROOT', destino), patch.object(sys, 'argv', ['backup.py', 'restaurar', str(arquivo), *argumentos]), \
                patch.dict(os.environ, ambiente), patch.object(backup, '_ler_saude', saude):
            return backup._principal(), destino

    def test_recusa_quando_a_mesa_responde_e_nao_toca_nos_dados(self):
        with self.assertRaisesRegex(ValueError, 'A Mesa está no ar'):
            self.principal(resposta=(200, b'{"ok": true}'))
        self.assertFalse((self.base / 'destino' / 'casos').exists())

    def test_qualquer_resposta_http_conta_como_no_ar(self):
        with self.assertRaisesRegex(ValueError, 'A Mesa está no ar'):
            self.principal(resposta=(503, b''))

    def test_com_a_confirmacao_explicita_restaura(self):
        codigo, destino = self.principal('--mesmo-com-a-mesa-no-ar', resposta=(200, b'{"ok": true}'))
        self.assertEqual(codigo, 0)
        self.assertTrue((destino / 'casos' / 'catalogo.json').is_file())

    def test_sem_resposta_do_app_restaura_sem_pedir_confirmacao(self):
        codigo, destino = self.principal(erro=OSError('Name or service not known'))
        self.assertEqual(codigo, 0)
        self.assertTrue((destino / 'acesso' / 'acesso.json').is_file())

    def test_verificar_nao_e_barrado_porque_nao_escreve_dados(self):
        arquivo = backup.criar(self.root, self.base / 'copias')
        ambiente = {'VLADO_AMBIENTE': 'homologacao', 'VLADO_BACKUP_TRABALHO': str(self.base / 'trabalho')}
        with patch.object(sys, 'argv', ['backup.py', 'verificar', str(arquivo)]), patch.dict(os.environ, ambiente), \
                patch.object(backup, '_ler_saude', lambda url: (200, b'{"ok": true}')):
            self.assertEqual(backup._principal(), 0)

    def test_mesa_no_ar_olha_o_endereco_configurado(self):
        visitados = []
        cfg = backup._configuracao({'VLADO_VIGIA_URL': 'http://outro:9000/saude'})
        with patch.object(backup, '_ler_saude', lambda url: visitados.append(url) or (200, b'')):
            self.assertTrue(backup.mesa_no_ar(cfg))
        self.assertEqual(visitados, ['http://outro:9000/saude'])


class TravaDeCadastroTest(Base):
    """A trava nova da CONF-01: `casos/.cadastro.trava`, arquivo que nunca é apagado, preso com flock."""

    def trava(self) -> Path:
        return self.root / 'casos' / '.cadastro.trava'

    def escrever_registro(self, estado='livre'):
        self.trava().write_text(json.dumps({'estado': estado, 'versao': 1}).ljust(2047) + '\n', encoding='utf-8')

    def test_arquivo_de_trava_e_arquivos_lock_nao_entram_no_backup(self):
        # Restos de uma queda ('ocupada' sem dono vivo) não podem voltar numa restauração como "trava abandonada".
        # No Windows de desenvolvimento não há flock e o registro 'ocupada' valeria como em uso: lá fica 'livre'.
        self.escrever_registro('ocupada' if os.name != 'nt' else 'livre')
        (self.root / 'acesso' / 'acesso.json.lock').write_bytes(b'')
        arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            nomes = pacote.getnames()
        self.assertNotIn('casos/.cadastro.trava', nomes)
        self.assertNotIn('acesso/acesso.json.lock', nomes)

    def test_arquivo_ausente_ou_livre_nao_e_trava_em_uso(self):
        self.assertFalse(backup._trava_cadastro_em_uso(self.root))
        self.escrever_registro('livre')
        self.assertFalse(backup._trava_cadastro_em_uso(self.root))

    @unittest.skipUnless(os.name == 'posix', 'flock só existe no Linux (onde o servidor roda)')
    def test_flock_preso_por_outro_descritor_faz_o_backup_esperar_e_depois_passar(self):
        import fcntl
        self.escrever_registro('ocupada')
        dono = os.open(self.trava(), os.O_RDWR)
        fcntl.flock(dono, fcntl.LOCK_EX)
        try:
            self.assertTrue(backup._trava_cadastro_em_uso(self.root))
            with self.assertRaisesRegex(backup.BackupOcupado, 'cadastro em curso'):
                backup.criar(self.root, self.base / 'copias')
        finally:
            fcntl.flock(dono, fcntl.LOCK_UN)
            os.close(dono)
        self.assertFalse(backup._trava_cadastro_em_uso(self.root), 'registro "ocupada" sem dono vivo não trava o backup')
        self.assertTrue(backup.criar(self.root, self.base / 'copias').is_file())

    @unittest.skipUnless(os.name == 'posix', 'flock só existe no Linux (onde o servidor roda)')
    def test_a_sonda_nao_fica_segurando_a_trava(self):
        import fcntl
        self.escrever_registro('livre')
        backup._trava_cadastro_em_uso(self.root)
        outro = os.open(self.trava(), os.O_RDWR)
        try:
            fcntl.flock(outro, fcntl.LOCK_EX | fcntl.LOCK_NB)  # um cadastro de usuário consegue logo em seguida
            fcntl.flock(outro, fcntl.LOCK_UN)
        finally:
            os.close(outro)

    @unittest.skipUnless(os.name == 'posix', 'flock só existe no Linux (onde o servidor roda)')
    def test_o_backup_nunca_segura_a_trava_enquanto_copia(self):
        import fcntl
        self.escrever_registro('livre')
        original = backup._escrever_pacote
        durante = []

        def espiar(root, pacote, incluir_segredos, trabalho=None):
            outro = os.open(self.trava(), os.O_RDWR)
            try:
                fcntl.flock(outro, fcntl.LOCK_EX | fcntl.LOCK_NB)
                durante.append('cadastro conseguiu a trava no meio da cópia')
                fcntl.flock(outro, fcntl.LOCK_UN)
            except OSError:
                durante.append('trava presa pelo backup')
            finally:
                os.close(outro)
            return original(root, pacote, incluir_segredos, trabalho)
        with patch.object(backup, '_escrever_pacote', espiar), patch.object(backup, '_assinatura_casos', lambda r: None):
            backup.criar(self.root, self.base / 'copias')
        self.assertEqual(durante, ['cadastro conseguiu a trava no meio da cópia'])

    def test_operacao_que_termina_durante_a_copia_muda_a_assinatura_e_refaz_o_backup(self):
        """Mesmos bytes 'livre' antes e depois, mas mtime/ctime do inode mudam: a cópia é descartada e refeita."""
        self.escrever_registro('livre')
        original = backup._escrever_pacote
        chamadas = []

        def com_cadastro_no_meio(root, pacote, incluir_segredos, trabalho=None):
            resultado = original(root, pacote, incluir_segredos, trabalho)
            if not chamadas:
                self.escrever_registro('livre')  # um cadastro inteiro: pega, grava, solta
                os.utime(self.trava(), ns=(5, 5))
            chamadas.append(1)
            return resultado
        with patch.object(backup, '_escrever_pacote', com_cadastro_no_meio):
            arquivo = backup.criar(self.root, self.base / 'copias')
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(len(list((self.base / 'copias').glob('*'))), 1, 'só a cópia coerente sobra')
        self.assertTrue(arquivo.is_file())

    def test_trava_que_aparece_durante_a_copia_tambem_refaz(self):
        original = backup._escrever_pacote
        chamadas = []

        def cria_a_trava(root, pacote, incluir_segredos, trabalho=None):
            resultado = original(root, pacote, incluir_segredos, trabalho)
            if not chamadas:
                self.escrever_registro('livre')
            chamadas.append(1)
            return resultado
        with patch.object(backup, '_escrever_pacote', cria_a_trava):
            backup.criar(self.root, self.base / 'copias')
        self.assertEqual(len(chamadas), 2)

    def test_assinatura_igual_nao_refaz(self):
        self.escrever_registro('livre')
        chamadas = []
        original = backup._escrever_pacote

        def conta(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)
        with patch.object(backup, '_escrever_pacote', conta):
            backup.criar(self.root, self.base / 'copias')
        self.assertEqual(len(chamadas), 1)

    def test_pasta_de_preparo_velha_de_uma_queda_nao_trava_o_backup_e_vai_para_os_avisos(self):
        velha = self.root / 'casos' / ('.lote_' + 'a' * 32)
        velha.mkdir()
        (velha / 'parcial.bin').write_bytes(b'meio do cadastro')
        recente = self.root / 'execucoes' / ('.r_' + 'b' * 32)
        os.utime(velha, (1, 1))
        with self.assertRaises(backup.BackupOcupado):  # uma recente ainda faz esperar
            recente.mkdir()
            try:
                backup.criar(self.root, self.base / 'copias')
            finally:
                shutil.rmtree(recente)
        arquivo = backup.criar(self.root, self.base / 'copias')
        with tarfile.open(arquivo) as pacote:
            nomes = pacote.getnames()
            manifesto = json.loads(pacote.extractfile('manifesto_backup.json').read())
        self.assertFalse(any('.lote_' in n for n in nomes), 'a pasta de preparo nunca entra')
        self.assertTrue(any('abandonada' in a and '.lote_' in a for a in manifesto['avisos']))

    def test_idade_maxima_do_marcador_e_configuravel(self):
        recente = self.root / 'casos' / ('.lote_' + 'c' * 32)
        recente.mkdir()
        with patch.dict(os.environ, {'VLADO_BACKUP_MARCADOR_IDADE_MAX_S': '0'}):
            time_passou = backup.time.time() + 5
            with patch.object(backup.time, 'time', lambda: time_passou):
                self.assertEqual(backup._marcadores(self.root, backup.PASTAS), [])


class ComposeDoBackupTest(unittest.TestCase):
    def setUp(self):
        self.compose = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        partes = re.split(r'^  ([a-z_]+):\s*$', self.compose.split('\nservices:', 1)[1].split('\nvolumes:\n', 1)[0], flags=re.MULTILINE)
        self.servicos = dict(zip(partes[1::2], partes[2::2]))

    def test_backup_le_dados_somente_leitura_e_sem_segredos_de_api(self):
        bloco = self.servicos['backup']
        montagens = re.findall(r'(?m)^      - (\S+:/app/\S+)$', bloco)
        self.assertGreaterEqual(len(montagens), 7)
        for montagem in montagens:
            self.assertTrue(montagem.endswith(':ro'), f'volume de dados do backup deve ser somente leitura: {montagem}')
        self.assertNotIn('segredos', ' '.join(montagens))
        self.assertNotIn('ANTHROPIC_API_KEY', bloco)
        self.assertNotIn('OPENAI_API_KEY', bloco)

    def test_chave_privada_nunca_entra_no_servico_agendado(self):
        bloco = self.servicos['backup']
        for proibido in ('CHAVE_PRIVADA', 'IDENTIDADE', 'AGE-SECRET-KEY', 'identidade'):
            self.assertNotIn(proibido, bloco)

    def test_restauracao_so_por_profile_e_a_chave_vem_do_ambiente_do_comando(self):
        bloco = self.servicos['restauracao']
        self.assertIn('profiles: ["restauracao"]', bloco)
        self.assertIn('--identidade-env', bloco)
        self.assertNotRegex(bloco, r'(?m)^\s+- .*identidade[^\n]*:/')

    def test_servico_agendado_tem_politica_de_reinicio_e_volume_de_trabalho(self):
        bloco = self.servicos['backup']
        self.assertIn('restart: unless-stopped', bloco)
        self.assertIn('backup_trabalho:/trabalho', bloco)
        self.assertIn('VLADO_BACKUP_RETENCAO: ${VLADO_BACKUP_RETENCAO:-diarios=7,semanais=4,mensais=6}', bloco)

    def test_exemplos_de_ambiente_pedem_so_a_chave_publica(self):
        for ambiente in ('homologacao', 'demonstracao', 'editorial'):
            texto = (RAIZ / 'deploy' / 'ambientes' / f'{ambiente}.env.example').read_text(encoding='utf-8')
            self.assertIn('VLADO_BACKUP_DESTINATARIOS', texto)
            self.assertIn('chave PÚBLICA', texto)
            self.assertIn('VLADO_BACKUP_RETENCAO=diarios=7,semanais=4,mensais=6', texto)
            self.assertNotIn('AGE-SECRET-KEY', texto)
        self.assertTrue((RAIZ / 'deploy' / 'BACKUP.md').is_file())

    def test_nenhum_arquivo_rastreado_contem_chave_privada_age(self):
        saida = subprocess.run(['git', 'grep', '-l', 'AGE-SECRET-KEY-1[0-9A-Z]\\{20,\\}', '--', '.'], cwd=RAIZ,
                               capture_output=True, text=True)
        arquivos = [a for a in saida.stdout.split() if a != 'testes/test_backup_agendado.py']
        self.assertEqual(arquivos, [], 'chave privada do age em arquivo versionado')


if __name__ == '__main__':
    unittest.main()
