"""O segundo fator no Entrar e na redefinição, num navegador de verdade contra o servidor de verdade (contrato de contas, 5.3, 5.4 e 8.2; docs/design/componentes.md#entrar-fator).

O servidor de ``cenario_redacoes`` (modo ``piloto``) tem contas com o fator cadastrado; o Chromium do Playwright entra com a senha, vê o passo 2, erra e acerta o código
do aplicativo (calculado no navegador, RFC 6238), entra com um código de reserva que vale uma vez, e redefine a senha de uma conta com fator pedindo o código
(``qa_entrar_fator.cjs``). Aqui se confere o que o servidor guardou: a senha nova só vale depois do passo 2. Sem Node ou sem o Playwright, o teste é pulado.
Sem modelo e sem rede.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
import correio
import segundo_fator as fator
from test_acesso import SENHA
from test_fator_contas import cadastrar, codigo_de

PLAYWRIGHT = RAIZ / '.ferramentas' / 'node' / 'node_modules' / 'playwright'
NOVA = 'uma-senha-nova-bem-longa'


@unittest.skipUnless(shutil.which('node') and PLAYWRIGHT.is_dir(), 'precisa do Node e do Playwright em .ferramentas/node')
class EntrarComFatorNoNavegadorTest(cenario.DuasRedacoes):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = patch.dict(os.environ, {'VLADO_SEGREDOS': ''})
        env.start()
        cls.addClassCleanup(env.stop)
        fator._CHAVES.clear()
        cls.addClassCleanup(fator._CHAVES.clear)

    def conta(self, email, nome):
        _, token, _ = acesso.convidar(self.root, self.a, self.ids['dono'], email, 'leitor', [])
        _, _, conta = acesso.aceitar_convite(self.root, token, nome, SENHA)
        return conta['id']

    def test_o_roteiro_pelo_navegador(self):
        acesso.limpar_limites()
        correio.limpar_caixa()
        com_app = self.conta('com.app@exemplo.test', 'Pessoa Com App')
        segredo_app, _ = cadastrar(self.root, com_app)
        com_reserva = self.conta('com.reserva@exemplo.test', 'Pessoa Com Reserva')
        _, reservas = cadastrar(self.root, com_reserva)
        a_redefinir = self.conta('redefine@exemplo.test', 'Pessoa Que Redefine')
        segredo_redefinir, _ = cadastrar(self.root, a_redefinir)
        token, _ = acesso.pedir_redefinicao(self.root, 'redefine@exemplo.test')
        entrada = {'porta': self.server.server_port, 'origem': cenario.ORIGEM, 'senha': SENHA,
                   'app': {'email': 'com.app@exemplo.test', 'segredo': segredo_app},
                   'reserva': {'email': 'com.reserva@exemplo.test', 'codigo': reservas[0]},
                   'redefinir': {'token': token, 'segredo': segredo_redefinir, 'senha_nova': NOVA}}
        if os.environ.get('VLADO_CAPTURAS'):
            entrada['capturas'] = os.environ['VLADO_CAPTURAS']
        with patch.object(acesso, 'TENTATIVAS_IP_MINUTO', 10000), correio.usar('simulado'):
            processo = subprocess.run(['node', str(Path(__file__).with_name('qa_entrar_fator.cjs')), json.dumps(entrada)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=420, cwd=RAIZ)
            correio.aguardar()
        self.assertEqual(processo.returncode, 0, (processo.stdout + processo.stderr)[-3000:])
        self.assertEqual(json.loads(processo.stdout.strip().splitlines()[-1]), {'app': 'ok', 'reserva': 'ok', 'redefinir': 'ok'})
        # A senha nova vale, e a entrada com ela ainda pede o segundo passo.
        acesso.limpar_limites()
        with self.assertRaises(acesso.PedeSegundoFator):
            acesso.entrar(self.root, 'redefine@exemplo.test', NOVA)
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'redefine@exemplo.test', SENHA)


if __name__ == '__main__':
    unittest.main()
