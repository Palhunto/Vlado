"""O formulário da tabela contra o servidor de verdade (interface/formularios.js, testes/tabelas_form.cjs).

O teste do navegador usa um servidor simulado; aqui cada corpo tem a forma que o formulário envia (colunas com id
gerado do nome, células {valor, fonte} nas linhas novas, as registradas de volta como {valor, fonte, estado}, as
evidências em ``referencia``/``papel``/``suporte``/``natureza``/``justificativa``) e passa por ``tabelas_apuracao``,
que aplica as regras de verdade. Dados sintéticos; sem modelo nem rede.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente
import tabelas_apuracao as tabelas
from test_tabelas_apuracao import Fontes

COLUNAS = [{'id': 'descricao', 'nome': 'Descrição', 'tipo': 'texto', 'moeda': None, 'unidade': None},
           {'id': 'valor_pago', 'nome': 'Valor pago', 'tipo': 'monetario', 'moeda': 'BRL', 'unidade': None},
           {'id': 'quantidade', 'nome': 'Quantidade', 'tipo': 'numero', 'moeda': None, 'unidade': 'itens'}]


class FormularioTabelaTest(Fontes, unittest.TestCase):
    def setUp(self):
        env, (_, _, _, second) = Ambiente.copia_completa(); self.addCleanup(env.cleanup)
        self.preparar(env, second)

    def pedido(self, **campos):
        return {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Editora B', **campos}

    def evidencias_do_detalhe(self, detalhe):
        # como camposDoVinculo: só o que a pessoa vê e decide, não a forma salva
        return [{k: e[k] for k in ('referencia', 'papel', 'suporte', 'natureza', 'justificativa')} for e in detalhe['evidencias']]

    def test_criar_editar_e_corrigir_com_os_corpos_do_formulario(self):
        criada = tabelas.salvar(self.root, self.pedido(
            titulo='Pagamentos 2025', descricao='', colunas=COLUNAS, evidencias=[self.link(self.ia())],
            linhas=[{'celulas': {'descricao': {'valor': 'Pagamento de janeiro', 'fonte': None},
                                 'valor_pago': {'valor': '8750000.50', 'fonte': 0}, 'quantidade': {'valor': '12', 'fonte': None}}}]), 'criar')
        detalhe = tabelas.tabela(self.root, 'alpha', criada['id'])
        self.assertEqual(detalhe['linhas'][0]['celulas']['valor_pago']['valor'], '8750000.50')
        self.assertEqual(detalhe['linhas'][0]['celulas']['descricao']['estado'], 'pendente', 'sem fonte: ○ a conferir')

        # editar: as colunas e linhas registradas voltam como o detalhe as entrega; uma coluna e uma linha novas vão ao fim
        colunas = [{k: c[k] for k in ('id', 'nome', 'tipo', 'moeda', 'unidade')} for c in detalhe['colunas']]
        colunas.append({'id': 'observacao', 'nome': 'Observação', 'tipo': 'texto', 'moeda': None, 'unidade': None})
        antigas = [{'id': l['id'], 'celulas': {k: {'valor': x['valor'], 'fonte': x['fonte'], 'estado': x['estado']} for k, x in l['celulas'].items()}} for l in detalhe['linhas']]
        nova = {'celulas': {'descricao': {'valor': 'Pagamento de fevereiro', 'fonte': 0}, 'valor_pago': {'valor': '980.00', 'fonte': 0},
                            'quantidade': {'valor': '3', 'fonte': None}, 'observacao': {'valor': None, 'fonte': None}}}
        editada = tabelas.salvar(self.root, self.pedido(
            id=criada['id'], anterior_sha256=detalhe['sha256'], titulo='Pagamentos 2025', descricao='', colunas=colunas, linhas=antigas + [nova],
            evidencias=self.evidencias_do_detalhe(detalhe)), 'atualizar')
        detalhe = tabelas.tabela(self.root, 'alpha', editada['id'])
        self.assertEqual([c['id'] for c in detalhe['colunas']], ['descricao', 'valor_pago', 'quantidade', 'observacao'])
        self.assertEqual([l['id'] for l in detalhe['linhas']], ['L0001', 'L0002'])
        self.assertEqual(detalhe['linhas'][0]['celulas']['observacao']['estado'], 'pendente', 'a coluna nova nasce vazia nas linhas antigas')

        # editar de novo, só com o título mudado e as mesmas linhas de volta (o que o formulário envia sem acrescentar nada)
        antigas = [{'id': l['id'], 'celulas': {k: {'valor': x['valor'], 'fonte': x['fonte'], 'estado': x['estado']} for k, x in l['celulas'].items() if k != 'observacao'}} for l in detalhe['linhas']]
        for l, original in zip(antigas, detalhe['linhas']):
            l['celulas']['observacao'] = {'valor': original['celulas']['observacao']['valor'], 'fonte': original['celulas']['observacao']['fonte'], 'estado': original['celulas']['observacao']['estado']}
        colunas = [{k: c[k] for k in ('id', 'nome', 'tipo', 'moeda', 'unidade')} for c in detalhe['colunas']]
        renomeada = tabelas.salvar(self.root, self.pedido(
            id=editada['id'], anterior_sha256=detalhe['sha256'], titulo='Pagamentos de 2025', descricao='Planilha de pagamentos.', colunas=colunas, linhas=antigas,
            evidencias=self.evidencias_do_detalhe(detalhe)), 'atualizar')
        detalhe = tabelas.tabela(self.root, 'alpha', renomeada['id'])
        self.assertEqual(detalhe['titulo'], 'Pagamentos de 2025')

        # corrigir uma célula: mudar o que existia pede justificativa; preencher o que faltava, não
        corrigida = tabelas.corrigir(self.root, self.pedido(
            id=detalhe['id'], anterior_sha256=detalhe['sha256'],
            correcoes=[{'linha': 'L0001', 'coluna': 'valor_pago', 'valor': '1020.00', 'fonte': 0, 'justificativa': 'A planilha original traz 1.020,00.'}]))
        detalhe = tabelas.tabela(self.root, 'alpha', corrigida['id'])
        celula = detalhe['linhas'][0]['celulas']['valor_pago']
        self.assertEqual((celula['valor'], celula['estado']), ('1020.00', 'corrigido_manual'))
        self.assertEqual(celula['ultima_correcao']['valor_anterior'], '8750000.50')
        with self.assertRaises(ValueError) as erro:
            tabelas.corrigir(self.root, self.pedido(id=detalhe['id'], anterior_sha256=detalhe['sha256'],
                correcoes=[{'linha': 'L0001', 'coluna': 'valor_pago', 'valor': '1030.00', 'fonte': 0, 'justificativa': ''}]))
        self.assertIn('justificativa', str(erro.exception))
        preenchida = tabelas.corrigir(self.root, self.pedido(
            id=detalhe['id'], anterior_sha256=detalhe['sha256'],
            correcoes=[{'linha': 'L0001', 'coluna': 'descricao', 'valor': 'Pagamento de janeiro', 'fonte': 0, 'justificativa': ''}]))
        detalhe = tabelas.tabela(self.root, 'alpha', preenchida['id'])
        self.assertEqual(detalhe['linhas'][0]['celulas']['descricao']['estado'], 'extraido')

    def test_a_evidencia_que_e_fonte_de_celula_nao_sai(self):
        criada = tabelas.salvar(self.root, self.pedido(
            titulo='T', descricao='', colunas=COLUNAS[:2], evidencias=[self.link(self.ia())],
            linhas=[{'celulas': {'descricao': {'valor': 'x', 'fonte': 0}, 'valor_pago': {'valor': '1', 'fonte': None}}}]), 'criar')
        detalhe = tabelas.tabela(self.root, 'alpha', criada['id'])
        antigas = [{'id': l['id'], 'celulas': {k: {'valor': x['valor'], 'fonte': x['fonte'], 'estado': x['estado']} for k, x in l['celulas'].items()}} for l in detalhe['linhas']]
        with self.assertRaises(ValueError) as erro:
            tabelas.salvar(self.root, self.pedido(id=criada['id'], anterior_sha256=detalhe['sha256'], titulo='T', descricao='',
                                                  colunas=[{k: c[k] for k in ('id', 'nome', 'tipo', 'moeda', 'unidade')} for c in detalhe['colunas']], linhas=antigas, evidencias=[]), 'atualizar')
        self.assertIn('fonte de célula', str(erro.exception))


if __name__ == '__main__':
    unittest.main()
