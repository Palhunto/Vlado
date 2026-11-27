"""Salvar cada quadro pela tela, nos modos ``local`` e ``piloto``, num navegador de verdade contra o servidor de verdade.

Os testes de rota sempre mandam o ``autor`` e nenhum teste de navegador salvava um quadro no modo local: por isso o 400 de autor que o ``--modo local`` dava
desde 3c1b363 (formularios.js não enviava o autor, e o modo local não tem conta que o dê) passou despercebido. Aqui o Chromium do Playwright abre a apuração
``alpha`` e salva pela tela uma hipótese, um acontecimento, duas entidades, uma ligação e uma tabela, sem montar corpo nenhum à mão (``qa_quadros_salvar.cjs``),
e confirma uma sugestão da IA e descarta outra. Depois se confere o que o servidor guardou: cada item existe, e a autoria é a certa. No modo local, o nome
digitado no campo Autor, declarado pelo usuário; no piloto, o nome da conta, autenticado pela conta da Mesa, sem que a tela o peça.

Sem Node ou sem o Playwright, o teste é pulado (e reprova com ``VLADO_EXIGIR_PLAYWRIGHT=1``). Dados sintéticos, sem modelo e sem rede.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from auxiliar_node import requer_navegador_node
import acesso
import caderno
import fator_de_teste
import hipoteses
import linha_tempo
import mapa_relacoes as mapa
import registros_achados
import rotas_evidencia
import sugestoes_quadros as sq
import tabelas_apuracao as tabelas
from fixture_achados import Ambiente
from interface_pesquisa import Servidor
from test_acesso import RAPIDO, SENHA
from test_sugestoes_quadros import CANDIDATOS

CASO = 'alpha'
AUTOR = 'Editora sintética'
ORIGEM_PILOTO = 'https://vlado.test'


@requer_navegador_node
class SalvarQuadrosNoNavegadorTest(unittest.TestCase):
    """Base: a apuração sintética de ``fixture_achados`` (A001 sustentado, E001) com os candidatos da IA gravados, e um servidor real num modo."""
    modo = None

    def setUp(self):
        env, _ = Ambiente.copia_completa()
        self.addCleanup(env.cleanup)
        self.root = env.root
        dados, _ = registros_achados.carregar(self.root, CASO, 'R001', 'r2')
        sq.gravar(env.run(), dados, CANDIDATOS, '1.3.0')
        ambiente = patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': '', 'VLADO_SEGREDOS': ''})
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def servir(self, **argumentos):
        self.server = Servidor(('127.0.0.1', 0), self.root, **argumentos)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def navegar(self, **entrada):
        entrada = {'porta': self.server.server_port, 'modo': self.modo, 'caso': CASO, **entrada}
        with patch.object(acesso, 'TENTATIVAS_IP_MINUTO', 10000):
            processo = subprocess.run(['node', str(Path(__file__).with_name('qa_quadros_salvar.cjs')), json.dumps(entrada)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=420, cwd=RAIZ)
        self.assertEqual(processo.returncode, 0, (processo.stdout + processo.stderr)[-3500:])
        resultado = json.loads(processo.stdout.strip().splitlines()[-1])
        self.assertEqual(resultado['salvos'], ['hipótese', 'acontecimento', 'entidade pessoa', 'entidade organizacao', 'ligação', 'tabela'])
        self.assertEqual(resultado['decisoes'], ['Confirmar:hipotese', 'Descartar:acontecimento'])

    def conferir_autoria(self, autor, origem, conta_id=None):
        """Os itens criados pela tela (e a hipótese que a confirmação da sugestão criou), com a autoria de cada evento."""
        itens = {'hipótese': hipoteses.listar(self.root, CASO), 'acontecimento': linha_tempo.listar(self.root, CASO),
                 'entidade': mapa.listar_entidades(self.root, CASO), 'ligação': mapa.listar_relacoes(self.root, CASO),
                 'tabela': tabelas.listar(self.root, CASO)}
        contagem = {quadro: len(lista) for quadro, lista in itens.items()}
        # 2 hipóteses: a digitada e a da sugestão confirmada; 1 acontecimento (a sugestão dele foi descartada, não confirmada)
        self.assertEqual(contagem, {'hipótese': 2, 'acontecimento': 1, 'entidade': 2, 'ligação': 1, 'tabela': 1})
        for quadro, lista in itens.items():
            for item in lista:
                self.assertFalse(item['divergente'], f'{quadro}: {item.get("erro")}')
                for evento in item['historico']:
                    with self.subTest(quadro=quadro, item=item['id']):
                        self.assertEqual((evento['autor'], evento['origem_autoria']), (autor, origem))
                        self.assertEqual(evento.get('conta_id'), conta_id)
        enunciados = sorted(h['estado']['enunciado'] for h in itens['hipótese'])
        self.assertEqual(enunciados, ['A Construtora Alfa declarou valor 12 no Contrato 041/2025.', 'Hipótese salva pela tela (QA).'])
        decididas = [s for q in ('hipoteses', 'linha_tempo')
                     for s in rotas_evidencia.executar(self.root, 'sugestoes-listar', {'caso': CASO, 'quadro': q, 'incluir_decididas': True})['sugestoes']
                     if s['estado'] != 'aberta']
        self.assertEqual(sorted((s['estado'], s['decisao']['acao'], s['decisao']['por']) for s in decididas),
                         [('confirmada', 'confirmar', autor), ('descartada', 'descartar', autor)])


class SalvarQuadrosModoLocalTest(SalvarQuadrosNoNavegadorTest):
    modo = 'local'

    def test_cada_quadro_salva_pela_tela_com_o_autor_declarado(self):
        self.servir()
        self.navegar(origem=self.server.origin, autor=AUTOR)
        self.conferir_autoria(AUTOR, caderno.AUTORIA_DECLARADA)


class SalvarQuadrosModoPilotoTest(SalvarQuadrosNoNavegadorTest):
    modo = 'piloto'

    def test_cada_quadro_salva_pela_tela_com_o_nome_da_conta(self):
        hasher = patch.object(acesso, "_HASHER", RAPIDO); hasher.start()
        self.addCleanup(hasher.stop)
        acesso.limpar_limites()
        self.addCleanup(fator_de_teste.esquecer, self.root)
        redacao = acesso.criar_redacao(self.root, 'Redação Alfa')['id']
        acesso.atribuir_caso(self.root, CASO, redacao)
        conta, token = acesso.criar_conta(self.root, 'Rita Reporter', 'rita.reporter', papel='reporter', casos=[CASO], organizacao=redacao, por='operador')
        acesso.ativar(self.root, token, SENHA)
        acesso.definir_responsavel(self.root, CASO, conta['id'], 'operador', redacao)
        self.servir(modo='piloto', origem=ORIGEM_PILOTO)
        self.navegar(origem=ORIGEM_PILOTO, login='rita.reporter', senha=SENHA)
        self.conferir_autoria('Rita Reporter', caderno.AUTORIA_CONTA, conta['id'])


if __name__ == '__main__':
    unittest.main()
