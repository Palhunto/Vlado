"""Teste de build das imagens (I7): constrói o Dockerfile de verdade e confere o que os testes de texto não alcançam.

LENTO e fora das suítes locais: só roda com Docker disponível E `VLADO_TESTE_IMAGEM=1`. Sem a variável, ou sem o daemon
do Docker, todos os testes saem como "pulados" na hora, sem tocar no Docker.

    VLADO_TESTE_IMAGEM=1 python -m unittest testes.test_imagem_build -v

Custo (build a frio, estimado): 4 a 8 min o app (apt do Tesseract e do Ghostscript, pip com hashes, ~640 MB) e cerca
de 1 min o backup; execução dos testes ~1 min; ~1,5 GB de disco temporário; 1 a 2 GB de RAM no pico; precisa de rede
(apt e pip). Com cache de camadas, menos de 1 min no total. Tags efêmeras `vlado-teste-imagem-<id>`: nada de `vlado:local`
nem de qualquer imagem ou contêiner da homologação; tudo o que este teste cria é removido no fim, com ou sem falha.
"""
import ast
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest
import uuid

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

HABILITADO = os.environ.get('VLADO_TESTE_IMAGEM') == '1'
# O mesmo conjunto de limites do Compose (docker-compose.yml): raiz somente leitura, sem capacidades, /home/vlado pequeno.
ENDURECIDO = ['--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
              '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=64m',
              '--tmpfs', '/home/vlado:rw,noexec,nosuid,nodev,size=16m,uid=10001,gid=10001,mode=0700',
              '--tmpfs', '/var/tmp/vlado:rw,nosuid,nodev,size=128m,uid=10001,gid=10001']
FERRAMENTAS_FORA = ('gerar_instalador', 'vlado_lancador', 'demo_evidencias', 'preparar_notebook',
                    'empacotar_entrega', 'verificar_projeto', 'montar_fluxo', 'selecionar_caso', 'achados', 'backup')


def docker(*args, timeout=300, entrada=None):
    return subprocess.run(['docker', *args], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=timeout, input=entrada)


def daemon_disponivel() -> bool:
    try:
        return docker('info', '--format', '{{.ServerVersion}}', timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def argumentos_de_cache(alvo) -> list:
    """Cache de camadas opcional, para o CI. Com `VLADO_BUILD_CACHE=<pasta>` o build usa o BuildKit (buildx) com cache
    local em `<pasta>/<estágio>` e carrega a imagem no daemon (`--load`, que um builder docker-container exige); sem a
    variável, é o `docker build` simples de sempre. O cache novo vai para `<estágio>-novo` (o workflow troca no fim):
    escrever sobre a própria origem só acumularia camadas velhas no cache salvo."""
    pasta = os.environ.get('VLADO_BUILD_CACHE')
    if not pasta:
        return []
    cache = f'{pasta}/{alvo or "app"}'
    return ['--load', '--cache-from', f'type=local,src={cache}', '--cache-to', f'type=local,dest={cache}-novo,mode=max']


def versoes_fixadas() -> dict:
    """age e rclone como o Dockerfile (estágio backup) os fixa: {'age': '1.1.1', 'rclone': '1.60.1'}."""
    texto = (RAIZ / 'Dockerfile').read_text(encoding='utf-8')
    estagio = texto.split('AS backup', 1)[1].split('AS vlado', 1)[0]
    return {'age': re.search(r'"age=(\d+(?:\.\d+)*)-', estagio)[1],
            'rclone': re.search(r'"rclone=(\d+(?:\.\d+)*)\+', estagio)[1]}


def scripts_copiados_pelo_dockerfile() -> set:
    """Nomes dos scripts que o estágio do app copia (do texto do Dockerfile, com as linhas de continuação)."""
    texto = (RAIZ / 'Dockerfile').read_text(encoding='utf-8').split('AS vlado', 1)[1]
    return set(re.findall(r'scripts/([a-z_]+)\.py', ' '.join(l for l in texto.splitlines() if not l.lstrip().startswith('#'))))


class ArgumentosDeCacheTest(unittest.TestCase):
    """O gancho de cache do CI: inerte sem a variável; com ela, cache por estágio e imagem carregada no daemon."""

    def test_sem_variavel_nao_muda_o_build(self):
        antes = os.environ.pop('VLADO_BUILD_CACHE', None)
        try:
            self.assertEqual(argumentos_de_cache(None), [])
            self.assertEqual(argumentos_de_cache('backup'), [])
        finally:
            if antes is not None:
                os.environ['VLADO_BUILD_CACHE'] = antes

    def test_com_variavel_cache_por_estagio_e_load(self):
        antes = os.environ.get('VLADO_BUILD_CACHE')
        os.environ['VLADO_BUILD_CACHE'] = '/tmp/.buildx-cache'
        try:
            app, backup = argumentos_de_cache(None), argumentos_de_cache('backup')
        finally:
            if antes is None:
                del os.environ['VLADO_BUILD_CACHE']
            else:
                os.environ['VLADO_BUILD_CACHE'] = antes
        self.assertIn('--load', app)
        self.assertIn('type=local,src=/tmp/.buildx-cache/app', app)
        self.assertIn('type=local,dest=/tmp/.buildx-cache/app-novo,mode=max', app)
        self.assertIn('type=local,src=/tmp/.buildx-cache/backup', backup)
        self.assertIn('type=local,dest=/tmp/.buildx-cache/backup-novo,mode=max', backup)


@unittest.skipUnless(HABILITADO, 'teste lento de build: defina VLADO_TESTE_IMAGEM=1 para rodar')
class ImagemBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not daemon_disponivel():
            raise unittest.SkipTest('Docker indisponível (o daemon não responde)')
        sufixo = f'{os.getpid()}-{uuid.uuid4().hex[:6]}'
        cls.app, cls.backup = f'vlado-teste-imagem-{sufixo}:app', f'vlado-teste-imagem-{sufixo}:backup'
        cls.contenedores = []
        cls.addClassCleanup(cls._limpar)
        for alvo, tag in (('backup', cls.backup), (None, cls.app)):  # sem --target: o estágio padrão, o do app
            comando = ['build', '-q', '-t', tag] + (['--target', alvo] if alvo else []) + argumentos_de_cache(alvo) + ['.']
            resultado = docker(*comando, timeout=1800)
            if resultado.returncode != 0:
                raise AssertionError(f'docker build ({alvo or "app"}) falhou:\n{resultado.stderr[-2000:]}')

    @classmethod
    def _limpar(cls):
        for nome in cls.contenedores:
            docker('rm', '-f', nome, timeout=60)
        docker('rmi', '-f', cls.app, cls.backup, timeout=120)

    def executar(self, imagem, *comando, opcoes=(), entrada=None, timeout=120):
        resultado = docker('run', '--rm', *(['-i'] if entrada else []), *opcoes, imagem, *comando, timeout=timeout, entrada=entrada)
        return resultado

    # --- imagem de backup -------------------------------------------------------------------------------

    def test_backup_tem_as_versoes_fixadas_do_age_e_do_rclone(self):
        fixadas = versoes_fixadas()
        age = self.executar(self.backup, 'age', '--version')
        self.assertEqual(age.returncode, 0, age.stderr)
        self.assertTrue(age.stdout.strip().startswith(fixadas['age']), age.stdout)
        rclone = self.executar(self.backup, 'rclone', 'version')
        self.assertEqual(rclone.returncode, 0, rclone.stderr)
        self.assertIn('v' + fixadas['rclone'], rclone.stdout.splitlines()[0])

    def test_backup_so_leva_o_script_de_backup_e_roda_sem_privilegios(self):
        r = self.executar(self.backup, 'sh', '-c', 'id -u; ls /app/scripts', opcoes=ENDURECIDO)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ['10001', 'backup.py'])
        r = self.executar(self.backup, 'python', 'scripts/backup.py', 'saude', opcoes=ENDURECIDO)
        self.assertNotEqual(r.returncode, 0, 'sem estado nem destino, a saúde do backup é "não"')
        self.assertNotIn('Traceback', r.stderr, 'o script precisa ao menos executar na imagem')

    # --- imagem do app ----------------------------------------------------------------------------------

    def test_app_so_leva_os_scripts_da_lista_e_nenhuma_ferramenta_de_desenvolvimento(self):
        r = self.executar(self.app, 'ls', '/app/scripts')
        self.assertEqual(r.returncode, 0, r.stderr)
        na_imagem = {n[:-3] for n in r.stdout.split() if n.endswith('.py')}
        self.assertEqual(na_imagem, scripts_copiados_pelo_dockerfile())
        for ferramenta in FERRAMENTAS_FORA:
            self.assertNotIn(ferramenta, na_imagem, ferramenta)
        for pasta in ('testes', 'docs', 'instalador', 'android', '.git'):
            self.assertNotEqual(self.executar(self.app, 'test', '-e', '/app/' + pasta).returncode, 0, pasta + ' entrou na imagem')
        # Pastas de dados existem só como ponto de montagem dos volumes: vazias (nenhum dado, nenhuma chave).
        for pasta in ('segredos', 'acesso', 'ajustes', 'conversas', 'execucoes', 'lixeira'):
            r = self.executar(self.app, 'sh', '-c', f'find /app/{pasta} -mindepth 1 | head -3')
            self.assertEqual(r.stdout.strip(), '', f'/app/{pasta} tem conteúdo na imagem: {r.stdout}')

    def test_todos_os_modulos_da_imagem_importam(self):
        codigo = ('import importlib, pathlib, sys; sys.path.insert(0, "/app/scripts"); falhas = []\n'
                  'for p in sorted(pathlib.Path("/app/scripts").glob("*.py")):\n'
                  '    try: importlib.import_module(p.stem)\n'
                  '    except Exception as e: falhas.append((p.stem, repr(e)[:100]))\n'
                  'print("FALHAS", falhas)\n')
        r = self.executar(self.app, 'python', '-c', codigo, opcoes=ENDURECIDO)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertIn('FALHAS []', r.stdout)

    def test_dependencias_consistentes_e_ocr_instalado(self):
        r = self.executar(self.app, 'pip', 'check')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        idiomas = self.executar(self.app, 'tesseract', '--list-langs')
        self.assertEqual(idiomas.returncode, 0, idiomas.stderr)
        for idioma in ('por', 'eng', 'osd'):
            self.assertIn(idioma, (idiomas.stdout + idiomas.stderr).split())
        self.assertEqual(self.executar(self.app, 'gs', '--version').returncode, 0)

    def test_home_e_gravavel_e_pequeno_e_var_tmp_continua_somente_leitura(self):
        script = ('id -u; touch /home/vlado/x && echo home-ok; touch /var/tmp/vlado/y && echo tmp-vlado-ok; '
                  'touch /var/tmp/z 2>/dev/null && echo var-tmp-GRAVAVEL; touch /app/scripts/z 2>/dev/null && echo app-GRAVAVEL; '
                  'dd if=/dev/zero of=/home/vlado/g bs=1M count=32 2>/dev/null || echo home-cheio')
        r = self.executar(self.app, 'sh', '-c', script, opcoes=ENDURECIDO)
        linhas = r.stdout.split()
        self.assertEqual(linhas[0], '10001', r.stdout + r.stderr)
        self.assertIn('home-ok', linhas)
        self.assertIn('tmp-vlado-ok', linhas)
        self.assertIn('home-cheio', linhas, '/home/vlado deveria ter teto (16 MiB)')
        self.assertNotIn('var-tmp-GRAVAVEL', linhas)
        self.assertNotIn('app-GRAVAVEL', linhas)

    def test_a_mesa_sobe_e_responde_saude_com_a_raiz_somente_leitura(self):
        nome = f'vlado-teste-imagem-app-{uuid.uuid4().hex[:6]}'
        self.contenedores.append(nome)
        r = docker('run', '-d', '--name', nome, *ENDURECIDO, '-e', 'VLADO_DOMINIO=teste.example',
                   '-e', 'VLADO_AMBIENTE=homologacao', '-e', 'VLADO_CONFIAR_PROXY=1', self.app, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        sonda = 'import urllib.request as u; print(u.urlopen("http://127.0.0.1:8765/saude", timeout=4).status)'
        fim, ultimo = time.monotonic() + 90, ''
        while time.monotonic() < fim:
            ultimo = docker('exec', nome, 'python', '-c', sonda, timeout=30).stdout.strip()
            if ultimo == '200':
                break
            time.sleep(2)
        logs = docker('logs', '--tail', '20', nome, timeout=30)
        self.assertEqual(ultimo, '200', 'a Mesa não respondeu /saude em 90 s:\n' + logs.stdout + logs.stderr)


class AuxiliaresDoTesteDeImagemTest(unittest.TestCase):
    """Roda sempre (sem Docker): garante que os auxiliares leem o Dockerfile e que o teste lento fica desligado por padrão."""

    def test_versoes_fixadas_saem_do_dockerfile(self):
        self.assertEqual(versoes_fixadas(), {'age': '1.1.1', 'rclone': '1.60.1'})

    def test_scripts_copiados_conferem_com_o_teste_de_texto(self):
        from test_dockerfile_endurecido import _copias
        esperados = {Path(o).stem for partes in _copias() for o in partes[:-1] if o.startswith('scripts/')} - {'backup'}
        self.assertEqual(scripts_copiados_pelo_dockerfile(), esperados)
        self.assertGreater(len(esperados), 40)

    def test_o_teste_lento_exige_a_variavel_e_nao_toca_no_docker_sem_ela(self):
        fonte = (RAIZ / 'testes' / 'test_imagem_build.py').read_text(encoding='utf-8')
        self.assertIn("os.environ.get('VLADO_TESTE_IMAGEM') == '1'", fonte)
        arvore = ast.parse(fonte)
        chamadas = [n.value.func.id for n in arvore.body
                    if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)]
        self.assertEqual(chamadas, [], 'nada de chamada ao Docker na importação')
        self.assertNotIn('vlado' + ':local', re.sub(r'`[^`]*`|"""[\s\S]*?"""', '', fonte))

    def test_o_modulo_esta_marcado_como_lento(self):
        lentos = (RAIZ / 'testes' / 'suite_lenta.txt').read_text(encoding='utf-8').split()
        self.assertIn('test_imagem_build', lentos)


if __name__ == '__main__':
    unittest.main()
