"""SEG-06: o registro bruto de cada consulta ao índice (saidas/consultas_sqlite/) tem teto por rodada.

Sem teto, uma rodada com milhares de consultas encheria o volume de dados. Passado o teto, a consulta é recusada com mensagem clara,
nada é apagado e o registro já feito fica preservado. Dados sintéticos apenas; fixture própria (não altera as compartilhadas)."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import PARTES, escrever_json, fluxo_esperado, manifesto_prompts
from criar_caso import criar_caso
from nova_rodada import criar_rodada
from selecionar_caso import selecionar
import indice_sqlite
from indice_sqlite import cobertura, ler_passagem, pesquisar


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'prompts').mkdir()
        for nome in PARTES:
            (self.root / 'prompts' / nome).write_text('# Fixture sintetica\n', encoding='utf-8')
        (self.root / 'prompts' / 'FLUXO_COMPLETO.md').write_bytes(fluxo_esperado(self.root))
        escrever_json(self.root / 'prompts' / 'manifesto_prompts.json', manifesto_prompts(self.root))
        (self.root / 'AGENTS.md').write_text('Fixture tecnica.', encoding='utf-8')
        escrever_json(self.root / 'configuracao.json', {'versao': '1.1.0', 'caso_ativo': None, 'manifesto_ativo': None,
                                                        'maximo_documentos_inicial': 20, 'indice_sqlite': True})
        arquivo = self.root / 'alpha.txt'
        arquivo.write_text('Ação técnica sintética. Código AB-123/2026.\nSegunda linha.\n', encoding='utf-8')
        criar_caso(self.root, 'alpha', 'Caso sintetico alpha', [arquivo], 'sinteticos')
        selecionar(self.root, 'alpha')
        self.run_dir = criar_rodada(self.root, 'R001', 'Pergunta sintetica de armazenamento, sem apuracao.')
        self.pasta = self.run_dir / 'saidas' / 'consultas_sqlite'
        env = patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': '', 'VLADO_CONSULTAS_MAX_MB': ''})
        env.start()
        self.addCleanup(env.stop)

    def registros(self) -> list[Path]:
        return sorted(self.pasta.glob('*.json')) if self.pasta.exists() else []

    def consultar(self, n=1):
        return [pesquisar(self.root, 'alpha', 'R001', 'acao') for _ in range(n)]


class TetoPorArquivosTest(Base):
    def test_ate_o_teto_cada_consulta_tem_o_seu_registro_bruto_como_sempre(self):
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': '5'}):
            respostas = self.consultar(5)
        self.assertEqual(len(self.registros()), 5)
        for resposta in respostas:  # o contrato de antes: o registro é a resposta, na íntegra
            self.assertEqual(json.loads((self.run_dir / resposta['arquivo_log']).read_text(encoding='utf-8')), resposta)

    def test_passado_o_teto_a_consulta_e_recusada_e_nada_e_apagado_nem_gravado(self):
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': '3'}):
            self.consultar(3)
            antes = {p.name: p.read_bytes() for p in self.registros()}
            with self.assertRaisesRegex(ValueError, r'Teto do registro de consultas desta rodada atingido \(3 arquivos'):
                pesquisar(self.root, 'alpha', 'R001', 'acao')
            with self.assertRaisesRegex(ValueError, 'Teto do registro'):
                cobertura(self.root, 'alpha', 'R001')
        depois = {p.name: p.read_bytes() for p in self.registros()}
        self.assertEqual(depois, antes, 'o registro bruto anterior está intacto e nenhum novo foi gravado')

    def test_ler_passagem_existente_tambem_respeita_o_teto(self):
        primeira = self.consultar(1)[0]
        referencia = primeira['resultados'][0]['referencia']
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': '1'}):
            with self.assertRaisesRegex(ValueError, 'Teto do registro'):
                ler_passagem(self.root, 'alpha', 'R001', referencia)

    def test_a_mensagem_nao_traz_caminho_do_servidor(self):
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': '1'}):
            self.consultar(1)
            with self.assertRaises(ValueError) as contexto:
                self.consultar(1)
        mensagem = str(contexto.exception)
        for proibido in (str(self.root), str(self.root).replace('\\', '/'), 'execucoes', 'saidas', 'consultas_sqlite', '.json'):
            self.assertNotIn(proibido, mensagem)

    def test_outra_rodada_tem_o_seu_proprio_teto(self):
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': '2'}):
            self.consultar(2)
            with self.assertRaises(ValueError):
                self.consultar(1)
            criar_rodada(self.root, 'R002', 'Outra pergunta sintetica, sem apuracao.')
            resposta = pesquisar(self.root, 'alpha', 'R002', 'acao')
            self.assertTrue((self.root / 'execucoes/alpha/R002' / resposta['arquivo_log']).is_file())


class TetoPorTamanhoTest(Base):
    def test_rodada_com_muitos_bytes_de_registro_recusa(self):
        self.pasta.mkdir(parents=True, exist_ok=True)
        (self.pasta / 'grande.json').write_bytes(b'x' * (1 << 20))  # 1 MiB de registros anteriores
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_MB': '1'}):
            with self.assertRaisesRegex(ValueError, r'Teto do registro.*1 MB'):
                self.consultar(1)
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_MB': '2'}):
            self.assertEqual(len(self.consultar(1)), 1)  # abaixo do teto: segue funcionando

    def test_padroes_e_valor_invalido(self):
        self.assertEqual((indice_sqlite.TETO_ARQUIVOS_PADRAO, indice_sqlite.TETO_MB_PADRAO), (2000, 256))
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': 'muitos'}):
            with self.assertRaisesRegex(ValueError, 'VLADO_CONSULTAS_MAX_ARQUIVOS'):
                self.consultar(1)

    def test_sem_a_pasta_de_registros_ainda_nao_ha_o_que_contar(self):
        self.assertFalse(self.pasta.exists())
        indice_sqlite._conferir_teto_do_registro(self.pasta)  # não levanta


class PelaInterfaceTest(Base):
    def test_o_teto_chega_a_quem_consulta_como_erro_de_validacao(self):
        import interface_pesquisa
        with patch.dict(os.environ, {'VLADO_CONSULTAS_MAX_ARQUIVOS': '1'}):
            interface_pesquisa.executar(self.root, 'buscar', {'caso': 'alpha', 'rodada': 'R001', 'consulta': 'acao'})
            with self.assertRaisesRegex(ValueError, 'Teto do registro de consultas'):
                interface_pesquisa.executar(self.root, 'buscar', {'caso': 'alpha', 'rodada': 'R001', 'consulta': 'acao'})

    def test_o_texto_da_busca_nao_vai_para_nenhum_registro_global(self):
        """O texto da consulta fica só no registro bruto da rodada (dentro do caso); o registro de auditoria nunca o vê."""
        import registro_acesso
        fonte = Path(registro_acesso.__file__).read_text(encoding='utf-8')
        for campo in ('consulta', 'pergunta', 'trecho'):
            self.assertNotIn(f"'{campo}'", fonte.split('CAMPOS = {', 1)[1].split('}\n', 1)[0], campo)


class ConfiguracaoNoComposeTest(unittest.TestCase):
    RAIZ = Path(__file__).resolve().parents[1]

    def test_compose_repassa_os_dois_tetos_so_ao_app_e_os_exemplos_trazem_os_padroes(self):
        compose = (self.RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        servico = compose.split('\n  vlado:\n', 1)[1].split('\n  caddy:\n', 1)[0]
        for nome in ('VLADO_CONSULTAS_MAX_ARQUIVOS', 'VLADO_CONSULTAS_MAX_MB'):
            self.assertIn(f'      {nome}: ${{{nome}:-}}\n', servico, nome)
            self.assertEqual(compose.count(f'      {nome}: '), 1, f'{nome} só no app')
        for exemplo in ('homologacao', 'editorial', 'demonstracao'):
            texto = (self.RAIZ / 'deploy' / 'ambientes' / f'{exemplo}.env.example').read_text(encoding='utf-8')
            self.assertIn(f'# VLADO_CONSULTAS_MAX_ARQUIVOS={indice_sqlite.TETO_ARQUIVOS_PADRAO}', texto, exemplo)
            self.assertIn(f'# VLADO_CONSULTAS_MAX_MB={indice_sqlite.TETO_MB_PADRAO}', texto, exemplo)


if __name__ == '__main__':
    unittest.main()
