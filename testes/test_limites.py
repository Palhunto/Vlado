"""Spend and size limits enforced by the server; no model calls."""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import escrever_json
import custo
import erros
import limites
from codex_apuracao import limitar_texto, limitar_argumentos
import test_codex_integracao as integracao  # module import: its TestCase is not re-collected here
from agente_fluxo_fixture import aguardar_fim


class LimitesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def configurar(self, valores):
        escrever_json(self.root / 'configuracao.json', {'limites': valores})

    def test_padroes_e_validacao(self):
        escrever_json(self.root / 'configuracao.json', {})
        self.assertEqual(limites.ler(self.root), {'tokens_por_consulta': 3_000_000, 'tokens_por_dia': 30_000_000,
                                                  'tokens_por_dia_por_organizacao': None})
        self.configurar({'tokens_por_consulta': None, 'tokens_por_dia': 500, 'tokens_por_dia_por_organizacao': 100})
        self.assertEqual(limites.ler(self.root), {'tokens_por_consulta': None, 'tokens_por_dia': 500,
                                                  'tokens_por_dia_por_organizacao': 100})
        for invalido in ({'tokens_por_consulta': 0}, {'tokens_por_dia': 'muito'}, {'outro': 1},
                         {'tokens_por_dia_por_organizacao': 0}):
            with self.subTest(invalido=invalido):
                self.configurar(invalido)
                with self.assertRaises(ValueError):
                    limites.ler(self.root)

    def test_contador_diario_soma_bloqueia_e_reinicia_no_dia_seguinte(self):
        self.configurar({'tokens_por_dia': 100})
        self.assertEqual(limites.somar_dia(self.root, 60), 60)
        limites.conferir_dia(self.root)
        self.assertEqual(limites.somar_dia(self.root, 50), 110)
        with self.assertRaises(ValueError) as recusa:
            limites.conferir_dia(self.root)
        # The installation's total adds up every newsroom (accounts contract, 4.5): no number in it.
        self.assertEqual(str(recusa.exception), limites.DIA_INSTALACAO)
        self.assertNotRegex(str(recusa.exception), r'\d')
        self.assertEqual(erros.codigo_de(str(recusa.exception)), ('limite_tokens_dia', {}))
        with patch('limites.hoje', return_value='2099-01-01'):
            limites.conferir_dia(self.root)
            self.assertEqual(limites.somar_dia(self.root, 1), 1)

    def test_contador_por_redacao_soma_bloqueia_so_a_redacao_e_reinicia(self):
        self.configurar({'tokens_por_dia': 1000, 'tokens_por_dia_por_organizacao': 50})
        self.assertEqual(limites.somar_dia(self.root, 60, 'redacao-1'), 60)
        self.assertEqual(limites.somar_dia(self.root, 30, 'redacao-2'), 90)
        self.assertEqual(limites.somar_dia(self.root, 10), 100)  # no organization: only the total
        self.assertEqual([limites.dia_da_organizacao(self.root, r) for r in ('redacao-1', 'redacao-2', 'outra')],
                         [60, 30, 0])
        with self.assertRaises(ValueError) as recusa:
            limites.conferir_dia(self.root, 'redacao-1')
        self.assertEqual(str(recusa.exception),
                         'Limite diário de tokens da redação atingido (50). Novas perguntas voltam amanhã (UTC).')
        self.assertEqual(erros.codigo_de(str(recusa.exception)), ('limite_tokens_dia_redacao', {}))
        limites.conferir_dia(self.root, 'redacao-2')  # the other newsroom goes on
        limites.conferir_dia(self.root)
        self.configurar({'tokens_por_dia': 1000, 'tokens_por_dia_por_organizacao': None})
        limites.conferir_dia(self.root, 'redacao-1')  # null: only the total
        with patch('limites.hoje', return_value='2099-01-01'):
            self.assertEqual(limites.dia_da_organizacao(self.root, 'redacao-1'), 0)

    def test_contador_corrompido_nao_quebra_a_soma(self):
        (self.root / 'ajustes').mkdir()
        (self.root / 'ajustes/uso_diario.json').write_text(json.dumps({'dia': limites.hoje(), 'tokens': 'x'}), encoding='utf-8')
        self.assertEqual(limites.somar_dia(self.root, 5), 5)
        # A counter from before the newsrooms (no "organizacoes") or with a damaged one goes on from its total.
        for organizacoes in (None, 'x', {'redacao-1': 'x', '': 3}):
            with self.subTest(organizacoes=organizacoes):
                dados = {'dia': limites.hoje(), 'tokens': 7, **({} if organizacoes is None else {'organizacoes': organizacoes})}
                (self.root / 'ajustes/uso_diario.json').write_text(json.dumps(dados), encoding='utf-8')
                self.assertEqual(limites.somar_dia(self.root, 5, 'redacao-1'), 12)
                self.assertEqual(limites.dia_da_organizacao(self.root, 'redacao-1'), 5)

    def test_texto_e_argumentos_grandes_sao_truncados_com_aviso(self):
        curto = 'abc'
        self.assertEqual(limitar_texto(curto, 10), curto)
        longo = limitar_texto('x' * 100, 40)
        self.assertLessEqual(len(longo), 40 + 200)
        self.assertIn('truncado', longo)
        self.assertEqual(limitar_argumentos({'acao': 'buscar'}), {'acao': 'buscar'})
        grande = limitar_argumentos({'acao': 'guardar', 'texto': 'y' * 20000})
        self.assertTrue(grande['truncado'])
        self.assertLessEqual(len(json.dumps(grande, ensure_ascii=False)), 8500)


class LimitesConversaTest(unittest.TestCase):
    def setUp(self):
        integracao.CodexIntegrationTest.setUp(self)
        config = json.loads((self.root / 'configuracao.json').read_text(encoding='utf-8'))
        escrever_json(self.root / 'configuracao.json', {**config, 'limites': {'tokens_por_consulta': 100, 'tokens_por_dia': 1000}})

    start = integracao.CodexIntegrationTest.start

    def test_consulta_acima_do_limite_de_tokens_e_interrompida_com_erro_claro(self):
        identifier = self.start()
        rpc = self.manager.rpc
        rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': 'm', 'uso': {'entrada': 80, 'saida': 30}})
        aguardar_fim(self.manager, identifier)
        eventos = self.manager.eventos(identifier)['eventos']
        self.assertTrue(any(e['tipo'] == 'erro' and 'Limite de tokens por consulta' in e['dados']['mensagem'] for e in eventos))
        self.assertTrue(any(method == 'turn/interrupt' for method, _ in rpc.calls))

    def test_pergunta_recusada_quando_limite_diario_ja_foi_atingido(self):
        limites.somar_dia(self.root, 1000)
        with self.assertRaisesRegex(ValueError, 'Limite diário de uso da instalação'):
            self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta sintética.'})

    def configurar_dia(self, **valores):
        config = json.loads((self.root / 'configuracao.json').read_text(encoding='utf-8'))
        escrever_json(self.root / 'configuracao.json', {**config, 'limites': {'tokens_por_consulta': None, **valores}})

    def test_pergunta_recusada_quando_a_redacao_ja_atingiu_o_dia(self):
        # Until the Onda 2, every account is in the one organization (custo.ORGANIZACAO): its counter is the newsroom's.
        self.configurar_dia(tokens_por_dia=1000, tokens_por_dia_por_organizacao=50)
        limites.somar_dia(self.root, 50, custo.chaves_orcamento(None)['organizacao'])
        with self.assertRaisesRegex(ValueError, r'^Limite diário de tokens da redação atingido \(50\)'):
            self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta sintética.'})

    def interrompida_por(self, esperado):
        identifier = self.start()
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': 'm', 'uso': {'entrada': 80, 'saida': 30}})
        aguardar_fim(self.manager, identifier)
        mensagens = [e['dados']['mensagem'] for e in self.manager.eventos(identifier)['eventos'] if e['tipo'] == 'erro']
        self.assertTrue(any(m.startswith(esperado) for m in mensagens), mensagens)
        self.assertTrue(any(method == 'turn/interrupt' for method, _ in self.manager.rpc.calls))
        self.assertEqual(limites.dia_da_organizacao(self.root, custo.ORGANIZACAO), 110)
        return mensagens

    def test_dia_da_redacao_interrompe_a_pergunta(self):
        self.configurar_dia(tokens_por_dia=1000, tokens_por_dia_por_organizacao=50)
        self.interrompida_por('Limite diário de tokens da redação atingido (110 de 50).')

    def test_dia_da_instalacao_interrompe_sem_mostrar_numero(self):
        self.configurar_dia(tokens_por_dia=50)
        mensagens = self.interrompida_por('Limite diário de uso da instalação atingido. Tente novamente amanhã (UTC).')
        self.assertFalse([m for m in mensagens if re.search(r'\d', m)], mensagens)


if __name__ == '__main__':
    unittest.main()
