"""A matriz operação × papel do contrato de contas, célula por célula (seção 5.17, itens 1 a 5).

1. ``autorizacao.MATRIZ`` é igual às tabelas 5.2 a 5.13 de ``.maestro/equipe/CONTRATO_CONTAS.md``: este teste lê o
   contrato. Mudar o código sem mudar o contrato, ou o contrário, falha aqui.
2. Nada fica de fora: as operações da matriz são as do servidor (``OPERACOES_API``); as que o contrato define e
   ainda não existem estão em ``autorizacao.PENDENTES``, uma a uma.
3. Cada célula é uma requisição HTTP de verdade contra um servidor em modo ``piloto``, com duas redações
   (``cenario_redacoes``): operação × papel × situação (própria, de colega com inclusão, de colega sem inclusão,
   de outra redação).

O corpo de cada pedido é o mínimo (só o que o portão usa para achar a apuração), de modo que uma célula que passa
costuma ser recusada depois pela validação da rota: o que se prova é que a autorização deixou passar. Uma célula
que recusa tem o status e o código exatos, não muda nada em disco nem no armazenamento de contas, e não devolve
nada da outra redação. Sem modelo e sem rede.
"""
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import autorizacao
import cenario_redacoes as cenario
import interface_pesquisa

CONTRATO = Path(__file__).resolve().parents[1] / '.maestro' / 'equipe' / 'CONTRATO_CONTAS.md'
COLUNAS_DE_PAPEL = ('D', 'E', 'R', 'L', 'C')
NOME = re.compile(r'`([^`]+)`(\\\*)?')
# Células em que o modo `piloto` do cenário difere da tabela, com a razão; cada uma tem o seu teste abaixo.
FORA_DA_TABELA = {
    'codex-desligar': 'no piloto o serviço não se encerra pela interface: recusado a todos (observação da linha)',
    'ia-config-salvar': 'com mais de uma redação, a chave do serviço não se troca pela Mesa até existir a chave própria '
                        'de cada redação (entrega seguinte)',
    'contas-criar': 'com mais de uma redação, ninguém escolhe login pela Mesa: o login é único na instalação e a recusa '
                    '"já existe" contaria a uma redação o que há na outra (operação em retirada; o convite a substitui)',
    'sessao-sair': 'encerra a sessão usada pelo próprio teste: conferida à parte, com uma sessão só para isso'}


def ler_contrato():
    """As tabelas 5.2 a 5.13 do contrato: ({chave: (resolvedor, tipo, células)}, públicas, com asterisco, rotas GET públicas)."""
    texto = CONTRATO.read_text(encoding='utf-8')
    corpo = texto[texto.index('### 5.2 '):texto.index('### 5.14 ')]
    linhas, publicas, novas, get_publicas = {}, set(), set(), set()
    for secao in re.split(r'\n(?=### 5\.\d+ )', corpo):
        padrao = re.search(r'Resolvedor `(\w+)`', secao.split('\n|', 1)[0])
        cabecalho = None
        for linha in secao.splitlines():
            if not linha.startswith('|'):
                cabecalho = None if not linha.strip() else cabecalho
                continue
            celulas = [c.strip() for c in linha.strip().strip('|').split('|')]
            if cabecalho is None:
                cabecalho = celulas
                continue
            if set(linha) <= set('|-: '):
                continue
            campos = dict(zip(cabecalho, celulas))
            primeiro = campos.get('Operação') or campos.get('Rota')
            nomes = NOME.findall(primeiro)
            novas |= {nome for nome, asterisco in nomes if asterisco}
            if 'D' not in campos:  # the table of operations before a session: no role
                publicas |= {nome for nome, _ in nomes}
                continue
            if campos['D'] == 'pública':
                get_publicas |= {nome for nome, _ in nomes}
                continue
            if nomes[0][0] == 'codex-perguntar':
                chaves = ['codex-perguntar#conversa' if 'com `conversa`' in primeiro else 'codex-perguntar']
            elif nomes[0][0] == 'cadastrar' and 'novo: true' in primeiro:
                chaves = ['cadastrar#novo']
            else:
                chaves = [nome.replace('GET ', 'GET:') for nome, _ in nomes]
            resolvedor = campos.get('Resolvedor')
            resolvedor = (frozenset(r for r in autorizacao.RESOLVEDORES if re.search(rf'\b{r}\b', resolvedor))
                          if resolvedor is not None else frozenset({padrao.group(1)}))
            papeis = dict(zip(autorizacao.PAPEIS, (campos[c] for c in COLUNAS_DE_PAPEL)))
            for chave in chaves:
                assert chave not in linhas, f'{chave} aparece em duas linhas do contrato'
                linhas[chave] = (resolvedor, campos['Tipo'], papeis)
    return linhas, publicas, novas, get_publicas


class ContratoTest(unittest.TestCase):
    """The contract is the source: the code's table is the document's table."""

    @classmethod
    def setUpClass(cls):
        cls.linhas, cls.publicas, cls.novas, cls.get_publicas = ler_contrato()

    def test_cada_linha_do_contrato_e_igual_a_da_matriz(self):
        for chave, (resolvedor, tipo, papeis) in sorted(self.linhas.items()):
            if chave in autorizacao.PENDENTES:
                continue
            with self.subTest(operacao=chave):
                self.assertIn(chave, autorizacao.MATRIZ, 'linha do contrato sem entrada na matriz')
                regra = autorizacao.MATRIZ[chave]
                self.assertEqual((regra.resolvedor, regra.tipo, regra.celulas), (resolvedor, tipo, papeis))

    def test_a_matriz_nao_tem_operacao_fora_do_contrato(self):
        self.assertEqual(set(autorizacao.MATRIZ) - set(self.linhas), set())
        self.assertTrue(all(c in autorizacao.CELULAS for _, _, papeis in self.linhas.values() for c in papeis.values()))

    def test_o_que_o_contrato_define_e_ainda_nao_existe_esta_listado_como_pendente(self):
        fora = (set(self.linhas) | self.publicas) - set(autorizacao.MATRIZ) - set(autorizacao.PUBLICAS)
        self.assertEqual(fora, set(autorizacao.PENDENTES))
        self.assertLessEqual(set(autorizacao.PENDENTES), self.novas, 'pendente que o contrato não marca como nova')
        self.assertFalse(set(autorizacao.PENDENTES) & set(interface_pesquisa.OPERACOES_API))

    def test_operacoes_do_servidor_e_da_matriz_sao_as_mesmas(self):
        self.assertEqual(autorizacao.operacoes_com_sessao(), set(interface_pesquisa.OPERACOES_API))
        self.assertEqual(set(autorizacao.PUBLICAS), set(interface_pesquisa.OPERACOES_PUBLICAS))
        self.assertEqual(self.publicas - self.novas, set(autorizacao.PUBLICAS))
        self.assertEqual({c for c in autorizacao.MATRIZ if c.startswith('GET:')},
                         {'GET:/', 'GET:/api/sessao', 'GET:/api/integracao', 'GET:/api/catalogo', 'GET:/api/fila', 'GET:/api/cota'})

    def test_operacoes_retiradas_do_contrato_sao_as_transitorias_e_so_o_dono_as_alcanca(self):
        texto = CONTRATO.read_text(encoding='utf-8')
        nota = texto[texto.index('**Operações retiradas:**'):].split('\n', 1)[0]
        retiradas = {nome for nome, _ in NOME.findall(nota) if nome.startswith('contas-')}
        self.assertEqual(retiradas, set(autorizacao.TRANSITORIAS))
        self.assertEqual(len(retiradas), 6)
        for regra in autorizacao.TRANSITORIAS.values():
            self.assertEqual(regra.celulas, {'dono': 'sim', 'editor': '—', 'reporter': '—', 'leitor': '—', 'convidado': '—'})

    def test_coluna_do_convidado_e_o_que_o_convidado_ja_alcancava_mais_a_propria_conta(self):
        # The legacy profile keeps what the guest could call; the only addition is the own account (section 5.4):
        # nothing of any case.
        alcanca = {c.split('#')[0] for c, regra in autorizacao.MATRIZ.items()
                   if not c.startswith('GET:') and regra.celulas['convidado'] != autorizacao.NEGADO}
        self.assertEqual(alcanca, set(interface_pesquisa.OPERACOES_CONVIDADO) | set(interface_pesquisa.CONTA_PROPRIA))
        self.assertTrue(all(o.startswith('conta-') for o in interface_pesquisa.CONTA_PROPRIA))
        for operacao in interface_pesquisa.CONTA_PROPRIA:
            self.assertEqual(autorizacao.MATRIZ[operacao].resolvedor, frozenset({'nenhum'}))

    def test_capacidades_saem_da_matriz(self):
        self.assertIn('redacao-revisar', autorizacao.capacidades({'papel': 'editor'}))
        self.assertNotIn('redacao-revisar', autorizacao.capacidades({'papel': 'reporter'}))
        self.assertNotIn('cadastrar', autorizacao.capacidades({'papel': 'editor'}))
        self.assertEqual(set(autorizacao.capacidades({'papel': 'convidado'})),
                         set(interface_pesquisa.OPERACOES_CONVIDADO) | set(interface_pesquisa.CONTA_PROPRIA))
        self.assertIn('equipe-papel', autorizacao.capacidades({'papel': 'dono'}))
        for papel in ('editor', 'reporter', 'leitor', 'convidado'):
            self.assertFalse([o for o in autorizacao.capacidades({'papel': papel}) if o.startswith('equipe-')], papel)


class Pedido:
    """One cell opened into one request: who, what, what to expect and how to tell."""

    def __init__(self, operacao, papel, situacao, corpo, esperado, alcance=None, rotulo=''):
        self.operacao, self.papel, self.situacao, self.corpo = operacao, papel, situacao, corpo
        self.esperado, self.alcance, self.rotulo = esperado, alcance, rotulo

    def __repr__(self):
        return f'{self.operacao} {self.papel} {self.situacao} {self.rotulo} -> {self.esperado}'


def esperado_por_caso(papel, celula, situacao):
    """The rule of section 5.1: what a cell means in each situation."""
    if celula == autorizacao.NEGADO:
        return 'papel'
    if situacao == 'X' or (situacao == 'N' and papel != 'dono'):
        return 'alcance'
    if celula == 'resp' and papel != 'dono' and situacao != 'P':
        return 'papel'
    return 'passa'


def esperado_por_conversa(papel, celula, situacao, autor):
    """`autor`: None for a conversation of the team, else the role of the reader or guest who opened it."""
    base = esperado_por_caso(papel, celula if celula in ('sim', autorizacao.NEGADO) else 'sim', situacao)
    if base != 'passa' or celula == 'sim':
        return base
    propria = autor == papel
    if celula == 'autor':
        return 'passa' if propria else 'objeto'
    if autor is None or propria:
        return 'passa'
    return 'passa' if celula == 'equipe ou resp' and situacao == 'P' and papel == 'reporter' else 'objeto'


class CelulasTest(cenario.DuasRedacoes):
    """Every cell of the matrix as a request, for the five roles of Redação Alfa."""

    def pedidos(self, papel):
        lista = []
        for chave, regra in sorted({**autorizacao.MATRIZ, **autorizacao.TRANSITORIAS}.items()):
            operacao, celula = chave.split('#')[0], regra.celulas[papel]
            if operacao in FORA_DA_TABELA:
                continue
            base = {'novo': True} if 'novo' in regra.resolvedor else {}
            if chave.startswith('GET:'):
                if 'lote' in regra.resolvedor:
                    lista.append(Pedido(chave, papel, '-', None, esperado_por_caso(papel, celula, 'P'), rotulo='sem parâmetro'))
                    for situacao, caso in cenario.SITUACOES[papel].items():
                        lista.append(Pedido(chave, papel, situacao, {'caso': caso}, esperado_por_caso(papel, celula, situacao), 'caso'))
                else:
                    lista.append(Pedido(chave, papel, '-', None, esperado_por_caso(papel, celula, 'P')))
            elif 'conversa' in regra.resolvedor and operacao != 'excluir':
                for situacao, caso in cenario.SITUACOES[papel].items():
                    for autor in (None, 'leitor', 'convidado'):
                        conversa = self.conversas.get(('equipe' if autor is None else autor, caso))
                        if conversa is None:
                            continue
                        corpo = {'conversa': conversa, **({'caso': caso} if 'caso' in regra.resolvedor else {})}
                        lista.append(Pedido(operacao, papel, situacao, corpo,
                                            esperado_por_conversa(papel, celula, situacao, autor),
                                            'caso' if 'caso' in regra.resolvedor else 'conversa',
                                            f'conversa de {autor or "equipe"}'))
            elif 'item' in regra.resolvedor:
                for situacao, caso in cenario.SITUACOES[papel].items():
                    lista.append(Pedido(operacao, papel, situacao, {'item': self.item_na_lixeira(caso)},
                                        esperado_por_caso(papel, celula, situacao), 'item'))
            elif 'caso' in regra.resolvedor:
                for situacao, caso in cenario.SITUACOES[papel].items():
                    lista.append(Pedido(operacao, papel, situacao, {**base, 'caso': caso},
                                        esperado_por_caso(papel, celula, situacao), 'caso'))
                if 'nenhum' in regra.resolvedor:
                    lista.append(Pedido(operacao, papel, '-', {}, esperado_por_caso(papel, celula, 'P'), rotulo='sem caso'))
            else:
                lista.append(Pedido(operacao, papel, '-', base, esperado_por_caso(papel, celula, 'P')))
        return lista

    def enviar(self, pedido):
        if pedido.operacao.startswith('GET:'):
            caminho = pedido.operacao[4:] + (f'?caso={pedido.corpo["caso"]}' if pedido.corpo else '')
            return self.get(pedido.papel, caminho)
        return self.post(pedido.papel, pedido.operacao, pedido.corpo)

    def conferir(self, pedido, inexistente):
        status, corpo, bruto = self.enviar(pedido)
        codigo = corpo.get('codigo')
        if pedido.esperado == 'papel':
            self.assertEqual((status, codigo, corpo.get('estado')), (403, 'operacao_proibida', 'proibido'), bruto[:200])
        elif pedido.esperado == 'objeto':
            self.assertEqual((status, codigo), (400, 'conversa_indisponivel'), bruto[:200])
        elif pedido.esperado == 'alcance':
            if pedido.alcance == 'caso':
                self.assertEqual((status, bruto), (404, inexistente['caso']), bruto[:200])
            elif pedido.alcance == 'conversa':
                self.assertEqual((status, bruto), inexistente['conversa'], bruto[:200])
            else:  # an item of the trash out of reach: the answer to an item that does not exist, byte for byte
                self.assertEqual((status, bruto), inexistente[pedido.operacao], bruto[:200])
        else:
            self.assertNotIn(status, (401, 403, 404, 500, 503), bruto[:200])
            self.assertNotIn(codigo, ('caso_indisponivel', 'conversa_indisponivel', 'operacao_proibida'), bruto[:200])
            self.assertNotIn('não liberada', str(corpo.get('erro')))
            if pedido.alcance == 'item':
                self.assertNotEqual((status, bruto), inexistente[pedido.operacao], 'respondeu como item inexistente')
        if pedido.esperado != 'passa' or pedido.situacao == 'X':
            self.sem_sentinela(bruto, repr(pedido))

    def respostas_do_inexistente(self, papel):
        """What this account gets for what does not exist: the yardstick for everything out of its reach."""
        caso = self.post(papel, 'codex-listar', {'caso': 'apuracao_' + 'f' * 32})[2]
        conversa = self.post(papel, 'codex-eventos', {'conversa': 'f' * 32})
        itens = {operacao: (lambda r: (r[0], r[2]))(self.post(papel, operacao, {'item': 'f' * 32}))
                 for operacao in ('restaurar', 'lixeira-alcance', 'lixeira-apagar')}
        return {'caso': caso, 'conversa': (conversa[0], conversa[2]), **itens}

    def test_cada_celula_da_matriz_para_os_cinco_papeis(self):
        total, celulas = 0, set()
        for papel in autorizacao.PAPEIS:
            inexistente = self.respostas_do_inexistente(papel)
            pedidos = self.pedidos(papel)
            recusados = [p for p in pedidos if p.esperado != 'passa']
            antes = self.retrato()
            for pedido in recusados:
                with self.subTest(pedido=repr(pedido)):
                    self.conferir(pedido, inexistente)
            self.assertEqual(antes, self.retrato(), f'um pedido recusado de {papel} mudou dados ou contas')
            for pedido in pedidos:
                if pedido.esperado == 'passa':
                    with self.subTest(pedido=repr(pedido)):
                        self.conferir(pedido, inexistente)
            total += len(pedidos)
            celulas |= {(p.operacao, papel) for p in pedidos}
        operacoes = {c.split('#')[0] for c in {**autorizacao.MATRIZ, **autorizacao.TRANSITORIAS}} - set(FORA_DA_TABELA)
        self.assertEqual({o for o, _ in celulas}, operacoes)
        self.assertEqual(len(celulas), len(operacoes) * len(autorizacao.PAPEIS))
        self.assertGreater(total, 1500)

    def test_em_outra_redacao_nenhum_papel_passa_em_nenhuma_linha(self):
        for papel in autorizacao.PAPEIS:
            for pedido in self.pedidos(papel):
                if pedido.situacao == 'X':
                    self.assertIn(pedido.esperado, ('alcance', 'papel'), repr(pedido))

    def test_sair_encerra_so_a_propria_sessao_em_todos_os_papeis(self):
        for papel, login in (('dono', 'dona.alfa'), ('editor', 'edu.editor'), ('reporter', 'rita.reporter'),
                             ('leitor', 'leo.leitor'), ('convidado', 'cora.convidada')):
            with self.subTest(papel=papel):
                descartavel = self._entrar(login)
                self.assertEqual(self.post(descartavel, 'sessao-sair', {})[0], 200)
                self.assertEqual(self.post(descartavel, 'codex-status', {})[0], 401)
                self.assertEqual(self.post(papel, 'codex-status', {})[0], 200)  # the other session of the account goes on

    def test_servico_hospedado_nao_se_encerra_por_nenhum_papel(self):
        for papel in autorizacao.PAPEIS:
            status, corpo, _ = self.post(papel, 'codex-desligar', {})
            self.assertEqual((status, corpo.get('codigo')), (403, 'servico_nao_encerravel'), papel)

    def test_chave_do_servico_nao_se_troca_pela_mesa_com_mais_de_uma_redacao(self):
        for papel in autorizacao.PAPEIS:
            status, corpo, _ = self.post(papel, 'ia-config-salvar', {'provedor': 'anthropic'})
            self.assertEqual((status, corpo.get('codigo')), (403, 'operacao_proibida'), papel)
        self.assertNotIn(self.post('dono', 'ia-config', {})[0], (401, 403, 404))
        # And what a newsroom reads of the service's key: that it exists, never its last characters.
        resposta = {'provedor': 'anthropic', 'chaves': {'anthropic': {'configurada': True, 'origem': 'ambiente', 'final': 'abcd'},
                                                        'openai': {'configurada': False, 'origem': None, 'final': None}}}
        principal = {'papel': 'dono', 'casos': []}
        self.assertEqual(autorizacao.filtrar(self.root, 'piloto', principal, 'ia-config', resposta)['chaves'], {
            'anthropic': {'configurada': True, 'origem': 'servico', 'final': None},
            'openai': {'configurada': False, 'origem': None, 'final': None}})
        self.assertEqual(autorizacao.filtrar(self.root, 'local', principal, 'ia-config', resposta), resposta)

    def test_contas_criar_e_recusada_a_todos_com_mais_de_uma_redacao_e_so_ai(self):
        for papel in autorizacao.PAPEIS:
            status, corpo, _ = self.post(papel, 'contas-criar', {'nome': 'Pessoa', 'login': 'pessoa.nova', 'papel': 'leitor'})
            self.assertEqual((status, corpo.get('codigo')), (403, 'operacao_proibida'), papel)
        principal = acesso.sessao(self.root, self.sessoes['dono'][0].split('=', 1)[1])
        with patch.object(acesso, 'total_redacoes', return_value=1):  # one newsroom: its logins are all its own
            self.assertEqual(autorizacao.conferir(self.root, 'piloto', principal, 'contas-criar', {}).operacao, 'contas-criar')
        for operacao in ('contas-listar', 'contas-atualizar', 'contas-desativar', 'contas-reativar', 'contas-recuperar'):
            self.assertEqual(autorizacao.conferir(self.root, 'piloto', principal, operacao, {}).operacao, operacao)

    def test_sessao_devolve_papel_redacao_alcance_explicito_e_capacidades(self):
        for papel, casos in (('dono', ['alpha', 'delta', 'gama']), ('editor', ['alpha']), ('reporter', ['alpha', 'gama']),
                             ('leitor', ['alpha']), ('convidado', ['alpha'])):
            with self.subTest(papel=papel):
                status, corpo, bruto = self.get(papel, '/api/sessao')
                self.assertEqual(status, 200)
                self.assertEqual((corpo['conta']['papel'], corpo['conta']['casos'], corpo['organizacao']),
                                 (papel, casos, {'id': self.a, 'nome': 'Redação Alfa'}))
                self.assertEqual(corpo['capacidades'], autorizacao.capacidades({'papel': papel}))
                self.assertEqual(corpo['pendencias'], [])
                self.sem_sentinela(bruto)


if __name__ == '__main__':
    unittest.main()
