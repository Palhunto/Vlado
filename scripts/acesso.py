"""Hosted access: newsrooms, individual accounts with roles, case ownership and participation, sessions.

Contract: `.maestro/equipe/CONTRATO_CONTAS.md`. Store: `acesso/contas.sqlite` (gitignored), next to the old
`acesso/acesso.json`, or next to the path in VLADO_ACESSO (e.g. a Docker volume). SQLite in WAL mode, foreign keys on,
every write in an immediate transaction. Passwords use argon2id (argon2-cffi). Activation tokens and session ids are
random (secrets.token_urlsafe) and only their SHA-256 is stored. Events never carry passwords, tokens, links or hashes.

Model: a newsroom (`organizacoes`) has accounts (`contas`), each with one role: dono, editor, reporter, leitor, or the
legacy profile convidado. Every case belongs to one newsroom (`casos`: the ownership record, with the account that
answers for it) and an account reaches a case by participation (`participacoes`); a dono reaches every case of the own
newsroom. A case without an ownership record is reached by nobody. `alcance` is the only place that computes reach.

Every event here also goes to the audit log (scripts/registro_acesso.py: JSON lines with UTC time, account, IP and
result, rotated by day, 30 days by default), after the transaction commits. The 1000 newest events stay in the store for
the administration screen; an event pushed out of that window is first copied to the audit log as `evento_arquivado`.

Migration, on first use: an `acesso.json` (v2, or v1 invitations) becomes the store. The installation becomes one
newsroom, every `admin` a dono and every `convidado` keeps the legacy profile, all with the SAME id (authorship in
notes, reviews and conversations is kept); the cases of the catalogue get the ownership of that newsroom; sessions are
dropped. The old file is kept as `acesso.v2.json` (or `acesso.v1.json`). No account reaches more than it did before.
An installation with no account yet: the first account creates the newsroom, which takes the cases already there.

CLI (run on the server; the activation link goes to this terminal's stdout only, or to --saida ARQUIVO with
permission 0600):
  python scripts/acesso.py criar-admin --nome "Editora" --login editora --origem https://vlado.example.org
  python scripts/acesso.py criar-conta --nome "Ana" --login ana.silva --casos caso_a,caso_b --cota 20 --origem ...
  python scripts/acesso.py listar
  python scripts/acesso.py desativar ID | reativar ID
  python scripts/acesso.py recuperar ID --origem https://vlado.example.org
  python scripts/acesso.py casos ID --casos caso_a,caso_b
  python scripts/acesso.py redacao-listar
  python scripts/acesso.py caso-atribuir --caso caso_a --redacao orgID [--responsavel ID]
  python scripts/acesso.py migrar --simular | migrar
"""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import threading
import time
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import ler_json, trava_arquivo  # noqa: E402
import registro_acesso  # noqa: E402

PAPEIS = ('dono', 'editor', 'reporter', 'leitor', 'convidado')
# Names of the two-role model, accepted on input (old CLI, `contas-*` while they exist) and never stored.
PAPEIS_ANTIGOS = {'admin': 'dono'}
RESPONSAVEIS = ('dono', 'reporter')  # who may answer for a case
ATRIBUIVEIS = ('dono', 'editor', 'reporter', 'leitor')  # the legacy `convidado` is never given to anybody again
IDIOMAS = ('pt', 'en')
CLIENTES = ('web', 'android')
ID_CASO = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
ID_CONTA = re.compile(r'[0-9a-f]{16}')
ID_ORGANIZACAO = re.compile(r'org[0-9a-f]{16}')
LOGIN = re.compile(r'[a-z0-9][a-z0-9._-]{2,63}')
SENHA_MIN, SENHA_MAX = 12, 256
SESSAO_HORAS = 12
INATIVIDADE_HORAS = 2
ULTIMO_USO_SEGUNDOS = 60
ATIVACAO_HORAS = 72
ATIVACAO_MAX_HORAS = 168
FALHAS_BLOQUEIO = 5
BLOQUEIO_MINUTOS = 15
TENTATIVAS_IP_MINUTO = 20
MAX_EVENTOS = 1000
MAX_TENTATIVAS_GUARDADAS = 2000
ESQUEMA = 2  # PRAGMA user_version of the store; `_ATUALIZACOES` takes an older store up to it
ESPERA_BD_S = 10
NOME_PADRAO_REDACAO = 'Redação'
CREDENCIAIS = 'Login ou senha incorretos.'
ATIVACAO_INVALIDA = 'Link de ativação inválido ou expirado. Peça um novo link à administração.'
BLOQUEADO = 'Muitas tentativas. Aguarde alguns minutos e tente de novo.'
CONTA_INEXISTENTE = 'Conta não encontrada.'
CASOS_INEXISTENTES = 'Escolha apurações existentes para a conta.'
CASO_INEXISTENTE = 'Apuração não encontrada.'
SESSAO_INEXISTENTE = 'Sessão não encontrada.'
SENHA_NECESSARIA = 'Digite a sua senha para confirmar.'
SENHA_INCORRETA = 'Senha incorreta.'
ULTIMO_DONO = 'A redação precisa de ao menos um dono ativo.'
TETO_INVALIDO = 'Informe o teto em reais, com até duas casas decimais (por exemplo, 50 ou 50.00).'
CHAVE_CONFIRMACAO = '#senha|'  # attempt counter of the password asked again; `#` never starts a login

_HASHER = PasswordHasher()  # library defaults (argon2id); check_needs_rehash follows them
_TRAVA = threading.RLock()
_PRONTOS: set[str] = set()  # stores already prepared by this process
_FICTICIO: dict[int, str] = {}
_IPS: dict[str, deque] = {}
_IPS_TRAVA = threading.Lock()
HASH_ESPERA_S = 10
_HASH_SEMAFORO = threading.BoundedSemaphore(4)  # argon2 uses ~64 MiB per hash: bound concurrent work
SID = re.compile(r'[A-Za-z0-9_-]{43}')  # secrets.token_urlsafe(32)

_TABELAS = """
CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE organizacoes (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'ativa' CHECK (situacao IN ('ativa', 'suspensa', 'encerrada')),
    cota_mensal_brl TEXT, teto_por_pessoa_brl TEXT, criada_em TEXT NOT NULL, criada_por TEXT NOT NULL);
CREATE TABLE contas (
    id TEXT PRIMARY KEY, organizacao TEXT NOT NULL REFERENCES organizacoes(id),
    papel TEXT NOT NULL CHECK (papel IN ('dono', 'editor', 'reporter', 'leitor', 'convidado')),
    nome TEXT NOT NULL, login TEXT UNIQUE, email TEXT UNIQUE, ativa INTEGER NOT NULL DEFAULT 1,
    senha_hash TEXT, senha_definida_em TEXT, cota_diaria INTEGER, teto_mensal_brl TEXT,
    criada_em TEXT NOT NULL, criada_por TEXT NOT NULL, migrada_de_convite INTEGER NOT NULL DEFAULT 0,
    ativacao_sha256 TEXT, ativacao_expira_em TEXT, ativacao_motivo TEXT, idioma TEXT, excluida_em TEXT);
CREATE INDEX contas_por_organizacao ON contas (organizacao);
CREATE INDEX contas_por_ativacao ON contas (ativacao_sha256);
CREATE TABLE casos (
    caso TEXT PRIMARY KEY, organizacao TEXT NOT NULL REFERENCES organizacoes(id),
    responsavel TEXT REFERENCES contas(id), criado_por TEXT, criado_em TEXT NOT NULL, origem TEXT NOT NULL,
    apagada_em TEXT);
CREATE INDEX casos_por_organizacao ON casos (organizacao);
CREATE TABLE participacoes (
    caso TEXT NOT NULL REFERENCES casos(caso), conta TEXT NOT NULL REFERENCES contas(id),
    incluida_por TEXT, incluida_em TEXT NOT NULL, origem TEXT NOT NULL, PRIMARY KEY (caso, conta));
CREATE INDEX participacoes_por_conta ON participacoes (conta);
CREATE TRIGGER participacao_na_mesma_redacao BEFORE INSERT ON participacoes
WHEN (SELECT organizacao FROM contas WHERE id = NEW.conta) IS NOT (SELECT organizacao FROM casos WHERE caso = NEW.caso)
BEGIN SELECT RAISE(ABORT, 'participacao entre redacoes'); END;
CREATE TRIGGER responsavel_na_mesma_redacao_ao_criar BEFORE INSERT ON casos
WHEN NEW.responsavel IS NOT NULL
     AND (SELECT organizacao FROM contas WHERE id = NEW.responsavel) IS NOT NEW.organizacao
BEGIN SELECT RAISE(ABORT, 'responsavel de outra redacao'); END;
CREATE TRIGGER responsavel_na_mesma_redacao_ao_mudar BEFORE UPDATE OF responsavel, organizacao ON casos
WHEN NEW.organizacao IS NOT OLD.organizacao
     OR (NEW.responsavel IS NOT NULL
         AND (SELECT organizacao FROM contas WHERE id = NEW.responsavel) IS NOT NEW.organizacao)
BEGIN SELECT RAISE(ABORT, 'posse nao muda de redacao'); END;
CREATE TRIGGER conta_nao_muda_de_redacao BEFORE UPDATE OF organizacao ON contas
WHEN NEW.organizacao IS NOT OLD.organizacao
BEGIN SELECT RAISE(ABORT, 'conta nao muda de redacao'); END;
CREATE TABLE sessoes (
    id_sha256 TEXT PRIMARY KEY, publico TEXT NOT NULL UNIQUE, conta TEXT NOT NULL REFERENCES contas(id),
    csrf TEXT NOT NULL, criada_em TEXT NOT NULL, expira_em TEXT NOT NULL, ultimo_uso TEXT NOT NULL,
    cliente TEXT NOT NULL DEFAULT 'web', aparelho TEXT, ip_criacao TEXT, ip_ultimo TEXT);
CREATE INDEX sessoes_por_conta ON sessoes (conta);
CREATE TABLE tentativas (chave TEXT PRIMARY KEY, falhas INTEGER NOT NULL DEFAULT 0, bloqueado_ate TEXT, em TEXT);
CREATE TABLE uso_diario (conta TEXT PRIMARY KEY, dia TEXT NOT NULL, feitas INTEGER NOT NULL);
CREATE TABLE eventos (
    n INTEGER PRIMARY KEY AUTOINCREMENT, em TEXT NOT NULL, tipo TEXT NOT NULL, conta TEXT, por TEXT,
    organizacao TEXT);
CREATE INDEX eventos_por_organizacao ON eventos (organizacao, n);
"""
# From each older version of the store to the next one (applied in order, each in one transaction).
_ATUALIZACOES = {1: ('ALTER TABLE contas ADD COLUMN idioma TEXT',
                     'ALTER TABLE contas ADD COLUMN excluida_em TEXT',
                     'ALTER TABLE sessoes ADD COLUMN aparelho TEXT',
                     'ALTER TABLE sessoes ADD COLUMN ip_criacao TEXT',
                     'ALTER TABLE sessoes ADD COLUMN ip_ultimo TEXT',
                     'CREATE INDEX eventos_por_organizacao ON eventos (organizacao, n)')}


class RegistroIlegivel(ValueError):
    """The store cannot be read; the server answers 503 and nobody is let in."""


class CredenciaisInvalidas(ValueError):
    """Unknown login, wrong password, account without password or deactivated: one answer."""


class _VezDoHash:
    """Wait a bounded time for one of the argon2 slots; a flood gets 429, not an ever-growing queue."""

    def __enter__(self):
        if not _HASH_SEMAFORO.acquire(timeout=HASH_ESPERA_S):
            raise Bloqueado(BLOQUEADO)
        return self

    def __exit__(self, *_):
        _HASH_SEMAFORO.release()


class Bloqueado(ValueError):
    """Too many attempts for this login (15 min) or from this address (per minute)."""


class AtivacaoInvalida(ValueError):
    """Unknown, used or expired activation link."""


class PrimeiroAcessoEncerrado(ValueError):
    """The store already has an account: the first-administrator form is gone for good."""


class Recusada(ValueError):
    """A refusal the server answers with its own status and code (the message is the text for the person)."""
    status, codigo, motivo = 400, 'requisicao_invalida', 'validacao'


class SenhaNecessaria(Recusada):
    """A sensitive operation came without the password of who asks."""
    status, codigo, motivo = 403, 'senha_necessaria', 'validacao'


class SenhaIncorreta(Recusada):
    """The password sent to confirm a sensitive operation is wrong (it counts for the attempt ceiling)."""
    status, codigo, motivo = 403, 'senha_atual_incorreta', 'senha_incorreta'


class UltimoDono(Recusada):
    """The newsroom would be left without an active dono."""
    status, codigo, motivo = 400, 'ultimo_dono', 'ultimo_dono'


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(momento: datetime) -> str:
    return momento.strftime('%Y-%m-%dT%H:%M:%SZ')


def _data(texto: str) -> datetime:
    return datetime.strptime(texto, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode('utf-8')).hexdigest()


def caminho(root: Path) -> Path:
    """The old JSON store (read once, by the migration). Its folder holds the SQLite store and the lock file."""
    destino = os.environ.get('VLADO_ACESSO', '').strip()
    return Path(destino) if destino else Path(root) / 'acesso' / 'acesso.json'


def caminho_bd(root: Path) -> Path:
    return caminho(root).with_name('contas.sqlite')


def limpar_limites() -> None:
    """Forget per-address attempt counters (memory only; used by tests and restarts)."""
    with _IPS_TRAVA:
        _IPS.clear()


def papel_valido(papel) -> str:
    """The stored name of a role; the old `admin` reads as `dono`."""
    papel = PAPEIS_ANTIGOS.get(papel, papel) if isinstance(papel, str) else None
    if papel not in PAPEIS:
        raise ValueError('Papel de acesso inválido.')
    return papel


# --- storage -------------------------------------------------------------------------------

def _ilegivel() -> ValueError:
    return RegistroIlegivel('Registro de acesso ilegível; restaure o backup de acesso/.')


class _Tx:
    """One transaction. `depois` runs after the commit (audit lines: never for something rolled back)."""

    def __init__(self, con):
        self.con, self.depois = con, []

    def um(self, sql, *args):
        return self.con.execute(sql, args).fetchone()

    def todos(self, sql, *args):
        return self.con.execute(sql, args).fetchall()

    def ex(self, sql, *args):
        return self.con.execute(sql, args)


def _desfazer(con) -> None:
    try:
        con.execute('ROLLBACK')
    except sqlite3.Error:
        pass


@contextmanager
def _bd(root: Path, escrever: bool = False):
    """A transaction on the store (immediate when writing). Any SQLite failure reads as an unreadable store."""
    registro_acesso.lembrar_raiz(root)  # the audit log follows the data root unless VLADO_REGISTRO says otherwise
    arquivo = _preparar(Path(root))
    try:
        con = sqlite3.connect(str(arquivo), timeout=ESPERA_BD_S, isolation_level=None)
    except sqlite3.Error as exc:
        raise _ilegivel() from exc
    tx = _Tx(con)
    try:
        try:
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA foreign_keys = ON')
            if con.execute('PRAGMA user_version').fetchone()[0] != ESQUEMA:
                raise _ilegivel()
            con.execute('BEGIN IMMEDIATE' if escrever else 'BEGIN')
        except sqlite3.Error as exc:
            raise _ilegivel() from exc
        try:
            yield tx
        except sqlite3.Error as exc:
            _desfazer(con)
            raise _ilegivel() from exc
        except BaseException:
            _desfazer(con)
            raise
        try:
            con.execute('COMMIT')
        except sqlite3.Error as exc:
            _desfazer(con)
            raise _ilegivel() from exc
    finally:
        con.close()
    for chamada in tx.depois:
        chamada()


def _preparar(root: Path) -> Path:
    """The store's file, created or migrated on first use (once per process; other processes wait on the lock)."""
    bd = caminho_bd(root)
    chave = str(bd)
    if chave in _PRONTOS and bd.is_file():
        return bd
    with _TRAVA, trava_arquivo(caminho(root)):
        antigo = caminho(root)
        if not bd.is_file():
            if antigo.is_file():
                _migrar_json(root, antigo, bd)
            else:
                _criar_bd(bd)
        elif antigo.is_file():
            # A stop between the two renames of a migration: the store is whole, the old file is put aside now.
            _guardar_antigo(antigo, _versao_do_json(antigo))
        try:
            con = sqlite3.connect(str(bd), timeout=ESPERA_BD_S, isolation_level=None)
            try:
                con.execute('PRAGMA journal_mode = WAL')
                _atualizar_esquema(con)
            finally:
                con.close()
        except sqlite3.Error as exc:
            raise _ilegivel() from exc
        _PRONTOS.add(chave)
    return bd


def _atualizar_esquema(con) -> None:
    """Take an older store up to ESQUEMA, one version at a time. A store newer than this code is left alone
    (it then reads as unreadable: nobody gets in with half-understood data)."""
    versao = con.execute('PRAGMA user_version').fetchone()[0]
    while versao in _ATUALIZACOES and versao < ESQUEMA:
        con.execute('BEGIN IMMEDIATE')
        try:
            if con.execute('PRAGMA user_version').fetchone()[0] == versao:  # another process may have done it
                for comando in _ATUALIZACOES[versao]:
                    con.execute(comando)
                con.execute(f'PRAGMA user_version = {versao + 1}')
            con.execute('COMMIT')
        except sqlite3.Error:
            _desfazer(con)
            raise
        versao = con.execute('PRAGMA user_version').fetchone()[0]


def _trocar(origem: Path, destino: Path, tentativas: int = 40) -> None:
    for tentativa in range(tentativas):
        try:
            os.replace(origem, destino)
            return
        except PermissionError:  # Windows: another reader or an antivirus scan holds the file for a moment
            if tentativa >= tentativas - 1:
                raise
            time.sleep(0.025)


def _criar_bd(bd: Path, povoar=None) -> None:
    """Build the store in a temporary file and rename it: a stop in the middle leaves no half store."""
    bd.parent.mkdir(parents=True, exist_ok=True)
    temporario = bd.with_name(f'{bd.name}.{secrets.token_hex(6)}.tmp')
    try:
        con = sqlite3.connect(str(temporario), isolation_level=None)
        try:
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA foreign_keys = ON')
            con.execute('BEGIN')
            for comando in _comandos(_TABELAS):
                con.execute(comando)
            if povoar is not None:
                povoar(_Tx(con))
            con.execute(f'PRAGMA user_version = {ESQUEMA}')
            con.execute('COMMIT')
        finally:
            con.close()
        try:
            os.chmod(temporario, 0o600)
        except OSError:
            pass
        _trocar(temporario, bd)
    except sqlite3.Error as exc:
        raise _ilegivel() from exc
    finally:
        temporario.unlink(missing_ok=True)


def _comandos(texto: str) -> list[str]:
    """Split the schema into statements (a trigger body has its own semicolons)."""
    comandos, atual = [], ''
    for linha in texto.strip().splitlines():
        atual += linha + '\n'
        if sqlite3.complete_statement(atual):
            comandos.append(atual)
            atual = ''
    return comandos


def _evento(tx: _Tx, tipo: str, conta: str | None, por: str | None, momento: datetime | None = None,
            organizacao: str | None = None, **detalhes) -> None:
    """Audit trail: type, account, author and time only (never secrets). The audit log adds the client IP and
    the few allowed details (`detalhes`: changed fields, role), once the transaction commits."""
    momento = momento or agora()
    if organizacao is None and conta:
        dona = tx.um('SELECT organizacao FROM contas WHERE id = ?', conta)
        organizacao = dona['organizacao'] if dona else None
    tx.ex('INSERT INTO eventos (em, tipo, conta, por, organizacao) VALUES (?, ?, ?, ?, ?)',
          _iso(momento), tipo, conta, por, organizacao)
    tx.depois.append(lambda: registro_acesso.do_acesso(tipo, conta, por, momento, organizacao=organizacao, **detalhes))
    # The window is of each newsroom: the activity of one never pushes out the activity of another.
    excesso = tx.um('SELECT COUNT(*) AS total FROM eventos WHERE organizacao IS ?', organizacao)['total'] - MAX_EVENTOS
    if excesso > 0:  # leaving the window is not silent: it goes to the audit log
        for antigo in tx.todos('SELECT n, em, tipo, conta, por FROM eventos WHERE organizacao IS ? ORDER BY n LIMIT ?',
                               organizacao, excesso):
            copia = {k: antigo[k] for k in ('em', 'tipo', 'conta', 'por')}
            tx.depois.append(lambda copia=copia: registro_acesso.arquivar_evento(copia))
            tx.ex('DELETE FROM eventos WHERE n = ?', antigo['n'])


def _meta(tx: _Tx, chave: str) -> str | None:
    linha = tx.um('SELECT valor FROM meta WHERE chave = ?', chave)
    return linha['valor'] if linha else None


def _definir_meta(tx: _Tx, chave: str, valor: str) -> None:
    tx.ex('INSERT INTO meta (chave, valor) VALUES (?, ?) ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor',
          chave, valor)


def _login_de_nome(nome: str, usados: set[str]) -> str:
    base = unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode('ascii').lower()
    base = re.sub(r'[^a-z0-9]+', '.', base).strip('._-')[:56] or 'conta'
    if len(base) < 3:
        base = f'conta.{base}'
    login, numero = base, 2
    while login in usados:
        login, numero = f'{base}-{numero}', numero + 1
    usados.add(login)
    return login


def _casos_do_catalogo(root: Path) -> list[str]:
    """Ids of the cases of this installation (the ones in the trash too). Metadata only, no case content."""
    arquivo = Path(root) / 'casos' / 'catalogo.json'
    if not arquivo.is_file():
        return []
    try:
        casos = ler_json(arquivo)['casos']
        return sorted({c['id'] for c in casos if isinstance(c.get('id'), str) and ID_CASO.fullmatch(c['id'])})
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Catálogo de apurações ilegível; a posse das apurações não pôde ser registrada.') from exc


def _nova_organizacao(tx: _Tx, nome: str, por: str, momento: datetime) -> str:
    oid = 'org' + secrets.token_hex(8)
    while tx.um('SELECT 1 FROM organizacoes WHERE id = ?', oid):
        oid = 'org' + secrets.token_hex(8)
    tx.ex('INSERT INTO organizacoes (id, nome, criada_em, criada_por) VALUES (?, ?, ?, ?)', oid, nome, _iso(momento), por)
    return oid


def _nome_da_redacao_inicial() -> str:
    nome = os.environ.get('VLADO_REDACAO_NOME', '').strip()
    return nome[:120] if nome and not any(ord(c) < 32 for c in nome) else NOME_PADRAO_REDACAO


def _redacao_inicial(tx: _Tx, root: Path, por: str, momento: datetime, origem: str) -> str:
    """The newsroom an installation starts with: it takes the cases that are already in the catalogue."""
    oid = _nova_organizacao(tx, _nome_da_redacao_inicial(), por, momento)
    for caso in _casos_do_catalogo(root):
        if not tx.um('SELECT 1 FROM casos WHERE caso = ?', caso):
            tx.ex('INSERT INTO casos (caso, organizacao, criado_em, origem) VALUES (?, ?, ?, ?)',
                  caso, oid, _iso(momento), origem)
    _definir_meta(tx, 'organizacao_inicial', oid)
    return oid


# --- migration of the JSON store -----------------------------------------------------------------

def _versao_do_json(arquivo: Path) -> int:
    try:
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
        return 1 if isinstance(dados, dict) and dados.get('versao') in (None, 1) else 2
    except (OSError, ValueError):
        return 2


def _ler_json_antigo(arquivo: Path) -> tuple[dict, int]:
    """The old store as a v2 dictionary and the version it was in. Anything else is refused, never overwritten."""
    try:
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise _ilegivel() from exc
    if not isinstance(dados, dict):
        raise _ilegivel()
    origem = 2
    if dados.get('versao') != 2:
        if dados.get('versao') not in (None, 1) or not isinstance(dados.get('convites'), dict):
            raise _ilegivel()
        dados, origem = _v1_para_v2(dados), 1
    for chave, tipo in (('contas', dict), ('sessoes', dict), ('tentativas', dict), ('uso', dict), ('eventos', list)):
        dados.setdefault(chave, tipo())
        if not isinstance(dados[chave], tipo):
            raise _ilegivel()
    return dados, origem


def _v1_para_v2(v1: dict) -> dict:
    """Invitations (v1) as accounts without password, with the SAME id; v1 sessions are dropped."""
    dados, usados, momento = {'versao': 2, 'contas': {}, 'sessoes': {}, 'tentativas': {}, 'uso': {}, 'eventos': []}, set(), agora()
    convites = sorted((v1.get('convites') or {}).items(), key=lambda item: str(item[1].get('criado_em', '')))
    for cid, convite in convites:
        if not isinstance(convite, dict) or convite.get('papel') not in ('admin', 'convidado'):
            continue
        papel = convite['papel']
        casos = [c for c in (convite.get('casos') if isinstance(convite.get('casos'), list) else [])
                 if isinstance(c, str) and ID_CASO.fullmatch(c)]
        cota = convite.get('cota_diaria')
        dados['contas'][cid] = {
            'nome': str(convite.get('nome') or cid)[:120], 'login': _login_de_nome(str(convite.get('nome') or ''), usados),
            'papel': papel, 'casos': sorted(set(casos)) if papel == 'convidado' else None,
            'cota_diaria': (cota if type(cota) is int and 1 <= cota <= 500 else 20) if papel == 'convidado' else None,
            'ativa': not convite.get('revogado'), 'senha_hash': None, 'senha_definida_em': None,
            'criada_em': convite.get('criado_em') or _iso(momento), 'criada_por': 'migracao',
            'migrada_de_convite': True}
    dados['uso'] = {k: v for k, v in (v1.get('uso') or {}).items() if k in dados['contas'] and isinstance(v, dict)}
    dados['eventos'].append({'em': _iso(momento), 'tipo': 'migracao_v1', 'conta': None, 'por': 'migracao'})
    return dados


def _plano_de_migracao(root: Path, dados: dict) -> dict:
    """What the migration does with a v2 dictionary: accounts by role, cases, participations dropped. No secrets."""
    catalogo = set(_casos_do_catalogo(root))
    contas, descartadas, sem_papel = [], [], []
    for cid, conta in dados['contas'].items():
        if not isinstance(cid, str) or not isinstance(conta, dict) or conta.get('papel') not in ('admin', 'convidado'):
            sem_papel.append(str(cid))
            continue
        papel = 'dono' if conta['papel'] == 'admin' else 'convidado'
        pedidos = [c for c in (conta.get('casos') or []) if isinstance(c, str)] if papel == 'convidado' else []
        casos = sorted(set(pedidos) & catalogo)
        descartadas += [{'conta': cid, 'caso': c} for c in sorted(set(pedidos) - catalogo)]
        contas.append({'id': cid, 'papel': papel, 'casos': casos})
    return {'redacao': _nome_da_redacao_inicial(), 'contas': contas, 'apuracoes': sorted(catalogo),
            'participacoes_descartadas': descartadas, 'contas_ignoradas': sem_papel,
            'resumo': {'donos': sum(1 for c in contas if c['papel'] == 'dono'),
                       'convidados': sum(1 for c in contas if c['papel'] == 'convidado'),
                       'apuracoes': len(catalogo), 'participacoes': sum(len(c['casos']) for c in contas),
                       'participacoes_descartadas': len(descartadas), 'contas_sem_email': len(contas),
                       'sessoes_encerradas': len(dados['sessoes'])}}


def _povoar_de_v2(tx: _Tx, root: Path, dados: dict, origem: int) -> None:
    momento = agora()
    plano = _plano_de_migracao(root, dados)
    oid = _redacao_inicial(tx, root, 'migracao', momento, 'migracao')
    dia = momento.strftime('%Y-%m-%d')
    for item in plano['contas']:
        cid, conta = item['id'], dados['contas'][item['id']]
        ativacao = conta.get('ativacao') if isinstance(conta.get('ativacao'), dict) else {}
        cota = conta.get('cota_diaria')
        tx.ex('INSERT INTO contas (id, organizacao, papel, nome, login, ativa, senha_hash, senha_definida_em, cota_diaria,'
              ' criada_em, criada_por, migrada_de_convite, ativacao_sha256, ativacao_expira_em, ativacao_motivo)'
              ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
              cid, oid, item['papel'], str(conta.get('nome') or cid)[:120], conta.get('login'),
              1 if conta.get('ativa') else 0, conta.get('senha_hash'), conta.get('senha_definida_em'),
              (cota if type(cota) is int and 1 <= cota <= 500 else 20) if item['papel'] == 'convidado' else None,
              conta.get('criada_em') or _iso(momento), str(conta.get('criada_por') or 'migracao'),
              1 if conta.get('migrada_de_convite') else 0,
              ativacao.get('token_sha256'), ativacao.get('expira_em'), ativacao.get('motivo'))
        for caso in item['casos']:
            tx.ex('INSERT INTO participacoes (caso, conta, incluida_por, incluida_em, origem) VALUES (?, ?, ?, ?, ?)',
                  caso, cid, 'migracao', _iso(momento), 'migracao')
        feitas = (dados['uso'].get(cid) or {}).get(dia) if isinstance(dados['uso'].get(cid), dict) else None
        if type(feitas) is int and feitas > 0:
            tx.ex('INSERT INTO uso_diario (conta, dia, feitas) VALUES (?, ?, ?)', cid, dia, feitas)
    for evento in dados['eventos'][-MAX_EVENTOS:]:
        if isinstance(evento, dict) and isinstance(evento.get('tipo'), str):
            tx.ex('INSERT INTO eventos (em, tipo, conta, por, organizacao) VALUES (?, ?, ?, ?, ?)',
                  str(evento.get('em') or _iso(momento)), evento['tipo'],
                  evento.get('conta') if isinstance(evento.get('conta'), str) else None,
                  evento.get('por') if isinstance(evento.get('por'), str) else None, oid)
    if dados.get('primeiro_admin_em'):
        _definir_meta(tx, 'primeiro_admin_em', str(dados['primeiro_admin_em']))
    _definir_meta(tx, 'migrado_de', f'acesso.json v{origem}')
    _definir_meta(tx, 'migrado_em', _iso(momento))
    _definir_meta(tx, 'relatorio_migracao', json.dumps({k: plano[k] for k in (
        'redacao', 'resumo', 'participacoes_descartadas', 'contas_ignoradas')}, ensure_ascii=False))
    _evento(tx, 'migracao_contas', None, 'migracao', momento, organizacao=oid)


def _guardar_antigo(antigo: Path, origem: int) -> None:
    copia = antigo.with_name(f'acesso.v{origem}.json')
    if copia.exists():
        copia = antigo.with_name(f'acesso.v{origem}.{agora().strftime("%Y%m%dT%H%M%S%f")}.json')
    _trocar(antigo, copia)
    try:
        os.chmod(copia, 0o600)
    except OSError:
        pass


def _migrar_json(root: Path, antigo: Path, bd: Path) -> None:
    """acesso.json becomes the store. The old file is put aside only after the store is in place."""
    dados, origem = _ler_json_antigo(antigo)
    tx_depois = []

    def povoar(tx):
        _povoar_de_v2(tx, root, dados, origem)
        tx_depois.extend(tx.depois)
    _criar_bd(bd, povoar)
    _guardar_antigo(antigo, origem)
    for chamada in tx_depois:
        chamada()


def simular_migracao(root: Path) -> dict:
    """Report of what `migrar` would do, without writing anything. No name, login, hash or token in it."""
    antigo = caminho(root)
    if caminho_bd(root).is_file():
        return {'estado': 'ja_migrado', **relatorio_migracao(root)}
    if not antigo.is_file():
        return {'estado': 'sem_registro_antigo'}
    dados, origem = _ler_json_antigo(antigo)
    plano = _plano_de_migracao(root, dados)
    return {'estado': 'a_migrar', 'origem': f'acesso.json v{origem}', 'redacao': plano['redacao'], 'resumo': plano['resumo'],
            'participacoes_descartadas': plano['participacoes_descartadas'], 'contas_ignoradas': plano['contas_ignoradas']}


def relatorio_migracao(root: Path) -> dict:
    with _bd(root) as tx:
        bruto = _meta(tx, 'relatorio_migracao')
        return {'origem': _meta(tx, 'migrado_de'), 'migrado_em': _meta(tx, 'migrado_em'),
                **(json.loads(bruto) if bruto else {})}


# --- validation and public view ---------------------------------------------------------------

def _validar_nome(nome) -> str:
    if not isinstance(nome, str) or not nome.strip() or len(nome) > 120 or any(ord(c) < 32 for c in nome):
        raise ValueError('Informe o nome da pessoa (até 120 caracteres).')
    return nome.strip()


def _validar_login(login) -> str:
    if not isinstance(login, str) or not LOGIN.fullmatch(login.strip().lower()):
        raise ValueError('Login inválido: use de 3 a 64 letras minúsculas, números, ponto, hífen ou sublinhado, '
                         'começando por letra ou número.')
    return login.strip().lower()


def _validar_casos(casos, vazio: bool = False) -> list[str]:
    if (not isinstance(casos, (list, tuple)) or (not casos and not vazio) or len(casos) > 50
            or not all(isinstance(c, str) and ID_CASO.fullmatch(c) for c in casos)):
        raise ValueError('Escolha ao menos uma apuração válida para a conta convidada.')
    return sorted(set(casos))


def _validar_cota(cota) -> int:
    if type(cota) is not int or not 1 <= cota <= 500:
        raise ValueError('A cota diária deve ser um número entre 1 e 500.')
    return cota


def _validar_horas(horas) -> int:
    if type(horas) is not int or not 1 <= horas <= ATIVACAO_MAX_HORAS:
        raise ValueError(f'A validade do link deve ficar entre 1 e {ATIVACAO_MAX_HORAS} horas.')
    return horas


def _validar_senha(senha) -> str:
    if not isinstance(senha, str) or not SENHA_MIN <= len(senha) <= SENHA_MAX:
        raise ValueError(f'A senha deve ter de {SENHA_MIN} a {SENHA_MAX} caracteres.')
    return senha


def _situacao(conta) -> str:
    if conta['excluida_em']:
        return 'excluida'
    if not conta['ativa']:
        return 'desativada'
    return 'ativa' if conta['senha_hash'] else 'aguardando_senha'


def _participacoes(tx: _Tx, cid: str) -> list[str]:
    return [linha['caso'] for linha in tx.todos(
        'SELECT p.caso FROM participacoes p JOIN casos c ON c.caso = p.caso'
        ' WHERE p.conta = ? AND c.apagada_em IS NULL ORDER BY p.caso', cid)]


def _publico(tx: _Tx, conta, momento: datetime | None = None) -> dict:
    """`casos` are the participations; None for a dono, who reaches every case of the newsroom."""
    expira = conta['ativacao_expira_em']
    return {'id': conta['id'], 'nome': conta['nome'], 'login': conta['login'], 'email': conta['email'],
            'papel': conta['papel'], 'organizacao': conta['organizacao'],
            'casos': None if conta['papel'] == 'dono' else _participacoes(tx, conta['id']),
            'cota_diaria': conta['cota_diaria'], 'teto_mensal_brl': conta['teto_mensal_brl'],
            'idioma': conta['idioma'] or IDIOMAS[0], 'ativa': bool(conta['ativa']),
            'situacao': _situacao(conta), 'criada_em': conta['criada_em'],
            'senha_definida_em': conta['senha_definida_em'], 'ativacao_expira_em': expira,
            'ativacao_vencida': bool(expira and _data(expira) <= (momento or agora())),
            'migrada_de_convite': bool(conta['migrada_de_convite'])}


def _conta(tx: _Tx, cid, organizacao: str | None = None):
    """The account, or the same refusal for an unknown id, for an account of another newsroom and for one that
    was removed (only its id is left)."""
    conta = tx.um('SELECT * FROM contas WHERE id = ?', cid) if isinstance(cid, str) else None
    if not conta or conta['excluida_em'] or (organizacao is not None and conta['organizacao'] != organizacao):
        raise ValueError(CONTA_INEXISTENTE)
    return conta


def _eh_conta(tx: _Tx, quem) -> bool:
    return bool(isinstance(quem, str) and ID_CONTA.fullmatch(quem) and tx.um('SELECT 1 FROM contas WHERE id = ?', quem))


def _donos_ativos(tx: _Tx, organizacao: str, exceto: str | None = None) -> int:
    return tx.um("SELECT COUNT(*) AS total FROM contas WHERE organizacao = ? AND papel = 'dono' AND ativa = 1 AND id IS NOT ?",
                 organizacao, exceto)['total']


def _derrubar_sessoes(tx: _Tx, cid: str) -> None:
    tx.ex('DELETE FROM sessoes WHERE conta = ?', cid)


def _emitir_ativacao(tx: _Tx, cid: str, horas: int, motivo: str, momento: datetime) -> str:
    token = secrets.token_urlsafe(32)
    tx.ex('UPDATE contas SET ativacao_sha256 = ?, ativacao_expira_em = ?, ativacao_motivo = ? WHERE id = ?',
          _hash(token), _iso(momento + timedelta(hours=horas)), motivo, cid)
    return token


def _sem_responsabilidade(tx: _Tx, cid: str, casos=None) -> None:
    """The cases this account answers for are left without one (the dono names another)."""
    if casos is None:
        tx.ex('UPDATE casos SET responsavel = NULL WHERE responsavel = ?', cid)
    for caso in casos or ():
        tx.ex('UPDATE casos SET responsavel = NULL WHERE responsavel = ? AND caso = ?', cid, caso)


def _definir_participacoes(tx: _Tx, conta, casos: list[str], por: str, momento: datetime) -> None:
    """Replace the account's participations by `casos`, all of its own newsroom. Only the terminal (`por` is not an
    account) may name a case nobody owns yet: it gets the ownership of this newsroom, like `caso-atribuir`."""
    cid, org, terminal = conta['id'], conta['organizacao'], not _eh_conta(tx, por)
    for caso in casos:
        posse_ = tx.um('SELECT organizacao, apagada_em FROM casos WHERE caso = ?', caso)
        if posse_ is None:
            if not terminal:
                raise ValueError(CASOS_INEXISTENTES)
            tx.ex('INSERT INTO casos (caso, organizacao, criado_em, origem) VALUES (?, ?, ?, ?)',
                  caso, org, _iso(momento), 'operador')
        elif posse_['organizacao'] != org or posse_['apagada_em']:
            raise ValueError(CASOS_INEXISTENTES)
    atuais = {linha['caso'] for linha in tx.todos('SELECT caso FROM participacoes WHERE conta = ?', cid)}
    for caso in atuais - set(casos):
        tx.ex('DELETE FROM participacoes WHERE conta = ? AND caso = ?', cid, caso)
    _sem_responsabilidade(tx, cid, atuais - set(casos))
    for caso in set(casos) - atuais:
        tx.ex('INSERT INTO participacoes (caso, conta, incluida_por, incluida_em, origem) VALUES (?, ?, ?, ?, ?)',
              caso, cid, por, _iso(momento), 'inclusao')


# --- newsrooms --------------------------------------------------------------------------------

def _organizacao_para(tx: _Tx, root: Path, organizacao, por: str, momento: datetime) -> str:
    """The newsroom of a new account: the one given, the one of the account that creates it, or the only one of the
    installation (created now, with the cases already there, when there is none yet)."""
    if organizacao is not None:
        if not isinstance(organizacao, str) or not tx.um('SELECT 1 FROM organizacoes WHERE id = ?', organizacao):
            raise ValueError('Redação não encontrada.')
        return organizacao
    if _eh_conta(tx, por):
        return tx.um('SELECT organizacao FROM contas WHERE id = ?', por)['organizacao']
    existentes = tx.todos('SELECT id FROM organizacoes ORDER BY criada_em LIMIT 2')
    if not existentes:
        return _redacao_inicial(tx, root, por, momento, 'instalacao')
    if len(existentes) > 1:
        raise ValueError('Há mais de uma redação nesta instalação: informe a redação da conta.')
    return existentes[0]['id']


def criar_redacao(root: Path, nome, por='operador') -> dict:
    """A new, empty newsroom (the operator's act; no route creates one)."""
    nome = _validar_nome(nome)
    with _bd(root, escrever=True) as tx:
        momento = agora()
        oid = _nova_organizacao(tx, nome, por, momento)
        if not _meta(tx, 'organizacao_inicial') and tx.um('SELECT COUNT(*) AS total FROM organizacoes')['total'] == 1:
            _definir_meta(tx, 'organizacao_inicial', oid)
        _evento(tx, 'redacao_criada', None, por, momento, organizacao=oid)
        return {'id': oid, 'nome': nome, 'situacao': 'ativa'}


def listar_redacoes(root: Path) -> list[dict]:
    """Totals only: no name of person or of case."""
    with _bd(root) as tx:
        return [{'id': o['id'], 'nome': o['nome'], 'situacao': o['situacao'], 'criada_em': o['criada_em'],
                 'pessoas': tx.um('SELECT COUNT(*) AS total FROM contas WHERE organizacao = ?', o['id'])['total'],
                 'apuracoes': tx.um('SELECT COUNT(*) AS total FROM casos WHERE organizacao = ? AND apagada_em IS NULL',
                                    o['id'])['total']}
                for o in tx.todos('SELECT * FROM organizacoes ORDER BY criada_em, id')]


def total_redacoes(root: Path) -> int:
    with _bd(root) as tx:
        return tx.um('SELECT COUNT(*) AS total FROM organizacoes')['total']


def organizacao_inicial(root: Path) -> str | None:
    """The newsroom the installation started with (the one that inherits what was of the whole installation)."""
    with _bd(root) as tx:
        return _meta(tx, 'organizacao_inicial')


def definir_situacao_redacao(root: Path, organizacao, situacao, por='operador') -> dict:
    if situacao not in ('ativa', 'suspensa', 'encerrada'):
        raise ValueError('Situação de redação inválida.')
    with _bd(root, escrever=True) as tx:
        if not isinstance(organizacao, str) or not tx.um('SELECT 1 FROM organizacoes WHERE id = ?', organizacao):
            raise ValueError('Redação não encontrada.')
        tx.ex('UPDATE organizacoes SET situacao = ? WHERE id = ?', situacao, organizacao)
        _evento(tx, 'redacao_' + {'ativa': 'reativada', 'suspensa': 'suspensa', 'encerrada': 'encerrada'}[situacao],
                None, por, organizacao=organizacao)
        linha = tx.um('SELECT id, nome, situacao FROM organizacoes WHERE id = ?', organizacao)
        return dict(linha)


def organizacao_da_conta(root: Path, cid) -> str | None:
    """The newsroom whose budget an account spends (None for an unknown account, as in the local mode)."""
    if not isinstance(cid, str) or not ID_CONTA.fullmatch(cid):
        return None
    with _bd(root) as tx:
        linha = tx.um('SELECT organizacao FROM contas WHERE id = ?', cid)
        return linha['organizacao'] if linha else None


def tetos_de_custo(root: Path, cid) -> dict | None:
    """Monthly ceilings in reais for the cost module, as decimal text ('50.00'); None where neither the dono nor the
    operator set one (the installation's default applies). `pessoa_brl` is the account's own ceiling or, without
    one, the newsroom's default per person; `redacao_brl` the newsroom's. None for an unknown account."""
    if not isinstance(cid, str) or not ID_CONTA.fullmatch(cid):
        return None
    with _bd(root) as tx:
        linha = tx.um('SELECT c.organizacao, c.teto_mensal_brl, o.teto_por_pessoa_brl, o.cota_mensal_brl'
                      ' FROM contas c JOIN organizacoes o ON o.id = c.organizacao WHERE c.id = ?', cid)
        if not linha:
            return None
        return {'organizacao': linha['organizacao'], 'pessoa_brl': linha['teto_mensal_brl'] or linha['teto_por_pessoa_brl'],
                'redacao_brl': linha['cota_mensal_brl']}


# --- case ownership and participation -----------------------------------------------------------

def _alcance(tx: _Tx, conta) -> tuple[list[str], list[str]]:
    """THE reach of an account: (cases it reaches, cases it answers for). A dono reaches every case of the own
    newsroom; everybody else, the cases they take part in. Deleted cases are reached by nobody."""
    if conta['papel'] == 'dono':
        casos = [l['caso'] for l in tx.todos(
            'SELECT caso FROM casos WHERE organizacao = ? AND apagada_em IS NULL ORDER BY caso', conta['organizacao'])]
    else:
        casos = _participacoes(tx, conta['id'])
    responsavel = [l['caso'] for l in tx.todos(
        'SELECT caso FROM casos WHERE responsavel = ? AND organizacao = ? AND apagada_em IS NULL ORDER BY caso',
        conta['id'], conta['organizacao'])] if conta['papel'] in RESPONSAVEIS else []
    return casos, [c for c in responsavel if c in set(casos)]


def alcance(root: Path, cid) -> tuple[frozenset, frozenset]:
    """(cases the account reaches, cases it answers for); empty for an unknown or inactive account."""
    with _bd(root) as tx:
        conta = tx.um('SELECT * FROM contas WHERE id = ?', cid) if isinstance(cid, str) else None
        if not conta or not conta['ativa']:
            return frozenset(), frozenset()
        casos, responsavel = _alcance(tx, conta)
        return frozenset(casos), frozenset(responsavel)


def posse(root: Path, caso) -> dict | None:
    """Ownership record of a case, or None. For the gate's audit reason and for the terminal; never sent to a browser."""
    if not isinstance(caso, str) or not ID_CASO.fullmatch(caso):
        return None
    with _bd(root) as tx:
        linha = tx.um('SELECT caso, organizacao, responsavel, origem, apagada_em FROM casos WHERE caso = ?', caso)
        return dict(linha) if linha else None


def registrar_caso(root: Path, caso: str, cid: str) -> None:
    """A case created in the Mesa: it belongs to the creator's newsroom, and the creator answers for it."""
    if not isinstance(caso, str) or not ID_CASO.fullmatch(caso):
        raise ValueError(CASO_INEXISTENTE)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid)
        if conta['papel'] not in RESPONSAVEIS or tx.um('SELECT 1 FROM casos WHERE caso = ?', caso):
            raise ValueError(CASO_INEXISTENTE)
        momento = agora()
        tx.ex('INSERT INTO casos (caso, organizacao, responsavel, criado_por, criado_em, origem) VALUES (?, ?, ?, ?, ?, ?)',
              caso, conta['organizacao'], cid, cid, _iso(momento), 'mesa')
        tx.ex('INSERT INTO participacoes (caso, conta, incluida_por, incluida_em, origem) VALUES (?, ?, ?, ?, ?)',
              caso, cid, cid, _iso(momento), 'criacao')
        _evento(tx, 'caso_criado', cid, cid, momento)


def descartar_caso_sem_arquivos(root: Path, caso: str) -> None:
    """Undo `registrar_caso` when the creation was refused before anything of the case existed."""
    with _bd(root, escrever=True) as tx:
        if tx.um("SELECT 1 FROM casos WHERE caso = ? AND origem = 'mesa'", caso):
            tx.ex('DELETE FROM participacoes WHERE caso = ?', caso)
            tx.ex('DELETE FROM casos WHERE caso = ?', caso)


def atribuir_caso(root: Path, caso, organizacao, responsavel=None, por='operador') -> dict:
    """Give ownership to a case that has none (one created at the terminal). The operator's act."""
    if not isinstance(caso, str) or not ID_CASO.fullmatch(caso):
        raise ValueError(CASO_INEXISTENTE)
    with _bd(root, escrever=True) as tx:
        if not isinstance(organizacao, str) or not tx.um('SELECT 1 FROM organizacoes WHERE id = ?', organizacao):
            raise ValueError('Redação não encontrada.')
        if tx.um('SELECT 1 FROM casos WHERE caso = ?', caso):
            raise ValueError('Esta apuração já pertence a uma redação; a posse não muda de redação.')
        momento = agora()
        if responsavel is not None:
            conta = _conta(tx, responsavel, organizacao)
            if conta['papel'] not in RESPONSAVEIS:
                raise ValueError('O responsável por uma apuração precisa ser dono ou repórter da redação.')
        tx.ex('INSERT INTO casos (caso, organizacao, responsavel, criado_por, criado_em, origem) VALUES (?, ?, ?, ?, ?, ?)',
              caso, organizacao, responsavel, por, _iso(momento), 'operador')
        if responsavel is not None:
            tx.ex('INSERT INTO participacoes (caso, conta, incluida_por, incluida_em, origem) VALUES (?, ?, ?, ?, ?)',
                  caso, responsavel, por, _iso(momento), 'inclusao')
        _evento(tx, 'caso_atribuido', responsavel, por, momento, organizacao=organizacao)
        return {'caso': caso, 'organizacao': organizacao, 'responsavel': responsavel}


def marcar_caso_apagado(root: Path, caso) -> None:
    """After the definitive deletion: the record stays as a mark nobody reaches, and the id is never used again."""
    if not isinstance(caso, str):
        return
    with _bd(root, escrever=True) as tx:
        if tx.um('SELECT 1 FROM casos WHERE caso = ? AND apagada_em IS NULL', caso):
            tx.ex('DELETE FROM participacoes WHERE caso = ?', caso)
            tx.ex('UPDATE casos SET apagada_em = ?, responsavel = NULL WHERE caso = ?', _iso(agora()), caso)


def _caso_da_redacao(tx: _Tx, caso, organizacao: str):
    linha = tx.um('SELECT * FROM casos WHERE caso = ?', caso) if isinstance(caso, str) else None
    if not linha or linha['organizacao'] != organizacao or linha['apagada_em']:
        raise ValueError(CASO_INEXISTENTE)
    return linha


def participantes(root: Path, caso, organizacao: str) -> dict:
    """Who is in a case of this newsroom. Names of colleagues only; nothing of the case itself."""
    with _bd(root) as tx:
        posse_ = _caso_da_redacao(tx, caso, organizacao)
        pessoas = tx.todos('SELECT c.id, c.nome, c.papel, c.ativa FROM participacoes p JOIN contas c ON c.id = p.conta'
                           ' WHERE p.caso = ? ORDER BY c.nome, c.id', caso)
        return {'caso': caso, 'responsavel': posse_['responsavel'],
                'participantes': [{'id': p['id'], 'nome': p['nome'], 'papel': p['papel'], 'ativa': bool(p['ativa']),
                                   'responsavel': p['id'] == posse_['responsavel']} for p in pessoas]}


def incluir_participante(root: Path, caso, cid, por: str, organizacao: str) -> dict:
    with _bd(root, escrever=True) as tx:
        _caso_da_redacao(tx, caso, organizacao)
        conta = _conta(tx, cid, organizacao)  # an account of another newsroom reads as unknown
        if not tx.um('SELECT 1 FROM participacoes WHERE caso = ? AND conta = ?', caso, cid):
            momento = agora()
            tx.ex('INSERT INTO participacoes (caso, conta, incluida_por, incluida_em, origem) VALUES (?, ?, ?, ?, ?)',
                  caso, conta['id'], por, _iso(momento), 'inclusao')
            _evento(tx, 'participacao_incluida', cid, por, momento)
    return participantes(root, caso, organizacao)


def retirar_participante(root: Path, caso, cid, por: str, organizacao: str) -> dict:
    with _bd(root, escrever=True) as tx:
        posse_ = _caso_da_redacao(tx, caso, organizacao)
        _conta(tx, cid, organizacao)
        if posse_['responsavel'] == cid:
            raise ValueError('Esta pessoa é a responsável pela apuração. Indique outro responsável antes de retirá-la.')
        if tx.um('SELECT 1 FROM participacoes WHERE caso = ? AND conta = ?', caso, cid):
            tx.ex('DELETE FROM participacoes WHERE caso = ? AND conta = ?', caso, cid)
            _evento(tx, 'participacao_retirada', cid, por)
    return participantes(root, caso, organizacao)


def definir_responsavel(root: Path, caso, cid, por: str, organizacao: str) -> dict:
    with _bd(root, escrever=True) as tx:
        _caso_da_redacao(tx, caso, organizacao)
        conta = _conta(tx, cid, organizacao)
        if conta['papel'] not in RESPONSAVEIS or not conta['ativa']:
            raise ValueError('O responsável por uma apuração precisa ser dono ou repórter ativo da redação.')
        momento = agora()
        if not tx.um('SELECT 1 FROM participacoes WHERE caso = ? AND conta = ?', caso, cid):
            tx.ex('INSERT INTO participacoes (caso, conta, incluida_por, incluida_em, origem) VALUES (?, ?, ?, ?, ?)',
                  caso, cid, por, _iso(momento), 'inclusao')
        tx.ex('UPDATE casos SET responsavel = ? WHERE caso = ?', cid, caso)
        _evento(tx, 'responsavel_alterado', cid, por, momento)
    return participantes(root, caso, organizacao)


# --- administration ---------------------------------------------------------------------------

def criar_conta(root: Path, nome, login, papel='convidado', casos=(), cota_diaria=20,
                horas=ATIVACAO_HORAS, por='cli', organizacao=None) -> tuple[dict, str]:
    """Return (public record, activation token). The token is shown once and only its hash is kept.

    `casos` are the participations (required for the legacy `convidado`, optional for editor, reporter and leitor,
    ignored for a dono). The newsroom is `organizacao`, or the one of the account `por`, or the installation's only one."""
    nome, login, papel = _validar_nome(nome), _validar_login(login), papel_valido(papel)
    if papel == 'convidado':
        casos, cota_diaria = _validar_casos(casos), _validar_cota(cota_diaria)
    else:
        casos, cota_diaria = ([] if papel == 'dono' else _validar_casos(casos or [], vazio=True)), None
    horas = _validar_horas(horas)
    with _bd(root, escrever=True) as tx:
        momento = agora()
        if tx.um('SELECT 1 FROM contas WHERE login = ?', login):
            raise ValueError('Esse login já existe. Escolha outro.')
        oid = _organizacao_para(tx, Path(root), organizacao, por, momento)
        cid = secrets.token_hex(8)
        while tx.um('SELECT 1 FROM contas WHERE id = ?', cid):
            cid = secrets.token_hex(8)
        tx.ex('INSERT INTO contas (id, organizacao, papel, nome, login, cota_diaria, criada_em, criada_por)'
              ' VALUES (?, ?, ?, ?, ?, ?, ?, ?)', cid, oid, papel, nome, login, cota_diaria, _iso(momento), por)
        conta = tx.um('SELECT * FROM contas WHERE id = ?', cid)
        _definir_participacoes(tx, conta, casos, por, momento)
        token = _emitir_ativacao(tx, cid, horas, 'criacao', momento)
        _evento(tx, 'conta_criada', cid, por, momento)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento), token


def listar(root: Path, organizacao: str | None = None) -> list[dict]:
    momento = agora()
    with _bd(root) as tx:
        contas = (tx.todos('SELECT * FROM contas WHERE organizacao = ? AND excluida_em IS NULL ORDER BY criada_em, rowid',
                           organizacao) if organizacao is not None
                  else tx.todos('SELECT * FROM contas WHERE excluida_em IS NULL ORDER BY criada_em, rowid'))
        return [_publico(tx, conta, momento) for conta in contas]


def eventos(root: Path, limite: int = 50, organizacao: str | None = None) -> list[dict]:
    with _bd(root) as tx:
        linhas = (tx.todos('SELECT em, tipo, conta, por FROM eventos WHERE organizacao = ? ORDER BY n DESC LIMIT ?',
                           organizacao, limite) if organizacao is not None
                  else tx.todos('SELECT em, tipo, conta, por FROM eventos ORDER BY n DESC LIMIT ?', limite))
        return [dict(linha) for linha in linhas]


def _senha_se(root: Path, por, senha, ip, exige) -> bool:
    """Ask the password of `por` again when `exige(tx)` says the operation is sensitive (contract, 5.15).
    Returns whether it was confirmed; the caller checks `exige` once more inside its own transaction."""
    with _bd(root) as tx:
        precisa = bool(exige(tx))
    if precisa:
        confirmar_senha(root, por, senha, ip)
    return precisa


def desativar(root: Path, cid, por='cli', organizacao: str | None = None, *, confirmar=False, senha=None, ip=None) -> dict:
    """Deactivate an account: its sessions end and the cases it answers for are left without one.
    With `confirmar` (the team screen), deactivating a dono asks the password of who does it."""
    confirmada = confirmar and _senha_se(root, por, senha, ip, lambda tx: _conta(tx, cid, organizacao)['papel'] == 'dono')
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        if confirmar and conta['papel'] == 'dono' and not confirmada:
            raise SenhaNecessaria(SENHA_NECESSARIA)
        if conta['papel'] == 'dono' and conta['ativa'] and not _donos_ativos(tx, conta['organizacao'], exceto=cid):
            raise UltimoDono('Não é possível desativar o último administrador ativo.')
        # An old link must not come back to life after reactivation.
        tx.ex('UPDATE contas SET ativa = 0, ativacao_sha256 = NULL, ativacao_expira_em = NULL, ativacao_motivo = NULL'
              ' WHERE id = ?', cid)
        _derrubar_sessoes(tx, cid)
        _sem_responsabilidade(tx, cid)
        _evento(tx, 'conta_desativada', cid, por)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid))


def reativar(root: Path, cid, por='cli', organizacao: str | None = None) -> dict:
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        tx.ex('UPDATE contas SET ativa = 1 WHERE id = ?', cid)
        _limpar_tentativas(tx, conta['login'])
        _evento(tx, 'conta_reativada', cid, por)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid))


def atualizar(root: Path, cid, por='cli', *, nome=None, papel=None, casos=None, cota_diaria=None,
              organizacao: str | None = None) -> dict:
    """Change name, role, participations or daily quota. Takes effect on the account's next request.

    A change of role keeps the participations. Whoever stops being dono or reporter no longer answers for cases."""
    if nome is not None:
        nome = _validar_nome(nome)
    if papel is not None:
        papel = papel_valido(papel)
    if casos is not None:
        casos = _validar_casos(casos, vazio=True)
    if cota_diaria is not None:
        cota_diaria = _validar_cota(cota_diaria)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        momento = agora()
        novo_papel = papel or conta['papel']
        if (conta['papel'] == 'dono' and novo_papel != 'dono' and conta['ativa']
                and not _donos_ativos(tx, conta['organizacao'], exceto=cid)):
            raise UltimoDono('Não é possível rebaixar o último administrador ativo.')
        antes = _publico(tx, conta, momento)
        if nome is not None:
            tx.ex('UPDATE contas SET nome = ? WHERE id = ?', nome, cid)
        if novo_papel == 'convidado':
            novos = casos if casos is not None else _participacoes(tx, cid)
            _validar_casos(novos)  # the legacy profile always has at least one case
            nova_cota = cota_diaria if cota_diaria is not None else (conta['cota_diaria'] or 20)
            tx.ex("UPDATE contas SET papel = 'convidado', cota_diaria = ? WHERE id = ?", nova_cota, cid)
            _definir_participacoes(tx, conta, novos, por, momento)
        else:
            tx.ex('UPDATE contas SET papel = ?, cota_diaria = NULL WHERE id = ?', novo_papel, cid)
            if casos is not None and novo_papel != 'dono':
                _definir_participacoes(tx, conta, casos, por, momento)
        if novo_papel not in RESPONSAVEIS:
            _sem_responsabilidade(tx, cid)
        depois = _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento)
        campos = [nome_campo for nome_campo, chave in (('nome', 'nome'), ('papel', 'papel'), ('casos', 'casos'),
                                                       ('cota', 'cota_diaria')) if antes[chave] != depois[chave]]
        _evento(tx, 'acesso_alterado', cid, por, momento, campos=campos or None, papel=depois['papel'])
        return depois


def recuperar(root: Path, cid, por='cli', horas=ATIVACAO_HORAS, organizacao: str | None = None) -> tuple[dict, str]:
    """Administrative recovery: end every session, clear the password and issue a new activation link."""
    horas = _validar_horas(horas)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        momento = agora()
        _derrubar_sessoes(tx, cid)
        tx.ex('UPDATE contas SET senha_hash = NULL, senha_definida_em = NULL WHERE id = ?', cid)
        token = _emitir_ativacao(tx, cid, horas, 'recuperacao', momento)
        _limpar_tentativas(tx, conta['login'])
        _evento(tx, 'recuperacao_emitida', cid, por, momento)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento), token


# --- the team screen (equipe-*) -----------------------------------------------------------------

def equipe(root: Path, organizacao: str) -> dict:
    """The people of one newsroom, for its dono: role, cases, own ceiling. Removed accounts are not listed.
    `casos` is None for a dono (every case of the newsroom)."""
    momento = agora()
    with _bd(root) as tx:
        redacao = tx.um('SELECT id, nome, situacao, cota_mensal_brl, teto_por_pessoa_brl FROM organizacoes WHERE id = ?',
                        organizacao)
        if not redacao:
            raise ValueError('Redação não encontrada.')
        pessoas = []
        for conta in tx.todos('SELECT * FROM contas WHERE organizacao = ? AND excluida_em IS NULL ORDER BY criada_em, rowid',
                              organizacao):
            ultimo = tx.um('SELECT MAX(ultimo_uso) AS em FROM sessoes WHERE conta = ?', conta['id'])['em']
            pessoas.append({**_publico(tx, conta, momento), 'responsavel_de': _alcance(tx, conta)[1],
                            'sessao_aberta': bool(ultimo), 'ultimo_uso': ultimo})
        return {'redacao': dict(redacao), 'pessoas': pessoas}


def mudar_papel(root: Path, cid, papel, por: str, organizacao: str, senha=None, ip=None) -> dict:
    """Change the role of a person of the newsroom. The participations stay; whoever stops being dono or reporter
    no longer answers for cases. Promoting to dono, or changing the role of a dono, asks the password of who does it
    (contract, 5.15, and the first condition of P28). The legacy `convidado` is never given."""
    if papel not in ATRIBUIVEIS:
        raise ValueError('Papel de acesso inválido.')

    def sensivel(tx):
        atual = _conta(tx, cid, organizacao)['papel']
        return atual != papel and 'dono' in (atual, papel)
    confirmada = _senha_se(root, por, senha, ip, sensivel)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        momento = agora()
        if conta['papel'] != papel:
            if sensivel(tx) and not confirmada:
                raise SenhaNecessaria(SENHA_NECESSARIA)
            if conta['papel'] == 'dono' and conta['ativa'] and not _donos_ativos(tx, organizacao, exceto=cid):
                raise UltimoDono(ULTIMO_DONO)
            tx.ex('UPDATE contas SET papel = ?, cota_diaria = NULL WHERE id = ?', papel, cid)
            if papel not in RESPONSAVEIS:
                _sem_responsabilidade(tx, cid)
            _evento(tx, 'papel_alterado', cid, por, momento, papel=papel)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento)


def remover(root: Path, cid, por: str, organizacao: str, senha=None, ip=None) -> dict:
    """Remove a person from the newsroom, for good: sessions, password, e-mail, login, name and participations
    go; only the id stays, never used again (it is what links notes and reviews to their author). Always asks
    the password of who does it. The own account is not removed here."""
    if cid == por:
        raise ValueError('Para excluir a sua própria conta, use a página Minha conta.')
    with _bd(root) as tx:
        _conta(tx, cid, organizacao)  # an unknown account is refused before the password is asked
    confirmar_senha(root, por, senha, ip)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        momento = agora()
        if conta['papel'] == 'dono' and conta['ativa'] and not _donos_ativos(tx, organizacao, exceto=cid):
            raise UltimoDono(ULTIMO_DONO)
        _derrubar_sessoes(tx, cid)
        tx.ex('DELETE FROM participacoes WHERE conta = ?', cid)
        _sem_responsabilidade(tx, cid)
        tx.ex('DELETE FROM uso_diario WHERE conta = ?', cid)
        _limpar_tentativas(tx, conta['login'])
        tx.ex('DELETE FROM tentativas WHERE chave = ?', CHAVE_CONFIRMACAO + cid)
        tx.ex("UPDATE contas SET ativa = 0, nome = '', login = NULL, email = NULL, senha_hash = NULL, senha_definida_em = NULL,"
              ' cota_diaria = NULL, teto_mensal_brl = NULL, idioma = NULL, ativacao_sha256 = NULL, ativacao_expira_em = NULL,'
              ' ativacao_motivo = NULL, excluida_em = ? WHERE id = ?', _iso(momento), cid)
        _evento(tx, 'conta_excluida', cid, por, momento)
        return {'id': cid, 'situacao': 'excluida'}


def _valor_do_teto(valor) -> str | None:
    """A ceiling in reais as the store keeps it ('50.00'), or None to go back to the default."""
    if valor is None:
        return None
    texto = str(valor) if type(valor) is int else valor
    if not isinstance(texto, str) or not re.fullmatch(r'\d{1,7}(\.\d{1,2})?', texto):
        raise ValueError(TETO_INVALIDO)
    inteiro, _, centavos = texto.partition('.')
    return f'{int(inteiro)}.{centavos.ljust(2, "0")}'


def _centavos(texto) -> int:
    inteiro, _, centavos = str(texto).partition('.')
    return int(inteiro or 0) * 100 + int((centavos + '00')[:2])


def definir_teto(root: Path, organizacao: str, por: str, valor, cid=None, teto_padrao=None) -> dict:
    """Monthly ceiling in reais of one person (`cid`) or the newsroom's default per person. Never above the
    newsroom's own ceiling, which only the operator sets; without one, `teto_padrao` (the installation's)."""
    valor = _valor_do_teto(valor)
    with _bd(root, escrever=True) as tx:
        redacao = tx.um('SELECT cota_mensal_brl, teto_por_pessoa_brl FROM organizacoes WHERE id = ?', organizacao)
        if not redacao:
            raise ValueError('Redação não encontrada.')
        limite = (_centavos(redacao['cota_mensal_brl']) if redacao['cota_mensal_brl']
                  else int(round(float(teto_padrao) * 100)) if teto_padrao is not None else None)
        if valor is not None and limite is not None and _centavos(valor) > limite:
            raise ValueError(f'O teto por pessoa não pode passar do teto da redação (R$ {limite // 100},{limite % 100:02d}).')
        momento = agora()
        if cid is None:
            tx.ex('UPDATE organizacoes SET teto_por_pessoa_brl = ? WHERE id = ?', valor, organizacao)
            _evento(tx, 'teto_alterado', None, por, momento, organizacao=organizacao)
            return {'teto_por_pessoa_brl': valor}
        _conta(tx, cid, organizacao)
        tx.ex('UPDATE contas SET teto_mensal_brl = ? WHERE id = ?', valor, cid)
        _evento(tx, 'teto_alterado', cid, por, momento)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento)


def atividade(root: Path, organizacao: str, limite: int = 50, antes=None) -> dict:
    """Accesses and administration acts of one newsroom, newest first: type, time, who and by whom. No content of
    any case, and never the refusals of the gate (those tell what exists elsewhere: they go to the audit log only).
    `antes` continues a previous page (its `proximo`)."""
    if type(limite) is not int or not 1 <= limite <= 200:
        raise ValueError('O limite da atividade deve ficar entre 1 e 200.')
    if antes is not None and (type(antes) is not int or antes < 1):
        raise ValueError('Continuação da atividade inválida.')
    with _bd(root) as tx:
        linhas = tx.todos('SELECT n, em, tipo, conta, por FROM eventos WHERE organizacao = ? AND n < ? ORDER BY n DESC LIMIT ?',
                          organizacao, antes if antes is not None else 1 << 62, limite + 1)
        nomes = {c['id']: c['nome'] for c in tx.todos(
            'SELECT id, nome FROM contas WHERE organizacao = ? AND excluida_em IS NULL', organizacao)}
        pagina = linhas[:limite]
        return {'eventos': [{'n': l['n'], 'em': l['em'], 'tipo': l['tipo'], 'conta': l['conta'], 'por': l['por'],
                             'conta_nome': nomes.get(l['conta']), 'por_nome': nomes.get(l['por'])} for l in pagina],
                'proximo': pagina[-1]['n'] if len(linhas) > limite else None}


# --- first administrator (local mode with accounts) ----------------------------------------------

PRIMEIRO_ACESSO_ENCERRADO = 'A conta de administração já foi criada. Entre com login e senha.'


def _primeiro_acesso_livre(tx: _Tx) -> bool:
    return not tx.um('SELECT 1 FROM contas LIMIT 1') and not _meta(tx, 'primeiro_admin_em')


def primeiro_acesso_disponivel(root: Path) -> bool:
    """True only while the store has never held an account (deactivated ones still count)."""
    with _bd(root) as tx:
        return _primeiro_acesso_livre(tx)


def criar_primeiro_admin(root: Path, nome, login, senha) -> dict:
    """Create the installation's newsroom and its first dono, with a password, once. The check and the write share
    one transaction, so two concurrent forms (threads or processes) end with exactly one account."""
    nome, login, senha = _validar_nome(nome), _validar_login(login), _validar_senha(senha)
    if not primeiro_acesso_disponivel(root):
        raise PrimeiroAcessoEncerrado(PRIMEIRO_ACESSO_ENCERRADO)
    with _VezDoHash():
        senha_hash = _HASHER.hash(senha)
    with _bd(root, escrever=True) as tx:
        if not _primeiro_acesso_livre(tx):
            raise PrimeiroAcessoEncerrado(PRIMEIRO_ACESSO_ENCERRADO)
        momento = agora()
        oid = _organizacao_para(tx, Path(root), None, 'primeiro_acesso', momento)
        cid = secrets.token_hex(8)
        tx.ex('INSERT INTO contas (id, organizacao, papel, nome, login, senha_hash, senha_definida_em, criada_em, criada_por)'
              " VALUES (?, ?, 'dono', ?, ?, ?, ?, ?, 'primeiro_acesso')",
              cid, oid, nome, login, senha_hash, _iso(momento), _iso(momento))
        _definir_meta(tx, 'primeiro_admin_em', _iso(momento))
        _evento(tx, 'primeiro_admin', cid, 'primeiro_acesso', momento)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento)


# --- activation -------------------------------------------------------------------------------

def _por_ativacao(tx: _Tx, token, momento: datetime):
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise AtivacaoInvalida(ATIVACAO_INVALIDA)
    conta = tx.um('SELECT * FROM contas WHERE ativacao_sha256 = ?', _hash(token))
    if not conta or not conta['ativa'] or not conta['ativacao_expira_em'] or _data(conta['ativacao_expira_em']) <= momento:
        raise AtivacaoInvalida(ATIVACAO_INVALIDA)
    return conta


def consultar_ativacao(root: Path, token) -> dict:
    """Login and name shown on the set-password form (read-only)."""
    try:
        with _bd(root) as tx:
            conta = _por_ativacao(tx, token, agora())
            return {'login': conta['login'], 'nome': conta['nome']}
    except AtivacaoInvalida:
        registro_acesso.registrar('ativacao_falha', 'falha', motivo='link_invalido', acesso_operacao='consultar')
        raise


def ativar(root: Path, token, senha) -> dict:
    """Set the password from a single-use link. Does not open a session (the person signs in next)."""
    senha = _validar_senha(senha)
    try:
        with _bd(root) as tx:
            _por_ativacao(tx, token, agora())  # refuse before spending time on the hash
    except AtivacaoInvalida:
        registro_acesso.registrar('ativacao_falha', 'falha', motivo='link_invalido', acesso_operacao='ativar')
        raise
    with _VezDoHash():
        senha_hash = _HASHER.hash(senha)
    with _bd(root, escrever=True) as tx:
        momento = agora()
        conta = _por_ativacao(tx, token, momento)
        cid = conta['id']
        tx.ex('UPDATE contas SET senha_hash = ?, senha_definida_em = ?, ativacao_sha256 = NULL, ativacao_expira_em = NULL,'
              ' ativacao_motivo = NULL WHERE id = ?', senha_hash, _iso(momento), cid)
        _limpar_tentativas(tx, conta['login'])
        _evento(tx, 'senha_definida', cid, cid, momento)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento)


# --- sign-in and sessions -----------------------------------------------------------------------

def _hash_ficticio() -> str:
    chave = id(_HASHER)
    if chave not in _FICTICIO:
        _FICTICIO[chave] = _HASHER.hash(secrets.token_urlsafe(24))
    return _FICTICIO[chave]


def limitar_ip(ip: str | None, operacao: str | None = None) -> None:
    """Per-address limit shared by sign-in and activation (20 per minute). `operacao` only labels the audit event."""
    try:
        _limite_ip(ip, agora())
    except Bloqueado:
        # One aggregated line per address and minute (not one per request): see registro_acesso.registrar_limite_ip.
        registro_acesso.registrar_limite_ip('ativacao_falha' if operacao in ('ativar', 'consultar') else 'login_falha', ip,
                                            _rede(ip), acesso_operacao=operacao)
        raise


def _rede(ip: str | None) -> str | None:
    """IPv6 clients usually own a whole /64: count attempts per /64, IPv4 per address."""
    if not ip:
        return ip
    try:
        endereco = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    mapeado = getattr(endereco, 'ipv4_mapped', None)  # IPv6 only; IPv4Address has no such attribute
    if endereco.version == 6 and not mapeado:
        return str(ipaddress.ip_network(f'{endereco}/64', strict=False))
    return str(mapeado or endereco)


def _limite_ip(ip: str | None, momento: datetime) -> None:
    ip = _rede(ip)
    if not ip:
        return
    with _IPS_TRAVA:
        fila = _IPS.setdefault(ip, deque())
        while fila and (momento - fila[0]).total_seconds() >= 60:
            fila.popleft()
        if len(fila) >= TENTATIVAS_IP_MINUTO:
            raise Bloqueado(BLOQUEADO)
        fila.append(momento)
        if len(_IPS) > 10000:  # forget addresses idle for a minute
            for chave in [k for k, f in _IPS.items() if not f or (momento - f[-1]).total_seconds() >= 60]:
                _IPS.pop(chave, None)


def _chave_tentativa(login: str, ip: str | None) -> str:
    """Lockout per login AND address: knowing a login is not enough to lock its owner out from elsewhere."""
    ip = _rede(ip)
    return f'{login}|{ip}' if ip else login


def _limpar_tentativas(tx: _Tx, login: str | None) -> None:
    if login:
        tx.ex("DELETE FROM tentativas WHERE chave = ? OR substr(chave, 1, ?) = ?", login, len(login) + 1, login + '|')


def _bloqueado(tx: _Tx, chave: str, momento: datetime) -> bool:
    registro = tx.um('SELECT bloqueado_ate FROM tentativas WHERE chave = ?', chave)
    ate = registro['bloqueado_ate'] if registro else None
    return bool(ate and _data(ate) > momento)


def _registrar_falha(tx: _Tx, chave: str, cid: str | None, momento: datetime) -> bool:
    """Count a failure of the typed login, whether an account has it or not; return True when it starts a block."""
    registro = tx.um('SELECT falhas, bloqueado_ate FROM tentativas WHERE chave = ?', chave)
    falhas, ate = (registro['falhas'], registro['bloqueado_ate']) if registro else (0, None)
    if ate and _data(ate) <= momento:
        falhas, ate = 0, None
    falhas += 1
    bloqueou = falhas >= FALHAS_BLOQUEIO
    if bloqueou:
        falhas, ate = 0, _iso(momento + timedelta(minutes=BLOQUEIO_MINUTOS))
    tx.ex('INSERT INTO tentativas (chave, falhas, bloqueado_ate, em) VALUES (?, ?, ?, ?) ON CONFLICT (chave) DO UPDATE'
          ' SET falhas = excluded.falhas, bloqueado_ate = excluded.bloqueado_ate, em = excluded.em',
          chave, falhas, ate, _iso(momento))
    _podar_tentativas(tx, momento)
    if cid and bloqueou:
        # Only blocks are audited: single failures would push account events out of the 1000-event window.
        _evento(tx, 'login_bloqueado', cid, None, momento)
    return bloqueou


def _podar_tentativas(tx: _Tx, momento: datetime) -> None:
    """Forget stale counters; active blocks are never evicted."""
    agora_, limite = _iso(momento), _iso(momento - timedelta(minutes=BLOQUEIO_MINUTOS))
    ativo = '(bloqueado_ate IS NOT NULL AND bloqueado_ate > ?)'
    tx.ex(f"DELETE FROM tentativas WHERE NOT {ativo} AND coalesce(em, '') <= ?", agora_, limite)
    excesso = tx.um('SELECT COUNT(*) AS total FROM tentativas')['total'] - MAX_TENTATIVAS_GUARDADAS
    if excesso > 0:
        tx.ex(f"DELETE FROM tentativas WHERE chave IN (SELECT chave FROM tentativas WHERE NOT {ativo}"
              " ORDER BY coalesce(em, '') LIMIT ?)", agora_, excesso)


def _motivo_vencida(registro, momento: datetime) -> str:
    try:
        return 'expirada' if _data(registro['expira_em']) <= momento else 'inatividade'
    except (KeyError, TypeError, ValueError):
        return 'expirada'


def _limpar_sessoes(tx: _Tx, momento: datetime) -> None:
    """Drop expired sessions; each one is audited (`sessao_expirada`), so an expiry never goes unrecorded."""
    for registro in tx.todos('SELECT * FROM sessoes'):
        if _sessao_vencida(registro, momento):
            tx.ex('DELETE FROM sessoes WHERE id_sha256 = ?', registro['id_sha256'])
            conta, motivo, cliente = registro['conta'], _motivo_vencida(registro, momento), registro['cliente']
            tx.depois.append(lambda conta=conta, motivo=motivo, cliente=cliente: registro_acesso.registrar(
                'sessao_expirada', 'ok', conta, momento, motivo=motivo, cliente=cliente))


def _sessao_vencida(registro, momento: datetime) -> bool:
    try:
        return (_data(registro['expira_em']) <= momento
                or _data(registro['ultimo_uso']) + timedelta(hours=INATIVIDADE_HORAS) <= momento)
    except (KeyError, TypeError, ValueError, IndexError):
        return True


def _aparelho(texto) -> str | None:
    """The device label of a session ('Firefox · Windows'): short text chosen by the server, never the raw header."""
    if not isinstance(texto, str) or not 1 <= len(texto) <= 60 or any(ord(c) < 32 for c in texto):
        return None
    return texto


def _ip_valido(ip) -> str | None:
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        return None


def entrar(root: Path, login, senha, ip: str | None = None, cliente='web', aparelho=None) -> tuple[str, str, dict]:
    """Return (session id, csrf token, public account). One generic refusal for every bad credential.
    Every outcome goes to the audit log: success, wrong credentials, lockout and per-address limit (never the text typed).
    `aparelho` and `ip` are kept with the session, for the person's own list of sessions."""
    momento = agora()
    try:
        _limite_ip(ip, momento)
    except Bloqueado:
        registro_acesso.registrar_limite_ip('login_falha', ip, _rede(ip), cliente=_cliente(cliente))
        raise
    login = login.strip().lower() if isinstance(login, str) else ''
    senha = senha if isinstance(senha, str) and len(senha) <= SENHA_MAX else ''
    valido = bool(LOGIN.fullmatch(login))
    chave = _chave_tentativa(login, ip)
    with _bd(root) as tx:
        conta = tx.um('SELECT id, ativa, senha_hash FROM contas WHERE login = ?', login) if valido else None
        cid = conta['id'] if conta else None
        bloqueado = valido and _bloqueado(tx, chave, momento)
        guardado = conta['senha_hash'] if conta and conta['ativa'] else None
    if bloqueado:
        _auditar_falha('bloqueado', cid, login, cliente, ip)
        raise Bloqueado(BLOQUEADO)
    # The hash is checked even for unknown logins (similar timing), outside the store's transaction.
    try:
        with _VezDoHash():
            certo = _HASHER.verify(guardado or _hash_ficticio(), senha) and bool(guardado) and bool(senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        certo = False
    momento = agora()
    aberta, bloqueou, existe = None, False, False
    with _bd(root, escrever=True) as tx:
        conta = tx.um('SELECT * FROM contas WHERE id = ?', cid) if cid else None
        existe = bool(conta)
        if certo and conta and conta['ativa'] and conta['senha_hash'] == guardado:
            if _bloqueado(tx, chave, momento):
                bloqueado = True
            else:
                if _HASHER.check_needs_rehash(guardado):
                    tx.ex('UPDATE contas SET senha_hash = ? WHERE id = ?', _HASHER.hash(senha), cid)
                tx.ex('DELETE FROM tentativas WHERE chave = ?', chave)
                sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                _limpar_sessoes(tx, momento)
                tx.ex('INSERT INTO sessoes (id_sha256, publico, conta, csrf, criada_em, expira_em, ultimo_uso, cliente,'
                      ' aparelho, ip_criacao, ip_ultimo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      _hash(sid), secrets.token_hex(8), cid, csrf, _iso(momento),
                      _iso(momento + timedelta(hours=SESSAO_HORAS)), _iso(momento), _cliente(cliente),
                      _aparelho(aparelho), _ip_valido(ip), _ip_valido(ip))
                tx.depois.append(lambda: registro_acesso.registrar('login_ok', 'ok', cid, momento,
                                                                   cliente=_cliente(cliente), ip=ip))
                aberta = (sid, csrf, _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento))
        elif valido:
            bloqueou = _registrar_falha(tx, chave, cid if conta else None, momento)
    if aberta:
        return aberta
    _auditar_falha('bloqueado' if bloqueado or bloqueou else 'credenciais', cid if existe else None, login, cliente, ip)
    raise (Bloqueado(BLOQUEADO) if bloqueado or bloqueou else CredenciaisInvalidas(CREDENCIAIS))


def _cliente(cliente) -> str:
    return cliente if cliente in CLIENTES else 'web'


def _auditar_falha(motivo: str, cid: str | None, login: str, cliente, ip: str | None) -> None:
    """A failed sign-in: the account id when it exists, otherwise a keyed reference of the typed login (never the
    text, which may be a password typed in the wrong field)."""
    registro_acesso.registrar('login_falha', 'falha', cid, motivo=motivo,
                              login_ref=None if cid else registro_acesso.referencia_do_login(login),
                              cliente=_cliente(cliente), ip=ip)


def sessao(root: Path, sid, ip: str | None = None) -> dict | None:
    """The calling account, re-read on every request (deactivation, role, participations and quota apply at once).
    `ip` is kept as the session's last address, at most once a minute, with its last use.

    `casos` is always the explicit reach (for a dono, every case of the own newsroom) and `responsavel_de` the cases
    the account answers for: outside the local mode no caller ever has "every case"."""
    if not isinstance(sid, str) or not SID.fullmatch(sid):
        return None  # malformed ids never touch the store
    momento, chave = agora(), _hash(sid)
    principal, vencida, tocar = None, False, False
    with _bd(root) as tx:
        registro = tx.um('SELECT * FROM sessoes WHERE id_sha256 = ?', chave)
        if not registro:
            return None
        vencida = _sessao_vencida(registro, momento)
        if not vencida:
            conta = tx.um('SELECT c.*, o.nome AS redacao_nome, o.situacao AS redacao_situacao FROM contas c'
                          ' JOIN organizacoes o ON o.id = c.organizacao WHERE c.id = ?', registro['conta'])
            if not conta or not conta['ativa'] or not conta['senha_hash']:
                return None
            casos, responsavel = _alcance(tx, conta)
            tocar = (momento - _data(registro['ultimo_uso'])).total_seconds() >= ULTIMO_USO_SEGUNDOS
            principal = {'conta': conta['id'], 'nome': conta['nome'], 'login': conta['login'], 'email': conta['email'],
                         'papel': conta['papel'],
                         'organizacao': {'id': conta['organizacao'], 'nome': conta['redacao_nome'],
                                         'situacao': conta['redacao_situacao']},
                         'casos': casos, 'responsavel_de': responsavel, 'pendencias': [],
                         'cota_diaria': conta['cota_diaria'], 'csrf': registro['csrf'], 'sessao': registro['publico'],
                         'expira_em': registro['expira_em'], 'cliente': registro['cliente'] or 'web'}
    if vencida or tocar:
        # Audited once (`sessao_expirada`) and forgotten: no event per later request.
        with _bd(root, escrever=True) as tx:
            if tocar:
                tx.ex('UPDATE sessoes SET ultimo_uso = ?, ip_ultimo = coalesce(?, ip_ultimo) WHERE id_sha256 = ?',
                      _iso(momento), _ip_valido(ip), chave)
            _limpar_sessoes(tx, momento)
    return principal


def encerrar(root: Path, sid) -> None:
    if not isinstance(sid, str):
        return
    with _bd(root, escrever=True) as tx:
        registro = tx.um('SELECT conta FROM sessoes WHERE id_sha256 = ?', _hash(sid))
        if registro is not None:
            tx.ex('DELETE FROM sessoes WHERE id_sha256 = ?', _hash(sid))
            _evento(tx, 'sessao_encerrada', registro['conta'], registro['conta'])


def encerrar_todas_as_sessoes(root: Path) -> int:
    """For a restore: a restored store must not bring yesterday's sessions back to life."""
    with _bd(root, escrever=True) as tx:
        total = tx.um('SELECT COUNT(*) AS total FROM sessoes')['total']
        tx.ex('DELETE FROM sessoes')
        return total


# --- the own account (conta-*) ------------------------------------------------------------------

def confirmar_senha(root: Path, cid, senha, ip: str | None = None) -> None:
    """The password of the session's account, asked again by a sensitive operation (contract, 5.15): a session left
    open, or hostile content shown in the Mesa, cannot run it. A wrong password counts: five in a row block the
    confirmation of this account for 15 minutes. Raises SenhaNecessaria, SenhaIncorreta or Bloqueado."""
    if not isinstance(senha, str) or not senha:
        raise SenhaNecessaria(SENHA_NECESSARIA)
    senha = senha if len(senha) <= SENHA_MAX else ''
    chave, momento = CHAVE_CONFIRMACAO + str(cid), agora()
    with _bd(root) as tx:
        conta = tx.um('SELECT ativa, senha_hash FROM contas WHERE id = ?', cid) if isinstance(cid, str) else None
        guardado = conta['senha_hash'] if conta and conta['ativa'] else None
        bloqueado = _bloqueado(tx, chave, momento)
    if bloqueado:
        registro_acesso.registrar('admin_recusada', 'falha', cid, motivo='bloqueado', ip=ip)
        raise Bloqueado(BLOQUEADO)
    try:
        with _VezDoHash():
            certo = _HASHER.verify(guardado or _hash_ficticio(), senha) and bool(guardado) and bool(senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        certo = False
    with _bd(root, escrever=True) as tx:
        if certo:
            tx.ex('DELETE FROM tentativas WHERE chave = ?', chave)
            return
        bloqueou = _registrar_falha(tx, chave, None, agora())
    registro_acesso.registrar('admin_recusada', 'falha', cid, motivo='bloqueado' if bloqueou else 'senha_incorreta', ip=ip)
    raise SenhaIncorreta(SENHA_INCORRETA)


def ver_conta(root: Path, cid) -> dict:
    """The own profile: name, e-mail, login, role, language, newsroom and when the password was set. The second
    factor and the terms come with their own deliveries."""
    with _bd(root) as tx:
        conta = _conta(tx, cid)
        redacao = tx.um('SELECT id, nome FROM organizacoes WHERE id = ?', conta['organizacao'])
        return {'conta': {'id': conta['id'], 'nome': conta['nome'], 'email': conta['email'], 'login': conta['login'],
                          'papel': conta['papel'], 'idioma': conta['idioma'] or IDIOMAS[0],
                          'senha_definida_em': conta['senha_definida_em'], 'criada_em': conta['criada_em']},
                'organizacao': dict(redacao), 'segundo_fator': {'ativo': False}, 'termos': None}


def atualizar_perfil(root: Path, cid, *, nome=None, idioma=None) -> dict:
    """The person changes the own name and the language of the e-mails; nothing else is theirs to change here."""
    if nome is None and idioma is None:
        raise ValueError('Informe o nome ou o idioma a alterar.')
    if nome is not None:
        nome = _validar_nome(nome)
    if idioma is not None and idioma not in IDIOMAS:
        raise ValueError('Idioma inválido: use pt ou en.')
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid)
        campos = [campo for campo, novo, atual in (('nome', nome, conta['nome']), ('idioma', idioma, conta['idioma'] or IDIOMAS[0]))
                  if novo is not None and novo != atual]
        if campos:
            tx.ex('UPDATE contas SET nome = ?, idioma = ? WHERE id = ?', nome if nome is not None else conta['nome'],
                  idioma if idioma is not None else conta['idioma'], cid)
            _evento(tx, 'conta_atualizada', cid, cid, campos=campos)
    return ver_conta(root, cid)


def trocar_senha(root: Path, cid, senha_atual, senha_nova, sessao_atual=None, ip: str | None = None) -> int:
    """Change the own password: asks the current one and ends every other session of the account (W08, rule 2).
    `sessao_atual` is the public id of the session that asks, the only one kept. Returns how many were ended."""
    senha_nova = _validar_senha(senha_nova)
    confirmar_senha(root, cid, senha_atual, ip)
    if senha_nova == senha_atual:
        raise ValueError('A senha nova precisa ser diferente da atual.')
    with _VezDoHash():
        senha_hash = _HASHER.hash(senha_nova)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid)
        momento = agora()
        tx.ex('UPDATE contas SET senha_hash = ?, senha_definida_em = ?, ativacao_sha256 = NULL, ativacao_expira_em = NULL,'
              ' ativacao_motivo = NULL WHERE id = ?', senha_hash, _iso(momento), cid)
        encerradas = tx.ex('DELETE FROM sessoes WHERE conta = ? AND publico IS NOT ?', cid, sessao_atual).rowcount
        _limpar_tentativas(tx, conta['login'])
        _evento(tx, 'senha_trocada', cid, cid, momento)
        return encerradas


def sessoes_da_conta(root: Path, cid, atual=None) -> list[dict]:
    """The open sessions of one account, newest use first: public id, device, client, dates and addresses.
    Never the cookie nor its hash. `atual` marks the session that asks."""
    momento = agora()
    with _bd(root) as tx:
        linhas = tx.todos('SELECT * FROM sessoes WHERE conta = ? ORDER BY ultimo_uso DESC, criada_em DESC', cid)
        return [{'id': l['publico'], 'aparelho': l['aparelho'], 'cliente': l['cliente'] or 'web', 'criada_em': l['criada_em'],
                 'ultimo_uso': l['ultimo_uso'], 'expira_em': l['expira_em'], 'ip': l['ip_ultimo'] or l['ip_criacao'],
                 'ip_criacao': l['ip_criacao'], 'atual': l['publico'] == atual}
                for l in linhas if not _sessao_vencida(l, momento)]


def encerrar_sessao_da_conta(root: Path, cid, publico, atual=None) -> None:
    """End one other session of the own account, at a distance. A session of another account, an ended one and an
    id that never existed get the same refusal. The session that asks is ended by signing out."""
    if not isinstance(publico, str) or not ID_CONTA.fullmatch(publico):
        raise ValueError(SESSAO_INEXISTENTE)
    if publico == atual:
        raise ValueError('Esta é a sessão em uso. Para encerrá-la, saia da conta.')
    with _bd(root, escrever=True) as tx:
        if not tx.ex('DELETE FROM sessoes WHERE conta = ? AND publico = ?', cid, publico).rowcount:
            raise ValueError(SESSAO_INEXISTENTE)
        _evento(tx, 'sessao_encerrada_a_distancia', cid, cid)


def encerrar_outras_sessoes(root: Path, cid, atual) -> int:
    """End every session of the own account but the one that asks. Returns how many."""
    with _bd(root, escrever=True) as tx:
        encerradas = tx.ex('DELETE FROM sessoes WHERE conta = ? AND publico IS NOT ?', cid, atual).rowcount
        if encerradas:
            _evento(tx, 'sessao_encerrada_a_distancia', cid, cid)
        return encerradas


def copia_consistente(root: Path, destino: Path) -> Path:
    """A consistent copy of the store while it is in use (SQLite backup API), for the backup to pack."""
    origem = _preparar(Path(root))
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        de = sqlite3.connect(str(origem), timeout=ESPERA_BD_S)
        try:
            para = sqlite3.connect(str(destino))
            try:
                de.backup(para)
            finally:
                para.close()
        finally:
            de.close()
    except sqlite3.Error as exc:
        raise _ilegivel() from exc
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    return destino


# --- daily quota ------------------------------------------------------------------------------

def registrar_consulta(root: Path, cid: str) -> int:
    """Count one question for today (UTC). Accounts with a daily quota (the legacy guests) over it are refused."""
    dia = agora().strftime('%Y-%m-%d')
    with _bd(root, escrever=True) as tx:
        conta = tx.um('SELECT ativa, cota_diaria FROM contas WHERE id = ?', cid) if isinstance(cid, str) else None
        if not conta or not conta['ativa']:
            raise ValueError('Conta indisponível. Entre novamente.')
        uso = tx.um('SELECT dia, feitas FROM uso_diario WHERE conta = ?', cid)
        feitas = uso['feitas'] if uso and uso['dia'] == dia else 0
        if conta['cota_diaria'] is not None and feitas >= conta['cota_diaria']:
            raise ValueError(f'Limite diário de {conta["cota_diaria"]} pergunta(s) atingido. Tente novamente amanhã.')
        tx.ex('INSERT INTO uso_diario (conta, dia, feitas) VALUES (?, ?, ?) ON CONFLICT (conta) DO UPDATE'
              ' SET dia = excluded.dia, feitas = excluded.feitas', cid, dia, feitas + 1)  # keep only today
        return feitas + 1


def devolver_consulta(root: Path, cid: str) -> None:
    """Give back today's question when the server refused it after counting."""
    dia = agora().strftime('%Y-%m-%d')
    with _bd(root, escrever=True) as tx:
        tx.ex('UPDATE uso_diario SET feitas = feitas - 1 WHERE conta = ? AND dia = ? AND feitas > 0', cid, dia)


# --- CLI --------------------------------------------------------------------------------------

def _link(origem: str, token: str) -> str:
    return origem.rstrip('/') + '/ativar/' + token


def _entregar_link(link: str, saida: str | None) -> None:
    """Terminal stdout only, or a 0600 file; never logs."""
    if not saida:
        print('Link de ativação (mostrado uma única vez; envie por canal seguro):', link)
        return
    descritor = os.open(saida, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, 'fchmod'):
        os.fchmod(descritor, 0o600)  # an existing file keeps its old mode until changed: change it before writing
    with os.fdopen(descritor, 'w', encoding='utf-8') as arquivo:
        arquivo.write(link + '\n')
    try:
        os.chmod(saida, 0o600)
    except OSError:
        pass
    print(f'Link de ativação gravado em {saida} (permissão 0600).')


def _casos_cli(texto: str) -> list[str]:
    return [c.strip() for c in texto.split(',') if c.strip()]


def _imprimir(valor) -> None:
    print(json.dumps(valor, ensure_ascii=False, indent=2))


def _principal() -> int:
    parser = argparse.ArgumentParser(description='Contas de acesso da Mesa hospedada.')
    sub = parser.add_subparsers(dest='comando', required=True)
    for nome in ('criar-admin', 'criar-conta'):
        cria = sub.add_parser(nome)
        cria.add_argument('--nome', required=True)
        cria.add_argument('--login', required=True)
        cria.add_argument('--origem', required=True, help='Endereço público, ex.: https://vlado.example.org')
        cria.add_argument('--horas', type=int, default=ATIVACAO_HORAS, help='Validade do link (1–168 h)')
        cria.add_argument('--saida', help='Grava o link neste arquivo (0600) em vez de imprimir')
        cria.add_argument('--redacao', help='Id da redação (obrigatório quando a instalação tem mais de uma)')
        if nome == 'criar-conta':
            cria.add_argument('--casos', required=True, help='IDs separados por vírgula')
            cria.add_argument('--cota', type=int, default=20)
    sub.add_parser('listar')
    sub.add_parser('redacao-listar')
    for nome in ('desativar', 'reativar'):
        sub.add_parser(nome).add_argument('id')
    recupera = sub.add_parser('recuperar')
    recupera.add_argument('id')
    recupera.add_argument('--origem', required=True)
    recupera.add_argument('--horas', type=int, default=ATIVACAO_HORAS)
    recupera.add_argument('--saida')
    casos = sub.add_parser('casos')
    casos.add_argument('id')
    casos.add_argument('--casos', required=True, help='IDs separados por vírgula')
    atribui = sub.add_parser('caso-atribuir', help='Dá posse a uma apuração criada pelo terminal')
    atribui.add_argument('--caso', required=True)
    atribui.add_argument('--redacao', required=True, help='Id da redação (veja redacao-listar)')
    atribui.add_argument('--responsavel', help='Id de uma conta dono ou repórter da redação')
    migra = sub.add_parser('migrar', help='Leva o acesso.json para o armazenamento novo')
    migra.add_argument('--simular', action='store_true', help='Só mostra o relatório; não grava nada')
    args = parser.parse_args()
    if args.comando in ('criar-admin', 'criar-conta', 'recuperar'):
        if args.comando == 'criar-admin':
            registro, token = criar_conta(ROOT, args.nome, args.login, papel='dono', horas=args.horas,
                                          organizacao=args.redacao)
        elif args.comando == 'criar-conta':
            registro, token = criar_conta(ROOT, args.nome, args.login, casos=_casos_cli(args.casos),
                                          cota_diaria=args.cota, horas=args.horas, organizacao=args.redacao)
        else:
            registro, token = recuperar(ROOT, args.id, por='cli', horas=args.horas)
        _imprimir(registro)
        _entregar_link(_link(args.origem, token), args.saida)
    elif args.comando == 'listar':
        _imprimir(listar(ROOT))
    elif args.comando == 'redacao-listar':
        _imprimir(listar_redacoes(ROOT))
    elif args.comando == 'desativar':
        _imprimir(desativar(ROOT, args.id, por='cli'))
    elif args.comando == 'reativar':
        _imprimir(reativar(ROOT, args.id, por='cli'))
    elif args.comando == 'caso-atribuir':
        if args.caso not in _casos_do_catalogo(ROOT):
            raise ValueError('Apuração não encontrada no catálogo desta instalação.')
        _imprimir(atribuir_caso(ROOT, args.caso, args.redacao, args.responsavel, por='operador'))
    elif args.comando == 'migrar':
        if args.simular:
            _imprimir(simular_migracao(ROOT))
        else:
            _imprimir({'estado': 'migrado', **relatorio_migracao(ROOT)})
    else:
        _imprimir(atualizar(ROOT, args.id, por='cli', casos=_casos_cli(args.casos)))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(_principal())
    except ValueError as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        raise SystemExit(1)
