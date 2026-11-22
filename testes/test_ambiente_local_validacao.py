"""Validações do script do ambiente local (A1, A2 e A3 da revisão): o deploy/vlado-local.ps1 só age em projeto
`vlado-local*` e em contêineres criados por ele, recusa etiqueta de imagem `local`/vazia e porta fora de 127.0.0.1.

O script roda de verdade (PowerShell), mas com um `docker` de mentira no PATH que só registra os comandos: nenhuma imagem,
contêiner ou volume é tocado. Os casos de recusa precisam sair ANTES de qualquer chamada ao Docker (registro vazio).
Só no Windows com `powershell` disponível; fora disso os testes de execução são pulados e os de texto continuam."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / 'deploy' / 'vlado-local.ps1'
POWERSHELL = shutil.which('powershell') if os.name == 'nt' else None

DOCKER_FALSO = """@echo off
setlocal
(echo %*)>>"%DOCKER_FALSO_LOG%"
if "%1"=="ps" (
  echo %* | findstr /C:"ambiente-local=1" >nul
  if errorlevel 1 ( if defined DOCKER_FALSO_TODOS echo %DOCKER_FALSO_TODOS% ) else ( if defined DOCKER_FALSO_NOSSOS echo %DOCKER_FALSO_NOSSOS% )
)
if "%1"=="compose" (echo AMBIENTE VERSAO=%VLADO_VERSAO% PORTA=%VLADO_LOCAL_PORTA%)>>"%DOCKER_FALSO_LOG%"
exit /b 0
"""


def exemplo(**mudancas) -> str:
    """local.env.example com a pasta de backup apontando para um lugar temporário e as mudanças pedidas.
    Valor None apaga a linha; chave nova é acrescentada."""
    texto = (RAIZ / 'deploy' / 'ambientes' / 'local.env.example').read_text(encoding='utf-8')
    linhas = []
    for linha in texto.splitlines():
        achado = re.match(r'^([A-Z][A-Z0-9_]*)=', linha)
        if achado and achado[1] in mudancas:
            if mudancas[achado[1]] is not None:
                linhas.append(f'{achado[1]}={mudancas[achado[1]]}')
            mudancas = {k: v for k, v in mudancas.items() if k != achado[1]}
            continue
        linhas.append(linha)
    for chave, valor in mudancas.items():
        if valor is not None:
            linhas.append(f'{chave}={valor}')
    return '\n'.join(linhas) + '\n'


@unittest.skipUnless(POWERSHELL and SCRIPT.exists(), 'precisa do Windows PowerShell')
class ScriptRecusaAntesDeTocarNoDockerTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        (self.base / 'bin').mkdir()
        (self.base / 'bin' / 'docker.cmd').write_text(DOCKER_FALSO, encoding='utf-8')
        self.log = self.base / 'docker.log'
        self.pasta_backup = (self.base / 'backups').as_posix()

    def rodar(self, comando='subir', projeto=None, env=None, ambiente=None, entrada=None):
        arquivo = self.base / 'ambiente.env'
        arquivo.write_text(env if env is not None else exemplo(VLADO_LOCAL_BACKUP_PASTA=self.pasta_backup), encoding='utf-8')
        argumentos = [POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
                      comando, '-ArquivoEnv', str(arquivo)]
        if projeto is not None:
            argumentos += ['-Projeto', projeto]
        variaveis = dict(os.environ, PATH=str(self.base / 'bin') + os.pathsep + os.environ['PATH'],
                         DOCKER_FALSO_LOG=str(self.log), **(ambiente or {}))
        resultado = subprocess.run(argumentos, cwd=RAIZ, capture_output=True, text=True, encoding='utf-8',
                                   errors='replace', env=variaveis, input=entrada, timeout=120)
        return resultado, (self.log.read_text(encoding='utf-8', errors='replace') if self.log.exists() else '')

    def assertRecusou(self, resultado, registro, mensagem, docker=False):
        saida = re.sub(r'\s+', ' ', resultado.stdout + resultado.stderr)  # o PowerShell quebra a linha do erro no console
        self.assertNotEqual(resultado.returncode, 0, saida)
        self.assertRegex(saida, mensagem)
        if not docker:
            self.assertEqual(registro.strip(), '', 'recusou DEPOIS de chamar o Docker:\n' + registro)
        self.assertNotRegex(registro, r'(?m)^compose ', 'chegou ao docker compose:\n' + registro)

    # --- A1: o projeto ----------------------------------------------------------------------------------

    def test_recusa_a_homologacao_e_qualquer_projeto_que_nao_seja_vlado_local(self):
        for projeto in ('vlado-homologacao', 'vlado-homologacao-1', 'outro-vlado-local', 'VLADO-LOCAL', 'vlado_local'):
            for comando in ('subir', 'restaurar', 'apagar-tudo', 'esquecer-ca'):
                with self.subTest(projeto=projeto, comando=comando):
                    r, registro = self.rodar(comando, projeto, entrada='RESTAURAR\n' + projeto + '\n')
                    self.assertRecusou(r, registro, r"come.ar com 'vlado-local'")

    def test_aceita_o_nome_padrao_e_variacoes_vlado_local(self):
        for projeto in (None, 'vlado-localteste', 'vlado-local-2'):
            with self.subTest(projeto=projeto):
                r, registro = self.rodar('parar', projeto)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertRegex(registro, rf'compose -p {projeto or "vlado-local"} ')

    def test_recusa_projeto_com_conteineres_que_nao_sao_deste_ambiente(self):
        for comando in ('subir', 'apagar-tudo'):
            with self.subTest(comando=comando):
                if self.log.exists():
                    self.log.unlink()
                r, registro = self.rodar(comando, 'vlado-local', ambiente={'DOCKER_FALSO_TODOS': 'abc123'},
                                         entrada=f'vlado-local\n')
                self.assertRecusou(r, registro, r'n.o foram criados por este ambiente local', docker=True)
                self.assertIn('label=com.vlado.ambiente-local=1', registro, 'conferiu o rótulo')

    def test_projeto_so_com_conteineres_do_ambiente_local_segue_em_frente(self):
        r, registro = self.rodar('parar', 'vlado-local', ambiente={'DOCKER_FALSO_TODOS': 'abc123', 'DOCKER_FALSO_NOSSOS': 'abc123'})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(registro, r'(?m)^compose -p vlado-local .* stop')

    def test_o_rotulo_esta_em_todos_os_servicos_da_camada_local(self):
        texto = (RAIZ / 'deploy' / 'compose.local.yml').read_text(encoding='utf-8')
        self.assertEqual(texto.count('com.vlado.ambiente-local: "1"'), 1, 'definido uma vez, reaproveitado por âncora')
        for servico in ('caddy', 'vlado', 'backup', 'restauracao'):
            self.assertRegex(texto, rf'(?m)^  {servico}:\n    labels: (&dono_local|\*dono_local)', servico)

    # --- A2: a etiqueta da imagem -----------------------------------------------------------------------

    def test_recusa_etiqueta_de_imagem_vazia_ausente_ou_vlado_local(self):
        for versao in ('', None, 'local', '2.2.0', 'localteste', 'local-', 'vlado:local'):
            with self.subTest(versao=versao):
                r, registro = self.rodar('subir', env=exemplo(VLADO_LOCAL_BACKUP_PASTA=self.pasta_backup, VLADO_VERSAO=versao))
                self.assertRecusou(r, registro, r'VLADO_VERSAO.*recusada.*local-')

    def test_aceita_etiqueta_local_com_sufixo_e_ela_vence_a_variavel_da_sessao(self):
        r, registro = self.rodar('parar', ambiente={'VLADO_VERSAO': 'local', 'VLADO_LOCAL_PORTA': '80'})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('VERSAO=local-dono PORTA=9443', registro, 'o valor do arquivo substitui o da sessão')

    # --- A3: a porta ------------------------------------------------------------------------------------

    def test_recusa_porta_que_nao_e_so_um_numero_valido(self):
        for porta in ('0.0.0.0:9443', '9443;calc', '80', '70000', '', '127.0.0.1:9443', None):
            with self.subTest(porta=porta):
                env = exemplo(VLADO_LOCAL_BACKUP_PASTA=self.pasta_backup, VLADO_LOCAL_PORTA=porta, VLADO_ORIGEM='https://vlado.localhost:' + (porta or ''))
                r, registro = self.rodar('subir', env=env)
                self.assertRecusou(r, registro, r'VLADO_LOCAL_PORTA.*recusada')

    def test_recusa_o_formato_antigo_que_publicaria_em_todas_as_interfaces(self):
        for antiga in ('VLADO_PORTA_HTTPS', 'VLADO_PORTA_HTTP'):
            for valor in ('0.0.0.0:9443', '8080'):
                with self.subTest(variavel=antiga, valor=valor):
                    env = exemplo(VLADO_LOCAL_BACKUP_PASTA=self.pasta_backup, **{antiga: valor})
                    r, registro = self.rodar('subir', env=env)
                    self.assertRecusou(r, registro, rf'{antiga} n.o vale mais.*VLADO_LOCAL_PORTA')

    def test_origem_dominio_caddyfile_e_ambiente_conferidos(self):
        casos = {
            'origem': ({'VLADO_ORIGEM': 'https://vlado.localhost:9444'}, r'VLADO_ORIGEM.*exatamente'),
            'origem http': ({'VLADO_ORIGEM': 'http://vlado.localhost:9443'}, r'VLADO_ORIGEM.*exatamente'),
            'caddyfile público': ({'VLADO_CADDYFILE': 'deploy/Caddyfile'}, r'VLADO_CADDYFILE.*Caddyfile.interno'),
            'editorial': ({'VLADO_AMBIENTE': 'editorial'}, r'VLADO_AMBIENTE.*dados sint.ticos'),
        }
        for nome, (mudanca, mensagem) in casos.items():
            with self.subTest(caso=nome):
                r, registro = self.rodar('subir', env=exemplo(VLADO_LOCAL_BACKUP_PASTA=self.pasta_backup, **mudanca))
                self.assertRecusou(r, registro, mensagem)

    def test_porta_valida_diferente_sobe_com_origem_coerente(self):
        env = exemplo(VLADO_LOCAL_BACKUP_PASTA=self.pasta_backup, VLADO_LOCAL_PORTA='9555', VLADO_ORIGEM='https://vlado.localhost:9555')
        r, registro = self.rodar('subir', env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('PORTA=9555', registro)
        self.assertRegex(registro, r'(?m)^compose -p vlado-local .* up -d --build')
        self.assertIn('https://vlado.localhost:9555', r.stdout)

    def test_comando_desconhecido_so_mostra_a_ajuda_sem_tocar_no_docker(self):
        r, registro = self.rodar('apagar-homologacao')
        self.assertEqual(registro.strip(), '')
        self.assertIn('vlado-local', r.stdout)


@unittest.skipUnless(shutil.which('docker'), 'sem docker no PATH')
class PortaNoComposeEFixaEmLoopbackTest(unittest.TestCase):
    """A3, segunda barreira: mesmo chamando o compose à mão, com VLADO_PORTA_HTTPS maliciosa na sessão ou no arquivo,
    só a porta do ambiente local é publicada e só em 127.0.0.1."""

    def config(self, extra_env: dict, texto_env: str) -> str:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'local.env'
            arquivo.write_text(texto_env.replace('C:/Users/SEU-USUARIO/Vlado-backups-teste', pasta.replace(chr(92), '/')), encoding='utf-8')
            r = subprocess.run(['docker', 'compose', '-p', 'vlado-localteste-unit', '--env-file', str(arquivo),
                                '-f', 'docker-compose.yml', '-f', 'deploy/compose.local.yml', 'config'],
                               cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', env=dict(os.environ, **extra_env))
        if r.returncode != 0 and 'unknown shorthand flag' in r.stderr:
            self.skipTest('docker sem o plugin compose')
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_porta_publicada_so_em_127_0_0_1_mesmo_com_variavel_hostil(self):
        base = (RAIZ / 'deploy' / 'ambientes' / 'local.env.example').read_text(encoding='utf-8')
        for extra, texto in (({}, base),
                             ({'VLADO_PORTA_HTTPS': '0.0.0.0:443', 'VLADO_PORTA_HTTP': '0.0.0.0:80'}, base),
                             ({}, base + 'VLADO_PORTA_HTTPS=0.0.0.0:443\nVLADO_PORTA_HTTP=80\n')):
            with self.subTest(extra=extra, no_arquivo='PORTA_HTTPS=0.0.0.0' in texto):
                saida = self.config(extra, texto)
                self.assertEqual(re.findall(r'published: "(\d+)"', saida), ['9443'], saida)
                self.assertEqual(re.findall(r'host_ip: (\S+)', saida), ['127.0.0.1'], saida)
                self.assertGreaterEqual(saida.count('com.vlado.ambiente-local: "1"'), 3)


if __name__ == '__main__':
    unittest.main()
