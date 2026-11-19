"""Authenticated loopback endpoints, findings isolated from documentary search."""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from fixture_achados import Ambiente
from interface_pesquisa import Servidor


class InterfaceAchadosTest(unittest.TestCase):
    def setUp(self):
        self.fx, _ = Ambiente.copia_completa(); self.addCleanup(self.fx.cleanup)
        self.server=Servidor(('127.0.0.1',0),self.fx.root)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start(); self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def request(self,op,body=None,headers=None,binary=False):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        h={'Content-Type':'application/json','X-Session-Token':self.server.token,'Origin':self.server.origin}
        h.update(headers or {})
        con.request('POST','/api/'+op,json.dumps(body or self.scope()),h)
        r=con.getresponse(); content=r.read(); status=r.status; con.close()
        return status,content if binary else json.loads(content)

    def scope(self,**kwargs):
        return {'caso':'alpha','rodada':'R001','revisao':'r2','geracao_achados':'g2',**kwargs}

    def test_catalogo_busca_detalhe_exportacao_e_original_visual(self):
        self.assertEqual(self.request('achados-catalogo')[1]['revisoes'],['r1','r2'])
        status,result=self.request('achados-buscar',self.scope(limite=1))
        self.assertEqual(status,200); self.assertEqual(result['total_correspondencias'],2)
        self.assertEqual(result['retornados'],1)
        full=self.request('achados-exportar',self.scope(limite=1,deslocamento=1))[1]
        self.assertTrue(full['completa']); self.assertEqual(full['retornados'],2)
        self.assertEqual(self.request('achados-detalhe',self.scope(achado_id='A001'))[1]['achado']['versao'],2)
        digest=next(a['sha256'] for a in full['artefatos'] if a['tipo']=='briefing')
        status,briefing=self.request('achados-briefing',self.scope(artefato_sha256=digest))
        self.assertEqual(status,200); self.assertIn('[A001@v2]',briefing['texto'])
        self.assertEqual(self.request('achados-briefing',self.scope(artefato_sha256='0'*64))[0],400)
        ctx=self.request('achados-evidencia',self.scope(evidencia_id='E003'))[1]
        self.assertIsNone(ctx['contexto'])
        status,content=self.request('achados-original',self.scope(evidencia_id='E003'),binary=True)
        self.assertEqual(status,200)
        self.assertEqual(content,(self.fx.run()/ctx['evidencia']['original']).read_bytes())
        self.assertEqual(self.request('achados-buscar',self.scope(revisao='r1',geracao_achados='g1'))[1]['revisoes_sucessoras'],['r2'])

    def test_origem_sessao_caminhos_injecao_e_erro_distinto_de_vazio(self):
        for op in ('achados-buscar','achados-exportar','achados-original','achados-evidencia','achados-catalogo','achados-detalhe','achados-briefing','achados-revisao-salvar','codex-observacoes'):
            for headers in ({'X-Session-Token':'errado'},{'Origin':'https://fora.test'},{'Host':'fora.test'}):
                self.assertEqual(self.request(op,headers=headers)[0],403)
        for body in (self.scope(caso='../beta'),self.scope(revisao='../r1'),self.scope(geracao_achados='../indice'),
                     self.scope(filtros={'documento':{}}),self.scope(limite=True)):
            self.assertEqual(self.request('achados-buscar',body)[0],400)
        self.assertEqual(self.request('achados-original',self.scope(evidencia_id='../../AGENTS.md'))[0],400)
        self.assertEqual(self.request('achados-original',self.scope(evidencia_id='E999',arquivo='AGENTS.md'))[0],400)
        status,result=self.request('achados-buscar',self.scope(filtros={'texto':'nada correspondente'}))
        self.assertEqual(status,200); self.assertEqual(result['total_correspondencias'],0)
        status,result=self.request('achados-buscar',self.scope(geracao_achados='ausente'))
        self.assertEqual(status,400); self.assertEqual(result['estado'],'erro')

    def test_previa_de_observacoes_preserva_texto_e_nao_inicia_modelo(self):
        detail=self.request('achados-detalhe',self.scope(achado_id='A001'))[1]
        status,saved=self.request('achados-revisao-salvar',self.scope(achado_id='A001',achado_versao=2,
            registros_sha256=detail['registros_sha256'],estado='precisa_de_ajuste',
            observacao='É o valor total do contrato.'))
        self.assertEqual(status,200)
        request=self.scope(selecoes=[{'achado_id':'A001','achado_versao':2,
            'registros_sha256':detail['registros_sha256'],'evento_id':saved['revisao_humana']['evento_id']}])
        status,preview=self.request('codex-observacoes',request)
        self.assertEqual(status,200)
        self.assertIsNone(preview['conversa'])
        self.assertEqual(preview['conteudo']['observacoes'][0]['observacao'],'É o valor total do contrato.')
        self.assertEqual(preview['conteudo']['observacoes'][0]['redacao_anterior'],detail['achado']['redacao'])
        self.assertIsNone(self.server.conversas.rpc)

    def test_conferida_no_original_exige_abrir_cada_original_citado_nesta_sessao(self):
        detail=self.request('achados-detalhe',self.scope(achado_id='A001'))[1]
        payload=self.scope(achado_id='A001',achado_versao=detail['achado']['versao'],
            registros_sha256=detail['registros_sha256'],estado='conferida_no_original',observacao='',anterior=None)
        status,erro=self.request('achados-revisao-salvar',payload)
        self.assertEqual((status,erro['codigo']),(400,'conferencia_sem_original'))
        faltam=erro['faltam']
        self.assertTrue(faltam)
        self.assertIn('abra', erro['erro'])
        # Opening it under another revision does not count for this one.
        self.request('achados-original',self.scope(revisao='r1',geracao_achados='g1',evidencia_id=faltam[0]),binary=True)
        self.assertEqual(self.request('achados-revisao-salvar',payload)[1]['faltam'],faltam)
        for evidence in faltam[:-1]:
            self.assertEqual(self.request('achados-original',self.scope(evidencia_id=evidence),binary=True)[0],200)
        self.assertEqual(self.request('achados-revisao-salvar',payload)[1]['faltam'],faltam[-1:])
        self.request('achados-original',self.scope(evidencia_id=faltam[-1]),binary=True)
        status,saved=self.request('achados-revisao-salvar',payload)
        self.assertEqual(status,200,saved)
        self.assertEqual(saved['revisao_humana']['estado'],'conferida_no_original')

    def test_vditor_tem_cache_longo_e_demais_estaticos_revalidam(self):
        def get(path):
            con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
            con.request('GET',path); r=con.getresponse(); r.read(); con.close()
            return r.status,r.getheader('Cache-Control')
        self.assertEqual(get('/vendor/vditor/dist/index.css?v=3.11.1'),(200,'public, max-age=31536000, immutable'))
        self.assertEqual(get('/vendor/vditor/dist/index.css'),(200,'no-cache'))  # unversioned URL keeps revalidating
        self.assertEqual(get('/style.css?v=1'),(200,'no-cache'))

    def test_conferencia_humana_por_http_e_exportacao_protegidas(self):
        detail = self.request('achados-detalhe',self.scope(achado_id='A001'))[1]
        payload = self.scope(achado_id='A001', achado_versao=detail['achado']['versao'],
            registros_sha256=detail['registros_sha256'], estado='precisa_de_ajuste', observacao='Falta contexto.', anterior=None)
        status,result = self.request('achados-revisao-salvar',payload)
        self.assertEqual(status,200)
        self.assertEqual(result['revisao_humana']['observacao'],'Falta contexto.')
        exported = self.request('achados-exportar',self.scope(filtros={'revisao_humana':'precisa_de_ajuste'}))[1]
        self.assertEqual(exported['retornados'],1)
        self.assertEqual(exported['resultados'][0]['revisao_humana']['estado'],'precisa_de_ajuste')
        self.assertEqual(exported['progresso_revisao_humana']['revisados'],1)
        self.request('excluir',{'tipo':'caso','caso':'alpha'})
        self.assertEqual(self.request('achados-revisao-salvar',payload)[0],400)


if __name__=='__main__':
    unittest.main()
