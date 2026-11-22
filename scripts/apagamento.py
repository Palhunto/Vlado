"""Apagamento definitivo de itens que já estão na lixeira. Sem chamadas de modelo ou rede.

`alcance` calcula, sem apagar nada, tudo o que a Mesa controla para o item (arquivos, pastas,
bytes por categoria) e uma confirmação derivada desse alcance. `apagar` exige essa confirmação,
recusa execuções ativas e remove somente dentro da raiz do projeto, sem seguir links simbólicos
ou junções. O registro de apagamento (lixeira/apagamentos.jsonl, somente acréscimo) guarda
identificadores, contagens e bytes; nunca conteúdo de documentos nem títulos.

**Quarentena** (a Mesa segue respondendo durante um apagamento grande). Sob as travas (a de cadastro
e a das conversas) só o que é rápido: conferir o item e o alcance e renomear cada raiz para
``<casos|conversas|execucoes>/.apagando/<item>/<n>``, no mesmo volume (no Compose cada pasta é um
volume, e renomear entre volumes falharia). Depois disso o item já não aparece em lugar nenhum; a
remoção dos arquivos corre fora das travas, em segundo plano na Mesa. Um manifesto em
``lixeira/.apagando/<item>.json`` guarda a fase: em ``renomeando`` (antes do ponto sem volta), uma
queda desfaz as renomeações e o item fica inteiro na lixeira; em ``removendo``, o apagamento é
concluído (catálogo, lixeira e registro, sem repetir; depois os arquivos). ``retomar`` faz isso na
partida da Mesa. Nada fica meio apagado à vista: ou o item está inteiro na lixeira, ou não está em
lugar nenhum. As pastas ``.apagando`` não entram no backup (é dado que a pessoa mandou apagar).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import stat
import threading
import time

from comum import dentro, ler_json
import lixeira

REGISTRO_APAGAMENTOS = 'lixeira/apagamentos.jsonl'
QUARENTENA = '.apagando'  # <volume>/.apagando/<item>/<n>: roots being removed
MANIFESTOS = 'lixeira/.apagando'  # <item>.json: the phase and the roots of each deletion in course
VOLUMES = ('casos', 'conversas', 'execucoes')
log = logging.getLogger('vlado.apagamento')
_remocoes: dict = {}  # (root, item) -> thread removing its quarantine
_remocoes_trava = threading.Lock()
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
                'quadros': 'quadros_evidencia', 'fontes_web': 'fontes_web', 'rascunhos': 'rascunhos'}.get(
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
    """Acumula arquivos (rel -> (categoria, bytes)) sem seguir links. Lê o diretório com scandir: o
    tamanho vem da própria entrada (no Windows, sem outra chamada ao sistema por arquivo)."""
    base = _alvo(root, relativo)
    if not os.path.lexists(base):
        return
    if _eh_link(base) or base.is_file():
        entradas[relativo] = (_categoria(Path(relativo).parts), 0 if _eh_link(base) else base.stat().st_size)
        return
    pastas.append(relativo)
    pendentes = [(str(base), relativo)]
    while pendentes:
        atual, rel_atual = pendentes.pop()
        with os.scandir(atual) as itens:
            for entrada in itens:
                rel = f'{rel_atual}/{entrada.name}'
                if entrada.is_symlink() or getattr(entrada, 'is_junction', lambda: False)():
                    entradas[rel] = (_categoria(Path(rel).parts), 0)
                elif entrada.is_dir(follow_symlinks=False):
                    pastas.append(rel)
                    pendentes.append((entrada.path, rel))
                else:
                    entradas[rel] = (_categoria(Path(rel).parts), entrada.stat(follow_symlinks=False).st_size)


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


def nome_para_confirmar(root, identificador: str) -> str:
    """O nome que a pessoa digita para confirmar, sem varrer os arquivos do item."""
    item = _item(Path(root).resolve(), identificador)
    return item.get('titulo') or item['caso']


def _manifesto(root: Path, item_id: str) -> Path:
    return dentro(root, f'{MANIFESTOS}/{item_id}.json')


def _gravar_manifesto(root: Path, manifesto: dict) -> None:
    from cadastrar_documentos import _atomico, _bytes
    caminho = _manifesto(root, manifesto['item']['id'])
    caminho.parent.mkdir(parents=True, exist_ok=True)
    _atomico(caminho, _bytes(manifesto))


def _renomear(root: Path, origem: str, destino: str) -> None:
    alvo = _alvo(root, destino)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    _tentar(lambda caminho: os.rename(caminho, alvo), _alvo(root, origem))


def _desfazer(root: Path, raizes) -> None:
    """Back from the quarantine to where they were, the last renamed first (an OSError leaves the rest)."""
    for origem, destino in reversed(list(raizes)):
        if os.path.lexists(_alvo(root, destino)) and not os.path.lexists(_alvo(root, origem)):
            _renomear(root, destino, origem)


def _limpar_quarentena_vazia(root: Path, item_id: str) -> None:
    for volume in VOLUMES:
        pasta = dentro(root, f'{volume}/{QUARENTENA}/{item_id}')
        for vazia in (pasta, pasta.parent):
            try:
                vazia.rmdir()
            except OSError:
                break


def _registrado(root: Path, item_id: str, confirmacao: str) -> bool:
    caminho = dentro(root, REGISTRO_APAGAMENTOS)
    try:
        linhas = caminho.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return False
    for linha in linhas:
        try:
            registro = json.loads(linha)
        except ValueError:
            continue
        if registro.get('item_id') == item_id and registro.get('confirmacao') == confirmacao:
            return True
    return False


def _concluir_registros(root: Path, manifesto: dict) -> None:
    """Catalog, trash and the deletion record, after the point of no return; idempotent."""
    item, resumo = manifesto['item'], manifesto['resumo']
    if manifesto.get('sem_registro'):
        return  # concluded and recorded before (see _concluir_ilegivel)
    _atualizar_registros(root, item)
    if not _registrado(root, item['id'], resumo['confirmacao']):
        _registrar(root, item, manifesto['quem'], resumo)


def _remover_quarentena(root: Path, manifesto: dict) -> bool:
    """Remove the item's quarantine and then its manifest. An OSError (a file in use) leaves both for
    the next start; nothing of it is visible meanwhile."""
    item_id = manifesto['item']['id']
    try:
        for _, destino in manifesto['raizes']:
            entradas: dict[str, tuple[str, int]] = {}
            pastas: list[str] = []
            _varrer(root, destino, entradas, pastas)
            _remover(root, sorted(entradas), pastas)
        _limpar_quarentena_vazia(root, item_id)
        _manifesto(root, item_id).unlink(missing_ok=True)
        return True
    except OSError as exc:
        log.warning('Apagamento definitivo %s: arquivos ainda não removidos (%s); a próxima partida conclui.',
                    item_id, exc.strerror or exc)
        return False


def _em_segundo_plano(root: Path, manifesto: dict) -> None:
    chave = (str(root), manifesto['item']['id'])

    def remover():
        try:
            _remover_quarentena(root, manifesto)
        except Exception:  # noqa: BLE001 - the next start concludes; the Mesa goes on
            log.exception('Apagamento definitivo %s: falha ao remover a quarentena.', chave[1])
        finally:
            with _remocoes_trava:
                _remocoes.pop(chave, None)
    with _remocoes_trava:
        if chave in _remocoes:
            return
        thread = threading.Thread(target=remover, daemon=True, name='vlado_apagamento')
        _remocoes[chave] = thread
    thread.start()


def aguardar(prazo: float | None = None) -> bool:
    """Wait for the background removals of this process (tests, orderly shutdown)."""
    limite = None if prazo is None else time.monotonic() + prazo
    while True:
        with _remocoes_trava:
            threads = list(_remocoes.values())
        if not threads:
            return True
        resta = None if limite is None else limite - time.monotonic()
        if resta is not None and resta <= 0:
            return False
        threads[0].join(resta)


def _concluir_ilegivel(root: Path, item_id: str) -> dict:
    """A manifest that cannot be read: it exists only after the person confirmed the deletion, so the
    deletion is concluded from the trash entry (when it is still there). Under the lock, like any
    deletion, only the quick part: the item's roots still in place go to the quarantine too, a readable
    manifest in ``removendo`` replaces the unreadable one, and catalog, trash and a record that says so.
    Returns that manifest; its files are removed outside the lock. OSError leaves it for the next try."""
    log.warning('Apagamento definitivo %s: manifesto ilegível; o item já tinha sido confirmado para apagar, '
                'então o apagamento é concluído a partir da lixeira.', item_id)
    item = next((i for i in lixeira.ativos(root) if i['id'] == item_id), None)
    raizes = []
    if item is not None:
        try:
            raizes = _escopo(root, item)['raizes']
        except (ValueError, KeyError, OSError):
            raizes = []
    pares = []
    for volume in VOLUMES:  # what the unreadable manifest had already moved
        pasta = dentro(root, f'{volume}/{QUARENTENA}/{item_id}')
        for parte in sorted(pasta.iterdir()) if pasta.is_dir() else []:
            pares.append([None, f'{volume}/{QUARENTENA}/{item_id}/{parte.name}'])
    for numero, origem in enumerate(raizes):  # and what was still in place
        if os.path.lexists(_alvo(root, origem)):
            destino = f'{origem.split("/")[0]}/{QUARENTENA}/{item_id}/i{numero}'
            _renomear(root, origem, destino)
            pares.append([origem, destino])
    identidade = ({k: item.get(k) for k in ('id', 'tipo', 'caso', 'conversa', 'rodada')} if item is not None
                  else {'id': item_id, 'tipo': None, 'caso': None, 'conversa': None, 'rodada': None})
    manifesto = {'esquema': 1, 'item': identidade, 'fase': 'removendo', 'quem': 'partida da Mesa (manifesto ilegível)',
                 'em_utc': datetime.now(timezone.utc).isoformat(), 'raizes': pares,
                 'resumo': {'conversas': [], 'rodadas': [], 'categorias': {}, 'totais': {},
                            'confirmacao': 'manifesto_ilegivel'},
                 # Gone from the trash already: its registries were concluded, and recorded, before.
                 'sem_registro': item is None}
    _gravar_manifesto(root, manifesto)  # readable from here on: a crash during the removal concludes it
    _concluir_registros(root, manifesto)
    return manifesto


def retomar(root, *, segundo_plano: bool = False, espera: float | None = None) -> dict:
    """At the Mesa's start: finish what a crash left. Phase ``renomeando``: the roots go back and the
    item stays whole in the trash. Phase ``removendo``: catalog, trash and record (without repeating),
    then the removal. A manifest that cannot be read: concluded from the trash (``_concluir_ilegivel``).
    A quarantine with no manifest (only this module writes there) is removed. ``espera``: how long to
    wait for the cadastro lock (the default of ``trava_cadastro`` when None)."""
    from cadastrar_documentos import _trava
    root = Path(root).resolve()
    resumo, pendentes = {'desfeitos': 0, 'concluidos': 0, 'orfas': 0, 'ilegiveis': 0}, []
    with _trava(root, **({} if espera is None else {'espera': espera})):
        pasta = dentro(root, MANIFESTOS)
        conhecidos = set()
        for caminho in sorted(pasta.glob('*.json')) if pasta.is_dir() else []:
            try:
                manifesto = ler_json(caminho)
                item_id, fase = manifesto['item']['id'], manifesto['fase']
            except (OSError, ValueError, KeyError, TypeError):
                conhecidos.add(caminho.stem)
                if not re.fullmatch(lixeira.ID_CONVERSA, caminho.stem):
                    log.warning('Apagamento definitivo: manifesto %s fora do padrão; ficou como está.', caminho.name)
                    continue
                try:
                    pendentes.append(_concluir_ilegivel(root, caminho.stem))  # its files: outside the lock
                    resumo['ilegiveis'] += 1
                except OSError as exc:
                    log.warning('Apagamento definitivo %s: não concluído (%s); a próxima partida tenta de novo.',
                                caminho.stem, exc.strerror or exc)
                continue
            conhecidos.add(item_id)
            if fase == 'renomeando':
                try:
                    _desfazer(root, manifesto['raizes'])
                except OSError as exc:
                    log.warning('Apagamento definitivo %s: renomeação não desfeita (%s); a próxima partida tenta de novo.',
                                item_id, exc.strerror or exc)
                    continue
                _limpar_quarentena_vazia(root, item_id)
                caminho.unlink(missing_ok=True)
                resumo['desfeitos'] += 1
            else:
                _concluir_registros(root, manifesto)
                pendentes.append(manifesto)
                resumo['concluidos'] += 1
        # A quarantine with no manifest (what a half-undone rename left): under the lock only a readable
        # manifest in "removendo" for it, with no record (there is no confirmed item to record); its files
        # are removed outside the lock, like any other, and a crash during that concludes it next time.
        orfas: dict[str, list] = {}
        for volume in VOLUMES:
            quarentena = dentro(root, f'{volume}/{QUARENTENA}')
            for orfa in sorted(quarentena.iterdir()) if quarentena.is_dir() else []:
                if orfa.name in conhecidos or not re.fullmatch(lixeira.ID_CONVERSA, orfa.name):
                    continue
                orfas.setdefault(orfa.name, []).append([None, f'{volume}/{QUARENTENA}/{orfa.name}'])
        for item_id, raizes in orfas.items():
            log.warning('Apagamento definitivo: quarentena %s sem manifesto; removida fora da trava.', item_id)
            manifesto = {'esquema': 1, 'item': {'id': item_id, 'tipo': None, 'caso': None, 'conversa': None, 'rodada': None},
                         'fase': 'removendo', 'quem': 'partida da Mesa (quarentena sem manifesto)',
                         'em_utc': datetime.now(timezone.utc).isoformat(), 'raizes': raizes,
                         'resumo': {'conversas': [], 'rodadas': [], 'categorias': {}, 'totais': {},
                                    'confirmacao': 'sem_manifesto'},
                         'sem_registro': True}
            try:
                _gravar_manifesto(root, manifesto)
            except OSError as exc:
                log.warning('Apagamento definitivo: quarentena %s não registrada (%s); a próxima partida tenta de novo.',
                            item_id, exc.strerror or exc)
                continue
            pendentes.append(manifesto)
            resumo['orfas'] += 1
    for manifesto in pendentes:
        if segundo_plano:
            _em_segundo_plano(root, manifesto)
        else:
            _remover_quarentena(root, manifesto)
    return resumo


def retomar_na_partida(root, *, espera: float = 2.0, intervalo: float = 30.0):
    """``retomar`` for the Mesa's start, which never falls for it: the summary, or None when it could not
    run now (cadastro lock busy, a file in use, anything else): then it tries again every ``intervalo``
    seconds in the background until it runs, and the next operation that takes the lock is unaffected."""
    try:
        return retomar(root, segundo_plano=True, espera=espera)
    except Exception as exc:  # noqa: BLE001 - the start goes on; this is retried below
        log.warning('Apagamento definitivo: retomada na partida não concluída (%s); tenta de novo em segundo plano.', exc)

    def tentar_depois():
        while True:
            time.sleep(intervalo)
            try:
                retomar(root, segundo_plano=True)
                log.warning('Apagamento definitivo: retomada concluída em segundo plano.')
                return
            except Exception as exc:  # noqa: BLE001 - keeps trying; the Mesa goes on
                log.warning('Apagamento definitivo: retomada ainda não concluída (%s).', exc)
    threading.Thread(target=tentar_depois, daemon=True, name='vlado_apagamento_retomada').start()
    return None


def apagar(root, identificador: str, confirmacao: str, *, quem: str, gerenciador=None, ativa=None,
           segundo_plano: bool = False) -> dict:
    """Apaga definitivamente um item da lixeira, se `confirmacao` ainda corresponder ao alcance atual.

    `gerenciador` é o objeto Conversas (usa seu lock e seus contextos); `ativa(caso, conversa)` é
    um callback opcional que devolve True quando há execução ativa para o item. Sob as travas, só a
    conferência e a quarentena; a remoção dos arquivos vem depois, fora delas (em segundo plano com
    `segundo_plano`, como na Mesa).
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
        raizes = [r for r in atual['raizes'] if os.path.lexists(_alvo(root, r))]
        # Identities only, like the deletion record: never the title (the manifest stays until the files go).
        manifesto = {'esquema': 1, 'item': {k: item.get(k) for k in ('id', 'tipo', 'caso', 'conversa', 'rodada')},
                     'fase': 'renomeando', 'quem': quem.strip()[:120],
                     'em_utc': datetime.now(timezone.utc).isoformat(),
                     'raizes': [[r, f'{r.split("/")[0]}/{QUARENTENA}/{item["id"]}/{n}'] for n, r in enumerate(raizes)],
                     'resumo': {k: atual[k] for k in ('conversas', 'rodadas', 'categorias', 'totais', 'confirmacao')}}
        _gravar_manifesto(root, manifesto)
        feitas = []
        try:
            for origem, destino in manifesto['raizes']:
                _renomear(root, origem, destino)
                feitas.append((origem, destino))
        except OSError as exc:
            try:
                _desfazer(root, feitas)
            except OSError:
                # The manifest stays in "renomeando": the next start puts them back. Say so.
                log.warning('Apagamento definitivo %s: renomeação desfeita só em parte; a partida termina.', item['id'])
                raise ValueError('Não foi possível apagar (arquivo em uso ou sem permissão), e parte do item já tinha '
                                 'sido separada para apagar: ela volta à lixeira na próxima partida da Mesa. Até lá, '
                                 'não restaure nem apague este item; feche os programas que usem esses arquivos e '
                                 'reinicie a Mesa.') from exc
            else:
                _limpar_quarentena_vazia(root, item['id'])
                _manifesto(root, item['id']).unlink(missing_ok=True)
            raise ValueError('Não foi possível apagar tudo (arquivo em uso ou sem permissão). '
                             'O item continua na lixeira; feche programas que usem esses arquivos e tente de novo.') from exc
        manifesto['fase'] = 'removendo'
        _gravar_manifesto(root, manifesto)  # the point of no return: a crash from here on concludes
        for conversa in atual['conversas']:
            if gerenciador is not None:
                gerenciador.contexts.pop(conversa, None)
                gerenciador.loaded.discard(conversa)
        _concluir_registros(root, manifesto)
    if segundo_plano:
        _em_segundo_plano(root, manifesto)
    else:
        _remover_quarentena(root, manifesto)
    return {'estado': 'apagado', 'item': atual['item'], 'categorias': atual['categorias'],
            'totais': atual['totais'], 'aviso_backup': AVISO_BACKUP}
