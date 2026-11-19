"""Tabelas de apuração conferíveis (scripts/tabelas_apuracao.py e scripts/rotas_tabelas.py), com fontes sintéticas.

Células com fonte do contrato do Core, correção gravada como evento novo, cálculos com decimal.Decimal
que recusam moedas e unidades diferentes, exportação CSV com a fonte de cada célula e rotas HTTP da
Mesa (sessão, convidado e outro caso). Sem modelo nem rede.
"""
import csv
from decimal import Decimal, ROUND_HALF_UP
import http.client
import io
import json
from pathlib import Path
import sys
import threading
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import sha256
from fixture_achados import Ambiente
from interface_pesquisa import Servidor
import caderno
import rotas_tabelas
import tabelas_apuracao as tabelas
import test_autorizacao as autorizacao  # module import: its TestCases are not re-collected here

COLUNAS = [{'id': 'contrato', 'nome': 'Contrato', 'tipo': 'texto'},
           {'id': 'assinatura', 'nome': 'Assinatura', 'tipo': 'data'},
           {'id': 'valor', 'nome': 'Valor', 'tipo': 'monetario', 'moeda': 'BRL'},
           {'id': 'valor_usd', 'nome': 'Valor em dólar', 'tipo': 'monetario', 'moeda': 'USD'},
           {'id': 'valor_mil', 'nome': 'Valor em milhares', 'tipo': 'monetario', 'moeda': 'BRL', 'unidade': 'mil'},
           {'id': 'peso', 'nome': 'Peso', 'tipo': 'numero', 'unidade': 'kg'},
           {'id': 'peso_t', 'nome': 'Peso em toneladas', 'tipo': 'numero', 'unidade': 't'}]


def linhas():
    return [{'celulas': {'contrato': {'valor': 'Contrato 1', 'fonte': 0}, 'assinatura': {'valor': '2021-03-12', 'fonte': 0},
                         'valor': {'valor': '12', 'fonte': 0}, 'valor_usd': {'valor': '3.50', 'fonte': 0},
                         'valor_mil': {'valor': '0.012', 'fonte': 0}, 'peso': {'valor': '1.5', 'fonte': 0},
                         'peso_t': {'valor': '2', 'fonte': 0}}},
            {'celulas': {'contrato': {'valor': '=HYPERLINK("http://x")'}, 'valor': {'valor': '14.25', 'fonte': 1}}},
            {'celulas': {'contrato': {'fonte': 1}, 'assinatura': {'valor': '2021'}, 'valor': {'valor': '007.50', 'fonte': 1},
                         'peso': {'valor': '-0.00', 'fonte': 0}}}]


class Fontes:
    """Referências sintéticas das duas origens do contrato (achados da IA e fonte do caderno)."""

    def preparar(self, env, second):
        self.env, self.root = env, env.root
        self.registros = second['manifesto']['registros_sha256']
        docs = caderno.documentos(self.root, 'alpha'); doc = docs['documentos'][0]
        self.nota = caderno.salvar(self.root, {
            'caso': 'alpha', 'origem_id': docs['origem_id'], 'documento_id': doc['documento_id'],
            'documento_sha256': doc['sha256'], 'pagina_pdf': None, 'localizador': 'Linha 2',
            'trecho': 'Outra versão declara valor 14.', 'titulo': 'Trecho humano', 'anotacao': '',
            'autor': 'Repórter A', 'tipo': 'trecho', 'transcricao_manual': False, 'requisicao_id': uuid.uuid4().hex})

    def ia(self, eid='E001', case='alpha'):
        return {'tipo': 'ia', 'caso_id': case, 'rodada': 'R001', 'revisao': 'r2', 'registros_sha256': self.registros,
                'evidencia_id': eid}

    def humana(self):
        return {'tipo': 'humana', 'caso_id': 'alpha', 'registro_id': self.nota['registro']['id'],
                'sha256': self.nota['sha256'], 'fonte': 0}

    @staticmethod
    def link(ref, papel='suporte'):
        return {'referencia': ref, 'papel': papel, 'suporte': 'sustentado' if papel != 'contexto' else 'nao_revisado',
                'natureza': 'declaracao_documental', 'justificativa': 'Trecho sintético que traz o valor.'}

    @staticmethod
    def base(caso='alpha', **fields):
        return {'caso': caso, 'requisicao_id': uuid.uuid4().hex, 'autor': 'Editora B', **fields}

    def corpo(self, **fields):
        return self.base(**{'titulo': 'Contratos sintéticos', 'colunas': COLUNAS, 'linhas': linhas(),
                            'evidencias': [self.link(self.ia()), self.link(self.humana())], **fields})


class TabelasApuracaoTest(Fontes, unittest.TestCase):
    def setUp(self):
        env, (_, _, _, second) = Ambiente.copia_completa(); self.addCleanup(env.cleanup)
        self.preparar(env, second)

    def arquivos(self):
        # Resolver evidência indexada acrescenta o log de consulta exigido pelo índice (somente acréscimo).
        return {p: sha256(p) for p in self.root.rglob('*') if p.is_file() and 'quadros' not in p.parts
                and 'consultas_sqlite' not in p.parts and not p.name.endswith('.lock')}

    def criar(self, **fields):
        return tabelas.salvar(self.root, self.corpo(**fields))

    def corrigir(self, record, correcoes, conta=None, **fields):
        return tabelas.corrigir(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'],
                                                     correcoes=correcoes, **fields), conta)

    @staticmethod
    def celula(record, linha, coluna):
        return next(r for r in record['estado']['linhas'] if r['id'] == linha)['celulas'][coluna]

    # Células, fontes e estados
    def test_colunas_tipadas_e_celula_sem_fonte_fica_pendente(self):
        before = self.arquivos()
        record = self.criar()
        self.assertTrue(record['id'].startswith('Q'))
        first, second, third = record['estado']['linhas']
        self.assertEqual([r['id'] for r in record['estado']['linhas']], ['L0001', 'L0002', 'L0003'])
        self.assertEqual({c['estado'] for c in first['celulas'].values()}, {'extraido'})
        self.assertEqual(second['celulas']['contrato'], {'valor': '=HYPERLINK("http://x")', 'fonte': None,
                                                          'estado': 'pendente'})  # valor sem fonte
        self.assertEqual(third['celulas']['contrato'], {'valor': None, 'fonte': 1, 'estado': 'pendente'})  # fonte sem valor
        self.assertEqual(second['celulas']['peso_t'], {'valor': None, 'fonte': None, 'estado': 'pendente'})  # omitida
        self.assertEqual(third['celulas']['valor']['valor'], '7.50')  # forma canônica, a escala é preservada
        self.assertEqual(third['celulas']['peso']['valor'], '0.00')  # sem zero negativo
        self.assertEqual(third['celulas']['assinatura']['valor'], '2021')  # data parcial
        view = tabelas.tabela(self.root, 'alpha', record['id'])
        self.assertEqual(view['celulas_por_estado'], {'extraido': 10, 'corrigido_manual': 0, 'pendente': 11})
        cell = view['linhas'][0]['celulas']['valor']
        self.assertEqual((cell['fonte_legivel'], cell['fonte_conferida']), ('D001 · linha 1', True))
        self.assertEqual(view['evidencias'][1]['evidencia']['trecho'], 'Outra versão declara valor 14.')
        self.assertIn('pendente', view['aviso'])
        self.assertEqual(self.arquivos(), before)  # originais, rodadas e caderno intactos

    def test_valores_e_definicoes_invalidos_sao_recusados(self):
        cases = [
            ({'linhas': [{'celulas': {'valor': {'valor': '1.234,56', 'fonte': 0}}}]}, 'Valor inválido em L0001/valor'),
            ({'linhas': [{'celulas': {'valor': {'valor': 12.5, 'fonte': 0}}}]}, 'Valor inválido'),
            ({'linhas': [{'celulas': {'valor': {'valor': '1e3', 'fonte': 0}}}]}, 'Valor inválido'),
            ({'linhas': [{'celulas': {'assinatura': {'valor': '2021-02-30', 'fonte': 0}}}]}, 'Valor inválido'),
            ({'linhas': [{'celulas': {'contrato': {'valor': '   ', 'fonte': 0}}}]}, 'Valor inválido'),
            ({'linhas': [{'celulas': {'valor': {'valor': '1', 'fonte': 0, 'estado': 'extraido'}}}]}, 'Célula inválida'),
            ({'linhas': [{'celulas': {'valor': {'valor': '1', 'fonte': 7}}}]}, 'Fonte da célula'),
            ({'linhas': [{'celulas': {'valor': {'valor': '1', 'fonte': True}}}]}, 'Fonte da célula'),
            ({'linhas': [{'celulas': {'inexistente': {'valor': '1'}}}]}, 'Linha inválida'),
            ({'linhas': [{'id': 'L0009', 'celulas': {}}]}, 'Linha inválida'),
            ({'colunas': [{'id': 'v', 'nome': 'V', 'tipo': 'monetario', 'moeda': 'R$'}]}, 'Coluna inválida'),
            ({'colunas': [{'id': 'v', 'nome': 'V', 'tipo': 'numero'}]}, 'Coluna inválida'),
            ({'colunas': [{'id': 'v', 'nome': 'V', 'tipo': 'texto', 'unidade': 'kg'}]}, 'Coluna inválida'),
            ({'colunas': [{'id': 'Valor', 'nome': 'V', 'tipo': 'texto'}]}, 'Coluna inválida'),
            ({'colunas': [{'id': 'v', 'nome': 'V', 'tipo': 'texto'}] * 2}, 'Coluna inválida'),
            ({'colunas': []}, 'Coluna inválida'),
            ({'linhas': [{'celulas': {}}] * (tabelas.MAXIMO_LINHAS + 1)}, 'Tabela grande demais'),
            ({'calculos': [{'id': 'd', 'operacao': 'diferenca', 'coluna': 'valor'}]}, 'Cálculo inválido'),
            ({'calculos': [{'id': 'm', 'operacao': 'soma', 'coluna': 'valor', 'casas_decimais': 2}]}, 'Cálculo inválido'),
            ({'calculos': [{'id': 'x', 'operacao': 'potencia', 'coluna': 'valor'}]}, 'Cálculo inválido'),
            ({'calculos': [{'id': 's', 'operacao': 'soma', 'coluna': 'contrato'}]}, 'Cálculo recusado'),
        ]
        for fields, message in cases:
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, message):
                self.criar(**fields)
        # A fonte de uma célula é evidência de suporte: contexto ou contradição não sustentam o valor.
        with self.assertRaisesRegex(ValueError, 'evidência de suporte'):
            self.criar(evidencias=[self.link(self.ia(), 'contradicao'), self.link(self.humana())])
        # Texto livre não é evidência, e evidência de outra apuração é recusada pelo contrato do Core.
        with self.assertRaisesRegex(ValueError, 'Referência'):
            self.criar(evidencias=[{'referencia': {'tipo': 'livre', 'trecho': 'sem fonte'}, 'papel': 'suporte',
                                    'justificativa': 'x'}])
        self.env.caso('beta', indice=False)
        with self.assertRaisesRegex(ValueError, 'outra apuração'):
            tabelas.salvar(self.root, self.corpo(caso='beta'))
        self.assertEqual(tabelas.listar(self.root, 'alpha'), [])

    # Correção manual e histórico
    def test_correcao_preserva_o_historico_com_autor_da_conta_data_e_justificativa(self):
        record = self.criar()
        conta = {'id': 'conta-7', 'nome': 'Editora C'}
        with self.assertRaisesRegex(ValueError, r'informe a justificativa \(L0001/valor\)'):
            self.corrigir(record, [{'linha': 'L0001', 'coluna': 'valor', 'valor': '12.50'}], conta)
        body = self.base(id=record['id'], anterior_sha256=record['sha256'], observacao='Conferência no original.',
                         correcoes=[{'linha': 'L0001', 'coluna': 'valor', 'valor': '12.50',
                                     'justificativa': 'O original traz 12,50; a extração perdeu os centavos.'}])
        second = tabelas.corrigir(self.root, body, conta)
        self.assertEqual(tabelas.corrigir(self.root, body, conta)['sha256'], second['sha256'])  # idempotente
        with self.assertRaisesRegex(ValueError, 'tentativa'):
            tabelas.corrigir(self.root, {**body, 'correcoes': [{**body['correcoes'][0], 'valor': '13'}]}, conta)
        event = second['historico'][-1]
        self.assertEqual((event['sequencia'], event['autor'], event['origem_autoria'], event['conta_id']),
                         (2, 'Editora C', caderno.AUTORIA_CONTA, 'conta-7'))
        self.assertTrue(event['em_utc'])
        self.assertEqual(event['estado']['correcoes'], [
            {'linha': 'L0001', 'coluna': 'valor', 'tipo': 'correcao', 'valor_anterior': '12', 'fonte_anterior': 0,
             'valor': '12.50', 'fonte': 0, 'justificativa': 'O original traz 12,50; a extração perdeu os centavos.'}])
        self.assertEqual(self.celula(second, 'L0001', 'valor'), {'valor': '12.50', 'fonte': 0, 'estado': 'corrigido_manual'})
        # O valor anterior continua no primeiro evento, que não é reescrito.
        self.assertEqual(second['historico'][0]['estado']['linhas'][0]['celulas']['valor']['valor'], '12')
        folder = self.root / f"casos/alpha/quadros/tabelas/{record['id']}"
        self.assertEqual(len(list(folder.glob('*.json'))), 2)
        with self.assertRaisesRegex(ValueError, 'O registro mudou'):
            self.corrigir(record, [{'linha': 'L0002', 'coluna': 'contrato', 'fonte': 0}])
        # Preencher a fonte que faltava não é correção; tirar a fonte de um valor é, e deixa a célula pendente.
        third = self.corrigir(second, [{'linha': 'L0002', 'coluna': 'contrato', 'fonte': 0},
                                       {'linha': 'L0003', 'coluna': 'peso', 'fonte': None,
                                        'justificativa': 'A passagem não trata de peso.'}])
        self.assertEqual([(c['tipo'], c['justificativa']) for c in third['estado']['correcoes']],
                         [('preenchimento', ''), ('correcao', 'A passagem não trata de peso.')])
        self.assertEqual(self.celula(third, 'L0002', 'contrato')['estado'], 'extraido')
        self.assertEqual(self.celula(third, 'L0003', 'peso'), {'valor': '0.00', 'fonte': None, 'estado': 'pendente'})
        self.assertEqual(third['historico'][-1]['origem_autoria'], caderno.AUTORIA_DECLARADA)
        versions = tabelas.historico_celula(self.root, 'alpha', record['id'], 'L0001', 'valor')['versoes']
        self.assertEqual([(v['sequencia'], v['valor'], v['estado']) for v in versions],
                         [(1, '12', 'extraido'), (2, '12.50', 'corrigido_manual')])
        self.assertEqual((versions[1]['autor'], versions[1]['correcao']['valor_anterior']), ('Editora C', '12'))
        self.assertEqual(versions[1]['fonte']['localizador'], 'D001 · linha 1')
        last = tabelas.tabela(self.root, 'alpha', record['id'])['linhas'][0]['celulas']['valor']['ultima_correcao']
        self.assertEqual((last['sequencia'], last['autor'], last['valor_anterior']), (2, 'Editora C', '12'))
        # Depois de uma correção, devolver a fonte é preenchimento, mas a célula não volta a parecer extraída.
        fourth = self.corrigir(third, [{'linha': 'L0003', 'coluna': 'peso', 'fonte': 0}])
        self.assertEqual(fourth['estado']['correcoes'][0]['tipo'], 'preenchimento')
        self.assertEqual(self.celula(fourth, 'L0003', 'peso'), {'valor': '0.00', 'fonte': 0, 'estado': 'corrigido_manual'})
        self.assertEqual(tabelas.tabela(self.root, 'alpha', record['id'])['linhas'][2]['celulas']['peso']['estado'],
                         'corrigido_manual')

    def test_celula_registrada_so_muda_por_correcao_e_linhas_so_sao_acrescentadas(self):
        record = self.criar()
        saved = record['estado']['linhas']
        changed = json.loads(json.dumps(saved)); changed[0]['celulas']['valor']['valor'] = '99'
        update = lambda current, **fields: tabelas.salvar(  # noqa: E731
            self.root, self.base(id=current['id'], anterior_sha256=current['sha256'], **fields), 'atualizar')
        with self.assertRaisesRegex(ValueError, r'Célula já registrada \(L0001/valor\)'):
            update(record, linhas=changed)
        with self.assertRaisesRegex(ValueError, 'Linha inválida'):
            update(record, linhas=saved[:2])
        with self.assertRaisesRegex(ValueError, 'Correção inválida'):
            update(record, correcoes=[{'linha': 'L0001', 'coluna': 'valor', 'valor': '1', 'justificativa': 'x'}])
        with self.assertRaisesRegex(ValueError, 'Correção inválida'):
            self.corrigir(record, [{'linha': 'L0001', 'coluna': 'valor', 'valor': '1', 'justificativa': 'x'}],
                          titulo='Outro título')
        with self.assertRaisesRegex(ValueError, 'já tem este valor'):
            self.corrigir(record, [{'linha': 'L0001', 'coluna': 'valor', 'valor': '12', 'justificativa': 'x'}])
        with self.assertRaisesRegex(ValueError, 'Célula inexistente'):
            self.corrigir(record, [{'linha': 'L0009', 'coluna': 'valor', 'valor': '1', 'justificativa': 'x'}])
        # Linha nova vai ao fim, com o id seguinte; coluna nova chega vazia (pendente) nas linhas registradas.
        columns = record['estado']['colunas'] + [{'id': 'orgao', 'nome': 'Órgão', 'tipo': 'texto'}]
        grown = update(record, colunas=columns, linhas=saved + [{'celulas': {'valor': {'valor': '1.00', 'fonte': 0}}}])
        self.assertEqual([r['id'] for r in grown['estado']['linhas']], ['L0001', 'L0002', 'L0003', 'L0004'])
        self.assertEqual(self.celula(grown, 'L0001', 'orgao'), {'valor': None, 'fonte': None, 'estado': 'pendente'})
        self.assertEqual(self.celula(grown, 'L0004', 'valor')['estado'], 'extraido')
        renamed = [{**c, 'nome': 'Valor contratado'} if c['id'] == 'valor' else c for c in grown['estado']['colunas']]
        renamed = update(grown, colunas=renamed)
        self.assertEqual(renamed['estado']['colunas'][2]['nome'], 'Valor contratado')
        retyped = [{**c, 'moeda': 'USD'} if c['id'] == 'valor' else c for c in renamed['estado']['colunas']]
        with self.assertRaisesRegex(ValueError, 'As colunas já registradas'):
            update(renamed, colunas=retyped)
        # A fonte segue a identidade da evidência quando a lista é reordenada; a que ainda é fonte não sai.
        links = renamed['estado']['evidencias']
        reordered = update(renamed, evidencias=[links[1], links[0]])
        self.assertEqual(self.celula(reordered, 'L0001', 'valor')['fonte'], 1)
        self.assertEqual(self.celula(reordered, 'L0002', 'valor')['fonte'], 0)
        self.assertEqual(reordered['estado']['evidencias'][1]['referencia']['evidencia_id'], 'E001')
        with self.assertRaisesRegex(ValueError, 'Evidência ainda é fonte de célula'):
            update(reordered, evidencias=[reordered['estado']['evidencias'][0]])
        retired = update(reordered, retirado=True, motivo_retirada='Tabela refeita em outro registro.')
        self.assertEqual(tabelas.quadro(self.root, 'alpha')['tabelas'], [])
        self.assertEqual(tabelas.quadro(self.root, 'alpha', incluir_retirados=True)['tabelas'][0]['id'], retired['id'])

    def test_historico_adulterado_e_recusado(self):
        record = self.criar()
        second = self.corrigir(record, [{'linha': 'L0001', 'coluna': 'valor', 'valor': '12.50', 'justificativa': 'x'}])
        path = sorted((self.root / f"casos/alpha/quadros/tabelas/{record['id']}").glob('*.json'))[-1]
        data = json.loads(path.read_text(encoding='utf-8'))
        data['estado']['correcoes'][0]['valor_anterior'] = None  # apagaria o valor anterior da correção
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'divergente'):
            tabelas.detalhe(self.root, 'alpha', second['id'])
        self.assertTrue(tabelas.quadro(self.root, 'alpha')['divergentes'])

    # Cálculos
    def calculos(self):
        columns = [{'id': 'valor', 'nome': 'Valor', 'tipo': 'monetario', 'moeda': 'BRL'},
                   {'id': 'percentual', 'nome': 'Percentual', 'tipo': 'numero', 'unidade': '%'},
                   {'id': 'nome', 'nome': 'Nome', 'tipo': 'texto'}]
        rows = [{'celulas': {'valor': {'valor': '0.10', 'fonte': 0}, 'percentual': {'valor': '12.5', 'fonte': 0},
                             'nome': {'valor': 'A', 'fonte': 0}}},
                {'celulas': {'valor': {'valor': '0.20', 'fonte': 0}, 'percentual': {'valor': '10', 'fonte': 0},
                             'nome': {'valor': 'B', 'fonte': 0}}},
                {'celulas': {'valor': {'valor': '100.00', 'fonte': 1}}}]
        calcs = [{'id': 'total', 'nome': 'Total contratado', 'operacao': 'soma', 'coluna': 'valor'},
                 {'id': 'media', 'operacao': 'media', 'coluna': 'valor'},
                 {'id': 'media_duas', 'operacao': 'media', 'coluna': 'valor', 'linhas': ['L0001', 'L0002']},
                 {'id': 'dif', 'operacao': 'diferenca', 'celulas': [{'linha': 'L0003', 'coluna': 'valor'},
                                                                    {'linha': 'L0001', 'coluna': 'valor'}]},
                 {'id': 'pp', 'operacao': 'diferenca', 'celulas': [{'linha': 'L0001', 'coluna': 'percentual'},
                                                                   {'linha': 'L0002', 'coluna': 'percentual'}]},
                 {'id': 'nomes', 'operacao': 'contagem', 'coluna': 'nome'}]
        return self.criar(colunas=columns, linhas=rows, calculos=calcs)

    def test_soma_de_moedas_ou_unidades_diferentes_e_recusada(self):
        record = self.criar()
        pair = lambda a, b: [{'linha': 'L0001', 'coluna': a}, {'linha': 'L0001', 'coluna': b}]  # noqa: E731
        refused = {('valor', 'valor_usd'): 'moeda BRL; moeda USD', ('peso', 'peso_t'): 'unidade kg; unidade t',
                   ('valor', 'valor_mil'): 'moeda BRL; moeda BRL \\(mil\\)', ('valor', 'peso'): 'moeda BRL; unidade kg'}
        for (a, b), label in refused.items():
            for operation in ('soma', 'diferenca', 'media'):
                with self.subTest(a=a, b=b, operation=operation):
                    with self.assertRaisesRegex(ValueError, 'Cálculo recusado: unidades ou moedas diferentes \\(' + label):
                        tabelas.calcular_tabela(self.root, 'alpha', record['id'],
                                                {'operacao': operation, 'celulas': pair(a, b)})
        # Declarar o cálculo misturando moedas também é recusado, antes de gravar.
        with self.assertRaisesRegex(ValueError, 'unidades ou moedas diferentes'):
            tabelas.salvar(self.root, self.base(id=record['id'], anterior_sha256=record['sha256'], calculos=[
                {'id': 'mistura', 'operacao': 'soma', 'celulas': pair('valor', 'valor_usd')}]), 'atualizar')
        with self.assertRaisesRegex(ValueError, 'não numérica: Contrato'):
            tabelas.calcular_tabela(self.root, 'alpha', record['id'], {'operacao': 'media', 'coluna': 'contrato'})
        with self.assertRaisesRegex(ValueError, r'célula sem valor \(L0002/valor_usd'):
            tabelas.calcular_tabela(self.root, 'alpha', record['id'], {'operacao': 'soma', 'coluna': 'valor_usd'})
        # A contagem não soma grandezas: conta as células com valor de qualquer coluna.
        count = tabelas.calcular_tabela(self.root, 'alpha', record['id'], {'operacao': 'contagem', 'celulas': pair('valor', 'valor_usd')})
        self.assertEqual(count['resultado'], '2')
        self.assertEqual(len(tabelas.detalhe(self.root, 'alpha', record['id'])['historico']), 1)

    def test_calculo_repetido_da_o_mesmo_resultado_e_lista_as_celulas(self):
        record = self.calculos()
        first = tabelas.calcular_tabela(self.root, 'alpha', record['id'], 'total')
        self.assertEqual(tabelas.calcular_tabela(self.root, 'alpha', record['id'], 'total'), first)
        state = tabelas.detalhe(self.root, 'alpha', record['id'])['estado']
        self.assertEqual(tabelas.calcular(state, state['calculos'][0]), tabelas.calcular(state, state['calculos'][0]))
        self.assertEqual((first['resultado'], first['exato'], first['expressao']), ('100.30', True, '0.10 + 0.20 + 100.00'))
        self.assertEqual(first['grandeza'], {'tipo': 'monetario', 'moeda': 'BRL', 'unidade': None})
        self.assertEqual([(c['linha'], c['coluna'], c['valor'], c['fonte_legivel']) for c in first['celulas']],
                         [('L0001', 'valor', '0.10', 'D001 · linha 1'), ('L0002', 'valor', '0.20', 'D001 · linha 1'),
                          ('L0003', 'valor', '100.00', 'D001 · Linha 2')])
        # Repetir a conta à mão com as células listadas dá o mesmo resultado (0,1 + 0,2 é exatamente 0,3).
        self.assertEqual(sum(Decimal(c['valor']) for c in first['celulas']), Decimal(first['resultado']))
        self.assertEqual((first['tabela']['sequencia'], first['tabela']['sha256'], first['estado']),
                         (1, record['sha256'], 'com_fonte'))
        self.assertEqual((first['fontes_sustentadas'], first['fontes_nao_sustentadas']), (True, []))
        view = {c['id']: c for c in tabelas.tabela(self.root, 'alpha', record['id'])['calculos']}
        mean = view['media']
        self.assertEqual((mean['resultado'], mean['exato'], mean['soma'], mean['divisor']), ('33.433333', False, '100.30', 3))
        self.assertEqual(mean['arredondamento']['regra'], 'meio_para_cima')
        self.assertEqual((Decimal(mean['soma']) / 3).quantize(Decimal('0.000001'), ROUND_HALF_UP), Decimal(mean['resultado']))
        self.assertEqual((view['media_duas']['resultado'], view['media_duas']['exato']), ('0.15', True))
        self.assertEqual((view['dif']['resultado'], view['dif']['expressao']), ('99.90', '100.00 - 0.10'))
        self.assertEqual((view['pp']['resultado'], view['pp']['grandeza']['unidade']), ('2.5', 'pontos percentuais'))
        self.assertEqual((view['nomes']['resultado'], view['nomes']['celulas_sem_valor'], view['nomes']['estado']),
                         ('2', ['L0003/nome'], 'pendente'))
        self.assertFalse(view['nomes']['fontes_sustentadas'])
        # Depois de uma correção, a versão anterior continua calculável e dá o resultado de antes.
        second = self.corrigir(record, [{'linha': 'L0001', 'coluna': 'valor', 'valor': '0.15',
                                         'justificativa': 'Centavos conferidos no original.'}])
        again = tabelas.calcular_tabela(self.root, 'alpha', record['id'], 'total', 1)
        self.assertEqual({k: v for k, v in again.items() if k != 'tabela'}, {k: v for k, v in first.items() if k != 'tabela'})
        self.assertEqual(again['tabela']['sha256'], tabelas.detalhe(self.root, 'alpha', record['id'])['historico'][1]['anterior_sha256'])
        current = tabelas.calcular_tabela(self.root, 'alpha', record['id'], 'total')
        self.assertEqual((current['resultado'], current['tabela']['sequencia'], current['tabela']['sha256']),
                         ('100.35', 2, second['sha256']))
        self.assertNotEqual(current['entrada_sha256'], first['entrada_sha256'])
        with self.assertRaisesRegex(ValueError, 'Versão da tabela inexistente'):
            tabelas.calcular_tabela(self.root, 'alpha', record['id'], 'total', 3)
        with self.assertRaisesRegex(ValueError, 'Cálculo não encontrado'):
            tabelas.calcular_tabela(self.root, 'alpha', record['id'], 'inexistente')
        # Uma célula esvaziada deixa o cálculo registrado recusado na visão, sem derrubar a tabela.
        self.corrigir(second, [{'linha': 'L0002', 'coluna': 'valor', 'valor': None, 'justificativa': 'Valor ilegível.'}])
        view = {c['id']: c for c in tabelas.tabela(self.root, 'alpha', record['id'])['calculos']}
        self.assertEqual(view['total']['estado'], 'recusado')
        self.assertIn('célula sem valor', view['total']['erro'])

    def test_calculo_aponta_fonte_ainda_nao_sustentada(self):
        weak = {**self.link(self.humana()), 'suporte': 'nao_revisado', 'natureza': 'pendencia'}
        record = self.criar(evidencias=[self.link(self.ia()), weak])
        cells = [{'linha': 'L0001', 'coluna': 'valor'}, {'linha': 'L0002', 'coluna': 'valor'}]
        result = tabelas.calcular_tabela(self.root, 'alpha', record['id'], {'operacao': 'soma', 'celulas': cells})
        self.assertEqual((result['resultado'], result['estado']), ('26.25', 'com_fonte'))
        self.assertEqual((result['fontes_sustentadas'], result['fontes_nao_sustentadas']), (False, ['L0002/valor']))
        self.assertEqual([(c['fonte_suporte'], c['fonte_natureza']) for c in result['celulas']],
                         [('sustentado', 'declaracao_documental'), ('nao_revisado', 'pendencia')])
        alone = tabelas.calcular_tabela(self.root, 'alpha', record['id'], {'operacao': 'soma', 'celulas': cells[:1]})
        self.assertEqual((alone['resultado'], alone['fontes_sustentadas']), ('12', True))

    def test_media_com_casas_declaradas_arredonda_meio_para_cima(self):
        columns = [{'id': 'valor', 'nome': 'Valor', 'tipo': 'monetario', 'moeda': 'BRL'}]
        values = ['1234.56', '1234.57', '-1234.56', '-1234.57']
        record = self.criar(colunas=columns, linhas=[{'celulas': {'valor': {'valor': v, 'fonte': 0}}} for v in values])
        mean = lambda rows, **extra: tabelas.calcular_tabela(  # noqa: E731
            self.root, 'alpha', record['id'], {'operacao': 'media', 'coluna': 'valor', 'linhas': rows, **extra})
        exact = mean(['L0001', 'L0002'])
        self.assertEqual((exact['resultado'], exact['exato'], exact['arredondamento']), ('1234.565', True, None))
        rounded = mean(['L0001', 'L0002'], casas_decimais=2)
        self.assertEqual((rounded['resultado'], rounded['exato'], rounded['arredondamento']['casas_decimais']),
                         ('1234.57', False, 2))
        self.assertEqual(mean(['L0003', 'L0004'], casas_decimais=2)['resultado'], '-1234.57')
        self.assertEqual(mean(['L0001', 'L0003'], casas_decimais=2)['resultado'], '0.00')
        self.assertEqual(mean(['L0001', 'L0002', 'L0003'])['resultado'], '411.523333')

    # Exportação
    def test_exportacao_csv_traz_a_fonte_de_cada_celula(self):
        record = self.criar(calculos=[{'id': 'total', 'operacao': 'soma', 'celulas': [
            {'linha': 'L0001', 'coluna': 'valor'}, {'linha': 'L0002', 'coluna': 'valor'}]}])
        name, content = tabelas.exportar_csv(self.root, 'alpha', record['id'])
        self.assertEqual(name, f"tabela_{record['id']}.csv")
        self.assertTrue(content.startswith(b'\xef\xbb\xbf'))
        rows = list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
        header = rows[0]
        self.assertEqual(len(header), 1 + 3 * len(COLUNAS))
        self.assertEqual(header[:4], ['linha', 'Contrato', 'Contrato - fonte', 'Contrato - estado'])
        self.assertIn('Valor (BRL) - fonte', header)
        self.assertIn('Peso (kg)', header)
        table = {r[0]: dict(zip(header, r)) for r in rows[1:]}
        self.assertEqual(list(table), ['L0001', 'L0002', 'L0003'])
        first = table['L0001']
        self.assertEqual((first['Valor (BRL)'], first['Valor (BRL) - estado']), ('12', 'extraido'))
        self.assertIn('D001 · linha 1 | achados alpha/R001/r2/E001', first['Valor (BRL) - fonte'])
        self.assertIn('original sha256 ' + record['estado']['evidencias'][0]['original_sha256'], first['Valor (BRL) - fonte'])
        self.assertIn('caderno alpha/' + self.nota['registro']['id'] + '/fonte 0', table['L0002']['Valor (BRL) - fonte'])
        # Cada célula tem a sua fonte: a pendente diz que não tem, e o texto com fórmula é neutralizado.
        self.assertEqual((table['L0002']['Contrato - fonte'], table['L0002']['Contrato - estado']),
                         ('PENDENTE: sem fonte', 'pendente'))
        self.assertEqual(table['L0002']['Contrato'], '\'=HYPERLINK("http://x")')
        self.assertEqual(table['L0003']['Contrato'], '')
        self.assertEqual(table['L0003']['Peso (kg)'], '0.00')
        # Para o Excel em português: ponto e vírgula e vírgula decimal.
        _, br = tabelas.exportar_csv(self.root, 'alpha', record['id'], 'excel_br')
        rows_br = list(csv.reader(io.StringIO(br.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(dict(zip(rows_br[0], rows_br[2]))['Valor (BRL)'], '14,25')
        with self.assertRaisesRegex(ValueError, 'Formato de exportação'):
            tabelas.exportar_csv(self.root, 'alpha', record['id'], 'xlsx')
        # Fonte que deixou de conferir (original do caderno alterado) aparece como indisponível, sem sumir.
        manifest = json.loads((self.root / 'casos/alpha/manifesto.json').read_text(encoding='utf-8'))
        (self.root / manifest['documentos'][0]['arquivo']).write_text('alterado', encoding='utf-8')
        _, changed = tabelas.exportar_csv(self.root, 'alpha', record['id'])
        changed = {r[0]: r for r in csv.reader(io.StringIO(changed.decode('utf-8-sig')))}
        self.assertIn('FONTE INDISPONÍVEL', changed['L0002'][header.index('Valor (BRL) - fonte')])
        self.assertNotIn('FONTE INDISPONÍVEL', changed['L0001'][header.index('Valor (BRL) - fonte')])
        total = tabelas.tabela(self.root, 'alpha', record['id'])['calculos'][0]
        self.assertEqual((total['resultado'], total['estado'], total['fontes_indisponiveis']), ('26.25', 'pendente', ['L0002/valor']))


class RotasTabelasTest(Fontes, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ambiente, (_, _, _, second) = Ambiente.copia_completa()
        cls.ambiente.caso('beta', indice=False)
        cls.registros_classe = second

    @classmethod
    def tearDownClass(cls):
        cls.ambiente.cleanup()

    def setUp(self):
        self.preparar(self.ambiente, self.registros_classe)
        self.server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def bruto(self, op, data, token=None, origin=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        headers = {'Content-Type': 'application/json', 'Origin': origin or self.server.origin}
        if token is not False:
            headers['X-Session-Token'] = token or self.server.token
        con.request('POST', '/api/' + op, body=json.dumps(data), headers=headers)
        response = con.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        con.close()
        return result

    def post(self, op, data, **kwargs):
        status, _, body = self.bruto(op, data, **kwargs)
        return status, json.loads(body or b'{}')

    def ok(self, op, data):
        status, body = self.post(op, data)
        self.assertEqual(status, 200, (op, body))
        return body

    def erro(self, op, data, codigo):
        status, body = self.post(op, data)
        self.assertEqual(status, 400, (op, body))
        self.assertEqual(body.get('codigo'), codigo, body)
        self.assertTrue(isinstance(body.get('erro'), str) and body['erro'].strip(), body)
        self.assertNotIn('Traceback', body['erro'])
        self.assertNotIn(str(self.root), body['erro'])
        return body

    def test_rotas_criar_detalhar_corrigir_calcular_historico_e_exportar(self):
        status, _, body = self.bruto('tabelas-listar', {'caso': 'alpha'})
        self.assertEqual(status, 200, body)
        created = self.ok('tabelas-criar', self.corpo(calculos=[{'id': 'total', 'operacao': 'soma', 'coluna': 'valor'}]))
        self.assertTrue(all('estado' not in e for e in created['historico']))  # resposta sem o estado de cada evento
        listed = self.ok('tabelas-listar', {'caso': 'alpha'})
        self.assertIn(created['id'], [t['id'] for t in listed['tabelas']])
        detail = self.ok('tabelas-detalhe', {'caso': 'alpha', 'id': created['id']})
        self.assertEqual(detail['calculos'][0]['resultado'], '33.75')
        corrected = self.ok('tabelas-corrigir', self.base(id=created['id'], anterior_sha256=created['sha256'], correcoes=[
            {'linha': 'L0001', 'coluna': 'valor', 'valor': '12.50', 'justificativa': 'Centavos conferidos no original.'}]))
        self.assertEqual(corrected['historico'][-1]['correcoes'][0]['valor_anterior'], '12')
        updated = self.ok('tabelas-atualizar', self.base(id=created['id'], anterior_sha256=corrected['sha256'],
                                                         titulo='Contratos sintéticos revisados'))
        self.assertEqual(updated['estado']['titulo'], 'Contratos sintéticos revisados')
        calc = self.ok('tabelas-calcular', {'caso': 'alpha', 'id': created['id'], 'calculo': 'total'})
        self.assertEqual((calc['resultado'], calc['tabela']['sequencia']), ('34.25', 3))
        old = self.ok('tabelas-calcular', {'caso': 'alpha', 'id': created['id'], 'calculo': 'total', 'sequencia': 1})
        self.assertEqual(old['resultado'], '33.75')
        history = self.ok('tabelas-historico-celula', {'caso': 'alpha', 'id': created['id'], 'linha': 'L0001',
                                                       'coluna': 'valor'})
        self.assertEqual([v['valor'] for v in history['versoes']], ['12', '12.50'])
        status, headers, content = self.bruto('tabelas-exportar', {'caso': 'alpha', 'id': created['id']})
        self.assertEqual(status, 200, content[:200])
        self.assertTrue(headers['Content-Type'].startswith('text/csv'))
        self.assertEqual(headers['Content-Disposition'], f'attachment; filename="tabela_{created["id"]}.csv"')
        exported = list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
        self.assertIn('Valor (BRL) - fonte', exported[0])
        self.assertIn('corrigido_manual', exported[1])
        integracao = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        integracao.request('GET', '/api/integracao', headers={'Cookie': f'apuracao_session={self.server.token}'})
        self.assertTrue(json.loads(integracao.getresponse().read())['tabelas_apuracao'])
        integracao.close()

    def test_rota_recusa_outro_caso(self):
        created = self.ok('tabelas-criar', self.corpo())
        for op, extra in (('tabelas-detalhe', {}), ('tabelas-calcular', {'calculo': {'operacao': 'contagem', 'coluna': 'valor'}}),
                          ('tabelas-historico-celula', {'linha': 'L0001', 'coluna': 'valor'}), ('tabelas-exportar', {})):
            with self.subTest(op=op):
                self.erro(op, {'caso': 'beta', 'id': created['id'], **extra}, 'registro_inexistente')
        self.erro('tabelas-corrigir', self.base(caso='beta', id=created['id'], anterior_sha256=created['sha256'], correcoes=[
            {'linha': 'L0001', 'coluna': 'valor', 'valor': '1', 'justificativa': 'x'}]), 'registro_inexistente')
        self.erro('tabelas-criar', self.corpo(caso='beta'), 'evidencia_outro_caso')
        self.assertNotIn(created['id'], json.dumps(self.ok('tabelas-listar', {'caso': 'beta'})))

    def test_validacao_legivel_de_caso_campos_e_calculo(self):
        created = self.ok('tabelas-criar', self.corpo())
        self.erro('tabelas-listar', {}, 'quadro_sem_caso')
        self.erro('tabelas-listar', {'caso': '../alpha'}, 'quadro_sem_caso')
        self.erro('tabelas-detalhe', {'caso': 'alpha', 'id': created['id'], 'caminho': '../x'}, 'quadro_campos_invalidos')
        self.erro('tabelas-listar', {'caso': 'alpha', 'incluir_retirados': 'sim'}, 'filtro_retirados_invalido')
        self.erro('tabelas-calcular', {'caso': 'alpha', 'id': created['id'], 'calculo': {'operacao': 'soma', 'celulas': [
            {'linha': 'L0001', 'coluna': 'valor'}, {'linha': 'L0001', 'coluna': 'valor_usd'}]}}, 'calculo_unidades_incompativeis')
        self.erro('tabelas-calcular', {'caso': 'alpha', 'id': created['id'], 'calculo': {'operacao': 'soma', 'coluna': 'valor_usd'}},
                  'calculo_celula_sem_valor')
        self.erro('tabelas-corrigir', self.base(id=created['id'], anterior_sha256=created['sha256'], correcoes=[
            {'linha': 'L0001', 'coluna': 'valor', 'valor': '1'}]), 'correcao_sem_justificativa')
        self.erro('tabelas-criar', self.corpo(linhas=[{'celulas': {'valor': {'valor': '1.234,56', 'fonte': 0}}}]),
                  'tabela_valor_invalido')
        self.erro('tabelas-exportar', {'caso': 'alpha', 'id': created['id'], 'formato': 'xlsx'}, 'exportacao_formato_invalido')
        self.erro('tabelas-detalhe', {'caso': 'alpha', 'id': 'Q' + '0' * 32}, 'registro_inexistente')

    def test_recusa_sem_sessao_ou_com_token_errado(self):
        for token in (False, 'token-errado'):
            for op in rotas_tabelas.OPERACOES:
                status, _, body = self.bruto(op, {'caso': 'alpha'}, token=token)
                self.assertIn(status, (401, 403), (op, token, body))
                self.assertNotIn(b'tabelas', body)
        status, _ = self.post('tabelas-listar', {'caso': 'alpha'}, origin='https://outro.example')
        self.assertEqual(status, 403)


class RotasTabelasContasTest(autorizacao.Http):
    """Hosted mode: no session → 401 before the case is read; guests never reach the tables."""

    def test_sem_sessao_401_e_convidado_403(self):
        for op in rotas_tabelas.OPERACOES:
            status, headers, body = self.request('POST', '/api/' + op, json.dumps({'caso': 'alpha'}),
                                                 {'Content-Type': 'application/json', 'Origin': autorizacao.ORIGEM})
            self.assertEqual(status, 401, (op, body))
            status, body = self.post(self.ana, op, {'caso': 'alpha'})
            self.assertEqual((status, body.get('codigo')), (403, 'operacao_proibida'), op)

    def test_admin_alcanca_as_tabelas(self):
        status, body = self.post(self.admin, 'tabelas-listar', {'caso': 'alpha'})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['tabelas'], [])


if __name__ == '__main__':
    unittest.main()
