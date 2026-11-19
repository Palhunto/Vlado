"""Rascunhos da Mesa: o texto ainda não confirmado de cada tela, guardado no servidor.

Há um rascunho por conta, apuração e tela (``caderno/<nota>``, ``pergunta``,
``pergunta/<conversa>``, ``revisao/<achado>``...). Cada gravação aumenta a ``versao``
em 1 e só acontece quando o pedido traz a versão que está gravada: a aba que ficou
para trás não sobrescreve o texto da outra. Recebe ``ConflitoRascunho`` com a versão
atual e a interface decide (restaurar, mesclar ou descartar). Reenviar o mesmo conteúdo
depois de perder a resposta não é conflito: devolve o rascunho já gravado.

Descartar apaga o conteúdo e deixa só a marca da versão (``descartado``), para que a
numeração continue crescente e uma aba antiga não ressuscite um rascunho descartado.

Os arquivos ficam em ``casos/<caso>/rascunhos/<conta>/<hash da tela>.json``: vão para a
lixeira junto com a apuração (``lixeira.conferir_disponivel`` recusa o uso enquanto ela
estiver lá) e entram no alcance do apagamento definitivo (``scripts/apagamento.py``,
categoria ``rascunhos``). A gravação é atômica (arquivo temporário + ``os.replace``) sob a
trava entre processos de ``comum.trava_arquivo``; os limites de tamanho vêm de
``scripts/limites.py``. Rascunho nunca guarda chave de API, senha ou token: campos com esses
nomes e valores com forma de chave são recusados antes de gravar. Nada aqui chama modelo
ou rede, e nenhum caminho vem do cliente.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import threading

from cadastrar_documentos import _atomico, _bytes
from comum import dentro, ler_json, trava_arquivo
import limites
import lixeira

FORMATO = 1
# Tela: nome curto e, opcionalmente, o identificador do item aberto nela.
TELA = re.compile(r'[a-z][a-z0-9_-]{0,39}(/[A-Za-z0-9_-]{1,80})?')
CONTA = re.compile(r'[a-z0-9]{1,64}')
CONTA_LOCAL = 'local'  # modo local, sem contas: um único dono
CAMPO = re.compile(r'[a-z][a-z0-9_]{0,39}')
MAXIMO_CAMPOS = 50
# Nomes de campo que nunca entram num rascunho, em qualquer posição do nome.
CAMPOS_PROIBIDOS = re.compile(r'chave|key|senha|password|passwd|token|secret|segredo|credencia|api', re.I)
# Forma das chaves dos provedores aceitos (Anthropic e OpenAI); o texto inteiro do rascunho é conferido.
VALOR_DE_CHAVE = re.compile(r'\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}')
VARIAVEIS_DE_CHAVE = re.compile(r'ANTHROPIC_API_KEY|OPENAI_API_KEY|ANTHROPIC_AUTH_TOKEN')
CAMPOS_PEDIDO = {
    'rascunhos-salvar': {'caso', 'tela', 'versao', 'conteudo'},
    'rascunhos-ler': {'caso', 'tela'},
    'rascunhos-listar': {'caso'},
    'rascunhos-descartar': {'caso', 'tela', 'versao'},
}
OPERACOES = tuple(CAMPOS_PEDIDO)
SALVAR = ('rascunhos-salvar',)
# Contas convidadas só guardam a pergunta em preparo (as demais telas são da redação).
TELAS_CONVIDADO = re.compile(r'pergunta(/[A-Za-z0-9_-]{1,80})?')
MENSAGEM_CONFLITO = 'O rascunho mudou em outra aba ou janela; nada foi gravado. Escolha qual versão manter.'
_TRAVA = threading.Lock()


class ConflitoRascunho(ValueError):
    """A versão enviada não é a gravada; nada foi gravado. ``atual`` é o rascunho que está no servidor."""

    def __init__(self, atual):
        super().__init__(MENSAGEM_CONFLITO)
        self.atual = atual


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conta(conta) -> str:
    """Dono do rascunho: o ID da conta autenticada, ou ``local`` sem contas."""
    if conta is None:
        return CONTA_LOCAL
    identifier = conta.get('id') if isinstance(conta, dict) else None
    if not isinstance(identifier, str) or not CONTA.fullmatch(identifier) or identifier == CONTA_LOCAL:
        raise ValueError('Conta do rascunho inválida.')
    return identifier


def _tela(tela) -> str:
    if not isinstance(tela, str) or not TELA.fullmatch(tela):
        raise ValueError('Tela de rascunho inválida.')
    return tela


def _pasta_caso(root: Path, caso) -> Path:
    """Apuração existente e fora da lixeira (o rascunho segue o caso para a lixeira)."""
    if not isinstance(caso, str) or not re.fullmatch(lixeira.ID_CASO, caso):
        raise ValueError('Selecione uma apuração para o rascunho.')
    lixeira.conferir_disponivel(root, caso)
    if not dentro(root, f'casos/{caso}').is_dir():
        raise ValueError('Apuração não encontrada.')
    return dentro(root, f'casos/{caso}/rascunhos')


def _arquivo(pasta: Path, conta: str, tela: str) -> Path:
    # O nome do arquivo é o hash da tela: maiúsculas, barras e nomes reservados do Windows não importam.
    return pasta / conta / (hashlib.sha256(tela.encode('utf-8')).hexdigest()[:40] + '.json')


def _sem_chave(texto: str) -> None:
    if VALOR_DE_CHAVE.search(texto) or VARIAVEIS_DE_CHAVE.search(texto):
        raise ValueError('Rascunhos não guardam chaves de API, senhas ou tokens. Retire esse trecho e tente de novo.')
    import segredos  # valores lidos ou salvos neste processo (sem abrir o arquivo de chaves)
    if any(valor in texto for valor in segredos.conhecidas()):
        raise ValueError('Rascunhos não guardam chaves de API, senhas ou tokens. Retire esse trecho e tente de novo.')


def _conteudo(conteudo) -> dict:
    """Campos planos (texto, número, verdadeiro/falso ou nulo), com nomes de lista branca."""
    if not isinstance(conteudo, dict) or not conteudo:
        raise ValueError('Rascunho inválido: envie os campos da tela como um objeto.')
    if len(conteudo) > MAXIMO_CAMPOS:
        raise ValueError(f'Rascunho inválido: no máximo {MAXIMO_CAMPOS} campos por tela.')
    resultado = {}
    for nome, valor in conteudo.items():
        if not isinstance(nome, str) or not CAMPO.fullmatch(nome):
            raise ValueError('Rascunho inválido: nome de campo fora do padrão.')
        if CAMPOS_PROIBIDOS.search(nome):
            raise ValueError('Rascunhos não guardam chaves de API, senhas ou tokens. Retire esse trecho e tente de novo.')
        if valor is not None and type(valor) not in (str, int, bool, float):
            raise ValueError('Rascunho inválido: cada campo guarda texto, número, verdadeiro/falso ou nulo.')
        if type(valor) is float and not math.isfinite(valor):  # NaN e infinito não são JSON
            raise ValueError('Rascunho inválido: número fora do padrão.')
        if isinstance(valor, str):
            _sem_chave(valor)
        resultado[nome] = valor
    return resultado


def _tamanho(conteudo) -> int:
    return len(json.dumps(conteudo, ensure_ascii=False, sort_keys=True).encode('utf-8')) if conteudo else 0


def _ler(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        dados = ler_json(path)
    except (OSError, ValueError) as exc:
        raise ValueError('Rascunho ilegível no servidor; descarte-o para continuar.') from exc
    if not isinstance(dados, dict) or dados.get('formato') != FORMATO or type(dados.get('versao')) is not int:
        raise ValueError('Rascunho ilegível no servidor; descarte-o para continuar.')
    return dados


def _publico(dados: dict | None, caso: str, tela: str) -> dict:
    """Forma devolvida à interface. Sem rascunho, ``versao`` 0 e ``conteudo`` nulo."""
    if not dados:
        return {'caso': caso, 'tela': tela, 'versao': 0, 'conteudo': None, 'descartado': False,
                'atualizado_em_utc': None, 'bytes': 0}
    return {'caso': caso, 'tela': tela, 'versao': dados['versao'], 'conteudo': dados.get('conteudo'),
            'descartado': bool(dados.get('descartado')), 'atualizado_em_utc': dados.get('atualizado_em_utc'),
            'bytes': dados.get('bytes', 0)}


def _resumo(dados: dict, caso: str) -> dict:
    return {k: v for k, v in _publico(dados, caso, dados['tela']).items() if k != 'conteudo'}


def _todos(pasta: Path):
    """Todos os rascunhos do caso (de todas as contas), para conferir os limites do caso."""
    if not pasta.is_dir():
        return
    for path in sorted(pasta.glob('*/*.json')):
        if path.is_file() and not path.is_symlink():
            try:
                dados = _ler(path)
            except ValueError:
                continue  # rascunho danificado não bloqueia os demais; ele é recusado ao ser lido
            if dados:
                yield path, dados


def _conferir_limites(pasta: Path, alvo: Path, tamanho: int, convidado: bool = False) -> None:
    valores = limites.RASCUNHOS
    limites.conferir_tamanho(tamanho, valores['bytes_por_rascunho'], 'Rascunho grande demais')
    abertos = [(path, dados) for path, dados in _todos(pasta) if path != alvo and not dados.get('descartado')]
    if convidado and sum(1 for path, _ in abertos if path.parent == alvo.parent) + 1 > valores['rascunhos_por_convidado']:
        raise ValueError(f'Rascunhos desta conta chegaram ao limite ({valores["rascunhos_por_convidado"]} abertos). '
                         'Envie ou descarte alguma pergunta antes de começar outra.')
    if len(abertos) + 1 > valores['rascunhos_por_caso']:
        raise ValueError(f'Rascunhos desta apuração chegaram ao limite ({valores["rascunhos_por_caso"]} abertos). '
                         'Conclua ou descarte algum antes de começar outro.')
    limites.conferir_tamanho(sum(d.get('bytes', 0) for _, d in abertos) + tamanho,
                             valores['bytes_rascunhos_por_caso'], 'Rascunhos desta apuração ocupam o limite do caso')


def ler(root, caso, conta, tela) -> dict:
    root = Path(root)
    tela = _tela(tela)
    pasta = _pasta_caso(root, caso)
    return _publico(_ler(_arquivo(pasta, _conta(conta), tela)), caso, tela)


def listar(root, caso, conta) -> dict:
    """Rascunhos abertos (não descartados) desta conta na apuração, sem o conteúdo."""
    root = Path(root)
    pasta = _pasta_caso(root, caso)
    dono = pasta / _conta(conta)
    itens = []
    for path in sorted(dono.glob('*.json')) if dono.is_dir() else []:
        try:
            dados = _ler(path)
        except ValueError:
            continue
        if dados and not dados.get('descartado') and isinstance(dados.get('tela'), str) \
                and path == _arquivo(pasta, dono.name, dados['tela']):
            itens.append(_resumo(dados, caso))
    itens.sort(key=lambda item: item['atualizado_em_utc'] or '', reverse=True)
    return {'caso': caso, 'rascunhos': itens}


def _gravar(root: Path, caso, conta, tela, versao, conteudo, *, descartar: bool, convidado: bool = False) -> dict:
    tela = _tela(tela)
    dono = _conta(conta)
    if type(versao) is not int or versao < 0:
        raise ValueError('Rascunho inválido: informe a versão que esta aba conhece (0 para um rascunho novo).')
    if not descartar:
        conteudo = _conteudo(conteudo)
    pasta = _pasta_caso(root, caso)
    alvo = _arquivo(pasta, dono, tela)
    with _TRAVA, trava_arquivo(pasta / 'rascunhos'):
        # Releitura sob a trava: a lixeira e o arquivo podem ter mudado desde a validação.
        _pasta_caso(root, caso)
        atual = _ler(alvo)
        gravada = atual['versao'] if atual else 0
        if atual and atual.get('tela') != tela:
            raise ValueError('Rascunho ilegível no servidor; descarte-o para continuar.')
        if gravada != versao:
            mesmo = (atual and not atual.get('descartado') and not descartar and atual.get('conteudo') == conteudo
                     and gravada == versao + 1)
            if mesmo:  # reenvio do mesmo salvamento cuja resposta se perdeu
                return _publico(atual, caso, tela)
            raise ConflitoRascunho(_publico(atual, caso, tela))
        if descartar and (not atual or atual.get('descartado')):
            return _publico(atual, caso, tela)
        tamanho = 0 if descartar else _tamanho(conteudo)
        if not descartar:
            _conferir_limites(pasta, alvo, tamanho, convidado)
        novo = {'formato': FORMATO, 'caso': caso, 'conta': dono, 'tela': tela, 'versao': gravada + 1,
                'atualizado_em_utc': _agora(), 'descartado': descartar,
                'conteudo': None if descartar else conteudo, 'bytes': tamanho}
        alvo.parent.mkdir(parents=True, exist_ok=True)
        _atomico(alvo, _bytes(novo))
        return _publico(novo, caso, tela)


def salvar(root, caso, conta, tela, versao, conteudo, convidado=False) -> dict:
    """Grava a versão ``versao + 1`` se ``versao`` for a gravada; senão ``ConflitoRascunho``."""
    return _gravar(Path(root), caso, conta, tela, versao, conteudo, descartar=False, convidado=convidado)


def descartar(root, caso, conta, tela, versao) -> dict:
    """Apaga o conteúdo e mantém a marca da versão. Exige a versão gravada, como ao salvar."""
    return _gravar(Path(root), caso, conta, tela, versao, None, descartar=True)


def executar(root, operation, data, conta=None, casos=None, convidado=False) -> dict:
    """Despacha ``POST /api/rascunhos-*``. ``casos`` é None para administradores (todas as apurações)."""
    if operation not in CAMPOS_PEDIDO or not isinstance(data, dict):
        raise ValueError('Operação de rascunho desconhecida.')
    if set(data) - CAMPOS_PEDIDO[operation]:
        raise ValueError('Rascunho inválido: campos fora do pedido.')
    caso = data.get('caso')
    if casos is not None and caso not in casos:
        raise ValueError('Apuração não liberada para esta conta.')
    tela = data.get('tela')
    if convidado and operation != 'rascunhos-listar' and not (isinstance(tela, str) and TELAS_CONVIDADO.fullmatch(tela)):
        raise ValueError('Convidados guardam somente o rascunho da pergunta.')
    if operation == 'rascunhos-salvar':
        return salvar(root, caso, conta, tela, data.get('versao'), data.get('conteudo'), convidado=convidado)
    if operation == 'rascunhos-ler':
        return ler(root, caso, conta, tela)
    if operation == 'rascunhos-descartar':
        return descartar(root, caso, conta, tela, data.get('versao'))
    resultado = listar(root, caso, conta)
    if convidado:
        resultado['rascunhos'] = [r for r in resultado['rascunhos'] if TELAS_CONVIDADO.fullmatch(r['tela'])]
    return resultado
