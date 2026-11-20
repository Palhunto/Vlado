"""Canonical findings acceptance with synthetic frozen documents only."""
import copy
import json
from pathlib import Path
from runpy import run_path
from shutil import copyfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import sha256
from fixture_achados import Ambiente
from registros_achados import publicar, carregar, validar, trava, conferir_evidencia


class AchadosTest(unittest.TestCase):
    def setUp(self):
        self.fx = Ambiente()
        self.addCleanup(self.fx.cleanup)
        self.root, self.run = self.fx.root, self.fx.run()

    def test_registro_correcao_briefing_historico_sem_aprovacao_humana(self):
        initial, revised, first, second = self.fx.completo()
        self.assertEqual(carregar(self.root,'alpha','R001','r1')[0], initial)
        self.assertEqual(carregar(self.root,'alpha','R001','r2')[0], revised)
        self.assertEqual(revised['conferencias_humanas'], [])
        self.assertEqual(second['manifesto']['anterior']['registros_sha256'], first['manifesto']['registros_sha256'])
        self.assertTrue((self.run / first['arquivo_recibo']).is_file())

    def test_fonte_fora_snapshot_hash_intervalo_trecho_e_indice_errado(self):
        original = self.fx.dados()
        mutations = [lambda e:e.update(original='../fora.txt'), lambda e:e.update(original_sha256='0'*64),
                     lambda e:e.update(fonte_textual='entradas/fora.txt'), lambda e:e.update(fonte_sha256='0'*64),
                     lambda e:e['localizador'].update(linha_fim=900), lambda e:e['localizador'].update(pagina_pdf=1),
                     lambda e:e.update(trecho='Não existe.'), lambda e:e['indice'].update(indice_id='0'*64),
                     lambda e:e['indice'].update(referencia='0'*64)]
        for mutation in mutations:
            data = copy.deepcopy(original)
            mutation(data['evidencias'][0])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validar(self.root,'alpha','R001',data)
        (self.run / original['evidencias'][0]['original']).unlink()
        with self.assertRaises(ValueError):
            validar(self.root,'alpha','R001',original)

    def test_visual_sem_fts_e_localizadores_invalidos(self):
        data = self.fx.dados()
        visual = data['evidencias'][2]
        self.assertIsNone(conferir_evidencia(self.root,'alpha','R001',visual)['contexto'])
        for values in ({'pagina_pdf':2}, {'linha_inicio':1}, {'tipo':'celula','descricao':'A1'}):
            ev = copy.deepcopy(visual)
            ev['localizador'].update(values)
            with self.assertRaises(ValueError):
                conferir_evidencia(self.root,'alpha','R001',ev)
        ev = copy.deepcopy(data['evidencias'][0])
        ev.update(modo='visual',fonte_textual=None,fonte_sha256=None,indice=None)
        ev['localizador'].update(tipo='pagina',pagina_pdf=1,linha_inicio=None,linha_fim=None)
        with self.assertRaises(ValueError):
            conferir_evidencia(self.root,'alpha','R001',ev)

    def test_celula_csv_limites_e_literal(self):
        data = self.fx.dados()
        docs = json.loads((self.run/'entradas/casos/alpha/manifesto.json').read_text(encoding='utf-8'))['documentos']
        ev = copy.deepcopy(data['evidencias'][2])
        ev.update(documento_id='D003',original='entradas/'+docs[2]['arquivo'],original_sha256=docs[2]['sha256'],trecho='12')
        ev['localizador'].update(tipo='celula',pagina_pdf=None,descricao='B2')
        conferir_evidencia(self.root,'alpha','R001',ev)
        for position in ('B3','C2','Planilha1!A1'):
            ev['localizador']['descricao'] = position
            with self.assertRaises(ValueError):
                conferir_evidencia(self.root,'alpha','R001',ev)

    def test_ids_orfaos_status_sem_suporte_e_humano_inventado(self):
        original = self.fx.dados()
        mutations = [lambda d:d['vinculos'][0].update(evidencia_id='E999'),
                     lambda d:d['vinculos'][0].update(versao=3),
                     lambda d:d['achados'][1]['versoes'][0].update(natureza='inferencia'),
                     lambda d:d['achados'][0]['versoes'][0].update(natureza='verificado'),
                     lambda d:d['evidencias'].append(copy.deepcopy(d['evidencias'][0])),
                     lambda d:d['conferencias_humanas'].append({'achado_id':'A001','versao':1,'decisao':'confirmacao'}),
                     lambda d:d['verificacao_externa'].update(estado='informada',relato='Uma busca não autorizada.')]
        for mutation in mutations:
            data=copy.deepcopy(original)
            mutation(data)
            with self.assertRaises(ValueError):
                publicar(self.root,'alpha','R001',data)
        self.assertFalse((self.run/'saidas/achados/revisoes/r1').exists())

    def test_correcao_nao_herda_suporte_e_ids_briefing_conferidos(self):
        data = self.fx.dados()
        first = publicar(self.root,'alpha','R001',data)
        old = copy.deepcopy(data)
        data = self.fx.sucessora(data,first,'r2')
        self.fx.revisar(data)
        self.fx.briefing(data)
        data['revisoes_assistidas'].pop()
        with self.assertRaisesRegex(ValueError,'Inclusão exige'):
            validar(self.root,'alpha','R001',data,old)
        data = self.fx.sucessora(old,first,'r2'); self.fx.revisar(data)
        (self.run/'saidas/08_briefing.md').write_text('[A999@v1] frase',encoding='utf-8')
        data['artefatos'].append({'arquivo':'saidas/08_briefing.md','sha256':sha256(self.run/'saidas/08_briefing.md'),'tipo':'briefing'})
        with self.assertRaisesRegex(ValueError,'Referência do briefing'):
            validar(self.root,'alpha','R001',data,old)

    def test_publicacao_inicial_precede_revisao_e_relatorios_sao_obrigatorios(self):
        data=self.fx.dados()
        self.fx.revisar(data)
        with self.assertRaisesRegex(ValueError,'geração inicial'):
            publicar(self.root,'alpha','R001',data)
        data=self.fx.dados()
        data['artefatos'].pop()
        with self.assertRaises(ValueError):
            publicar(self.root,'alpha','R001',data)
        data=self.fx.dados()
        data['achados'].pop()
        with self.assertRaisesRegex(ValueError,'correspondência'):
            publicar(self.root,'alpha','R001',data)

    def test_pdf_ilegivel_nao_publica_localizador_visual(self):
        data=self.fx.dados()
        with patch('pypdf.PdfReader',side_effect=RuntimeError('PDF sintético ilegível')):
            with self.assertRaisesRegex(ValueError,'não validável'):
                publicar(self.root,'alpha','R001',data)

    def test_imutabilidade_sobrescrita_corrida_e_falha_atomica(self):
        data = self.fx.dados()
        with trava(self.run), self.assertRaises(ValueError):
            publicar(self.root,'alpha','R001',data)
        with patch('registros_achados.escrever_json', side_effect=OSError('Falha sintética')):
            with self.assertRaises(OSError):
                publicar(self.root,'alpha','R001',data)
        self.assertFalse((self.run/'saidas/achados/revisoes/r1').exists())
        first=publicar(self.root,'alpha','R001',data)
        path=self.run/'saidas/achados/revisoes/r1/registros.json'
        before=path.read_bytes()
        with self.assertRaises(ValueError):
            publicar(self.root,'alpha','R001',data)
        next_=self.fx.sucessora(data,first,'r2')
        next_['achados'][0]['versoes'][0]['redacao']='Alterada'
        with self.assertRaises(ValueError):
            publicar(self.root,'alpha','R001',next_)
        next_=self.fx.sucessora(data,first,'r2')
        publicar(self.root,'alpha','R001',next_)
        stale=self.fx.sucessora(data,first,'r3')
        with self.assertRaises(ValueError):
            publicar(self.root,'alpha','R001',stale)
        self.assertEqual(before,path.read_bytes())

    def test_retirada_e_retorno_humano_parcial_preservam_historico(self):
        _, revised, _, second=self.fx.completo()
        third=self.fx.sucessora(revised,second,'r3')
        third['revisoes_assistidas'].append({'achado_id':'A001','versao':2,'suporte':'nao_sustentado',
            'motivo':'Reavaliação sintética','fontes_reabertas':['E001'],'limitacoes':'Limitada.','acao':'retirar'})
        with self.assertRaises(ValueError):
            publicar(self.root,'alpha','R001',third)
        third['destinos'].append({'achado_id':'A001','versao':2,'destino':'retirado','motivo':'Suporte reavaliado.',
                                 'briefing':None,'revisao_suporte':None})
        third['conferencias_humanas'].append({'achado_id':'A001','versao':2,'retorno_literal_ou_referencia':'Conferi somente o número 12.',
            'alcance':'Apenas número','decisao':'confirmacao','responsavel':None,'fontes_informadas':[]})
        third['procedencia'].append({'etapa':'retorno_humano','artefatos':[],'ferramentas':['fixture sintética'],'modelo_informado_ou_observado':None})
        self.fx.relatorio(third,'saidas/09_retorno_humano.md','retorno_humano','A001@v2: Conferi somente o número 12.',-1)
        publicar(self.root,'alpha','R001',third)
        self.assertEqual(len(carregar(self.root,'alpha','R001','r3')[0]['achados']),2)

    def test_isolamento_casos_rodadas_e_leitura_direta_sem_indice(self):
        self.fx.caso('beta',indice=False)
        beta=self.fx.dados('beta',indexed=False)
        publicar(self.root,'beta','R001',beta)
        alpha=self.fx.dados()
        with self.assertRaises(ValueError):
            publicar(self.root,'beta','R001',alpha)
        with self.assertRaises(ValueError):
            publicar(self.root,'alpha','R002',alpha)
        self.assertEqual(carregar(self.root,'beta','R001','r1')[0]['caso_id'],'beta')

    def test_conjunto_vazio_revisado_e_contrato_exemplo(self):
        data=self.fx.dados()
        self.fx.vazio_revisado(data)
        publicar(self.root,'alpha','R001',data)
        self.assertEqual(carregar(self.root,'alpha','R001','r2')[0],data)
        from registros_achados import validar_esquema
        validar_esquema(json.loads((Path(__file__).parent/'fixtures/achados_exemplo.json').read_text(encoding='utf-8')))

    def test_schema_carregado_do_pacote_windows(self):
        projeto = Path(__file__).resolve().parents[1]
        pacote = self.root / '_internal'
        schema = pacote / 'modelo_dados' / 'modelos' / 'ACHADOS.schema.json'
        schema.parent.mkdir(parents=True)
        copyfile(projeto / 'modelos' / schema.name, schema)
        amostra = json.loads((projeto / 'testes/fixtures/achados_exemplo.json').read_text(encoding='utf-8'))

        with patch.object(sys, '_MEIPASS', str(pacote), create=True):
            modulo = run_path(str(projeto / 'scripts/registros_achados.py'))
        self.assertEqual(modulo['SCHEMA'], schema)
        modulo['validar_esquema'](amostra)


if __name__=='__main__':
    unittest.main()
