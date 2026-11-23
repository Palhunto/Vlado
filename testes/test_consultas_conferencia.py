"""T1 (SEG-06): a conferência interna de evidência indexada não grava registro bruto de consulta.

Cada carga de revisão (``registros_achados.carregar``, que refaz a conferência técnica de cada evidência
indexada em toda a cadeia de revisões), cada evidência resolvida (``evidencias.resolver``, usada por Conferir,
Pedidos e prazos e Quadros) e o detalhe do índice de achados passavam por ``indice_sqlite.ler_passagem``, que
grava um JSON em ``saidas/consultas_sqlite/``: abrir a tela gastava o teto de arquivos por rodada sem ninguém
consultar. O 'Ver contexto' de uma evidência (``indice_achados.evidencia``, ``achados-evidencia``) é leitura da
pessoa e continua gravando um registro por clique (W1). A procedência da evidência já está no próprio
registro (referência, geração, ``indice_id``, ``banco_sha256``, trecho e linhas); o registro bruto que o
AGENTS.md manda preservar é o das consultas (busca, cobertura e leitura de contexto), e esse continua.
Dados sintéticos apenas.
"""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fixture_achados import Ambiente  # noqa: E402
import evidencias  # noqa: E402
import indice_achados  # noqa: E402
import indice_sqlite  # noqa: E402
from registros_achados import carregar, conferir_evidencia, publicar  # noqa: E402

ABERTURAS = 10


class ConferenciaSemRegistroTest(unittest.TestCase):
    def setUp(self):
        self.fx, (self.inicial, self.revisada, _, self.segunda) = Ambiente.copia_completa()
        self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root
        self.pasta = self.fx.run() / 'saidas' / 'consultas_sqlite'
        self.indexadas = [e for e in self.revisada['evidencias'] if e['modo'] == 'indexada']
        self.assertTrue(self.indexadas, 'a fixture precisa de evidência indexada')

    def registros(self):
        return sorted(p.name for p in self.pasta.glob('*.json')) if self.pasta.exists() else []

    def abrir_tudo(self):
        """What opening Conferir, Pedidos e prazos, Quadros and the findings index does, once."""
        carregar(self.root, 'alpha', 'R001', 'r2')  # validates r2 and, through it, r1
        for item in self.indexadas:
            ref = {'tipo': 'ia', 'caso_id': 'alpha', 'rodada': 'R001', 'revisao': 'r2',
                   'registros_sha256': self.segunda['manifesto']['registros_sha256'], 'evidencia_id': item['id']}
            self.assertEqual(evidencias.resolver(self.root, 'alpha', ref)['referencia'], ref)
        indice_achados.detalhe(self.root, 'alpha', 'R001', 'r2', 'g2', 'A001')

    def test_abrir_n_vezes_nao_grava_registro_de_consulta(self):
        antes = self.registros()
        for _ in range(ABERTURAS):
            self.abrir_tudo()
        self.assertEqual(self.registros(), antes)

    def test_ver_contexto_grava_um_registro_por_clique(self):
        # W1: 'Ver contexto' in Conferir is the person's reading of the context, which AGENTS.md keeps.
        item = self.indexadas[0]
        for clique in range(1, 4):
            antes = set(self.registros())
            resposta = indice_achados.evidencia(self.root, 'alpha', 'R001', 'r2', item['id'])
            novos = set(self.registros()) - antes
            self.assertEqual(len(novos), 1, f'clique {clique}')
            registro = json.loads((self.pasta / novos.pop()).read_text(encoding='utf-8'))
            self.assertEqual((registro['operacao'], registro['passagem']['referencia']),
                             ('ler', item['indice']['referencia']))
            self.assertEqual(resposta['evidencia'], item)
        antes = self.registros()
        self.abrir_tudo()  # the load of the review still writes nothing
        self.assertEqual(self.registros(), antes)

    def test_publicar_revisao_nao_grava_registro_de_consulta(self):
        antes = self.registros()
        terceira = self.fx.sucessora(self.revisada, self.segunda, 'r3')
        publicar(self.root, 'alpha', 'R001', terceira)
        self.assertEqual(self.registros(), antes)

    def test_conferencia_continua_recusando_evidencia_divergente(self):
        # Not writing the record does not weaken the check: a passage of another range is still refused.
        item = {**self.indexadas[0], 'localizador': {**self.indexadas[0]['localizador'], 'linha_inicio': 2, 'linha_fim': 2}}
        with self.assertRaisesRegex(ValueError, 'Intervalo fora da passagem|Trecho literal'):
            conferir_evidencia(self.root, 'alpha', 'R001', item)
        self.assertEqual(conferir_evidencia(self.root, 'alpha', 'R001', self.indexadas[0])['evidencia'], self.indexadas[0])

    def test_busca_cobertura_e_leitura_de_contexto_continuam_gravando(self):
        antes = len(self.registros())
        busca = indice_sqlite.pesquisar(self.root, 'alpha', 'R001', 'valor')
        indice_sqlite.cobertura(self.root, 'alpha', 'R001')
        leitura = indice_sqlite.ler_passagem(self.root, 'alpha', 'R001', busca['resultados'][0]['referencia'])
        self.assertEqual(len(self.registros()), antes + 3)
        self.assertIn(Path(leitura['arquivo_log']).name, self.registros())
        interna = indice_sqlite.ler_passagem(self.root, 'alpha', 'R001', busca['resultados'][0]['referencia'],
                                             registrar=False)
        self.assertNotIn('arquivo_log', interna)
        self.assertEqual(interna['passagem'], leitura['passagem'])
        self.assertEqual(len(self.registros()), antes + 3)

    def test_aberturas_nao_gastam_o_teto_seg06(self):
        if not hasattr(indice_sqlite, 'TETO_ARQUIVOS_PADRAO'):
            self.skipTest('o teto SEG-06 (75eb1c6) não está nesta base; vale na integração')
        teto = len(self.registros()) + 1  # one more raw query file fits, no more
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': str(teto), 'VLADO_CONSULTAS_MAX_MB': ''}):
            for _ in range(ABERTURAS):
                self.abrir_tudo()
            indice_sqlite.pesquisar(self.root, 'alpha', 'R001', 'valor')  # the one real query still fits
            with self.assertRaisesRegex(ValueError, 'Teto do registro de consultas'):
                indice_sqlite.pesquisar(self.root, 'alpha', 'R001', 'valor')
            self.abrir_tudo()  # past the ceiling, opening the screens still works


if __name__ == '__main__':
    unittest.main()
