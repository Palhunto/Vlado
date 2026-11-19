"""Versioned documentary continuity, without real documents or model calls."""
import base64
import copy
import http.client
import json
import threading
import unittest
from unittest.mock import patch

import test_codex_integracao as fixture
from agente_fluxo_fixture import completar, entrega, esperar
from cadastrar_documentos import cadastrar
from codex_apuracao import ACTIVE, Conversas
from comum import ler_json, sha256
from interface_pesquisa import Servidor
import continuidade
import revisao_humana


def completar_expansao(manager, identifier, *, tipo='alterada', parar_antes=None):
    refs={}
    for stage in manager.contexts[identifier]['pipeline'].etapas:
        esperar(lambda: manager.contexts[identifier]['meta'].get('etapa')==stage and manager.contexts[identifier]['meta'].get('turn_id'))
        if stage==parar_antes:return
        tool=lambda args:manager.ferramenta(identifier,args)[0]
        if stage=='busca':
            refs['hit']=tool({'acao':'buscar','consulta':'Contrato'})['resultados'][0]
            tool({'acao':'ler','referencia':refs['hit']['referencia']})
            raw='Documento novo consultado e contexto lido.'
        elif stage=='comparacao':
            raw=json.dumps({'comparacoes':[{'anteriores':['A001'],'atuais':['A001'],
                'tipo':tipo,'justificativa':'A resposta documental altera o valor declarado, com atribuição à fonte.'}]})
        else:
            raw=entrega(stage,tool,refs,'Resposta técnica após novos documentos.',valor='246')
        tool({'acao':'guardar','etapa':'sintese' if stage=='comparacao' else stage,'texto':raw})
        turn=manager.contexts[identifier]['meta']['turn_id']
        manager.rpc.emit('turn/completed',{'turn':{'id':turn,'status':'completed'}})
    esperar(lambda:manager.eventos(identifier)['conversa']['estado'] not in
        ('preparando','executando','publicando','aguardando_aprovacao','cancelando'))


class ContinuarDocumentosTest(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.CodexIntegrationTest();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.manager,self.root=self.fx.manager,self.fx.root
        self.chat=self.fx.start();completar(self.manager,self.chat)
        self.first=self.manager.contexts[self.chat]['run']

    def cadastrar_novo(self,name='assessoria.txt',text='Contrato adicional. Valor total 246.'):
        path=self.root/name;path.write_text(text,encoding='utf-8')
        return cadastrar(self.root,'alpha',[path],natureza='sinteticos')

    def previa(self):
        return self.manager.preparar_corpus({'caso':'alpha','conversa':self.chat})

    def test_mesma_conversa_nova_versao_comparativo_e_complemento_posterior(self):
        detail=revisao_humana.detalhe(self.root,'alpha','R001','r3_sintese','g1','A001')
        revisao_humana.salvar(self.root,'alpha','R001','r3_sintese',achado_id='A001',achado_versao=1,
            registros_sha256=detail['registros_sha256'],estado='conferida_no_original')
        before={p:sha256(p) for p in self.first.rglob('*') if p.is_file()}
        config=(self.root/'configuracao.json').read_bytes()
        receipt=self.cadastrar_novo();preview=self.previa()
        self.assertEqual(receipt['corpus_id'],'alpha_v2');self.assertEqual(preview['documentos_novos'][0]['id'],'D002')
        self.assertEqual(self.manager.contexts[self.chat]['meta']['rodadas'],['R001'])
        self.fx.start(conversa=self.chat,atualizar_corpus=preview['solicitacao'])
        completar_expansao(self.manager,self.chat)
        ctx=self.manager.contexts[self.chat]
        self.assertEqual(ctx['meta']['estado'],'concluido')
        self.assertEqual(ctx['meta']['rodadas'],['R001','R002'])
        self.assertEqual(ctx['meta']['corpus_id'],'alpha_v2')
        report=ler_json(ctx['run']/'saidas/codex_execucao.json')
        self.assertEqual(report['etapas_sem_registro'],[])
        self.assertEqual(len(report['etapas_validadas']),7)
        comparison=ler_json(ctx['run']/report['comparativo']['arquivo'])
        self.assertEqual(comparison['comparacoes'][0]['tipo'],'alterada')
        self.assertEqual(comparison['evidencias_novas'][0]['documento_id'],'D002')
        self.assertEqual(comparison['nova_conferencia'][0]['id'],'A001')
        self.assertEqual(comparison['corpus_anterior'],'alpha_v1')
        self.assertEqual(comparison['corpus_atual'],'alpha_v2')
        current=revisao_humana.detalhe(self.root,'alpha','R002','r3_sintese','g1','A001')
        self.assertEqual(current['achado']['revisao_humana']['estado'],'pendente')
        self.assertTrue(all(sha256(p)==digest for p,digest in before.items()))
        self.assertEqual(config,(self.root/'configuracao.json').read_bytes())
        # Resume from disk: ordinary follow-ups retain the expanded frozen corpus.
        self.manager.close()
        other=Conversas(self.root,fixture.FakeServer);self.addCleanup(other.close)
        response=other.perguntar({'caso':'alpha','conversa':self.chat,'pergunta':'Complemento técnico.'})
        esperar(lambda:other.contexts[response['conversa']]['meta'].get('turn_id'))
        completar(other,self.chat)
        self.assertEqual([d['id'] for d in other.contexts[self.chat]['manifest']['documentos']],['D001','D002'])
        self.assertEqual(other.contexts[self.chat]['meta']['corpus_id'],'alpha_v2')

    def test_duplicatas_nao_criam_versao_e_previa_desatualizada_nao_cria_rodada(self):
        cadastrar(self.root,'alpha',[self.root/'alpha.txt'])
        with self.assertRaisesRegex(ValueError,'Não há documentos novos'):self.previa()
        self.cadastrar_novo();preview=self.previa()
        self.cadastrar_novo('outro.txt','Outra peça documental sintética.')
        with self.assertRaisesRegex(ValueError,'mudou desde a prévia'):
            self.manager.perguntar({'caso':'alpha','conversa':self.chat,'pergunta':'Continuar.',
                'atualizar_corpus':preview['solicitacao']})
        self.assertFalse((self.root/'execucoes/alpha/R002').exists())
        with self.assertRaisesRegex(ValueError,'outro caso'):
            self.manager.preparar_corpus({'caso':'beta','conversa':self.chat})

    def test_mudanca_antes_de_congelar_nao_altera_checkpoint_da_rodada_antiga(self):
        self.cadastrar_novo();preview=self.previa()
        state=self.first/'saidas/codex_fluxo_estado.json';before=sha256(state)
        freeze=self.manager._freeze
        def racing(identifier,question):
            self.cadastrar_novo('tardio.txt','Documento que chegou depois da prévia.')
            return freeze(identifier,question)
        with patch.object(self.manager,'_freeze',side_effect=racing):
            self.manager.perguntar({'caso':'alpha','conversa':self.chat,'pergunta':'Continuar.',
                'atualizar_corpus':preview['solicitacao']})
            esperar(lambda:not self.manager.contexts[self.chat]['busy'])
        self.assertEqual(self.manager.contexts[self.chat]['meta']['estado'],'erro')
        self.assertEqual(sha256(state),before)
        self.assertFalse((self.root/'execucoes/alpha/R002').exists())

    def test_comparativo_recusa_vinculos_incompletos_ou_pendencia_falsamente_respondida(self):
        self.cadastrar_novo();preview=self.previa()
        self.fx.start(conversa=self.chat,atualizar_corpus=preview['solicitacao'])
        completar_expansao(self.manager,self.chat)
        pipeline=self.manager.contexts[self.chat]['pipeline']
        entry={'anteriores':['A001'],'atuais':['A001'],'tipo':'alterada','justificativa':'Reexame sintético.'}
        invalid=[{'comparacoes':[]},{'comparacoes':[entry,entry]},
            {'comparacoes':[{**entry,'atuais':['A999']}]},
            {'comparacoes':[{**entry,'tipo':'pendencia_respondida'}]},
            {'comparacoes':[{**entry,'tipo':'nova'}]},
            {'comparacoes':[{**entry,'justificativa':''}]}]
        for payload in invalid:
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                continuidade.comparar(pipeline.continuidade,pipeline.data,pipeline.references,pipeline.evidence_refs,payload)
        pending=copy.deepcopy(pipeline.continuidade)
        pending['achados_anteriores'][0].update(natureza='pendencia',destino='pendencia')
        result=continuidade.comparar(pending,pipeline.data,pipeline.references,pipeline.evidence_refs,
            {'comparacoes':[{**entry,'tipo':'pendencia_respondida'}]})
        self.assertEqual(result['comparacoes'][0]['tipo'],'pendencia_respondida')

    def test_cadastro_http_confere_recibo_sem_perguntar_e_protege_o_destino(self):
        server=Servidor(('127.0.0.1',0),self.root);server.conversas=self.manager
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join(3)))
        def post(op,data,headers=None):
            con=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            h={'Content-Type':'application/json','Origin':server.origin,'X-Session-Token':server.token};h.update(headers or {})
            con.request('POST','/api/'+op,json.dumps(data),h)
            response=con.getresponse();status=response.status;body=json.loads(response.read());con.close();return status,body
        data={'caso':'alpha','conversa':self.chat,'natureza':'sinteticos','arquivos':[
            {'nome':'assessoria.txt','base64':base64.b64encode(b'Contrato adicional. Valor total 246.\n'+b'x'*40000).decode()}]*2}
        scope={'caso':'alpha','conversa':self.chat}
        for op in ('codex-documentos-cadastrar','codex-corpus-previa'):
            body=data if op=='codex-documentos-cadastrar' else scope
            self.assertEqual(post(op,body,{'X-Session-Token':'errado'})[0],403)
            self.assertEqual(post(op,body,{'Origin':'https://fora.test'})[0],403)
        self.assertEqual(post('codex-documentos-cadastrar',{**data,'caso':'beta'})[0],400)
        status,receipt=post('codex-documentos-cadastrar',data)
        self.assertEqual(status,200);self.assertEqual((receipt['recebidos'],receipt['novos'],receipt['duplicados']),(2,1,1))
        self.assertEqual(len(receipt['arquivos']),2)
        self.assertFalse((self.root/'execucoes/alpha/R002').exists())
        status,preview=post('codex-corpus-previa',scope)
        self.assertEqual(status,200);self.assertEqual(preview['corpus_novo'],'alpha_v2')
        self.assertEqual(post('codex-documentos-cadastrar',{**data,'arquivos':[{'nome':'negado.exe','base64':'eA=='}]})[0],400)

    def test_comparacao_ausente_impede_conclusao_e_preserva_publicacoes_parciais(self):
        self.cadastrar_novo();preview=self.previa()
        self.fx.start(conversa=self.chat,atualizar_corpus=preview['solicitacao'])
        completar_expansao(self.manager,self.chat,parar_antes='comparacao')
        ctx=self.manager.contexts[self.chat]
        for attempt in (1,2):
            esperar(lambda:ctx['meta'].get('etapa')=='comparacao' and ctx['meta'].get('tentativa_etapa')==attempt and ctx['meta'].get('turn_id'))
            self.manager.rpc.emit('turn/completed',{'turn':{'id':ctx['meta']['turn_id'],'status':'completed'}})
        # _finish clears busy before writing codex_execucao.json, all under the manager lock;
        # eventos() takes that lock, so the final state is only seen once the report exists.
        esperar(lambda:self.manager.eventos(self.chat)['conversa']['estado'] not in ACTIVE)
        self.assertEqual(ctx['meta']['estado'],'incompleto')
        report=ler_json(ctx['run']/'saidas/codex_execucao.json')
        self.assertEqual(report['etapas_sem_registro'],['comparacao'])
        self.assertIsNone(report['comparativo'])
        self.assertIsNone(report['publicacao_achados'])
        self.assertTrue((ctx['run']/'saidas/achados/revisoes/r3_sintese/registros.json').is_file())

    def test_pendencia_respondida_vincula_ultima_rodada_concluida_a_suporte_novo(self):
        self.fx.start(conversa=self.chat,pergunta='Pendência técnica sintética.')
        refs={}
        for stage in ('inventario','plano','busca','geracao_inicial','revisao','sintese'):
            ctx=self.manager.contexts[self.chat]
            esperar(lambda:ctx['meta'].get('etapa')==stage and ctx['meta'].get('turn_id'))
            tool=lambda args:self.manager.ferramenta(self.chat,args)[0]
            if stage=='geracao_inicial':raw=json.dumps({'texto':'Insuficiência documental sintética.','achados':[{
                'subquestao':'O contrato foi localizado?','redacao':'Falta o contrato complementar.',
                'natureza':'pendencia','limitacoes':'Teste sintético.','evidencias':[]}]})
            elif stage=='revisao':raw=json.dumps({'texto':'Pendência permanece.','revisoes':[{
                'achado_id':'A001','suporte':'nao_sustentado','motivo':'Sem fonte.','limitacoes':'Teste.', 'acao':'pendencia'}]})
            elif stage=='sintese':raw=json.dumps({'texto':'Insuficiência de suporte nesta rodada.','destinos':[{
                'achado_id':'A001','destino':'pendencia','motivo':'Documento não localizado.'}]})
            else:raw=entrega(stage,tool,refs)
            tool({'acao':'guardar','etapa':stage,'texto':raw})
            self.manager.rpc.emit('turn/completed',{'turn':{'id':ctx['meta']['turn_id'],'status':'completed'}})
        esperar(lambda:not ctx['busy'])
        self.cadastrar_novo();preview=self.previa()
        self.assertEqual(preview['rodada_anterior'],'R002')
        self.fx.start(conversa=self.chat,atualizar_corpus=preview['solicitacao'])
        completar_expansao(self.manager,self.chat,tipo='pendencia_respondida')
        ctx=self.manager.contexts[self.chat]
        self.assertEqual(ctx['meta']['estado'],'concluido')
        self.assertEqual(ctx['pipeline'].comparativo['comparacoes'][0]['tipo'],'pendencia_respondida')
        self.assertEqual(ctx['pipeline'].comparativo['rodada_anterior'],'R002')
