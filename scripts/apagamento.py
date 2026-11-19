"""Apagamento definitivo de itens que já estão na lixeira. Sem chamadas de modelo ou rede.

`alcance` calcula, sem apagar nada, tudo o que a Mesa controla para o item (arquivos, pastas,
bytes por categoria) e uma confirmação derivada desse alcance. `apagar` exige essa confirmação,
recusa execuções ativas e remove somente dentro da raiz do projeto, sem seguir links simbólicos
ou junções. O registro de apagamento (lixeira/apagamentos.jsonl, somente acréscimo) guarda
identificadores, contagens e bytes; nunca conteúdo de documentos nem títulos.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import time

from comum import dentro, ler_json
import lixeira

REGISTRO_APAGAMENTOS = 'lixeira/apagamentos.jsonl'
TENTATIVAS = 12
ESPERA_S = 0.05
ESTADOS_ATIVOS = ('preparando', 'executando', 'cancelando', 'publicando')
AVISO_BACKUP = ('Cópias que já estejam em backups feitos com scripts/backup.py não são apagadas por esta ação. '
                'Elas permanecem até expirar conforme a retenção de backups definida pelo operador.')


def _eh_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(os.path, 'isjunction', lambda _p: False)(path))


def _alvo(root: Path, relativo: str) -> Path:
    """Caminho sem resolver o último componente, para nunca seguir link simbólico final."""
    rel = Path(relativo)
    pai = dentro(root, rel.parent.as_posix())  # resolve e recusa saída da raiz
    return pai / rel.name


def _categoria(partes: tuple[str, ...]) -> str:
    raiz = partes[0]
    if raiz == 'conversas':
        return 'conversas'
    if raiz == 'casos':
        resto = partes[2:]
        if resto[:1] == ('cadastros',) and len(resto) > 3 and resto[2] in ('originais', 'derivados'):
            return resto[2]
        return {'caderno': 'caderno', 'diligencias': 'diligencias', 'apuracao': 'notas',
                'quadros': 'quadros_evidencia'}.get(
            resto[0] if resto else '', 'corpus')
    resto = partes[3:]
    if resto[:1] == ('indice',):
        return 'indice_documental'
    if resto[:3] == ('saidas', 'achados', 'indices'):
        return 'indice_achados'
    if resto[:2] == ('saidas', 'revisao_humana'):
        return 'revisoes_humanas'
    if resto[:2] == ('saidas', 'achados'):
        return 'registros_achados'
    return 'rodadas'


def _varrer(root: Path, relativo: str, entradas: dict, pastas: list) -> None:
    """Acumula arquivos (rel -> (categoria, bytes)) sem seguir links."""
    base = _alvo(root, relativo)
    if not os.path.lexists(base):
        return
    if _eh_link(base) or base.is_file():
        entradas[relativo] = (_categoria(Path(relativo).parts), 0 if _eh_link(base) else base.stat().st_size)
        return
    pastas.append(relativo)
    for atual, nomes, arquivos in os.walk(base, followlinks=False):
        rel_atual = Path(atual).relative_to(root.resolve()).as_posix()
        for nome in list(nomes):
            caminho = Path(atual) / nome
            if _eh_link(caminho):
                nomes.remove(nome)
                rel = f'{rel_atual}/{nome}'
                entradas[rel] = (_categoria(Path(rel).parts), 0)
            else:
                pastas.append(f'{rel_atual}/{nome}')
        for nome in arquivos:
            caminho = Path(atual) / nome
            rel = f'{rel_atual}/{nome}'
            tamanho = 0 if _eh_link(caminho) else caminho.stat().st_size
            entradas[rel] = (_categoria(Path(rel).parts), tamanho)


def _item(root: Path, identificador: str) -> dict:
    if not isinstance(identificador, str) or not re.fullmatch(lixeira.ID_CONVERSA, identificador):
        raise ValueError('Identificador da lixeira inválido.')
    item = next((i for i in lixeira.ativos(root) if i['id'] == identificador), None)
    if not item:
        raise ValueError('Só é possível apagar definitivamente um item que está na lixeira.')
    lixeira.validar(item['tipo'], item['caso'], item.get('conversa'), item.get('rodada'))
    return item


def _conversas_do_caso(root: Path, caso: str) -> list[dict]:
    pasta = dentro(root, 'conversas')
    metas = []
    for caminho in sorted(pasta.glob('*/conversa.json')) if pasta.is_dir() else []:
        try:
            meta = ler_json(caminho)
        except (OSError, ValueError):
            continue
        if meta.get('caso') == caso and isinstance(meta.get('id'), str) and meta['id'] == caminho.parent.name:
            metas.append(meta)
    return metas


def _escopo(root: Path, item: dict) -> dict:
    """Define pastas, conversas e rodadas do item. Lê apenas identidades, nunca documentos."""
    tipo, caso = item['tipo'], item['caso']
    metas = _conversas_do_caso(root, caso)
    raizes, conversas, rodadas, preservadas = [], [], [], []
    if tipo == 'caso':
        raizes += [f'casos/{caso}', f'execucoes/{caso}']
        conversas = [m['id'] for m in metas]
    elif tipo == 'conversa':
        conversa = item['conversa']
        meta = next((m for m in metas if m['id'] == conversa), {})
        conversas = [conversa]
        outras = {r for m in metas if m['id'] != conversa for r in m.get('rodadas', [])}
        candidatas = list(dict.fromkeys([*item.get('rodadas', []), *meta.get('rodadas', [])]))
        rodadas = [r for r in candidatas if re.fullmatch(lixeira.ID_RODADA, str(r)) and r not in outras]
        preservadas = [r for r in candidatas if r in outras]
        raizes += [f'execucoes/{caso}/{r}' for r in rodadas]
    else:
        rodadas = [item['rodada']]
        raizes.append(f'execucoes/{caso}/{item["rodada"]}')
    raizes += [f'conversas/{c}' for c in conversas]
    return {'raizes': raizes, 'conversas': conversas, 'rodadas': rodadas, 'preservadas': preservadas}


def _token(item: dict, entradas: dict, pastas: list) -> str:
    corpo = {'item': item['id'], 'tipo': item['tipo'], 'caso': item['caso'],
             'arquivos': sorted([rel, dados[1]] for rel, dados in entradas.items()),
             'pastas': sorted(pastas)}
    return hashlib.sha256(json.dumps(corpo, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def alcance(root, identificador: str) -> dict:
    """Função pura: lista o que seria apagado definitivamente para um item da lixeira."""
    root = Path(root).resolve()
    item = _item(root, identificador)
    escopo = _escopo(root, item)
    entradas: dict[str, tuple[str, int]] = {}
    pastas: list[str] = []
    for raiz in escopo['raizes']:
        _varrer(root, raiz, entradas, pastas)
    categorias: dict[str, dict] = {}
    for categoria, tamanho in entradas.values():
        atual = categorias.setdefault(categoria, {'arquivos': 0, 'bytes': 0})
        atual['arquivos'] += 1
        atual['bytes'] += tamanho
    registros = {'catalogo': 1 if item['tipo'] == 'caso' else 0,
                 'lixeira': 1 + (sum(1 for i in lixeira.ativos(root)
                                     if item['tipo'] == 'caso' and i['caso'] == item['caso'] and i['id'] != item['id']))}
    return {'item': {k: item.get(k) for k in ('id', 'tipo', 'caso', 'titulo', 'conversa', 'rodada')},
            'nome_para_confirmar': item.get('titulo') or item['caso'],
            'categorias': dict(sorted(categorias.items())),
            'totais': {'arquivos': len(entradas), 'pastas': len(pastas),
                       'bytes': sum(t for _, t in entradas.values())},
            'raizes': sorted(escopo['raizes']), 'conversas': escopo['conversas'],
            'rodadas': escopo['rodadas'], 'rodadas_preservadas': escopo['preservadas'],
            'registros': registros, 'aviso_backup': AVISO_BACKUP,
            'confirmacao': _token(item, entradas, pastas),
            '_entradas': sorted(entradas), '_pastas': sorted(pastas)}


def alcance_publico(root, identificador: str) -> dict:
    """Mesmo resultado de `alcance`, sem as listas internas de caminhos (para JSON da interface)."""
    return {k: v for k, v in alcance(root, identificador).items() if not k.startswith('_')}


def _tentar(operacao, caminho: Path) -> None:
    for tentativa in range(TENTATIVAS):
        try:
            operacao(caminho)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if tentativa == TENTATIVAS - 1:
                raise
            try:
                os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            except OSError:
                pass
            time.sleep(ESPERA_S * (tentativa + 1))


def _apagar_arquivo(caminho: Path) -> None:
    if _eh_link(caminho) and caminho.is_dir() and not caminho.is_symlink():
        _tentar(os.rmdir, caminho)  # junção do Windows: remove só a junção
    else:
        _tentar(os.unlink, caminho)


def _remover(root: Path, entradas: list[str], pastas: list[str]) -> None:
    for rel in entradas:
        _apagar_arquivo(_alvo(root, rel))
    for rel in sorted(pastas, key=lambda p: p.count('/'), reverse=True):
        _tentar(os.rmdir, _alvo(root, rel))


def _ativo(root: Path, item: dict, gerenciador, ativa) -> bool:
    if ativa is not None and ativa(item['caso'], item.get('conversa')):
        return True
    for ctx in (gerenciador.contexts.values() if gerenciador is not None else ()):
        meta = ctx['meta']
        relacionado = meta['caso'] == item['caso'] and (item['tipo'] != 'conversa' or meta['id'] == item['conversa'])
        if relacionado and (ctx.get('busy') or meta.get('estado') in ESTADOS_ATIVOS):
            return True
    return False


def _atualizar_registros(root: Path, item: dict) -> None:
    from cadastrar_documentos import _atomico, _bytes
    if item['tipo'] == 'caso':
        caminho = dentro(root, 'casos/catalogo.json')
        if caminho.exists():
            catalogo = ler_json(caminho)
            catalogo['casos'] = [c for c in catalogo['casos'] if c['id'] != item['caso']]
            _atomico(caminho, _bytes(catalogo))
        config_caminho = dentro(root, 'configuracao.json')
        if config_caminho.exists():
            config = ler_json(config_caminho)
            if config.get('caso_ativo') == item['caso']:
                config.update(caso_ativo=None, manifesto_ativo=None, estado_inicial='sem_caso_selecionado')
                _atomico(config_caminho, _bytes(config))
        restantes = [i for i in lixeira.registros(root) if i['caso'] != item['caso']]
    else:
        restantes = [i for i in lixeira.registros(root) if i['id'] != item['id']]
    lixeira.salvar(root, restantes)


def _registrar(root: Path, item: dict, quem: str, resumo: dict) -> dict:
    registro = {'em_utc': datetime.now(timezone.utc).isoformat(), 'quem': quem,
                'item_id': item['id'], 'tipo': item['tipo'], 'caso': item['caso'],
                'conversa': item.get('conversa'), 'rodada': item.get('rodada'),
                'conversas': resumo['conversas'], 'rodadas': resumo['rodadas'],
                'categorias': resumo['categorias'], 'totais': resumo['totais'],
                'confirmacao': resumo['confirmacao']}
    caminho = dentro(root, REGISTRO_APAGAMENTOS)
    caminho.parent.mkdir(exist_ok=True)
    with caminho.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    return registro


def apagar(root, identificador: str, confirmacao: str, *, quem: str, gerenciador=None, ativa=None) -> dict:
    """Apaga definitivamente um item da lixeira, se `confirmacao` ainda corresponder ao alcance atual.

    `gerenciador` é o objeto Conversas (usa seu lock e seus contextos); `ativa(caso, conversa)` é
    um callback opcional que devolve True quando há execução ativa para o item.
    """
    root = Path(root).resolve()
    if not isinstance(quem, str) or not quem.strip():
        raise ValueError('Identifique quem confirma o apagamento.')
    if not isinstance(confirmacao, str) or not confirmacao:
        raise ValueError('Confirmação ausente. Consulte o alcance antes de apagar.')
    from contextlib import ExitStack
    from cadastrar_documentos import _trava
    with ExitStack() as pilha:
        if gerenciador is not None:
            pilha.enter_context(gerenciador.lock)
        pilha.enter_context(_trava(root))
        item = _item(root, identificador)
        if _ativo(root, item, gerenciador, ativa):
            raise ValueError('Há uma execução em andamento. Cancele-a e aguarde o encerramento antes de apagar definitivamente.')
        atual = alcance(root, identificador)
        if not hmac.compare_digest(atual['confirmacao'], confirmacao):
            raise ValueError('O conteúdo do item mudou desde a conferência. Revise o alcance e confirme novamente.')
        try:
            _remover(root, atual['_entradas'], atual['_pastas'])
        except OSError as exc:
            raise ValueError('Não foi possível apagar tudo (arquivo em uso ou sem permissão). '
                             'O item continua na lixeira; feche programas que usem esses arquivos e tente de novo.') from exc
        for conversa in atual['conversas']:
            if gerenciador is not None:
                gerenciador.contexts.pop(conversa, None)
                gerenciador.loaded.discard(conversa)
        _atualizar_registros(root, item)
        _registrar(root, item, quem.strip()[:120], atual)
    return {'estado': 'apagado', 'item': atual['item'], 'categorias': atual['categorias'],
            'totais': atual['totais'], 'aviso_backup': AVISO_BACKUP}
