"""Medida offline das instruções da Mesa e o prompts/MESA.md, ligado nos prompts 1.5.0 (T3).

A medida congela os arquivos do projeto numa rodada temporária como a `nova_rodada` (R2 da Coruja): o lado
`antes` é uma rodada sem a chave `mesa` no manifesto (o legado), o `depois` é o manifesto do projeto. Os dois
chamam as funções reais. O teste prende o legado: os turnos e a adaptação de transporte do modo antigo têm hash
fixo, para que ninguém edite os textos 1.4.1 que as rodadas antigas continuam usando.
"""
import hashlib
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
from comum import VERSAO_MESA, VERSAO_PROMPTS, conferir_prompts, ler_json, sha256  # noqa: E402

MESA = RAIZ / 'prompts' / 'MESA.md'
# Fluxo.prompt no modo legado, tentativa 1, com medida.PERGUNTA e sem dados: os textos de formatos 1.4.1.
TURNOS_LEGADO = {
    'inventario': 'd0d35a06dff18e9243f793862efed5d9ce8ba5c5aecc9859d751327ddab87d6f',
    'plano': '5bf1f394d10e488b3b9c25e1e98416e898c5dc05c2f17fff5a712bc2450ef2c2',
    'busca': '008495a9835aa846af9853f7fe11e532a5f05d56d7fa22dee67808ed96034729',
    'geracao_inicial': '8eb1889263b77d99a7e1849d74788c48cdbc7bfb1dc22b66c7749303e2eb13ae',
    'revisao': 'cf900f0b8bf3057124394e92f52fb42ab759a16889df97d5819ff5ebc6637299',
    'sintese': 'e423852e0784a4b777dbd48dc49d66ef04c698574228155f84fe96b2289d6f34',
}
ADAPTACAO_LEGADO = '3504ab080cc3a598c0f5879f97e54e134e4a20df23260aa25487af8ec2f9af4d'


def _raiz_sintetica(pasta: Path) -> Path:
    """Projeto mínimo com os arquivos que a medida lê, todos sintéticos, e o manifesto com a chave mesa."""
    (pasta / 'prompts').mkdir()
    (pasta / 'AGENTS.md').write_text('# Regras sintéticas do projeto\n' * 40, encoding='utf-8')
    (pasta / 'README.md').write_text('# Apresentação sintética\n' * 20, encoding='utf-8')
    (pasta / 'prompts' / 'FLUXO_COMPLETO.md').write_text('# Fluxo sintético\n' * 60, encoding='utf-8')
    (pasta / 'configuracao.json').write_text(json.dumps({'provedor': 'anthropic'}), encoding='utf-8')
    shutil.copyfile(MESA, pasta / 'prompts' / 'MESA.md')
    (pasta / 'prompts' / 'manifesto_prompts.json').write_text(json.dumps({
        'versao': VERSAO_PROMPTS, 'mesa': {'arquivo': 'prompts/MESA.md', 'versao': VERSAO_MESA,
                                           'sha256': sha256(MESA)}}), encoding='utf-8')
    shutil.copyfile(RAIZ / 'precos_modelos.json', pasta / 'precos_modelos.json')
    return pasta


def _arquivos(pasta: Path) -> dict:
    return {str(p.relative_to(pasta)): p.read_bytes() for p in sorted(pasta.rglob('*')) if p.is_file()}


class MesaNoManifesto(unittest.TestCase):
    def test_tem_todos_os_blocos_e_um_formato_por_etapa(self):
        blocos = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))
        self.assertEqual({n for n in blocos if n.startswith('formato:')},
                         {f'formato:{e}' for e in medida.ETAPAS})
        for marca in ('{pergunta}', '{etapa}', '{etapa_ferramenta}', '{tentativa}'):
            self.assertIn(marca, blocos['controle'])

    def test_as_etapas_da_medida_sao_as_do_fluxo(self):
        from fluxo_codex import ETAPAS
        self.assertEqual(medida.ETAPAS, ETAPAS)

    def test_ligado_pelo_manifesto_1_5_0(self):
        manifesto = ler_json(RAIZ / 'prompts' / 'manifesto_prompts.json')
        self.assertEqual(manifesto['versao'], '1.5.0')
        self.assertEqual(manifesto['mesa'], {'arquivo': 'prompts/MESA.md', 'versao': VERSAO_MESA, 'sha256': sha256(MESA)})
        conferir_prompts(RAIZ)
        # O FLUXO_COMPLETO (do agente de chat) continua montado só dos módulos 00 a 06.
        self.assertNotIn('mesa:sistema', (RAIZ / 'prompts' / 'FLUXO_COMPLETO.md').read_text(encoding='utf-8'))

    def test_frase_de_recusa_passa_pela_conferencia_de_insuficiencia_da_sintese(self):
        # Same regex fluxo_codex.Fluxo.synthesis applies when nothing is included.
        texto = MESA.read_text(encoding='utf-8')
        frase = re.search(r'^> (.+)$', texto, re.M).group(1)
        self.assertRegex(frase, re.compile(r'insufici|não (?:foi|há|foram)|sem (?:suporte|evidência|achados)', re.I))

    def test_frase_de_recusa_passa_pela_conferencia_do_briefing(self):
        import conferencia_briefing
        frase = re.search(r'^> (.+)$', MESA.read_text(encoding='utf-8'), re.M).group(1)
        vazio = {'achados': [], 'evidencias': [], 'vinculos': [], 'destinos': []}
        self.assertEqual(conferencia_briefing.conferir(frase, vazio, {})['recusas'], [])

    def test_formato_da_sintese_separa_fora_do_briefing_de_retirado(self):
        sintese = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))['formato:sintese']
        self.assertIn('incluido|fora_do_briefing|pendencia|retirado', sintese)
        self.assertIn('Outros achados sustentados', sintese)
        self.assertIn('idioma da pergunta', sintese)
        self.assertNotIn('em português', sintese)
        self.assertIn('operandos = resultado', sintese)  # a regra da conferência do briefing (L5)

    def test_secoes_editoriais_da_auditoria(self):
        # Recomendações L1 a L6 da proposta, parte de protocolo: núcleo fixo da síntese, cobertura e contraverificação.
        blocos = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))
        for secao in ('"Resposta direta"', '"Contexto"', '"Outro lado"', '"Números"', '"Lacunas e diligências"'):
            self.assertIn(secao, blocos['formato:sintese'])
        self.assertIn('"Cobertura"', blocos['formato:busca'])
        self.assertIn('"Contraverificação"', blocos['formato:busca'])
        self.assertIn('papel contradicao', blocos['formato:busca'])

    def test_r1_respostas_anteriores_nao_sao_evidencia(self):
        sistema = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))['sistema']
        self.assertIn('Achados ou respostas anteriores, inclusive desta conversa, não são evidência desta rodada.',
                      sistema)

    def test_bloco_ausente_repetido_ou_sem_marca_e_recusado(self):
        texto = MESA.read_text(encoding='utf-8')
        sem_plano = re.sub(r'<!-- mesa:formato:plano -->\n.*?\n<!-- /mesa -->', '', texto, flags=re.S)
        with self.assertRaisesRegex(ValueError, 'formato:plano'):
            medida.blocos_mesa(sem_plano)
        with self.assertRaisesRegex(ValueError, 'repetido'):
            medida.blocos_mesa(texto + '\n<!-- mesa:controle -->\nde novo\n<!-- /mesa -->\n')
        with self.assertRaisesRegex(ValueError, 'etapa_ferramenta'):
            medida.blocos_mesa(texto.replace('{etapa_ferramenta}', 'sintese'))


class Medida(unittest.TestCase):
    def test_tokens_estimados_e_faixa(self):
        self.assertEqual(medida.tokens(7), 2)
        self.assertEqual(medida.tokens(0), 0)
        menos, mais = medida._medida('x' * 120)['faixa_tokens']
        self.assertEqual((menos, mais), (30, 40))

    def test_mede_os_dois_modos_sem_gravar_no_projeto(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = _raiz_sintetica(Path(pasta))
            antes_de_medir = _arquivos(raiz)
            r = medida.medir(raiz, chamadas=10)
            self.assertEqual(_arquivos(raiz), antes_de_medir)
        a, d = r['antes'], r['depois']
        self.assertEqual((a['modo'], d['modo']), ('legado', 'mesa'))
        self.assertEqual(set(a['turnos']), set(medida.ETAPAS))
        self.assertEqual(set(d['turnos']), set(medida.ETAPAS))
        self.assertEqual(a['ferramentas'], d['ferramentas'])
        fixa = a['sistema']['caracteres'] + a['ferramentas']['caracteres']
        self.assertEqual(a['parte_fixa_por_chamada']['caracteres'], fixa)
        self.assertEqual(r['estimativa']['chamadas_por_pergunta'], 10)
        self.assertEqual(set(a['parte_fixa_por_pergunta_usd']), set(medida.MODELOS))

    def test_antes_e_o_legado_e_depois_e_o_que_a_mesa_manda(self):
        textos = medida.montar(RAIZ)
        antes, depois = textos['antes'], textos['depois']
        self.assertEqual((antes['modo'], depois['modo']), ('legado', 'mesa'))
        for arquivo in ('AGENTS.md', 'prompts/FLUXO_COMPLETO.md', 'README.md'):
            self.assertIn((RAIZ / arquivo).read_text(encoding='utf-8-sig'), antes['sistema'])
            self.assertNotIn((RAIZ / arquivo).read_text(encoding='utf-8-sig'), depois['sistema'])
        self.assertIn('ADAPTAÇÃO DE TRANSPORTE', antes['sistema'])
        self.assertIn('Etapa obrigatória atual: sintese', antes['turnos']['sintese'])
        blocos = medida.blocos_mesa(MESA.read_text(encoding='utf-8'))
        self.assertTrue(depois['sistema'].startswith(blocos['sistema'] + '\n\n{"caso": "caso-medida"'))
        for etapa in medida.ETAPAS:
            self.assertIn(blocos[f'formato:{etapa}'], depois['turnos'][etapa])
            self.assertIn(f'etapa={etapa}', depois['turnos'][etapa])
            self.assertIn(medida.PERGUNTA, depois['turnos'][etapa])
            self.assertNotIn('Etapa obrigatória atual', depois['turnos'][etapa])

    def test_o_legado_fica_como_era(self):
        """Os textos 1.4.1 que as rodadas antigas usam: nenhuma edição, nem de espaço."""
        antes = medida.montar(RAIZ)['antes']
        for etapa, digest in TURNOS_LEGADO.items():
            self.assertEqual(hashlib.sha256(antes['turnos'][etapa].encode()).hexdigest(), digest, etapa)
        sistema = antes['sistema']
        adaptacao = sistema[sistema.index('ADAPTAÇÃO DE TRANSPORTE'):sistema.rindex('\n\n{')]
        self.assertEqual(hashlib.sha256(adaptacao.encode()).hexdigest(), ADAPTACAO_LEGADO)

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
