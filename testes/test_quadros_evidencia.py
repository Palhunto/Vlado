"""Contrato de evidência e quadros (hipóteses, linha do tempo, comparador, mapa), com fontes sintéticas."""
import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fixture_achados import Ambiente
from comum import sha256
from criar_caso import criar_caso
from nova_rodada import criar_rodada
from selecionar_caso import selecionar
import caderno
import comparador
import evidencias as ev
import hipoteses
import lixeira
import linha_tempo
import mapa_relacoes as mapa


class QuadrosEvidenciaTest(unittest.TestCase):
    def setUp(self):
        self.env = Ambiente(); self.addCleanup(self.env.cleanup)
        self.root = self.env.root
        _, revised, _, second = self.env.completo()
        self.registros = second['manifesto']['registros_sha256']
        docs = caderno.documentos(self.root, 'alpha'); doc = docs['documentos'][0]
        self.nota = caderno.salvar(self.root, {
            'caso': 'alpha', 'origem_id': docs['origem_id'], 'documento_id': doc['documento_id'],
            'documento_sha256': doc['sha256'], 'pagina_pdf': None, 'localizador': 'Linha 2',
            'trecho': 'Outra versão declara valor 14.', 'titulo': 'Trecho humano', 'anotacao': '',
            'autor': 'Repórter A', 'tipo': 'trecho', 'transcricao_manual': False, 'requisicao_id': uuid.uuid4().hex})

    def ia(self, eid='E001'):
        return {'tipo': 'ia', 'caso_id': 'alpha', 'rodada': 'R001', 'revisao': 'r2', 'registros_sha256': self.registros, 'evidencia_id': eid}

    def humana(self):
        return {'tipo': 'humana', 'caso_id': 'alpha', 'registro_id': self.nota['registro']['id'], 'sha256': self.nota['sha256'], 'fonte': 0}

    def link(self, ref, papel='suporte', suporte='nao_revisado', natureza=None):
        natureza = natureza or ('declaracao_documental' if suporte == 'sustentado' else 'pendencia')
        return {'referencia': ref, 'papel': papel, 'suporte': suporte, 'natureza': natureza,
                'justificativa': 'Vínculo sintético.'}

    def base(self, **fields):
        return {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Editora B', **fields}

    def arquivos(self):
        # Resolver evidência indexada acrescenta o log de consulta exigido pelo índice (somente acréscimo).
        return {p: sha256(p) for p in self.root.rglob('*') if p.is_file() and 'quadros' not in p.parts
                and 'consultas_sqlite' not in p.parts and not p.name.endswith('.lock')}

    # Contrato
    def test_contrato_resolve_documento_localizador_e_trecho_das_duas_origens(self):
        ia = ev.resolver(self.root, 'alpha', self.ia())
        self.assertEqual((ia['origem'], ia['documento']['documento_id'], ia['trecho']), ('ia', 'D001', 'A fonte declara valor 12.'))
        self.assertEqual(ia['localizador']['linha_inicio'], 1)
        self.assertIn('linha 1', ia['localizador']['legivel'])
        human = ev.resolver(self.root, 'alpha', self.humana())
        self.assertEqual((human['origem'], human['autor'], human['localizador']['descricao']), ('humana', 'Repórter A', 'Linha 2'))
        self.assertEqual(human['conferencia'], 'literal_localizado')
        for ref in (self.ia(), self.humana()):
            self.assertEqual(ev.original(self.root, 'alpha', ref).read_bytes(), self.env.text.read_bytes())
        visual = ev.resolver(self.root, 'alpha', self.ia('E003'))
        self.assertEqual(visual['conferencia'], 'leitura_visual')

    def test_contrato_recusa_texto_livre_outro_caso_e_identidade_divergente(self):
        bad = [{'tipo': 'livre', 'trecho': 'sem fonte'}, {**self.ia(), 'extra': 1}, {**self.ia(), 'evidencia_id': 'X1'},
               {**self.humana(), 'fonte': True}, {**self.humana(), 'fonte': 5}, {**self.ia(), 'evidencia_id': 'E999'},
               {**self.ia(), 'registros_sha256': '0' * 64}, {**self.humana(), 'sha256': '0' * 64}]
        for ref in bad:
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                ev.resolver(self.root, 'alpha', ref)
        self.env.caso('beta')
        with self.assertRaises(ValueError):
            ev.resolver(self.root, 'beta', self.humana())
        with self.assertRaises(ValueError):
            ev.vinculos(self.root, 'alpha', [self.link(self.ia()), self.link(self.ia())])
        with self.assertRaisesRegex(ValueError, 'Papel'):
            ev.vinculos(self.root, 'alpha', [self.link(self.ia(), papel='prova')])

    def test_vinculo_salvo_fica_indisponivel_se_original_mudar(self):
        item = hipoteses.salvar(self.root, self.base(enunciado='Hipótese H', evidencias=[self.link(self.humana())]))
        manifest = json.loads((self.root / 'casos/alpha/manifesto.json').read_text(encoding='utf-8'))
        (self.root / manifest['documentos'][0]['arquivo']).write_text('alterado', encoding='utf-8')
        row = hipoteses.quadro(self.root, 'alpha')['hipoteses'][0]
        self.assertEqual(row['id'], item['id'])
        self.assertEqual((row['sustentam'], row['indisponiveis'][0]['estado']), ([], 'indisponivel'))
        self.assertTrue(any('indisponível' in f['descricao'] for f in row['faltam']))

    # Item 3
    def test_hipoteses_separam_sustentam_contrariam_e_faltam_sem_julgamento(self):
        before = self.arquivos()
        body = self.base(enunciado='O valor declarado é 12.', evidencias=[
            self.link(self.ia()), self.link(self.humana(), 'contradicao', 'sustentado')],
            lacunas=[{'descricao': 'Ordem bancária do pagamento.'}])
        first = hipoteses.salvar(self.root, body)
        self.assertEqual(first['estado']['situacao'], 'em_aberto')
        self.assertEqual(hipoteses.salvar(self.root, body)['sha256'], first['sha256'])
        with self.assertRaisesRegex(ValueError, 'tentativa'):
            hipoteses.salvar(self.root, {**body, 'enunciado': 'Outro'})
        with self.assertRaisesRegex(ValueError, 'sustentada'):
            hipoteses.salvar(self.root, self.base(id=first['id'], anterior_sha256=first['sha256'], situacao='sustentada'), 'atualizar')
        board = hipoteses.quadro(self.root, 'alpha')['hipoteses'][0]
        self.assertEqual([x['evidencia']['trecho'] for x in board['sustentam']], ['A fonte declara valor 12.'])
        self.assertEqual([x['evidencia']['trecho'] for x in board['contrariam']], ['Outra versão declara valor 14.'])
        self.assertEqual(board['faltam'][0], {'origem': 'registrada', 'descricao': 'Ordem bancária do pagamento.',
                                              'diligencia_id': None, 'diligencia_estado': None})
        self.assertTrue(any('não revisado' in f['descricao'] for f in board['faltam']))
        links = [self.link(self.ia(), suporte='sustentado'), self.link(self.humana(), 'contradicao', 'sustentado')]
        second = hipoteses.salvar(self.root, self.base(id=first['id'], anterior_sha256=first['sha256'],
                                                       situacao='inconclusiva', evidencias=links), 'atualizar')
        self.assertEqual((second['estado']['situacao'], len(second['historico'])), ('inconclusiva', 2))
        self.assertEqual(second['historico'][0]['estado']['situacao'], 'em_aberto')
        self.assertEqual(second['estado']['lacunas'], first['estado']['lacunas'])
        with self.assertRaisesRegex(ValueError, 'mudou'):
            hipoteses.salvar(self.root, self.base(id=first['id'], anterior_sha256=first['sha256'], situacao='descartada'), 'atualizar')
        with self.assertRaises(ValueError):
            hipoteses.salvar(self.root, self.base(enunciado='X', lacunas=[{'descricao': 'Y', 'diligencia_id': 'G' + '0' * 32}]))
        self.assertEqual(self.arquivos(), before)

    def test_historico_adulterado_e_recusado(self):
        item = hipoteses.salvar(self.root, self.base(enunciado='Hipótese H'))
        path = next((self.root / f"casos/alpha/quadros/hipoteses/{item['id']}").glob('*.json'))
        data = json.loads(path.read_text(encoding='utf-8')); data['estado']['situacao'] = 'sustentada'
        path.write_text(json.dumps(data), encoding='utf-8')
        second = path.with_name('00000002_' + 'a' * 32 + '.json'); second.write_text(json.dumps({**data, 'sequencia': 2}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'divergente'):
            hipoteses.detalhe(self.root, 'alpha', item['id'])

    # Item 4
    def test_linha_do_tempo_ordena_datas_parciais_e_preserva_tipos(self):
        links = [self.link(self.ia()), self.link(self.humana(), 'contexto')]
        first = linha_tempo.salvar(self.root, self.base(descricao='Assinatura do contrato', evidencias=links, datas=[
            {'tipo': 'assinatura', 'valor': '2021-03-12', 'fonte': 0},
            {'tipo': 'publicacao', 'valor': '2021-04', 'fonte': 0, 'aproximada': True},
            {'tipo': 'declarada_por_fonte', 'valor': '2021', 'fonte': 1}]))
        linha_tempo.salvar(self.root, self.base(descricao='Pagamento', evidencias=links[:1], datas=[
            {'tipo': 'pagamento', 'valor': '2021-03-01', 'fonte': 0}, {'tipo': 'pagamento', 'valor': '2021-03-02', 'fonte': 0}]))
        result = linha_tempo.linha(self.root, 'alpha')
        self.assertEqual([e['data']['valor'] for e in result['entradas']], ['2021', '2021-03-01', '2021-03-02', '2021-03-12', '2021-04'])
        self.assertEqual(result['entradas'][0]['data']['precisao'], 'ano')
        self.assertEqual(result['entradas'][3]['fonte_da_data']['evidencia']['trecho'], 'A fonte declara valor 12.')
        self.assertEqual([d['tipo'] for d in result['divergencias']], ['pagamento'])
        self.assertTrue(result['entradas'][1]['divergente'])
        only = linha_tempo.linha(self.root, 'alpha', tipos=['assinatura'])
        self.assertEqual([e['evento_id'] for e in only['entradas']], [first['id']])
        invalid = [{'datas': [{'tipo': 'fato', 'valor': '2021-02-30', 'fonte': 0}]},
                   {'datas': [{'tipo': 'fato', 'valor': '12/03/2021', 'fonte': 0}]},
                   {'datas': [{'tipo': 'fato', 'valor': '2021', 'fonte': None}]},
                   {'datas': [{'tipo': 'fato', 'valor': '2021', 'fonte': 3}]},
                   {'datas': [{'tipo': 'hoje', 'valor': '2021', 'fonte': 0}]},
                   {'datas': [{'tipo': 'fato', 'valor': '2021', 'fonte': 1}]},
                   {'evidencias': [self.link(self.ia(), 'contexto')], 'datas': [{'tipo': 'declarada_por_fonte', 'valor': '2021', 'fonte': 0}]},
                   {'evidencias': []}]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                linha_tempo.salvar(self.root, self.base(**{'descricao': 'Evento', 'evidencias': links,
                                                           'datas': [{'tipo': 'fato', 'valor': '2021', 'fonte': 0}], **change}))

    # Item 5
    def test_comparador_de_evidencias_destaca_valor_com_contexto(self):
        result = comparador.comparar_evidencias(self.root, 'alpha', self.ia('E001'), self.humana())
        self.assertFalse(result['identicos'])
        self.assertEqual(result['a']['documento']['documento_id'], 'D001')
        changes = [c for c in result['alteracoes'] if c['classe'] == 'valor']
        self.assertEqual((changes[0]['a'], changes[0]['b']), ('12.', '14.'))
        self.assertEqual(result['marcas']['somente_a'][0]['normalizado'], '12')
        with self.assertRaisesRegex(ValueError, 'visual'):
            comparador.comparar_evidencias(self.root, 'alpha', self.ia('E003'), self.ia('E001'))

    def test_comparador_de_documentos_localiza_diferencas_de_valores_e_datas(self):
        a, b = self.root / 'contrato_v1.txt', self.root / 'contrato_v2.txt'
        common = ['Cláusula 1. Objeto: fornecimento de vacinas.', 'Cláusula 2. Prazo de 12 meses.']
        a.write_text('\n'.join([*common, 'Valor total: R$ 1.234,56.', 'Assinado em 12/03/2021.', 'Foro de Brasília.']), encoding='utf-8')
        b.write_text('\n'.join([*common, 'Valor total: R$ 1.500,00.', 'Assinado em 15 de março de 2021.', 'Foro de Brasília.',
                                'Cláusula adicional sintética.']), encoding='utf-8')
        criar_caso(self.root, 'gamma', 'Comparação sintética', [a, b], 'sinteticos')
        selecionar(self.root, 'gamma'); criar_rodada(self.root, 'R001', 'Teste técnico sintético.', indice=False)
        selecionar(self.root, None)
        result = comparador.comparar_documentos(self.root, 'gamma', 'R001', 'D001', 'D002', contexto=1)
        classes = [(c['operacao'], c['classe']) for c in result['alteracoes']]
        self.assertIn(('substituido', 'valor_e_data'), classes)
        self.assertIn(('inserido', 'conteudo'), classes)
        changed = result['alteracoes'][0]
        self.assertEqual((changed['localizador_a']['linha_inicio'], changed['localizador_b']['linha_inicio']), (3, 3))
        self.assertEqual(changed['contexto_a'][0]['texto'], common[1])
        self.assertIn({'tipo': 'valor_monetario', 'normalizado': 'R$ 1234.56', 'ocorrencias': 1}, result['marcas']['somente_a'])
        self.assertIn({'tipo': 'data', 'normalizado': '2021-03-15', 'ocorrencias': 1}, result['marcas']['somente_b'])
        self.assertIn({'tipo': 'numero', 'normalizado': '12', 'ocorrencias': 1}, result['marcas']['comuns'])
        for args in (('D001', 'D001'), ('D001', 'D999')):
            with self.subTest(args=args), self.assertRaises(ValueError):
                comparador.comparar_documentos(self.root, 'gamma', 'R001', *args)
        with self.assertRaisesRegex(ValueError, 'texto utilizável'):
            comparador.comparar_documentos(self.root, 'alpha', 'R001', 'D001', 'D002')

    def test_marcas_normalizam_formatos_brasileiros(self):
        found = comparador.marcas('Em 3 de março de 2022 pagou R$ 1.234,56 (12,5%) no contrato R001; 10 itens.')
        self.assertEqual([(m['tipo'], m['normalizado']) for m in found], [
            ('data', '2022-03-03'), ('valor_monetario', 'R$ 1234.56'), ('percentual', '12.5%'), ('numero', '10')])

    # Item 7
    def test_mapa_exige_evidencia_e_deixa_homonimos_para_conferencia_humana(self):
        joao = mapa.salvar_entidade(self.root, self.base(tipo='pessoa', nome='João da Silva', evidencias=[self.link(self.ia())],
            identificadores=[{'tipo': 'cpf', 'valor': '111.111.111-11', 'fonte': 0}]))
        outro = mapa.salvar_entidade(self.root, self.base(tipo='pessoa', nome='Joao Silva', evidencias=[self.link(self.humana())],
            identificadores=[{'tipo': 'cpf', 'valor': '22222222222', 'fonte': 0}]))
        empresa = mapa.salvar_entidade(self.root, self.base(tipo='organizacao', nome='Fornecedora Sintética Ltda.'))
        pairs = mapa.homonimos(self.root, 'alpha')
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]['situacao'], pairs[0]['motivo'], pairs[0]['identificadores_divergentes']), ('pendente', 'nome_igual', ['cpf']))
        with self.assertRaisesRegex(ValueError, 'evidência'):
            mapa.salvar_entidade(self.root, self.base(id=joao['id'], anterior_sha256=joao['sha256'], conferencias=[
                {'entidade_id': outro['id'], 'decisao': 'entidade_distinta', 'justificativa': 'CPFs diferentes.'}]), 'atualizar')
        with self.assertRaisesRegex(ValueError, 'si mesma'):
            mapa.salvar_entidade(self.root, self.base(id=joao['id'], anterior_sha256=joao['sha256'], conferencias=[
                {'entidade_id': joao['id'], 'decisao': 'indeterminado', 'justificativa': 'X'}]), 'atualizar')
        mapa.salvar_entidade(self.root, self.base(id=joao['id'], anterior_sha256=joao['sha256'], conferencias=[
            {'entidade_id': outro['id'], 'decisao': 'entidade_distinta', 'justificativa': 'CPFs diferentes.', 'fontes': [0]}]), 'atualizar')
        self.assertEqual(mapa.homonimos(self.root, 'alpha')[0]['situacao'], 'entidade_distinta')
        for bad in ({'evidencias': []}, {'evidencias': [self.link(self.ia(), 'contexto')]}, {'destino': joao['id']},
                    {'destino': 'P' + '0' * 32}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                mapa.salvar_relacao(self.root, self.base(**{'origem': joao['id'], 'destino': empresa['id'], 'tipo': 'sócio de',
                                                            'evidencias': [self.link(self.ia())], **bad}))
        rel = mapa.salvar_relacao(self.root, self.base(origem=joao['id'], destino=empresa['id'], tipo='sócio de',
                                                       evidencias=[self.link(self.ia(), suporte='sustentado')]))
        result = mapa.mapa(self.root, 'alpha')
        self.assertEqual(len(result['entidades']), 3)
        self.assertEqual(result['relacoes'][0]['id'], rel['id'])
        self.assertEqual(result['relacoes'][0]['situacao'], 'documentada')
        self.assertEqual(result['relacoes'][0]['evidencias'][0]['evidencia']['localizador']['linha_inicio'], 1)
        with self.assertRaisesRegex(ValueError, 'dígitos'):
            mapa.salvar_entidade(self.root, self.base(tipo='pessoa', nome='Maria', evidencias=[self.link(self.ia())],
                identificadores=[{'tipo': 'cpf', 'valor': '123', 'fonte': 0}]))

    # Cobertura da revisão (Working/core-revisao.md)
    def nota_da_rodada(self, rodada='R001'):
        docs = caderno.documentos(self.root, 'alpha', rodada); doc = docs['documentos'][0]
        nota = caderno.salvar(self.root, {
            'caso': 'alpha', 'rodada': rodada, 'origem_id': docs['origem_id'], 'documento_id': doc['documento_id'],
            'documento_sha256': doc['sha256'], 'pagina_pdf': None, 'localizador': 'Linha 1',
            'trecho': 'A fonte declara valor 12.', 'titulo': 'Trecho da rodada', 'anotacao': '',
            'autor': 'Repórter A', 'tipo': 'trecho', 'transcricao_manual': False, 'requisicao_id': uuid.uuid4().hex})
        return {'tipo': 'humana', 'caso_id': 'alpha', 'registro_id': nota['registro']['id'], 'sha256': nota['sha256'], 'fonte': 0}

    def test_resolucao_recusa_outro_caso_hash_divergente_e_rodada_na_lixeira(self):
        self.env.caso('beta')
        for ref in ({**self.ia(), 'caso_id': 'beta'}, {**self.humana(), 'caso_id': 'beta'}):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, 'outra apuração'):
                ev.resolver(self.root, 'alpha', ref)
        with self.assertRaisesRegex(ValueError, 'outra apuração'):
            hipoteses.salvar(self.root, self.base(enunciado='H', evidencias=[self.link({**self.ia(), 'caso_id': 'beta'})]))
        for ref in ({**self.ia(), 'registros_sha256': 'f' * 64}, {**self.humana(), 'sha256': 'f' * 64}):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                ev.resolver(self.root, 'alpha', ref)
        da_rodada = self.nota_da_rodada()
        self.assertEqual(ev.resolver(self.root, 'alpha', da_rodada)['documento']['rodada'], 'R001')
        item = lixeira.adicionar(self.root, 'rodada', 'alpha', 'Rodada sintética', rodada='R001')
        for ref in (self.ia(), da_rodada):
            with self.subTest(ref=ref['tipo']), self.assertRaisesRegex(ValueError, 'lixeira'):
                ev.resolver(self.root, 'alpha', ref)
        self.assertEqual(ev.resolver(self.root, 'alpha', self.humana())['origem'], 'humana')
        lixeira.restaurar(self.root, item['id'])
        self.assertEqual(ev.resolver(self.root, 'alpha', self.ia())['documento']['rodada'], 'R001')

    def test_recusas_nao_expoem_caminho_absoluto(self):
        for ref in ({**self.ia(), 'revisao': 'r9'}, {**self.ia(), 'rodada': 'R009'}):
            with self.subTest(ref=ref):
                with self.assertRaises(ValueError) as ctx:
                    ev.resolver(self.root, 'alpha', ref)
                self.assertNotIn(str(self.root), str(ctx.exception))

    def test_hipotese_sem_suporte_aparece_como_lacuna_e_pendencia(self):
        vazia = hipoteses.salvar(self.root, self.base(enunciado='Hipótese sem vínculo.'))
        so_contexto = hipoteses.salvar(self.root, self.base(enunciado='Hipótese só com contexto.',
                                                            evidencias=[self.link(self.ia(), 'contexto')]))
        pendente = hipoteses.salvar(self.root, self.base(enunciado='Hipótese com suporte pendente.',
                                                         evidencias=[self.link(self.ia())]))
        rows = {r['id']: r for r in hipoteses.quadro(self.root, 'alpha')['hipoteses']}
        for item in (vazia, so_contexto):
            row = rows[item['id']]
            with self.subTest(enunciado=row['enunciado']):
                self.assertEqual((row['condicao'], row['natureza'], row['sustentam']), ('pendencia', 'pendencia', []))
                self.assertIn({'origem': 'automatica', 'descricao': 'Nenhuma evidência de suporte conferida.',
                               'diligencia_id': None, 'diligencia_estado': None}, row['faltam'])
        row = rows[pendente['id']]
        self.assertEqual((row['condicao'], row['natureza'], len(row['sustentam'])), ('pendencia', 'pendencia', 1))
        self.assertTrue(any('pendência' in f['descricao'] for f in row['faltam']))
        self.assertEqual(rows[so_contexto['id']]['contexto'][0]['evidencia']['trecho'], 'A fonte declara valor 12.')
        with self.assertRaisesRegex(ValueError, 'sustentada'):
            hipoteses.salvar(self.root, self.base(id=vazia['id'], anterior_sha256=vazia['sha256'], situacao='sustentada'), 'atualizar')
        with self.assertRaisesRegex(ValueError, 'Pendência'):
            hipoteses.salvar(self.root, self.base(enunciado='X', evidencias=[
                self.link(self.ia(), suporte='sustentado', natureza='pendencia')]))

    def test_linha_do_tempo_ordena_data_parcial_no_inicio_do_periodo(self):
        links = [self.link(self.ia())]
        for descricao, valor in (('Dia', '2021-03-12'), ('Ano', '2021'), ('Mês', '2021-03'), ('Ano anterior', '2020-12-31')):
            linha_tempo.salvar(self.root, self.base(descricao=descricao, evidencias=links,
                                                    datas=[{'tipo': 'fato', 'valor': valor, 'fonte': 0}]))
        result = linha_tempo.linha(self.root, 'alpha')
        self.assertEqual([(e['descricao'], e['data']['precisao']) for e in result['entradas']],
                         [('Ano anterior', 'dia'), ('Ano', 'ano'), ('Mês', 'mes'), ('Dia', 'dia')])
        for entry in result['entradas']:
            self.assertTrue(entry['fonte_conferida'])
            self.assertEqual(entry['fonte_da_data']['evidencia']['localizador']['linha_inicio'], 1)
        self.assertEqual(result['divergencias'], [])
        self.assertTrue({'fato', 'emissao_documento', 'publicacao', 'registro'} <= set(result['tipos_data']))
        mixed = linha_tempo.salvar(self.root, self.base(descricao='Precisões distintas', evidencias=links, datas=[
            {'tipo': 'registro', 'valor': '2022-05', 'fonte': 0}, {'tipo': 'registro', 'valor': '2022-05-10', 'fonte': 0}]))
        div = [d for d in linha_tempo.linha(self.root, 'alpha')['divergencias'] if d['evento_id'] == mixed['id']]
        self.assertEqual([(d['tipo'], d['classe']) for d in div], [('registro', 'compativel_precisao_diferente')])

    def test_comparador_nao_calcula_diferenca_com_unidades_incompativeis(self):
        result = comparador.comparar_textos('Foram entregues 10 kg de insumos.', 'Foram entregues 10 t de insumos.')
        change = result['alteracoes'][0]
        self.assertEqual((change['operacao'], change['classe']), ('substituido', 'valor'))
        self.assertEqual((change['calculo']['diferenca'], change['calculo']['motivo']), (None, 'unidades_incompativeis'))
        self.assertEqual(result['marcas']['comuns'], [])
        for a, b in (('R$ 10,00', 'US$ 10,00'), ('12,5%', 'R$ 12,50'), ('10 kg', '10 m')):
            with self.subTest(a=a, b=b):
                calc = comparador.calculo(a, b)
                self.assertEqual((calc['diferenca'], calc['motivo']), (None, 'unidades_incompativeis'))
        self.assertEqual(comparador.calculo('10 kg', '12 kg')['diferenca'], '2')
        self.assertEqual(comparador.calculo('R$ 1.234,56', 'R$ 1.500,00')['diferenca'], '265.44')
        self.assertEqual(comparador.calculo('1 e 2 kg', '3 kg')['motivo'], 'pareamento_ambiguo')
        texto = json.dumps(result, ensure_ascii=False).lower()
        for termo in ('fraude', 'culpa', 'irregular'):
            self.assertNotIn(termo, texto)

    def test_homonimos_sugerem_conferencia_sem_fundir(self):
        a = mapa.salvar_entidade(self.root, self.base(tipo='pessoa', nome='Maria Souza', evidencias=[self.link(self.ia())],
            identificadores=[{'tipo': 'cpf', 'valor': '33333333333', 'fonte': 0}]))
        b = mapa.salvar_entidade(self.root, self.base(tipo='pessoa', nome='Maria Pereira', evidencias=[self.link(self.humana())],
            identificadores=[{'tipo': 'cpf', 'valor': '33333333333', 'fonte': 0}]))
        c = mapa.salvar_entidade(self.root, self.base(tipo='pessoa', nome='MARIA  SOUZA', evidencias=[self.link(self.humana())]))
        pares = {frozenset(p['entidades']): p for p in mapa.homonimos(self.root, 'alpha')}
        self.assertEqual(pares[frozenset((a['id'], b['id']))]['motivo'], 'identificador_igual')
        self.assertEqual(pares[frozenset((a['id'], c['id']))]['motivo'], 'nome_igual')
        for par in pares.values():
            self.assertEqual(par['situacao'], 'pendente')
            self.assertIn('não foram fundidas', par['aviso'])
        mapa.salvar_entidade(self.root, self.base(id=a['id'], anterior_sha256=a['sha256'], conferencias=[
            {'entidade_id': c['id'], 'decisao': 'mesma_entidade', 'justificativa': 'Mesmo nome e documento.', 'fontes': [0]}]),
            'atualizar')
        par = next(p for p in mapa.homonimos(self.root, 'alpha') if set(p['entidades']) == {a['id'], c['id']})
        self.assertEqual(par['situacao'], 'mesma_entidade')
        result = mapa.mapa(self.root, 'alpha')
        self.assertEqual({e['id'] for e in result['entidades']}, {a['id'], b['id'], c['id']})
        for item in (a, c):
            self.assertEqual(mapa.detalhe_entidade(self.root, 'alpha', item['id'])['id'], item['id'])

    def test_nome_normalizado(self):
        self.assertEqual(mapa.nome_normalizado('José  DOS Santos'), 'jose santos')
        self.assertEqual(mapa.nome_normalizado('Fornecedora Sintética Ltda.', 'organizacao'), 'fornecedora sintetica')


if __name__ == '__main__':
    unittest.main()
