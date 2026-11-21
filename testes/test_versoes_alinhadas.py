"""Uma versão por release (P8): aplicação, imagem Docker e instalador têm de ser iguais.

Não inclui versões de formato de arquivo (acesso, achados, rascunhos) nem `versao_prompts`.
"""
from pathlib import Path
import json
import re
import unittest

RAIZ = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r'\d+\.\d+\.\d+')


def versoes():
    encontradas = {'configuracao.json': json.loads((RAIZ / 'configuracao.json').read_text(encoding='utf-8'))['versao'],
                   'instalador/dependencias.json': json.loads(
                       (RAIZ / 'instalador' / 'dependencias.json').read_text(encoding='utf-8'))['versao_vlado']}
    iss = (RAIZ / 'instalador' / 'vlado.iss').read_text(encoding='utf-8')
    encontradas['instalador/vlado.iss'] = re.search(r'#define Versao "([^"]+)"', iss).group(1)
    for arquivo in [RAIZ / '.env.example', *sorted((RAIZ / 'deploy' / 'ambientes').glob('*.env.example'))]:
        linhas = re.findall(r'^VLADO_VERSAO=(.*)$', arquivo.read_text(encoding='utf-8'), re.M)
        if len(linhas) != 1:
            raise AssertionError(f'{arquivo.name}: esperada exatamente uma linha VLADO_VERSAO=, achei {len(linhas)}')
        encontradas[arquivo.relative_to(RAIZ).as_posix()] = linhas[0].strip()
    return encontradas


class VersoesAlinhadasTest(unittest.TestCase):
    def test_todas_iguais(self):
        encontradas = versoes()
        self.assertEqual(len(set(encontradas.values())), 1, f'Versões divergentes: {encontradas}')

    def test_formato_numerico(self):
        for arquivo, versao in versoes().items():
            self.assertIsNotNone(SEMVER.fullmatch(versao), f'{arquivo}: {versao!r} não é X.Y.Z')


if __name__ == '__main__':
    unittest.main()
