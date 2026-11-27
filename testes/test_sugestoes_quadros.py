"""P45: as sugestões da IA nos quadros e as decisões das pessoas (contrato CONTRATO_QUADROS_ONDA4, seção 2).

Sobre a rodada sintética de ``fixture_achados`` (A001 v2 sustentado e incluído na r2, com E001 de suporte; a r1 tem
A001 v1 sem revisão), os candidatos são gravados como a síntese grava. Listar, confirmar, corrigir, descartar e
restaurar passam pela rota (``rotas_evidencia.executar``). Nomes sintéticos; sem modelo e sem rede.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente
from test_vinculo_ia import publicar_r3_com_e_id_compartilhada
import erros
import evidencias as ev
import hipoteses
import linha_tempo
import mapa_relacoes as mapa
from registros_achados import carregar, publicar
import rotas_evidencia
import sugestoes_quadros as sq

CANDIDATOS = [
    {'chave': 'C1', 'tipo': 'pessoa', 'achado_id': 'A001', 'evidencias': ['E001'], 'campos': {'nome': 'Marta Reis'}},
    {'chave': 'C2', 'tipo': 'organizacao', 'achado_id': 'A001', 'evidencias': ['E001'],
     'campos': {'nome': 'Construtora Alfa Ltda.', 'variantes': ['Construtora Alfa']}},
    {'chave': 'C3', 'tipo': 'ligacao', 'achado_id': 'A001', 'evidencias': ['E001'],
     'campos': {'de': 'C1', 'para': 'C2', 'tipo': 'sócia', 'descricao': 'Sócia segundo o contrato social.'}},
    {'chave': 'C4', 'tipo': 'acontecimento', 'achado_id': 'A001', 'evidencias': ['E001', 'E003'],
     'campos': {'descricao': 'Declaração do valor 12 em Vila Serena', 'datas': [{'tipo': 'declarada_por_fonte', 'valor': '2025'}]}},
    {'chave': 'C5', 'tipo': 'hipotese', 'achado_id': 'A001', 'evidencias': ['E001'],
     'campos': {'enunciado': 'A Construtora Alfa declarou valor 12 no Contrato 041/2025.'}},
]


class SugestoesQuadrosTest(unittest.TestCase):
    def setUp(self):
        self.env, (_, _, _, _) = Ambiente.copia_completa(); self.addCleanup(self.env.cleanup)
        self.root = self.env.root
        self.gravar('r2', CANDIDATOS)

    def gravar(self, revisao, candidatos):
        data, manifest = carregar(self.root, 'alpha', 'R001', revisao)
        record = sq.gravar(self.env.run(), data, candidatos, '1.3.0')
        self.assertEqual(record['registros_sha256'], manifest['registros_sha256'])  # the predicted hash is the published one
        return record

    def op(self, operation, **data):
        return rotas_evidencia.executar(self.root, operation, {'caso': 'alpha', **data})

    def listar(self, quadro, **extra):
        return self.op('sugestoes-listar', quadro=quadro, **extra)

    def por_chave(self, quadro, chave, revisao='r2', **extra):
        _, manifest = carregar(self.root, 'alpha', 'R001', revisao)
        sid = sq.identidade('alpha', 'R001', manifest['registros_sha256'], chave)
        return next(s for s in self.listar(quadro, incluir_decididas=True, **extra)['sugestoes'] if s['id'] == sid)

    def acao(self, acao, sugestao, autor='Ana Lima', rid=None, **extra):
        return self.op(f'sugestoes-{acao}', id=sugestao['id'], requisicao_id=rid or uuid.uuid4().hex, autor=autor, **extra)

    def codigo(self, call):
        with self.assertRaises(ValueError) as caught:
            call()
        return erros.codigo_de(str(caught.exception))

    # --- listar ------------------------------------------------------------------------------------

    def test_lista_por_quadro_com_campos_prontos_para_criar_e_a_origem(self):
        found = self.listar('mapa')
        self.assertEqual(found['contagem'], {'abertas': 3, 'descartadas': 0})
        self.assertEqual([s['tipo'] for s in found['sugestoes']], ['pessoa', 'organizacao', 'ligacao'])
        pessoa, _, ligacao = found['sugestoes']
        self.assertEqual(set(pessoa['campos']), {'tipo', 'nome', 'variantes', 'identificadores', 'evidencias'})
        link = pessoa['campos']['evidencias'][0]
        self.assertEqual((link['papel'], link['suporte'], link['natureza'], link['justificativa']),
                         ('suporte', 'sustentado', 'alegacao_atribuida', 'Relação sintética atribuída.'))
        self.assertEqual(set(link['referencia']), ev.CAMPOS_REF['ia'])
        self.assertEqual((pessoa['estado'], pessoa['decisao'], pessoa['bloqueio'], pessoa['avisos'], pessoa['pontas']),
                         ('aberta', None, None, [], None))
        self.assertEqual((pessoa['achado']['id'], pessoa['achado']['versao'], pessoa['achado']['suporte_ia'],
                          pessoa['achado']['destino'], pessoa['achado']['versao_atual']), ('A001', 2, 'sustentado', 'incluido', 2))
        self.assertEqual((pessoa['analise']['rodada'], pessoa['analise']['revisao']), ('R001', 'r2'))
        self.assertEqual(pessoa['evidencias'][0]['estado'], 'conferida')
        self.assertEqual(pessoa['evidencias'][0]['revisao_ia']['destino'], 'incluido')
        self.assertTrue(all(not k.startswith('_') for k in pessoa))
        self.assertEqual((ligacao['campos']['origem'], ligacao['campos']['destino'], ligacao['bloqueio']),
                         (None, None, 'ponta_ainda_sugestao'))
        self.assertEqual([ligacao['pontas'][s]['nome'] for s in ('origem', 'destino')], ['Marta Reis', 'Construtora Alfa Ltda.'])
        evento = self.listar('linha_tempo')['sugestoes'][0]
        self.assertEqual([(l['papel'], l['suporte']) for l in evento['campos']['evidencias']],
                         [('suporte', 'sustentado'), ('contexto', 'nao_revisado')])
        hip = self.listar('hipoteses')['sugestoes'][0]
        self.assertEqual((hip['campos']['situacao'], hip['campos']['lacunas']), ('em_aberto', []))

    def test_rodada_sem_candidatos_nao_traz_sugestao(self):
        self.env.caso('beta')
        found = rotas_evidencia.executar(self.root, 'sugestoes-listar', {'caso': 'beta', 'quadro': 'mapa'})
        self.assertEqual((found['sugestoes'], found['contagem']), ([], {'abertas': 0, 'descartadas': 0}))

    def test_arquivo_adulterado_ou_de_outra_revisao_nao_aparece(self):
        path = sq.caminho(self.env.run(), 'r2')
        path.write_text(path.read_text(encoding='utf-8').replace('"registros_sha256": "', '"registros_sha256": "0'),
                        encoding='utf-8')
        self.assertEqual(self.listar('mapa')['sugestoes'], [])

    # --- confirmar ---------------------------------------------------------------------------------

    def test_confirmar_cria_o_item_com_o_vinculo_da_revisao_e_registra_quem_decidiu(self):
        pessoa = self.listar('mapa')['sugestoes'][0]
        result = self.acao('confirmar', pessoa)
        item = result['item']
        self.assertTrue(item['id'].startswith('P'))
        self.assertEqual((item['estado']['nome'], item['estado']['tipo']), ('Marta Reis', 'pessoa'))
        saved = item['estado']['evidencias'][0]
        self.assertEqual(saved['revisao_ia']['suporte'], 'sustentado')
        self.assertNotIn('alteracoes', saved)
        decided = result['sugestao']
        self.assertEqual((decided['estado'], decided['decisao']['acao'], decided['decisao']['por'], decided['decisao']['item_id']),
                         ('confirmada', 'confirmar', 'Ana Lima', item['id']))
        found = self.listar('mapa')
        self.assertEqual(found['contagem'], {'abertas': 2, 'descartadas': 0})
        self.assertNotIn(pessoa['id'], [s['id'] for s in found['sugestoes']])
        ligacao = self.por_chave('mapa', 'C3')
        self.assertEqual((ligacao['pontas']['origem']['item_id'], ligacao['campos']['origem']), (item['id'], item['id']))
        hip = self.acao('confirmar', self.listar('hipoteses')['sugestoes'][0])['item']
        self.assertEqual(hipoteses.detalhe(self.root, 'alpha', hip['id'])['estado']['situacao'], 'em_aberto')

    def test_ligacao_espera_as_pontas_e_descartar_e_restaurar_se_desfazem(self):
        pessoa, org, ligacao = self.listar('mapa')['sugestoes']
        code, params = self.codigo(lambda: self.acao('confirmar', ligacao))
        self.assertEqual((code, params), ('ponta_ainda_sugestao', {'ponta': 'origem'}))
        self.acao('confirmar', pessoa)
        self.assertEqual(self.codigo(lambda: self.acao('confirmar', ligacao)), ('ponta_ainda_sugestao', {'ponta': 'destino'}))
        discarded = self.acao('descartar', org)
        self.assertEqual((discarded['sugestao']['estado'], discarded['item']), ('descartada', None))
        self.assertEqual(self.listar('mapa')['contagem'], {'abertas': 1, 'descartadas': 1})
        self.assertEqual(self.por_chave('mapa', 'C3')['bloqueio'], 'ponta_descartada')
        self.assertEqual(self.codigo(lambda: self.acao('confirmar', ligacao)), ('ponta_descartada', {'ponta': 'destino'}))
        self.assertEqual(self.codigo(lambda: self.acao('confirmar', org))[0], 'sugestao_ja_decidida')
        self.assertEqual(self.codigo(lambda: self.acao('restaurar', pessoa))[0], 'sugestao_ja_decidida')
        restored = self.acao('restaurar', org)
        self.assertEqual((restored['sugestao']['estado'], restored['item']), ('aberta', None))
        self.acao('confirmar', org)
        made = self.acao('confirmar', ligacao)['item']
        self.assertTrue(made['id'].startswith('L'))
        self.assertEqual((made['estado']['origem'], made['estado']['tipo']), (self.por_chave('mapa', 'C1')['decisao']['item_id'], 'sócia'))
        self.assertEqual(len(mapa.listar_relacoes(self.root, 'alpha')), 1)

    def test_repetir_com_a_mesma_tentativa_nao_duplica(self):
        hip = self.listar('hipoteses')['sugestoes'][0]
        rid = uuid.uuid4().hex
        first = self.acao('confirmar', hip, rid=rid)
        again = self.acao('confirmar', hip, rid=rid)
        self.assertEqual(first['item']['id'], again['item']['id'])
        self.assertEqual(len(hipoteses.listar(self.root, 'alpha')), 1)
        self.assertEqual(len(sq.DECISOES.listar(self.root, 'alpha')), 1)
        self.assertEqual(self.codigo(lambda: self.acao('descartar', hip, rid=rid))[0], 'tentativa_reutilizada')
        self.assertEqual(self.codigo(lambda: self.acao('confirmar', hip))[0], 'sugestao_ja_decidida')

    # --- corrigir ----------------------------------------------------------------------------------

    def test_corrigir_cria_o_item_editado_e_marca_o_que_a_pessoa_mudou(self):
        evento = self.listar('linha_tempo')['sugestoes'][0]
        campos = deepcopy(evento['campos'])
        campos['descricao'] = 'Declaração do valor 12, segundo a fonte sintética'
        campos['evidencias'][0]['suporte'] = 'parcial'
        result = self.acao('corrigir', evento, autor='Carlos Prado', campos=campos)
        self.assertEqual(result['sugestao']['decisao']['alterados'], ['descricao'])
        saved = linha_tempo.detalhe(self.root, 'alpha', result['item']['id'])['estado']
        self.assertEqual(saved['descricao'], campos['descricao'])
        mark = saved['evidencias'][0]['alteracoes']['suporte']
        self.assertEqual((mark['anterior'], mark['valor'], mark['por']), ('sustentado', 'parcial', 'Carlos Prado'))

    def test_corrigir_a_ligacao_trocando_a_ponta_por_uma_entidade_do_mapa(self):
        _, org, ligacao = self.listar('mapa')['sugestoes']
        existing = mapa.salvar_entidade(self.root, {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Ana Lima',
                                                    'tipo': 'pessoa', 'nome': 'Carlos Prado', 'evidencias': []})
        self.acao('confirmar', org)
        campos = {**deepcopy(ligacao['campos']), 'origem': existing['id'], 'destino': self.por_chave('mapa', 'C2')['decisao']['item_id']}
        self.assertEqual(self.codigo(lambda: self.acao('corrigir', ligacao, campos={**campos, 'origem': None})),
                         ('ponta_ainda_sugestao', {'ponta': 'origem'}))
        made = self.acao('corrigir', ligacao, campos=campos)
        self.assertEqual(made['sugestao']['decisao']['alterados'], ['origem'])
        self.assertEqual(made['item']['estado']['origem'], existing['id'])
        self.assertEqual(self.codigo(lambda: self.acao('corrigir', ligacao, campos={**campos, 'caso': 'beta'}))[0],
                         'sugestao_ja_decidida')

    def test_corrigir_aplica_as_regras_do_quadro(self):
        hip = self.listar('hipoteses')['sugestoes'][0]
        campos = {**deepcopy(hip['campos']), 'situacao': 'contrariada'}
        with self.assertRaisesRegex(ValueError, 'Para marcar como contrariada'):
            self.acao('corrigir', hip, campos=campos)
        self.assertEqual(self.codigo(lambda: self.acao('corrigir', hip, campos={**hip['campos'], 'requisicao_id': 'x'}))[0],
                         'quadro_campos_invalidos')
        self.assertEqual(self.por_chave('hipoteses', 'C5')['estado'], 'aberta')

    # --- bloqueios ---------------------------------------------------------------------------------

    def com_revisao(self, **mudar):
        """Lists with the newest revision (r2) seen as if its review or synthesis had said otherwise."""
        real = sq.vinculo_ia._dados

        def alterado(root, case, rodada, revisao, cache):
            data, manifest = deepcopy(real(root, case, rodada, revisao, {}))
            for review in data['revisoes_assistidas']:
                review['suporte'] = mudar.get('suporte', review['suporte'])
            for fate in data['destinos']:
                fate['destino'] = mudar.get('destino', fate['destino'])
            return data, manifest
        return patch.object(sq.vinculo_ia, '_dados', alterado)

    def test_confirmar_fica_indisponivel_com_a_razao_de_cada_caso(self):
        for mudar, code in (({'destino': 'retirado'}, 'achado_retirado'), ({'suporte': 'nao_sustentado'}, 'nao_sustentado'),
                            ({'suporte': 'ilegivel'}, 'ilegivel'), ({'destino': 'substituido'}, 'versao_substituida')):
            with self.subTest(code=code), self.com_revisao(**mudar):
                pessoa = self.listar('mapa')['sugestoes'][0]
                self.assertEqual(pessoa['bloqueio'], code)
                self.assertEqual(self.codigo(lambda: self.acao('confirmar', pessoa))[0], code)
        with self.com_revisao(destino='retirado'):
            self.assertIn('achado_retirado', self.listar('mapa')['sugestoes'][0]['avisos'])
        with patch.object(ev, 'resolver', side_effect=ValueError('Fonte da evidência ausente nesta apuração.')):
            pessoa = self.listar('mapa')['sugestoes'][0]
            self.assertEqual((pessoa['bloqueio'], pessoa['evidencias'][0]['estado']), ('evidencia_indisponivel', 'indisponivel'))
            self.assertEqual(self.codigo(lambda: self.acao('confirmar', pessoa))[0], 'evidencia_indisponivel')
        pessoa = self.listar('mapa')['sugestoes'][0]
        self.acao('descartar', pessoa)  # "Corrigir" and "Descartar" never wait for the review

    def test_versao_substituida_e_ja_descartada_entre_rodadas(self):
        self.gravar('r1', CANDIDATOS[:1])  # A001 v1, before the review: v2 came after it
        old = self.por_chave('mapa', 'C1', 'r1')
        self.assertEqual((old['achado']['versao'], old['achado']['versao_atual'], old['bloqueio']), (1, 2, 'versao_substituida'))
        # The fill and the verdict come from the newest revision of the round (B1 of the Coruja on ef88880).
        self.assertNotIn('analise_sem_revisao', old['avisos'])
        link = old['campos']['evidencias'][0]
        self.assertEqual((link['referencia']['revisao'], link['suporte']), ('r2', 'sustentado'))
        self.assertEqual(old['analise']['revisao'], 'r1')
        new = self.por_chave('mapa', 'C1')
        self.acao('descartar', new)
        old = self.por_chave('mapa', 'C1', 'r1')
        self.assertEqual(old['estado'], 'descartada')
        self.assertEqual((old['decisao'], old['descartada_antes']['sugestao_id'], old['descartada_antes']['por']),
                         (None, new['id'], 'Ana Lima'))
        self.assertEqual(self.acao('restaurar', old)['sugestao']['estado'], 'aberta')

    # --- recusas da rota ---------------------------------------------------------------------------

    def test_recusas_da_rota_com_codigo(self):
        self.assertEqual(self.codigo(lambda: self.listar('tabelas'))[0], 'quadro_sugestao_invalido')
        self.assertEqual(self.codigo(lambda: self.listar('mapa', outro=1))[0], 'quadro_campos_invalidos')
        self.assertEqual(self.codigo(lambda: self.op('sugestoes-confirmar', id='S' + 'e' * 32, requisicao_id=uuid.uuid4().hex,
                                                     autor='Ana Lima'))[0], 'sugestao_inexistente')
        self.assertEqual(self.codigo(lambda: self.op('sugestoes-confirmar', id='../S', requisicao_id=uuid.uuid4().hex))[0],
                         'sugestao_inexistente')
        pessoa = self.listar('mapa')['sugestoes'][0]
        self.assertEqual(self.codigo(lambda: self.acao('confirmar', pessoa, campos={}))[0], 'quadro_campos_invalidos')
        with self.assertRaisesRegex(ValueError, 'Selecione uma apuração'):
            rotas_evidencia.executar(self.root, 'sugestoes-listar', {'caso': '../alpha', 'quadro': 'mapa'})
        with self.assertRaisesRegex(ValueError, 'não liberada'):
            rotas_evidencia.executar(self.root, 'sugestoes-descartar', {'caso': 'alpha', 'id': pessoa['id']}, casos={'beta'})


    # --- ressalvas da Coruja sobre c06ea1e --------------------------------------------------------

    def test_candidato_com_cpf_ou_cnpj_no_texto_e_recusado(self):
        data, _ = carregar(self.root, 'alpha', 'R001', 'r2')
        for texto in ('Marta Reis, CPF 123.456.789-09', 'Marta Reis 12345678909', 'Construtora Alfa 12.345.678/0001-90',
                      'Construtora Alfa 12345678000190'):
            aceitos, recusados = sq.conferir([{**CANDIDATOS[0], 'campos': {'nome': texto}}], data)
            self.assertEqual([r['codigo'] for r in recusados], ['dado_pessoal'], texto)
        hip = {**CANDIDATOS[4], 'campos': {'enunciado': 'O CNPJ 12.345.678/0001-90 assinou o Contrato 041/2025.'}}
        self.assertEqual([r['codigo'] for r in sq.conferir([hip], data)[1]], ['dado_pessoal'])
        # Dates, contract numbers and amounts are not personal data.
        aceitos, recusados = sq.conferir([CANDIDATOS[3], {**CANDIDATOS[4], 'campos': {
            'enunciado': 'O Contrato 041/2025, de R$ 1.234.567,89, foi assinado em 03/03/2025.'}}], data)
        self.assertEqual((len(aceitos), recusados), (2, []))

    def test_arquivo_do_agente_de_chat_e_conferido_de_novo_e_recusados_ignorados(self):
        path = sq.caminho(self.env.run(), 'r2')
        record = sq.ler_json(path)
        record['candidatos'].append({'chave': 'C9', 'tipo': 'pessoa', 'achado_id': 'A999', 'evidencias': ['E001'],
                                     'campos': {'nome': 'Carlos Prado'}})
        record['recusados'] = [{'chave': 'C1', 'codigo': 'achado_inexistente', 'motivo': 'Escrito à mão.'}]
        path.write_bytes((sq.json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        nomes = [s['campos']['nome'] for s in self.listar('mapa')['sugestoes'] if s['tipo'] != 'ligacao']
        self.assertEqual(nomes, ['Marta Reis', 'Construtora Alfa Ltda.'])

    def test_o_preenchimento_usa_o_achado_do_candidato(self):
        self.gravar_r3 = publicar_r3_com_e_id_compartilhada(self.env)
        self.gravar('r3', [{'chave': 'C1', 'tipo': 'pessoa', 'achado_id': 'A003', 'evidencias': ['E001'],
                            'campos': {'nome': 'Carlos Prado'}}])
        sug = self.por_chave('mapa', 'C1', 'r3')
        link = sug['campos']['evidencias'][0]
        self.assertEqual((link['achado_id'], link['suporte'], link['justificativa']),
                         ('A003', 'nao_revisado', 'Mesma linha, outra afirmação.'))
        self.assertEqual((sug['evidencias'][0]['revisao_ia']['achado_id'], sug['achado']['id'], sug['bloqueio']),
                         ('A003', 'A003', 'achado_retirado'))
        made = self.acao('corrigir', sug, campos=deepcopy(sug['campos']))['item']
        self.assertEqual(made['estado']['evidencias'][0]['revisao_ia']['achado_id'], 'A003')

    def test_mapa_entidade_detalhe_devolve_o_registro_sem_mascara(self):
        pessoa = self.listar('mapa')['sugestoes'][0]
        campos = deepcopy(pessoa['campos'])
        campos['identificadores'] = [{'tipo': 'cpf', 'valor': '123.456.789-09', 'fonte': 0}]
        made = self.acao('corrigir', pessoa, campos=campos)['item']
        found = self.op('mapa-entidade-detalhe', id=made['id'])
        self.assertEqual((found['id'], found['sha256']), (made['id'], made['sha256']))
        self.assertEqual(found['estado']['identificadores'][0]['valor'], '12345678909')
        self.assertEqual(found['evidencias'][0]['estado'], 'conferida')
        self.assertEqual(found['evidencias'][0]['revisao_ia']['achado_id'], 'A001')
        self.assertEqual(self.codigo(lambda: self.op('mapa-entidade-detalhe', id='P' + 'e' * 32))[0], 'registro_inexistente')
        self.assertEqual(self.codigo(lambda: self.op('mapa-entidade-detalhe', id=made['id'], extra=1))[0],
                         'quadro_campos_invalidos')


    # --- ressalvas da Coruja sobre ef88880 --------------------------------------------------------

    def retirar_a001_numa_r3(self):
        """r3 over r2: the review takes A001 v2 down (não sustentado, retirar) and the synthesis withdraws it."""
        data, manifest = carregar(self.root, 'alpha', 'R001', 'r2')
        r3 = self.env.sucessora(data, {'manifesto': manifest}, 'r3')
        r3['revisoes_assistidas'].append({'achado_id': 'A001', 'versao': 2, 'suporte': 'nao_sustentado',
                                          'motivo': 'Releitura sintética.', 'fontes_reabertas': ['E001'],
                                          'limitacoes': 'Revisão pela IA.', 'acao': 'retirar'})
        r3['destinos'].append({'achado_id': 'A001', 'versao': 2, 'destino': 'retirado', 'motivo': 'Não sustentado.',
                               'briefing': None, 'revisao_suporte': None})
        r3['procedencia'].append({'etapa': 'sintese', 'artefatos': [], 'ferramentas': ['fixture'], 'modelo_informado_ou_observado': None})
        self.env.relatorio(r3, 'saidas/08c_insuficiencia.md', 'insuficiencia', 'Sem achados com suporte.', -1)
        return publicar(self.root, 'alpha', 'R001', r3)['manifesto']['registros_sha256']

    def test_revisao_seguinte_que_retira_o_achado_vale_para_a_sugestao(self):
        r3 = self.retirar_a001_numa_r3()
        pessoa = self.listar('mapa')['sugestoes'][0]
        self.assertEqual((pessoa['achado']['destino'], pessoa['achado']['suporte_ia'], pessoa['bloqueio']),
                         ('retirado', 'nao_sustentado', 'achado_retirado'))
        self.assertIn('achado_retirado', pessoa['avisos'])
        link = pessoa['campos']['evidencias'][0]
        self.assertEqual((link['referencia']['revisao'], link['referencia']['registros_sha256'], link['suporte']),
                         ('r3', r3, 'nao_revisado'))
        self.assertEqual(pessoa['evidencias'][0]['revisao_ia']['destino'], 'retirado')
        self.assertEqual(pessoa['analise']['revisao'], 'r2')  # the analysis that suggested it does not change
        self.assertEqual(self.codigo(lambda: self.acao('confirmar', pessoa))[0], 'achado_retirado')
        made = self.acao('corrigir', pessoa, campos=deepcopy(pessoa['campos']))['item']
        saved = made['estado']['evidencias'][0]
        self.assertEqual((saved['suporte'], saved['revisao_ia']['destino'], 'alteracoes' in saved), ('nao_revisado', 'retirado', False))

    def test_decisao_divergente_trava_so_a_propria_sugestao(self):
        pessoa, org, _ = self.listar('mapa')['sugestoes']
        self.acao('descartar', pessoa)
        record = sq.DECISOES.listar(self.root, 'alpha')[0]
        folder = sq.DECISOES.pasta(self.root, 'alpha') / record['id']
        event = next(folder.glob('*.json'))
        content = sq.ler_json(event)
        content['estado']['alterados'] = ['adulterado']
        event.write_bytes((sq.json.dumps(content, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        found = {s['id']: s for s in self.listar('mapa', incluir_decididas=True)['sugestoes']}
        self.assertEqual((found[pessoa['id']]['bloqueio'], 'decisao_divergente' in found[pessoa['id']]['avisos']),
                         ('historico_divergente', True))
        self.assertEqual(self.codigo(lambda: self.acao('restaurar', found[pessoa['id']]))[0], 'historico_divergente')
        self.assertEqual(found[org['id']]['bloqueio'], None)
        self.assertEqual(self.acao('confirmar', found[org['id']])['sugestao']['estado'], 'confirmada')
        # A record with nothing readable could hide a confirmation: then nothing is decided.
        event.write_bytes(b'{')
        self.assertEqual(self.codigo(lambda: self.listar('mapa'))[0], 'historico_divergente')

    def test_mapa_entidade_detalhe_so_para_quem_edita_o_mapa(self):
        import autorizacao
        for papel, alcanca in (('dono', True), ('editor', True), ('reporter', True), ('leitor', False), ('convidado', False)):
            caps = autorizacao.capacidades(None, 'local-contas', {'papel': papel})
            self.assertEqual('mapa-entidade-detalhe' in caps, alcanca, papel)
            self.assertEqual('mapa-entidade-detalhe' in caps, 'mapa-entidade-atualizar' in caps, papel)

    def test_cpf_e_cnpj_com_espacos_ou_tracos_tambem_sao_recusados(self):
        data, _ = carregar(self.root, 'alpha', 'R001', 'r2')
        for texto in ('Marta Reis 123 456 789 09', 'Marta Reis 123.456.789 – 09', 'Alfa 12 345 678 / 0001 - 90',
                      'Marta Reis 123456789\u00a009'):
            recusados = sq.conferir([{**CANDIDATOS[0], 'campos': {'nome': texto}}], data)[1]
            self.assertEqual([r['codigo'] for r in recusados], ['dado_pessoal'], texto)


if __name__ == '__main__':
    unittest.main()
