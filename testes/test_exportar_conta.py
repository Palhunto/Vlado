"""Exportar meus dados (``conta-exportar``; contrato de contas, seção 8.4 e entrega 4b-2).

Um arquivo JSON para baixar, com o que o armazenamento guarda da pessoa e só dela: perfil, redação, segundo fator
(estado), aceites dos termos, sessões abertas, aparelhos (datas), participações e os eventos da atividade em que
ela aparece. A outra conta de um evento sai sem nome nem id (ressalva B1), e nenhum segredo sai, nem em parte: um
teste de sentinela planta valores marcados em cada lugar e confere o arquivo. Sem modelo e sem rede.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
from cenario_redacoes import SENHA
import fator_de_teste
import registro_acesso
import rotas_contas
import segredos

CHAVE_IA = 'sk-sentinela-da-chave-de-ia-000SENTINELA'


class ExportarTest(cenario.DuasRedacoes):
    _n = 0

    def nova(self, papel='reporter'):
        ExportarTest._n += 1
        login = f'pessoa.exporta{ExportarTest._n}'
        cid = self.conta(f'Pessoa Exporta {ExportarTest._n}', login, papel, casos=['alpha'])
        acesso.limpar_limites()  # the per-address ceiling of sign-ins: this class signs in many times a minute
        return self._entrar(login), cid

    def exportar(self, sessao):
        cookie, csrf = sessao
        return self.pedir('POST', '/api/conta-exportar', '{}', {'Content-Type': 'application/json', 'Cookie': cookie,
                                                                'X-Session-Token': csrf, 'Origin': cenario.ORIGEM})

    def banco(self, sql, *args, escrever=False):
        con = sqlite3.connect(acesso.caminho_bd(self.root))
        try:
            linhas = con.execute(sql, args).fetchall()
            if escrever:
                con.commit()
            return linhas
        finally:
            con.close()

    def sem_partes(self):
        """The audit log's part absent, and no module answering for the items: the file says both are missing."""
        return patch.object(registro_acesso, 'acessos_da_conta', None, create=True)

    def test_o_arquivo_e_um_anexo_json_com_a_conta_e_o_que_falta(self):
        sessao, cid = self.nova()
        with self.sem_partes():
            status, cabecalhos, corpo = self.exportar(sessao)
        self.assertEqual(status, 200, corpo[:200])
        self.assertEqual(cabecalhos['Content-Type'], 'application/json; charset=utf-8')
        self.assertRegex(cabecalhos['Content-Disposition'], r'^attachment; filename="vlado-meus-dados-\d{4}-\d{2}-\d{2}\.json"$')
        self.assertEqual(cabecalhos['Cache-Control'], 'no-store')
        dados = json.loads(corpo)
        self.assertEqual((dados['formato'], dados['versao'], dados['incompleto']),
                         ('vlado-meus-dados', 1, ['itens_criados', 'registro_de_acesso']))
        self.assertEqual(set(dados), {'formato', 'versao', 'gerado_em', 'conta', 'redacao', 'segundo_fator', 'termos',
                                      'sessoes', 'aparelhos', 'participacoes', 'eventos', 'itens_criados', 'acessos',
                                      'conversas_desde', 'incompleto'})
        self.assertEqual((dados['itens_criados'], dados['acessos']), (None, None))
        self.assertEqual((dados['conta']['id'], dados['conta']['papel'], dados['redacao']['id'], dados['participacoes']),
                         (cid, 'reporter', self.a, ['alpha']))
        self.assertTrue(dados['sessoes'] and dados['aparelhos'])
        dia = re.search(r'(\d{4}-\d{2}-\d{2})\.json', cabecalhos['Content-Disposition']).group(1)
        self.assertTrue(dados['gerado_em'].startswith(dia))  # the date of the name is the UTC day of the file
        self.sem_sentinela(corpo)  # nothing of the other newsroom

    def test_nenhum_segredo_sai_nem_em_parte(self):
        sessao, cid = self.nova('editor')  # an editor of the hosted service: with the second factor enrolled
        cookie, csrf = sessao
        sid = cookie.split('=', 1)[1]
        fator = fator_de_teste._CADASTRADOS[str(self.root), cid]
        agora = acesso._iso(acesso.agora())
        # Secrets the store keeps for this account, marked, wherever they are: links, the ticket of the second step,
        # a recovery, an accepted invitation, the AI key of the newsroom.
        marcados = {'link': 'SENTINELA-LINK-' + 'a' * 40, 'bilhete': 'SENTINELA-BILHETE-' + 'b' * 40,
                    'convite': 'SENTINELA-CONVITE-' + 'c' * 40, 'recuperacao': 'SENTINELA-RECUPERACAO-' + 'd' * 20}
        self.banco('INSERT INTO links (token_sha256, tipo, conta, criado_em, expira_em) VALUES (?, ?, ?, ?, ?)',
                   marcados['link'], 'redefinicao', cid, agora, '2999-01-01T00:00:00+00:00', escrever=True)
        self.banco('INSERT INTO entradas (id_sha256, conta, chave, criada_em, expira_em) VALUES (?, ?, ?, ?, ?)',
                   marcados['bilhete'], cid, 'x', agora, '2999-01-01T00:00:00+00:00', escrever=True)
        self.banco("INSERT INTO convites (id, organizacao, email, papel, token_sha256, estado, criado_em, criado_por, expira_em,"
                   " enviado_em, conta) VALUES (?, ?, 'x@exemplo.test', 'editor', ?, 'aceito', ?, ?, ?, ?, ?)",
                   'f' * 16, self.a, marcados['convite'], agora, self.ids['dono'], agora, agora, cid, escrever=True)
        self.banco('INSERT INTO recuperacoes (id, organizacao, conta, pedida_por, pedida_em, expira_em) VALUES (?, ?, ?, ?, ?, ?)',
                   marcados['recuperacao'], self.a, cid, self.ids['dono'], agora, agora, escrever=True)
        with patch.dict(os.environ, {'VLADO_SEGREDOS': ''}):
            segredos.salvar_chave(self.root, 'anthropic', CHAVE_IA, self.a)
        guardados = {
            'hash da senha': self.banco('SELECT senha_hash FROM contas WHERE id = ?', cid)[0][0],
            'senha': SENHA, 'cookie da sessão': sid, 'csrf': csrf,
            'id da sessão': self.banco('SELECT publico FROM sessoes WHERE conta = ?', cid)[0][0],
            'resumo da sessão': self.banco('SELECT id_sha256 FROM sessoes WHERE conta = ?', cid)[0][0],
            'semente cifrada': self.banco('SELECT semente FROM fatores WHERE conta = ?', cid)[0][0],
            'semente': fator['segredo'], 'código de reserva': fator['reserva'][0],
            'resumo de reserva': self.banco('SELECT resumo FROM codigos_reserva WHERE conta = ?', cid)[0][0],
            'marca do aparelho': self.banco('SELECT resumo FROM aparelhos WHERE conta = ?', cid)[0][0],
            'chave de IA': CHAVE_IA, **marcados}
        status, cabecalhos, corpo = self.exportar(sessao)
        self.assertEqual(status, 200, corpo[:200])
        texto = corpo.decode('utf-8')
        for onde, valor in guardados.items():
            self.assertTrue(valor and len(valor) >= 8, onde)
            for pedaco in {valor, valor[:12], valor[-12:]}:  # nor a part of it
                self.assertNotIn(pedaco, texto, f'{onde} saiu na exportação')
        self.assertIn(cookie.split('=')[0], 'vlado_sessao')  # the test used the session it thinks it used

    def test_a_outra_conta_de_um_evento_sai_sem_nome_nem_id(self):
        # Ressalva B1: the dono changes the role of the person; neither one's file names or identifies the other.
        sessao, cid = self.nova()
        status, _, bruto = self.post('dono', 'equipe-papel', {'conta': cid, 'papel': 'leitor'})
        self.assertEqual(status, 200, bruto[:200])
        dono = acesso.ver_conta(self.root, self.ids['dono'])['conta']
        pessoa = acesso.ver_conta(self.root, cid)['conta']
        da_pessoa = self.exportar(sessao)[2]
        do_dono = self.exportar(self.sessoes['dono'])[2]
        for corpo, outra in ((da_pessoa, dono), (do_dono, pessoa)):
            texto = corpo.decode('utf-8')
            for dado in (outra['id'], outra['nome'], outra['login'], outra['email']):
                if dado:
                    self.assertNotIn(dado, texto)
        eventos = json.loads(da_pessoa)['eventos']
        self.assertIn({'tipo': 'papel_alterado', 'conta': 'voce', 'por': 'outra_conta'},
                      [{k: e[k] for k in ('tipo', 'conta', 'por')} for e in eventos])
        dele = [{k: e[k] for k in ('tipo', 'conta', 'por')} for e in json.loads(do_dono)['eventos']]
        self.assertIn({'tipo': 'papel_alterado', 'conta': 'outra_conta', 'por': 'voce'}, dele)
        criada = [e for e in eventos if e['por'] not in ('voce', 'outra_conta', None)]
        self.assertTrue(all(re.fullmatch(r'[a-z_]+', e['por']) for e in criada), criada)  # only the system's fixed labels

    def test_eventos_so_dos_90_dias_da_atividade(self):
        # Between two daily sweeps an older row may still be in the table; the file follows the window, not the sweep.
        sessao, cid = self.nova()
        velho = acesso._iso(acesso.agora() - acesso.timedelta(days=acesso.ATIVIDADE_DIAS, minutes=1))
        self.banco('INSERT INTO eventos (em, tipo, conta, por, organizacao) VALUES (?, ?, ?, ?, ?)',
                   velho, 'papel_alterado', cid, 'manutencao', self.a, escrever=True)
        eventos = json.loads(self.exportar(sessao)[2])['eventos']
        self.assertTrue(eventos)
        self.assertNotIn(velho, [e['em'] for e in eventos])

    def test_com_termos_pendentes_exporta_e_com_o_fator_pendente_nao(self):
        sessao, cid = self.nova('editor')
        with patch.dict(os.environ, {'VLADO_TERMOS_VERSAO': 'v-exporta', 'VLADO_TERMOS_ENDERECO': 'https://vlado.test/termos'}):
            self.assertEqual(self.get(sessao, '/api/sessao')[1]['pendencias'], ['termos'])
            self.assertEqual(self.exportar(sessao)[0], 200)  # ressalva B2
            acesso.remover_fator(self.root, cid, SENHA)
            self.assertEqual(self.get(sessao, '/api/sessao')[1]['pendencias'], ['termos', 'segundo_fator'])
            status, _, corpo = self.exportar(sessao)  # R1 of the review of 4b-1: the terms never open what the factor closes
            self.assertEqual((status, json.loads(corpo).get('codigo')), (403, 'pendencia_de_conta'))
            self.assertEqual(self.post(sessao, 'conta-termos-aceitar', {'versao': 'v-exporta'})[0], 200)
            self.assertEqual(self.exportar(sessao)[0], 403)  # the factor alone, still pending

    def test_limite_de_exportacoes_por_conta(self):
        # X1 of the review: a file, not a feed. The sixth in the hour is refused; another account is not affected.
        sessao, _ = self.nova()
        for _ in range(acesso.EXPORTACOES_POR_JANELA):
            self.assertEqual(self.exportar(sessao)[0], 200)
        status, _, corpo = self.exportar(sessao)
        recusa = json.loads(corpo)
        self.assertEqual((status, recusa.get('codigo')), (429, 'limite_de_exportacoes'))
        self.assertIn('Tente de novo em até uma hora', recusa['erro'])  # W1: the hour, not "a few minutes"
        self.assertNotIn('minutos', recusa['erro'])
        self.assertEqual(self.exportar(self.nova()[0])[0], 200)
        with patch('acesso.agora', return_value=acesso.agora() + acesso.timedelta(seconds=acesso.EXPORTACAO_JANELA_S)):
            self.assertEqual(self.exportar(sessao)[0], 200)  # the window passed

    def test_eventos_lidos_pelo_indice_da_redacao(self):
        # X1: the events of the file are read from the newsroom's own window, by its index, never the whole table.
        plano = ' '.join(str(linha[-1]) for linha in self.banco(
            'EXPLAIN QUERY PLAN SELECT em, tipo, conta, por FROM eventos WHERE organizacao = ? AND (conta = ? OR por = ?)'
            ' AND em > ? ORDER BY n', self.a, 'c' * 16, 'c' * 16, '2026-01-01T00:00:00Z'))
        self.assertIn('eventos_por_organizacao', plano)

    def test_acessos_do_registro_entram_e_o_que_falha_fica_em_incompleto(self):
        # 4b-2b: the lines of the audit log the person caused, from the Platform's function, as it gives them.
        sessao, cid = self.nova()
        linhas = [{'em': '2026-11-23T10:00:00Z', 'evento': 'login_ok', 'resultado': 'ok', 'cliente': 'web', 'ip': '203.0.113.9'}]
        pedidos = []
        def acessos(root, conta):
            pedidos.append(conta)
            return linhas
        with patch.object(registro_acesso, 'acessos_da_conta', acessos, create=True):
            dados = json.loads(self.exportar(sessao)[2])
        self.assertEqual(pedidos, [cid])  # only the own account, from the session
        self.assertEqual((dados['acessos'], dados['incompleto']), (linhas, ['itens_criados']))
        for erro in (OSError('pasta ilegível'), ValueError('linha ilegível')):
            with patch.object(registro_acesso, 'acessos_da_conta', side_effect=erro, create=True):
                status, _, corpo = self.exportar(sessao)
            dados = json.loads(corpo)
            self.assertEqual((status, dados['acessos'], dados['incompleto']), (200, None, ['itens_criados', 'registro_de_acesso']))

    def test_itens_criados_de_cada_modulo_so_da_propria_redacao(self):
        # 4b-2b: every module answers itens_da_conta(root, conta, casos); the junction asks with the cases of the own
        # newsroom and keeps only the four fields of an item of those cases, whatever a module sends.
        sessao, cid = self.nova()
        pedidos = []
        def itens(root, conta, casos):
            pedidos.append((conta, sorted(casos)))
            return [{'tipo': 'nota', 'caso': 'alpha', 'criado_em': '2026-11-20T10:00:00Z', 'id': 'E1', 'titulo': 'segredo'},
                    {'tipo': 'nota', 'caso': cenario.CASO_B, 'criado_em': '2026-11-21T10:00:00Z', 'id': 'E2'},
                    {'tipo': 'nota', 'caso': 'gama', 'criado_em': 7, 'id': 'E3'},
                    'lixo']
        falso = types.ModuleType('modulo_de_itens_falso')
        falso.itens_da_conta = itens
        with patch.dict(sys.modules, {'modulo_de_itens_falso': falso}), \
                patch.object(rotas_contas, 'MODULOS_DE_ITENS', ('modulo_de_itens_falso',)), \
                patch.object(registro_acesso, 'acessos_da_conta', lambda root, conta: [], create=True), \
                self.sem_criador(lambda root, casos: None):
            dados = json.loads(self.exportar(sessao)[2])
        self.assertEqual(dados['itens_criados'], [{'tipo': 'nota', 'caso': 'alpha', 'criado_em': '2026-11-20T10:00:00Z', 'id': 'E1'}])
        self.assertEqual(dados['incompleto'], [])  # whole: both parts in
        (conta, casos), = pedidos
        self.assertEqual(conta, cid)
        self.assertNotIn(cenario.CASO_B, casos)  # never a case of the other newsroom
        self.assertTrue({'alpha', 'gama', 'delta'} <= set(casos))  # every case of the newsroom, not only the own ones
        # A module whose function does not exist yet, or that fails, leaves the code in `incompleto`.
        for modulo in (types.ModuleType('modulo_de_itens_falso'), falso):
            with patch.dict(sys.modules, {'modulo_de_itens_falso': modulo}), \
                    patch.object(rotas_contas, 'MODULOS_DE_ITENS', ('modulo_de_itens_falso',)), \
                    patch.object(falso, 'itens_da_conta', side_effect=OSError('ilegível')), \
                    patch.object(registro_acesso, 'acessos_da_conta', lambda root, conta: [], create=True), \
                    self.sem_criador(lambda root, casos: None):
                dados = json.loads(self.exportar(sessao)[2])
            self.assertEqual((dados['itens_criados'], dados['incompleto']), (None, ['itens_criados']))

    @staticmethod
    def sem_criador(funcao):
        """`codex_apuracao.conversas_sem_criador` as the Platform's commit brings it (or None: not there yet)."""
        import codex_apuracao
        return patch.object(codex_apuracao, 'conversas_sem_criador', funcao, create=True)

    def test_conversas_de_antes_do_criador_ficam_ditas_em_incompleto(self):
        # The conversations record who created them only from the version that brought it: the file says from when
        # its list of conversations is whole, and that the ones before are not in it.
        sessao, _ = self.nova()
        falso = types.ModuleType('modulo_de_itens_falso')
        falso.itens_da_conta = lambda root, conta, casos: []
        pedidos = []
        def sem_criador(root, casos):
            pedidos.append(sorted(casos))
            return '2026-11-24T09:00:00+00:00'
        casos = [(None, (False, None)), (sem_criador, (False, '2026-11-24T09:00:00+00:00')),
                 (lambda root, casos: None, (True, None)), (lambda root, casos: (_ for _ in ()).throw(OSError()), (False, None))]
        for funcao, (inteiras, desde) in casos:
            with patch.dict(sys.modules, {'modulo_de_itens_falso': falso}), \
                    patch.object(rotas_contas, 'MODULOS_DE_ITENS', ('modulo_de_itens_falso',)), \
                    patch.object(registro_acesso, 'acessos_da_conta', lambda root, conta: [], create=True), \
                    self.sem_criador(funcao):
                dados = json.loads(self.exportar(sessao)[2])
            self.assertEqual((dados['conversas_desde'], dados['incompleto']),
                             (desde, [] if inteiras else ['conversas_anteriores']), funcao)
        self.assertNotIn(cenario.CASO_B, pedidos[0])  # the same cases as the items: never of the other newsroom
        # Without the items, `itens_criados` already says it: the conversations are not asked.
        with patch.object(registro_acesso, 'acessos_da_conta', lambda root, conta: [], create=True), \
                self.sem_criador(sem_criador):
            dados = json.loads(self.exportar(sessao)[2])
        self.assertEqual((dados['conversas_desde'], dados['incompleto']), (None, ['itens_criados']))

    @staticmethod
    def downloads(registrar):
        return [c for c in registrar.call_args_list if c.args[:2] == ('download', 'ok')]

    def test_o_download_fica_no_registro_de_acesso(self):
        sessao, _ = self.nova()
        with patch.object(acesso.registro_acesso, 'registrar', wraps=acesso.registro_acesso.registrar) as registrar:
            self.assertEqual(self.exportar(sessao)[0], 200)
            # The server audits after the body is written: the client may read it first. Wait, inside the patch.
            limite = time.monotonic() + 5
            while not self.downloads(registrar) and time.monotonic() < limite:
                time.sleep(0.02)
        downloads = self.downloads(registrar)
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0].kwargs.get('tipo'), 'exportacao')


if __name__ == '__main__':
    unittest.main()
