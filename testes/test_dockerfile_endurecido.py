"""Fixa o endurecimento da imagem e do Compose (SEG-04): digests, lista de inclusão, trava com hashes,
sistema de arquivos somente leitura, capacidades mínimas e limites. Só lê arquivos do repositório."""
import ast
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
    'deploy/requirements.lock', 'interface/', 'prompts/', 'modelos/',
    'configuracao.json', 'AGENTS.md', 'README.md', 'precos_modelos.json', 'casos/README.md', 'casos/catalogo.json',
    'entrada/README.md', 'scripts/backup.py',  # esta última só no estágio `backup` (age + rclone), sem o app
}
PROIBIDO_NA_IMAGEM = ('.maestro', '.maestri', '.claude', '.git', 'segredos', 'acesso', 'ajustes', 'testes',
                      'docs', 'instalador', 'android', 'conversas', 'execucoes', 'lixeira')


def _dockerfile() -> list[str]:
    """Instruções do Dockerfile sem comentários, com as linhas de continuação (terminadas em barra invertida) juntadas."""
    barra = chr(92)
    linhas, acumulado = [], []
    for linha in (RAIZ / 'Dockerfile').read_text(encoding='utf-8').splitlines():
        if not acumulado and (not linha.strip() or linha.lstrip().startswith('#')):
            continue
        continua = linha.rstrip().endswith(barra)
        acumulado.append(linha.strip().removesuffix(barra).strip())
        if not continua:
            linhas.append(' '.join(parte for parte in acumulado if parte))
            acumulado = []
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


    def test_gerador_monta_so_os_requisitos_somente_leitura(self):
        """O contêiner do gerador tem rede: não pode ver segredos/, acesso/, casos/ nem o repositório (I3)."""
        sys.path.insert(0, str(RAIZ / 'deploy'))
        try:
            import gerar_trava
            comando = gerar_trava.comando_docker()
        finally:
            sys.path.remove(str(RAIZ / 'deploy'))
        montagens = [comando[i + 1] for i, a in enumerate(comando) if a == '-v']
        self.assertEqual(len(montagens), 2, montagens)
        for montagem in montagens:
            self.assertTrue(montagem.endswith(':ro'), montagem)
            self.assertRegex(montagem, r':/w/requirements(-opcional)?\.txt:ro$')
        self.assertNotIn(str(RAIZ) + ':', ' '.join(comando))


class ListaDeInclusaoTest(unittest.TestCase):
    def test_sem_copy_do_contexto_inteiro(self):
        for partes in _copias():
            for origem in partes[:-1]:
                self.assertNotIn(origem, ('.', './', '*', './*'), f'COPY do contexto inteiro: {partes}')

    def test_copy_so_do_que_a_mesa_le_em_execucao(self):
        for partes in _copias():
            for origem in partes[:-1]:
                if origem.startswith('scripts/'):  # um arquivo por vez (I5); o fecho de imports é conferido abaixo
                    self.assertRegex(origem, r'^scripts/[a-z_]+\.py$', f'COPY de scripts fora da lista por arquivo: {origem}')
                    continue
                self.assertIn(origem, COPY_PERMITIDO, f'COPY fora da lista de inclusão: {origem}')
                for proibido in PROIBIDO_NA_IMAGEM:
                    self.assertFalse(origem.strip('/').startswith(proibido), f'{origem} não pode entrar na imagem')
                self.assertTrue((RAIZ / origem.rstrip('/')).exists(), f'{origem} não existe')

    # Citados em mensagens de erro ("instale as dependências de requirements.txt"), nunca lidos em execução.
    SO_EM_MENSAGEM = {'requirements.txt', 'requirements-opcional.txt'}

    def test_arquivos_de_dados_que_os_scripts_da_imagem_leem_por_caminho_foram_copiados(self):
        """O teste do fecho só enxerga `import`; um arquivo lido do disco (precos_modelos.json, configuracao.json...) some da
        imagem sem aviso e a Mesa recusa perguntas ou não parte. Procura, nos scripts que a imagem copia, todo texto que é o nome de
        um arquivo de dados existente na raiz do projeto (ou em casos/ e entrada/) e exige que haja um COPY dele."""
        scripts = {Path(o).name for partes in _copias() for o in partes[:-1] if o.startswith('scripts/')} - {'backup.py'}
        self.assertGreater(len(scripts), 40)
        copiados_na_raiz = {o for partes in _copias() for o in partes[:-1] if '/' not in o and partes[-1] == './'}
        copiados_exatos = {o for partes in _copias() for o in partes[:-1]}
        padrao_raiz = re.compile(r'[A-Za-z0-9_.-]+\.(?:json|md|txt|csv)')
        padrao_pasta = re.compile(r'(?:casos|entrada)/[A-Za-z0-9_.-]+\.(?:json|md|txt|csv)')
        lidos_raiz, lidos_pasta = {}, {}
        for nome in sorted(scripts):
            for no in ast.walk(ast.parse((RAIZ / 'scripts' / nome).read_text(encoding='utf-8'))):
                if isinstance(no, ast.Constant) and isinstance(no.value, str):
                    if padrao_raiz.fullmatch(no.value) and (RAIZ / no.value).is_file():
                        lidos_raiz.setdefault(no.value, nome)
                    elif padrao_pasta.fullmatch(no.value) and (RAIZ / no.value).is_file():
                        lidos_pasta.setdefault(no.value, nome)
        for esperado in ('precos_modelos.json', 'configuracao.json'):
            self.assertIn(esperado, lidos_raiz, f'o teste deveria enxergar a leitura de {esperado}')
        faltando = {f: por for f, por in lidos_raiz.items() if f not in copiados_na_raiz and f not in self.SO_EM_MENSAGEM}
        self.assertEqual(faltando, {}, f'arquivos de dados lidos pelos scripts e fora da imagem (arquivo: script que o cita): {faltando}')
        faltando = {f: por for f, por in lidos_pasta.items() if f not in copiados_exatos}
        self.assertEqual(faltando, {}, f'arquivos de dados de casos/ e entrada/ lidos e fora da imagem: {faltando}')

    def test_tabela_de_precos_que_o_custo_le_esta_na_imagem_na_raiz_que_a_mesa_le(self):
        """scripts/custo.py lê `precos_modelos.json` de ROOT (a pasta do projeto, /app na imagem); sem ele a Mesa não pergunta."""
        fonte = (RAIZ / 'scripts' / 'custo.py').read_text(encoding='utf-8')
        self.assertIn("TABELA = 'precos_modelos.json'", fonte)
        self.assertIn('caminho = ROOT / TABELA', fonte)
        copias = {origem: partes[-1] for partes in _copias() for origem in partes[:-1]}
        self.assertEqual(copias.get('precos_modelos.json'), './', 'copiado para a raiz do WORKDIR (/app), onde ROOT aponta')
        self.assertTrue((RAIZ / 'precos_modelos.json').is_file())

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

    def test_scripts_da_imagem_do_app_sao_o_fecho_de_imports_da_mesa_mais_os_do_operador(self):
        """I5: nada que a Mesa importe pode faltar na imagem, e as ferramentas de desenvolvimento e do Windows
        não entram. O fecho é recalculado a partir de scripts/interface_pesquisa.py (import, from-import,
        importlib com texto e nomes de arquivo .py citados)."""
        modulos = {p.stem for p in (RAIZ / 'scripts').glob('*.py')}

        def dependencias(nome: str) -> set[str]:
            fonte = (RAIZ / 'scripts' / f'{nome}.py').read_text(encoding='utf-8')
            achados = set()
            for no in ast.walk(ast.parse(fonte)):
                if isinstance(no, ast.Import):
                    achados |= {a.name.split('.')[0] for a in no.names}
                elif isinstance(no, ast.ImportFrom):
                    if no.module and no.level == 0:
                        achados.add(no.module.split('.')[0])
                    elif no.level and not no.module:
                        achados |= {a.name for a in no.names}
            for m in modulos - {nome}:
                if re.search(rf"['\"/\\]{m}\.py['\"]|import_module\(['\"]{m}['\"]", fonte):
                    achados.add(m)
            return achados & modulos

        fecho, fila = set(), ['interface_pesquisa']
        while fila:
            atual = fila.pop()
            if atual not in fecho:
                fecho.add(atual)
                fila.extend(dependencias(atual))
        operador = {'semear_ambiente', 'dados_sinteticos'}
        copiados = {Path(o).stem for partes in _copias() for o in partes[:-1] if o.startswith('scripts/')}
        copiados_app = copiados - {'backup'}
        self.assertEqual(fecho - copiados, set(), 'a Mesa importa módulos que a imagem não copia')
        self.assertEqual(copiados_app, fecho | operador, 'a imagem copia módulos que a Mesa não usa')
        for ferramenta in ('gerar_instalador', 'vlado_lancador', 'demo_evidencias', 'preparar_notebook',
                           'empacotar_entrega', 'verificar_projeto', 'montar_fluxo', 'selecionar_caso', 'achados', 'backup'):
            self.assertNotIn(ferramenta, copiados_app, ferramenta)

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
            for chave in ('mem_limit', 'memswap_limit', 'cpu_shares', 'pids_limit'):
                self.assertRegex(bloco, rf'(?m)^    {chave}: ', f'{nome} sem {chave}')
        self.assertRegex(self.servicos['vlado'], r'stop_grace_period: ')
        texto = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('max-size', texto)
        self.assertIn('max-file', texto)

    def test_temporarios_do_ocr_em_disco_e_nao_em_memoria(self):
        """Um tmpfs grande conta na memória e 85 páginas coloridas esgotam 1 GB (I1): TMPDIR vai para volume."""
        bloco = self.servicos['vlado']
        self.assertIn('TMPDIR: /var/tmp/vlado', bloco)
        self.assertIn('tmp_vlado:/var/tmp/vlado', bloco)
        tamanho = re.search(r'/tmp:rw,noexec,nosuid,nodev,size=\$\{VLADO_TMP_TAMANHO:-(\d+)m\}', bloco)
        self.assertIsNotNone(tamanho, 'o /tmp em memória tem tamanho padrão pequeno, em MB')
        self.assertLessEqual(int(tamanho[1]), 128)
        dockerfile = (RAIZ / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('/var/tmp/vlado', dockerfile.split('AS vlado', 1)[1])
        self.assertIn('find /var/tmp/vlado -mindepth 1 -delete', dockerfile, 'esvazia os restos na partida')

    def test_cpu_so_por_peso_relativo_para_subir_em_qualquer_servidor(self):
        """`cpus` acima do número de núcleos impede o contêiner de subir (I2): o teto rígido é opcional."""
        compose = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertNotRegex(compose, r'(?m)^\s+cpus:')
        opcional = (RAIZ / 'deploy' / 'compose.limite-cpu.yml').read_text(encoding='utf-8')
        self.assertRegex(opcional, r'(?m)^    cpus: \$\{VLADO_CPUS:\?')

    def test_volumes_de_dados_nao_viram_bind_mount_do_hospedeiro(self):
        bloco = self.servicos['vlado']
        for linha in re.findall(r'(?m)^      - (\S+:/app/\S+)$', bloco):
            origem = linha.split(':', 1)[0]
            self.assertFalse(origem.startswith(('.', '/', '~')), f'bind mount de dados: {linha}')

    def test_caddy_espera_o_app_saudavel(self):
        self.assertRegex(self.servicos['caddy'], r'vlado:\n\s+condition: service_healthy')

    def test_home_gravavel_pequeno_e_limitado_nos_tres_servicos_que_rodam_como_vlado(self):
        """I8: com a raiz somente leitura, /home/vlado precisa de um destino gravável e pequeno (tmpfs com teto, dono
        uid 10001, noexec); /var/tmp continua só leitura, os temporários do OCR vão para o volume tmp_vlado."""
        for nome in ('vlado', 'backup', 'restauracao'):
            linha = re.search(r'(?m)^      - (/home/vlado:\S+)$', self.servicos[nome])
            self.assertIsNotNone(linha, f'{nome} sem tmpfs em /home/vlado')
            opcoes = linha[1]
            for exigido in ('rw', 'noexec', 'nosuid', 'nodev', 'uid=10001', 'gid=10001', 'mode=0700'):
                self.assertIn(exigido, opcoes, f'{nome}: {exigido}')
            tamanho = re.search(r'size=(?:\$\{[A-Z_]+:-)?(\d+)m', opcoes)
            self.assertIsNotNone(tamanho, f'{nome}: sem teto de tamanho')
            self.assertLessEqual(int(tamanho[1]), 32)
            self.assertNotRegex(self.servicos[nome], r'(?m)^      - /var/tmp:')


class VersoesDasFerramentasDeBackupTest(unittest.TestCase):
    def test_age_e_rclone_com_versao_fixada_e_conferida_no_build(self):
        """J4: nada de `apt-get install age rclone` sem versão; o build confere a versão instalada."""
        dockerfile = (RAIZ / 'Dockerfile').read_text(encoding='utf-8')
        estagio = dockerfile.split('AS backup', 1)[1].split('AS vlado', 1)[0]
        self.assertIn('"age=1.1.1-1*"', estagio)
        self.assertIn('"rclone=1.60.1+dfsg-2*"', estagio)
        self.assertIn(r"age --version | grep -q '^1\.1\.1'", estagio)
        self.assertIn(r"rclone version | head -1 | grep -q 'v1\.60\.1'", estagio)
        self.assertNotRegex(estagio, r'install[^\n]* age (?!=)')
        self.assertIn('FALHA, de propósito', estagio, 'o motivo e o jeito de atualizar ficam no arquivo')


if __name__ == '__main__':
    unittest.main()
