"""Salvar e remover a chave de IA com a senha, num navegador de verdade contra o servidor de verdade (``ia-config-salvar``; contrato de contas, 5.15).

Uma redação só, com login (``local-contas``, como ``test_senha_gestao.py``): numa instalação com mais de uma redação a chave do serviço não se troca pela
Mesa. O Chromium do Playwright entra como o dono, abre Configurações (o painel do provedor e da chave da IA, P43) e salva e remove a chave (``qa_ia_senha.cjs``): o servidor recusa
sem a senha, o diálogo a pede, a senha errada fica no campo, cancelar não envia nada e a senha certa conclui. Aqui se confere o que ficou guardado: a
chave de teste sumiu depois de removida e a senha não está em nenhum arquivo de texto da instalação. Com ``VLADO_CAPTURAS=<pasta>`` grava os PNGs do
Design. Sem Node ou sem o Playwright, o teste é pulado. Sem modelo e sem rede.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from auxiliar_node import requer_navegador_node
import acesso
from comum import escrever_json
from interface_pesquisa import Servidor
import segredos
from test_acesso import SENHA, hasher_rapido



@requer_navegador_node
class IaComSenhaNoNavegadorTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        escrever_json(self.root / 'configuracao.json', {'provedor': 'anthropic', 'modelo_preferido': None, 'max_tokens_saida': 4096})
        env = patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': '', 'ANTHROPIC_API_KEY': '',
                                      'OPENAI_API_KEY': '', 'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        hasher_rapido(self)
        acesso.limpar_limites()
        acesso.criar_primeiro_admin(self.root, 'Editora', 'editora', SENHA)
        self.server = Servidor(('127.0.0.1', 0), self.root, modo='local-contas')
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def test_salvar_e_remover_a_chave_pedem_a_senha_pelo_navegador(self):
        porta = self.server.server_port
        entrada = {'porta': porta, 'origem': f'http://127.0.0.1:{porta}', 'login': 'editora', 'senha': SENHA}
        if os.environ.get('VLADO_CAPTURAS'):
            entrada['capturas'] = os.environ['VLADO_CAPTURAS']
        # Quatro passagens (duas telas, dois temas), cada uma com a conta entrando de novo e uma senha errada: sob o teto de erros seguidos.
        with patch.object(acesso, 'TENTATIVAS_IP_MINUTO', 10000):
            processo = subprocess.run(['node', str(Path(__file__).with_name('qa_ia_senha.cjs')), json.dumps(entrada)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=420, cwd=RAIZ)
        self.assertEqual(processo.returncode, 0, (processo.stdout + processo.stderr)[-3000:])
        self.assertEqual(len(json.loads(processo.stdout.strip().splitlines()[-1])), 4)
        for provedor in ('anthropic', 'openai'):
            self.assertIsNone(segredos.ler_chave(self.root, provedor), f'a chave de teste de {provedor} foi removida')
        achados = []
        for arquivo in self.root.rglob('*'):
            if arquivo.is_file() and arquivo.suffix in ('.json', '.jsonl', '.txt', '.log', '.md', '.csv'):
                if SENHA in arquivo.read_text(encoding='utf-8', errors='ignore'):
                    achados.append(str(arquivo.relative_to(self.root)))
        self.assertEqual(achados, [], 'a senha digitada nunca é gravada')


if __name__ == '__main__':
    unittest.main()
