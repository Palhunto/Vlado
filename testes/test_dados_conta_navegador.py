"""Seus dados em Minha conta, num navegador de verdade contra o servidor de verdade (``conta-exportar`` e ``conta-excluir``; contrato de contas, 12, entrega 4b; docs/design/componentes.md#minha-conta).

O servidor de ``cenario_redacoes`` (modo ``piloto``) tem a redação Alfa, com termos de uso vigentes (``VLADO_TERMOS_VERSAO`` e ``VLADO_TERMOS_ENDERECO``) já aceitos pelas contas do teste. O
Chromium do Playwright (``qa_dados_conta.cjs``) entra como a repórter: vê a versão dos termos e o link, baixa o arquivo (nome com a data, formato ``vlado-meus-dados``, sem a senha, com o que
``incompleto`` diz que ainda não traz) e exclui a própria conta (senha errada no campo da senha; certa, a Mesa vai ao Entrar com o aviso e o cookie some). Como a única dona da redação, tenta
excluir e recebe a razão do último dono; o pedido feito à mão com outro nome é recusado antes da senha. Aqui se confere o que o servidor guardou: a conta excluída não entra mais, a dona
segue, e a senha não está em nenhum arquivo de texto. Com ``VLADO_CAPTURAS`` apontando uma pasta, o roteiro grava também as capturas de 375 e 1440 px nos dois temas. Sem Node ou sem o Playwright,
o teste é pulado. Sem modelo e sem rede.
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
import fator_de_teste
from test_acesso import SENHA

PLAYWRIGHT = RAIZ / '.ferramentas' / 'node' / 'node_modules' / 'playwright'
VERSAO, ENDERECO = '2026-12-01', 'https://vlado.test/termos'


@unittest.skipUnless(shutil.which('node') and PLAYWRIGHT.is_dir(), 'precisa do Node e do Playwright em .ferramentas/node')
class SeusDadosNoNavegadorTest(cenario.DuasRedacoes):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = patch.dict(os.environ, {'VLADO_SEGREDOS': '', 'VLADO_TERMOS_VERSAO': VERSAO, 'VLADO_TERMOS_ENDERECO': ENDERECO})
        env.start()
        cls.addClassCleanup(env.stop)

    def test_exportar_e_excluir_pelo_navegador(self):
        acesso.limpar_limites()
        vigentes = acesso.termos_vigentes()
        for chave in ('reporter', 'dono'):  # quem já aceitou a versão vigente não tem a pendência dos termos
            acesso.aceitar_termos(self.root, self.ids[chave], VERSAO, vigentes)
        entrada = {'porta': self.server.server_port, 'origem': cenario.ORIGEM, 'senha': SENHA, 'versao': VERSAO, 'endereco': ENDERECO,
                   'reporter': {'login': 'rita.reporter', 'nome': 'Rita Reporter'}, 'dono': {'login': 'dona.alfa', 'nome': 'Dona Alfa',
                           # No piloto a dona tem o segundo fator: um código de reserva a cada entrada (a página do Entrar com o passo 2 é do Lume)
                           'codigos': [fator_de_teste.codigo(self.root, self.ids['dono']) for _ in range(6)]}}
        if os.environ.get('VLADO_CAPTURAS'):
            entrada['capturas'] = os.environ['VLADO_CAPTURAS']
        with patch.object(acesso, 'TENTATIVAS_IP_MINUTO', 10000), correio.usar('simulado'):
            processo = subprocess.run(['node', str(Path(__file__).with_name('qa_dados_conta.cjs')), json.dumps(entrada)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=420, cwd=RAIZ)
            correio.aguardar()
        self.assertEqual(processo.returncode, 0, (processo.stdout + processo.stderr)[-3000:])
        resultado = json.loads(processo.stdout.strip().splitlines()[-1])
        self.assertEqual(resultado['exportado']['incompleto'], ['conversas_anteriores'])

        # A repórter excluiu a conta: a senha certa já não a deixa entrar. A dona, que não saiu, segue.
        acesso.limpar_limites()
        with self.assertRaises(Exception) as cai:
            acesso.entrar(self.root, 'rita.reporter', SENHA)
        self.assertNotIsInstance(cai.exception, acesso.PedeSegundoFator)
        acesso.limpar_limites()
        with self.assertRaises(acesso.PedeSegundoFator):  # a senha da dona vale: falta só o segundo passo
            acesso.entrar(self.root, 'dona.alfa', SENHA)
        # A senha não está em nenhum arquivo de texto da instalação.
        achados = []
        for arquivo in self.root.rglob('*'):
            if arquivo.is_file() and arquivo.suffix in ('.json', '.jsonl', '.txt', '.log', '.md', '.csv'):
                if SENHA in arquivo.read_text(encoding='utf-8', errors='ignore'):
                    achados.append(str(arquivo.relative_to(self.root)))
        self.assertEqual(achados, [], 'a senha não fica em arquivo de texto')


if __name__ == '__main__':
    unittest.main()
