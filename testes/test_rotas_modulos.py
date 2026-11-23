"""Contrato da separação das rotas de ``interface_pesquisa`` em módulos (Onda 0).

Fixa a lista branca das operações ``POST /api/*``: acrescentar ou retirar uma operação
exige mudar este teste de propósito. Confere também que cada operação cai num único ramo
do despacho de ``do_POST`` e que nenhum ``rotas_*`` importa ``interface_pesquisa``, que
roda como ``__main__`` e seria carregado uma segunda vez. Sem servidor, rede nem modelo.
"""
import ast
from itertools import combinations
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import fontes_web  # noqa: E402
import interface_pesquisa  # noqa: E402
import rascunhos  # noqa: E402
import rotas_achados  # noqa: E402
import rotas_caderno  # noqa: E402
import rotas_conversa  # noqa: E402
import rotas_downloads  # noqa: E402
import rotas_equipe  # noqa: E402
import rotas_evidencia  # noqa: E402
import rotas_gestao  # noqa: E402
import rotas_redacao  # noqa: E402
import rotas_tabelas  # noqa: E402

OPERACOES = {
    'achados-briefing', 'achados-buscar', 'achados-catalogo', 'achados-detalhe', 'achados-evidencia',
    'achados-exportar', 'achados-original', 'achados-revisao-salvar', 'ambiente', 'analises',
    'apuracao-adicionar', 'apuracao-excluir', 'apuracao-exportar', 'apuracao-listar', 'apuracao-nota',
    'apuracao-nota-excluir', 'apuracao-nota-inserir', 'apuracao-nota-salvar', 'apuracao-notas',
    'apuracao-original', 'apuracao-salvar', 'buscar', 'cadastrar', 'caderno-cruzar', 'caderno-detalhe',
    'caso-incluir', 'caso-participantes', 'caso-responsavel', 'caso-retirar',
    'conta-atualizar', 'conta-senha-trocar', 'conta-sessao-encerrar', 'conta-sessoes', 'conta-sessoes-encerrar-outras',
    'conta-ver', 'equipe-atividade', 'equipe-desativar', 'equipe-listar', 'equipe-papel', 'equipe-reativar',
    'equipe-remover', 'equipe-teto', 'equipe-convidar', 'equipe-convite-reenviar', 'equipe-convite-cancelar',
    'equipe-recuperar', 'equipe-recuperar-confirmar', 'conta-email-trocar',
    'conta-fator-iniciar', 'conta-fator-confirmar', 'conta-fator-codigos', 'conta-fator-remover', 'conta-termos-aceitar',
    'conta-exportar', 'conta-excluir',
    'caderno-documentos', 'caderno-exportar', 'caderno-listar', 'caderno-original', 'caderno-salvar',
    'cobertura', 'codex-caderno-previa', 'codex-cancelar', 'codex-corpus-previa', 'codex-desligar',
    'codex-diligencias-previa', 'codex-documentos-cadastrar', 'codex-eventos', 'codex-listar',
    'codex-observacoes', 'codex-original', 'codex-perguntar', 'codex-retomar', 'codex-status',
    'comparar-documentos', 'comparar-evidencias', 'continuidade-resumo', 'diligencias-atualizar',
    'diligencias-criar', 'diligencias-listar', 'diligencias-original', 'diligencias-responder',
    'entrevistas-detalhe', 'entrevistas-editar', 'entrevistas-exportar', 'entrevistas-lacunas',
    'entrevistas-listar', 'entrevistas-preparar', 'entrevistas-responder', 'excluir', 'fontes-web-abrir',
    'fontes-web-capturar', 'fontes-web-listar', 'gerenciar-listar', 'hipoteses-atualizar', 'hipoteses-criar',
    'hipoteses-detalhe', 'hipoteses-listar', 'hipoteses-quadro', 'ia-config', 'ia-config-salvar',
    'inventario', 'ler', 'linha-tempo-atualizar', 'linha-tempo-criar', 'linha-tempo-detalhe',
    'linha-tempo-listar', 'lixeira-alcance', 'lixeira-apagar', 'mapa-entidade-atualizar',
    'mapa-entidade-criar', 'mapa-homonimos', 'mapa-relacao-atualizar', 'mapa-relacao-criar', 'mapa-ver',
    'original', 'preparar-pdfs', 'rascunhos-descartar', 'rascunhos-ler', 'rascunhos-listar',
    'rascunhos-salvar', 'redacao-conferir', 'redacao-criar', 'redacao-dividir', 'redacao-listar',
    'redacao-nova-versao', 'redacao-revisar', 'redacao-vincular', 'restaurar', 'sessao-sair',
    'tabelas-atualizar', 'tabelas-calcular', 'tabelas-corrigir', 'tabelas-criar', 'tabelas-detalhe',
    'tabelas-exportar', 'tabelas-historico-celula', 'tabelas-listar',
}


class RotasModulosTest(unittest.TestCase):
    def test_lista_branca_tem_as_138_operacoes(self):
        # The 114 of before without the six `contas-*`, withdrawn with the invitation by e-mail (P30), plus the four
        # `caso-*` (contrato de contas, 5.6), fourteen `conta-*` (5.4) and twelve `equipe-*` (5.5).
        self.assertEqual(len(OPERACOES), 138)
        self.assertEqual(len(interface_pesquisa.OPERACOES_API), 138, 'operação repetida na lista branca')
        self.assertFalse([o for o in interface_pesquisa.OPERACOES_API if o.startswith('contas-')])
        self.assertEqual(set(interface_pesquisa.OPERACOES_API), OPERACOES)

    def test_publicas_ficam_fora_da_lista_com_sessao(self):
        self.assertFalse(set(interface_pesquisa.OPERACOES_PUBLICAS) & OPERACOES)

    def test_cada_operacao_cai_num_unico_ramo_do_despacho(self):
        # Ramos de do_POST, na ordem do código; o que sobra vai para executar.
        ramos = {
            'sessao-sair': {'sessao-sair'},
            'downloads': set(rotas_downloads.OPERACOES),
            'captura web': {fontes_web.CAPTURAR},
            'gestao': set(rotas_gestao.OPERACOES),
            'equipe': set(rotas_equipe.OPERACOES) | set(interface_pesquisa.CONTA_PROPRIA),
            'conversa': set(rotas_conversa.OPERACOES),
        }
        for (a, x), (b, y) in combinations(ramos.items(), 2):
            self.assertFalse(x & y, f'{a} e {b} disputam {sorted(x & y)}')
        despachadas = set().union(*ramos.values())
        self.assertLessEqual(despachadas, OPERACOES)
        # O restante precisa ter destino em executar, sem cair em "Operação desconhecida".
        executar = {o for o in OPERACOES - despachadas
                    if o in interface_pesquisa.CONSULTA_OPERACOES or o.startswith(rotas_caderno.PREFIXOS)
                    or o in rotas_evidencia.OPERACOES or o in rotas_tabelas.OPERACOES
                    or o in rotas_redacao.OPERACOES or o in rascunhos.OPERACOES or o in fontes_web.OPERACOES
                    or o in rotas_achados.OPERACOES}
        self.assertEqual(executar, OPERACOES - despachadas)
        self.assertLessEqual(set(rotas_downloads.ORIGINAIS_PASSAGEM), executar)

    def test_nenhum_modulo_de_rota_importa_interface_pesquisa(self):
        modulos = sorted(SCRIPTS.glob('rotas_*.py'))
        self.assertGreaterEqual(len(modulos), 11)
        for caminho in modulos:
            arvore = ast.parse(caminho.read_text(encoding='utf-8'))
            importados = {a.name.split('.')[0] for n in ast.walk(arvore) if isinstance(n, ast.Import) for a in n.names}
            importados |= {(n.module or '').split('.')[0] for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom)}
            self.assertNotIn('interface_pesquisa', importados, caminho.name)


if __name__ == '__main__':
    unittest.main()
