"""L5: a conferência do briefing contra os achados, sem modelo, antes de publicar a síntese.

A falha real que ela tem de pegar: o achado diz que o acórdão reformou a decisão em parte, e o briefing diz que
reformou tudo. As regras são fixas (scripts/conferencia_briefing.py); os testes também prendem o que elas NÃO
recusam (frase de limite, seção de diligências, número da pergunta, conta escrita por extenso), para que uma
pergunta legítima não fique sem resposta por falso positivo.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import conferencia_briefing as cb
import test_codex_integracao as fixture  # módulos, para não recoletar os TestCases deles
import test_fluxo_codex as fluxo

ACORDAO = 'O Acórdão 1.234/2024 reformou parcialmente a decisão, só quanto à multa de R$ 50.000,00.'
CONTRATO = ('O contrato 041/2025 declara valor global de R$ 8.750.000,00 e assinatura em 3 de março de 2025; '
            'o aditivo soma R$ 250.000,00.')
TRECHO_ACORDAO = 'dar provimento parcial ao recurso, apenas para reduzir a multa a R$ 50.000,00'
TRECHO_CONTRATO = 'Valor global: R$ 8.750.000,00. Data de assinatura: 3 de marco de 2025. Aditivo: R$ 250.000,00.'


def dados():
    """Dois achados revisados, cada um com uma evidência de suporte (E001 → R1, E002 → R2)."""
    achado = lambda i, redacao, natureza='declaracao_documental': {
        'id': i, 'subquestao': '...', 'versoes': [{'versao': 1, 'redacao': redacao, 'natureza': natureza,
                                                   'limitacoes': '...'}]}
    evidencia = lambda i, trecho: {'id': i, 'trecho': trecho, 'localizador': {'tipo': 'linhas', 'descricao': ''}}
    return {'achados': [achado('A001', ACORDAO), achado('A002', CONTRATO)],
            'evidencias': [evidencia('E001', TRECHO_ACORDAO), evidencia('E002', TRECHO_CONTRATO)],
            'vinculos': [{'achado_id': 'A001', 'versao': 1, 'evidencia_id': 'E001', 'papel': 'suporte'},
                         {'achado_id': 'A002', 'versao': 1, 'evidencia_id': 'E002', 'papel': 'suporte'}],
            'destinos': []}


REFS = {'E001': 'R1', 'E002': 'R2'}


def tipos(texto, pergunta=''):
    return [r['tipo'] for r in cb.conferir(texto, dados(), REFS, pergunta)['recusas']]


class FalhaRealTest(unittest.TestCase):
    def test_reformou_tudo_quando_a_reforma_foi_parcial_e_recusado(self):
        resultado = cb.conferir('[A001@v1] O Acórdão 1.234/2024 reformou tudo. [fonte:R1]', dados(), REFS)
        self.assertEqual([r['tipo'] for r in resultado['recusas']], ['quantificador_mais_forte', 'ressalva_omitida'])
        motivo = resultado['recusas'][0]['motivo']
        self.assertIn('"tudo"', motivo)
        self.assertIn('alcance parcial (A001 v1)', motivo)
        self.assertIn('Conferência do briefing contra os achados', cb.mensagem(resultado))
        self.assertIn('O Acórdão 1.234/2024 reformou tudo.', cb.mensagem(resultado))

    def test_outras_formas_da_mesma_falha(self):
        self.assertIn('quantificador_mais_forte', tipos('[A001@v1] O acórdão reformou integralmente a decisão.'))
        self.assertIn('quantificador_mais_forte', tipos('[A001@v1] The ruling reversed everything.'))
        # Sem exagero, mas sem a ressalva: a omissão também é recusada.
        self.assertEqual(tipos('[A001@v1] O Acórdão 1.234/2024 reformou a decisão. [fonte:R1]'), ['ressalva_omitida'])

    def test_a_redacao_no_alcance_do_achado_passa(self):
        self.assertEqual(tipos('[A001@v1] O Acórdão 1.234/2024 reformou a decisão em parte, só quanto à multa '
                               'de R$ 50 mil. [fonte:R1]'), [])
        # A ressalva basta numa das frases que citam o achado.
        self.assertEqual(tipos('[A001@v1] O Acórdão 1.234/2024 reformou parcialmente a decisão. [fonte:R1]\n\n'
                               '[A001@v1] A multa ficou em R$ 50.000,00. [fonte:R1]'), [])


class CoberturaTest(unittest.TestCase):
    def test_frase_factual_sem_achado_e_recusada(self):
        self.assertEqual(tipos('O contrato vale R$ 10 milhões.'), ['afirmacao_sem_achado'])
        self.assertEqual(tipos('Todos os pagamentos foram feitos.'), ['afirmacao_sem_achado'])

    def test_fonte_que_nao_sustenta_achado_e_recusada(self):
        # Uma passagem lida na rodada, mas que nenhum achado usa: é o fato que nasce só na síntese.
        self.assertIn('fonte_sem_achado', tipos('O pagamento foi de R$ 8.750.000,00. [fonte:LIDA_SEM_ACHADO]'))

    def test_numero_fora_do_achado_e_recusado(self):
        self.assertEqual(tipos('[A002@v1] O contrato vale R$ 9.750.000,00. [fonte:R2]'), ['numero_fora_do_achado'])
        self.assertEqual(tipos('[A002@v1] O contrato foi assinado em 4 de março de 2025. [fonte:R2]'),
                         ['numero_fora_do_achado'])

    def test_formatos_diferentes_do_mesmo_valor_passam(self):
        self.assertEqual(tipos('[A002@v1] O contrato 041/2025 vale R$ 8,75 milhões e foi assinado em 03/03/2025, '
                               'em março de 2025. [fonte:R2]'), [])

    def test_a_marca_vale_para_o_paragrafo_inteiro(self):
        self.assertEqual(tipos('O contrato foi assinado em 3 de março de 2025. O valor é de R$ 8,75 milhões. '
                               '[A002@v1] [fonte:R2]'), [])
        # Mas cada frase é conferida contra o achado citado no parágrafo.
        self.assertEqual(tipos('O contrato foi pago em 2026. [A002@v1]'), ['numero_fora_do_achado'])

    def test_conta_escrita_por_extenso_tem_resultado_derivado(self):
        conta = '[A002@v1] Valor com aditivo: R$ 8.750.000,00 + R$ 250.000,00 = R$ 9.000.000,00. [fonte:R2]'
        self.assertEqual(tipos(conta), [])
        self.assertEqual(tipos('[A002@v1] Com o aditivo, o total chega a R$ 9.000.000,00. [fonte:R2]'),
                         ['numero_fora_do_achado'])

    def test_lista_fora_do_briefing_e_conferida_pelo_id_por_extenso(self):
        base = '[A002@v1] O contrato vale R$ 8.750.000,00. [fonte:R2]\n\n## Outros achados sustentados\n'
        self.assertEqual(tipos(base + '- A001 v1: reforma parcial, só da multa. [fonte:R1]\n'), [])
        self.assertIn('quantificador_mais_forte', tipos(base + '- A001 v1: a decisão foi reformada por inteiro. [fonte:R1]\n'))


class SemFalsoPositivoTest(unittest.TestCase):
    def test_frase_de_limite_e_secao_de_diligencias_sem_numero_nao_precisam_de_achado(self):
        texto = ('O pagamento do aditivo não foi localizado no corpus.\n\n'
                 '## Lacunas e diligências\n'
                 '- Pedir ao órgão, pela Lei de Acesso à Informação e sem exigir motivo, todos os pagamentos do aditivo.\n\n'
                 'Outro lado:\nNão se aplica: nenhum achado atribui conduta a pessoa ou entidade.')
        self.assertEqual(tipos(texto), [])

    def test_adjetivo_solto_nao_e_quantificador(self):
        """B1: "inteiro teor" e "nome completo" não dizem alcance; a frase com achado e localizador passa."""
        self.assertEqual(tipos('[A002@v1] O inteiro teor do contrato 041/2025 traz o valor global de '
                               'R$ 8.750.000,00. [fonte:R2]'), [])
        self.assertEqual(tipos('[A002@v1] O contrato traz o nome completo da contratada e o valor de '
                               'R$ 8.750.000,00. [fonte:R2]'), [])
        for adjetivo in ('integral', 'inteiro', 'inteira', 'completo', 'completa', 'todo', 'toda', 'unanime'):
            self.assertNotIn(adjetivo, cb.QUANTIFICADORES)
        # O quantificador de fato continua recusado.
        self.assertIn('quantificador_mais_forte', tipos('[A002@v1] O contrato foi integralmente pago. [fonte:R2]'))


class NumeroSempreTemAchadoTest(unittest.TestCase):
    """B2: número precisa de achado em qualquer seção e também numa frase negativa."""

    def test_frase_negativa_com_numero_e_recusada(self):
        self.assertEqual(tipos('Não houve licitação para o contrato de R$ 5 milhões.'), ['afirmacao_sem_achado'])
        self.assertEqual(tipos('O pagamento de 2024 não foi localizado no corpus.'), ['afirmacao_sem_achado'])

    def test_secao_de_lacunas_ou_limitacoes_com_numero_e_recusada(self):
        for titulo in ('## Lacunas e diligências', '## Limitações', 'Lacunas:'):
            texto = f'{titulo}\n- Pedir ao órgão os pagamentos de R$ 2 milhões feitos em 2024.\n'
            self.assertEqual(tipos(texto), ['afirmacao_sem_achado'], titulo)
            self.assertIn('cite a lei pelo nome', cb.mensagem(cb.conferir(texto, dados(), REFS)))

    def test_numero_da_pergunta_continua_livre_na_lacuna(self):
        self.assertEqual(tipos('## Lacunas e diligências\n- Pedir o contrato 041/2025 assinado.\n',
                               pergunta='O que diz o contrato 041/2025?'), [])


def com_pendencia():
    """dados() mais A003, uma pendência sem evidência (não leva a marca [A003@v1])."""
    d = dados()
    d['achados'].append({'id': 'A003', 'subquestao': '...', 'versoes': [{
        'versao': 1, 'redacao': 'Pagamento de R$ 3 milhões ao fornecedor, sem comprovante no corpus.',
        'natureza': 'pendencia', 'limitacoes': '...'}]})
    return d


class PendenciaPorExtensoTest(unittest.TestCase):
    """R1 da Coruja à bc55751: a pendência, citada pelo ID com versão por extenso, cobre o número que ela registra."""

    def recusas(self, texto):
        return [r['tipo'] for r in cb.conferir(texto, com_pendencia(), REFS)['recusas']]

    def test_pendencia_por_extenso_cobre_o_numero(self):
        self.assertEqual(self.recusas('## Lacunas e diligências\n- Pagamento de R$ 3 milhões sem comprovante '
                                      '(A003 v1, pendência).\n'), [])
        self.assertEqual(self.recusas('O pagamento de R$ 3 milhões segue sem comprovante (A003, v1).'), [])

    def test_numero_que_a_pendencia_nao_registra_continua_recusado(self):
        self.assertEqual(self.recusas('O pagamento de R$ 4 milhões segue sem comprovante (A003 v1, pendência).'),
                         ['numero_fora_do_achado'])
        # ID por extenso de achado que não existe não cobre nada.
        self.assertEqual(self.recusas('O pagamento de R$ 3 milhões segue sem comprovante (A009 v1).'),
                         ['afirmacao_sem_achado'])


class CabecalhoDaRodadaTest(unittest.TestCase):
    """N2: o cabeçalho cita os metadados da própria rodada, conferidos contra o registro dela."""
    METADADOS = ['alpha', 'R001', 'alpha_v3', 'r3_sintese', '25/11/2026']

    def recusas(self, texto):
        return [r['tipo'] for r in cb.conferir(texto, dados(), REFS, '', self.METADADOS)['recusas']]

    def test_data_da_rodada_no_cabecalho_passa(self):
        self.assertEqual(self.recusas('Rodada R001, de 25/11/2026, corpus alpha_v3.\n\n## Resposta direta\n\n'
                                      '[A002@v1] O contrato vale R$ 8.750.000,00. [fonte:R2]'), [])
        self.assertEqual(self.recusas('Rodada R001 (25 de novembro de 2026), revisão r3_sintese.'), [])

    def test_outra_data_no_cabecalho_ou_a_data_da_rodada_fora_dele_e_recusada(self):
        self.assertEqual(self.recusas('Rodada R001, de 24/11/2026.'), ['afirmacao_sem_achado'])
        self.assertEqual(self.recusas('## Resposta direta\n\nO pagamento foi feito em 25/11/2026.'),
                         ['afirmacao_sem_achado'])

    def test_o_fluxo_le_os_metadados_do_registro_da_rodada(self):
        import tempfile
        from comum import escrever_json
        from fluxo_codex import Fluxo
        with tempfile.TemporaryDirectory() as pasta:
            run = Path(pasta)
            (run / 'saidas').mkdir()
            escrever_json(run / 'registro.json', {'criada_em_utc': '2026-11-26T01:30:00+00:00'})
            fluxo = Fluxo(run, run, {'caso': 'alpha', 'rodada': 'R001', 'corpus_id': 'alpha_v3'}, {},
                          instrucoes={'modo': 'legado', 'versao_prompts': '1.5.0'})
            metadados = fluxo._metadados_da_rodada()
        # 01:30 UTC de 26/11 ainda é 25/11 em Brasília: as duas datas valem.
        self.assertEqual(set(metadados), {'alpha', 'R001', 'alpha_v3', 'r3_sintese', '26/11/2026', '25/11/2026'})


class EscopoDaConferenciaTest(unittest.TestCase):
    """R3 (decisão do Maestro): vale para rodadas congeladas em 1.5.0 ou depois; a legada segue sem ela."""

    def test_versoes(self):
        for versao, vale in (('1.5.0', True), ('1.5.1', True), ('2.0.0', True), ('1.4.1', False),
                             ('1.2.0', False), (None, False), ('', False), ('x.y.z', False)):
            self.assertEqual(cb.aplica({'modo': 'legado', 'versao_prompts': versao}), vale, versao)
        self.assertFalse(cb.aplica(None))

    def test_numeros_da_pergunta_e_contagens_pequenas(self):
        self.assertEqual(tipos('Rodada R001, sobre o contrato 041/2025 e os 3 aditivos citados.',
                               pergunta='O que diz o contrato 041/2025?'), [])

    def test_titulos_e_marcas_nao_viram_numeros(self):
        self.assertEqual(tipos('## Resposta direta (R001)\n\n[A002@v1] O contrato vale R$ 8.750.000,00. [fonte:R2]'), [])

    def test_causalidade_fica_como_alerta(self):
        resultado = cb.conferir('[A002@v1] O aditivo de R$ 250.000,00 provocou o atraso. [fonte:R2]', dados(), REFS)
        self.assertEqual(resultado['recusas'], [])
        self.assertEqual([a['tipo'] for a in resultado['alertas']], ['causalidade_sem_suporte'])

    def test_mensagem_limita_os_motivos(self):
        texto = '\n\n'.join(f'O contrato {n} vale R$ {n}0 milhões.' for n in range(11, 20))
        resultado = cb.conferir(texto, dados(), REFS)
        self.assertEqual(len(resultado['recusas']), 9)
        self.assertIn('e mais 3 frase(s)', cb.mensagem(resultado))


class RodadaLegadaSemConferenciaTest(unittest.TestCase):
    """Uma rodada congelada com os prompts 1.4.1 publica o briefing que a conferência recusaria: o novo não trava o
    antigo. A instalação de teste simula uma de antes da 1.5.0 (comum.VERSAO_PROMPTS = 1.4.1 ao montar e ao
    congelar), e a rodada guarda a versão no manifesto congelado."""
    tool, wait_stage, end, step, terminal = (getattr(fluxo.FluxoAutomaticoTest, n) for n in
                                             ('tool', 'wait_stage', 'end', 'step', 'terminal'))

    def setUp(self):
        from unittest.mock import patch
        from codex_apuracao import Conversas
        from agente_fluxo_fixture import encerrar_gerenciador
        from modelo_pasta import copiar
        versao = patch('comum.VERSAO_PROMPTS', '1.4.1')
        versao.start()
        self.addCleanup(versao.stop)
        temp, self.root, _ = copiar('ConferenciaBriefingLegado141', fixture.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
        self.manager = Conversas(self.root, fixture.FakeServer)
        self.addCleanup(encerrar_gerenciador, self.manager)
        self.identifier = fixture.CodexIntegrationTest.start(self)
        self.ctx = self.manager.contexts[self.identifier]
        self.refs = {}

    def test_rodada_1_4_1_publica_sem_a_conferencia(self):
        self.assertEqual(self.ctx['meta']['instrucoes']['versao_prompts'], '1.4.1')
        for etapa in ('inventario', 'plano', 'busca', 'geracao_inicial', 'revisao'):
            self.step(etapa)
        ref = self.refs['hit']['referencia']
        self.step('sintese', {'texto': f'[A001@v1] A fonte sintética sempre declara valor 123 e 456. [fonte:{ref}]',
                              'destinos': [{'achado_id': 'A001', 'destino': 'incluido', 'motivo': 'Revisado.'}]})
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido', self.ctx['meta'].get('situacao'))
        self.assertEqual(list((self.ctx['run'] / 'saidas').glob('codex_conferencia_briefing_*.json')), [])


class SinteseDoFluxoTest(unittest.TestCase):
    """A conferência no fluxo da Mesa: recusa na primeira tentativa, a mesma etapa refaz e publica."""

    start = fixture.CodexIntegrationTest.start
    setUp = fluxo.FluxoAutomaticoTest.setUp
    tool, wait_stage, end, step, terminal = (getattr(fluxo.FluxoAutomaticoTest, n) for n in
                                             ('tool', 'wait_stage', 'end', 'step', 'terminal'))

    def test_recusa_explica_e_a_segunda_tentativa_publica(self):
        from agente_fluxo_fixture import entrega
        for etapa in ('inventario', 'plano', 'busca', 'geracao_inicial', 'revisao'):
            self.step(etapa)
        self.wait_stage('sintese')
        ref = self.refs['hit']['referencia']
        exagero = {'texto': f'[A001@v1] A fonte sintética sempre declara valor 123 e 456. [fonte:{ref}]',
                   'destinos': [{'achado_id': 'A001', 'destino': 'incluido', 'motivo': 'Revisado.'}]}
        with self.assertRaisesRegex(ValueError, 'Conferência do briefing') as recusa:
            self.tool({'acao': 'guardar', 'etapa': 'sintese', 'texto': json.dumps(exagero, ensure_ascii=False)})
        self.assertIn('"456" não está na redação', str(recusa.exception))
        self.assertIn('"sempre" é mais forte que A001 v1', str(recusa.exception))
        revisoes = self.ctx['run'] / 'saidas/achados/revisoes'
        self.assertEqual(sorted(p.name for p in revisoes.iterdir()), ['r1_busca', 'r2_revisao'])
        self.end()
        self.wait_stage('sintese', 2)
        self.assertIn('Conferência do briefing', self.manager.rpc.calls[-1][1]['input'][0]['text'])
        self.tool({'acao': 'guardar', 'etapa': 'sintese', 'texto': entrega('sintese', self.tool, self.refs)})
        self.end()
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido', self.ctx['meta'].get('situacao'))
        registros = sorted((self.ctx['run'] / 'saidas').glob('codex_conferencia_briefing_*.json'))
        resultados = [json.loads(p.read_text(encoding='utf-8')) for p in registros]
        self.assertEqual(sorted(len(r['recusas']) for r in resultados), [0, 2])


if __name__ == '__main__':
    unittest.main()
