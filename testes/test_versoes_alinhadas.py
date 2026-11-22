"""Uma versão por release (P8): aplicação, imagem Docker e instalador têm de ser iguais.

Não inclui versões de formato de arquivo (acesso, achados, rascunhos) nem `versao_prompts`.
"""
from pathlib import Path
import json
import re
import unittest

RAIZ = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r'\d+\.\d+\.\d+')
# O ambiente local do dono (deploy/LOCAL.md) não é release: ele constrói uma imagem para o computador dele, com etiqueta
# própria `local-*`, para nunca regravar `vlado:local` (a da homologação). A P8 (uma versão por release) vale para as imagens
# publicadas; este arquivo sai do alinhamento e tem a sua própria regra (ver VersaoDoAmbienteLocalTest).
AMBIENTE_LOCAL = 'deploy/ambientes/local.env.example'


def versoes():
    encontradas = {'configuracao.json': json.loads((RAIZ / 'configuracao.json').read_text(encoding='utf-8'))['versao'],
                   'instalador/dependencias.json': json.loads(
                       (RAIZ / 'instalador' / 'dependencias.json').read_text(encoding='utf-8'))['versao_vlado']}
    iss = (RAIZ / 'instalador' / 'vlado.iss').read_text(encoding='utf-8')
    encontradas['instalador/vlado.iss'] = re.search(r'#define Versao "([^"]+)"', iss).group(1)
    for arquivo in [RAIZ / '.env.example', *sorted((RAIZ / 'deploy' / 'ambientes').glob('*.env.example'))]:
        if arquivo.relative_to(RAIZ).as_posix() == AMBIENTE_LOCAL:
            continue
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


class VersaoDoAmbienteLocalTest(unittest.TestCase):
    def test_etiqueta_local_com_sufixo_e_nunca_vlado_local(self):
        linhas = re.findall(r'^VLADO_VERSAO=(.*)$', (RAIZ / AMBIENTE_LOCAL).read_text(encoding='utf-8'), re.M)
        self.assertEqual(len(linhas), 1, f'{AMBIENTE_LOCAL}: esperada exatamente uma linha VLADO_VERSAO=')
        versao = linhas[0].strip()
        self.assertTrue(versao.startswith('local-'), f'{AMBIENTE_LOCAL}: {versao!r} precisa começar com local-')
        self.assertNotEqual(versao, 'local', 'nunca a imagem vlado:local da homologação')
        self.assertRegex(versao, r'^local-[A-Za-z0-9_.-]+$')

    def test_o_ambiente_local_fica_fora_do_alinhamento_e_os_outros_continuam_exigidos(self):
        encontradas = versoes()
        self.assertNotIn(AMBIENTE_LOCAL, encontradas)
        for arquivo in ('.env.example', 'deploy/ambientes/homologacao.env.example', 'deploy/ambientes/editorial.env.example',
                        'deploy/ambientes/demonstracao.env.example', 'configuracao.json', 'instalador/vlado.iss'):
            self.assertIn(arquivo, encontradas, f'{arquivo} saiu do alinhamento de release')


if __name__ == '__main__':
    unittest.main()
