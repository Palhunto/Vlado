"""Hosted mode over HTTP: sign-in, activation, sessions and what the dono and the legacy guest profile reach.

One newsroom (the installation's first account creates it and it takes the cases alpha and beta, already there).
The whole matrix of roles is in test_matriz_contas.py and the crossing between newsrooms in
test_isolamento_redacoes.py. Reuses the synthetic cases and the fake provider of the integration fixture. No paid API.
"""
import http.client
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import test_codex_integracao as integracao  # module import: its TestCase is not re-collected here
from test_acesso import SENHA, hasher_rapido
from interface_pesquisa import Servidor

ORIGEM = 'https://vlado.test'

def bytes_do_armazenamento(root):
    """Every byte of the accounts store on disk (the file and its write-ahead log), to look for secrets."""
    return b''.join(p.read_bytes() for p in sorted((Path(root) / 'acesso').glob('contas.sqlite*'))).decode('latin-1')


# Everything a guest must never reach, even with a released case in the body.
SO_ADMIN = (
    'cadastrar', 'inventario', 'preparar-pdfs', 'ambiente', 'gerenciar-listar', 'excluir', 'restaurar',
    'lixeira-alcance', 'lixeira-apagar', 'ia-config', 'ia-config-salvar', 'analises', 'buscar', 'ler', 'cobertura',
    'original', 'achados-catalogo', 'achados-buscar', 'achados-detalhe', 'achados-evidencia', 'achados-original',
    'achados-exportar', 'achados-briefing', 'achados-revisao-salvar', 'apuracao-listar', 'apuracao-notas',
    'apuracao-nota', 'apuracao-nota-salvar', 'apuracao-exportar', 'apuracao-original', 'caderno-documentos',
    'caderno-listar', 'caderno-detalhe', 'caderno-salvar', 'caderno-cruzar', 'caderno-exportar', 'caderno-original',
    'diligencias-listar', 'diligencias-criar', 'diligencias-atualizar', 'diligencias-responder',
    'diligencias-original', 'codex-observacoes', 'codex-corpus-previa', 'codex-documentos-cadastrar',
    'codex-caderno-previa', 'codex-diligencias-previa', 'codex-desligar',
    # The team of the newsroom (scripts/rotas_equipe.py): dono only.
    'equipe-listar', 'equipe-papel', 'equipe-desativar', 'equipe-remover', 'equipe-convidar', 'equipe-recuperar',
    'equipe-atividade', 'caso-incluir', 'caso-retirar', 'caso-responsavel',
    # Evidence boards (scripts/rotas_evidencia.py): admin only.
    'hipoteses-listar', 'hipoteses-detalhe', 'hipoteses-quadro', 'hipoteses-criar', 'hipoteses-atualizar',
    'linha-tempo-listar', 'linha-tempo-detalhe', 'linha-tempo-criar', 'linha-tempo-atualizar',
    'comparar-evidencias', 'comparar-documentos', 'mapa-ver', 'mapa-homonimos', 'mapa-entidade-criar',
    'mapa-entidade-atualizar', 'mapa-relacao-criar', 'mapa-relacao-atualizar',
    # Investigation tables (scripts/rotas_tabelas.py): admin only.
    'tabelas-listar', 'tabelas-detalhe', 'tabelas-historico-celula', 'tabelas-calcular', 'tabelas-criar',
    'tabelas-atualizar', 'tabelas-corrigir', 'tabelas-exportar',
    # Claim-by-claim review of the story text (scripts/rotas_redacao.py): admin only.
    'redacao-listar', 'redacao-conferir', 'redacao-dividir', 'redacao-criar', 'redacao-nova-versao',
    'redacao-vincular', 'redacao-revisar',
    # Interviews and information requests (scripts/rotas_redacao.py): admin only.
    'entrevistas-lacunas', 'entrevistas-listar', 'entrevistas-detalhe', 'entrevistas-exportar',
    'entrevistas-preparar', 'entrevistas-editar', 'entrevistas-responder',
    # Web sources per case (scripts/fontes_web.py): admin only; the capture is the only network route.
    'fontes-web-listar', 'fontes-web-abrir', 'fontes-web-capturar',
    # Case resume summary (scripts/continuidade.py): admin only; guests keep only the question draft.
    'continuidade-resumo')


class Http(unittest.TestCase):
    def setUp(self):
        integracao.CodexIntegrationTest.setUp(self)
        env = patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': ''})
        env.start()
        self.addCleanup(env.stop)
        hasher_rapido(self)
        acesso.limpar_limites()
        self.server = Servidor(('127.0.0.1', 0), self.root, modo='piloto', origem=ORIGEM)
        self.server.conversas.close()
        self.server.conversas = self.manager
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))
        self.admin_id = self.conta('Editora', 'editora', papel='admin')
        self.ana_id = self.conta('Ana', 'ana', casos=['alpha'], cota=5)
        self.bia_id = self.conta('Bia', 'bia', casos=['beta'], cota=5)
        self.admin, self.ana, self.bia = self.entrar('editora'), self.entrar('ana'), self.entrar('bia')

    def conta(self, nome, login, papel='convidado', casos=(), cota=20):
        conta, token = acesso.criar_conta(self.root, nome, login, papel=papel, casos=list(casos), cota_diaria=cota)
        acesso.ativar(self.root, token, SENHA)
        return conta['id']

    def request(self, method, path, body=None, headers=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request(method, path, body, {'Host': 'vlado.test', **(headers or {})})
        response = con.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        con.close()
        return result

    def publico(self, operation, data, origin=ORIGEM, tipo='application/json', extra=None):
        headers = {'Content-Type': tipo, **({'Origin': origin} if origin else {}), **(extra or {})}
        status, headers, body = self.request('POST', '/api/' + operation, json.dumps(data), headers)
        return status, headers, json.loads(body or b'{}')

    def entrar(self, login, senha=SENHA):
        status, headers, body = self.publico('entrar', {'login': login, 'senha': senha})
        self.assertEqual(status, 200, body)
        return headers['Set-Cookie'].split(';')[0], body['csrf']

    def post(self, sessao, operation, data, origin=ORIGEM):
        cookie, csrf = sessao
        headers = {'Content-Type': 'application/json', 'Cookie': cookie, 'X-Session-Token': csrf}
        if origin:
            headers['Origin'] = origin
        status, _, body = self.request('POST', '/api/' + operation, json.dumps(data), headers)
        try:
            return status, json.loads(body or b'{}')
        except ValueError:
            return status, {'bruto': body[:50]}

    def get(self, sessao, path):
        status, headers, body = self.request('GET', path, headers={'Cookie': sessao[0]} if sessao else {})
        return status, headers, body

    def perguntar(self, sessao, caso='alpha'):
        status, result = self.post(sessao, 'codex-perguntar', {'caso': caso, 'pergunta': 'Pergunta sintética.'})
        self.assertEqual(status, 200, result)
        self.assertTrue(self.manager.rpc.ready.wait(30))
        self.addCleanup(lambda: self.manager.cancelar(result['conversa']))
        return result['conversa']


class EntrarTest(Http):
    def test_pagina_sem_sessao_vai_para_entrar_e_paginas_publicas_sem_dados(self):
        status, headers, _ = self.request('GET', '/')
        self.assertEqual((status, headers['Location']), (303, '/entrar'))
        for caminho in ('/entrar', '/ativar/' + 'x' * 43):
            status, headers, corpo = self.request('GET', caminho)
            self.assertEqual(status, 200, caminho)
            self.assertIn(b'/entrar.js', corpo)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
            self.assertNotIn(b'alpha', corpo)
        self.assertEqual(self.request('GET', '/entrar.js')[0], 200)
        self.assertEqual(self.request('GET', '/api/sessao')[0], 401)
        self.assertEqual(self.request('GET', '/api/catalogo')[0], 401)
        status, _, body = self.request('GET', '/saude', headers={'Host': '127.0.0.1:8765'})
        self.assertEqual((status, json.loads(body)), (200, {'ok': True}))

    def test_link_antigo_de_convite_explica_que_agora_o_acesso_e_por_conta(self):
        status, headers, corpo = self.request('GET', '/convite/' + 'x' * 43)
        self.assertEqual(status, 410)
        self.assertNotIn('Set-Cookie', headers)
        self.assertIn('conta'.encode(), corpo)
        self.assertIn(b'/entrar', corpo)

    def test_entrar_abre_sessao_com_cookie_seguro_sem_max_age(self):
        status, headers, body = self.publico('entrar', {'login': 'Ana', 'senha': SENHA})
        self.assertEqual(status, 200, body)
        cookie = headers['Set-Cookie']
        for atributo in ('HttpOnly', 'Secure', 'SameSite=Strict', 'Path=/'):
            self.assertIn(atributo, cookie)
        self.assertNotIn('Max-Age', cookie)
        self.assertEqual((body['conta']['id'], body['conta']['papel']), (self.ana_id, 'convidado'))
        self.assertNotIn('senha_hash', json.dumps(body))
        sessao = (cookie.split(';')[0], body['csrf'])
        status, _, corpo = self.get(sessao, '/api/sessao')
        dados = json.loads(corpo)
        self.assertEqual(status, 200)
        self.assertEqual((dados['conta']['login'], dados['conta']['casos'], dados['csrf'], dados['ambiente']),
                         ('ana', ['alpha'], body['csrf'], 'homologacao'))
        self.assertIn('expira_em', dados)
        status, _, pagina = self.get(sessao, '/')
        self.assertEqual(status, 200)
        self.assertIn(f'content="{body["csrf"]}"'.encode(), pagina)
        self.assertIn(b'data-papel="convidado"', pagina)

    def test_ambiente_vem_da_variavel(self):
        with patch.dict(os.environ, {'VLADO_AMBIENTE': 'editorial'}):
            self.assertEqual(json.loads(self.get(self.ana, '/api/sessao')[2])['ambiente'], 'editorial')
        with patch.dict(os.environ, {'VLADO_AMBIENTE': 'qualquer'}):
            self.assertEqual(json.loads(self.get(self.ana, '/api/sessao')[2])['ambiente'], 'homologacao')

    def test_entrar_exige_origem_publica_e_json(self):
        self.assertEqual(self.publico('entrar', {'login': 'ana', 'senha': SENHA}, origin=None)[0], 403)
        self.assertEqual(self.publico('entrar', {'login': 'ana', 'senha': SENHA}, origin='https://outro.test')[0], 403)
        self.assertEqual(self.publico('entrar', {'login': 'ana', 'senha': SENHA}, tipo='text/plain')[0], 403)
        status, _, _ = self.request('POST', '/api/entrar', b'{"login":' + b'"a' * 5000 + b'"}',
                                    {'Content-Type': 'application/json', 'Origin': ORIGEM})
        self.assertEqual(status, 400)

    def test_recusa_unica_para_credenciais_e_bloqueio_depois_de_cinco_falhas(self):
        respostas = [self.publico('entrar', {'login': login, 'senha': senha})
                     for login, senha in (('ana', 'errada-mas-longa'), ('ninguem', SENHA), ('ana', ''))]
        for status, headers, body in respostas:
            self.assertEqual((status, body['codigo'], body['erro']), (401, 'credenciais', 'Login ou senha incorretos.'))
            self.assertNotIn('Set-Cookie', headers)
        for _ in range(3):
            self.publico('entrar', {'login': 'ana', 'senha': 'errada-mas-longa'})
        status, _, body = self.publico('entrar', {'login': 'ana', 'senha': SENHA})
        self.assertEqual((status, body['codigo']), (429, 'bloqueado'))

    def test_limite_por_ip_usa_o_proxy_somente_quando_configurado(self):
        for numero in range(20):
            self.publico('entrar', {'login': f'ninguem{numero}', 'senha': SENHA},
                         extra={'X-Forwarded-For': f'198.51.100.{numero}'})
        self.assertEqual(self.publico('entrar', {'login': 'ana', 'senha': SENHA})[0], 429)  # same socket address
        acesso.limpar_limites()
        with patch.dict(os.environ, {'VLADO_CONFIAR_PROXY': '1'}):
            for numero in range(20):
                self.publico('entrar', {'login': f'ninguem{numero}', 'senha': SENHA},
                             extra={'X-Forwarded-For': '10.0.0.1, 203.0.113.7'})
            self.assertEqual(self.publico('entrar', {'login': 'ana', 'senha': SENHA},
                                          extra={'X-Forwarded-For': '203.0.113.7'})[0], 429)
            self.assertEqual(self.publico('entrar', {'login': 'ana', 'senha': SENHA},
                                          extra={'X-Forwarded-For': '203.0.113.8'})[0], 200)

    def test_sair_encerra_a_sessao_e_apaga_o_cookie(self):
        status, _ = self.post(self.ana, 'sessao-sair', {})
        self.assertEqual(status, 200)
        self.assertEqual(self.post(self.ana, 'codex-status', {})[0], 401)
        self.assertEqual(self.get(self.ana, '/api/sessao')[0], 401)
        self.assertEqual(self.get(self.ana, '/')[0], 303)

    def test_inatividade_derruba_a_sessao(self):
        with patch('acesso.agora', return_value=acesso.agora() + timedelta(hours=2, minutes=1)):
            status, body = self.post(self.ana, 'codex-status', {})
        self.assertEqual((status, body['estado'], body['codigo']), (401, 'sem_sessao', 'sessao_expirada'))

    def test_post_anonimo_pequeno_sempre_recebe_401_inteiro(self):
        # Without draining the small body, Windows may reset the socket and lose the 401 (seen once under load).
        corpo = json.dumps({'caso': 'alpha', 'texto': 'x' * 30000})
        for _ in range(40):
            status, _, body = self.request('POST', '/api/codex-status', corpo,
                                           {'Content-Type': 'application/json', 'Origin': ORIGEM})
            self.assertEqual((status, json.loads(body)['codigo']), (401, 'sessao_expirada'))

    def test_post_autenticado_exige_origem_csrf_e_json(self):
        self.assertEqual(self.post(self.ana, 'codex-status', {}, origin='http://127.0.0.1')[0], 403)
        self.assertEqual(self.post(self.ana, 'codex-status', {}, origin=None)[0], 403)
        self.assertEqual(self.post((self.ana[0], 'errado'), 'codex-status', {})[0], 403)
        self.assertEqual(self.post(('vlado_sessao=forjada', self.ana[1]), 'codex-status', {})[0], 401)
        self.assertEqual(self.post(self.ana, 'codex-status', {})[0], 200)

    def test_registro_de_acesso_corrompido_responde_503(self):
        acesso._PRONTOS.clear()
        for sobra in (self.root / 'acesso').glob('contas.sqlite-*'):
            sobra.unlink()
        acesso.caminho_bd(self.root).write_bytes(b'{quebrado' * 200)
        self.assertEqual(self.get(self.ana, '/')[0], 503)
        self.assertEqual(self.post(self.ana, 'codex-status', {})[0], 503)
        self.assertEqual(self.publico('entrar', {'login': 'ana', 'senha': SENHA})[0], 503)


class AtivacaoTest(Http):
    def test_link_de_ativacao_do_operador_ativa_uma_unica_vez_sem_abrir_sessao(self):
        # Activation links are the operator's now (the terminal); in the Mesa people come in by invitation.
        conta, token = acesso.criar_conta(self.root, 'Caio', 'caio', casos=['alpha'], cota_diaria=3)
        self.assertEqual(conta['situacao'], 'aguardando_senha')
        status, _, body = self.publico('ativacao-consultar', {'token': token})
        self.assertEqual((status, body['login']), (200, 'caio'))
        self.assertEqual(self.publico('ativar', {'token': token, 'senha': 'curta'})[0], 400)
        status, headers, body = self.publico('ativar', {'token': token, 'senha': SENHA})
        self.assertEqual(status, 200, body)
        self.assertNotIn('Set-Cookie', headers)
        status, _, body = self.publico('ativar', {'token': token, 'senha': SENHA})
        self.assertEqual((status, body['codigo']), (400, 'ativacao_invalida'))
        self.assertEqual(self.publico('ativacao-consultar', {'token': token})[0], 400)
        self.entrar('caio')
        listadas = self.post(self.admin, 'equipe-listar', {})[1]
        self.assertIn('caio', [p['login'] for p in listadas['pessoas']])
        texto = json.dumps(listadas)
        self.assertNotIn(token, texto)
        self.assertNotIn('senha_hash', texto)
        self.assertNotIn(token, bytes_do_armazenamento(self.root))

    def test_ativacao_expirada_e_recusada(self):
        _, token = acesso.criar_conta(self.root, 'Duda', 'duda', casos=['alpha'], horas=1)
        with patch('acesso.agora', return_value=acesso.agora() + timedelta(hours=2)):
            status, _, body = self.publico('ativar', {'token': token, 'senha': SENHA})
        self.assertEqual((status, body['codigo']), (400, 'ativacao_invalida'))

    def test_ativar_exige_origem(self):
        _, token = acesso.criar_conta(self.root, 'Duda', 'duda', casos=['alpha'])
        self.assertEqual(self.publico('ativar', {'token': token, 'senha': SENHA}, origin=None)[0], 403)


class PapeisTest(Http):
    def test_convidado_e_recusado_em_toda_operacao_de_administracao(self):
        for operation in SO_ADMIN:
            with self.subTest(operation=operation):
                status, body = self.post(self.ana, operation, {'caso': 'alpha', 'id': self.ana_id})
                self.assertEqual((status, body.get('estado')), (403, 'proibido'), body)
        self.assertEqual(self.post(self.ana, 'acesso-listar', {})[0], 404)  # v1 invitation operations are gone

    def test_convidado_so_alcanca_os_rascunhos_da_pergunta(self):
        import interface_pesquisa
        import rascunhos
        # Beyond the conversation itself, the only guest operations are the drafts.
        extras = set(interface_pesquisa.OPERACOES_CONVIDADO) - {
            'codex-status', 'codex-listar', 'codex-perguntar', 'codex-eventos', 'codex-cancelar', 'codex-retomar',
            'codex-original', 'sessao-sair'}
        self.assertEqual(extras, set(rascunhos.OPERACOES))
        status, body = self.post(self.ana, 'rascunhos-salvar', {'caso': 'alpha', 'tela': 'pergunta', 'versao': 0,
                                                                'conteudo': {'texto': 'Pergunta em preparo.'}})
        self.assertEqual(status, 200, body)
        for tela in ('caderno/N0001', 'quadro-diligencias', 'quadro-revisao/A001'):
            with self.subTest(tela=tela):
                status, body = self.post(self.ana, 'rascunhos-salvar', {'caso': 'alpha', 'tela': tela, 'versao': 0,
                                                                        'conteudo': {'texto': 'Fora da pergunta.'}})
                self.assertEqual(status, 400, body)
                status, body = self.post(self.ana, 'rascunhos-ler', {'caso': 'alpha', 'tela': tela})
                self.assertEqual(status, 400, body)
        # A draft of another screen written by the admin does not show in the guest listing.
        self.assertEqual(self.post(self.admin, 'rascunhos-salvar', {'caso': 'alpha', 'tela': 'caderno/N0001', 'versao': 0,
                                                                   'conteudo': {'texto': 'Nota da editora.'}})[0], 200)
        status, body = self.post(self.ana, 'rascunhos-listar', {'caso': 'alpha'})
        self.assertEqual(status, 200, body)
        self.assertEqual([r['tela'] for r in body['rascunhos']], ['pergunta'])
        self.assertEqual(self.post(self.ana, 'continuidade-resumo', {'caso': 'alpha'})[0], 403)

    def test_admin_alcanca_operacoes_de_administracao(self):
        for operation in ('equipe-listar', 'apuracao-notas', 'caderno-listar', 'gerenciar-listar', 'ia-config'):
            with self.subTest(operation=operation):
                self.assertNotIn(self.post(self.admin, operation, {'caso': 'alpha'})[0], (401, 403))
        self.assertEqual(self.post(self.admin, 'codex-desligar', {})[0], 403)

    def test_catalogo_filtrado_por_conta(self):
        casos = lambda sessao: [c['id'] for c in json.loads(self.get(sessao, '/api/catalogo')[2])['casos']]  # noqa: E731
        self.assertEqual(casos(self.ana), ['alpha'])
        self.assertEqual(casos(self.bia), ['beta'])
        self.assertEqual(sorted(casos(self.admin)), ['alpha', 'beta'])

    def test_convidado_so_nos_casos_liberados_e_campos_permitidos(self):
        # A case out of reach and a case that does not exist: the same answer, byte for byte.
        fora = self.post(self.ana, 'codex-listar', {'caso': 'beta'})
        self.assertEqual((fora[0], fora[1]['codigo']), (404, 'caso_indisponivel'))
        self.assertEqual(fora, self.post(self.ana, 'codex-listar', {'caso': 'nao_existe'}))
        self.assertEqual(fora, self.post(self.ana, 'codex-listar', {'caso': '../x'}))
        self.assertEqual(self.post(self.ana, 'codex-perguntar', {'caso': 'beta', 'pergunta': 'x'}), fora)
        self.assertEqual(self.post(self.ana, 'codex-perguntar', {'caso': 'alpha', 'pergunta': 'x',
                                                                 'observacoes_humanas': {}})[0], 403)
        self.assertEqual(self.post(self.ana, 'codex-listar', {'caso': 'alpha'})[0], 200)

    def test_convidados_isolados_entre_si(self):
        conversa = self.perguntar(self.ana)
        self.assertEqual(self.post(self.ana, 'codex-listar', {'caso': 'alpha'})[1]['conversas'][0]['id'], conversa)
        status, eventos = self.post(self.ana, 'codex-eventos', {'conversa': conversa})
        self.assertEqual(status, 200)
        self.assertFalse({'dono', 'thread_id', 'turn_id', 'politica'} & set(eventos['conversa']))
        outra_alpha = self.conta('Edu', 'edu', casos=['alpha'])
        edu = self.entrar('edu')
        self.assertEqual(self.post(edu, 'codex-listar', {'caso': 'alpha'})[1]['conversas'], [])
        for sessao in (edu, self.bia):
            for operation in ('codex-eventos', 'codex-cancelar', 'codex-original', 'codex-retomar'):
                with self.subTest(operation=operation, sessao=sessao[0][-6:]):
                    dados = {'conversa': conversa} if operation == 'codex-retomar' else {'conversa': conversa, 'referencia': '0' * 64}
                    status, result = self.post(sessao, operation, dados)
                    self.assertEqual(status, 400, result)
                    self.assertEqual(result['codigo'], 'conversa_indisponivel')
        self.assertTrue(outra_alpha)

    def test_caso_retirado_vale_na_requisicao_seguinte_inclusive_para_conversas_proprias(self):
        conversa = self.perguntar(self.ana)
        self.assertEqual(self.post(self.admin, 'caso-incluir', {'caso': 'beta', 'conta': self.ana_id})[0], 200)
        self.assertEqual(self.post(self.admin, 'caso-retirar', {'caso': 'alpha', 'conta': self.ana_id})[0], 200)
        self.assertEqual(self.post(self.ana, 'codex-listar', {'caso': 'alpha'})[0], 404)
        for operation in ('codex-eventos', 'codex-cancelar', 'codex-original', 'codex-retomar'):
            with self.subTest(operation=operation):
                dados = {'conversa': conversa} if operation == 'codex-retomar' else {'conversa': conversa, 'referencia': '0' * 64}
                status, result = self.post(self.ana, operation, dados)
                self.assertEqual((status, result['codigo']), (400, 'conversa_indisponivel'), result)
        self.assertEqual(self.post(self.ana, 'codex-perguntar', {'caso': 'alpha', 'pergunta': 'x', 'conversa': conversa})[0], 404)
        self.assertEqual([c['id'] for c in json.loads(self.get(self.ana, '/api/catalogo')[2])['casos']], ['beta'])

    def test_conta_desativada_ou_recuperada_perde_a_sessao_na_requisicao_seguinte(self):
        self.assertEqual(self.post(self.admin, 'equipe-desativar', {'conta': self.ana_id})[0], 200)
        self.assertEqual(self.post(self.ana, 'codex-status', {})[0], 401)
        self.assertEqual(self.publico('entrar', {'login': 'ana', 'senha': SENHA})[0], 401)
        self.assertEqual(self.post(self.admin, 'equipe-reativar', {'conta': self.ana_id})[0], 200)
        self.entrar('ana')
        # In the hosted service no answer of the Mesa carries a recovery link: without real delivery, and for an
        # account without e-mail, the recovery is the operator's, at the terminal (contract, 8.2).
        status, result = self.post(self.admin, 'equipe-recuperar', {'conta': self.bia_id, 'senha': SENHA})
        self.assertEqual((status, result.get('codigo')), (400, 'recuperacao_pelo_operador'))
        self.assertNotIn('link', result)
        self.assertEqual(self.post(self.bia, 'codex-status', {})[0], 200)  # nothing happened to the account
        acesso.recuperar(self.root, self.bia_id, por='cli')
        self.assertEqual(self.post(self.bia, 'codex-status', {})[0], 401)

    def test_papel_rebaixado_perde_administracao_na_requisicao_seguinte(self):
        segundo = self.conta('Chefe', 'chefe', papel='admin')
        chefe = self.entrar('chefe')
        self.assertEqual(self.post(chefe, 'equipe-listar', {})[0], 200)
        # Changing the role of a dono, and deactivating one, ask the password (contract, 5.15) ...
        status, result = self.post(self.admin, 'equipe-papel', {'conta': segundo, 'papel': 'leitor'})
        self.assertEqual((status, result.get('codigo')), (403, 'senha_necessaria'))
        self.assertEqual(self.post(self.admin, 'equipe-desativar', {'conta': segundo})[1].get('codigo'), 'senha_necessaria')
        self.assertEqual(self.post(chefe, 'equipe-listar', {})[0], 200)
        # ... and nobody is given the legacy guest profile again (contract, 2.3).
        status, _ = self.post(self.admin, 'equipe-papel', {'conta': segundo, 'papel': 'convidado', 'senha': SENHA})
        self.assertEqual(status, 400)
        status, _ = self.post(self.admin, 'equipe-papel', {'conta': segundo, 'papel': 'leitor', 'senha': SENHA})
        self.assertEqual(status, 200)
        self.assertEqual(self.post(chefe, 'equipe-listar', {})[0], 403)

    def test_promover_a_dono_pede_a_senha(self):
        for senha, codigo in (({}, 'senha_necessaria'), ({'senha': 'senha-errada-de-teste'}, 'senha_atual_incorreta')):
            status, result = self.post(self.admin, 'equipe-papel', {'conta': self.ana_id, 'papel': 'dono', **senha})
            self.assertEqual((status, result.get('codigo')), (403, codigo))
        self.assertEqual(self.post(self.admin, 'equipe-papel', {'conta': self.ana_id, 'papel': 'admin', 'senha': SENHA})[0], 400)
        status, result = self.post(self.admin, 'equipe-convidar', {'email': 'outra.chefe@exemplo.test', 'papel': 'dono'})
        self.assertEqual((status, result.get('codigo')), (403, 'senha_necessaria'))
        self.assertEqual(self.post(self.ana, 'equipe-listar', {})[0], 403)  # still a guest
        self.assertEqual(self.post(self.admin, 'equipe-listar', {})[1]['convites'], [])
        self.assertEqual(self.post(self.admin, 'equipe-papel', {'conta': self.ana_id, 'papel': 'dono', 'senha': SENHA})[0], 200)
        self.assertEqual(self.post(self.ana, 'equipe-listar', {})[0], 200)

    def test_as_contas_antigas_sairam_com_o_convite(self):
        # Withdrawn (P30): the old account operations answer as any operation that does not exist.
        for operation, dados in (('contas-listar', {}), ('contas-criar', {'nome': 'X', 'login': 'xis', 'papel': 'admin'}),
                                 ('contas-atualizar', {'id': self.ana_id, 'papel': 'admin'}),
                                 ('contas-desativar', {'id': self.bia_id}), ('contas-reativar', {'id': self.bia_id}),
                                 ('contas-recuperar', {'id': self.bia_id})):
            for sessao in (self.admin, self.ana):
                self.assertEqual(self.post(sessao, operation, dados)[0], 404, operation)
        self.assertEqual(self.post(self.bia, 'codex-status', {})[0], 200)
        self.assertNotIn('xis', [p['login'] for p in self.post(self.admin, 'equipe-listar', {})[1]['pessoas']])

    def test_ultimo_admin_protegido_pela_interface(self):
        status, result = self.post(self.admin, 'equipe-desativar', {'conta': self.admin_id, 'senha': SENHA})
        self.assertEqual((status, result.get('codigo')), (400, 'ultimo_dono'))
        self.assertIn('último', result['erro'])
        status, result = self.post(self.admin, 'equipe-papel', {'conta': self.admin_id, 'papel': 'leitor', 'senha': SENHA})
        self.assertEqual((status, result.get('codigo')), (400, 'ultimo_dono'))

    def test_convite_e_participacao_validam_apuracoes_existentes(self):
        status, result = self.post(self.admin, 'equipe-convidar', {'email': 'xis@exemplo.test', 'papel': 'leitor',
                                                                   'casos': ['inexistente']})
        self.assertEqual(status, 400, result)
        status, result = self.post(self.admin, 'caso-incluir', {'caso': 'inexistente', 'conta': self.ana_id})
        self.assertEqual(status, 404, result)
        self.assertEqual(self.post(self.admin, 'equipe-listar', {})[1]['convites'], [])

    def test_autoria_de_notas_vem_da_conta_da_sessao(self):
        status, result = self.post(self.admin, 'apuracao-nota-salvar', {'caso': 'alpha', 'requisicao_id': 'a' * 32,
                                                                         'titulo': 'Nota', 'texto': 'Texto.'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['nota']['criado_por']['nome'], 'Editora')
        self.assertEqual(result['nota']['criado_por']['origem'], 'conta_autenticada_da_mesa')

    def test_cota_diaria_por_conta(self):
        acesso.atualizar(self.root, self.ana_id, por='cli', cota_diaria=1)  # the legacy daily quota is the operator's
        self.perguntar(self.ana)
        status, erro = self.post(self.ana, 'codex-perguntar', {'caso': 'alpha', 'pergunta': 'Outra.'})
        self.assertEqual((status, erro['codigo'], erro['parametros']), (400, 'cota_diaria_esgotada', {'cota': 1}))

    def test_convidado_nao_envia_corpo_grande(self):
        cookie, csrf = self.ana
        status, _, body = self.request('POST', '/api/cadastrar', b'{"x": "' + b'a' * 40000 + b'"}', {
            'Content-Type': 'application/json', 'Cookie': cookie, 'X-Session-Token': csrf, 'Origin': ORIGEM})
        self.assertEqual(status, 400)


class SegredosTest(Http):
    def test_eventos_e_registro_nao_guardam_senhas_tokens_ou_links(self):
        _, token = acesso.criar_conta(self.root, 'Fia', 'fia', casos=['alpha'], cota_diaria=3)
        criada = {'link': ORIGEM + '/ativar/' + token}
        self.publico('ativar', {'token': token, 'senha': 'senha-da-fia-123'})
        self.publico('entrar', {'login': 'fia', 'senha': 'senha-errada-da-fia'})
        fia = self.entrar('fia', 'senha-da-fia-123')
        self.post(fia, 'sessao-sair', {})
        bruto = bytes_do_armazenamento(self.root)
        for segredo in (token, criada['link'], 'senha-da-fia-123', 'senha-errada-da-fia', fia[0].split('=', 1)[1]):
            self.assertNotIn(segredo, bruto)
        eventos = json.dumps(acesso.eventos(self.root, 1000))
        self.assertNotIn('$argon2', eventos)
        self.assertNotIn(fia[1], eventos)
        listados = self.post(self.admin, 'equipe-atividade', {})[1]
        self.assertTrue(listados['eventos'])
        self.assertNotIn('csrf', json.dumps(listados))


if __name__ == '__main__':
    unittest.main()
