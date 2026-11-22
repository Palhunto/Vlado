"""Regras dos workflows do GitHub Actions (`.github/workflows/*.yml`), conferidas pelo texto, sem parser de YAML.

O que um erro aqui custa em silêncio: ação por tag móvel (cadeia de suprimentos), job sem teto de tempo (runner preso),
segredo entrando num teste, ou o teste de imagem deixando de rodar toda noite sem ninguém notar.
"""
from pathlib import Path
import re
import unittest

WORKFLOWS = Path(__file__).resolve().parents[1] / '.github' / 'workflows'
ARQUIVOS = sorted(WORKFLOWS.glob('*.yml'))


def texto(nome: str) -> str:
    return (WORKFLOWS / nome).read_text(encoding='utf-8')


def sem_comentarios(conteudo: str) -> str:
    return '\n'.join(re.sub(r'(^|\s)#.*$', '', linha) for linha in conteudo.splitlines())


class RegrasGeraisTest(unittest.TestCase):
    def test_ha_workflows(self):
        self.assertTrue({'testes.yml', 'imagem.yml'} <= {a.name for a in ARQUIVOS})

    def test_acoes_fixadas_por_sha_de_commit(self):
        for arquivo in ARQUIVOS:
            usos = re.findall(r'^\s*(?:-\s+)?uses:\s*(\S+)', arquivo.read_text(encoding='utf-8'), re.M)
            self.assertTrue(usos, arquivo.name)
            for uso in usos:
                with self.subTest(arquivo=arquivo.name, uso=uso):
                    self.assertRegex(uso, r'^[\w.-]+/[\w./-]+@[0-9a-f]{40}$', 'fixe a ação pelo SHA do commit, não por tag')

    def test_todo_job_tem_teto_de_tempo(self):
        for arquivo in ARQUIVOS:
            conteudo = sem_comentarios(arquivo.read_text(encoding='utf-8'))
            jobs = re.findall(r'^  [\w-]+:\s*$', conteudo.split('\njobs:', 1)[1], re.M)
            tetos = re.findall(r'^    timeout-minutes:\s*(\d+)', conteudo, re.M)
            with self.subTest(arquivo=arquivo.name):
                self.assertEqual(len(jobs), len(tetos), 'job sem timeout-minutes')
                self.assertTrue(all(int(t) <= 90 for t in tetos), tetos)

    def test_permissao_minima_e_sem_segredos_nem_push_de_imagem(self):
        for arquivo in ARQUIVOS:
            conteudo = sem_comentarios(arquivo.read_text(encoding='utf-8'))
            with self.subTest(arquivo=arquivo.name):
                self.assertRegex(conteudo, r'(?m)^permissions:\s*\n\s+contents:\s*read\s*$')
                self.assertNotIn('secrets.', conteudo)
                self.assertNotRegex(conteudo, r'docker (?:push|login)|push:\s*true|ANTHROPIC_API_KEY|OPENAI_API_KEY')
                self.assertNotIn('pull_request_target', conteudo)


class WorkflowDaImagemTest(unittest.TestCase):
    def setUp(self):
        self.conteudo = sem_comentarios(texto('imagem.yml'))

    def test_noturno_e_sob_demanda_e_fora_dos_pushes(self):
        self.assertRegex(self.conteudo, r'(?m)^  schedule:\s*\n\s+- cron:')
        self.assertRegex(self.conteudo, r'(?m)^  workflow_dispatch:')
        self.assertNotRegex(self.conteudo, r'(?m)^  (?:push|pull_request):')

    def test_liga_o_teste_lento_e_roda_o_modulo_certo_com_timeout_de_30_minutos(self):
        self.assertIn("VLADO_TESTE_IMAGEM: '1'", self.conteudo)
        self.assertIn('python -m unittest testes.test_imagem_build -v', self.conteudo)
        self.assertRegex(self.conteudo, r'(?m)^    timeout-minutes:\s*30\s*$')
        self.assertIn('ubuntu-latest', self.conteudo)

    def test_cache_de_camadas_em_tmp_buildx_cache(self):
        self.assertIn('docker/setup-buildx-action@', self.conteudo)
        self.assertIn('actions/cache@', self.conteudo)
        self.assertIn('path: /tmp/.buildx-cache', self.conteudo)
        self.assertIn('VLADO_BUILD_CACHE: /tmp/.buildx-cache', self.conteudo)


if __name__ == '__main__':
    unittest.main()
