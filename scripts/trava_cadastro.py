"""Trava de cadastro: uma operação por vez sobre ``casos/`` e ``execucoes/``, entre processos.

Substitui a pasta ``casos/.cadastro.lock`` criada com ``mkdir``, que falhava na hora quando
ocupada e, se o processo morresse no meio, bloqueava cadastro e perguntas até alguém apagá-la
à mão (CONF-01). Seguram esta trava o cadastro de lotes, a preparação de PDFs, o congelamento
de rodadas, a captura web (para conferir e publicar), a gestão de apurações e o apagamento.

- **Exclusão.** Trava do sistema operacional (``flock`` no Linux, ``msvcrt.locking`` no
  Windows) sobre o arquivo ``casos/.cadastro.trava``, que nunca é apagado. O sistema solta a
  trava quando o processo termina, inclusive por ``kill -9`` ou queda do contêiner; uma trava
  viva nunca é tirada de quem a segura, porque ninguém a solta por fora.
- **Dono.** Quem segura grava no arquivo pid, host, horário (UTC) e a operação; ao soltar,
  grava ``livre``, sempre com os mesmos bytes. Quem pega a trava e encontra um dono gravado
  sabe que o anterior morreu segurando-a (trava abandonada): registra o fato no registro do
  servidor e limpa o que ele deixou pela metade.
- **Espera.** Trava ocupada é esperada até o prazo, em vez de falhar na hora. Esgotado o
  prazo, a operação recusa com a mesma frase de antes ("Há um cadastro ou congelamento em
  andamento...") e o horário de início de quem segura. Pid e host ficam no registro do
  servidor, não na mensagem, que também chega a convidados.
- **Threads.** Dentro do processo, as threads se revezam numa trava de thread antes da trava
  do sistema. A mesma thread pedindo de novo falha na hora: seria esperar por si mesma.
- **Partida.** ``recuperar`` limpa o que um processo morto deixou: dono gravado, a pasta
  antiga ``casos/.cadastro.lock`` e as pastas de preparo que só existem dentro desta trava
  (``casos/.lote_*`` do cadastro e ``execucoes/.r_*`` do congelamento). Só age quando consegue
  a trava; se ela está viva em outro processo (um cadastro pela linha de comando), não toca em
  nada. A pasta antiga não tem dono para conferir: em funcionamento ela é recusada na hora,
  como antes, e só a partida a remove (a partida pressupõe que não há processo da versão
  anterior rodando; a atualização encerra a Mesa antes).
- **Encerramento.** ``encerrar`` faz as esperas em curso desistirem e recusa novas;
  ``aguardar_livre`` dá às operações que já seguram a trava o prazo para terminar.

Ordem das travas na Mesa: ``cadastro_lock`` (threads da Mesa) → ``Conversas.lock`` → esta.
Dentro desta trava não se pega ``Conversas.lock``.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import json
import logging
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import threading
import time
import uuid

ARQUIVO = '.cadastro.trava'
ANTIGA = '.cadastro.lock'  # pasta da trava por mkdir, das versões anteriores
ESPERA = 20.0  # segundos que uma operação espera a trava antes de desistir
TAMANHO_REGISTRO = 2048  # o registro do dono ocupa sempre os mesmos bytes: nunca truncar o arquivo
# Windows: o byte travado fica longe do registro, que continua legível para quem espera.
BYTE_TRAVADO = 1 << 30
MENSAGEM = 'Há um cadastro ou congelamento em andamento{detalhe}; tente novamente após sua conclusão.'
# Always the same bytes when free: after any operation the file is identical to before it (who
# held it and when goes to the server log, not here).
LIVRE = {'estado': 'livre', 'versao': 1}
# Pastas de preparo criadas só por quem segura a trava (comum.pasta_preparacao + uuid4().hex).
PREPARO = (('casos', re.compile(r'\.lote_[0-9a-f]{32}')), ('execucoes', re.compile(r'\.r_[0-9a-f]{32}')))

log = logging.getLogger('vlado.trava_cadastro')


class TravaOcupada(ValueError):
    """A trava não veio no prazo (ou não podia vir). ``dono``: o registro lido, quando havia."""

    def __init__(self, mensagem, dono=None):
        super().__init__(mensagem)
        self.dono = dono


class TravaInterrompida(TravaOcupada):
    """A espera foi interrompida: a Mesa está encerrando ou a operação foi cancelada."""


class _Estado:
    """Estado desta trava dentro do processo (um por pasta ``casos``)."""

    def __init__(self):
        self.threads = threading.Lock()  # revezamento das threads deste processo
        self.dono = None  # ident da thread que segura
        self.encerrando = False
        self.mudou = threading.Condition()  # avisa quem aguarda a trava ficar livre


_estados: dict[str, _Estado] = {}
_estados_lock = threading.Lock()


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _pasta(root) -> Path:
    # Same resolution as comum.dentro (kept local: comum imports nothing from here).
    return Path(root).resolve() / 'casos'


def _estado(pasta: Path) -> _Estado:
    chave = os.path.normcase(str(pasta))
    with _estados_lock:
        return _estados.setdefault(chave, _Estado())


# --- trava do sistema operacional -------------------------------------------------------------

if os.name == 'nt':
    import msvcrt

    def _tentar(fd) -> bool:
        os.lseek(fd, BYTE_TRAVADO, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EDEADLK, getattr(errno, 'EDEADLOCK', errno.EDEADLK)):
                return False
            raise
        return True

    def _soltar(fd):
        os.lseek(fd, BYTE_TRAVADO, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _tentar(fd) -> bool:
        # flock belongs to the open file description: two threads or two processes that open
        # the file separately exclude each other, and the kernel drops it when the holder dies.
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                return False
            raise
        return True

    def _soltar(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


def _abrir(caminho: Path, prazo: float):
    """Open (creating) the lock file; a transient sharing refusal on Windows is retried."""
    while True:
        try:
            # os.open fds are not inherited by child processes (PEP 446): OCR subprocesses
            # never keep the lock alive after the holder dies.
            return os.open(caminho, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o666)
        except PermissionError:
            if time.monotonic() >= prazo:
                raise
            time.sleep(0.05)


def _ler(fd):
    """Registro gravado no arquivo: None se vazio; {'estado': 'ilegivel'} se corrompido."""
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        bruto = os.read(fd, TAMANHO_REGISTRO).strip(b'\x00 \r\n\t')
    except OSError:
        return {'estado': 'ilegivel'}
    if not bruto:
        return None
    try:
        registro = json.loads(bruto.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {'estado': 'ilegivel'}
    return registro if isinstance(registro, dict) else {'estado': 'ilegivel'}


def _gravar(fd, registro):
    dados = json.dumps(registro, ensure_ascii=False).encode('utf-8')[:TAMANHO_REGISTRO - 1]
    # Fixed size, padded with spaces: a reader never sees a shorter file, and the file is never
    # truncated (on Windows, truncating under a byte-range lock is not something to rely on).
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, dados + b' ' * (TAMANHO_REGISTRO - 1 - len(dados)) + b'\n')


def ler_dono(root):
    """Who holds (or last held) the lock, without taking it. None when there is no record."""
    caminho = _pasta(root) / ARQUIVO
    try:
        fd = os.open(caminho, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    except OSError:
        return None
    try:
        return _ler(fd)
    finally:
        os.close(fd)


def _detalhe(dono):
    desde = dono.get('desde_utc') if isinstance(dono, dict) and dono.get('estado') == 'ocupada' else None
    if isinstance(desde, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d.*', desde):
        return f' desde {desde[11:16]} (UTC)'
    return ''


def _ocupada(caminho: Path, dono=None, motivo=None):
    if motivo == 'encerrando':
        return TravaInterrompida('A Mesa está sendo encerrada; a operação não começou. '
                                 'Tente novamente quando ela voltar.', dono)
    if motivo == 'cancelada':
        return TravaInterrompida('Operação cancelada enquanto esperava o fim de um cadastro ou congelamento.', dono)
    if motivo == 'antiga':
        return TravaOcupada(MENSAGEM.format(detalhe=' (trava antiga casos/.cadastro.lock, sem dono registrado)')
                            + ' Se nenhuma Mesa ou cadastro de versão anterior estiver aberto, reinicie a Mesa:'
                            ' a partida remove essa trava.', dono)
    if motivo == 'mesma_thread':
        return TravaOcupada(MENSAGEM.format(detalhe=' nesta mesma operação (trava pedida duas vezes)'), dono)
    return TravaOcupada(MENSAGEM.format(detalhe=_detalhe(dono)), dono)


# --- trava -------------------------------------------------------------------------------------

@contextmanager
def trava(root, *, espera=None, operacao=None, cancelar=None, avisar=True):
    """Hold the project's cadastro lock; wait up to ``espera`` seconds (default ``ESPERA``).

    ``cancelar``: optional callable checked while waiting; when it returns true the wait stops
    with ``TravaInterrompida``. ``avisar=False``: no log line when the wait runs out (a caller
    that simply tries again, as the extraction queue). Yields the owner record written to the
    lock file.
    """
    espera = ESPERA if espera is None else max(0.0, float(espera))
    prazo = time.monotonic() + espera
    pasta = _pasta(root)
    pasta.mkdir(exist_ok=True)
    caminho = pasta / ARQUIVO
    estado = _estado(pasta)
    eu = threading.get_ident()
    if estado.dono == eu:
        raise _ocupada(caminho, motivo='mesma_thread')
    _esperar_threads(estado, caminho, prazo, cancelar, avisar)
    try:
        fd = _abrir(caminho, prazo)
        try:
            anterior = _esperar_sistema(fd, estado, caminho, prazo, cancelar, avisar)
            try:
                if (pasta / ANTIGA).exists():
                    # Old-format lock: nobody to check, so neither waited for nor removed here.
                    raise _ocupada(caminho, motivo='antiga')
                if anterior and anterior.get('estado') != 'livre':
                    _recuperar_abandonada(Path(root), anterior)
                registro = {'estado': 'ocupada', 'pid': os.getpid(), 'host': socket.gethostname(),
                            'desde_utc': _agora(), 'operacao': operacao, 'token': uuid.uuid4().hex, 'versao': 1}
                _gravar(fd, registro)
                estado.dono = eu
                try:
                    yield dict(registro)
                finally:
                    estado.dono = None
                    try:
                        _gravar(fd, LIVRE)
                    except OSError:
                        log.warning('Não foi possível marcar a trava de cadastro como livre; o sistema a solta '
                                    'mesmo assim, e o próximo dono a tratará como abandonada.')
            finally:
                _soltar(fd)
        finally:
            os.close(fd)
    finally:
        estado.threads.release()
        with estado.mudou:
            estado.mudou.notify_all()


def _esperar_threads(estado, caminho, prazo, cancelar, avisar=True):
    while True:
        if estado.encerrando:
            raise _ocupada(caminho, ler_dono(caminho.parent.parent), 'encerrando')
        if cancelar is not None and cancelar():
            raise _ocupada(caminho, ler_dono(caminho.parent.parent), 'cancelada')
        restante = prazo - time.monotonic()
        if restante <= 0:
            if estado.threads.acquire(blocking=False):
                return
            dono = ler_dono(caminho.parent.parent)
            if avisar:
                log.warning('Trava de cadastro ocupada além do prazo por outra operação deste processo: %s', dono)
            raise _ocupada(caminho, dono)
        if estado.threads.acquire(timeout=min(0.2, restante)):
            if estado.encerrando:  # shutdown began while this thread was queued
                estado.threads.release()
                raise _ocupada(caminho, ler_dono(caminho.parent.parent), 'encerrando')
            return


def _esperar_sistema(fd, estado, caminho, prazo, cancelar, avisar=True):
    pausa = 0.02
    while True:
        if _tentar(fd):
            return _ler(fd)
        if estado.encerrando or (cancelar is not None and cancelar()):
            raise _ocupada(caminho, _ler(fd), 'encerrando' if estado.encerrando else 'cancelada')
        agora = time.monotonic()
        if agora >= prazo:
            dono = _ler(fd)
            if avisar:
                log.warning('Trava de cadastro ocupada além do prazo por outro processo: %s', dono)
            raise _ocupada(caminho, dono)
        time.sleep(min(pausa, prazo - agora))
        pausa = min(pausa * 2, 0.25)


def _recuperar_abandonada(root: Path, anterior):
    """Called while holding the lock, when the previous holder died holding it."""
    log.warning('Trava de cadastro abandonada recuperada: processo %s em %s, desde %s (%s). '
                'O sistema já a tinha soltado; limpando o preparo deixado pela metade.',
                anterior.get('pid', '?'), anterior.get('host', '?'), anterior.get('desde_utc', '?'),
                anterior.get('operacao') or anterior.get('estado'))
    _limpar_preparo(root)


def _limpar_preparo(root: Path):
    """Remove staging folders that only a lock holder creates. Caller holds the lock."""
    removidas = []
    for nome_pasta, padrao in PREPARO:
        pasta = root / nome_pasta
        try:
            itens = list(pasta.iterdir()) if pasta.is_dir() else []
        except OSError:
            continue
        for item in itens:
            if not padrao.fullmatch(item.name):
                continue
            try:
                # A junction or symlink is unlinked, never followed.
                if item.is_symlink() or (os.name == 'nt' and item.is_junction()):
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, onexc=_liberar_somente_leitura)
                else:
                    continue
                removidas.append(f'{nome_pasta}/{item.name}')
            except OSError as exc:
                log.warning('Preparo abandonado não removido (%s/%s): %s', nome_pasta, item.name, exc.strerror or exc)
    if removidas:
        log.warning('Preparo abandonado removido: %s.', ', '.join(removidas))
    return removidas


def _liberar_somente_leitura(funcao, caminho, _exc):
    # Read-only files (Windows) are made writable and removed once more.
    os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)
    funcao(caminho)


# --- partida e encerramento ------------------------------------------------------------------

def recuperar(root, espera=2.0):
    """At service start: clean what a dead process left, only if the lock can be taken.

    Waits at most ``espera`` seconds (Windows releases a dead process's byte-range lock a moment
    after it ends) and never takes a live lock. Returns a summary for logs and tests:
    ``{'estado': 'livre'|'em_uso'|'sem_casos', 'abandonada': record|None, 'antiga_removida': bool,
    'preparo_removido': [...], 'dono': record}``.
    """
    root = Path(root).resolve()
    pasta = _pasta(root)
    estado = _estado(pasta)
    estado.encerrando = False  # a new start in this process (tests run several servers)
    resumo = {'estado': 'sem_casos', 'abandonada': None, 'antiga_removida': False, 'preparo_removido': [], 'dono': None}
    if not pasta.is_dir():
        return resumo
    if not estado.threads.acquire(blocking=False):
        resumo.update(estado='em_uso', dono=ler_dono(root))
        return resumo
    try:
        limite = time.monotonic() + max(0.0, espera)
        fd = _abrir(pasta / ARQUIVO, max(limite, time.monotonic() + 1))
        try:
            obtida = _tentar(fd)
            while not obtida and time.monotonic() < limite:
                time.sleep(0.05)
                obtida = _tentar(fd)
            if not obtida:
                resumo.update(estado='em_uso', dono=_ler(fd))
                log.warning('Partida: trava de cadastro em uso por outro processo (%s); nada foi limpo.', resumo['dono'])
                return resumo
            try:
                anterior = _ler(fd)
                if anterior and anterior.get('estado') != 'livre':
                    resumo['abandonada'] = anterior
                    log.warning('Partida: trava de cadastro abandonada pelo processo %s em %s, desde %s (%s).',
                                anterior.get('pid', '?'), anterior.get('host', '?'),
                                anterior.get('desde_utc', '?'), anterior.get('operacao') or anterior.get('estado'))
                antiga = pasta / ANTIGA
                if antiga.is_dir() and not antiga.is_symlink():
                    try:
                        antiga.rmdir()  # only when empty, as the old mkdir lock always was
                        resumo['antiga_removida'] = True
                        log.warning('Partida: trava antiga casos/.cadastro.lock removida (versão anterior, sem dono).')
                    except OSError as exc:
                        log.warning('Partida: trava antiga casos/.cadastro.lock não removida: %s', exc.strerror or exc)
                resumo['preparo_removido'] = _limpar_preparo(root)
                if anterior is not None and anterior != LIVRE:
                    _gravar(fd, LIVRE)  # a clean start writes nothing: the file stays as it was
                resumo['estado'] = 'livre'
                return resumo
            finally:
                _soltar(fd)
        finally:
            os.close(fd)
    finally:
        estado.threads.release()


def encerrar(root):
    """Shutdown: waiting operations give up and new ones are refused (until the next start)."""
    estado = _estado(_pasta(root))
    estado.encerrando = True
    with estado.mudou:
        estado.mudou.notify_all()


def aguardar_livre(root, prazo) -> bool:
    """Wait up to ``prazo`` seconds until no thread of this process holds the lock."""
    estado = _estado(_pasta(root))
    limite = time.monotonic() + max(0.0, prazo)
    with estado.mudou:
        while estado.dono is not None:
            restante = limite - time.monotonic()
            if restante <= 0:
                return False
            estado.mudou.wait(min(restante, 0.2))
    return True


def em_uso_neste_processo(root) -> bool:
    return _estado(_pasta(root)).dono is not None


class TravaExclusiva:
    """The same system lock on another file, without waiting (the extraction queue's coordinator).

    ``tentar()`` returns True when this process now holds it; ``soltar()`` releases it. The system
    releases it when the process ends; the file is never deleted.
    """

    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self._fd = None

    def tentar(self) -> bool:
        if self._fd is not None:
            return True
        fd = _abrir(self.caminho, time.monotonic() + 1)
        try:
            if _tentar(fd):
                self._fd = fd
                return True
        except OSError:
            os.close(fd)
            raise
        os.close(fd)
        return False

    @property
    def segura(self) -> bool:
        return self._fd is not None

    def soltar(self):
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                _soltar(fd)
            finally:
                os.close(fd)
