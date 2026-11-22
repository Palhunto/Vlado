"""Registro de acesso do Caddy, monitoramento e roteiros (Fase 3): formato e máscara do registro, compose válido,
batimento de disponibilidade e documentos de operação. Só lê arquivos do repositório; o ensaio com o Caddy
de verdade (requisições com token, cookie e senha, e a conferência de que nada vaza) está no registro de verificação."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
import backup

CADDYFILES = ('deploy/Caddyfile', 'deploy/Caddyfile.interno')


def bloco_de_registro(texto: str) -> str:
    """Do `log_append` ao fim do bloco `log { ... }` (a chave de fechamento com um tab de recuo)."""
    inicio = texto.index('log_append rota')
    fim = re.compile(r'(?m)^\t\}$').search(texto, texto.index('\tlog {', inicio)).end()
    return texto[inicio:fim].strip()


class RegistroDoCaddyTest(unittest.TestCase):
    def setUp(self):
        self.textos = {nome: (RAIZ / nome).read_text(encoding='utf-8') for nome in CADDYFILES}

    def test_os_dois_caddyfiles_tem_o_mesmo_bloco_de_registro(self):
        blocos = {nome: bloco_de_registro(t) for nome, t in self.textos.items()}
        self.assertEqual(blocos['deploy/Caddyfile'], blocos['deploy/Caddyfile.interno'])

    def test_json_em_arquivo_com_rotacao_e_sem_uri_nem_cabecalhos(self):
        for nome, texto in self.textos.items():
            bloco = bloco_de_registro(texto)
            self.assertIn('output file /var/log/caddy/acesso.log', bloco, nome)
            for chave in ('roll_size 20MiB', 'roll_keep 20', 'roll_keep_for 720h'):
                self.assertIn(chave, bloco, f'{nome}: rotação sem {chave}')
            self.assertIn('wrap json', bloco)
            # A URI inteira (com query) e todos os cabeçalhos saem: Cookie, Authorization, Set-Cookie...
            for campo in ('request>uri delete', 'request>headers delete', 'resp_headers delete'):
                self.assertIn(campo, bloco, f'{nome}: falta {campo}')

    def bloco_global(self, texto: str) -> str:
        """As opções globais: o `{ ... }` do topo do arquivo, antes do bloco do site (sem os comentários)."""
        corpo = '\n'.join(l for l in texto.splitlines() if not l.lstrip().startswith('#'))
        self.assertTrue(corpo.lstrip().startswith('{'), 'o bloco global precisa ser o primeiro do arquivo')
        inicio = corpo.index('{')
        fim = re.compile(r'(?m)^\}$').search(corpo, inicio).end()
        return corpo[inicio:fim]

    def log_padrao(self, texto: str) -> str:
        """O `log { ... }` sem nome das opções globais (o log padrão), do `log {` à chave que o fecha."""
        glob = self.bloco_global(texto)
        inicio = glob.index('\tlog {')
        return glob[inicio:glob.index('\n\t}', glob.index('format filter', inicio)) + 3]

    def test_o_log_padrao_do_conteiner_tem_o_mesmo_filtro_sem_uri_nem_cabecalhos(self):
        # Com a Mesa fora do ar (502) o Caddy escreve no log padrão (stdout), não no registro do site.
        for nome, texto in self.textos.items():
            glob = self.bloco_global(texto)
            padrao = self.log_padrao(texto)
            self.assertIn('wrap json', padrao, nome)
            for campo in ('request>uri delete', 'request>headers delete', 'resp_headers delete'):
                self.assertIn(campo, padrao, f'{nome}: o log padrão não apaga {campo}')
            # É o log padrão (sem nome e sem arquivo): continua em stdout/stderr, onde o `docker logs` lê.
            self.assertNotIn('output', padrao, nome)
            self.assertNotRegex(padrao, r'log \w+ \{', nome)
            self.assertNotIn('rota', padrao, nome)
            self.assertEqual(glob.count('\tlog {'), 1, nome)
        iguais = {nome: re.sub(r'\s+', ' ', self.log_padrao(t)) for nome, t in self.textos.items()}
        self.assertEqual(iguais['deploy/Caddyfile'], iguais['deploy/Caddyfile.interno'])

    def test_o_caminho_vai_em_campo_proprio_e_mascarado(self):
        for nome, texto in self.textos.items():
            bloco = bloco_de_registro(texto)
            self.assertIn('log_append rota {http.request.uri.path}', bloco, nome)
            self.assertRegex(bloco, r'(?m)^\s+rota regexp ', f'{nome}: o campo "rota" precisa do filtro de máscara')
            # Nada de query no registro: o placeholder usado é só o do caminho.
            self.assertNotIn('uri.query', bloco)
            self.assertNotIn('{http.request.uri}', bloco)
            self.assertNotIn('{http.request.header', bloco)
            self.assertNotIn('{http.request.cookie', bloco)
            self.assertNotIn('{http.request.body', bloco)

    def mascarar(self, caminho: str) -> str:
        """A mesma expressão do Caddyfile, aplicada em Python (a sintaxe `(?P<n>...)` é igual na RE2 do Go)."""
        achado = re.search(r'rota regexp "([^"]+)" "([^"]+)"', self.textos['deploy/Caddyfile'])
        padrao, troca = achado[1], achado[2]
        troca = troca.replace('${p}', r'\g<p>').replace('${q}', r'\g<q>')
        return re.sub(padrao, troca, caminho)

    def test_mascara_dos_tokens_de_ativacao_e_convite(self):
        token = 'Zx9_-' * 9  # 45 caracteres, como secrets.token_urlsafe(32) (43)
        self.assertEqual(self.mascarar(f'/ativar/{token}'), '/ativar/***')
        self.assertEqual(self.mascarar('/ativar/curto'), '/ativar/***', 'mesmo um token curto some')
        self.assertEqual(self.mascarar('/convite/abc123'), '/convite/***')
        self.assertEqual(self.mascarar('/ativar'), '/ativar', 'a página sem token continua legível')
        self.assertEqual(self.mascarar('/entrar'), '/entrar')

    def test_segmento_longo_qualquer_e_mascarado_e_as_rotas_normais_ficam(self):
        self.assertEqual(self.mascarar('/api/documento/0123456789abcdef0123456789abcdef'), '/api/documento/***')
        self.assertEqual(self.mascarar('/recuperar/' + 'A' * 43), '/recuperar/***')
        for rota in ('/', '/saude', '/api/sessao', '/api/perguntar', '/interface/app.js', '/vendor/pdfjs/viewer.mjs',
                     '/api/catalogo'):
            self.assertEqual(self.mascarar(rota), rota, rota)

    def test_compose_guarda_o_registro_em_volume_proprio(self):
        compose = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('- caddy_logs:/var/log/caddy', compose)
        self.assertRegex(compose, r'(?m)^  caddy_logs:\s*$')
        # O volume de registro não é montado no app nem no backup: dado de acesso não viaja nos backups.
        for servico in ('vlado', 'backup', 'restauracao'):
            bloco = compose.split(f'\n  {servico}:\n', 1)[1].split('\n\n', 1)[0]
            self.assertNotIn('caddy_logs', bloco, servico)


def estado_de_vigia(**campos):
    return campos


class BatimentoDeDisponibilidadeTest(unittest.TestCase):
    """A Mesa cai => o alerta tem de disparar: `/fail` na hora e, se tudo cair, a falta de batimento."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        (self.base / 'dados' / 'casos').mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.object(backup, 'ROOT', self.base / 'dados').start()
        self.visitas = []
        patch.object(backup, '_visitar', lambda url, corpo=None: self.visitas.append((url, corpo)) or b'').start()

    def cfg(self, **env):
        ambiente = {'VLADO_AMBIENTE': 'homologacao', 'VLADO_BACKUP_TRABALHO': str(self.base / 'trabalho'),
                    'VLADO_VIGIA_PING_URL': 'https://ping.exemplo/vigia-uuid', 'VLADO_VIGIA_URL': 'http://vlado:8765/saude'}
        ambiente.update(env)
        return backup._configuracao(ambiente)

    def app(self, resposta):
        return patch.object(backup, '_ler_saude', lambda url: resposta)

    def test_mesa_saudavel_envia_o_batimento_normal(self):
        with self.app((200, b'{"ok": true}')):
            ok, texto = backup.verificar_disponibilidade(self.cfg())
        self.assertTrue(ok, texto)
        with self.app((200, b'{"ok": true}')):
            backup.batimento(self.cfg())
        self.assertEqual(self.visitas, [('https://ping.exemplo/vigia-uuid', None)])

    def test_mesa_fora_do_ar_envia_falha_com_o_motivo(self):
        def cai(url):
            raise OSError('Connection refused')
        with patch.object(backup, '_ler_saude', cai):
            backup.batimento(self.cfg())
        self.assertEqual(len(self.visitas), 1)
        url, corpo = self.visitas[0]
        self.assertEqual(url, 'https://ping.exemplo/vigia-uuid/fail')
        self.assertIn('sem resposta', corpo)

    def test_resposta_que_nao_e_ok_ou_status_diferente_de_200_e_falha(self):
        for resposta in ((503, b'{"ok": true}'), (200, b'{"ok": false}'), (200, b'<html>erro</html>'), (200, b'')):
            self.visitas.clear()
            with self.app(resposta):
                backup.batimento(self.cfg())
            self.assertTrue(self.visitas[0][0].endswith('/fail'), resposta)

    def test_disco_quase_cheio_e_falha_mesmo_com_a_mesa_no_ar(self):
        usage = type('U', (), {'free': 2 * 1024 ** 3, 'total': 100 * 1024 ** 3, 'used': 98 * 1024 ** 3})
        with self.app((200, b'{"ok": true}')), patch.object(backup.shutil, 'disk_usage', lambda p: usage):
            ok, texto = backup.verificar_disponibilidade(self.cfg(VLADO_VIGIA_DISCO_MIN_GB='5'))
            self.assertFalse(ok)
            self.assertIn('disco', texto)
            backup.batimento(self.cfg(VLADO_VIGIA_DISCO_MIN_GB='5'))
        self.assertTrue(self.visitas[0][0].endswith('/fail'))
        self.assertIn('2.0 GB', self.visitas[0][1])

    def test_texto_do_alerta_nao_leva_dado_de_conta_nem_de_caso(self):
        def cai(url):
            raise OSError('Connection refused: http://vlado:8765/saude')
        with patch.object(backup, '_ler_saude', cai):
            backup.batimento(self.cfg())
        corpo = self.visitas[0][1]
        self.assertNotRegex(corpo, r'(?i)senha|token|cookie|caso|documento')

    def test_sem_endereco_de_batimento_nada_e_enviado_e_a_vigia_nao_inicia(self):
        cfg = self.cfg(VLADO_VIGIA_PING_URL='')
        backup.batimento(cfg)
        self.assertEqual(self.visitas, [])
        self.assertIsNone(backup.iniciar_vigia(cfg, []))

    def test_vigia_inicia_em_thread_propria_para_nao_parar_durante_um_backup_longo(self):
        parar = []
        cfg = self.cfg(VLADO_VIGIA_INTERVALO_S='1')
        chamadas = []
        with patch.object(backup, 'batimento', lambda c: chamadas.append(1) or parar.append(True)):
            fio = backup.iniciar_vigia(cfg, parar)
            self.assertTrue(fio.daemon)
            fio.join(5)
        self.assertGreaterEqual(len(chamadas), 1)

    def test_saude_do_servico_falha_se_a_vigia_parou_de_bater(self):
        cfg = self.cfg(VLADO_BACKUP_DESTINO='/x', VLADO_BACKUP_DESTINATARIOS='age1' + 'q' * 58)
        agora = datetime.now(timezone.utc)
        backup._gravar_estado(cfg, iniciado_em_utc=agora.isoformat(), destino_configurado=True,
                              ultimo_sucesso_utc=agora.isoformat())
        backup._gravar_vigia(cfg, ultimo_batimento_utc=agora.isoformat(), ok=True)
        self.assertEqual(backup.saude(cfg), 0)
        antigo = (agora - timedelta(minutes=30)).isoformat()
        backup._gravar_vigia(cfg, ultimo_batimento_utc=antigo, ok=True)
        self.assertEqual(backup.saude(cfg), 1)

    def test_compose_repassa_as_variaveis_da_vigia_ao_servico_de_backup(self):
        compose = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        bloco = compose.split('\n  backup:\n', 1)[1].split('\n  restauracao:', 1)[0]
        for variavel in ('VLADO_VIGIA_PING_URL', 'VLADO_VIGIA_URL', 'VLADO_VIGIA_DISCO_MIN_GB', 'VLADO_VIGIA_INTERVALO_S'):
            self.assertIn(variavel + ':', bloco)
        self.assertIn('http://vlado:8765/saude', bloco)


class DocumentosDeOperacaoTest(unittest.TestCase):
    def texto(self, nome):
        return (RAIZ / 'deploy' / nome).read_text(encoding='utf-8')

    def test_roteiro_de_incidente_cobre_os_cenarios_pedidos(self):
        texto = self.texto('INCIDENTE.md')
        for secao in ('Mesa fora do ar', 'Disco cheio', 'Certificado vencido', 'Backup falhando',
                      'Suspeita de invasão', 'Restauração'):
            self.assertRegex(texto, rf'(?m)^## .*{secao}', secao)
        for assunto in ('trocar', 'Quem avisar', 'preserv'):
            self.assertIn(assunto, texto)

    def test_roteiro_nunca_manda_apagar_evidencia(self):
        texto = self.texto('INCIDENTE.md')
        self.assertIn('Não apague', texto)
        self.assertNotRegex(texto, r'down\s+(-\w*\s+)*-v|--volumes|rm\s+-rf|docker\s+volume\s+(rm|prune)|system\s+prune|truncate|:\s*>\s*/var/log')
        invasao = texto.split('Suspeita de invasão', 1)[1].split('\n## ', 1)[0]
        self.assertIn('Não apague', invasao)
        self.assertRegex(invasao, r'(?i)preserv')

    def test_chave_privada_nunca_vai_para_o_disco_do_servidor_nos_roteiros(self):
        """B1: os roteiros dizem onde a chave privada pode estar e onde nunca, e não mandam ler de arquivo no servidor."""
        backup_md = self.texto('BACKUP.md')
        self.assertIn('Onde a chave privada pode estar e onde nunca', backup_md)
        self.assertIn('OUTRA máquina', backup_md)
        self.assertIn('read -rs', backup_md)
        self.assertIn('credencial só de leitura', backup_md)
        for nome in ('BACKUP.md', 'INCIDENTE.md', 'MONITORAMENTO.md'):
            texto = self.texto(nome)
            # nenhum comando manda ler a chave de um arquivo comum da máquina; só o pen drive montado é citado
            for linha in texto.splitlines():
                if '$(cat' in linha:
                    self.assertIn('/mnt/pendrive', linha, f'{nome}: {linha.strip()}')
        incidente = self.texto('INCIDENTE.md')
        self.assertIn('nunca gravada em arquivo no servidor', incidente)
        self.assertIn('read -rs', incidente)

    def test_roteiros_dizem_que_a_restauracao_recusa_rodar_com_a_mesa_no_ar(self):
        self.assertIn('recusa rodar com a Mesa no ar', self.texto('BACKUP.md'))
        self.assertIn('--mesmo-com-a-mesa-no-ar', self.texto('BACKUP.md'))
        self.assertIn('se recusa', self.texto('INCIDENTE.md'))

    def test_backup_declara_as_limitacoes_da_revisao_e_o_que_mudou_na_fase_4(self):
        texto = (RAIZ / 'deploy' / 'BACKUP.md').read_text(encoding='utf-8')
        secao = texto[texto.index('## Limitações conhecidas'):texto.index('## Pendências que dependem de pessoa')]
        for codigo in ('J3', 'J5', 'J6', 'J8', 'J2'):
            self.assertRegex(secao, rf'\| {codigo} \|', codigo)
        for trecho in ('unhealthy', 'tmp_vlado', 'VLADO_VIGIA_DISCO_MIN_GB', 'bloqueio de objeto',
                       'VLADO_BACKUP_STDIN_MAX_GB', '10 GB', 'age=1.1.1-1*', 'rclone=1.60.1+dfsg-2*', 'falha de propósito'):
            self.assertIn(trecho, secao, trecho)

    def test_backup_registra_que_a_fila_de_extracao_entra_e_o_que_fica_de_fora(self):
        texto = (RAIZ / 'deploy' / 'BACKUP.md').read_text(encoding='utf-8')
        secao = texto[texto.index('### Fila de extração'):texto.index('Quem quiser incluir as chaves de API')]
        for trecho in ('entra no backup', 'casos/.fila/.coordenador', '.novo_', 'antes', 'idempotente', 'ordem'.capitalize()):
            self.assertIn(trecho, secao, trecho)
        self.assertIn('`.novo_*`', texto.split('## O que entra', 1)[0], 'marcador na lista de pastas de preparo')

    def test_roteiro_nao_traz_chave_nem_senha_de_exemplo_reais(self):
        for nome in ('INCIDENTE.md', 'MONITORAMENTO.md', 'BACKUP.md'):
            texto = self.texto(nome)
            self.assertNotRegex(texto, r'AGE-SECRET-KEY-1[0-9A-Z]{20,}')
            self.assertNotRegex(texto, r'sk-ant-[A-Za-z0-9_-]{10,}')

    def test_monitoramento_explica_os_dois_alertas_e_o_que_o_dono_faz(self):
        texto = self.texto('MONITORAMENTO.md')
        for assunto in ('/saude', 'VLADO_BACKUP_PING_URL', 'VLADO_VIGIA_PING_URL', 'healthchecks.io', 'UptimeRobot',
                        'Dono', 'teste do alerta'):
            self.assertIn(assunto, texto, assunto)

    def test_exemplos_de_ambiente_documentam_a_vigia(self):
        for ambiente in ('homologacao', 'demonstracao', 'editorial'):
            texto = (RAIZ / 'deploy' / 'ambientes' / f'{ambiente}.env.example').read_text(encoding='utf-8')
            self.assertIn('VLADO_VIGIA_PING_URL', texto, ambiente)


if __name__ == '__main__':
    unittest.main()
