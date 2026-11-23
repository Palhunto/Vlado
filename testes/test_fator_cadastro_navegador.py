"""O cadastro do segundo fator em Minha conta, num navegador de verdade contra o servidor de verdade (``conta-fator-*``; contrato de contas, 5.4 e 8.2; docs/design/componentes.md#segundo-fator).

O servidor de ``cenario_redacoes`` (modo ``piloto``) tem as contas da redação Alfa; o Chromium do Playwright entra como a repórter e como a dona (``qa_fator_cadastro.cjs``), cadastra o
fator pelos três passos (o código do aplicativo é calculado no navegador a partir da chave que a tela mostra, RFC 6238), vê os dez códigos de reserva uma vez (19 caracteres) e confere que
nem eles nem a chave ficam na página ou no armazenamento depois de "Já guardei"; gera novos códigos e remove o fator (a repórter pode). A dona, que não tem a capacidade de remover,
cadastra, não vê "Remover" e tem o pedido feito à mão recusado pelo servidor (403 operacao_proibida). Aqui se confere o que o servidor guardou: o fator ligado ou removido, os códigos
de reserva que valem (os novos) e os que deixaram de valer (os antigos), e que a senha não está em nenhum arquivo de texto da instalação. Sem Node ou sem o Playwright, o teste é pulado.
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
import fator_de_teste
import segundo_fator as fator
from test_acesso import SENHA

PLAYWRIGHT = RAIZ / '.ferramentas' / 'node' / 'node_modules' / 'playwright'


@unittest.skipUnless(shutil.which('node') and PLAYWRIGHT.is_dir(), 'precisa do Node e do Playwright em .ferramentas/node')
class CadastroDoFatorNoNavegadorTest(cenario.DuasRedacoes):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = patch.dict(os.environ, {'VLADO_SEGREDOS': ''})
        env.start()
        cls.addClassCleanup(env.stop)
        fator._CHAVES.clear()
        cls.addClassCleanup(fator._CHAVES.clear)

    def estado_do_fator(self, chave):
        return acesso.ver_conta(self.root, self.ids[chave])['segundo_fator']

    def entra_com_reserva(self, login, codigo):
        """Sign in with the password and a reserve code (the second step); returns whether it let the person in."""
        acesso.limpar_limites()
        try:
            acesso.entrar(self.root, login, SENHA)
        except acesso.PedeSegundoFator as pede:
            try:
                acesso.entrar_segundo_fator(self.root, pede.bilhete, codigo)
            except (acesso.CodigoInvalido, acesso.EntradaExpirada):
                return False
            return True
        return False

    def test_cadastrar_gerar_e_remover_pelo_navegador(self):
        acesso.limpar_limites()
        entrada = {'porta': self.server.server_port, 'origem': cenario.ORIGEM, 'senha': SENHA,
                   'reporter': {'login': 'rita.reporter'},
                   # A dona já tem o segundo fator (obrigatório para o dono no piloto; o cenário o cadastra): ela entra com um código de reserva
                   'dono': {'login': 'dona.alfa', 'codigos': [fator_de_teste.codigo(self.root, self.ids['dono']) for _ in range(2)]}}
        # Duas contas, cada uma com o cadastro, e a conta entrando de novo e errando uma senha antes de acertar: sob o teto de erros seguidos.
        with patch.object(acesso, 'TENTATIVAS_IP_MINUTO', 10000), correio.usar('simulado'):
            processo = subprocess.run(['node', str(Path(__file__).with_name('qa_fator_cadastro.cjs')), json.dumps(entrada)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=420, cwd=RAIZ)
            correio.aguardar()
        self.assertEqual(processo.returncode, 0, (processo.stdout + processo.stderr)[-3000:])
        resultado = json.loads(processo.stdout.strip().splitlines()[-1])

        # A repórter removeu o fator no fim: nada ficou ligado.
        self.assertFalse(self.estado_do_fator('reporter')['ativo'], 'o fator da repórter foi removido')
        # A dona segue com o fator ligado (a tela não tem como removê-lo e o pedido feito à mão foi recusado pelo servidor).
        self.assertTrue(self.estado_do_fator('dono')['ativo'], 'o fator da dona continua ligado')
        # O código de reserva que ela usou para entrar valeu uma vez só.
        usado = entrada['dono']['codigos'][0]
        self.assertFalse(self.entra_com_reserva('dona.alfa', usado), 'o código de reserva usado não entra de novo')
        # Nenhum arquivo de texto da instalação guarda a senha, a chave em claro ou um código de reserva em claro.
        proibidos = [SENHA, resultado['reporter']['segredo'], *resultado['reporter']['codigos'], *resultado['reporter']['novos']]
        achados = []
        for arquivo in self.root.rglob('*'):
            if arquivo.is_file() and arquivo.suffix in ('.json', '.jsonl', '.txt', '.log', '.md', '.csv'):
                texto = arquivo.read_text(encoding='utf-8', errors='ignore')
                achados += [f'{arquivo.relative_to(self.root)}: {p[:8]}…' for p in proibidos if p in texto]
        self.assertEqual(achados, [], 'a senha, a chave e os códigos não ficam em arquivo de texto')


if __name__ == '__main__':
    unittest.main()
