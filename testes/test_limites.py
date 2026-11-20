"""Spend and size limits enforced by the server; no model calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import escrever_json
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
        self.assertEqual(limites.ler(self.root), {'tokens_por_consulta': 3_000_000, 'tokens_por_dia': 30_000_000})
        self.configurar({'tokens_por_consulta': None, 'tokens_por_dia': 500})
        self.assertEqual(limites.ler(self.root), {'tokens_por_consulta': None, 'tokens_por_dia': 500})
        for invalido in ({'tokens_por_consulta': 0}, {'tokens_por_dia': 'muito'}, {'outro': 1}):
            with self.subTest(invalido=invalido):
                self.configurar(invalido)
                with self.assertRaises(ValueError):
                    limites.ler(self.root)

    def test_contador_diario_soma_bloqueia_e_reinicia_no_dia_seguinte(self):
        self.configurar({'tokens_por_dia': 100})
        self.assertEqual(limites.somar_dia(self.root, 60), 60)
        limites.conferir_dia(self.root)
        self.assertEqual(limites.somar_dia(self.root, 50), 110)
        with self.assertRaisesRegex(ValueError, 'Limite diário de tokens'):
            limites.conferir_dia(self.root)
        with patch('limites.hoje', return_value='2099-01-01'):
            limites.conferir_dia(self.root)
            self.assertEqual(limites.somar_dia(self.root, 1), 1)

    def test_contador_corrompido_nao_quebra_a_soma(self):
        (self.root / 'ajustes').mkdir()
        (self.root / 'ajustes/uso_diario.json').write_text(json.dumps({'dia': limites.hoje(), 'tokens': 'x'}), encoding='utf-8')
        self.assertEqual(limites.somar_dia(self.root, 5), 5)

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
        with self.assertRaisesRegex(ValueError, 'Limite diário de tokens'):
            self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta sintética.'})


if __name__ == '__main__':
    unittest.main()
