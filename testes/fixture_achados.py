"""Synthetic setup shared by storage, index and HTTP acceptance tests."""
import copy
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import PARTES, escrever_json, fluxo_esperado, manifesto_prompts, sha256
from criar_caso import criar_caso
from selecionar_caso import selecionar
from nova_rodada import criar_rodada
from indice_sqlite import pesquisar
from registros_achados import publicar
from indice_achados import construir
from modelo_pasta import copiar


class Ambiente:
    @classmethod
    def copia_completa(cls, quantidade=2):
        """Ambiente equivalente a `Ambiente()` seguido de `completo(quantidade)`, em pasta temporária própria.

        O modelo é construído pelo caminho normal uma vez por processo e por `quantidade` e depois copiado
        (`modelo_pasta.copiar`); os registros guardam só caminhos relativos à raiz. Devolve
        `(ambiente, resultado)`, em que `resultado` é uma cópia profunda do que `completo` devolveu.
        """
        temp, root, resultado = copiar(('Ambiente.completo', quantidade), lambda raiz: cls(raiz).completo(quantidade))
        env = cls.__new__(cls)
        env.temp, env.root = temp, root
        env.text, env.pdf, env.tab = root / 'texto.txt', root / 'visual.pdf', root / 'tabela.csv'
        return env, resultado

    def __init__(self, root=None):
        self.temp = tempfile.TemporaryDirectory() if root is None else None
        self.root = Path(self.temp.name) if self.temp else Path(root)
        self.root.mkdir(exist_ok=True, parents=True)
        (self.root / 'prompts').mkdir()
        for name in PARTES:
            (self.root / 'prompts' / name).write_text('# Fixture sintética\n', encoding='utf-8')
        (self.root / 'prompts/FLUXO_COMPLETO.md').write_bytes(fluxo_esperado(self.root))
        escrever_json(self.root / 'prompts/manifesto_prompts.json', manifesto_prompts(self.root))
        (self.root / 'AGENTS.md').write_text('Fixture técnica.', encoding='utf-8')
        escrever_json(self.root / 'configuracao.json', {'caso_ativo': None, 'manifesto_ativo': None,
            'maximo_documentos_inicial': 20, 'indice_sqlite': True, 'web_na_apuracao': False})
        self.text = self.root / 'texto.txt'
        self.text.write_text('A fonte declara valor 12.\nOutra versão declara valor 14.\n<script>window.INJETADO=1</script>\n', encoding='utf-8')
        from pypdf import PdfWriter
        self.pdf = self.root / 'visual.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        writer.write(self.pdf)
        self.tab = self.root / 'tabela.csv'
        self.tab.write_text('nome,valor\nExemplo,12\n', encoding='utf-8')
        self.caso('alpha')

    def cleanup(self):
        if self.temp:
            self.temp.cleanup()

    def caso(self, case, *, indice=True):
        criar_caso(self.root, case, 'Caso sintético ' + case, [self.text, self.pdf, self.tab], 'sinteticos')
        selecionar(self.root, case)
        run = criar_rodada(self.root, 'R001', 'Teste técnico sintético, sem pergunta editorial.', indice=indice)
        selecionar(self.root, None)
        return run

    def run(self, case='alpha'):
        return self.root / f'execucoes/{case}/R001'

    def dados(self, case='alpha', indexed=True):
        run = self.run(case)
        frozen = __import__('json').loads((run / f'entradas/casos/{case}/manifesto.json').read_text(encoding='utf-8'))
        docs = frozen['documentos']
        original = 'entradas/' + docs[0]['arquivo']
        hit = pesquisar(self.root, case, 'R001', 'valor')['resultados'][0] if indexed else None
        index = None
        if indexed:
            from indice_sqlite import cobertura
            identity = cobertura(self.root, case, 'R001')
            index = {k: identity[k] for k in ('indice_id', 'banco_sha256')}
            index.update(geracao='v1', referencia=hit['referencia'])
        e1 = {'id':'E001', 'documento_id':'D001', 'modo':'indexada' if indexed else 'direta',
              'original':original, 'original_sha256':docs[0]['sha256'], 'fonte_textual':original,
              'fonte_sha256':docs[0]['sha256'], 'indice': index if indexed else None,
              'localizador':{'tipo':'linhas','pagina_pdf':None,'linha_inicio':1,'linha_fim':1,'descricao':''},
              'trecho':'A fonte declara valor 12.', 'atribuicao':'Fonte sintética', 'contexto':'Declaração em teste.',
              'limitacoes':'Não comprova pagamento.'}
        e2 = copy.deepcopy(e1)
        e2.update(id='E002', trecho='Outra versão declara valor 14.')
        e2['localizador'].update(linha_inicio=2, linha_fim=2)
        e3 = {'id':'E003','documento_id':'D002','modo':'visual','original':'entradas/'+docs[1]['arquivo'],
              'original_sha256':docs[1]['sha256'],'fonte_textual':None,'fonte_sha256':None,'indice':None,
              'localizador':{'tipo':'pagina','pagina_pdf':1,'linha_inicio':None,'linha_fim':None,'descricao':'Página sintética vazia'},
              'trecho':'','atribuicao':'PDF sintético','contexto':'Página visual sem FTS.', 'limitacoes':'Página vazia.'}
        data = {'esquema':1,'caso_id':case,'rodada':'R001','snapshot_sha256':sha256(run/'snapshot.json'),
                'revisao':'r1','anterior':None,
                'achados':[{'id':'A001','subquestao':'Valores declarados?', 'versoes':[
                    {'versao':1,'redacao':'A fonte declara valor 12. <script>window.INJETADO=1</script>',
                     'natureza':'alegacao_atribuida','limitacoes':'Redação inicial sujeita à revisão.'}]},
                    {'id':'A002','subquestao':'O valor foi pago?', 'versoes':[
                    {'versao':1,'redacao':'Não foi estabelecido pagamento.','natureza':'pendencia','limitacoes':'Sem suporte.'}]}],
                'evidencias':[e1,e2,e3],
                'vinculos':[{'achado_id':'A001','versao':1,'evidencia_id':eid,'papel':role,'justificativa':'Relação sintética atribuída.'}
                            for eid,role in [('E001','suporte'),('E002','contradicao'),('E003','contexto')]],
                'revisoes_assistidas':[], 'destinos':[], 'conferencias_humanas':[],
                'verificacao_externa':{'estado':'nao_realizada','relato':None,'limitacao':'Corpus fechado; sem verificação externa.'},
                'procedencia':[{'etapa':'busca','artefatos':[],'ferramentas':['fixture sintética'], 'modelo_informado_ou_observado':None}],
                'artefatos':[]}
        self.relatorio(data,'saidas/04_evidencias_brutas.md','evidencias','E001 E002 E003 · fontes sintéticas.',0)
        self.relatorio(data,'saidas/05_cruzamentos_brutos.md','cruzamentos','A001@v1 A002@v1 · redações sintéticas.',0)
        return data

    def relatorio(self,data,name,kind,content,event):
        path=self.run(data['caso_id'])/name
        if not path.exists():
            path.write_text(content,encoding='utf-8')
        data['artefatos'].append({'arquivo':name,'sha256':sha256(path),'tipo':kind})
        data['procedencia'][event]['artefatos'].append(name)

    def vazio_revisado(self,data):
        for field in ('achados','evidencias','vinculos'):
            data[field]=[]
        self.sincronizar_brutos(data)
        first=publicar(self.root,data['caso_id'],'R001',data)
        next_=self.sucessora(data,first,'r2')
        data.clear(); data.update(next_)
        data['procedencia'].append({'etapa':'revisao','artefatos':[],'ferramentas':['fixture sintética'],'modelo_informado_ou_observado':None})
        self.relatorio(data,'saidas/06_insuficiencia.md','insuficiencia','Sem achados com suporte.',-1)

    def sincronizar_brutos(self,data):
        for kind,field in [('evidencias','evidencias'),('cruzamentos','achados')]:
            artifact=next(a for a in data['artefatos'] if a['tipo']==kind)
            path=self.run(data['caso_id'])/artifact['arquivo']
            path.write_text(' '.join(x['id'] for x in data[field]) or 'Nenhum registro sintético.',encoding='utf-8')
            artifact['sha256']=sha256(path)

    def sucessora(self, data, receipt, revision):
        result = copy.deepcopy(data)
        result.update(revisao=revision, anterior={'revisao':data['revisao'], 'registros_sha256':receipt['manifesto']['registros_sha256']})
        return result

    def revisar(self, data):
        data['achados'][0]['versoes'].append({'versao':2,'redacao':'A fonte declara valor 12.',
            'natureza':'alegacao_atribuida','limitacoes':'Declaração documental, sem verificação externa.'})
        data['vinculos'].extend([{**v,'versao':2} for v in data['vinculos'] if v['achado_id']=='A001' and v['versao']==1])
        data['revisoes_assistidas'].append({'achado_id':'A001','versao':1,'suporte':'parcial','motivo':'Remover código estranho da redação.',
            'fontes_reabertas':['E001','E002','E003'],'limitacoes':'Revisão pela IA.','acao':'corrigir'})
        data['revisoes_assistidas'].append({'achado_id':'A001','versao':2,'suporte':'sustentado','motivo':'Atribuição delimitada.',
            'fontes_reabertas':['E001','E002','E003'],'limitacoes':'Revisão pela IA.','acao':'manter'})
        data['procedencia'].append({'etapa':'revisao','artefatos':[],'ferramentas':['fixture sintética'],'modelo_informado_ou_observado':None})
        self.relatorio(data,'saidas/06_revisao_assistida.md','revisao','A001@v1 parcial; A001@v2 sustentado; A002 pendente.',-1)
        self.relatorio(data,'saidas/07_achados_revisados.md','achados_revisados','A001@v2 A002@v1 · síntese sintética.',-1)

    def briefing(self, data, name='saidas/08_briefing.md'):
        run = self.run(data['caso_id'])
        (run / name).write_text('[A001@v2] A fonte declara valor 12. E001, D001, linha 1.\n', encoding='utf-8')
        data['artefatos'].append({'arquivo':name,'sha256':sha256(run/name),'tipo':'briefing'})
        data['destinos'].append({'achado_id':'A001','versao':2,'destino':'incluido','motivo':'Alegação atribuída sustentada.',
                                  'briefing':name,'revisao_suporte':2})
        data['procedencia'].append({'etapa':'sintese','artefatos':[name], 'ferramentas':['fixture sintética'], 'modelo_informado_ou_observado':None})

    def completo(self, quantidade=2):
        initial = self.dados()
        for number in range(3,quantidade+1):
            initial['achados'].append({'id':f'A{number:03}','subquestao':'Pendência sintética de paginação.',
                'versoes':[{'versao':1,'redacao':f'Pendência sintética {number}.','natureza':'pendencia','limitacoes':'Sem evidência.'}]})
        if quantidade>2:
            self.sincronizar_brutos(initial)
        first = publicar(self.root,'alpha','R001',initial)
        revised = self.sucessora(initial,first,'r2')
        self.revisar(revised)
        self.briefing(revised)
        second = publicar(self.root,'alpha','R001',revised)
        construir(self.root,'alpha','R001','r1','g1')
        construir(self.root,'alpha','R001','r2','g2')
        return initial, revised, first, second
