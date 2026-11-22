"""A lista de capacidades por papel que os testes da interface usam (``testes/fixtures/capacidades_por_papel.json``) é a do servidor.

``papeis.cjs`` esconde e mostra controles pelas ``capacidades`` de ``GET /api/sessao``; se a matriz de ``autorizacao.py`` mudar,
este teste falha e o arquivo se refaz com ``autorizacao.capacidades`` de cada papel. Sem modelo e sem rede.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import autorizacao

ARQUIVO = Path(__file__).resolve().parent / 'fixtures' / 'capacidades_por_papel.json'


class CapacidadesFixtureTest(unittest.TestCase):
    def test_o_arquivo_e_a_lista_do_servidor_para_cada_papel(self):
        esperado = {papel: autorizacao.capacidades({'papel': papel}) for papel in autorizacao.PAPEIS}
        self.assertEqual(json.loads(ARQUIVO.read_text(encoding='utf-8')), esperado,
                         'refaça testes/fixtures/capacidades_por_papel.json com autorizacao.capacidades de cada papel')

    def test_os_papeis_diferem_nas_operacoes_que_a_interface_esconde(self):
        dados = json.loads(ARQUIVO.read_text(encoding='utf-8'))
        for operacao, quem in (('cadastrar', {'dono', 'reporter'}), ('caderno-salvar', {'dono', 'editor', 'reporter'}), ('ia-config', {'dono'})):
            self.assertEqual({papel for papel, lista in dados.items() if operacao in lista}, quem, operacao)


if __name__ == '__main__':
    unittest.main()
