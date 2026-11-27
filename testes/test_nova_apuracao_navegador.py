"""A Nova apuração no modo hospedado, num navegador de verdade contra o servidor de verdade.

A repórter de ``cenario_redacoes`` (modo ``piloto``) entra no Chromium do Playwright, cria a apuração pelo passo 1 e pelo primeiro envio, e o cabeçalho
(seletor do topo e subtítulo) tem de dizer o nome da apuração em cada momento do passo 3, nunca o identificador (``qa_nova_apuracao_hospedada.cjs``).
Aqui se confere o que o servidor guardou: uma apuração só, da repórter e da redação dela, com o título digitado. Sem Node ou sem o Playwright, o teste é
pulado. Sem modelo e sem rede.
"""
import json
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
from test_acesso import SENHA



@requer_navegador_node
class NovaApuracaoNoNavegadorTest(cenario.DuasRedacoes):
    def test_o_cabecalho_diz_o_nome_da_apuracao_nova_no_passo_3(self):
        acesso.limpar_limites()
        entrada = {'porta': self.server.server_port, 'origem': cenario.ORIGEM, 'login': 'rita.reporter', 'senha': SENHA}
        with patch.object(acesso, 'TENTATIVAS_IP_MINUTO', 10000):
            processo = subprocess.run(['node', str(Path(__file__).with_name('qa_nova_apuracao_hospedada.cjs')), json.dumps(entrada)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=420, cwd=RAIZ)
        self.assertEqual(processo.returncode, 0, (processo.stdout + processo.stderr)[-3000:])
        titulo = json.loads(processo.stdout.strip().splitlines()[-1])['ok']
        catalogo = self.get('reporter', '/api/catalogo')[1]['casos']
        criadas = [c for c in catalogo if c['titulo'] == titulo]
        self.assertEqual(len(criadas), 1, 'uma apuração só')
        registro = acesso.posse(self.root, criadas[0]['id'])
        self.assertEqual((registro['organizacao'], registro['responsavel']), (self.a, self.ids['reporter']))


if __name__ == '__main__':
    unittest.main()
