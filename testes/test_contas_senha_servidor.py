"""A tela antiga "Contas de acesso" (piloto.js) contra o servidor de verdade (``POST /api/contas-*``; contrato de contas, 5.15).

As operações que o diálogo da senha reenvia (recuperar, desativar dono, promover a dono; criar dono, quando a instalação permitir criar) recusam sem o campo ``senha``
(403 ``senha_necessaria``), recusam a senha errada (403 ``senha_atual_incorreta``) e passam com a senha de quem age. Os códigos
são os que ``Dialogo.comSenha`` (dialogo.js) espera. As regras do armazenamento estão em ``test_acesso.py``; a tela Equipe, em ``test_equipe.py``.
Sem modelo e sem rede.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
from test_acesso import SENHA

ERRADA = 'senha-errada-de-teste'


class ContasSenhaTest(cenario.DuasRedacoes):
    numero = 0

    def nova(self, papel):
        """A fresh active account of Alfa: (id, login)."""
        type(self).numero += 1
        login = f'{papel}.senha{self.numero}'
        conta, token = acesso.criar_conta(self.root, f'Pessoa Senha {self.numero}', login, papel=papel, organizacao=self.a, por='operador')
        acesso.ativar(self.root, token, SENHA)
        acesso.limpar_limites()
        return conta['id'], login

    def recusa(self, operacao, dados, codigo):
        status, corpo, bruto = self.post('dono', operacao, dados)
        self.assertEqual((status, corpo.get('codigo')), (403, codigo), bruto[:200])

    def situacao(self, cid):
        return next(c for c in self.post('dono', 'contas-listar', {})[1]['contas'] if c['id'] == cid)

    def test_recuperar_recusa_sem_senha_e_com_a_errada_e_passa_com_a_certa(self):
        alvo, _ = self.nova('reporter')
        self.recusa('contas-recuperar', {'id': alvo}, 'senha_necessaria')
        self.recusa('contas-recuperar', {'id': alvo, 'senha': ERRADA}, 'senha_atual_incorreta')
        status, corpo, bruto = self.post('dono', 'contas-recuperar', {'id': alvo, 'senha': SENHA})
        self.assertEqual(status, 200, bruto[:200])
        self.assertTrue(corpo['link'])
        self.assertEqual(self.situacao(alvo)['situacao'], 'aguardando_senha')

    def test_criar_conta_nesta_instalacao_e_recusada_antes_de_pedir_a_senha(self):
        # Nesta instalação as contas novas vêm de quem a administra: a recusa vem sem pedir a senha, e o diálogo não abre à toa
        # (por isso piloto.js envia o pedido primeiro). Quando o convite por e-mail entrar, a regra da senha do dono vale (contrato, 5.15).
        dados = {'nome': 'Caio Dono', 'login': 'caio.dono.senha', 'papel': 'admin', 'horas': 72}
        status, corpo, bruto = self.post('dono', 'contas-criar', dados)
        self.assertEqual((status, corpo.get('codigo')), (403, 'operacao_proibida'), bruto[:200])

    def test_desativar_outro_dono_pede_a_senha_e_desativar_um_reporter_nao(self):
        outro, _ = self.nova('dono')
        self.recusa('contas-desativar', {'id': outro}, 'senha_necessaria')
        self.recusa('contas-desativar', {'id': outro, 'senha': ERRADA}, 'senha_atual_incorreta')
        self.assertTrue(self.situacao(outro)['ativa'])
        self.assertEqual(self.post('dono', 'contas-desativar', {'id': outro, 'senha': SENHA})[0], 200)
        self.assertFalse(self.situacao(outro)['ativa'])
        reporter, _ = self.nova('reporter')
        self.assertEqual(self.post('dono', 'contas-desativar', {'id': reporter})[0], 200)

    def test_promover_a_dono_pede_a_senha(self):
        alvo, _ = self.nova('reporter')
        self.recusa('contas-atualizar', {'id': alvo, 'papel': 'dono'}, 'senha_necessaria')
        self.recusa('contas-atualizar', {'id': alvo, 'papel': 'dono', 'senha': ERRADA}, 'senha_atual_incorreta')
        self.assertEqual(self.situacao(alvo)['papel'], 'reporter')
        self.assertEqual(self.post('dono', 'contas-atualizar', {'id': alvo, 'papel': 'dono', 'senha': SENHA})[0], 200)
        self.assertIn(self.situacao(alvo)['papel'], ('admin', 'dono'))  # a listagem ainda mostra o dono como `admin`


if __name__ == '__main__':
    unittest.main()
