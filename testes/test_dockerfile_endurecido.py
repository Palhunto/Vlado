"""Fixa o endurecimento da imagem e do Compose (SEG-04): digests, lista de inclusão, trava com hashes,
sistema de arquivos somente leitura, capacidades mínimas e limites. Só lê arquivos do repositório."""
from fnmatch import fnmatchcase
from pathlib import Path
import re
import sys
import unittest

RAIZ = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r'@sha256:[0-9a-f]{64}$')
# O que a Mesa hospedada lê em execução. Ampliar exige decisão consciente: cada item novo vira superfície
# da imagem. Pastas de agente, docs, testes, instalador, Android e dados nunca entram.
COPY_PERMITIDO = {
    'deploy/requirements.lock', 'scripts/', 'interface/', 'prompts/', 'modelos/',
    'configuracao.json', 'AGENTS.md', 'README.md', 'casos/README.md', 'casos/catalogo.json',
    'entrada/README.md', 'scripts/backup.py',  # esta última só no estágio `backup` (age + rclone), sem o app
}
PROIBIDO_NA_IMAGEM = ('.maestro', '.maestri', '.claude', '.git', 'segredos', 'acesso', 'ajustes', 'testes',
                      'docs', 'instalador', 'android', 'conversas', 'execucoes', 'lixeira')


def _dockerfile() -> list[str]:
    linhas = []
    for linha in (RAIZ / 'Dockerfile').read_text(encoding='utf-8').splitlines():
        if linha.strip() and not linha.lstrip().startswith('#'):
            linhas.append(linha.strip())
    return linhas


def _copias() -> list[list[str]]:
    copias = []
    for linha in _dockerfile():
        if linha.upper().startswith('COPY '):
            partes = [p for p in linha.split()[1:] if not p.startswith('--')]
            copias.append(partes)
    return copias


def _servicos() -> dict[str, str]:
    """Blocos de texto de cada serviço do compose (sem depender de PyYAML)."""
    texto = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
    inicio = re.search(r'^services:\s*$', texto, flags=re.MULTILINE)
    resto = texto[inicio.end():]
    fim = re.search(r'^\S', resto, flags=re.MULTILINE)
    corpo = resto[:fim.start()] if fim else resto
    blocos = {}
    pedacos = re.split(r'^  ([a-z_]+):\s*$', corpo, flags=re.MULTILINE)
    for nome, bloco in zip(pedacos[1::2], pedacos[2::2]):
        blocos[nome] = bloco
    return blocos


class ImagemPorDigestTest(unittest.TestCase):
    def test_from_por_digest_com_etiqueta_de_origem_comentada(self):
        texto = (RAIZ / 'Dockerfile').read_text(encoding='utf-8')
        froms = [l.split()[1] for l in _dockerfile() if l.upper().startswith('FROM ')]
        self.assertTrue(froms)
        for imagem in froms:
            self.assertRegex(imagem, DIGEST, f'FROM sem digest: {imagem}')
        self.assertIn('python:3.12-slim-bookworm', texto.split('FROM ', 1)[0], 'comentário com a etiqueta de origem')
        self.assertEqual(len(set(froms)), 1, 'os estágios partem do mesmo digest')

    def test_estagio_de_backup_so_leva_o_script_de_backup(self):
        linhas = _dockerfile()
        inicio = next(i for i, l in enumerate(linhas) if l.upper().startswith('FROM ') and l.endswith(' AS backup'))
        fim = next(i for i, l in enumerate(linhas) if i > inicio and l.upper().startswith('FROM '))
        copias = [l.split()[1:] for l in linhas[inicio:fim] if l.upper().startswith('COPY ')]
        self.assertEqual(copias, [['scripts/backup.py', './scripts/backup.py']])
        self.assertTrue(linhas[-3].startswith('HEALTHCHECK') or any(l.startswith('CMD') for l in linhas[fim:]))
        self.assertTrue(linhas[fim].endswith(' AS vlado'), 'o estágio do app é o último (padrão do build)')

    def test_caddy_por_digest_com_etiqueta_de_origem_comentada(self):
        texto = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        for nome, bloco in _servicos().items():
            for imagem in re.findall(r'^\s+image:\s*(\S+)', bloco, flags=re.MULTILINE):
                if nome in ('vlado', 'backup', 'restauracao'):  # imagens construídas aqui (base por digest no Dockerfile)
                    continue
                self.assertRegex(imagem, DIGEST, f'{nome}: imagem sem digest ({imagem})')
        self.assertIn('Etiqueta de origem: caddy:2.8', texto)


class TravaDeDependenciasTest(unittest.TestCase):
    def setUp(self):
        self.trava = (RAIZ / 'deploy' / 'requirements.lock').read_text(encoding='utf-8')

    def test_dockerfile_instala_so_com_hashes(self):
        instalacoes = [l for l in _dockerfile() if 'pip install' in l]
        self.assertEqual(len(instalacoes), 1, instalacoes)
        self.assertIn('--require-hashes', instalacoes[0])
        self.assertIn('deploy/requirements.lock', instalacoes[0])
        self.assertNotIn('requirements.txt', ' '.join(l for l in _dockerfile() if l.upper().startswith('COPY')))

    def test_todo_pacote_da_trava_tem_versao_exata_e_hash(self):
        pacotes = re.split(r'\n(?=[A-Za-z0-9][A-Za-z0-9._-]*==)', '\n' + self.trava)[1:]
        self.assertGreater(len(pacotes), 20)
        for bloco in pacotes:
            nome = bloco.split('==', 1)[0]
            self.assertRegex(bloco, r'^[A-Za-z0-9._-]+==[0-9][^\s\\]*', nome)
            self.assertRegex(bloco, r'--hash=sha256:[0-9a-f]{64}', f'{nome} sem hash')

    def test_trava_cobre_as_dependencias_diretas_com_a_mesma_versao(self):
        # Nome normalizado como o pip faz: minúsculas, sublinhado e ponto viram hífen.
        travados = {re.sub(r'[-_.]+', '-', n).lower(): v for n, v in re.findall(r'^([A-Za-z0-9._-]+)==(\S+?)(?:\s|\\)', self.trava, flags=re.MULTILINE)}
        for arquivo in ('requirements.txt',):
            for linha in (RAIZ / arquivo).read_text(encoding='utf-8').splitlines():
                achado = re.match(r'^([A-Za-z0-9._-]+)==(\S+)$', linha.strip())
                if achado:
                    nome = re.sub(r'[-_.]+', '-', achado[1]).lower()
                    self.assertEqual(travados.get(nome), achado[2], f'{nome} diverge de requirements.txt: regere deploy/requirements.lock')

    def test_gerador_le_o_digest_do_dockerfile(self):
        sys.path.insert(0, str(RAIZ / 'deploy'))
        try:
            import gerar_trava
            self.assertRegex(gerar_trava.imagem_base(), r'^python:3\.12-slim-bookworm@sha256:[0-9a-f]{64}$')
        finally:
            sys.path.remove(str(RAIZ / 'deploy'))


class ListaDeInclusaoTest(unittest.TestCase):
    def test_sem_copy_do_contexto_inteiro(self):
        for partes in _copias():
            for origem in partes[:-1]:
                self.assertNotIn(origem, ('.', './', '*', './*'), f'COPY do contexto inteiro: {partes}')

    def test_copy_so_do_que_a_mesa_le_em_execucao(self):
        for partes in _copias():
            for origem in partes[:-1]:
                self.assertIn(origem, COPY_PERMITIDO, f'COPY fora da lista de inclusão: {origem}')
                for proibido in PROIBIDO_NA_IMAGEM:
                    self.assertFalse(origem.strip('/').startswith(proibido), f'{origem} não pode entrar na imagem')
                self.assertTrue((RAIZ / origem.rstrip('/')).exists(), f'{origem} não existe')

    def test_dockerignore_nao_esconde_o_que_o_copy_precisa(self):
        regras = [l.strip() for l in (RAIZ / '.dockerignore').read_text(encoding='utf-8').splitlines()
                  if l.strip() and not l.lstrip().startswith('#')]

        def ignorado(caminho: str) -> bool:
            estado = False
            for regra in regras:
                negacao = regra.startswith('!')
                padrao = regra.lstrip('!').rstrip('/')
                pais = [caminho] + [caminho.rsplit('/', n)[0] for n in range(1, caminho.count('/') + 1)]
                if any(fnmatchcase(p, padrao) for p in pais):
                    estado = not negacao
            return estado

        for partes in _copias():
            for origem in partes[:-1]:
                self.assertFalse(ignorado(origem.rstrip('/')), f'.dockerignore esconde {origem}, que o COPY precisa')

    def test_dockerignore_amplo_cobre_agentes_segredos_e_dumps(self):
        regras = {l.strip() for l in (RAIZ / '.dockerignore').read_text(encoding='utf-8').splitlines()}
        for padrao in ('**/.git', '**/.venv', '**/.env', '**/*.sqlite', '**/*.db', '**/*.tar.gz', '**/chaves.json',
                       'docs', '.github', 'instalador', 'android', 'backups', '**/.maestro'):
            self.assertIn(padrao, regras, f'.dockerignore sem {padrao}')


class ComposeEndurecidoTest(unittest.TestCase):
    def setUp(self):
        self.servicos = _servicos()

    def test_servicos_esperados(self):
        self.assertEqual(set(self.servicos), {'vlado', 'caddy', 'backup', 'restauracao'})

    def test_cada_servico_com_init_somente_leitura_e_sem_privilegios(self):
        for nome, bloco in self.servicos.items():
            self.assertRegex(bloco, r'(?m)^    init: true$', f'{nome} sem init')
            self.assertRegex(bloco, r'(?m)^    read_only: true$', f'{nome} sem read_only')
            self.assertRegex(bloco, r'(?m)^    cap_drop:\n      - ALL$', f'{nome} sem cap_drop ALL')
            self.assertIn('no-new-privileges:true', bloco, f'{nome} sem no-new-privileges')
            self.assertNotRegex(bloco, r'privileged:\s*true')
            self.assertRegex(bloco, r'(?m)^    tmpfs:\n      - /tmp:', f'{nome} sem tmpfs em /tmp')
            self.assertRegex(bloco, r'noexec,nosuid,nodev', f'{nome}: tmpfs deve ser noexec,nosuid,nodev')

    def test_capacidade_devolvida_so_ao_caddy_e_so_uma(self):
        self.assertNotIn('cap_add', self.servicos['vlado'])
        bloco = self.servicos['caddy']
        self.assertIn('cap_add:', bloco)
        lista = bloco.split('cap_add:', 1)[1].split('security_opt:', 1)[0]
        devolvidas = re.findall(r'(?m)^      - (\S+)$', lista)
        self.assertEqual(devolvidas, ['NET_BIND_SERVICE'], 'só NET_BIND_SERVICE volta ao Caddy')

    def test_limites_de_memoria_cpu_processos_e_logs(self):
        for nome, bloco in self.servicos.items():
            for chave in ('mem_limit', 'memswap_limit', 'cpus', 'pids_limit'):
                self.assertRegex(bloco, rf'(?m)^    {chave}: ', f'{nome} sem {chave}')
        self.assertRegex(self.servicos['vlado'], r'stop_grace_period: ')
        texto = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('max-size', texto)
        self.assertIn('max-file', texto)

    def test_volumes_de_dados_nao_viram_bind_mount_do_hospedeiro(self):
        bloco = self.servicos['vlado']
        for linha in re.findall(r'(?m)^      - (\S+:/app/\S+)$', bloco):
            origem = linha.split(':', 1)[0]
            self.assertFalse(origem.startswith(('.', '/', '~')), f'bind mount de dados: {linha}')

    def test_caddy_espera_o_app_saudavel(self):
        self.assertRegex(self.servicos['caddy'], r'vlado:\n\s+condition: service_healthy')


if __name__ == '__main__':
    unittest.main()
