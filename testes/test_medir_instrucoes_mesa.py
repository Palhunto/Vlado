"""Medida offline das instruções da Mesa (passo 0b da Onda 4) e o rascunho prompts/MESA.md, ainda não ligado."""
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
import medir_instrucoes_mesa as medida  # noqa: E402
from comum import conferir_prompts, ler_json  # noqa: E402

MESA = RAIZ / 'prompts' / 'MESA.md'


def _raiz_sintetica(pasta: Path) -> Path:
    """Projeto mínimo com os arquivos que a medida lê, todos sintéticos."""
    (pasta / 'prompts').mkdir()
    (pasta / 'AGENTS.md').write_text('# Regras sintéticas do projeto\n' * 40, encoding='utf-8')
    (pasta / 'README.md').write_text('# Apresentação sintética\n' * 20, encoding='utf-8')
    (pasta / 'prompts' / 'FLUXO_COMPLETO.md').write_text('# Fluxo sintético\n' * 60, encoding='utf-8')
    (pasta / 'configuracao.json').write_text(json.dumps({'provedor': 'anthropic'}), encoding='utf-8')
    shutil.copyfile(MESA, pasta / 'prompts' / 'MESA.md')
    shutil.copyfile(RAIZ / 'precos_modelos.json', pasta / 'precos_modelos.json')
    return pasta


def _arquivos(pasta: Path) -> dict:
    return {str(p.relative_to(pasta)): p.read_bytes() for p in sorted(pasta.rglob('*')) if p.is_file()}


class RascunhoMesa(unittest.TestCase):
    def test_tem_todos_os_blocos_e_um_formato_por_etapa(self):
        blocos = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))
        self.assertEqual({n for n in blocos if n.startswith('formato:')},
                         {f'formato:{e}' for e in medida.ETAPAS})
        for marca in ('{pergunta}', '{etapa}', '{tentativa}'):
            self.assertIn(marca, blocos['controle'])

    def test_as_etapas_da_medida_sao_as_do_fluxo(self):
        from fluxo_codex import ETAPAS
        self.assertEqual(medida.ETAPAS, ETAPAS)

    def test_ainda_nao_esta_ligado(self):
        # Rascunho da T3: fora do manifesto e fora do que a Mesa manda hoje.
        manifesto = ler_json(RAIZ / 'prompts' / 'manifesto_prompts.json')
        self.assertNotIn('MESA', json.dumps(manifesto))
        conferir_prompts(RAIZ)
        antes = medida.montar(RAIZ)['antes']
        self.assertNotIn('Esta pergunta está fora do escopo da Mesa', antes['sistema'])
        self.assertNotIn('fora_do_briefing', antes['turnos']['sintese'])
        self.assertIn((RAIZ / 'AGENTS.md').read_text(encoding='utf-8-sig'), antes['sistema'])

    def test_frase_de_recusa_passa_pela_conferencia_de_insuficiencia_da_sintese(self):
        # Same regex fluxo_codex.Fluxo.synthesis applies when nothing is included.
        texto = MESA.read_text(encoding='utf-8')
        frase = re.search(r'^> (.+)$', texto, re.M).group(1)
        self.assertRegex(frase, re.compile(r'insufici|não (?:foi|há|foram)|sem (?:suporte|evidência|achados)', re.I))

    def test_formato_da_sintese_separa_fora_do_briefing_de_retirado(self):
        sintese = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))['formato:sintese']
        self.assertIn('incluido|fora_do_briefing|pendencia|retirado', sintese)
        self.assertIn('Outros achados sustentados', sintese)
        self.assertIn('idioma da pergunta', sintese)
        self.assertNotIn('em português', sintese)

    def test_secoes_editoriais_da_auditoria(self):
        # Recomendações L1 a L6 da proposta, parte de protocolo: núcleo fixo da síntese, cobertura e contraverificação.
        blocos = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))
        for secao in ('"Resposta direta"', '"Contexto"', '"Outro lado"', '"Números"', '"Lacunas e diligências"'):
            self.assertIn(secao, blocos['formato:sintese'])
        self.assertIn('"Cobertura"', blocos['formato:busca'])
        self.assertIn('"Contraverificação"', blocos['formato:busca'])
        self.assertIn('papel contradicao', blocos['formato:busca'])

    def test_bloco_ausente_ou_repetido_e_recusado(self):
        texto = MESA.read_text(encoding='utf-8')
        sem_plano = re.sub(r'<!-- mesa:formato:plano -->\n.*?\n<!-- /mesa -->', '', texto, flags=re.S)
        with self.assertRaisesRegex(ValueError, 'formato:plano'):
            medida.blocos_mesa(sem_plano)
        with self.assertRaisesRegex(ValueError, 'repetido'):
            medida.blocos_mesa(texto + '\n<!-- mesa:controle -->\nde novo\n<!-- /mesa -->\n')


class Medida(unittest.TestCase):
    def test_tokens_estimados_e_faixa(self):
        self.assertEqual(medida.tokens(7), 2)
        self.assertEqual(medida.tokens(0), 0)
        menos, mais = medida._medida('x' * 120)['faixa_tokens']
        self.assertEqual((menos, mais), (30, 40))

    def test_mede_os_dois_fluxos_sem_gravar_no_projeto(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = _raiz_sintetica(Path(pasta))
            antes_de_medir = _arquivos(raiz)
            r = medida.medir(raiz, chamadas=10)
            self.assertEqual(_arquivos(raiz), antes_de_medir)
        a, d = r['antes'], r['depois']
        self.assertEqual(set(a['turnos']), set(medida.ETAPAS))
        self.assertEqual(set(d['turnos']), set(medida.ETAPAS))
        self.assertEqual(a['ferramentas'], d['ferramentas'])
        fixa = a['sistema']['caracteres'] + a['ferramentas']['caracteres']
        self.assertEqual(a['parte_fixa_por_chamada']['caracteres'], fixa)
        self.assertEqual(r['estimativa']['chamadas_por_pergunta'], 10)
        self.assertEqual(set(a['parte_fixa_por_pergunta_usd']), set(medida.MODELOS))

    def test_antes_e_o_que_a_mesa_manda_hoje(self):
        textos = medida.montar(RAIZ)
        antes, depois = textos['antes'], textos['depois']
        for arquivo in ('AGENTS.md', 'prompts/FLUXO_COMPLETO.md', 'README.md'):
            self.assertIn((RAIZ / arquivo).read_text(encoding='utf-8-sig'), antes['sistema'])
            self.assertNotIn((RAIZ / arquivo).read_text(encoding='utf-8-sig'), depois['sistema'])
        self.assertIn('ADAPTAÇÃO DE TRANSPORTE', antes['sistema'])
        self.assertIn('Etapa obrigatória atual: sintese', antes['turnos']['sintese'])
        blocos = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))
        for etapa in medida.ETAPAS:
            self.assertIn(blocos[f'formato:{etapa}'], depois['turnos'][etapa])
            self.assertIn(f'etapa={etapa}', depois['turnos'][etapa])
            self.assertIn(medida.PERGUNTA, depois['turnos'][etapa])

    def test_com_o_mesa_a_parte_fixa_cai(self):
        r = medida.medir(RAIZ)
        self.assertLess(r['depois']['parte_fixa_por_chamada']['caracteres'],
                        r['antes']['parte_fixa_por_chamada']['caracteres'] // 4)
        for modelo, usd in r['depois']['parte_fixa_por_pergunta_usd'].items():
            self.assertLess(float(usd['com_cache']), float(r['antes']['parte_fixa_por_pergunta_usd'][modelo]['com_cache']))

    def test_linha_de_comando(self):
        from io import StringIO
        from contextlib import redirect_stdout
        saida = StringIO()
        with redirect_stdout(saida):
            medida.main(['--json', '--chamadas', '3'])
        self.assertEqual(json.loads(saida.getvalue())['estimativa']['chamadas_por_pergunta'], 3)
        with self.assertRaises(SystemExit), redirect_stdout(StringIO()):
            from contextlib import redirect_stderr
            with redirect_stderr(StringIO()):
                medida.main(['--chamadas', '0'])


if __name__ == '__main__':
    unittest.main()
