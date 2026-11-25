"""Caminho inteiro da Mesa ao quadro, pelo HTTP de um servidor real e com o provedor simulado.

Sem rede, sem modelo e sem chave. Uma pergunta enviada pela Mesa (`codex-perguntar`) percorre as seis etapas
com o agente sintético, que publica as revisões com os nomes REAIS do fluxo (`r1_busca`, `r2_revisao`,
`r3_sintese`; scripts/fluxo_codex.py). Depois, só pelas rotas da Mesa, uma evidência publicada é ligada a um
nó do mapa de relações, a um acontecimento da linha do tempo, a uma hipótese e a uma célula de tabela, e o
original é aberto pelo localizador (documento e página do PDF). Uma segunda Mesa, com outra rodada, termina
na revisão `r3_briefing` (o nome que o prompt 05 e docs/ACHADOS_IA.md usam no modo agente de chat), para provar
que os quadros resolvem qualquer variante publicada. As duas não cabem na mesma rodada: `publicar` recusa uma
segunda sucessora da mesma revisão.

Este teste não conserta nada: o que não resolver aqui é defeito do código de produção.
"""
import copy
import hashlib
import http.client
import io
import json
from pathlib import Path
import sys
import threading
import unittest
import uuid

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados_sinteticos
import indice_achados
from agente_fluxo_fixture import aguardar_fim, encerrar_gerenciador, esperar
from codex_apuracao import ACTIVE, Conversas
from comum import sha256
from criar_caso import criar_caso
from interface_pesquisa import Servidor
from modelo_pasta import copiar
from registros_achados import carregar, publicar
import test_codex_integracao as integracao  # módulo, para não recoletar os TestCases dele

ETAPAS = ('inventario', 'plano', 'busca', 'geracao_inicial', 'revisao', 'sintese')
REVISOES_REAIS = ('r1_busca', 'r2_revisao', 'r3_sintese')
PERGUNTA = 'Qual o valor global do contrato 041/2025, quando foi assinado e quem é a contratada?'
VALOR = 'Valor global: R$ 8.750.000,00 (oito milhoes, setecentos e cinquenta mil reais).'
ASSINATURA = 'Data de assinatura: 3 de marco de 2025.'
CONTRATADA = 'Contratada: Construtora Horizonte Azul Ltda. (ficticia), CNPJ 00.000.000/0001-00.'
CASO = 'vila'


def montar(root):
    """Um caso com o contrato sintético em PDF de texto nativo (D001, uma página)."""
    integracao.CodexIntegrationTest.montar(root)
    lotes = dados_sinteticos.gerar(root / 'corpus_sintetico')
    criar_caso(root, CASO, 'Contrato sintético', [lotes['lote1'][0]], 'sinteticos')


def agente(manager, identificador, ao_entregar=None, ate='sintese'):
    """O agente sintético: cumpre as seis etapas pelas ferramentas da própria Mesa, com os nomes reais.

    A geração inicial entrega uma afirmação com três evidências de linhas diferentes da mesma página do PDF;
    quem lê o resultado são os quadros, mais adiante."""
    tool = lambda args: manager.ferramenta(identificador, args)[0]
    refs = {}
    for etapa in ETAPAS[:ETAPAS.index(ate) + 1]:
        meta = lambda: manager.contexts[identificador]['meta']  # relido: o gerenciador troca o dicionário
        esperar(lambda: (meta().get('etapa') == etapa and meta().get('turn_id')) or meta()['estado'] not in ACTIVE,
                mensagem=f'A etapa {etapa} não começou: {meta().get("estado")} / {meta().get("etapa")} / '
                         f'{meta().get("situacao")}')
        assert meta().get('etapa') == etapa, (etapa, meta().get('estado'), meta().get('situacao'))
        if etapa == 'inventario':
            tool({'acao': 'cobertura'})
            bruto = 'Inventário sintético: um PDF de texto nativo; sem validação humana.'
        elif etapa == 'plano':
            bruto = 'Plano sintético: localizar valor, data de assinatura e contratada.'
        elif etapa == 'busca':
            achado = tool({'acao': 'buscar', 'consulta': 'Valor global'})['resultados'][0]
            tool({'acao': 'ler', 'referencia': achado['referencia']})
            refs['achado'] = achado
            bruto = 'Busca sintética: Valor global; passagem lida e fonte atribuída.'
        else:
            achado = refs['achado']
            linhas = achado['trecho'].splitlines()

            def evidencia(texto, papel='suporte'):
                numero = achado['linha_inicio'] + linhas.index(texto)
                return {'referencia': achado['referencia'], 'trecho': texto, 'linha_inicio': numero,
                        'linha_fim': numero, 'papel': papel, 'justificativa': 'A linha traz o dado literal.',
                        'atribuicao': 'Contrato 041/2025 (sintético)', 'contexto': 'Página 1 do contrato.',
                        'limitacoes': 'Documento fictício de teste.'}
            if etapa == 'geracao_inicial':
                bruto = json.dumps({'texto': 'Geração inicial sintética preservada.', 'achados': [{
                    'subquestao': 'O que o contrato declara?',
                    'redacao': 'O contrato 041/2025 declara valor global de R$ 8.750.000,00, assinatura em 3 de '
                               'março de 2025 e a Construtora Horizonte Azul como contratada.',
                    'natureza': 'declaracao_documental', 'limitacoes': 'Só o contrato; sem pagamentos.',
                    'evidencias': [evidencia(VALOR), evidencia(ASSINATURA), evidencia(CONTRATADA)]}]},
                    ensure_ascii=False)
            elif etapa == 'revisao':
                tool({'acao': 'ler', 'referencia': achado['referencia']})
                bruto = json.dumps({'texto': 'Revisão sintética pela mesma IA; sem aprovação humana.', 'revisoes': [{
                    'achado_id': 'A001', 'suporte': 'sustentado', 'acao': 'manter',
                    'motivo': 'As três linhas conferem com a página reaberta.',
                    'limitacoes': 'Teste técnico sintético.'}]}, ensure_ascii=False)
            else:
                bruto = json.dumps({'texto': 'Briefing sintético.\n[A001@v1] O contrato declara valor global '
                                    'de R$ 8.750.000,00. [fonte:' + achado['referencia'] + ']',
                                    'destinos': [{'achado_id': 'A001', 'destino': 'incluido',
                                                  'motivo': 'Declaração documental revisada.'}]},
                                   ensure_ascii=False)
        tool({'acao': 'guardar', 'etapa': etapa, 'texto': bruto})
        turno = manager.contexts[identificador]['meta']['turn_id']
        manager.rpc.emit('item/completed', {'item': {'id': 'msg-' + turno, 'type': 'agentMessage',
                         'phase': 'final_answer', 'text': 'Etapa sintética entregue.'}})
        manager.rpc.emit('turn/completed', {'turn': {'id': turno, 'status': 'completed'}})
        if ao_entregar:
            ao_entregar(etapa)
    if ate != 'sintese':
        return None  # o chamador encerra a conversa: o resto é do agente de chat
    return aguardar_fim(manager, identificador)


class Mesa:
    """Servidor real da Mesa (porta local, sessão e CSRF de verdade) com o provedor simulado.

    Uma conversa por gerenciador: o provedor simulado usa um só `threadId`. Por isso cada variante de revisão
    final tem a sua classe, e cada classe a sua Mesa e a sua rodada."""
    ate = 'sintese'

    @classmethod
    def setUpClass(cls):
        cls.temp, cls.root, _ = copiar('MesaAoQuadroTest', montar)
        cls.gerenciador = Conversas(cls.root, integracao.FakeServer)
        cls.servidor = Servidor(('127.0.0.1', 0), cls.root)
        cls.servidor.conversas = cls.gerenciador
        cls.thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.thread.start()
        cls.mesa = cls.percorrer_a_mesa(CASO)
        cls.rodada = cls.mesa['eventos']['conversa']['rodadas'][-1]
        cls.completar()

    @classmethod
    def completar(cls):
        """Nada, na Mesa inteira; a variante de chat publica a revisão final por conta própria."""

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.thread.join(3)
        encerrar_gerenciador(cls.gerenciador)
        cls.temp.cleanup()

    # --- HTTP, como o navegador da Mesa -------------------------------------------------------------------
    @classmethod
    def chamar(cls, operacao, dados, corpo_bruto=False):
        con = http.client.HTTPConnection('127.0.0.1', cls.servidor.server_port, timeout=60)
        con.request('POST', '/api/' + operacao, json.dumps(dados),
                    {'Content-Type': 'application/json', 'Origin': cls.servidor.origin,
                     'X-Session-Token': cls.servidor.token})
        resposta = con.getresponse()
        conteudo = resposta.read()
        con.close()
        return resposta.status, (conteudo if corpo_bruto else json.loads(conteudo or b'{}'))

    @classmethod
    def ok(cls, operacao, dados):
        status, corpo = cls.chamar(operacao, dados)
        assert status == 200, (operacao, status, corpo)
        return corpo

    @classmethod
    def percorrer_a_mesa(cls, caso):
        """Pergunta pela Mesa e deixa o agente sintético cumprir as seis etapas; devolve o que a Mesa mostra."""
        enviada = cls.ok('codex-perguntar', {'caso': caso, 'pergunta': PERGUNTA})
        identificador = enviada['conversa']
        etapas_vistas = []
        final = agente(cls.gerenciador, identificador, etapas_vistas.append, cls.ate)
        eventos = cls.ok('codex-eventos', {'conversa': identificador})
        return {'conversa': identificador, 'final': final, 'eventos': eventos, 'etapas': etapas_vistas}

    # --- o que a Mesa mostra de uma revisão ------------------------------------------------------------------
    def detalhe(self, revisao, geracao):
        return self.ok('achados-detalhe', {'caso': CASO, 'rodada': self.rodada, 'revisao': revisao,
                                           'geracao_achados': geracao, 'achado_id': 'A001'})

    @staticmethod
    def vinculo(referencia, papel='suporte'):
        return {'referencia': referencia, 'papel': papel, 'suporte': 'sustentado',
                'natureza': 'declaracao_documental', 'justificativa': 'A linha do contrato traz o dado.'}

    @staticmethod
    def base(**campos):
        return {'caso': CASO, 'requisicao_id': uuid.uuid4().hex, 'autor': 'Editora sintética', **campos}


class QuadrosPelaMesa:
    """As quatro ligações e a abertura do original, sobre uma revisão publicada. Cada classe diz qual."""
    revisao = None
    geracao = None

    def da_mesa(self, revisao, evidencia):
        """O que a Mesa responde ao abrir a evidência (`achados-evidencia`): identidade, localizador, original."""
        return self.ok('achados-evidencia', {'caso': CASO, 'rodada': self.rodada, 'revisao': revisao,
                                             'evidencia_id': evidencia})

    def ref(self, revisao, evidencia):
        return {'tipo': 'ia', 'caso_id': CASO, 'rodada': self.rodada, 'revisao': revisao,
                'registros_sha256': self.da_mesa(revisao, evidencia)['registros_sha256'], 'evidencia_id': evidencia}

    def conferir_ligacao(self, vinculo, trecho, linha):
        """Um vínculo devolvido por um quadro: resolvido contra o original, no documento e na página certos."""
        self.assertEqual(vinculo.get('estado'), 'conferida', vinculo)
        self.assertEqual(vinculo['evidencia']['conferencia'], 'trecho_localizado_no_texto_autorizado')
        self.assertEqual(vinculo['documento_id'], 'D001')
        self.assertEqual(vinculo['localizador']['pagina_pdf'], 1)
        self.assertEqual((vinculo['localizador']['linha_inicio'], vinculo['localizador']['linha_fim']), (linha, linha))
        self.assertIn('D001', vinculo['localizador']['legivel'])
        self.assertIn('página PDF 1', vinculo['localizador']['legivel'])
        self.assertIn(trecho, json.dumps(vinculo, ensure_ascii=False))

    def abrir_original(self, ref, trecho):
        """Segue o vínculo até o arquivo: a Mesa entrega o PDF íntegro e a página do localizador traz o trecho."""
        aberta = self.da_mesa(ref['revisao'], ref['evidencia_id'])
        evidencia = aberta['evidencia']
        status, conteudo = self.chamar('achados-original', {'caso': CASO, 'rodada': self.rodada,
                                       'revisao': ref['revisao'], 'evidencia_id': ref['evidencia_id']}, True)
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(conteudo).hexdigest(), evidencia['original_sha256'])
        self.assertTrue(conteudo.startswith(b'%PDF'))
        pagina = evidencia['localizador']['pagina_pdf']
        leitor = PdfReader(io.BytesIO(conteudo))
        self.assertTrue(1 <= pagina <= len(leitor.pages), (pagina, len(leitor.pages)))
        # A página física, não o rótulo: o trecho inteiro está no texto da página que o localizador aponta.
        texto_da_pagina = ' '.join(leitor.pages[pagina - 1].extract_text().split())
        self.assertIn(' '.join(trecho.split()), texto_da_pagina)
        # E a linha do localizador, na cópia textual conferida por hash (a que a Mesa mostra em `contexto`),
        # é exatamente esse trecho: linha, página e arquivo dizem a mesma coisa.
        contexto = {c['linha']: c['texto'] for c in aberta['contexto']}
        inicio, fim = evidencia['localizador']['linha_inicio'], evidencia['localizador']['linha_fim']
        self.assertEqual(' '.join(' '.join(contexto[n] for n in range(inicio, fim + 1)).split()),
                         ' '.join(trecho.split()))
        return evidencia

    def test_uma_evidencia_publicada_chega_aos_quatro_quadros_e_ao_original(self):
        valor, assinatura, contratada = (self.ref(self.revisao, e) for e in ('E001', 'E002', 'E003'))
        # Hipótese, pelas rotas da Mesa.
        hipotese = self.ok('hipoteses-criar', self.base(enunciado='O contrato 041/2025 vale R$ 8.750.000,00.',
                                                        evidencias=[self.vinculo(valor)]))
        detalhe = self.ok('hipoteses-detalhe', {'caso': CASO, 'id': hipotese['id']})
        self.assertEqual(len(detalhe['evidencias']), 1)
        self.conferir_ligacao(detalhe['evidencias'][0], VALOR, 6)
        quadro = self.ok('hipoteses-quadro', {'caso': CASO})
        self.assertEqual([len(h['sustentam']) for h in quadro['hipoteses'] if h['id'] == hipotese['id']], [1])
        # Linha do tempo: o acontecimento é a assinatura.
        data = {'tipo': 'fato', 'valor': '2025-03-03', 'aproximada': False, 'fonte': 0, 'observacao': ''}
        evento = self.ok('linha-tempo-criar', self.base(descricao='Assinatura do contrato 041/2025.',
                                                        evidencias=[self.vinculo(assinatura)], datas=[data]))
        detalhe = self.ok('linha-tempo-detalhe', {'caso': CASO, 'id': evento['id']})
        self.conferir_ligacao(detalhe['evidencias'][0], ASSINATURA, 8)
        self.assertIn(evento['id'], json.dumps(self.ok('linha-tempo-listar', {'caso': CASO})))
        # Mapa de relações: o nó é a contratada, com o CNPJ que a mesma linha traz.
        no = self.ok('mapa-entidade-criar', self.base(
            tipo='organizacao', nome='Construtora Horizonte Azul Ltda.', evidencias=[self.vinculo(contratada)],
            identificadores=[{'tipo': 'cnpj', 'valor': '00.000.000/0001-00', 'fonte': 0}]))
        mapa = self.ok('mapa-ver', {'caso': CASO})
        no_visto = next(n for n in mapa['entidades'] if n['id'] == no['id'])
        self.conferir_ligacao(no_visto['evidencias'][0], CONTRATADA, 4)
        # Tabela: a célula do valor aponta para a linha do valor.
        colunas = [{'id': 'contrato', 'nome': 'Contrato', 'tipo': 'texto'},
                   {'id': 'valor', 'nome': 'Valor global', 'tipo': 'monetario', 'moeda': 'BRL'}]
        linhas = [{'celulas': {'contrato': {'valor': '041/2025', 'fonte': 0},
                               'valor': {'valor': '8750000.00', 'fonte': 0}}}]
        tabela = self.ok('tabelas-criar', self.base(titulo='Contratos sintéticos', colunas=colunas, linhas=linhas,
                                                    evidencias=[self.vinculo(valor)]))
        visto = self.ok('tabelas-detalhe', {'caso': CASO, 'id': tabela['id']})
        self.conferir_ligacao(visto['evidencias'][0], VALOR, 6)
        celula = visto['linhas'][0]['celulas']['valor']
        self.assertEqual((celula['valor'], celula['fonte']), ('8750000.00', 0))
        # O original: de cada ligação até o PDF, na página do localizador.
        for ref, trecho in ((valor, VALOR), (assinatura, ASSINATURA), (contratada, CONTRATADA)):
            evidencia = self.abrir_original(ref, trecho)
            self.assertEqual(evidencia['trecho'], trecho)
            self.assertEqual(evidencia['documento_id'], 'D001')

    def tentativas_de_gravar(self, ref):
        """Um pedido de criação por quadro, todos com a mesma referência (a adulterada)."""
        data = {'tipo': 'fato', 'valor': '2025-03-03', 'aproximada': False, 'fonte': 0, 'observacao': ''}
        colunas = [{'id': 'valor', 'nome': 'Valor global', 'tipo': 'monetario', 'moeda': 'BRL'}]
        linhas = [{'celulas': {'valor': {'valor': '8750000.00', 'fonte': 0}}}]
        vinculos = [self.vinculo(ref)]
        return {
            'hipoteses-criar': self.base(enunciado='Hipótese com referência adulterada.', evidencias=vinculos),
            'linha-tempo-criar': self.base(descricao='Acontecimento com referência adulterada.',
                                           evidencias=vinculos, datas=[data]),
            'mapa-entidade-criar': self.base(tipo='organizacao', nome='Entidade com referência adulterada',
                                             evidencias=vinculos),
            'tabelas-criar': self.base(titulo='Tabela com referência adulterada', colunas=colunas,
                                       linhas=linhas, evidencias=vinculos)}

    def estado_dos_quadros(self):
        """Tudo o que os quatro quadros guardam do caso, lido pelas rotas da Mesa."""
        return {operacao: self.ok(operacao, {'caso': CASO}) for operacao in
                ('hipoteses-listar', 'linha-tempo-listar', 'mapa-ver', 'tabelas-listar')}

    def test_identidade_adulterada_ou_revisao_inexistente_e_recusada_em_cada_quadro(self):
        """Independe dos outros testes: compara o estado dos quadros antes e depois, não com 'vazio'."""
        ref = self.ref(self.revisao, 'E001')
        antes = self.estado_dos_quadros()
        for campo, valor in (('registros_sha256', '0' * 64), ('revisao', 'r9_inexistente')):
            for operacao, pedido in self.tentativas_de_gravar({**ref, campo: valor}).items():
                status, corpo = self.chamar(operacao, pedido)
                self.assertEqual(status, 400, (operacao, campo, corpo))
                self.assertTrue(corpo.get('erro'), (operacao, campo, corpo))
                self.assertNotIn(str(self.root), json.dumps(corpo))
        self.assertEqual(self.estado_dos_quadros(), antes)
        # Com a referência íntegra o mesmo pedido grava: a recusa acima foi da adulteração, não do pedido.
        for operacao, pedido in self.tentativas_de_gravar(ref).items():
            self.ok(operacao, pedido)


class MesaInteiraTest(Mesa, QuadrosPelaMesa, unittest.TestCase):
    """Pergunta, seis etapas e quadros sobre a síntese publicada pelo fluxo da Mesa (`r3_sintese`)."""
    revisao, geracao = 'r3_sintese', 'g1'

    def test_a_mesa_cumpriu_as_seis_etapas_e_publicou_as_tres_revisoes_com_os_nomes_reais(self):
        self.assertEqual(self.mesa['etapas'], list(ETAPAS))
        self.assertEqual(self.mesa['eventos']['conversa']['estado'], 'concluido')
        publicacoes = [e['dados'] for e in self.mesa['eventos']['eventos'] if e['tipo'] == 'publicacao']
        self.assertEqual([(p['revisao'], p['geracao'], p['estado']) for p in publicacoes],
                         [('r3_sintese', 'g1', 'verificado')])
        catalogo = self.ok('achados-catalogo', {'caso': CASO, 'rodada': self.rodada})
        self.assertEqual(catalogo['revisoes'], list(REVISOES_REAIS))
        self.assertEqual(catalogo['indices'], [{'geracao': 'g1', 'revisao': 'r3_sintese'}])
        pasta = self.root / 'execucoes' / CASO / self.rodada / 'saidas/achados/revisoes'
        self.assertEqual(sorted(p.name for p in pasta.iterdir()), sorted(REVISOES_REAIS))
        achado = self.detalhe('r3_sintese', 'g1')['achado']
        self.assertEqual((achado['suporte'], achado['destino']), ('sustentado', 'incluido'))
        self.assertEqual([e['id'] for e in achado['evidencias']], ['E001', 'E002', 'E003'])

    def test_os_quadros_resolvem_cada_revisao_publicada_pelo_fluxo(self):
        """Qualquer das três revisões reais serve de origem: hipótese e original, uma por revisão."""
        for revisao in REVISOES_REAIS:
            ref = self.ref(revisao, 'E001')
            criada = self.ok('hipoteses-criar', self.base(enunciado=f'Valor segundo {revisao}.',
                                                          evidencias=[self.vinculo(ref)]))
            vinculo = self.ok('hipoteses-detalhe', {'caso': CASO, 'id': criada['id']})['evidencias'][0]
            self.conferir_ligacao(vinculo, VALOR, 6)
            self.assertEqual(vinculo['referencia']['revisao'], revisao)
            self.abrir_original(ref, VALOR)


class MesaDoAgenteDeChatTest(Mesa, QuadrosPelaMesa, unittest.TestCase):
    """O modo agente de chat (prompts/05_SINTETIZAR.md): as etapas até a revisão pela Mesa e a revisão final
    `r3_briefing` publicada pelo agente, com `achados.py construir`. Nenhuma `r3_sintese` na rodada."""
    revisao, geracao = 'r3_briefing', 'g1'
    ate = 'revisao'

    @classmethod
    def completar(cls):
        cls.ok('codex-cancelar', {'conversa': cls.mesa['conversa']})
        aguardar_fim(cls.gerenciador, cls.mesa['conversa'])
        r2, manifesto = carregar(cls.root, CASO, cls.rodada, 'r2_revisao')
        run = cls.root / 'execucoes' / CASO / cls.rodada
        arquivo = 'saidas/achados_briefing_r3.md'
        (run / arquivo).write_text('[A001@v1] O contrato 041/2025 declara valor global de R$ 8.750.000,00.\n',
                                   encoding='utf-8')
        briefing = copy.deepcopy(r2)
        briefing.update(revisao='r3_briefing',
                        anterior={'revisao': 'r2_revisao', 'registros_sha256': manifesto['registros_sha256']})
        briefing['artefatos'].append({'arquivo': arquivo, 'sha256': sha256(run / arquivo), 'tipo': 'briefing'})
        briefing['procedencia'].append({'etapa': 'sintese', 'artefatos': [arquivo], 'ferramentas': ['achados.py'],
                                        'modelo_informado_ou_observado': None})
        briefing['destinos'].append({'achado_id': 'A001', 'versao': 1, 'destino': 'incluido',
                                     'motivo': 'Declaração documental revisada.', 'briefing': arquivo,
                                     'revisao_suporte': 1})
        publicar(cls.root, CASO, cls.rodada, briefing)
        indice_achados.construir(cls.root, CASO, cls.rodada, 'r3_briefing', 'g1')
        indice_achados.verificar(cls.root, CASO, cls.rodada, 'r3_briefing', 'g1')

    def test_a_rodada_tem_r3_briefing_e_nenhuma_r3_sintese(self):
        catalogo = self.ok('achados-catalogo', {'caso': CASO, 'rodada': self.rodada})
        self.assertEqual(catalogo['revisoes'], ['r1_busca', 'r2_revisao', 'r3_briefing'])
        self.assertEqual(catalogo['indices'], [{'geracao': 'g1', 'revisao': 'r3_briefing'}])
        achado = self.detalhe('r3_briefing', 'g1')['achado']
        self.assertEqual((achado['suporte'], achado['destino']), ('sustentado', 'incluido'))
        digest = sha256(self.root / 'execucoes' / CASO / self.rodada / achado['briefing'])
        texto = self.ok('achados-briefing', {'caso': CASO, 'rodada': self.rodada, 'revisao': 'r3_briefing',
                                             'artefato_sha256': digest})['texto']
        self.assertIn('[A001@v1]', texto)


if __name__ == '__main__':
    unittest.main()
