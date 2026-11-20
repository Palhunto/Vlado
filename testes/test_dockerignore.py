"""Fixa o conteúdo de .dockerignore: pastas de agente e dados sensíveis nunca entram na imagem (SEG-04)."""
from pathlib import Path
import unittest

RAIZ = Path(__file__).resolve().parents[1]
# Com `**/` para valer em qualquer nível do contexto, não só na raiz.
EM_QUALQUER_NIVEL = ('**/.claude', '**/.maestri', '**/.maestro', '**/segredos', '**/acesso', '**/ajustes')
NA_RAIZ = ('.git', '.venv', '.env', '.env.*', 'conversas', 'execucoes', 'lixeira',
           'deploy/ambientes/*.env', '**/*.pem', '**/*.key')
# Exceções (`!`) permitidas: qualquer outra pode reabrir um segredo ou pasta de agente.
EXCECOES_PERMITIDAS = {'!.env.example', '!entrada/README.md', '!casos/README.md', '!casos/catalogo.json'}


class DockerignoreTest(unittest.TestCase):
    def setUp(self):
        linhas = (RAIZ / '.dockerignore').read_text(encoding='utf-8').splitlines()
        self.regras = {l.strip() for l in linhas if l.strip() and not l.lstrip().startswith('#')}

    def test_pastas_de_agente_e_sensiveis_em_qualquer_nivel(self):
        for padrao in EM_QUALQUER_NIVEL:
            self.assertIn(padrao, self.regras, f'.dockerignore sem {padrao}')

    def test_ambientes_e_dados_de_trabalho_ficam_fora(self):
        for padrao in NA_RAIZ:
            self.assertIn(padrao, self.regras, f'.dockerignore sem {padrao}')
        self.assertIn('!.env.example', self.regras)

    def test_excecoes_so_da_lista_permitida(self):
        excecoes = {r for r in self.regras if r.startswith('!')}
        self.assertEqual(excecoes - EXCECOES_PERMITIDAS, set(), 'exceção "!" fora da lista permitida em .dockerignore')

    def test_nenhuma_regra_de_agente_sem_alcance_total(self):
        for nome in ('.claude', '.maestri', '.maestro', 'segredos', 'acesso', 'ajustes'):
            self.assertNotIn(nome, self.regras, f'"{nome}" só vale na raiz; use "**/{nome}"')


if __name__ == '__main__':
    unittest.main()
