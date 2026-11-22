"""Ambiente local no computador do dono (decisão D7): o exemplo de ambiente, a camada do Compose, o script do
PowerShell e o roteiro. Só lê arquivos do repositório (e, se houver `docker`, valida a combinação com `compose config`,
que não precisa do daemon). O ensaio real, com contêineres, está no registro de verificação da entrega."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]


def ler(caminho: str) -> str:
    return (RAIZ / caminho).read_text(encoding='utf-8-sig')


def variaveis(texto: str) -> dict:
    """CHAVE=VALOR das linhas ativas (não comentadas)."""
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r'(?m)^([A-Z][A-Z0-9_]*)=(.*)$', texto)}


def gigas(valor: str) -> float:
    numero, unidade = re.fullmatch(r'(\d+(?:\.\d+)?)([mg])', valor).groups()
    return float(numero) / (1024 if unidade == 'm' else 1)


class ExemploDeAmbienteLocalTest(unittest.TestCase):
    def setUp(self):
        self.texto = ler('deploy/ambientes/local.env.example')
        self.env = variaveis(self.texto)

    def test_nao_colide_com_a_homologacao_que_ja_roda_no_computador(self):
        # A homologação do dono publica 127.0.0.1:443 e 127.0.0.1:8080 e usa a imagem vlado:local.
        self.assertTrue(self.env['VLADO_PORTA_HTTPS'].startswith('127.0.0.1:'), 'só o próprio computador alcança')
        self.assertNotIn(self.env['VLADO_PORTA_HTTPS'].split(':')[-1], ('80', '443', '8080', '8443'))
        self.assertNotIn('VLADO_PORTA_HTTP', self.env, 'a porta HTTP fica fechada (compose.local.yml)')
        self.assertNotEqual(self.env['VLADO_VERSAO'], 'local', 'não pode reaproveitar a imagem vlado:local')
        # .localhost: separa os cookies do `localhost` da homologação (cookie não distingue porta).
        self.assertTrue(self.env['VLADO_DOMINIO'].endswith('.localhost'))
        self.assertEqual(self.env['VLADO_ORIGEM'],
                         f"https://{self.env['VLADO_DOMINIO']}:{self.env['VLADO_PORTA_HTTPS'].split(':')[-1]}")

    def test_usa_a_ca_interna_e_ambiente_sintetico(self):
        self.assertEqual(self.env['VLADO_CADDYFILE'], 'deploy/Caddyfile.interno')
        self.assertEqual(self.env['VLADO_AMBIENTE'], 'homologacao')

    def test_limites_cabem_em_8_gb_com_os_agentes(self):
        app, backup = gigas(self.env['VLADO_MEM_LIMITE']), gigas(self.env['VLADO_BACKUP_MEM_LIMITE'])
        self.assertLessEqual(app, 2.0, 'o padrão de servidor (5 GB) não cabe junto com os agentes')
        self.assertLessEqual(app + backup + 0.25, 3.0)  # + Caddy, 256 MB fixos no compose

    def test_backup_vai_para_pasta_local_e_exige_preencher_pasta_e_chave_publica(self):
        self.assertEqual(self.env['VLADO_BACKUP_DESTINO'], '/destino-backup')
        self.assertIn('SEU-USUARIO', self.env['VLADO_LOCAL_BACKUP_PASTA'])
        self.assertEqual(self.env['VLADO_BACKUP_DESTINATARIOS'], '', 'a chave pública é do dono, não vem no exemplo')
        self.assertEqual(self.env['VLADO_BACKUP_AO_INICIAR'], '1', 'o computador pode estar desligado no horário')
        self.assertGreaterEqual(float(self.env['VLADO_BACKUP_IDADE_MAX_H']), 48)

    def test_vigia_desligada_e_sem_segredo_no_exemplo(self):
        self.assertNotIn('VLADO_VIGIA_PING_URL', self.env)
        self.assertRegex(self.texto, r'(?m)^# VLADO_VIGIA_PING_URL=\s*$')
        self.assertIn('DESLIGADA', self.texto)
        for chave in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VLADO_BACKUP_CHAVE_PRIVADA'):
            self.assertNotIn(chave, self.env)
        self.assertNotIn('AGE-SECRET-KEY', self.texto)


class CamadaDoComposeLocalTest(unittest.TestCase):
    def setUp(self):
        self.texto = ler('deploy/compose.local.yml')

    def test_so_a_porta_https_e_publicada_e_so_em_loopback(self):
        self.assertIn('ports: !override', self.texto)
        self.assertIn('${VLADO_PORTA_HTTPS:-127.0.0.1:9443}:443', self.texto)
        self.assertNotIn(':80"', self.texto)

    def test_pasta_de_backup_montada_no_backup_e_so_para_leitura_na_restauracao(self):
        self.assertRegex(self.texto, r'(?s)backup:\s+volumes:\s+- \$\{VLADO_LOCAL_BACKUP_PASTA:\?[^}]+\}:/destino-backup\n')
        self.assertRegex(self.texto, r'(?s)restauracao:.*:/destino-backup:ro\n')

    def test_nao_monta_segredos_nem_afrouxa_o_endurecimento(self):
        for proibido in ('segredos', 'privileged', 'read_only: false', 'cap_add', 'docker.sock', 'network_mode'):
            self.assertNotIn(proibido, self.texto)

    @unittest.skipUnless(shutil.which('docker'), 'sem docker no PATH')
    def test_combinacao_com_o_compose_base_e_valida_e_publica_so_uma_porta(self):
        with tempfile.TemporaryDirectory() as pasta:
            env = Path(pasta) / 'local.env'
            texto = ler('deploy/ambientes/local.env.example').replace('C:/Users/SEU-USUARIO/Vlado-backups-teste', pasta.replace('\\', '/'))
            env.write_text(texto, encoding='utf-8')
            r = subprocess.run(['docker', 'compose', '-p', 'vlado-localteste-unit', '--env-file', str(env),
                                '-f', 'docker-compose.yml', '-f', 'deploy/compose.local.yml', 'config'],
                               cwd=RAIZ, capture_output=True, text=True, encoding='utf-8')
        if r.returncode != 0 and 'unknown shorthand flag' in r.stderr:
            self.skipTest('docker sem o plugin compose')
        self.assertEqual(r.returncode, 0, r.stderr)
        saida = r.stdout
        self.assertEqual(len(re.findall(r'published: "\d+"', saida)), 1, saida)
        self.assertIn('published: "9443"', saida)
        self.assertIn('host_ip: 127.0.0.1', saida)
        self.assertIn('target: /destino-backup', saida)
        self.assertIn('mem_limit: "2147483648"', saida.replace('mem_limit: 2147483648', 'mem_limit: "2147483648"'))
        self.assertIn('image: vlado:local-dono', saida)


class ScriptDoPowerShellTest(unittest.TestCase):
    def setUp(self):
        self.bruto = (RAIZ / 'deploy/vlado-local.ps1').read_bytes()
        self.texto = self.bruto.decode('utf-8-sig')

    def test_tem_bom_utf8_para_o_powershell_5_ler_os_acentos(self):
        self.assertTrue(self.bruto.startswith(b'\xef\xbb\xbf'))

    def test_projeto_proprio_e_arquivo_de_ambiente_ignorado_pelo_git(self):
        self.assertIn("[string]$Projeto = 'vlado-local'", self.texto)
        self.assertIn("'deploy/ambientes/local.env'", self.texto)
        self.assertRegex(ler('.gitignore'), r'(?m)^/deploy/ambientes/\*\.env$')
        codigo = self.texto[self.texto.index('#>'):]  # o cabeçalho de ajuda diz que não toca nos vlado-homologacao-*
        self.assertNotIn('homologacao', codigo)

    def test_tem_todos_os_comandos_do_roteiro(self):
        for comando in ('subir', 'parar', 'status', 'registros', 'seguir', 'acessos', 'semear', 'backup', 'backups',
                        'verificar-backup', 'restaurar', 'ca', 'confiar-ca', 'esquecer-ca', 'apagar-tudo'):
            self.assertRegex(self.texto, rf"(?m)^    '{re.escape(comando)}' \{{", comando)

    def test_so_age_sobre_o_projeto_e_nunca_em_comandos_globais_do_docker(self):
        # Todo `docker compose` leva -p do projeto; nada de prune, rm -f ou down sem o projeto.
        for linha in self.texto.splitlines():
            if re.search(r'& docker compose', linha):
                self.assertIn('-p $Projeto', linha, linha)
        for proibido in ('prune', 'docker rm', 'docker rmi', 'docker volume', 'docker network', 'system'):
            self.assertNotIn(proibido, self.texto)

    def test_chave_privada_so_na_memoria_do_comando(self):
        self.assertIn('Read-Host', self.texto)
        self.assertIn('-AsSecureString', self.texto)
        self.assertRegex(self.texto, r'finally \{ Remove-Item Env:\\VLADO_BACKUP_CHAVE_PRIVADA')
        self.assertEqual(self.texto.count('$env:VLADO_BACKUP_CHAVE_PRIVADA ='), 2)  # verificar-backup e restaurar
        for gravar in ('Set-Content', 'Out-File', 'Add-Content', '>>', 'WriteAllText'):
            self.assertNotIn(gravar, self.texto)

    def test_restauracao_e_apagar_exigem_confirmacao_digitada(self):
        self.assertIn("Confirmar 'RESTAURAR'", self.texto)
        self.assertIn('Confirmar $Projeto', self.texto)
        self.assertIn('-cne $palavra', self.texto)

    def test_confiar_na_ca_e_so_a_pedido_e_so_no_usuario_e_a_remocao_e_pela_impressao_digital(self):
        self.assertIn('Cert:\\CurrentUser\\Root', self.texto)
        self.assertNotIn('LocalMachine', self.texto)
        self.assertIn('$cert.Thumbprint', self.texto)
        self.assertNotIn('-like', self.texto)  # nunca por nome: levaria a CA da homologação junto
        self.assertNotIn('root.key', self.texto)
        self.assertIn('root.crt', self.texto)

    def test_nao_le_pastas_de_segredos(self):
        self.assertNotRegex(self.texto, r'segredos[/\\]|acesso[/\\](?!links)')


class RoteiroLocalTest(unittest.TestCase):
    def setUp(self):
        self.texto = ler('deploy/LOCAL.md')

    def test_cobre_o_que_o_dono_pediu(self):
        for trecho in ('subir', 'parar', 'registros', '`backup`', '`restaurar`', 'verificar-backup', 'confiar-ca',
                       'esquecer-ca', 'Firefox', 'vlado.localhost:9443', '2 GB', 'vlado-local'):
            self.assertIn(trecho, self.texto, trecho)

    def test_lista_o_que_so_um_servidor_real_valida(self):
        parte = self.texto[self.texto.index('## O que só um servidor real valida'):]
        for item in ('Certificado público', 'DNS', 'Monitor externo', 'Backup fora da máquina', 'E-mail'):
            self.assertIn(item, parte, item)

    def test_avisa_dos_limites_do_ambiente(self):
        self.assertIn('mesma máquina', self.texto)
        self.assertIn('Vigia', self.texto)
        self.assertIn('dado de\nverdade', self.texto)

    def test_chave_privada_nunca_em_arquivo_do_repositorio(self):
        self.assertIn('fora da pasta do repositório', self.texto)
        self.assertNotIn('AGE-SECRET-KEY-1' + 'A', self.texto)
        self.assertNotRegex(self.texto, r'age1[a-z0-9]{50,}')


if __name__ == '__main__':
    unittest.main()
