"""Apagar definitivamente com a senha, num navegador de verdade contra o servidor de verdade (``lixeira-apagar``; contrato de contas, 5.15).

Uma redação só, com login (``local-contas``, como ``test_senha_gestao.py`` e ``test_ia_senha_navegador.py``). O Chromium do Playwright entra como o dono, abre "Apurações e lixeira" e
apaga de vez um item da lixeira (``qa_apagar_senha.cjs``): o diálogo pede o nome e a senha, a senha errada fica no campo da senha com o nome digitado, Cancelar não apaga nada, seis
pedidos com o nome errado respondem ``nome_confirmacao_divergente`` e NÃO contam tentativa (a conta segue livre) e a senha certa conclui. Quatro passagens (duas telas, dois temas),
um item da lixeira por passagem. Aqui se confere o que ficou no disco: os itens apagados saíram da lixeira e a senha digitada não está em nenhum arquivo de texto da instalação.
Com ``VLADO_CAPTURAS=<pasta>`` grava os PNGs do Design. Sem Node ou sem o Playwright, o teste é pulado. Sem modelo e sem rede.
"""
import json
import os
from pathlib import Path
import shutil
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
import apagamento
from criar_caso import criar_caso
from interface_pesquisa import Servidor
import lixeira
from test_acesso import SENHA, hasher_rapido

PASSAGENS = 4


@requer_navegador_node
class ApagarComSenhaNoNavegadorTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copy(RAIZ / 'configuracao.json', self.root / 'configuracao.json')  # criar_caso lê os limites da configuração do projeto
        env = patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': '', 'ANTHROPIC_API_KEY': '',
                                      'OPENAI_API_KEY': '', 'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        hasher_rapido(self)
        acesso.limpar_limites()
        conta = acesso.criar_primeiro_admin(self.root, 'Editora', 'editora', SENHA)
        arquivo = self.root / 'alfa.txt'
        arquivo.write_text('Alfa sintético. Valor 123.\n', encoding='utf-8')
        criar_caso(self.root, 'alfa', 'Pauta Alfa', [arquivo], 'sinteticos')
        acesso.atribuir_caso(self.root, 'alfa', conta['organizacao'])
        # Uma rodada que nunca rodou por passagem: nada do caso fica escondido por ela, e cada passagem apaga a sua.
        self.itens = [lixeira.adicionar(self.root, 'rodada', 'alfa', f'R90{i}', rodada=f'R90{i}')['id'] for i in range(PASSAGENS)]
        self.addCleanup(apagamento.aguardar, 60)
        self.server = Servidor(('127.0.0.1', 0), self.root, modo='local-contas')
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def test_apagar_de_vez_pede_nome_e_senha_pelo_navegador(self):
        porta = self.server.server_port
        entrada = {'porta': porta, 'origem': f'http://127.0.0.1:{porta}', 'login': 'editora', 'senha': SENHA}
        if os.environ.get('VLADO_CAPTURAS'):
            entrada['capturas'] = os.environ['VLADO_CAPTURAS']
        # Quatro passagens, cada uma com a conta entrando de novo e uma senha errada: sob o teto de erros seguidos (cinco) e do endereço.
        with patch.object(acesso, 'TENTATIVAS_IP_MINUTO', 10000):
            processo = subprocess.run(['node', str(Path(__file__).with_name('qa_apagar_senha.cjs')), json.dumps(entrada)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=480, cwd=RAIZ)
        self.assertEqual(processo.returncode, 0, (processo.stdout + processo.stderr)[-3000:])
        self.assertEqual(len(json.loads(processo.stdout.strip().splitlines()[-1])), PASSAGENS)
        apagamento.aguardar(60)
        restantes = {item['id'] for item in lixeira.ativos(self.root)}
        self.assertEqual(restantes & set(self.itens), set(), 'os quatro itens foram apagados de vez')
        achados = []
        for arquivo in self.root.rglob('*'):
            if arquivo.is_file() and arquivo.suffix in ('.json', '.jsonl', '.txt', '.log', '.md', '.csv'):
                if SENHA in arquivo.read_text(encoding='utf-8', errors='ignore'):
                    achados.append(str(arquivo.relative_to(self.root)))
        self.assertEqual(achados, [], 'a senha digitada nunca é gravada')


if __name__ == '__main__':
    unittest.main()
