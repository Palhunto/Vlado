"""O Compose repassa ao app as variáveis da extração (CONF-02) e dos tetos do documento recebido (SEG-01), os exemplos de ambiente
documentam os padrões (que não podem divergir do código) e o ambiente local cabe no teto de 2 GB. Só lê arquivos do repositório; a
conferência com `docker compose config` roda se houver docker (não precisa do daemon)."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
import fila_extracao
import tetos_extracao

VARIAVEIS = ('PROCESSOS', 'PAGINAS', 'TEMPO_MAXIMO', 'TETO_PAGINAS', 'TETO_MEGAPIXELS', 'TETO_MEMORIA_MB', 'TETO_CPU_S', 'NUCLEOS')
NOMES = [f'VLADO_EXTRACAO_{v}' for v in VARIAVEIS]
EXEMPLOS = ('homologacao', 'editorial', 'demonstracao')


def servicos() -> dict[str, str]:
    texto = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
    corpo = texto.split('\nservices:\n', 1)[1].split('\nvolumes:\n', 1)[0]
    partes = re.split(r'(?m)^  ([a-z_]+):\s*$', corpo)
    return dict(zip(partes[1::2], partes[2::2]))


def padroes_do_codigo() -> dict:
    """Os padrões que o código aplica (com 4 CPUs, a máquina da D7), por nome de variável."""
    tetos = tetos_extracao.PADROES
    return {'VLADO_EXTRACAO_PROCESSOS': 2, 'VLADO_EXTRACAO_PAGINAS': 4, 'VLADO_EXTRACAO_TEMPO_MAXIMO': 4 * 3600,
            'VLADO_EXTRACAO_TETO_PAGINAS': tetos['paginas'], 'VLADO_EXTRACAO_TETO_MEGAPIXELS': tetos['megapixels'],
            'VLADO_EXTRACAO_TETO_MEMORIA_MB': tetos['memoria_mb'], 'VLADO_EXTRACAO_TETO_CPU_S': tetos['cpu_s'],
            'VLADO_EXTRACAO_NUCLEOS': 3}


class ComposeRepassaTest(unittest.TestCase):
    def test_o_app_recebe_cada_variavel_e_so_o_app(self):
        todos = servicos()
        for nome in NOMES:
            self.assertIn(f'      {nome}: ${{{nome}:-}}\n', todos['vlado'], nome)
            for outro in ('caddy', 'backup', 'restauracao'):
                self.assertNotIn(nome, todos[outro], f'{nome} não tem o que fazer em {outro}')

    def test_vazio_vale_o_padrao_do_codigo(self):
        """O Compose entrega texto vazio quando o ambiente não define a variável: o código tem de tratar como "usa o padrão"."""
        env = {nome: '' for nome in NOMES}
        antigo = {n: os.environ.get(n) for n in NOMES}
        try:
            os.environ.update(env)
            self.assertEqual(tetos_extracao.configuracao()['memoria_mb'], tetos_extracao.PADROES['memoria_mb'])
            configuracao = fila_extracao.configuracao('processos')
            self.assertEqual((configuracao['processos'], configuracao['tempo_maximo']), (2, 4 * 3600))
        finally:
            for nome, valor in antigo.items():
                if valor is None:
                    os.environ.pop(nome, None)
                else:
                    os.environ[nome] = valor

    @unittest.skipUnless(shutil.which('docker'), 'sem docker no PATH')
    def test_compose_config_entrega_cada_valor_ao_contêiner_do_app(self):
        valores = {nome: str(100 + i) for i, nome in enumerate(NOMES)}
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'x.env'
            arquivo.write_text('VLADO_AMBIENTE=homologacao\nVLADO_DOMINIO=x.example\n', encoding='utf-8')
            r = subprocess.run(['docker', 'compose', '-p', 'vlado-teste-extracao', '--env-file', str(arquivo), '-f', 'docker-compose.yml', 'config'],
                               cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', env=dict(os.environ, **valores))
        if r.returncode != 0 and 'unknown shorthand flag' in r.stderr:
            self.skipTest('docker sem o plugin compose')
        self.assertEqual(r.returncode, 0, r.stderr)
        for nome, valor in valores.items():
            self.assertRegex(r.stdout, rf'(?m)^      {nome}: "?{valor}"?$', nome)


class ExemplosDeAmbienteTest(unittest.TestCase):
    def comentadas(self, nome):
        texto = (RAIZ / 'deploy' / 'ambientes' / f'{nome}.env.example').read_text(encoding='utf-8')
        return dict(re.findall(r'(?m)^# (VLADO_EXTRACAO_[A-Z_]+)=(\S+)', texto))

    def test_os_tres_exemplos_de_servidor_trazem_as_oito_com_o_padrao_do_codigo(self):
        esperado = {k: str(v) for k, v in padroes_do_codigo().items()}
        for nome in EXEMPLOS:
            self.assertEqual(self.comentadas(nome), esperado, f'{nome}: variáveis ou padrões divergem do código')

    def test_no_servidor_os_padroes_cabem_no_teto_do_app(self):
        padroes = padroes_do_codigo()
        total = padroes['VLADO_EXTRACAO_PROCESSOS'] * padroes['VLADO_EXTRACAO_TETO_MEMORIA_MB']
        compose = servicos()['vlado']
        self.assertIn('${VLADO_MEM_LIMITE:-5g}', compose)
        self.assertLessEqual(total, 5 * 1024, 'o padrão do servidor (5g) comporta as extrações')


class AmbienteLocalCabeEm2GTest(unittest.TestCase):
    def setUp(self):
        texto = (RAIZ / 'deploy' / 'ambientes' / 'local.env.example').read_text(encoding='utf-8')
        self.env = dict(re.findall(r'(?m)^([A-Z][A-Z0-9_]*)=(.*)$', texto))
        self.texto = texto

    def test_um_processo_de_1024_mb(self):
        self.assertEqual((self.env['VLADO_EXTRACAO_PROCESSOS'], self.env['VLADO_EXTRACAO_TETO_MEMORIA_MB']), ('1', '1024'))

    def test_processos_vezes_teto_cabem_no_limite_do_app_com_folga_para_a_mesa(self):
        limite_mb = int(self.env['VLADO_MEM_LIMITE'].rstrip('g')) * 1024
        total = int(self.env['VLADO_EXTRACAO_PROCESSOS']) * int(self.env['VLADO_EXTRACAO_TETO_MEMORIA_MB'])
        self.assertLessEqual(total, limite_mb // 2, 'a Mesa precisa de pelo menos a metade do teto do app')
        padroes = padroes_do_codigo()
        self.assertGreater(padroes['VLADO_EXTRACAO_PROCESSOS'] * padroes['VLADO_EXTRACAO_TETO_MEMORIA_MB'], limite_mb,
                           'é por isso que o padrão de servidor não serve no local')

    def test_local_md_explica(self):
        local = (RAIZ / 'deploy' / 'LOCAL.md').read_text(encoding='utf-8')
        for trecho in ('Extração e OCR no teto de 2 GB', 'VLADO_EXTRACAO_PROCESSOS=1', 'VLADO_EXTRACAO_TETO_MEMORIA_MB=1024', 'em fila'):
            self.assertIn(trecho, local, trecho)

    def test_o_script_nao_recusa_as_novas_variaveis(self):
        """O script do ambiente local lê o arquivo inteiro; variável nova não pode ser tratada como a antiga porta."""
        script = (RAIZ / 'deploy' / 'vlado-local.ps1').read_bytes().decode('utf-8-sig')
        self.assertNotIn('VLADO_EXTRACAO', script)


if __name__ == '__main__':
    unittest.main()
