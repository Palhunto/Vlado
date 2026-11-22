"""A tela Equipe pelo servidor (``POST /api/equipe-*``; contrato de contas, seções 5.5 e 5.15).

Duas redações no mesmo servidor em modo ``piloto`` (``cenario_redacoes``). O que só o dono alcança está na matriz
(``test_matriz_contas.py``); aqui fica o que as operações fazem: mudar papel, desativar, reativar, remover, definir
tetos e ler a atividade, sempre só dentro da própria redação, com a senha pedida de novo nas operações sensíveis
(inclusive para rebaixar ou desativar outro dono, a primeira ressalva de P28). As regras do armazenamento estão em
``test_acesso.py``. Sem modelo e sem rede.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
import custo
import interface_pesquisa
import registro_acesso
from test_acesso import SENHA

ERRADA = 'senha-errada-de-teste'
INEXISTENTE = '0123456789abcdef'


class EquipeTest(cenario.DuasRedacoes):
    numero = 0

    def nova(self, papel, casos=(), redacao=None):
        """A fresh account of Alfa (or of ``redacao``), signed in: (id, session, login)."""
        type(self).numero += 1
        login = f'{papel}.novo{self.numero}'
        conta, token = acesso.criar_conta(self.root, f'Pessoa Nova {self.numero}', login, papel=papel, casos=list(casos),
                                          organizacao=redacao or self.a, por='operador')
        acesso.ativar(self.root, token, SENHA)
        acesso.limpar_limites()
        return conta['id'], self._entrar(login), login

    def pessoa(self, quem, cid):
        return next((p for p in self.post(quem, 'equipe-listar', {})[1]['pessoas'] if p['id'] == cid), None)

    def recusa(self, quem, operacao, dados, status, codigo):
        resposta = self.post(quem, operacao, dados)
        self.assertEqual((resposta[0], resposta[1].get('codigo')), (status, codigo), resposta[2][:200])
        return resposta

    # --- listar e atividade ---------------------------------------------------------------------

    def test_listar_traz_so_a_propria_redacao_com_papel_apuracoes_e_gasto_de_cada_pessoa(self):
        status, corpo, bruto = self.post('dono', 'equipe-listar', {})
        self.assertEqual(status, 200, bruto[:200])
        pessoas = {p['login']: p for p in corpo['pessoas']}
        self.assertLessEqual({'dona.alfa', 'edu.editor', 'rita.reporter', 'rui.reporter', 'leo.leitor', 'cora.convidada'}, set(pessoas))
        self.assertEqual((corpo['redacao']['id'], corpo['redacao']['nome']), (self.a, 'Redação Alfa'))
        self.assertIsNone(pessoas['dona.alfa']['casos'])  # the dono: every case of the newsroom
        self.assertEqual((pessoas['rita.reporter']['papel'], pessoas['rita.reporter']['casos'], pessoas['rita.reporter']['responsavel_de']),
                         ('reporter', ['alpha', 'gama'], ['alpha']))
        self.assertEqual(pessoas['cora.convidada']['papel'], 'convidado')  # the legacy profile is shown as it is
        for pessoa in corpo['pessoas']:
            self.assertEqual(set(pessoa['gasto']), {'mes', 'gasto_brl', 'teto_brl', 'saldo_brl', 'esgotada'})
        self.assertEqual(corpo['convites'], [])
        self.sem_sentinela(bruto)
        for segredo in ('senha_hash', 'ativacao_sha256', '$argon2', self.sessoes['dono'][1]):
            self.assertNotIn(segredo, bruto.decode('utf-8'))
        da_beta = self.post('dono_b', 'equipe-listar', {})[1]
        self.assertEqual({p['login'] for p in da_beta['pessoas']}, {'dono.sentinela', 'rep.sentinela'})

    def test_gasto_que_soma_redacoes_nao_vai_a_nenhum_dono(self):
        # Until the cost module counts by newsroom, its "organization" is the whole installation: with two newsrooms
        # that number adds both, and it goes to nobody (contrato de contas, 4.5).
        self.assertEqual(custo.chaves_orcamento(self.ids['dono'])['organizacao'], custo.ORGANIZACAO)
        self.assertIsNone(self.post('dono', 'equipe-listar', {})[1]['gasto'])
        cota = self.get('dono', '/api/cota')
        self.assertEqual(cota[0], 200)
        self.assertIn('conta', cota[1])
        self.assertNotIn('organizacao', cota[1])
        with patch.object(custo, 'chaves_orcamento', lambda conta: {'conta': conta, 'organizacao': self.a}):
            self.assertIn('organizacao', self.get('dono', '/api/cota')[1])  # counted by newsroom: its dono sees it
            self.assertEqual(set(self.post('dono', 'equipe-listar', {})[1]['gasto']),
                             {'mes', 'gasto_brl', 'teto_brl', 'saldo_brl', 'esgotada'})
            self.assertNotIn('organizacao', self.get('dono_b', '/api/cota')[1])  # and the other newsroom's dono does not
            self.assertNotIn('organizacao', self.get('editor', '/api/cota')[1])

    def test_atividade_e_so_da_propria_redacao_e_nunca_traz_recusas_do_portao(self):
        alvo, _, _ = self.nova('leitor')
        self.assertEqual(self.post('dono', 'equipe-papel', {'conta': alvo, 'papel': 'editor'})[0], 200)
        self.assertEqual(self.post('editor', 'analises', {'caso': 'beta'})[0], 404)  # a refusal of the gate
        status, corpo, bruto = self.post('dono', 'equipe-atividade', {'limite': 200})
        self.assertEqual(status, 200, bruto[:200])
        primeiro = corpo['eventos'][0]
        self.assertEqual((primeiro['tipo'], primeiro['conta'], primeiro['por'], primeiro['por_nome']),
                         ('papel_alterado', alvo, self.ids['dono'], 'Dona Alfa'))
        self.assertFalse({'acesso_negado', 'operacao_negada'} & {e['tipo'] for e in corpo['eventos']})
        self.assertFalse({self.ids['dono_b'], self.ids['reporter_b']} & {e['conta'] for e in corpo['eventos']})
        self.sem_sentinela(bruto)
        pagina = self.post('dono', 'equipe-atividade', {'limite': 2})[1]
        self.assertEqual((len(pagina['eventos']), pagina['eventos']), (2, corpo['eventos'][:2]))
        seguinte = self.post('dono', 'equipe-atividade', {'limite': 2, 'antes': pagina['proximo']})[1]
        self.assertEqual(seguinte['eventos'], corpo['eventos'][2:4])
        # No number of the store, and a cursor that only this newsroom's own activity moves: seven events in Beta
        # change nothing in what Alfa reads (the row number of the table would jump by seven).
        self.assertEqual(set(primeiro), {'em', 'tipo', 'conta', 'por', 'conta_nome', 'por_nome'})
        for papel in ('editor', 'leitor', 'reporter', 'editor', 'leitor', 'reporter', 'editor'):
            acesso.mudar_papel(self.root, self.ids['reporter_b'], papel, self.ids['dono_b'], self.b)
        self.assertEqual(self.post('dono', 'equipe-atividade', {'limite': 2})[1], pagina)
        acesso.mudar_papel(self.root, self.ids['reporter_b'], 'reporter', self.ids['dono_b'], self.b)
        acesso.definir_responsavel(self.root, 'beta', self.ids['reporter_b'], 'operador', self.b)  # the scenario as it was
        for invalido in ({'limite': 0}, {'limite': 'tudo'}, {'antes': -1}, {'organizacao': self.b}, {'conta': self.ids['dono_b']}):
            self.assertEqual(self.post('dono', 'equipe-atividade', invalido)[0], 400, invalido)
        self.assertNotIn(self.ids['dono'], {e['conta'] for e in self.post('dono_b', 'equipe-atividade', {})[1]['eventos']})

    # --- papel ----------------------------------------------------------------------------------

    def test_mudar_papel_vale_na_requisicao_seguinte_e_mantem_as_apuracoes(self):
        alvo, sessao, _ = self.nova('leitor', casos=('alpha',))
        self.assertEqual(self.post(sessao, 'apuracao-nota-salvar', {'caso': 'alpha'})[0], 403)
        status, corpo, _ = self.post('dono', 'equipe-papel', {'conta': alvo, 'papel': 'editor'})
        self.assertEqual((status, corpo['conta']['papel'], corpo['conta']['casos']), (200, 'editor', ['alpha']))
        conta = self.get(sessao, '/api/sessao')[1]
        self.assertEqual((conta['conta']['papel'], conta['conta']['casos']), ('editor', ['alpha']))
        self.assertIn('redacao-revisar', conta['capacidades'])
        self.assertNotEqual(self.post(sessao, 'apuracao-nota-salvar', {'caso': 'alpha'})[0], 403)  # the same session, the new role
        for papel in ('convidado', 'admin', 'operador', None):
            self.assertEqual(self.post('dono', 'equipe-papel', {'conta': alvo, 'papel': papel})[0], 400, papel)
        self.assertEqual(self.pessoa('dono', alvo)['papel'], 'editor')

    def test_promover_a_dono_e_rebaixar_outro_dono_pedem_a_senha(self):
        alvo, sessao, _ = self.nova('reporter')
        self.recusa('dono', 'equipe-papel', {'conta': alvo, 'papel': 'dono'}, 403, 'senha_necessaria')
        self.recusa('dono', 'equipe-papel', {'conta': alvo, 'papel': 'dono', 'senha': ERRADA}, 403, 'senha_atual_incorreta')
        self.assertEqual(self.pessoa('dono', alvo)['papel'], 'reporter')
        self.assertEqual(self.post(sessao, 'equipe-listar', {})[0], 403)
        self.assertEqual(self.post('dono', 'equipe-papel', {'conta': alvo, 'papel': 'dono', 'senha': SENHA})[0], 200)
        self.assertEqual(self.post(sessao, 'equipe-listar', {})[0], 200)
        # P28, first condition: demoting another dono asks the password of who does it.
        self.recusa('dono', 'equipe-papel', {'conta': alvo, 'papel': 'reporter'}, 403, 'senha_necessaria')
        self.recusa('dono', 'equipe-papel', {'conta': alvo, 'papel': 'reporter', 'senha': ERRADA}, 403, 'senha_atual_incorreta')
        self.assertEqual(self.pessoa('dono', alvo)['papel'], 'dono')
        resposta = self.post('dono', 'equipe-papel', {'conta': alvo, 'papel': 'reporter', 'senha': SENHA})
        self.assertEqual((resposta[0], resposta[1]['conta']['papel']), (200, 'reporter'))
        self.assertNotIn(SENHA, resposta[2].decode('utf-8'))

    def test_a_redacao_nao_fica_sem_dono_ativo(self):
        unico = self.ids['dono_b']
        self.recusa('dono_b', 'equipe-papel', {'conta': unico, 'papel': 'editor', 'senha': SENHA}, 400, 'ultimo_dono')
        self.recusa('dono_b', 'equipe-desativar', {'conta': unico, 'senha': SENHA}, 400, 'ultimo_dono')
        self.assertEqual(self.post('dono_b', 'equipe-remover', {'conta': unico, 'senha': SENHA})[0], 400)  # not here: Minha conta
        self.assertEqual(self.get('dono_b', '/api/sessao')[1]['conta']['papel'], 'dono')

    # --- desativar, reativar, remover -----------------------------------------------------------

    def test_desativar_encerra_as_sessoes_e_para_as_execucoes_e_reativar_devolve_o_acesso(self):
        alvo, sessao, login = self.nova('reporter', casos=('alpha',))
        with patch.object(interface_pesquisa.Handler, '_parar_execucoes') as parar:
            status, corpo, _ = self.post('dono', 'equipe-desativar', {'conta': alvo})
        self.assertEqual((status, corpo['conta']['situacao']), (200, 'desativada'))
        parar.assert_called_once_with(alvo, ())
        self.assertEqual(self.post(sessao, 'codex-status', {})[0], 401)
        self.assertEqual(self.pessoa('dono', alvo)['casos'], ['alpha'])  # the participations are kept
        self.assertEqual(self.post('dono', 'equipe-reativar', {'conta': alvo})[1]['conta']['situacao'], 'ativa')
        acesso.limpar_limites()
        self.assertEqual(self.get(self._entrar(login), '/api/sessao')[1]['conta']['casos'], ['alpha'])

    def test_desativar_outro_dono_pede_a_senha(self):
        alvo, sessao, _ = self.nova('dono')
        self.recusa('dono', 'equipe-desativar', {'conta': alvo}, 403, 'senha_necessaria')
        self.recusa('dono', 'equipe-desativar', {'conta': alvo, 'senha': ERRADA}, 403, 'senha_atual_incorreta')
        self.assertEqual(self.post(sessao, 'codex-status', {})[0], 200)  # still in
        self.assertEqual(self.post('dono', 'equipe-desativar', {'conta': alvo, 'senha': SENHA})[0], 200)
        self.assertEqual(self.post(sessao, 'codex-status', {})[0], 401)

    def test_remover_pede_a_senha_e_a_pessoa_some_da_redacao(self):
        alvo, sessao, login = self.nova('editor', casos=('alpha',))
        self.recusa('dono', 'equipe-remover', {'conta': alvo}, 403, 'senha_necessaria')
        self.recusa('dono', 'equipe-remover', {'conta': alvo, 'senha': ERRADA}, 403, 'senha_atual_incorreta')
        self.assertEqual(self.post(sessao, 'codex-status', {})[0], 200)
        with patch.object(interface_pesquisa.Handler, '_parar_execucoes') as parar:
            status, corpo, bruto = self.post('dono', 'equipe-remover', {'conta': alvo, 'senha': SENHA})
        self.assertEqual((status, corpo), (200, {'conta': {'id': alvo, 'situacao': 'excluida'}}), bruto[:200])
        parar.assert_called_once_with(alvo, ())
        self.assertEqual(self.post(sessao, 'codex-status', {})[0], 401)
        self.assertIsNone(self.pessoa('dono', alvo))
        self.assertNotIn(alvo, {p['id'] for p in self.post('dono', 'caso-participantes', {'caso': 'alpha'})[1]['participantes']})
        acesso.limpar_limites()
        status, _, _ = self.pedir('POST', '/api/entrar', json.dumps({'login': login, 'senha': SENHA}),
                                  {'Content-Type': 'application/json', 'Origin': cenario.ORIGEM})
        self.assertEqual(status, 401)
        # The id that is left answers as an account that does not exist.
        nao_existe = self.post('dono', 'equipe-reativar', {'conta': INEXISTENTE})
        removida = self.post('dono', 'equipe-reativar', {'conta': alvo})
        self.assertEqual((removida[0], removida[2]), (nao_existe[0], nao_existe[2]))

    def test_conta_de_outra_redacao_responde_como_inexistente_com_ou_sem_senha(self):
        de_beta = self.ids['reporter_b']
        for operacao, extra in (('equipe-papel', {'papel': 'dono'}), ('equipe-papel', {'papel': 'leitor'}), ('equipe-desativar', {}),
                                ('equipe-reativar', {}), ('equipe-remover', {}), ('equipe-teto', {'teto_brl': '10'})):
            for senha in ({}, {'senha': ERRADA}, {'senha': SENHA}):
                if operacao in ('equipe-reativar', 'equipe-teto') and senha:
                    continue
                with self.subTest(operacao=operacao, senha=bool(senha)):
                    real = self.post('dono', operacao, {'conta': de_beta, **extra, **senha})
                    falso = self.post('dono', operacao, {'conta': INEXISTENTE, **extra, **senha})
                    self.assertEqual((real[0], real[2]), (falso[0], falso[2]))
                    self.assertEqual((real[0], real[1]['erro']), (400, 'Conta não encontrada.'))
                    self.sem_sentinela(real[2])
        self.assertEqual(self.post('reporter_b', 'codex-status', {})[0], 200)
        self.assertEqual(self.get('reporter_b', '/api/sessao')[1]['conta']['papel'], 'reporter')
        # And a wrong password sent with an account that is not there did not count against anybody.
        self.assertEqual(self.post('dono', 'equipe-papel', {'conta': self.ids['leitor'], 'papel': 'leitor'})[0], 200)

    def test_cinco_senhas_erradas_bloqueiam_as_operacoes_sensiveis_de_quem_errou(self):
        apressado, sessao, _ = self.nova('dono')
        alvo, _, _ = self.nova('leitor')
        for _ in range(acesso.FALHAS_BLOQUEIO):
            self.recusa(sessao, 'equipe-remover', {'conta': alvo, 'senha': ERRADA}, 403, 'senha_atual_incorreta')
        resposta = self.recusa(sessao, 'equipe-remover', {'conta': alvo, 'senha': SENHA}, 429, 'bloqueado')
        self.assertEqual(resposta[1]['estado'], 'bloqueado')
        self.assertIsNotNone(self.pessoa('dono', alvo))
        self.assertEqual(self.post(sessao, 'equipe-listar', {})[0], 200)  # the rest of the session goes on
        self.assertEqual(self.post('dono', 'equipe-remover', {'conta': alvo, 'senha': SENHA})[0], 200)  # another dono is not blocked
        self.assertEqual(self.post('dono', 'equipe-remover', {'conta': apressado, 'senha': SENHA})[0], 200)

    def test_cada_recusa_vai_uma_vez_so_ao_registro_de_auditoria(self):
        alvo, _, _ = self.nova('leitor')
        for quem, operacao, dados, motivo in (
                ('dono', 'equipe-remover', {'conta': alvo, 'senha': ERRADA}, 'senha_incorreta'),
                ('dono', 'equipe-remover', {'conta': alvo}, 'validacao'),
                ('dono_b', 'equipe-desativar', {'conta': self.ids['dono_b'], 'senha': SENHA}, 'ultimo_dono'),
                ('dono', 'equipe-papel', {'conta': INEXISTENTE, 'papel': 'leitor'}, 'validacao')):
            with self.subTest(operacao=operacao, motivo=motivo):
                with patch.object(registro_acesso, 'registrar') as registrar:
                    self.assertIn(self.post(quem, operacao, dados)[0], (400, 403))
                recusas = [c for c in registrar.call_args_list if c.args[0] == 'admin_recusada']
                self.assertEqual([(c.args[2], c.kwargs.get('motivo')) for c in recusas], [(self.ids[quem], motivo)])
        self.assertEqual(self.post('dono', 'equipe-remover', {'conta': alvo, 'senha': SENHA})[0], 200)  # and clears the counter

    # --- tetos ----------------------------------------------------------------------------------

    def test_teto_por_pessoa_e_padrao_da_redacao_ate_o_teto_da_instalacao(self):
        alvo, _, _ = self.nova('reporter')
        maximo = custo.ler_orcamento(self.root)['mensal_organizacao_brl']
        status, corpo, _ = self.post('dono', 'equipe-teto', {'conta': alvo, 'teto_brl': '12.5'})
        self.assertEqual((status, corpo['conta']['teto_mensal_brl']), (200, '12.50'))
        self.assertEqual(self.pessoa('dono', alvo)['teto_mensal_brl'], '12.50')
        self.assertEqual(acesso.tetos_de_custo(self.root, alvo)['pessoa_brl'], '12.50')
        acima = self.post('dono', 'equipe-teto', {'conta': alvo, 'teto_brl': str(int(maximo) + 1)})
        self.assertEqual(acima[0], 400)
        self.assertIn('teto da redação', acima[1]['erro'])
        self.assertEqual(self.post('dono', 'equipe-teto', {'teto_brl': '7'})[1], {'redacao': {'teto_por_pessoa_brl': '7.00'}})
        self.assertEqual(acesso.tetos_de_custo(self.root, self.ids['editor'])['pessoa_brl'], '7.00')
        self.assertIsNone(acesso.tetos_de_custo(self.root, self.ids['reporter_b'])['pessoa_brl'])  # Beta's default is its own
        self.assertEqual(self.post('dono', 'equipe-teto', {'teto_brl': None})[1], {'redacao': {'teto_por_pessoa_brl': None}})
        for invalido in ({}, {'conta': alvo}, {'teto_brl': '-1'}, {'teto_brl': 'muito'}, {'teto_brl': 1.5},
                         {'teto_brl': '5', 'cota_mensal_brl': '999'}, {'teto_brl': '5', 'organizacao': self.b}):
            self.assertEqual(self.post('dono', 'equipe-teto', invalido)[0], 400, invalido)
        self.assertEqual(self.post('dono', 'equipe-listar', {})[1]['redacao']['cota_mensal_brl'], None)  # only the operator sets it

    def test_quem_e_retirado_de_uma_apuracao_tem_as_execucoes_dela_paradas(self):
        # As `contas-atualizar` did before it left: nobody keeps spending the API on a case taken away.
        alvo, _, _ = self.nova('leitor', casos=('alpha', 'gama'))
        with patch.object(interface_pesquisa.Handler, '_parar_execucoes') as parar:
            self.assertEqual(self.post('dono', 'caso-retirar', {'caso': 'alpha', 'conta': alvo})[0], 200)
        parar.assert_called_once_with(alvo, ('gama',))  # what is kept: the cases the account still reaches
        with patch.object(interface_pesquisa.Handler, '_parar_execucoes') as parar:
            self.assertEqual(self.post('dono', 'caso-retirar', {'caso': 'alpha', 'conta': INEXISTENTE})[0], 400)
        parar.assert_not_called()

    def test_campos_fora_da_lista_sao_recusados_sem_efeito(self):
        alvo, _, _ = self.nova('leitor')
        for operacao, dados in (('equipe-papel', {'conta': alvo, 'papel': 'editor', 'organizacao': self.b}),
                                ('equipe-desativar', {'conta': alvo, 'por': self.ids['dono_b']}),
                                ('equipe-reativar', {'conta': alvo, 'senha': SENHA}),
                                ('equipe-listar', {'organizacao': self.b})):
            resposta = self.post('dono', operacao, dados)
            self.assertEqual((resposta[0], resposta[1]['erro']), (400, 'Campos inválidos no pedido de equipe.'), operacao)
        self.assertEqual((self.pessoa('dono', alvo)['papel'], self.pessoa('dono', alvo)['situacao']), ('leitor', 'ativa'))


if __name__ == '__main__':
    unittest.main()
