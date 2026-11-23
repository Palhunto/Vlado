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
    'conta-fator-remover': 'no piloto o segundo fator é obrigatório para dono e editor, que não o removem (observação '
                           'da linha); no local-contas, onde é opcional, a célula vale para todos',
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
        self.assertEqual(self.publicas - set(autorizacao.PENDENTES), set(autorizacao.PUBLICAS))
        self.assertEqual(self.publicas - self.novas, {'entrar', 'ativar', 'ativacao-consultar', 'primeiro-admin'})
        self.assertEqual({c for c in autorizacao.MATRIZ if c.startswith('GET:')},
                         {'GET:/', 'GET:/api/sessao', 'GET:/api/integracao', 'GET:/api/catalogo', 'GET:/api/fila', 'GET:/api/cota'})

    def test_operacoes_retiradas_do_contrato_sairam_da_matriz_e_do_servidor(self):
        texto = CONTRATO.read_text(encoding='utf-8')
        nota = texto[texto.index('**Operações retiradas:**'):].split('\n', 1)[0]
        retiradas = {nome for nome, _ in NOME.findall(nota) if nome.startswith('contas-')}
        self.assertEqual(retiradas, set(autorizacao.RETIRADAS))
        self.assertEqual(len(retiradas), 6)
        self.assertEqual(autorizacao.TRANSITORIAS, {})  # nothing is in withdrawal any more: they left with the invitation (P30)
        self.assertFalse(retiradas & (set(autorizacao.MATRIZ) | set(interface_pesquisa.OPERACOES_API) | set(autorizacao.PENDENTES)))

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
        def de(papel):  # the mode with accounts that refuses nothing of its own: the cells alone
            return autorizacao.capacidades(None, 'local-contas', {'papel': papel})
        self.assertIn('redacao-revisar', de('editor'))
        self.assertNotIn('redacao-revisar', de('reporter'))
        self.assertNotIn('cadastrar', de('editor'))
        self.assertEqual(set(de('convidado')), set(interface_pesquisa.OPERACOES_CONVIDADO) | set(interface_pesquisa.CONTA_PROPRIA))
        self.assertIn('equipe-papel', de('dono'))
        for papel in ('editor', 'reporter', 'leitor', 'convidado'):
            self.assertFalse([o for o in de(papel) if o.startswith('equipe-')], papel)
        # The single operator of the local mode has no accounts: nothing of them is offered to the interface.
        local = autorizacao.capacidades(None, 'local', {'papel': 'dono'})
        self.assertFalse([o for o in local if o.startswith(('conta-', 'equipe-', 'caso-'))])
        self.assertIn('codex-desligar', local)


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
            # The gate let it through. A sensitive operation may still ask the password of who does it, or the
            # code of the second factor: that is not a refusal of the role, and each has its own code.
            self.assertNotIn(status, (401, 404, 500, 503), bruto[:200])
            self.assertTrue(status != 403 or codigo in ('senha_necessaria', 'fator_necessario'), bruto[:200])
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

    def test_no_piloto_a_mesa_so_toca_a_chave_da_propria_redacao(self):
        # The cell is the table's (dono only). What the hosted mode adds is in the route: the dono saves the key of
        # the own newsroom, never the service's (test_chave_da_redacao); and a caller without a newsroom gets
        # neither, it fails closed. Here, the second lock: nothing that comes from the service's key leaves with its
        # last characters, whatever the route answered.
        resposta = {'provedor': 'anthropic', 'chaves': {'anthropic': {'configurada': True, 'origem': 'ambiente', 'final': 'abcd'},
                                                        'openai': {'configurada': True, 'origem': 'redacao', 'final': 'wxyz'}}}
        principal = {'papel': 'dono', 'casos': []}
        for operacao in ('ia-config', 'ia-config-salvar'):
            self.assertEqual(autorizacao.filtrar(self.root, 'piloto', principal, operacao, resposta)['chaves'], {
                'anthropic': {'configurada': True, 'origem': 'servico', 'final': None},
                'openai': {'configurada': True, 'origem': 'redacao', 'final': 'wxyz'}}, operacao)
            self.assertEqual(autorizacao.filtrar(self.root, 'local', principal, operacao, resposta), resposta)

    def test_remover_o_fator_e_negado_onde_ele_e_obrigatorio_e_so_ali(self):
        antes = self.retrato()
        for papel in autorizacao.PAPEIS:
            status, corpo, _ = self.post(papel, 'conta-fator-remover', {})
            # Who must have it is refused by the gate; the others pass it and are asked the password (5.15).
            esperado = 'operacao_proibida' if papel in acesso.FATOR_OBRIGATORIO else 'senha_necessaria'
            self.assertEqual((status, corpo.get('codigo')), (403, esperado), papel)
        self.assertEqual(antes, self.retrato())
        for papel in autorizacao.PAPEIS:  # in the installed Mesa the factor is optional, and everybody removes it
            principal = acesso.sessao(self.root, self.sessoes[papel][0].split('=', 1)[1])
            concedido = autorizacao.conferir(self.root, 'local-contas', principal, 'conta-fator-remover', {})
            self.assertEqual(concedido.operacao, 'conta-fator-remover', papel)

    def test_capacidades_e_portao_concordam_em_todo_modo_e_papel(self):
        # Condition of the review for the cell above: the interface never gets a capability the gate refuses by a
        # rule of the mode, and never loses one the gate grants. Asked to the gate itself, operation by operation.
        local = {'papel': 'dono', 'conta': None, 'organizacao': None, 'casos': None, 'responsavel_de': None, 'pendencias': []}
        contas = {papel: acesso.sessao(self.root, self.sessoes[papel][0].split('=', 1)[1], obrigar_fator=True)
                  for papel in autorizacao.PAPEIS}
        recusas_de_papel_ou_modo = {(403, 'operacao_proibida'), (403, 'servico_nao_encerravel')}
        conferidas = 0
        for modo, principais in (('local', {'operador': local}), ('local-contas', contas), ('piloto', contas)):
            for quem, principal in principais.items():
                self.assertEqual(principal['pendencias'], [], quem)
                recebidas = set(autorizacao.capacidades(self.root, modo, principal))
                for operacao in sorted(autorizacao.operacoes_com_sessao()):
                    passa = False
                    for dados in ({}, {'novo': True}, {'conversa': 'f' * 32}):  # every variant of the operation
                        try:
                            autorizacao.conferir(self.root, modo, principal, operacao, dados)
                            passa = True
                        except autorizacao.Recusa as recusa:  # out of reach, missing object: not the role nor the mode
                            passa = passa or (recusa.status, recusa.codigo) not in recusas_de_papel_ou_modo
                    self.assertEqual(operacao in recebidas, passa, (modo, quem, operacao))
                    conferidas += 1
        self.assertEqual(conferidas, len(autorizacao.operacoes_com_sessao()) * 11)
        piloto = set(autorizacao.capacidades(self.root, 'piloto', contas['dono']))
        instalada = set(autorizacao.capacidades(self.root, 'local-contas', contas['dono']))
        self.assertEqual(instalada - piloto, {'codex-desligar', 'conta-fator-remover'})
        self.assertEqual(piloto - instalada, set())

    def test_as_contas_antigas_respondem_como_operacao_inexistente_a_todos_os_papeis(self):
        # Withdrawn with the invitation by e-mail (P30): the same 404 of an operation that never existed, to the
        # dono as to anybody, with the body they would send before.
        inexistente = self.post('dono', 'operacao-que-nunca-existiu', {})
        self.assertEqual(inexistente[0], 404)
        antes = self.retrato()
        for papel in autorizacao.PAPEIS:
            for operacao, dados in (('contas-listar', {}), ('contas-criar', {'nome': 'Pessoa', 'login': 'pessoa.nova', 'papel': 'admin'}),
                                    ('contas-atualizar', {'id': self.ids['leitor'], 'papel': 'admin'}),
                                    ('contas-desativar', {'id': self.ids['dono']}), ('contas-reativar', {'id': self.ids['leitor']}),
                                    ('contas-recuperar', {'id': self.ids['leitor']})):
                resposta = self.post(papel, operacao, dados)
                self.assertEqual((resposta[0], resposta[2]), (404, inexistente[2]), (papel, operacao))
        self.assertEqual(antes, self.retrato())
        principal = acesso.sessao(self.root, self.sessoes['dono'][0].split('=', 1)[1])
        with self.assertRaises(autorizacao.Recusa) as recusa:
            autorizacao.conferir(self.root, 'piloto', principal, 'contas-recuperar', {})
        self.assertEqual(recusa.exception.status, 404)

    def test_sessao_devolve_papel_redacao_alcance_explicito_e_capacidades(self):
        for papel, casos in (('dono', ['alpha', 'delta', 'gama']), ('editor', ['alpha']), ('reporter', ['alpha', 'gama']),
                             ('leitor', ['alpha']), ('convidado', ['alpha'])):
            with self.subTest(papel=papel):
                status, corpo, bruto = self.get(papel, '/api/sessao')
                self.assertEqual(status, 200)
                self.assertEqual((corpo['conta']['papel'], corpo['conta']['casos'], corpo['organizacao']),
                                 (papel, casos, {'id': self.a, 'nome': 'Redação Alfa'}))
                self.assertEqual(corpo['capacidades'], autorizacao.capacidades(self.root, 'piloto', {'papel': papel}))
                # What the hosted mode refuses is not offered: the page would show a button that answers 403.
                self.assertNotIn('codex-desligar', corpo['capacidades'], papel)
                self.assertEqual('ia-config-salvar' in corpo['capacidades'], papel == 'dono', papel)
                self.assertEqual('conta-fator-remover' in corpo['capacidades'], papel not in acesso.FATOR_OBRIGATORIO, papel)
                self.assertEqual(corpo['pendencias'], [])  # dono and editor of the scenario have their second factor
                self.sem_sentinela(bruto)


if __name__ == '__main__':
    unittest.main()
