"""O portão: o único lugar em que papel, redação e participação são conferidos (contrato de contas, seções 4 e 5).

``MATRIZ`` é dado: uma entrada por operação, com o resolvedor (de onde vem a apuração do pedido), o tipo e a célula de
cada papel. As tabelas 5.2 a 5.13 de ``.maestro/equipe/CONTRATO_CONTAS.md`` são a fonte; ``testes/test_matriz_contas.py``
exige que as duas sejam iguais e faz de cada célula uma requisição. Operação sem entrada aqui não existe.

- ``alcance``: as apurações que uma conta alcança (a conta que está em ``acesso._alcance``, a única que o calcula).
- ``conferir``: a decisão sobre um pedido. Devolve o ``Acesso`` concedido ou levanta ``Recusa`` com a resposta pronta.
  A ordem é a da seção 4.2: redação ativa, pendências, papel, campos, apuração ao alcance, lixeira, regra do objeto.
- ``filtrar``: tira de uma resposta o que está fora do alcance (as listagens que juntam apurações) e o que o papel não
  recebe (texto bruto de erro e campos internos de conversa, para leitor e convidado).

"Não existe" e "não é seu" têm a mesma resposta, byte a byte: apuração inexistente, de outra redação, sem participação,
sem posse ou com id malformado dão sempre ``caso_indisponivel``. A causa verdadeira vai só no ``motivo`` da recusa, que
o servidor grava no registro de auditoria e nunca devolve.

No modo ``local`` (um operador, sem contas) nada disto se aplica: não há redação nem posse, e o operador alcança tudo.
Nos modos com contas ninguém tem "todas as apurações": ``principal['casos']`` é sempre a lista explícita.
Sem modelo e sem rede. Os módulos de rota não leem o papel: perguntam aqui.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import NamedTuple
import uuid

import acesso
from comum import ler_json
import lixeira

PAPEIS = acesso.PAPEIS  # dono, editor, reporter, leitor, convidado (as colunas D, E, R, L, C do contrato)
# Leitor e convidado legado: conversas próprias, só os campos da pergunta, sem texto bruto de erro.
RESTRITOS = ('leitor', 'convidado')
NEGADO = '—'
CELULAS = ('sim', 'resp', 'autor', 'equipe', 'equipe ou resp', NEGADO)
RESOLVEDORES = ('caso', 'conversa', 'item', 'lote', 'novo', 'nenhum')
TIPOS = ('L', 'B', 'E', 'IA', 'A')  # lê, baixa arquivo, escreve, chama o modelo, administra
CASO_INDISPONIVEL = 'Apuração indisponível para esta conta.'
CONVERSA_INDISPONIVEL = 'Conversa indisponível para este acesso.'
PROIBIDA = 'Operação não permitida para esta conta.'
LOTE_INEXISTENTE = 'Lote não encontrado na fila.'
# Sobre apuração que está na lixeira só passam estas (seção 4.6).
DE_LIXEIRA = frozenset({'gerenciar-listar', 'restaurar', 'lixeira-alcance', 'lixeira-apagar'})
# O que leitor e convidado enviam (os demais campos são do trabalho de mesa).
CAMPOS_RESTRITOS = {'codex-perguntar': {'caso', 'pergunta', 'conversa'}, 'codex-retomar': {'conversa'}}
MENSAGEM_CAMPOS = {'codex-perguntar': 'Esta conta envia somente a pergunta e a conversa.',
                   'codex-retomar': 'Esta conta envia somente a conversa a retomar.'}
# O que uma conta com pendência ainda alcança (seção 4.2): a própria sessão e o que resolve cada pendência.
SEM_PENDENCIA = frozenset({'sessao-sair', 'GET:/api/sessao'})
RESOLVE_PENDENCIA = {'segundo_fator': frozenset({'conta-ver', 'conta-fator-iniciar', 'conta-fator-confirmar'}),
                     'termos': frozenset({'conta-ver', 'conta-termos-aceitar'})}
# As saídas que uma pendência deixa abertas sem resolvê-la: quem não aceita os termos novos ainda leva os próprios
# dados e sai do serviço (ressalva B2). Uma saída só passa se TODAS as pendências da conta a deixam: com o segundo
# fator pendente, nenhuma (ressalva R1 da revisão da 4b-1: a liberação de uma pendência nunca abre o que outra fecha).
SAIDAS_DA_PENDENCIA = {'termos': frozenset({'conta-exportar', 'conta-excluir'}), 'segundo_fator': frozenset()}
# A página que resolve cada pendência: com ela, `GET /` responde 303 para cá (da família do Entrar, sem dado de conta).
PAGINA_DA_PENDENCIA = {'termos': '/conta/termos', 'segundo_fator': '/conta/segundo-fator'}
FATOR_OBRIGATORIO = 'O segundo fator é obrigatório para o seu papel neste serviço e não pode ser removido.'
ID_CONVERSA = re.compile(lixeira.ID_CONVERSA)


class Regra(NamedTuple):
    resolvedor: frozenset
    tipo: str
    celulas: dict


class Acesso(NamedTuple):
    """O que o portão concedeu. ``dados`` é o corpo a usar daqui em diante (pode diferir do recebido: ver ``item``)."""
    operacao: str
    dados: dict
    caso: str | None = None
    restrito: bool = False      # leitor ou convidado: só a tela da pergunta, respostas sem texto bruto de erro
    dono: str | None = None     # o ``dono`` que a conversa recebe: a conta, quando ela só alcança conversas próprias
    novo: bool = False          # a operação cria uma apuração: o servidor gera o id e registra a posse
    item: dict | None = None    # item da lixeira resolvido


class Recusa(Exception):
    """A resposta de uma recusa. ``motivo`` e ``codigo`` vão para a auditoria; só ``corpo`` vai ao navegador."""

    def __init__(self, status: int, corpo: dict, codigo: str, motivo: str | None = None):
        super().__init__(corpo.get('erro', codigo))
        self.status, self.corpo, self.codigo, self.motivo = status, corpo, codigo, motivo


def _linhas(destino: dict, resolvedor: str, tipo: str, celulas: str, operacoes: str) -> None:
    valores = [c.strip() for c in celulas.split('|')]
    assert len(valores) == len(PAPEIS) and all(v in CELULAS for v in valores) and tipo in TIPOS, operacoes
    regra = Regra(frozenset(resolvedor.split('+')), tipo, dict(zip(PAPEIS, valores)))
    assert regra.resolvedor <= set(RESOLVEDORES), operacoes
    for operacao in operacoes.split():
        assert operacao not in destino, operacao
        destino[operacao] = regra


TODOS, MESA, LEITURA = 'sim|sim|sim|sim|sim', 'sim|sim|sim|—|—', 'sim|sim|sim|sim|—'
SO_DONO, DONO_E_REPORTER = 'sim|—|—|—|—', 'sim|—|sim|—|—'
MATRIZ: dict[str, Regra] = {}
# 5.2 Páginas e leituras por GET (as rotas públicas não têm papel e não passam por aqui).
_linhas(MATRIZ, 'nenhum', 'L', TODOS, 'GET:/ GET:/api/sessao GET:/api/integracao GET:/api/catalogo GET:/api/cota')
_linhas(MATRIZ, 'lote+caso+nenhum', 'L', TODOS, 'GET:/api/fila')
# 5.4 A própria conta.
_linhas(MATRIZ, 'nenhum', 'A', TODOS, 'sessao-sair conta-senha-trocar conta-sessao-encerrar conta-sessoes-encerrar-outras '
                                      'conta-email-trocar conta-fator-iniciar conta-fator-confirmar conta-fator-codigos '
                                      'conta-fator-remover conta-termos-aceitar')  # remover: negado onde o fator é
# obrigatório; aceitar os termos: só onde eles existem, o `piloto` (as duas em `_recusa_do_modo`)
_linhas(MATRIZ, 'nenhum', 'L', TODOS, 'conta-ver conta-sessoes')
_linhas(MATRIZ, 'nenhum', 'B', TODOS, 'conta-exportar')
_linhas(MATRIZ, 'nenhum', 'A', TODOS, 'conta-excluir')
_linhas(MATRIZ, 'nenhum', 'E', TODOS, 'conta-atualizar')
# 5.5 A redação.
_linhas(MATRIZ, 'nenhum', 'L', SO_DONO, 'ia-config equipe-listar equipe-atividade')
_linhas(MATRIZ, 'nenhum', 'A', SO_DONO, 'ia-config-salvar codex-desligar equipe-papel equipe-desativar equipe-reativar '
                                        'equipe-remover equipe-teto equipe-convidar equipe-convite-reenviar '
                                        'equipe-convite-cancelar equipe-recuperar equipe-recuperar-confirmar')
_linhas(MATRIZ, 'nenhum', 'L', DONO_E_REPORTER, 'ambiente')
_linhas(MATRIZ, 'nenhum', 'L', TODOS, 'codex-status')
# 5.6 Apurações: criação, participação e lixeira.
_linhas(MATRIZ, 'novo', 'E', DONO_E_REPORTER, 'cadastrar#novo')
_linhas(MATRIZ, 'nenhum+caso', 'L', DONO_E_REPORTER, 'gerenciar-listar')
_linhas(MATRIZ, 'caso', 'L', LEITURA, 'caso-participantes')
_linhas(MATRIZ, 'caso', 'A', 'sim|—|resp|—|—', 'caso-incluir caso-retirar')
_linhas(MATRIZ, 'caso', 'A', SO_DONO, 'caso-responsavel')
_linhas(MATRIZ, 'caso+conversa', 'E', 'sim|—|resp|—|—', 'excluir')
_linhas(MATRIZ, 'item', 'E', 'sim|—|resp|—|—', 'restaurar')
_linhas(MATRIZ, 'item', 'L', SO_DONO, 'lixeira-alcance')
_linhas(MATRIZ, 'item', 'A', SO_DONO, 'lixeira-apagar')
# 5.7 Documentos e busca.
_linhas(MATRIZ, 'caso', 'E', DONO_E_REPORTER, 'cadastrar preparar-pdfs')
_linhas(MATRIZ, 'caso', 'L', LEITURA, 'inventario analises buscar ler cobertura fontes-web-listar fontes-web-abrir')
_linhas(MATRIZ, 'caso', 'B', LEITURA, 'original')
_linhas(MATRIZ, 'caso', 'E', SO_DONO, 'fontes-web-capturar')
# 5.8 Conversa com os documentos.
_linhas(MATRIZ, 'caso', 'L', 'sim|sim|sim|sim|autor', 'codex-listar')
_linhas(MATRIZ, 'caso', 'IA', TODOS, 'codex-perguntar')
_linhas(MATRIZ, 'caso+conversa', 'IA', 'equipe|equipe|equipe|autor|autor', 'codex-perguntar#conversa')
_linhas(MATRIZ, 'conversa', 'IA', 'equipe|equipe|equipe|autor|autor', 'codex-retomar')
_linhas(MATRIZ, 'conversa', 'E', 'sim|equipe|equipe ou resp|autor|autor', 'codex-cancelar')
_linhas(MATRIZ, 'conversa', 'L', 'sim|sim|sim|sim|autor', 'codex-eventos')
_linhas(MATRIZ, 'conversa', 'B', 'sim|sim|sim|sim|autor', 'codex-original')
_linhas(MATRIZ, 'caso', 'L', MESA, 'codex-observacoes')
_linhas(MATRIZ, 'caso+conversa', 'L', MESA, 'codex-corpus-previa codex-caderno-previa codex-diligencias-previa')
_linhas(MATRIZ, 'caso+conversa', 'E', 'equipe|—|equipe|—|—', 'codex-documentos-cadastrar')
# 5.9 Achados.
_linhas(MATRIZ, 'caso', 'L', LEITURA, 'achados-catalogo achados-buscar achados-detalhe achados-evidencia achados-briefing')
_linhas(MATRIZ, 'caso', 'B', LEITURA, 'achados-original achados-exportar')
_linhas(MATRIZ, 'caso', 'E', MESA, 'achados-revisao-salvar')
# 5.10 Caderno, notas e diligências.
_linhas(MATRIZ, 'caso', 'L', LEITURA, 'apuracao-listar apuracao-notas apuracao-nota caderno-documentos caderno-listar '
                                      'caderno-detalhe diligencias-listar')
_linhas(MATRIZ, 'caso', 'B', LEITURA, 'apuracao-exportar apuracao-original caderno-exportar caderno-original '
                                      'diligencias-original')
_linhas(MATRIZ, 'caso', 'E', MESA, 'apuracao-salvar apuracao-adicionar apuracao-excluir apuracao-nota-salvar '
                                   'apuracao-nota-inserir apuracao-nota-excluir caderno-salvar caderno-cruzar '
                                   'diligencias-criar diligencias-atualizar diligencias-responder')
# 5.11 Quadros de evidência e tabelas.
_linhas(MATRIZ, 'caso', 'L', LEITURA, 'hipoteses-listar hipoteses-detalhe hipoteses-quadro linha-tempo-listar '
                                      'linha-tempo-detalhe comparar-evidencias comparar-documentos mapa-ver mapa-homonimos '
                                      'tabelas-listar tabelas-detalhe tabelas-historico-celula tabelas-calcular')
_linhas(MATRIZ, 'caso', 'B', LEITURA, 'tabelas-exportar')
_linhas(MATRIZ, 'caso', 'E', MESA, 'hipoteses-criar hipoteses-atualizar linha-tempo-criar linha-tempo-atualizar '
                                   'mapa-entidade-criar mapa-entidade-atualizar mapa-relacao-criar mapa-relacao-atualizar '
                                   'tabelas-criar tabelas-atualizar tabelas-corrigir')
# 5.12 Texto da matéria e entrevistas.
_linhas(MATRIZ, 'caso', 'L', LEITURA, 'redacao-listar redacao-conferir redacao-dividir entrevistas-lacunas '
                                      'entrevistas-listar entrevistas-detalhe')
_linhas(MATRIZ, 'caso', 'B', LEITURA, 'entrevistas-exportar')
_linhas(MATRIZ, 'caso', 'E', MESA, 'redacao-criar redacao-nova-versao redacao-vincular entrevistas-preparar '
                                   'entrevistas-editar entrevistas-responder')
_linhas(MATRIZ, 'caso', 'E', 'sim|sim|—|—|—', 'redacao-revisar')
# 5.13 Rascunhos e retomada.
_linhas(MATRIZ, 'caso', 'E', TODOS, 'rascunhos-salvar rascunhos-ler rascunhos-listar rascunhos-descartar')
_linhas(MATRIZ, 'caso', 'L', MESA, 'continuidade-resumo')

# Operações em retirada: nenhuma. As seis `contas-*` (nota da seção 5.5) saíram com o convite por e-mail (P30) e
# respondem 404 como qualquer operação inexistente; `equipe-*`, `caso-*` e o convite as substituem.
TRANSITORIAS: dict[str, Regra] = {}
RETIRADAS = ('contas-listar', 'contas-criar', 'contas-atualizar', 'contas-desativar', 'contas-reativar', 'contas-recuperar')
# Operações que o contrato já define e que entram nas próximas entregas (segundo fator, ciclo de vida).
PENDENTES: frozenset[str] = frozenset()
# Antes da sessão (seção 5.3): sem papel, conferidas em `rotas_contas._publico`.
PUBLICAS = ('entrar', 'ativar', 'ativacao-consultar', 'primeiro-admin', 'convite-consultar', 'convite-aceitar',
            'senha-esqueci', 'senha-redefinir', 'email-confirmar', 'entrar-segundo-fator')
_REGRAS = {**MATRIZ, **TRANSITORIAS}


def operacoes_com_sessao() -> frozenset:
    """Os nomes de `POST /api/…` que o portão conhece (sem as variantes e sem as rotas GET)."""
    return frozenset(nome.split('#')[0] for nome in _REGRAS if not nome.startswith('GET:'))


def _variante(operacao: str, dados: dict) -> str:
    if operacao == 'cadastrar' and dados.get('novo') is True:
        return 'cadastrar#novo'
    if operacao == 'codex-perguntar' and dados.get('conversa'):
        return 'codex-perguntar#conversa'
    return operacao


def _variantes(operacao: str) -> list[Regra]:
    return [regra for nome, regra in _REGRAS.items() if nome.split('#')[0] == operacao]


def alcance(root: Path, conta: str) -> tuple[frozenset, frozenset]:
    """(apurações que a conta alcança, apurações pelas quais responde). A conta é feita num lugar só: ``acesso``."""
    return acesso.alcance(root, conta)


def restrito(principal: dict | None) -> bool:
    return bool(principal) and principal.get('papel') in RESTRITOS


def ve_redacao(principal: dict) -> bool:
    """Quem vê os números da redação (gasto, cota): o dono; no modo local, o operador."""
    return principal.get('papel') == 'dono'


def gasto_da_redacao(root: Path, modo: str, principal: dict) -> bool:
    """Se o gasto "da organização" que o módulo de custo guarda para esta conta é o da redação dela, e só dela.
    Nenhuma resposta leva número que some redações (seção 4.5). O custo conta por redação (P1 da Plataforma): o bloco
    ``organizacao`` de ``custo.situacao`` é sempre o da redação da conta, nunca o total da instalação; se um dia puder
    trazer o total, esta função tem de voltar a barrar."""
    if modo == 'local':
        return True
    if not ve_redacao(principal):
        return False
    import custo
    redacao = (principal.get('organizacao') or {}).get('id')
    return redacao is not None and custo.redacao_do_gasto(root, principal.get('conta')) == redacao


def papel_para_interface(principal: dict) -> str:
    """O valor de ``data-papel`` da página. Enquanto a interface não conhece os papéis novos, o dono vai como
    ``admin`` (o nome que ela usa para mostrar a administração); os demais vão com o próprio nome."""
    return 'admin' if principal.get('papel') == 'dono' else str(principal.get('papel') or '')


def capacidades(root: Path, modo: str, principal: dict) -> list[str]:
    """As operações que a conta alcança em alguma situação, para a interface esconder o resto (ela nunca decide):
    as da célula do papel, menos as que o modo recusa. A regra por modo é a mesma função que o portão usa
    (``_recusa_do_modo``), de modo que a interface nunca mostra um botão que o servidor recusa por ela."""
    papel = principal.get('papel')
    return sorted({nome.split('#')[0] for nome, regra in _REGRAS.items()
                   if not nome.startswith('GET:') and regra.celulas.get(papel, NEGADO) != NEGADO
                   and _recusa_do_modo(root, modo, papel, nome.split('#')[0]) is None})


def pagina_da_pendencia(recusa: 'Recusa') -> str | None:
    """Para onde `GET /` manda a conta que o portão recusou por pendência: a página que resolve a primeira delas."""
    if recusa.codigo != 'pendencia_de_conta':
        return None
    return next((PAGINA_DA_PENDENCIA[p] for p in recusa.corpo.get('pendencias', ()) if p in PAGINA_DA_PENDENCIA), None)


def _barrada_pela_pendencia(principal: dict, operacao: str) -> bool:
    """A conta com pendência só alcança a própria sessão e o que resolve a pendência (seção 4.2). Um lugar só,
    lido pelo portão e pelo teto do corpo."""
    pendencias = principal.get('pendencias') or ()
    if not pendencias:
        return False
    if operacao in SEM_PENDENCIA.union(*(RESOLVE_PENDENCIA.get(p, ()) for p in pendencias)):
        return False  # what resolves one of them, whatever the others
    return not all(operacao in SAIDAS_DA_PENDENCIA.get(p, ()) for p in pendencias)


def corpo_grande(modo: str, principal: dict, operacao: str) -> bool:
    """Quem não alcança a operação nunca tem um corpo grande lido (seção 4.2, passo 3): nem pelo papel, nem pela
    pendência da conta (ressalva R1 da revisão da obrigação)."""
    if modo == 'local':
        return True
    if _barrada_pela_pendencia(principal, operacao):
        return False
    return any(regra.celulas.get(principal.get('papel'), NEGADO) != NEGADO for regra in _variantes(operacao))


def destino_inicial(conta: dict) -> str:
    """Para onde a página de entrada manda a pessoa: quem só pergunta vai direto à conversa."""
    if conta.get('papel') not in RESTRITOS:
        return '/'
    from urllib.parse import quote
    casos = conta.get('casos') or []
    return '/?area=codex' + (f'&caso={quote(casos[0], safe="")}' if len(casos) == 1 else '')


def conta_publica(principal: dict) -> dict:
    """A conta como `GET /api/sessao` a devolve."""
    return {'id': principal.get('conta'), **{k: principal.get(k) for k in ('nome', 'email', 'login', 'papel', 'casos')}}


def _proibida(mensagem: str = PROIBIDA, codigo: str = 'operacao_proibida', motivo: str = 'papel') -> Recusa:
    return Recusa(403, {'estado': 'proibido', 'erro': mensagem, 'codigo': codigo}, codigo, motivo)


def _motivo(root: Path, principal: dict, caso) -> str:
    """Por que a apuração está fora do alcance. Só para a auditoria: a resposta é a mesma nos três casos."""
    registro = acesso.posse(root, caso if isinstance(caso, str) else '')
    if not registro or registro.get('apagada_em'):
        return 'inexistente'
    return 'sem_participacao' if registro['organizacao'] == (principal.get('organizacao') or {}).get('id') else 'outra_redacao'


def _caso_indisponivel(root: Path, principal: dict, caso) -> Recusa:
    return Recusa(404, {'estado': 'indisponivel', 'codigo': 'caso_indisponivel', 'erro': CASO_INDISPONIVEL},
                  'caso_indisponivel', _motivo(root, principal, caso))


def _conversa_indisponivel(root: Path, principal: dict, caso=None, motivo: str | None = None) -> Recusa:
    # Sem ``codigo`` no corpo: o servidor o acrescenta pela mensagem, como faz com a recusa do próprio módulo.
    return Recusa(400, {'estado': 'erro', 'erro': CONVERSA_INDISPONIVEL}, 'conversa_indisponivel',
                  motivo or _motivo(root, principal, caso))


def _conversa(root: Path, identificador) -> dict | None:
    """Identidade de uma conversa (apuração e autor restrito), ou None. Só metadados; nenhum conteúdo."""
    if not isinstance(identificador, str) or not ID_CONVERSA.fullmatch(identificador):
        return None
    try:
        meta = ler_json(Path(root) / 'conversas' / identificador / 'conversa.json')
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get('id') != identificador or not isinstance(meta.get('caso'), str):
        return None
    return {'caso': meta['caso'], 'dono': meta.get('dono')}


def _item_da_lixeira(root: Path, identificador) -> dict | None:
    try:
        return next((item for item in lixeira.ativos(root) if item.get('id') == identificador), None)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _lote(root: Path, lote) -> str | None:
    """A apuração de um lote da fila. Lote inexistente ou malformado: a mensagem do próprio módulo."""
    import fila_extracao
    try:
        return fila_extracao.consultar(root, lote=lote)['lote'].get('caso')
    except ValueError as exc:
        raise Recusa(400, {'erro': str(exc)}, 'lote_inexistente', 'inexistente') from exc


def _recusa_do_modo(root: Path, modo: str, papel, operacao: str) -> Recusa | None:
    """O que o modo recusa a quem a célula do papel deixaria passar (as observações das tabelas 5.4 e 5.5). Um
    lugar só, lido pelo portão e por ``capacidades``."""
    if modo == 'local':
        return _proibida('Contas só existem nos modos com login.') if operacao.startswith(('caso-', 'conta-', 'equipe-')) else None
    if modo != 'piloto':
        if operacao == 'conta-termos-aceitar':  # a Mesa instalada não tem termos de serviço (seção 12, entrega 4b-1)
            return _proibida('Esta instalação não tem termos de uso a aceitar.')
        return None
    if operacao == 'codex-desligar':
        return _proibida('O serviço hospedado não pode ser encerrado pela interface.', 'servico_nao_encerravel')
    if operacao == 'conta-fator-remover' and papel in acesso.FATOR_OBRIGATORIO:
        return _proibida(FATOR_OBRIGATORIO)  # onde o fator é obrigatório, quem é obrigado não o remove (seção 8.2)
    return None


def conferir(root: Path, modo: str, principal: dict, operacao: str, dados: dict) -> Acesso:
    """Decide um pedido. Levanta ``Recusa`` (a resposta pronta) ou ``ValueError`` (apuração na lixeira, com a
    mensagem de sempre). Não grava nada: quem registra a posse de uma apuração nova é ``registrar_novo``."""
    root = Path(root)
    if modo == 'local' or operacao == 'codex-desligar':
        # O modo local não tem contas; e encerrar o serviço hospedado é recusado a todo papel com a mesma resposta,
        # antes de olhar a conta (observação da tabela 5.5).
        recusa = _recusa_do_modo(root, modo, None, operacao)
        if recusa:
            raise recusa
    if modo == 'local':
        return Acesso(operacao, dados, dados.get('caso') if isinstance(dados.get('caso'), str) else None)
    casos, papel, conta = principal.get('casos'), principal.get('papel'), principal.get('conta')
    if casos is None or papel not in PAPEIS or not conta:
        # Fora do modo local ninguém tem "todas as apurações": um principal assim é defeito, e não passa.
        raise Recusa(503, {'estado': 'indisponivel', 'erro': 'Registro de acesso indisponível. Avise a administração.'},
                     'acesso_indisponivel', 'erro')
    casos, responde = set(casos), set(principal.get('responsavel_de') or ())
    if (principal.get('organizacao') or {}).get('situacao') != 'ativa' and operacao != 'sessao-sair':
        raise _proibida('A redação desta conta está suspensa. Fale com quem administra o serviço.', 'redacao_suspensa',
                        'redacao_suspensa')
    pendencias = principal.get('pendencias') or ()
    if _barrada_pela_pendencia(principal, operacao):
        raise Recusa(403, {'estado': 'proibido', 'codigo': 'pendencia_de_conta', 'pendencias': list(pendencias),
                           'erro': 'Conclua o que falta na sua conta antes de continuar.'}, 'pendencia_de_conta', 'papel')
    regra = _REGRAS.get(_variante(operacao, dados))
    if regra is None:
        raise Recusa(404, {'erro': 'Operação não encontrada.'}, 'operacao_inexistente', 'inexistente')
    celula = regra.celulas[papel]
    if celula == NEGADO:
        raise _proibida()
    recusa = _recusa_do_modo(root, modo, papel, operacao)  # o papel passa, e o modo não
    if recusa:
        raise recusa
    if papel in RESTRITOS and operacao in CAMPOS_RESTRITOS and set(dados) - CAMPOS_RESTRITOS[operacao]:
        raise _proibida(MENSAGEM_CAMPOS[operacao], 'campos_nao_permitidos')
    novo = 'novo' in regra.resolvedor
    if novo and dados.get('caso') is not None:
        raise _proibida('O identificador de uma apuração nova é escolhido pelo servidor.', 'campos_nao_permitidos')
    caso, conversa, item, saida = None, None, None, dados
    if 'caso' in regra.resolvedor and not ('nenhum' in regra.resolvedor and dados.get('caso') is None):
        caso = dados.get('caso')
        if not isinstance(caso, str) or not acesso.ID_CASO.fullmatch(caso) or caso not in casos:
            raise _caso_indisponivel(root, principal, caso)
    if 'conversa' in regra.resolvedor and _pede_conversa(operacao, dados):
        conversa = _conversa(root, dados.get('conversa'))
        if conversa is None or conversa['caso'] not in casos:
            raise _conversa_indisponivel(root, principal, conversa['caso'] if conversa else None)
        if caso is not None and conversa['caso'] != caso:
            raise _conversa_indisponivel(root, principal, motivo='inexistente')
        caso = conversa['caso']
    if 'item' in regra.resolvedor and isinstance(dados.get('item'), str):
        item = _item_da_lixeira(root, dados['item'])
        if item is None or item.get('caso') not in casos:
            # Fora do alcance: o módulo responde como responde a um item que não existe, porque é isso que recebe.
            item, saida = None, {**dados, 'item': uuid.uuid4().hex}
        else:
            caso = item['caso']
    if 'lote' in regra.resolvedor:
        if dados.get('lote') is not None:
            caso_do_lote = _lote(root, dados['lote'])
            if caso_do_lote not in casos:
                raise Recusa(400, {'erro': LOTE_INEXISTENTE}, 'lote_inexistente', _motivo(root, principal, caso_do_lote))
            caso = caso_do_lote
        elif dados.get('caso') is not None:
            caso = dados['caso']
            if not isinstance(caso, str) or caso not in casos:
                raise _caso_indisponivel(root, principal, caso)
    if caso is not None and operacao not in DE_LIXEIRA:
        lixeira.conferir_disponivel(root, caso)  # ValueError com a mensagem de item na lixeira (seção 4.6)
    if celula == 'resp' and papel != 'dono' and caso is not None and caso not in responde:
        raise _proibida()
    if conversa is not None and celula in ('autor', 'equipe', 'equipe ou resp'):
        propria = conversa['dono'] == conta
        da_equipe = conversa['dono'] is None
        passa = propria or (celula != 'autor' and da_equipe) or (celula == 'equipe ou resp' and caso in responde)
        if not passa:
            raise _conversa_indisponivel(root, principal, motivo='papel')
    # A conversa recebe ``dono`` quando a conta só alcança as próprias: o convidado sempre; o leitor ao escrever
    # (as conversas dele nascem com autor restrito), mas não ao ler, porque ele lê todas as da apuração.
    dono = conta if papel == 'convidado' or (papel == 'leitor' and regra.tipo in ('IA', 'E')) else None
    return Acesso(operacao, saida, caso, papel in RESTRITOS, dono, novo, item)


def _pede_conversa(operacao: str, dados: dict) -> bool:
    """A conversa é opcional em duas prévias e, em `excluir`, só vale quando o item é uma conversa."""
    if operacao == 'excluir':
        return dados.get('tipo') == 'conversa'
    if operacao in ('codex-caderno-previa', 'codex-diligencias-previa'):
        return bool(dados.get('conversa'))
    return True


def registrar_novo(root: Path, principal: dict, dados: dict) -> dict:
    """Apuração nova: o servidor escolhe o id e registra posse, responsável e participação de quem cria."""
    caso = 'apuracao_' + uuid.uuid4().hex
    acesso.registrar_caso(root, caso, principal['conta'])
    return {**dados, 'caso': caso}


def desfazer_novo(root: Path, caso: str) -> None:
    """A criação foi recusada: sem pasta e sem lote na fila, a posse registrada há pouco não fica sobrando."""
    import fila_extracao
    try:
        if not (Path(root) / 'casos' / caso).is_dir() and not fila_extracao.pendentes(root, caso):
            acesso.descartar_caso_sem_arquivos(root, caso)
    except (OSError, ValueError):
        pass


def filtrar(root: Path, modo: str, principal: dict, operacao: str, resposta):
    """Tira de uma resposta o que quem pede não alcança. As listagens que juntam apurações passam todas por aqui."""
    if modo == 'local' or not isinstance(resposta, dict):
        return resposta
    casos = set(principal.get('casos') or ())
    if operacao == 'GET:/api/catalogo':
        return {**resposta, 'casos': [c for c in resposta.get('casos', []) if c.get('id') in casos]}
    if operacao == 'gerenciar-listar':
        return {**resposta, 'casos': [c for c in resposta.get('casos', []) if c.get('id') in casos],
                'lixeira': [i for i in resposta.get('lixeira', []) if i.get('caso') in casos]}
    if operacao == 'GET:/api/fila':
        lotes = [dict(lote) for lote in ([resposta['lote']] if 'lote' in resposta else resposta.get('lotes', []))
                 if lote.get('caso') in casos]
        for lote in lotes:  # o recibo vai sem o caminho do arquivo no servidor
            if isinstance(lote.get('recibo'), dict):
                lote['recibo'] = {k: v for k, v in lote['recibo'].items() if k != 'arquivo_recibo'}
        if 'lote' in resposta:
            if not lotes:
                raise Recusa(400, {'erro': LOTE_INEXISTENTE}, 'lote_inexistente', 'inexistente')
            return {**resposta, 'lote': lotes[0]}
        return {**resposta, 'lotes': lotes}
    if operacao == 'ambiente' and modo == 'piloto':
        return {k: v for k, v in resposta.items() if k != 'python'}
    if operacao in ('ia-config', 'ia-config-salvar') and modo == 'piloto':
        # A rota já devolve só a chave da própria redação (`rotas_gestao.resumo_da_redacao`). Aqui fica a segunda
        # trava: nada que tenha origem na chave do serviço sai com os quatro últimos caracteres.
        chaves = {provedor: chave if chave.get('origem') == 'redacao' else
                  {'configurada': bool(chave.get('configurada')), 'final': None,
                   'origem': 'servico' if chave.get('configurada') else None}
                  for provedor, chave in (resposta.get('chaves') or {}).items() if isinstance(chave, dict)}
        return {**resposta, 'chaves': chaves}
    if principal.get('papel') == 'leitor' and operacao in ('codex-listar', 'codex-eventos'):
        # O leitor lê todas as conversas da apuração (sem ``dono``), então é aqui que a resposta dele é curada;
        # a do convidado, que só lê as próprias, já sai curada do gerenciador de conversas.
        return _conversa_para_restrito(operacao, resposta)
    return resposta


def _conversa_para_restrito(operacao: str, resposta: dict) -> dict:
    """Leitor e convidado nunca leem o texto bruto de um erro nem os campos internos da conversa (SEG-06)."""
    from codex_apuracao import evento_para_convidado, situacao_para_convidado
    from rotas_conversa import CAMPOS_INTERNOS_CONVERSA
    if operacao == 'codex-listar':
        return {**resposta, 'conversas': [{**c, 'situacao': situacao_para_convidado(c.get('situacao'))}
                                          for c in resposta.get('conversas', [])]}
    conversa = resposta.get('conversa')
    if isinstance(conversa, dict):
        conversa = {k: v for k, v in conversa.items() if k not in CAMPOS_INTERNOS_CONVERSA}
        conversa['situacao'] = situacao_para_convidado(conversa.get('situacao'))
    return {**resposta, 'conversa': conversa,
            'eventos': [evento_para_convidado(e) for e in resposta.get('eventos', [])]}
