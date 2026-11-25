"""Portão da Onda 2, complemento: escritas COMPLETAS e válidas na apuração própria de Alfa que apontam ids reais de Beta.

O teste de isolamento já mandava referências de outra redação, mas quase todas paravam na validação do corpo (campo faltando, hash inventado) e nunca
chegavam à conferência de posse. Aqui cada corpo é completo e válido: o mesmo corpo, com a referência da PRÓPRIA apuração de Alfa (`epsilon`), é gravado
(200), e a prova é que, com a referência trocada por uma de Beta (`zetazeta`), o servidor recusa e:

  - nada muda em Beta (a pasta da apuração, a das execuções e as conversas, byte a byte);
  - nada muda em Alfa (a recusa não deixa gravação pela metade);
  - nenhuma sentinela de Beta (nome, ids reais, hashes, trechos) aparece na resposta nem nos arquivos de Alfa.

As quatro formas de apontar para Beta, em cada operação: referência humana (fonte do caderno) e referência da IA (evidência de achados), cada uma
com o `caso_id` de Beta e com o `caso_id` de Alfa mas os ids de Beta. Os ids internos de Beta que o cenário repete em Alfa (D001, E001, A001) não
distinguem nada; por isso o que aponta para Beta é o `caso_id`, o registro do caderno, os hashes e a identidade do conjunto de achados.

Operações: hipoteses-criar/atualizar, linha-tempo-criar/atualizar (com `datas[].fonte`), mapa-relacao-criar/atualizar, tabelas-criar/atualizar (a fonte de
cada célula é um índice nas evidências da tabela), apuracao-nota-salvar (nota_id de Beta), achados-revisao-salvar (achado_id, registros_sha256),
comparar-evidencias e comparar-documentos.
"""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import caderno
import cenario_redacoes as cenario
from fixture_achados import Ambiente
from indice_achados import construir
from registros_achados import publicar

CASO_A, CASO_B = 'epsilon', 'zetazeta'
# Arquivos que uma leitura acrescenta por conta própria (log de consulta do índice, travas): não são gravação do pedido. `quadros` NÃO entra aqui:
# é em casos/<caso>/quadros/<nome> (evidencias.py) que hipóteses, linha do tempo, mapa e tabelas gravam, e filtrá-la deixava o teste cego a elas.
TRANSITORIOS = ('consultas_sqlite', '.lock')


def semear(root, caso, titulo_extra, pasta):
    """Um caso com rodada R001 e achados publicados (r1/g1), como o fixture dos testes de evidência faz, mas com o texto-fonte de cada redação."""
    from pypdf import PdfWriter
    env = Ambiente.__new__(Ambiente)
    env.temp, env.root = None, root
    pasta.mkdir()
    env.text = pasta / 'texto.txt'
    env.text.write_text('A fonte declara valor 12.\nOutra versão declara valor 14.\n' + titulo_extra + '\n', encoding='utf-8')
    env.pdf = pasta / 'visual.pdf'
    escritor = PdfWriter()
    escritor.add_blank_page(width=300, height=300)
    escritor.write(env.pdf)
    env.tab = pasta / 'segunda.txt'   # o terceiro documento é um segundo texto, para o comparador de documentos
    env.tab.write_text('A fonte declara cifra 12.\nOutra versão declara cifra 15.\n', encoding='utf-8')   # sem a palavra que o fixture pesquisa
    env.caso(caso)
    primeira = publicar(root, caso, 'R001', env.dados(caso))
    construir(root, caso, 'R001', 'r1', 'g1')
    return primeira['manifesto']['registros_sha256']


class EscritasCruzadasTest(cenario.DuasRedacoes):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        externa = tempfile.TemporaryDirectory()
        cls._pilha.callback(externa.cleanup)
        fontes = Path(externa.name)
        cls.regs = {CASO_A: semear(cls.root, CASO_A, 'Nada reservado aqui.', fontes / 'a'),
                    CASO_B: semear(cls.root, CASO_B, 'Zetazetico reservado.', fontes / 'b')}
        acesso.atribuir_caso(cls.root, CASO_A, cls.a)
        acesso.atribuir_caso(cls.root, CASO_B, cls.b)
        acesso.definir_responsavel(cls.root, CASO_A, cls.ids['reporter'], 'operador', cls.a)
        acesso.definir_responsavel(cls.root, CASO_B, cls.ids['reporter_b'], 'operador', cls.b)
        cls.registro = {caso: cls._registro(caso, autor) for caso, autor in ((CASO_A, 'Repórter de Alfa'), (CASO_B, 'Repórter Zetazetico'))}
        cls.sentinelas = (*cls.sentinelas, CASO_B, 'Zetazetico', cls.registro[CASO_B]['registro']['id'], cls.registro[CASO_B]['sha256'],
                          cls.regs[CASO_B], 'Caso sintético ' + CASO_B)
        # O que é próprio de Alfa e não pode aparecer como se fosse de Beta, e vice-versa, só vale para a leitura de sentinelas: Alfa não tem nenhuma delas.
        assert not any(s in (CASO_A, cls.regs[CASO_A], cls.registro[CASO_A]['sha256']) for s in cls.sentinelas)

    @classmethod
    def _registro(cls, caso, autor):
        """Uma fonte do caderno do caso (trecho da linha 2 do original), gravada como a Mesa grava."""
        docs = caderno.documentos(cls.root, caso)
        doc = docs['documentos'][0]
        return caderno.salvar(cls.root, {
            'caso': caso, 'origem_id': docs['origem_id'], 'documento_id': doc['documento_id'], 'documento_sha256': doc['sha256'],
            'pagina_pdf': None, 'localizador': 'Linha 2', 'trecho': 'Outra versão declara valor 14.', 'titulo': 'Trecho humano',
            'anotacao': '', 'autor': autor, 'tipo': 'trecho', 'transcricao_manual': False, 'requisicao_id': uuid.uuid4().hex})

    # --- referências -------------------------------------------------------------------------------

    def humana(self, caso):
        r = self.registro[caso]
        return {'tipo': 'humana', 'caso_id': caso, 'registro_id': r['registro']['id'], 'sha256': r['sha256'], 'fonte': 0}

    def ia(self, caso, evidencia='E001'):
        return {'tipo': 'ia', 'caso_id': caso, 'rodada': 'R001', 'revisao': 'r1', 'registros_sha256': self.regs[caso], 'evidencia_id': evidencia}

    def hostis(self):
        """As quatro formas de apontar para Beta de dentro da apuração de Alfa."""
        return {'humana, caso_id de Beta': self.humana(CASO_B),
                'humana, caso_id de Alfa e registro de Beta': {**self.humana(CASO_B), 'caso_id': CASO_A},
                'ia, caso_id de Beta': self.ia(CASO_B),
                'ia, caso_id de Alfa e identidade de achados de Beta': {**self.ia(CASO_B), 'caso_id': CASO_A}}

    @staticmethod
    def vinculo(ref, papel='suporte'):
        return {'referencia': ref, 'papel': papel, 'suporte': 'sustentado', 'natureza': 'declaracao_documental', 'justificativa': 'Trecho sintético.'}

    @staticmethod
    def base(caso=CASO_A, **campos):
        return {'caso': caso, 'requisicao_id': uuid.uuid4().hex, 'autor': 'Dona Alfa', **campos}

    # --- o que "nada muda" quer dizer ---------------------------------------------------------------

    def arquivos(self, *pastas):
        resumo = {}
        for pasta in pastas:
            base = self.root / pasta
            for arquivo in sorted(p for p in base.rglob('*') if p.is_file()) if base.is_dir() else []:
                if any(parte in TRANSITORIOS or arquivo.name.endswith('.lock') for parte in arquivo.parts):
                    continue
                resumo[arquivo.relative_to(self.root).as_posix()] = hashlib.sha256(arquivo.read_bytes()).hexdigest()
        return resumo

    def de_beta(self):
        return self.arquivos(f'casos/{CASO_B}', f'execucoes/{CASO_B}')

    def de_alfa(self):
        return self.arquivos(f'casos/{CASO_A}', f'execucoes/{CASO_A}')

    def sem_rastro_de_beta_em_alfa(self):
        """Nenhum arquivo da apuração de Alfa carrega o que é de Beta."""
        procurado = [s.encode('utf-8') for s in self.sentinelas if s not in (self.b, REDACAO_B)]
        for caminho in self.de_alfa():
            conteudo = (self.root / caminho).read_bytes()
            for s in procurado:
                self.assertNotIn(s, conteudo, f'{caminho} carrega {s!r} de Beta')

    # --- as provas ----------------------------------------------------------------------------------

    def gravada(self, operacao, corpo):
        """O corpo válido, com a referência de Alfa: grava (200). Sem isto a recusa abaixo poderia ser só um corpo mal formado."""
        antes = self.de_alfa()
        status, dados, bruto = self.post('dono', operacao, corpo)
        self.assertEqual(status, 200, f'{operacao}: o corpo de controle não é válido: {bruto[:300]!r}')
        # A gravação aparece no que o teste vigia: se não mudasse de_alfa, "nada muda em Alfa" nas recusas não provaria nada para esta operação.
        self.assertNotEqual(self.de_alfa(), antes, f'{operacao}: a escrita de controle não mudou nenhum arquivo lido por de_alfa()')
        self.sem_sentinela(bruto, operacao)
        return dados

    def recusada(self, operacao, corpo, rotulo=''):
        """O mesmo corpo, com a referência de Beta: recusa, sem rastro, e nada muda em Beta nem em Alfa."""
        beta, alfa = self.de_beta(), self.de_alfa()
        status, _, bruto = self.post('dono', operacao, corpo)
        onde = f'{operacao} ({rotulo})'
        if os.environ.get('VLADO_VER_RECUSAS'):
            print(f'RECUSA {onde}: {status} {bruto[:160].decode("utf-8", "replace")}')
        self.assertGreaterEqual(status, 400, f'{onde}: gravou o que aponta para Beta: {bruto[:300]!r}')
        self.assertLess(status, 500, f'{onde}: erro do servidor em vez de recusa: {bruto[:300]!r}')
        self.sem_sentinela(bruto, onde)
        self.assertEqual(self.de_beta(), beta, f'{onde}: mudou algo em Beta')
        self.assertEqual(self.de_alfa(), alfa, f'{onde}: a recusa deixou gravação em Alfa')
        self.sem_rastro_de_beta_em_alfa()

    def recusa_todas(self, operacao, montar):
        """`montar(ref)` devolve o corpo completo com `ref` no lugar da referência; roda as quatro formas hostis."""
        for rotulo, ref in self.hostis().items():
            with self.subTest(operacao=operacao, ref=rotulo):
                self.recusada(operacao, montar(ref), rotulo)

    # --- hipóteses, linha do tempo, mapa ------------------------------------------------------------

    def test_hipoteses_criar_com_evidencia_de_beta(self):
        self.gravada('hipoteses-criar', self.base(enunciado='Hipótese de Alfa', evidencias=[self.vinculo(self.humana(CASO_A))]))
        self.recusa_todas('hipoteses-criar', lambda ref: self.base(enunciado='Hipótese que aponta para Beta', evidencias=[self.vinculo(ref)]))

    def test_hipoteses_atualizar_troca_a_evidencia_por_uma_de_beta(self):
        criada = self.gravada('hipoteses-criar', self.base(enunciado='Hipótese própria', evidencias=[self.vinculo(self.ia(CASO_A))]))
        for rotulo, ref in self.hostis().items():
            with self.subTest(ref=rotulo):
                self.recusada('hipoteses-atualizar', self.base(id=criada['id'], anterior_sha256=criada['sha256'], situacao='sustentada',
                                                              evidencias=[self.vinculo(ref)]), rotulo)
        # E a hipótese de Alfa continua como estava: a atualização válida, depois das recusas, ainda encontra o hash anterior.
        self.gravada('hipoteses-atualizar', self.base(id=criada['id'], anterior_sha256=criada['sha256'], situacao='sustentada'))

    def test_hipoteses_com_a_evidencia_de_beta_ao_lado_de_uma_de_alfa(self):
        self.recusa_todas('hipoteses-criar', lambda ref: self.base(
            enunciado='Hipótese com duas evidências', evidencias=[self.vinculo(self.ia(CASO_A)), self.vinculo(ref, 'contradicao')]))

    def datas(self):
        return [{'tipo': 'fato', 'valor': '2021-03', 'aproximada': False, 'fonte': 0, 'observacao': ''}]

    def test_linha_do_tempo_criar_e_atualizar_com_evidencia_de_beta(self):
        criado = self.gravada('linha-tempo-criar', self.base(descricao='Fato de Alfa', evidencias=[self.vinculo(self.ia(CASO_A))], datas=self.datas()))
        self.recusa_todas('linha-tempo-criar', lambda ref: self.base(descricao='Fato que aponta para Beta', evidencias=[self.vinculo(ref)],
                                                                       datas=self.datas()))
        self.recusa_todas('linha-tempo-atualizar', lambda ref: self.base(id=criado['id'], anterior_sha256=criado['sha256'],
                                                                         evidencias=[self.vinculo(ref)], datas=self.datas()))

    def test_mapa_relacao_criar_e_atualizar_com_evidencia_de_beta(self):
        p1 = self.gravada('mapa-entidade-criar', self.base(tipo='pessoa', nome='Pessoa Um de Alfa'))
        p2 = self.gravada('mapa-entidade-criar', self.base(tipo='pessoa', nome='Pessoa Dois de Alfa'))
        relacao = self.gravada('mapa-relacao-criar', self.base(origem=p1['id'], destino=p2['id'], tipo='socio',
                                                               evidencias=[self.vinculo(self.humana(CASO_A))]))
        self.recusa_todas('mapa-relacao-criar', lambda ref: self.base(origem=p1['id'], destino=p2['id'], tipo='parente', evidencias=[self.vinculo(ref)]))
        self.recusa_todas('mapa-relacao-atualizar', lambda ref: self.base(id=relacao['id'], anterior_sha256=relacao['sha256'], tipo='socio',
                                                                          evidencias=[self.vinculo(ref)]))

    # --- tabelas: a fonte de cada célula é um índice nas evidências -----------------------------------

    COLUNAS = [{'id': 'contrato', 'nome': 'Contrato', 'tipo': 'texto'}, {'id': 'valor', 'nome': 'Valor', 'tipo': 'monetario', 'moeda': 'BRL'}]

    def linhas(self):
        return [{'celulas': {'contrato': {'valor': 'Contrato 1', 'fonte': 0}, 'valor': {'valor': '12', 'fonte': 0}}},
                {'celulas': {'contrato': {'valor': 'Contrato 2', 'fonte': 1}, 'valor': {'valor': '14.25', 'fonte': 1}}}]

    def tabela(self, ref_a, ref_b):
        return self.base(titulo='Contratos sintéticos', colunas=self.COLUNAS, linhas=self.linhas(),
                         evidencias=[self.vinculo(ref_a), self.vinculo(ref_b)])

    def test_tabelas_criar_e_atualizar_com_fonte_de_beta(self):
        criada = self.gravada('tabelas-criar', self.tabela(self.ia(CASO_A), self.humana(CASO_A)))
        for rotulo, ref in self.hostis().items():
            with self.subTest(ref=rotulo):
                self.recusada('tabelas-criar', self.tabela(ref, self.humana(CASO_A)), rotulo + ', na primeira fonte')
                self.recusada('tabelas-criar', self.tabela(self.ia(CASO_A), ref), rotulo + ', na segunda fonte')
                self.recusada('tabelas-atualizar', self.base(id=criada['id'], anterior_sha256=criada['sha256'],
                                                             evidencias=[self.vinculo(self.ia(CASO_A)), self.vinculo(ref)]), rotulo)

    # --- notas, achados e comparadores ---------------------------------------------------------------

    def salvar_nota(self, quem, caso, titulo, texto, **campos):
        return self.post(quem, 'apuracao-nota-salvar', {'caso': caso, 'requisicao_id': uuid.uuid4().hex, 'titulo': titulo, 'texto': texto, **campos})

    def test_nota_de_beta_nao_se_edita_pela_apuracao_de_alfa(self):
        # Beta com duas notas; Alfa com uma. O id da primeira se repete nas duas redações (ids internos iguais), o da segunda só existe em Beta.
        primeira_b = self.salvar_nota('dono_b', CASO_B, 'Primeira de Beta', 'Anotação Zetazetico reservada.')[1]['nota']['id']
        segunda = self.salvar_nota('dono_b', CASO_B, 'Segunda de Beta', 'Outra anotação Zetazetico.')[1]['nota']
        segunda_b = segunda['id']
        propria = self.gravada('apuracao-nota-salvar', {'caso': CASO_A, 'requisicao_id': uuid.uuid4().hex, 'titulo': 'Nota de Alfa', 'texto': 'Anotação de Alfa.'})
        id_a = propria['nota']['id']
        self.assertNotEqual(segunda_b, id_a, 'o cenário precisa de um id de Beta que Alfa não tem')
        revisao_a, revisao_b = propria['nota']['revisao'], segunda['revisao']   # o hash de conflito de cada nota: a edição só vai além dele se a nota for da apuração
        edicao = {'titulo': 'Troca', 'texto': 'Texto novo.'}
        self.recusada('apuracao-nota-salvar', {'caso': CASO_A, 'requisicao_id': uuid.uuid4().hex, 'nota_id': segunda_b, 'revisao_nota': revisao_b, **edicao},
                      'nota_id de Beta na apuração de Alfa')
        self.recusada('apuracao-nota-salvar', {'caso': CASO_B, 'requisicao_id': uuid.uuid4().hex, 'nota_id': segunda_b, 'revisao_nota': revisao_b, **edicao},
                      'apuração de Beta, pela dona de Alfa')
        if primeira_b == id_a:   # o mesmo id nas duas: a edição de Alfa é de Alfa, e a nota de Beta continua como estava
            beta = self.de_beta()
            editada = self.salvar_nota('dono', CASO_A, 'Troca', 'Texto novo de Alfa.', nota_id=id_a, revisao_nota=revisao_a)
            self.assertEqual(editada[0], 200, editada[2][:300])
            self.sem_sentinela(editada[2], 'edição da nota de Alfa com o id repetido')
            self.assertEqual(self.de_beta(), beta)
        lida = self.post('dono_b', 'apuracao-nota', {'caso': CASO_B, 'nota_id': primeira_b})[2].decode('utf-8')
        self.assertIn('Zetazetico', lida)   # a nota de Beta segue intacta para a dona de Beta

    def test_achados_revisao_salvar_com_identidade_de_beta(self):
        def corpo(caso, regs, **campos):
            return {'caso': caso, 'rodada': 'R001', 'revisao': 'r1', 'geracao_achados': 'g1', 'achado_id': 'A001', 'achado_versao': 1,
                    'registros_sha256': regs, 'estado': 'sem_suporte_suficiente', 'observacao': 'Conferido em teste.', **campos}
        # O corpo de Alfa é válido; se o servidor exigir que o original tenha sido aberto antes, o controle diz isso com a mensagem dele.
        status, _, bruto = self.post('dono', 'achados-revisao-salvar', corpo(CASO_A, self.regs[CASO_A]))
        self.assertEqual(status, 200, bruto[:300])
        self.recusada('achados-revisao-salvar', corpo(CASO_A, self.regs[CASO_B]), 'registros_sha256 de Beta na apuração de Alfa')
        self.recusada('achados-revisao-salvar', corpo(CASO_B, self.regs[CASO_B]), 'apuração de Beta, pela dona de Alfa')
        self.recusada('achados-revisao-salvar', corpo(CASO_B, self.regs[CASO_A]), 'apuração de Beta com a identidade de Alfa')

    def test_comparar_evidencias_e_documentos_com_ids_de_beta(self):
        ok = self.post('dono', 'comparar-evidencias', {'caso': CASO_A, 'a': self.ia(CASO_A, 'E001'), 'b': self.ia(CASO_A, 'E002')})
        self.assertEqual(ok[0], 200, ok[2][:300])
        for rotulo, ref in self.hostis().items():
            with self.subTest(ref=rotulo):
                self.recusada('comparar-evidencias', {'caso': CASO_A, 'a': self.ia(CASO_A, 'E001'), 'b': ref}, rotulo + ', em b')
                self.recusada('comparar-evidencias', {'caso': CASO_A, 'a': ref, 'b': self.ia(CASO_A, 'E002')}, rotulo + ', em a')
        docs = {'caso': CASO_A, 'rodada': 'R001', 'documento_a': 'D001', 'documento_b': 'D003', 'contexto': 1}
        comparados = self.post('dono', 'comparar-documentos', docs)
        self.assertEqual(comparados[0], 200, comparados[2][:300])
        # Os documentos de Beta têm os mesmos ids; o que os separa é a apuração, e Alfa não chega a ela.
        self.recusada('comparar-documentos', {**docs, 'caso': CASO_B}, 'apuração de Beta')


REDACAO_B = cenario.REDACAO_B


if __name__ == '__main__':
    unittest.main()
