"""Ponta a ponta sem modelo: backup de uma instalação, restauração em outra e uso pelo HTTP do piloto.

Confere, na instalação restaurada: caderno com autoria da conta, original aberto na página citada com
o mesmo hash, histórico de conversas e isolamento entre duas contas convidadas. Sem rede nem API paga.
"""
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fixture_achados import Ambiente
import acesso
import apuracao
import backup
from comum import escrever_json, ler_json
from interface_pesquisa import Servidor

ORIGEM = 'https://vlado.test'
SENHA = 'senha-longa-de-teste-1'
CONVERSA_ANA = 'a' * 32
CONVERSA_BIA = 'b' * 32


def conversa(root, identificador, caso, dono, pergunta):
    pasta = root / 'conversas' / identificador
    escrever_json(pasta / 'conversa.json', {
        'id': identificador, 'caso': caso, 'titulo': pergunta, 'estado': 'concluido', 'dono': dono,
        'rodadas': ['R001'], 'pergunta_atual': pergunta, 'criada_em_utc': '2026-01-01T00:00:00Z'})
    eventos = [{'seq': 1, 'em_utc': '2026-01-01T00:00:01Z', 'tipo': 'pergunta', 'dados': {'texto': pergunta}},
               {'seq': 2, 'em_utc': '2026-01-01T00:00:02Z', 'tipo': 'final', 'dados': {'texto': 'Resposta sintética.'}}]
    (pasta / 'eventos.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in eventos),
                                         encoding='utf-8')


class PontaAPontaTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'VLADO_ACESSO': ''})
        env.start()
        self.addCleanup(env.stop)
        self.origem = self.instalacao_original()
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for nome in ('prompts', 'AGENTS.md', 'configuracao.json'):  # código/configuração da nova instalação
            fonte = self.origem.root / nome
            (shutil.copytree if fonte.is_dir() else shutil.copy2)(fonte, self.root / nome)
        pacotes = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pacotes, ignore_errors=True)
        restauradas = backup.restaurar(self.root, backup.criar(self.origem.root, pacotes))
        self.assertIn('casos', restauradas)
        self.server = Servidor(('127.0.0.1', 0), self.root, modo='piloto', origem=ORIGEM)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(),
                                 self.server.conversas.close(), thread.join(3)))

    def instalacao_original(self):
        fx = Ambiente()
        self.addCleanup(fx.cleanup)
        fx.completo()
        fx.caso('beta')
        root = fx.root
        # Accounts with passwords (acesso v2); the activation happens before the backup.
        self.editora, self.token_editora = self.criar(root, 'Editora', 'editora', 'admin')
        self.ana, self.token_ana = self.criar(root, 'Ana', 'ana')
        self.bia, self.token_bia = self.criar(root, 'Bia', 'bia')
        conta = {'id': self.editora['id'], 'nome': 'Editora'}
        nota = apuracao.executar(root, 'apuracao-nota-salvar', {
            'caso': 'alpha', 'requisicao_id': 'c' * 32, 'titulo': 'Pauta', 'texto': 'Hipótese.'}, conta)['nota']
        apuracao.executar(root, 'apuracao-nota-inserir', {
            'caso': 'alpha', 'requisicao_id': 'd' * 32, 'nota_id': nota['id'], 'revisao_nota': nota['revisao'],
            'origem': {'tipo': 'ia', 'rodada': 'R001', 'revisao': 'r2', 'geracao_achados': 'g2',
                       'achado_id': 'A001', 'achado_versao': 2, 'texto': 'A fonte declara'}}, conta)
        conversa(root, CONVERSA_ANA, 'alpha', self.ana['id'], 'Pergunta da Ana?')
        conversa(root, CONVERSA_BIA, 'alpha', self.bia['id'], 'Pergunta da Bia?')
        return fx

    def request(self, method, path, body=None, headers=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request(method, path, body, {'Host': 'vlado.test', **(headers or {})})
        response = con.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        con.close()
        return result

    @staticmethod
    def criar(root, nome, login, papel='convidado'):
        conta, token = acesso.criar_conta(root, nome, login, papel=papel, casos=['alpha'])
        acesso.ativar(root, token, SENHA)
        return conta, login

    def entrar(self, login):
        status, headers, body = self.request('POST', '/api/entrar', json.dumps({'login': login, 'senha': SENHA}),
                                             {'Content-Type': 'application/json', 'Origin': ORIGEM})
        self.assertEqual(status, 200, body[:200])
        return headers['Set-Cookie'].split(';')[0], json.loads(body)['csrf']

    def post(self, sessao, operation, data):
        cookie, csrf = sessao
        status, _, body = self.request('POST', '/api/' + operation, json.dumps(data), {
            'Content-Type': 'application/json', 'Cookie': cookie, 'X-Session-Token': csrf, 'Origin': ORIGEM})
        return status, body

    def json(self, sessao, operation, data, esperado=200):
        status, body = self.post(sessao, operation, data)
        self.assertEqual(status, esperado, body[:300])
        return json.loads(body)

    def test_originais_restaurados_conservam_o_hash_do_manifesto(self):
        manifesto = ler_json(self.root / 'casos/alpha/manifesto.json')
        for documento in manifesto['documentos']:
            caminho = self.root / documento['arquivo']
            self.assertEqual(hashlib.sha256(caminho.read_bytes()).hexdigest(), documento['sha256'])

    def test_caderno_restaurado_abre_o_original_na_pagina_citada(self):
        editora = self.entrar(self.token_editora)
        notas = self.json(editora, 'apuracao-notas', {'caso': 'alpha'})['notas']
        self.assertEqual([(n['titulo'], n['autor'], n['fontes']) for n in notas], [('Pauta', 'Editora', 1)])
        detalhe = self.json(editora, 'apuracao-nota', {'caso': 'alpha', 'nota_id': notas[0]['id']})
        self.assertIn('[Fonte 1]', detalhe['nota']['texto'])
        documento = next(d for d in detalhe['fontes'][0]['documentos'] if d['pagina_pdf'])
        self.assertTrue(documento['disponivel'])
        abrir = {k: v for k, v in documento['abrir'].items() if k != 'operacao'}
        status, corpo = self.post(editora, 'apuracao-original', abrir)
        self.assertEqual(status, 200)
        self.assertTrue(corpo.startswith(b'%PDF'))
        self.assertEqual(hashlib.sha256(corpo).hexdigest(), documento['original_sha256'])
        from pypdf import PdfReader
        self.assertGreaterEqual(len(PdfReader(io.BytesIO(corpo)).pages), documento['pagina_pdf'])

    def test_historico_restaurado_e_isolado_entre_duas_contas(self):
        ana, bia = self.entrar(self.token_ana), self.entrar(self.token_bia)
        listadas = self.json(ana, 'codex-listar', {'caso': 'alpha'})['conversas']
        self.assertEqual([(c['id'], c['pergunta']) for c in listadas], [(CONVERSA_ANA, 'Pergunta da Ana?')])
        eventos = self.json(ana, 'codex-eventos', {'conversa': CONVERSA_ANA})
        self.assertEqual([e['tipo'] for e in eventos['eventos']], ['pergunta', 'final'])
        self.assertEqual([c['id'] for c in self.json(bia, 'codex-listar', {'caso': 'alpha'})['conversas']],
                         [CONVERSA_BIA])
        for operation in ('codex-eventos', 'codex-retomar', 'codex-cancelar'):
            with self.subTest(operation=operation):
                erro = self.json(bia, operation, {'conversa': CONVERSA_ANA}, esperado=400)
                self.assertIn('indisponível', erro['erro'])
        self.assertEqual(self.post(ana, 'codex-listar', {'caso': 'beta'})[0], 404)  # out of reach: as nonexistent (contrato de contas, 4.3)
        self.assertEqual(self.post(ana, 'apuracao-notas', {'caso': 'alpha'})[0], 403)


if __name__ == '__main__':
    unittest.main()
