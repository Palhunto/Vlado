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
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
from cenario_redacoes import SENHA
import fator_de_teste
import segredos

CHAVE_IA = 'sk-sentinela-da-chave-de-ia-000SENTINELA'


class ExportarTest(cenario.DuasRedacoes):
    _n = 0

    def nova(self, papel='reporter'):
        ExportarTest._n += 1
        login = f'pessoa.exporta{ExportarTest._n}'
        cid = self.conta(f'Pessoa Exporta {ExportarTest._n}', login, papel, casos=['alpha'])
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

    def test_o_arquivo_e_um_anexo_json_com_a_conta_e_o_que_falta(self):
        sessao, cid = self.nova()
        status, cabecalhos, corpo = self.exportar(sessao)
        self.assertEqual(status, 200, corpo[:200])
        self.assertEqual(cabecalhos['Content-Type'], 'application/json; charset=utf-8')
        self.assertRegex(cabecalhos['Content-Disposition'], r'^attachment; filename="vlado-meus-dados-\d{4}-\d{2}-\d{2}\.json"$')
        self.assertEqual(cabecalhos['Cache-Control'], 'no-store')
        dados = json.loads(corpo)
        self.assertEqual((dados['formato'], dados['versao'], dados['incompleto']),
                         ('vlado-meus-dados', 1, ['itens_criados', 'registro_de_acesso']))
        self.assertEqual(set(dados), {'formato', 'versao', 'gerado_em', 'conta', 'redacao', 'segundo_fator', 'termos',
                                      'sessoes', 'aparelhos', 'participacoes', 'eventos', 'incompleto'})
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
