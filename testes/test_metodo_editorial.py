"""P50: o mesmo método editorial nos dois caminhos, a Mesa (prompts/MESA.md) e o agente de chat (prompts 02 a 05,
montados no FLUXO_COMPLETO.md).

L1 a L6 são as recomendações da auditoria editorial (núcleo fixo da síntese, contraverificação, cobertura, números,
resposta a cada parte conferida contra os achados, diligências); L8 é a premissa da pergunta; L9, a comparação
entre processos do mesmo caso. Os textos são genéricos: nenhum fato de caso entra nos prompts.
"""
from pathlib import Path
import sys
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
import conferencia_briefing  # noqa: E402
from instrucoes_mesa import blocos_mesa  # noqa: E402

PROMPTS = RAIZ / 'prompts'


def ler(nome):
    return ' '.join((PROMPTS / nome).read_text(encoding='utf-8').split())


def mesa(bloco):
    return ' '.join(blocos_mesa((PROMPTS / 'MESA.md').read_text(encoding='utf-8'))[bloco].split())


# (recomendação, trecho, onde no agente de chat, onde na Mesa)
METODO = [
    ('L1', '"Resposta direta"', '05_SINTETIZAR.md', 'formato:sintese'),
    ('L1', '"Contexto": o estado do procedimento', '05_SINTETIZAR.md', 'formato:sintese'),
    ('L1', '"Outro lado"', '05_SINTETIZAR.md', 'formato:sintese'),
    ('L1', 'por relevância editorial e não pela ordem dos achados', '05_SINTETIZAR.md', 'formato:sintese'),
    ('L2', '"Contraverificação"', '03_BUSCAR_E_CRUZAR.md', 'formato:busca'),
    ('L2', 'ônus da prova, normas do próprio emissor, contradições internas da peça', '03_BUSCAR_E_CRUZAR.md', 'formato:busca'),
    ('L3', '"Cobertura": cada documento candidato do plano, lido ou com a exclusão justificada', '03_BUSCAR_E_CRUZAR.md', 'formato:busca'),
    ('L3', 'cruzar as listas de anexos e as referências das próprias peças', '03_BUSCAR_E_CRUZAR.md', None),
    ('L4', '"Números"', '05_SINTETIZAR.md', 'formato:sintese'),
    ('L4', 'operandos = resultado', '05_SINTETIZAR.md', 'formato:sintese'),
    ('L5', 'responde a cada parte da pergunta, inclusive ao porquê', '05_SINTETIZAR.md', 'formato:sintese'),
    ('L5', 'a ressalva de alcance parcial', '05_SINTETIZAR.md', None),
    ('L6', '"Lacunas e diligências"', '05_SINTETIZAR.md', 'formato:sintese'),
    ('L6', 'o destinatário (órgão ou papel), o meio (pedido de acesso à informação, ofício ou entrevista) e o que pedir',
     '04_REVISAR_SUPORTE.md', None),
    ('L6', 'Antes de manter uma pendência, procur', '04_REVISAR_SUPORTE.md', 'formato:revisao'),
    ('L8', '"Premissa da pergunta": o que a pergunta supõe e se o corpus confirma, contraria ou não trata disso',
     '05_SINTETIZAR.md', 'formato:sintese'),
    ('L9', 'o mesmo documento, parecer ou fundamento aparece em mais de um deles e compar', '03_BUSCAR_E_CRUZAR.md', 'formato:busca'),
    ('L9', 'a diferença de desfecho não prova irregularidade', '03_BUSCAR_E_CRUZAR.md', 'formato:busca'),
    ('L9', 'Numa comparação entre processos, conf', '04_REVISAR_SUPORTE.md', 'formato:revisao'),
]


class MesmoMetodoNosDoisCaminhosTest(unittest.TestCase):
    def test_cada_recomendacao_esta_no_agente_de_chat_e_na_mesa(self):
        fluxo = ' '.join((PROMPTS / 'FLUXO_COMPLETO.md').read_text(encoding='utf-8').split())
        for codigo, trecho, modulo, bloco in METODO:
            self.assertIn(trecho, ler(modulo), (codigo, modulo))
            self.assertIn(trecho, fluxo, (codigo, 'FLUXO_COMPLETO.md'))  # o montar_fluxo levou o texto ao roteiro
            if bloco:
                self.assertIn(trecho, mesa(bloco), (codigo, bloco))

    def test_a_premissa_vem_antes_da_resposta(self):
        for texto in (ler('05_SINTETIZAR.md'), mesa('formato:sintese')):
            self.assertLess(texto.index('"Premissa da pergunta"'), texto.index('"Resposta direta"'))

    def test_o_05_tambem_lista_o_sustentado_que_nao_coube(self):
        texto = ler('05_SINTETIZAR.md')
        self.assertIn('"Outros achados sustentados"', texto)
        self.assertIn('`fora_do_briefing`', texto)
        self.assertIn('nunca do sustentado que não coube', texto)

    def test_a_premissa_contrariada_passa_pela_conferencia_do_briefing(self):
        """A seção nova não abre buraco nem falso positivo na L5: o número da pergunta não é fato novo, e o
        que contraria a premissa vem do achado citado."""
        dados = {'achados': [{'id': 'A001', 'subquestao': '...', 'versoes': [{
            'versao': 1, 'redacao': 'O pagamento foi feito em 2025, segundo o extrato.', 'natureza': 'alegacao_atribuida',
            'limitacoes': '...'}]}], 'evidencias': [{'id': 'E001', 'trecho': 'Pagamento em 2025.', 'localizador': {}}],
            'vinculos': [{'achado_id': 'A001', 'versao': 1, 'evidencia_id': 'E001', 'papel': 'suporte'}], 'destinos': []}
        texto = ('## Premissa da pergunta\n\nA pergunta supõe um pagamento em 2024. O corpus contraria a premissa: '
                 'o pagamento foi feito em 2025, segundo o extrato. [A001@v1] [fonte:R1]\n')
        resultado = conferencia_briefing.conferir(texto, dados, {'E001': 'R1'}, 'Por que o pagamento de 2024 atrasou?')
        self.assertEqual(resultado['recusas'], [])
        sem_achado = '## Premissa da pergunta\n\nO corpus contraria a premissa: o pagamento foi feito em 2026.\n'
        self.assertEqual([r['tipo'] for r in conferencia_briefing.conferir(sem_achado, dados, {'E001': 'R1'})['recusas']],
                         ['afirmacao_sem_achado'])


if __name__ == '__main__':
    unittest.main()
