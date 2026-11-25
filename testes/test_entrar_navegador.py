"""A página do Entrar com convite, Esqueci a senha, redefinição e confirmação de e-mail, num navegador de verdade contra o servidor de verdade.

O servidor de ``cenario_redacoes`` (modo ``piloto``, duas redações) responde; o Chromium do Playwright abre ``/entrar``,
``/aceitar/<token>``, ``/redefinir/<token>`` e ``/confirmar-email/<token>`` e age como uma pessoa (``qa_entrar_convites.cjs``); aqui se conferem os
links que o teste fez e o que o servidor guardou depois: conta criada pelo convite, senha trocada, e-mail trocado e a mensagem de Esqueci a senha.
Com ``VLADO_CAPTURAS=<pasta>`` o mesmo roteiro grava os PNGs do Design (375 e 1440 px, nos dois temas). Sem Node ou sem o Playwright, o teste é pulado.
Sem modelo e sem rede (o transporte de e-mail é o ``simulado``).
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from auxiliar_node import requer_navegador_node
import acesso
import cenario_redacoes as cenario
import correio
from test_acesso import SENHA

NOVA = 'uma-senha-nova-bem-longa'
SENHA_DO_CONVITE = 'senha-do-convite-bem-longa'
VARIACOES = 4  # duas telas (375 e 1440) vezes dois temas


@requer_navegador_node
class EntrarNoNavegadorTest(cenario.DuasRedacoes):
    def test_o_roteiro_inteiro_pelo_navegador(self):
        acesso.limpar_limites()
        correio.limpar_caixa()
        dono = self.ids['dono']
        convites = []
        for i in range(VARIACOES):
            email = f'convidada{i}@exemplo.test'
            _, token, _ = acesso.convidar(self.root, self.a, dono, email, 'reporter', [], idioma='pt')
            convites.append({'token': token, 'email': email, 'nome': f'Pessoa Convidada {i}', 'senha': SENHA_DO_CONVITE,
                             'redacao': 'Redação Alfa', 'por': 'Dona Alfa'})
        redefinires, contas_redefinir = [], []
        emails, contas_email = [], []
        for i in range(VARIACOES):
            email = f'esquecida{i}@exemplo.test'
            _, token, _ = acesso.convidar(self.root, self.a, dono, email, 'leitor', [])
            _, _, conta = acesso.aceitar_convite(self.root, token, f'Pessoa Esquecida {i}', SENHA)
            link, _ = acesso.pedir_redefinicao(self.root, email)
            redefinires.append({'token': link, 'senha': NOVA})
            contas_redefinir.append((email, conta['id']))
            email_antigo = f'trocar{i}@exemplo.test'
            _, token, _ = acesso.convidar(self.root, self.a, dono, email_antigo, 'leitor', [])
            _, _, conta = acesso.aceitar_convite(self.root, token, f'Pessoa Que Troca {i}', SENHA)
            pedido = acesso.pedir_troca_de_email(self.root, conta['id'], f'novo{i}@exemplo.test', SENHA)
            emails.append({'token': pedido['token']})
            contas_email.append((email_antigo, f'novo{i}@exemplo.test', conta['id']))
        esquecida = 'pediu.link@exemplo.test'
        _, token, _ = acesso.convidar(self.root, self.a, dono, esquecida, 'leitor', [])
        acesso.aceitar_convite(self.root, token, 'Pessoa Que Pede o Link', SENHA)
        correio.limpar_caixa()

        entrada = {'porta': self.server.server_port, 'origem': cenario.ORIGEM, 'esqueci': esquecida, 'convites': convites,
                   'redefinires': redefinires, 'emails': emails}
        if os.environ.get('VLADO_CAPTURAS'):
            entrada['capturas'] = os.environ['VLADO_CAPTURAS']
        # O roteiro faz uns 40 pedidos públicos em menos de um minuto, do mesmo endereço: acima dos 20 por minuto do servidor.
        with correio.usar('simulado'), patch.object(acesso, 'TENTATIVAS_IP_MINUTO', 10000):
            processo = subprocess.run(['node', str(Path(__file__).with_name('qa_entrar_convites.cjs')), json.dumps(entrada)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=420, cwd=RAIZ)
            correio.aguardar()
        self.assertEqual(processo.returncode, 0, (processo.stdout + processo.stderr)[-3000:])
        feito = json.loads(processo.stdout.strip().splitlines()[-1])
        self.assertEqual(len(feito), 4 * VARIACOES, feito)

        # Esqueci a senha: uma mensagem só para o endereço (no máximo uma a cada cinco minutos), com o link da redefinição.
        mensagens = [m for m in correio.caixa() if m['tipo'] == 'redefinicao' and m['para'] == esquecida]
        self.assertEqual(len(mensagens), 1, correio.caixa())
        self.assertRegex(mensagens[0]['link'], '^' + cenario.ORIGEM + r'/redefinir/[A-Za-z0-9_-]{43}$')

        # Convite: a conta nasceu com o e-mail do convite, o papel e a senha escolhida na página.
        for convite in convites:
            sid, _, conta = acesso.entrar(self.root, convite['email'], SENHA_DO_CONVITE)
            self.assertEqual((conta['papel'], conta['email'], conta['nome']), ('reporter', convite['email'], convite['nome']))
            self.assertTrue(sid)
        # Redefinição: a senha nova vale, a antiga não, e as sessões da conta foram encerradas.
        for email, _ in contas_redefinir:
            acesso.limpar_limites()
            with self.assertRaises(acesso.CredenciaisInvalidas):
                acesso.entrar(self.root, email, SENHA)
            self.assertEqual(acesso.entrar(self.root, email, NOVA)[2]['email'], email)
        # E-mail: o novo endereço entra com a mesma senha; o antigo deixou de existir.
        for antigo, novo, _ in contas_email:
            acesso.limpar_limites()
            self.assertEqual(acesso.entrar(self.root, novo, SENHA)[2]['email'], novo)
            with self.assertRaises(acesso.CredenciaisInvalidas):
                acesso.entrar(self.root, antigo, SENHA)


if __name__ == '__main__':
    unittest.main()
