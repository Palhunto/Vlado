"""SEG-02 de ponta a ponta: cada evento de autenticação, administração e download gera uma linha no registro de auditoria,
com horário UTC, conta, IP, operação e resultado, e NADA sensível entra (senha, token, cookie, link, nome de caso, de
documento, pergunta). Reaproveita o servidor HTTP em modo piloto de test_autorizacao (casos sintéticos alpha e beta)."""
import http.client
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import interface_pesquisa
import registro_acesso as reg
from test_acesso import SENHA
from test_autorizacao import Http, ORIGEM

HEX = re.compile(r'^[0-9a-f]{12}$')


def mudar_sessoes(root, conta, campo, valor):
    """Rewrite one field of every session of an account, in the accounts store (acesso/contas.sqlite)."""
    assert campo in ('expira_em', 'ultimo_uso')
    con = sqlite3.connect(acesso.caminho_bd(root))
    try:
        with con:
            mudadas = con.execute(f'UPDATE sessoes SET {campo} = ? WHERE conta = ?', (valor, conta)).rowcount
    finally:
        con.close()
    assert mudadas >= 1, 'a conta não tinha sessão aberta'


class Auditoria(Http):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pasta_registro = Path(temp.name) / 'registro'
        env = patch.dict(os.environ, {'VLADO_REGISTRO': str(self.pasta_registro), 'VLADO_REGISTRO_RETENCAO_DIAS': '',
                                      'VLADO_REGISTRO_DIA_MAX_MB': '', 'VLADO_PROXIES_CONFIAVEIS': '',
                                      'VLADO_REGISTRO_CHAVE': str(Path(temp.name) / 'segredos' / 'registro_ref.chave')})
        env.start()
        self.addCleanup(env.stop)
        reg._ESTADO.update(limpeza=0.0, aviso=0.0)
        reg._ESTADO['cheio'].clear()
        reg._ESTADO['chave'].clear()
        reg._AGREGADOS.clear()
        self.addCleanup(reg._AGREGADOS.clear)
        super().setUp()
        self.inicio = len(self.todas())

    def todas(self) -> list[dict]:
        saida = []
        for arquivo in reg.arquivos(self.pasta_registro):
            saida += [json.loads(l) for l in arquivo.read_text(encoding='ascii').splitlines()]
        return saida

    def novas(self, evento=None, **filtros) -> list[dict]:
        linhas = self.todas()[self.inicio:]
        return [l for l in linhas if (evento is None or l['evento'] == evento)
                and all(l.get(k) == v for k, v in filtros.items())]

    def texto(self) -> str:
        return ''.join(a.read_text(encoding='ascii') for a in reg.arquivos(self.pasta_registro))

    def esperar(self, evento, quantidade=1, prazo=5.0) -> list[dict]:
        """O download é registrado depois do envio do arquivo, no fio do servidor: espera a linha aparecer."""
        import time
        limite = time.monotonic() + prazo
        while time.monotonic() < limite:
            linhas = self.novas(evento)
            if len(linhas) >= quantidade:
                return linhas
            time.sleep(0.05)
        return self.novas(evento)

    def marcar(self):
        self.inicio = len(self.todas())


class AutenticacaoTest(Auditoria):
    def test_login_ok_leva_conta_ip_cliente_e_operacao(self):
        self.entrar('ana')
        linha, = self.novas('login_ok')
        self.assertEqual((linha['resultado'], linha['conta'], linha['ip'], linha['cliente'], linha['operacao'], linha['origem']),
                         ('ok', self.ana_id, '127.0.0.1', 'web', 'entrar', 'web'))
        self.assertRegex(linha['em'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        agora = datetime.now(timezone.utc)
        self.assertLess(abs((datetime.strptime(linha['em'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc) - agora).total_seconds()), 60)

    def test_cliente_android_e_registrado_como_tal(self):
        status, _, _ = self.publico('entrar', {'login': 'ana', 'senha': SENHA, 'cliente': 'android'})
        self.assertEqual(status, 200)
        self.assertEqual(self.novas('login_ok')[-1]['cliente'], 'android')

    def test_senha_errada_de_conta_existente_leva_o_id_da_conta(self):
        self.publico('entrar', {'login': 'ana', 'senha': 'errada-mas-longa'})
        linha, = self.novas('login_falha')
        self.assertEqual((linha['resultado'], linha['motivo'], linha['conta'], linha['ip']), ('falha', 'credenciais', self.ana_id, '127.0.0.1'))
        self.assertNotIn('login_ref', linha)

    def test_login_inexistente_leva_so_a_referencia_nunca_o_texto_digitado(self):
        # Quem digita a senha no campo de login não pode vê-la no registro.
        for digitado in ('fulano.inexistente', 'senha-longa-de-teste-1-no-campo-errado'):
            self.publico('entrar', {'login': digitado, 'senha': 'qualquer-coisa-longa'})
        linhas = self.novas('login_falha')
        self.assertEqual(len(linhas), 2)
        for linha in linhas:
            self.assertIsNone(linha['conta'])
            self.assertRegex(linha['login_ref'], HEX)
        self.assertEqual(len({l['login_ref'] for l in linhas}), 2)
        for texto in ('fulano', 'inexistente', 'campo-errado', 'qualquer-coisa'):
            self.assertNotIn(texto, self.texto())
        # O mesmo login digitado de novo gera a mesma referência (dá para ver uma varredura de senhas).
        self.publico('entrar', {'login': 'Fulano.Inexistente ', 'senha': 'outra-senha-longa'})
        self.assertEqual(self.novas('login_falha')[-1]['login_ref'], linhas[0]['login_ref'])

    def test_bloqueio_depois_de_cinco_falhas_e_tentativa_durante_o_bloqueio(self):
        for _ in range(5):
            self.publico('entrar', {'login': 'bia', 'senha': 'errada-mas-longa'})
        self.assertEqual(len(self.novas('login_bloqueado')), 1, 'evento da conta bloqueada')
        self.assertEqual(self.novas('login_bloqueado')[0]['conta'], self.bia_id)
        motivos = [l['motivo'] for l in self.novas('login_falha')]
        self.assertEqual(motivos, ['credenciais'] * 4 + ['bloqueado'])
        self.publico('entrar', {'login': 'bia', 'senha': SENHA})  # certa, mas bloqueada
        ultima = self.novas('login_falha')[-1]
        self.assertEqual((ultima['motivo'], ultima['conta']), ('bloqueado', self.bia_id))

    def test_limite_de_tentativas_por_ip_vira_uma_linha_agregada_por_ip_e_minuto(self):
        acesso.limpar_limites()
        for numero in range(45):
            self.publico('entrar', {'login': f'ninguem{numero}', 'senha': SENHA})
        reg.descarregar(tudo=True)
        self.assertEqual(len(self.novas('login_falha', motivo='credenciais')), 20, 'as 20 primeiras, uma linha cada')
        limite = self.novas('login_falha', motivo='limite_ip')
        self.assertEqual(len(limite), 1, 'as 25 acima do limite: uma só linha, com a contagem')
        self.assertEqual((limite[0]['ip'], limite[0]['resultado'], limite[0]['quantidade'], limite[0]['operacao']),
                         ('127.0.0.1', 'falha', 25, 'entrar'))

    def test_sair_registra_logout(self):
        self.post(self.ana, 'sessao-sair', {})
        linha, = self.novas('logout')
        self.assertEqual((linha['conta'], linha['ip'], linha['operacao']), (self.ana_id, '127.0.0.1', 'sessao-sair'))

    def test_sessao_expirada_e_registrada_uma_vez(self):
        mudar_sessoes(self.root, self.bia_id, 'expira_em', acesso._iso(datetime.now(timezone.utc) - timedelta(hours=1)))
        self.assertEqual(self.get(self.bia, '/api/sessao')[0], 401)
        self.assertEqual(self.get(self.bia, '/api/sessao')[0], 401)
        linhas = self.novas('sessao_expirada')
        self.assertEqual(len(linhas), 1, 'uma linha, não uma por requisição')
        self.assertEqual((linhas[0]['conta'], linhas[0]['motivo']), (self.bia_id, 'expirada'))

    def test_sessao_por_inatividade_tem_o_motivo(self):
        mudar_sessoes(self.root, self.bia_id, 'ultimo_uso', acesso._iso(datetime.now(timezone.utc) - timedelta(hours=3)))
        self.get(self.bia, '/api/sessao')
        self.assertEqual(self.novas('sessao_expirada')[0]['motivo'], 'inatividade')

    def test_ativacao_define_senha_e_falhas_de_ativacao(self):
        conta, token = acesso.criar_conta(self.root, 'Carla', 'carla', casos=['alpha'])
        self.marcar()
        self.publico('ativacao-consultar', {'token': 'T' * 43})
        self.publico('ativar', {'token': 'T' * 43, 'senha': SENHA})
        self.publico('ativar', {'token': token, 'senha': 'curta'})
        status, _, _ = self.publico('ativar', {'token': token, 'senha': SENHA})
        self.assertEqual(status, 200)
        falhas = self.novas('ativacao_falha')
        self.assertEqual([(l['acesso_operacao'], l['motivo']) for l in falhas],
                         [('consultar', 'link_invalido'), ('ativar', 'link_invalido'), ('ativar', 'validacao')])
        definida, = self.novas('senha_definida')
        self.assertEqual((definida['conta'], definida['ip']), (conta['id'], '127.0.0.1'))
        self.assertNotIn(token, self.texto())

    def test_primeiro_administrador_e_registrado(self):
        raiz = Path(self.pasta_registro.parent) / 'outra-raiz'
        acesso.criar_primeiro_admin(raiz, 'Chefe', 'chefe', SENHA)
        linha = self.novas('primeiro_admin')[0]
        self.assertEqual((linha['por'], linha['origem']), ('primeiro_acesso', 'cli'))


class DiaCheioTest(Auditoria):
    """B1 de ponta a ponta: com o dia cheio de falhas anônimas, o administrador entra e cria outro administrador, e as duas
    coisas ficam no registro."""

    def test_administrador_entra_e_cria_administrador_com_o_dia_cheio(self):
        with patch.dict(os.environ, {'VLADO_REGISTRO_DIA_MAX_MB': '1'}):
            reg.iniciar_requisicao(lambda: '203.0.113.9')
            for i in range(10000):
                reg.registrar('login_falha', 'falha', None, motivo='credenciais', login_ref=f'{i:012x}')
            reg.encerrar_requisicao()
            self.assertTrue([l for l in self.todas() if l['evento'] == 'registro_cheio'], 'o dia está cheio de falhas')
            self.marcar()
            cookie, csrf = self.entrar('editora')
            status, criada = self.post((cookie, csrf), 'contas-criar', {'nome': 'Outra Editora', 'login': 'outra.editora',
                                                                        'papel': 'admin', 'senha': SENHA})
            self.assertEqual(status, 200, criada)
            self.publico('entrar', {'login': 'ninguem', 'senha': SENHA})  # falha anônima: descartada, sem derrubar nada
        eventos = [(l['evento'], l['resultado']) for l in self.novas()]
        self.assertEqual(eventos, [('login_ok', 'ok'), ('conta_criada', 'ok')])
        criacao = self.novas('conta_criada')[0]
        self.assertEqual((criacao['por'], criacao['conta'], criacao['operacao']),
                         (self.admin_id, criada['conta']['id'], 'contas-criar'))

    def test_inundar_com_pedidos_anonimos_nao_chega_perto_do_teto(self):
        """Os 300 mil pedidos da prova da revisão: do mesmo IP, agora, são poucas linhas."""
        acesso.limpar_limites()
        antes = len(self.todas())
        for numero in range(400):
            self.publico('entrar', {'login': f'ninguem{numero}', 'senha': SENHA})
        reg.descarregar(tudo=True)
        novas = self.todas()[antes:]
        self.assertLessEqual(len(novas), 21, '400 pedidos do mesmo IP: 20 falhas e uma linha agregada')
        self.assertEqual(sum(l.get('quantidade', 1) for l in novas), 400)


class AdministracaoTest(Auditoria):
    def admin_posta(self, operation, data):
        return self.post(self.admin, operation, data)

    def test_criar_alterar_desativar_reativar_e_recuperar(self):
        status, criada = self.admin_posta('contas-criar', {'nome': 'Carla Souza', 'login': 'carla', 'papel': 'convidado',
                                                           'casos': ['alpha'], 'cota_diaria': 3})
        self.assertEqual(status, 200, criada)
        cid, link = criada['conta']['id'], criada['link']
        # Promoting to dono, changing the role of a dono and recovering ask the password (contrato de contas, 5.15),
        # and the legacy guest profile is not given again (2.3): the account goes on as leitor.
        self.assertEqual(self.admin_posta('contas-atualizar', {'id': cid, 'papel': 'admin', 'senha': SENHA})[0], 200)
        self.assertEqual(self.admin_posta('contas-atualizar', {'id': cid, 'papel': 'leitor', 'casos': ['beta'], 'senha': SENHA})[0], 200)
        self.assertEqual(self.admin_posta('contas-desativar', {'id': cid})[0], 200)
        self.assertEqual(self.admin_posta('contas-reativar', {'id': cid})[0], 200)
        status, recuperada = self.admin_posta('contas-recuperar', {'id': cid, 'senha': SENHA})
        self.assertEqual(status, 200)
        eventos = [(l['evento'], l['conta'], l['por']) for l in self.novas() if l['evento'] != 'sessao_expirada']
        self.assertEqual(eventos, [('conta_criada', cid, self.admin_id), ('acesso_alterado', cid, self.admin_id),
                                   ('acesso_alterado', cid, self.admin_id), ('conta_desativada', cid, self.admin_id),
                                   ('conta_reativada', cid, self.admin_id), ('recuperacao_emitida', cid, self.admin_id)])
        for linha in self.novas():
            self.assertEqual((linha['ip'], linha['resultado']), ('127.0.0.1', 'ok'))
        papel1, papel2 = self.novas('acesso_alterado')
        # The administrator of before is the dono (contrato de contas, 2.4 and 6); `admin` is still accepted on input.
        self.assertEqual((papel1['papel'], papel1['campos']), ('dono', ['casos', 'cota', 'papel']))
        self.assertEqual((papel2['papel'], papel2['campos']), ('leitor', ['casos', 'papel']))
        self.assertEqual([l['operacao'] for l in self.novas()],
                         ['contas-criar', 'contas-atualizar', 'contas-atualizar', 'contas-desativar', 'contas-reativar', 'contas-recuperar'])
        for segredo in (link, recuperada['link'], link.rsplit('/', 1)[1], recuperada['link'].rsplit('/', 1)[1], 'Carla', 'carla'):
            self.assertNotIn(segredo, self.texto())

    def test_operacao_de_administracao_recusada_e_registrada(self):
        status, _ = self.admin_posta('contas-criar', {'nome': 'Outra Ana', 'login': 'ana', 'papel': 'convidado',
                                                      'casos': ['alpha'], 'cota_diaria': 3})  # login já existe
        self.assertEqual(status, 400)
        linha, = self.novas('admin_recusada')
        self.assertEqual((linha['resultado'], linha['conta'], linha['motivo'], linha['operacao']),
                         ('falha', self.admin_id, 'validacao', 'contas-criar'))
        status, _ = self.admin_posta('contas-desativar', {'id': self.admin_id, 'senha': SENHA})  # último administrador
        self.assertEqual(status, 400)
        ultima = self.novas('admin_recusada')[-1]
        self.assertEqual((ultima['operacao'], ultima['alvo']), ('contas-desativar', self.admin_id))

    def test_convidado_tentando_administrar_e_negado_e_registrado(self):
        for operacao in ('contas-listar', 'contas-criar', 'contas-recuperar'):
            self.assertEqual(self.post(self.ana, operacao, {'id': self.bia_id})[0], 403)
        negadas = self.novas('acesso_negado')  # the gate's refusal, with its reason (contrato de contas, 4.3)
        self.assertEqual([(l['conta'], l['operacao'], l['resultado'], l['codigo'], l['motivo']) for l in negadas],
                         [(self.ana_id, o, 'negado', 'operacao_proibida', 'papel')
                          for o in ('contas-listar', 'contas-criar', 'contas-recuperar')])
        self.assertEqual(self.novas('conta_criada'), [], 'nada foi criado')

    def test_apuracao_nao_liberada_ao_convidado_e_negada(self):
        status, _ = self.post(self.ana, 'codex-perguntar', {'caso': 'beta', 'pergunta': 'Pergunta sintética.'})
        # Out of reach answers as nonexistent (404 caso_indisponivel); the real reason goes to the audit log only
        # (contrato de contas, 4.3).
        self.assertEqual(status, 404)
        linha, = self.novas('acesso_negado')
        self.assertEqual((linha['codigo'], linha['motivo'], linha['operacao']),
                         ('caso_indisponivel', 'sem_participacao', 'codex-perguntar'))
        self.assertNotIn('beta', json.dumps(linha))


class DownloadsTest(Auditoria):
    def test_exportacao_em_arquivo_e_registrada_com_tamanho_e_sem_nome_nem_caso(self):
        status, cabecalhos, corpo = self.request('POST', '/api/apuracao-exportar', json.dumps({'caso': 'alpha', 'formato': 'md'}), {
            'Content-Type': 'application/json', 'Cookie': self.admin[0], 'X-Session-Token': self.admin[1], 'Origin': ORIGEM})
        self.assertEqual(status, 200, corpo[:200])
        self.assertIn('attachment', cabecalhos['Content-Disposition'])
        linha, = self.esperar('download')
        self.assertEqual((linha['resultado'], linha['conta'], linha['tipo'], linha['operacao'], linha['bytes'], linha['ip']),
                         ('ok', self.admin_id, 'exportacao', 'apuracao-exportar', len(corpo), '127.0.0.1'))
        self.assertRegex(linha['caso_ref'], HEX)
        self.assertNotIn('alpha', self.texto())
        self.assertNotIn('caderno', json.dumps(linha))

    def test_a_referencia_do_caso_e_a_mesma_entre_downloads_e_diferente_entre_casos(self):
        for caso in ('alpha', 'alpha', 'beta'):
            self.request('POST', '/api/apuracao-exportar', json.dumps({'caso': caso, 'formato': 'md'}), {
                'Content-Type': 'application/json', 'Cookie': self.admin[0], 'X-Session-Token': self.admin[1], 'Origin': ORIGEM})
        a1, a2, b = (l['caso_ref'] for l in self.esperar('download', 3))
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b)

    def test_download_que_falha_e_registrado_como_falha(self):
        status, _ = self.post(self.admin, 'apuracao-exportar', {'caso': 'alpha', 'formato': 'zip'})
        self.assertEqual(status, 400)
        linha, = self.novas('download')
        self.assertEqual((linha['resultado'], linha['tipo'], linha['operacao']), ('falha', 'exportacao', 'apuracao-exportar'))
        self.assertNotIn('bytes', linha)

    def test_convidado_baixando_original_de_outro_caso_e_recusado_sem_download(self):
        status, _ = self.post(self.ana, 'original', {'caso': 'beta', 'rodada': 'R1', 'passagem': 'x'})
        self.assertEqual(status, 403)
        self.assertEqual(self.novas('download'), [])
        self.assertEqual(self.novas('acesso_negado')[0]['operacao'], 'original')

    def test_original_da_conversa_do_convidado_entra_como_download_de_original(self):
        conversa = self.perguntar(self.ana)
        self.marcar()
        status, cabecalhos, _ = self.request('POST', '/api/codex-original', json.dumps({'conversa': conversa, 'referencia': 'nao-existe'}), {
            'Content-Type': 'application/json', 'Cookie': self.ana[0], 'X-Session-Token': self.ana[1], 'Origin': ORIGEM})
        linhas = self.esperar('download')
        self.assertEqual(len(linhas), 1, 'uma linha por pedido, com sucesso ou falha')
        self.assertEqual((linhas[0]['tipo'], linhas[0]['operacao'], linhas[0]['conta']), ('original', 'codex-original', self.ana_id))
        self.assertEqual(linhas[0]['resultado'], 'ok' if status == 200 else 'falha')


class NadaSensivelNoRegistroTest(Auditoria):
    def test_apos_um_dia_inteiro_de_uso_nenhum_segredo_ou_conteudo_no_registro(self):
        # Entrar, perguntar, baixar, administrar, errar, sair: tudo junto.
        conversa = self.perguntar(self.ana)
        self.post(self.admin, 'apuracao-exportar', {'caso': 'alpha', 'formato': 'md'})
        status, criada = self.post(self.admin, 'contas-criar', {'nome': 'Dora Lima', 'login': 'dora', 'papel': 'convidado',
                                                                'casos': ['alpha'], 'cota_diaria': 3})
        self.publico('entrar', {'login': 'dora', 'senha': SENHA})
        self.publico('entrar', {'login': 'ana', 'senha': 'errada-mas-longa'})
        self.post(self.ana, 'contas-listar', {})
        self.post(self.ana, 'sessao-sair', {})
        texto = self.texto()
        sessoes = [self.admin, self.ana, self.bia]
        proibidos = [SENHA, 'errada-mas-longa', criada['link'], criada['link'].rsplit('/', 1)[1], conversa, 'Pergunta sintética',
                     'alpha', 'beta', 'Dora', 'dora', 'Ana', 'Editora', 'editora', 'Bia', 'Carla',
                     *(s[0].split('=', 1)[1] for s in sessoes), *(s[1] for s in sessoes), 'vlado_sessao', 'X-Session-Token',
                     'Authorization', 'Set-Cookie', 'password', 'cookie', 'csrf']
        for proibido in proibidos:
            self.assertNotIn(proibido, texto, proibido)
        # Nem os documentos sintéticos dos casos (nomes e trechos), que o registro nunca vê.
        for arquivo in (self.root / 'casos').glob('*/originais/*'):
            self.assertNotIn(arquivo.name, texto)
        for linha in self.todas():
            self.assertLessEqual(set(linha), {'em', 'evento', 'resultado', 'conta', 'ip', 'origem', 'operacao', 'caso_ref',
                                               'motivo', 'tipo', 'bytes', 'papel', 'campos', 'por', 'alvo', 'cliente', 'codigo',
                                               'login_ref', 'acesso_operacao', 'tipo_original', 'em_original', 'quantidade',
                                               'organizacao'})  # the newsroom's id, never its name (contrato de contas, 10)
            if 'organizacao' in linha:
                self.assertRegex(linha['organizacao'], r'^(org[0-9a-f]{16}|instalacao)$')

    def test_log_message_continua_sem_registrar_consultas_ou_tokens(self):
        saida = StringIO()
        with redirect_stderr(saida):
            self.request('GET', '/api/catalogo?consulta=segredo-do-caso&token=abcdef', headers={'Cookie': self.ana[0]})
            self.request('GET', '/ativar/' + 'T' * 43)
        self.assertEqual(saida.getvalue(), '', 'nada vai para o terminal')
        self.assertNotIn('segredo-do-caso', self.texto())
        self.assertIsNone(interface_pesquisa.Handler.log_message(None, '%s', 'GET /x?q=segredo'))

    def test_get_nao_gera_evento_de_download_nem_de_login(self):
        self.request('GET', '/api/catalogo', headers={'Cookie': self.ana[0]})
        self.request('GET', '/saude')
        self.assertEqual(self.novas(), [], 'leituras comuns não entram no registro')


class IpDoClienteNoRegistroTest(Auditoria):
    def entrar_com(self, xff, login='ana'):
        return self.publico('entrar', {'login': login, 'senha': SENHA}, extra={'X-Forwarded-For': xff})

    def test_com_a_lista_o_ip_registrado_e_o_primeiro_nao_confiavel(self):
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '127.0.0.1, 203.0.113.0/24'}):
            self.entrar_com('9.9.9.9, 198.51.100.7, 203.0.113.50')
        self.assertEqual(self.novas('login_ok')[-1]['ip'], '198.51.100.7', 'o valor forjado à esquerda não vence')

    def test_par_tcp_fora_da_lista_registra_o_par_e_ignora_o_cabecalho(self):
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '10.0.0.0/8'}):
            self.entrar_com('198.51.100.7')
        self.assertEqual(self.novas('login_ok')[-1]['ip'], '127.0.0.1')

    def test_sem_a_lista_vale_o_comportamento_anterior(self):
        self.entrar_com('198.51.100.7')
        self.assertEqual(self.novas('login_ok')[-1]['ip'], '127.0.0.1')
        with patch.dict(os.environ, {'VLADO_CONFIAR_PROXY': '1'}):
            self.entrar_com('1.1.1.1, 198.51.100.8')
        self.assertEqual(self.novas('login_ok')[-1]['ip'], '198.51.100.8')


if __name__ == '__main__':
    unittest.main()
