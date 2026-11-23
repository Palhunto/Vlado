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
import hmac
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
import segundo_fator  # noqa: E402

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
# An e-mail address as the store keeps it (lower case). It never has `|` nor `#`, which the attempt counters use.
EMAIL = re.compile(r'[a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+')
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
CONVITE_DIAS = 7  # an invitation is valid for a week, once (decision 15)
CONVITES_PENDENTES = 50  # per newsroom: an invitation must not become a way to fill somebody's mailbox
REENVIO_MINUTOS = 60  # each invitation is sent again at most once an hour
CONVITES_POR_ENDERECO = 3  # messages a newsroom sends to the same address in that hour, cancelled ones included
ATIVIDADE_DIAS = 90  # the newsroom's activity is kept for 90 days (decision 15)
REDEFINICAO_MINUTOS = 60  # a password-reset link is valid for one hour, once (decision 15)
REDEFINICAO_INTERVALO_MINUTOS = 5  # the same address is sent at most one reset message in this time
CHAVE_ESQUECI = '#esqueci|'  # when a reset was last asked for an address, whether an account has it or not
RECUPERACAO_HORAS = 24  # a recovery asked by a dono: how long it waits for the second dono, and how long its link lives
ENTRADA_MINUTOS = 5  # between the right password and the second factor: the ticket of the second step
ENTRADA_FALHAS = 5  # wrong codes that kill that ticket
FATOR_OBRIGATORIO = ('dono', 'editor')  # who must have a second factor where it is mandatory: the hosted mode (8.2)
FATOR_PENDENTE_MINUTOS = 15  # an enrolment not confirmed in this time starts again
FATOR_RETIRADO = 'fator_removido_na_recuperacao'  # the event of a factor that a recovery took away (link or operator)
CHAVE_FATOR = '#fator|'  # wrong codes of the authenticator, counted on the account (sign-in and sensitive operations)
CHAVE_RESERVA = '#reserva|'  # wrong reserve codes, on a counter of their own: they never block the authenticator
FATOR_CONTADOR_HORAS = 24  # how long those two counters are remembered without a new failure
PROTECAO_FALHAS = 10  # failures of one identifier, from any address, inside the window below ...
PROTECAO_JANELA_MINUTOS = 60
PROTECAO_MINUTOS = 60  # ... put it in protected mode for this long
BALDES = 20000  # counters of identifiers WITHOUT an account: a table of fixed size, so it never fills nor grows
APARELHOS_MAX = 20  # known devices kept for each account (the least recently used goes first)
CHAVE_BALDE = '#balde|'  # the ceiling of an identifier, with an account or without: one of BALDES counters, by HMAC
CHAVE_MARCA = '#marca|'  # failures with a known device mark: the mark does not switch the ceiling off
ESQUEMA = 8  # PRAGMA user_version of the store; `_ATUALIZACOES` takes an older store up to it
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
CONVITE_INVALIDO = 'Convite inválido, cancelado ou vencido. Peça um novo a quem convidou.'
CONVITE_INEXISTENTE = 'Convite não encontrado.'
LINK_INVALIDO = 'Link inválido, usado ou vencido. Peça outro em Esqueci a senha.'
CODIGO_INVALIDO = 'Código incorreto.'
FATOR_INDISPONIVEL = ('O código do aplicativo não pode ser conferido neste servidor agora. Se você tem um código de '
                      'reserva, use-o, e avise quem administra o serviço.')
CADASTRO_INDISPONIVEL = 'O cadastro do segundo fator está indisponível neste servidor. Avise quem administra o serviço.'
CODIGO_NECESSARIO = 'Digite o código do aplicativo autenticador, ou um código de reserva.'
ENTRADA_EXPIRADA = 'A entrada expirou. Digite o login e a senha de novo.'
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
CREATE TABLE convites (
    id TEXT PRIMARY KEY, organizacao TEXT NOT NULL REFERENCES organizacoes(id), email TEXT NOT NULL,
    papel TEXT NOT NULL, casos TEXT NOT NULL DEFAULT '[]', idioma TEXT, token_sha256 TEXT UNIQUE,
    estado TEXT NOT NULL DEFAULT 'pendente', criado_em TEXT NOT NULL, criado_por TEXT NOT NULL, expira_em TEXT NOT NULL,
    enviado_em TEXT NOT NULL, envio TEXT, encerrado_em TEXT, conta TEXT);
CREATE INDEX convites_por_organizacao ON convites (organizacao, estado);
CREATE INDEX convites_por_email ON convites (email);
CREATE TABLE links (
    token_sha256 TEXT PRIMARY KEY, tipo TEXT NOT NULL, conta TEXT NOT NULL REFERENCES contas(id),
    criado_em TEXT NOT NULL, expira_em TEXT NOT NULL, dado TEXT);
CREATE INDEX links_por_conta ON links (conta, tipo);
CREATE TABLE recuperacoes (
    id TEXT PRIMARY KEY, organizacao TEXT NOT NULL REFERENCES organizacoes(id), conta TEXT NOT NULL REFERENCES contas(id),
    pedida_por TEXT NOT NULL, pedida_em TEXT NOT NULL, expira_em TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'pendente',
    confirmada_por TEXT, encerrada_em TEXT);
CREATE INDEX recuperacoes_por_organizacao ON recuperacoes (organizacao, estado);
CREATE TABLE fatores (
    conta TEXT PRIMARY KEY REFERENCES contas(id), semente TEXT, ativo INTEGER NOT NULL DEFAULT 0, criado_em TEXT NOT NULL,
    ativado_em TEXT, ultimo_passo INTEGER, pendente TEXT, pendente_em TEXT);
CREATE TABLE codigos_reserva (
    conta TEXT NOT NULL REFERENCES contas(id), resumo TEXT NOT NULL, criado_em TEXT NOT NULL, usado_em TEXT,
    PRIMARY KEY (conta, resumo));
CREATE TABLE entradas (
    id_sha256 TEXT PRIMARY KEY, conta TEXT NOT NULL REFERENCES contas(id), chave TEXT NOT NULL, criada_em TEXT NOT NULL,
    expira_em TEXT NOT NULL, falhas INTEGER NOT NULL DEFAULT 0, cliente TEXT, aparelho TEXT);
CREATE TABLE aparelhos (
    conta TEXT NOT NULL REFERENCES contas(id), resumo TEXT NOT NULL, criado_em TEXT NOT NULL, ultimo_uso TEXT NOT NULL,
    PRIMARY KEY (conta, resumo));
CREATE TABLE termos_aceites (conta TEXT NOT NULL REFERENCES contas(id), versao TEXT NOT NULL, aceito_em TEXT NOT NULL, ip TEXT);
CREATE INDEX termos_por_conta ON termos_aceites (conta, aceito_em);
"""
# From each older version of the store to the next one (applied in order, each in one transaction).
_ATUALIZACOES = {1: ('ALTER TABLE contas ADD COLUMN idioma TEXT',
                     'ALTER TABLE contas ADD COLUMN excluida_em TEXT',
                     'ALTER TABLE sessoes ADD COLUMN aparelho TEXT',
                     'ALTER TABLE sessoes ADD COLUMN ip_criacao TEXT',
                     'ALTER TABLE sessoes ADD COLUMN ip_ultimo TEXT',
                     'CREATE INDEX eventos_por_organizacao ON eventos (organizacao, n)'),
                 2: ('CREATE TABLE convites (id TEXT PRIMARY KEY, organizacao TEXT NOT NULL REFERENCES organizacoes(id),'
                     " email TEXT NOT NULL, papel TEXT NOT NULL, casos TEXT NOT NULL DEFAULT '[]', idioma TEXT,"
                     " token_sha256 TEXT UNIQUE, estado TEXT NOT NULL DEFAULT 'pendente', criado_em TEXT NOT NULL,"
                     ' criado_por TEXT NOT NULL, expira_em TEXT NOT NULL, enviado_em TEXT NOT NULL, envio TEXT,'
                     ' encerrado_em TEXT, conta TEXT)',
                     'CREATE INDEX convites_por_organizacao ON convites (organizacao, estado)',
                     'CREATE INDEX convites_por_email ON convites (email)'),
                 3: ('CREATE TABLE links (token_sha256 TEXT PRIMARY KEY, tipo TEXT NOT NULL,'
                     ' conta TEXT NOT NULL REFERENCES contas(id), criado_em TEXT NOT NULL, expira_em TEXT NOT NULL)',
                     'CREATE INDEX links_por_conta ON links (conta, tipo)'),
                 4: ('ALTER TABLE links ADD COLUMN dado TEXT',
                     'CREATE TABLE recuperacoes (id TEXT PRIMARY KEY, organizacao TEXT NOT NULL REFERENCES organizacoes(id),'
                     ' conta TEXT NOT NULL REFERENCES contas(id), pedida_por TEXT NOT NULL, pedida_em TEXT NOT NULL,'
                     " expira_em TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'pendente', confirmada_por TEXT, encerrada_em TEXT)",
                     'CREATE INDEX recuperacoes_por_organizacao ON recuperacoes (organizacao, estado)'),
                 5: ('CREATE TABLE fatores (conta TEXT PRIMARY KEY REFERENCES contas(id), semente TEXT,'
                     ' ativo INTEGER NOT NULL DEFAULT 0, criado_em TEXT NOT NULL, ativado_em TEXT, ultimo_passo INTEGER,'
                     ' pendente TEXT, pendente_em TEXT)',
                     'CREATE TABLE codigos_reserva (conta TEXT NOT NULL REFERENCES contas(id), resumo TEXT NOT NULL,'
                     ' criado_em TEXT NOT NULL, usado_em TEXT, PRIMARY KEY (conta, resumo))',
                     'CREATE TABLE entradas (id_sha256 TEXT PRIMARY KEY, conta TEXT NOT NULL REFERENCES contas(id),'
                     ' chave TEXT NOT NULL, criada_em TEXT NOT NULL, expira_em TEXT NOT NULL,'
                     ' falhas INTEGER NOT NULL DEFAULT 0, cliente TEXT, aparelho TEXT)'),
                 6: ('CREATE TABLE aparelhos (conta TEXT NOT NULL REFERENCES contas(id), resumo TEXT NOT NULL,'
                     ' criado_em TEXT NOT NULL, ultimo_uso TEXT NOT NULL, PRIMARY KEY (conta, resumo))',),
                 7: ('CREATE TABLE termos_aceites (conta TEXT NOT NULL REFERENCES contas(id), versao TEXT NOT NULL,'
                     ' aceito_em TEXT NOT NULL, ip TEXT)',
                     'CREATE INDEX termos_por_conta ON termos_aceites (conta, aceito_em)')}


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


class FatorBloqueado(Bloqueado):
    """The fifth wrong code in a row just blocked the second factor of an account, whatever the addresses the
    codes came from. `aviso` is who is told, at the account's own address."""

    def __init__(self, aviso: dict):
        super().__init__(BLOQUEADO)
        self.aviso = aviso


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


class NomeDivergente(Recusada):
    """The name typed to confirm the deletion of the own account is not the account's (it is not a wrong password)."""
    status, codigo, motivo = 400, 'nome_confirmacao_divergente', 'validacao'


class TermosDesatualizados(Recusada):
    """The version of the terms sent is not the one in force (or none came while there is one)."""
    status, codigo, motivo = 400, 'termos_desatualizados', 'validacao'


class ConviteDuplicado(Recusada):
    """The e-mail is already of the own newsroom, as a person or as a pending invitation (the dono sees both)."""
    status, codigo, motivo = 400, 'convite_duplicado', 'validacao'


class LimiteDeConvites(Recusada):
    """Too many pending invitations in the newsroom, or the same one sent again too soon."""
    status, codigo, motivo = 429, 'limite_de_convites', 'limite'


class ConviteInvalido(ValueError):
    """One refusal for every invitation link that creates nothing: unknown, used, cancelled, expired, or of an
    e-mail that already has an account. `motivo` goes to the audit log only."""

    def __init__(self, motivo='link_invalido'):
        super().__init__(CONVITE_INVALIDO)
        self.motivo = motivo


class SenhaInvalida(ValueError):
    """The password somebody chose is out of size (the public pages answer it with their own code)."""


class LinkInvalido(ValueError):
    """One refusal for every password-reset link that changes nothing: unknown, used, expired, or of an account
    that is no longer active. `motivo` goes to the audit log only."""

    def __init__(self, motivo='link_invalido', mensagem=None):
        super().__init__(mensagem or LINK_INVALIDO)
        self.motivo = motivo


class CodigoInvalido(Recusada):
    """The code of the second factor (or the reserve code) is wrong, or was already used (it counts)."""
    status, codigo, motivo = 403, 'codigo_invalido', 'codigo_invalido'


class CodigoNecessario(Recusada):
    """The operation needs the second factor and no code came. Not a wrong code: nothing is counted nor recorded
    (a page may ask first without it, to learn that the account has a factor)."""
    status, codigo, motivo = 403, 'fator_necessario', 'validacao'


class FatorIndisponivel(Recusada):
    """The second factor cannot be checked or enrolled here: the key of the seeds is missing, or is not the one
    they were stored with (a restore without `segredos/`). Not the person's mistake: nothing is counted. A reserve
    code still works, as it needs neither the seed nor the key."""
    status, codigo, motivo = 503, 'fator_indisponivel', 'erro'


class PedeSegundoFator(Exception):
    """The password was right and the account has a second factor: no session yet. `bilhete` is the ticket of the
    second step (five minutes, good only for `entrar_segundo_fator`). Not an error: `entrar` says it this way."""

    def __init__(self, bilhete: str):
        super().__init__('segundo_fator')
        self.bilhete = bilhete


class EntradaExpirada(ValueError):
    """The ticket of the second step is unknown, past its five minutes, or was killed by wrong codes."""


class SoPeloOperador(Recusada):
    """A recovery the Mesa cannot complete with two parties (no other dono to confirm, or no way to hand the link to
    the person): it is done by the operator of the service, at the terminal."""
    status, codigo, motivo = 400, 'recuperacao_pelo_operador', 'validacao'


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
                # An older store put in place while this process runs (a backup restored without stopping the Mesa)
                # is brought up here too, not only on the first use by the process.
                _atualizar_esquema(con)
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
        raise SenhaInvalida(f'A senha deve ter de {SENHA_MIN} a {SENHA_MAX} caracteres.')
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


def _cancelar_convites_de(tx: _Tx, cid: str, momento: datetime | None = None) -> None:
    """The pending invitations of who stops being a dono, is deactivated or is removed do not outlive it: an
    invitation is an act of a dono, and stays good only while the one who made it could still make it."""
    momento = momento or agora()
    for convite in tx.todos("SELECT id, organizacao FROM convites WHERE criado_por = ? AND estado = 'pendente'", cid):
        tx.ex("UPDATE convites SET estado = 'cancelado', token_sha256 = NULL, encerrado_em = ? WHERE id = ?",
              _iso(momento), convite['id'])
        _evento(tx, 'convite_cancelado', None, cid, momento, organizacao=convite['organizacao'])


def _derrubar_sessoes(tx: _Tx, cid: str) -> None:
    """End every session of the account. A password-reset link still pending dies with them: whatever ends the
    sessions (deactivation, recovery, removal, a new password) must not leave a way back in."""
    tx.ex('DELETE FROM sessoes WHERE conta = ?', cid)
    tx.ex('DELETE FROM links WHERE conta = ?', cid)
    tx.ex('DELETE FROM entradas WHERE conta = ?', cid)


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


EVENTOS_DA_CHAVE_DE_IA = ('chave_ia_salva', 'chave_ia_removida')


def registrar_chave_de_ia(root: Path, cid: str, tipo: str) -> None:
    """The dono saved or removed the newsroom's own AI key: it goes to the activity of the newsroom and to the audit
    log. Who and when; never the key, nor any part of it."""
    if tipo not in EVENTOS_DA_CHAVE_DE_IA:
        raise ValueError('Evento de chave desconhecido.')
    with _bd(root, escrever=True) as tx:
        _evento(tx, tipo, _conta(tx, cid)['id'], cid)


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
                horas=ATIVACAO_HORAS, por='cli', organizacao=None, *, confirmar=False, senha=None, ip=None) -> tuple[dict, str]:
    """Return (public record, activation token). The token is shown once and only its hash is kept.

    `casos` are the participations (required for the legacy `convidado`, optional for editor, reporter and leitor,
    ignored for a dono). The newsroom is `organizacao`, or the one of the account `por`, or the installation's only one.
    With `confirmar` (a session of the Mesa), creating a dono asks the password of who does it (contract, 5.15)."""
    nome, login, papel = _validar_nome(nome), _validar_login(login), papel_valido(papel)
    if papel == 'convidado':
        casos, cota_diaria = _validar_casos(casos), _validar_cota(cota_diaria)
    else:
        casos, cota_diaria = ([] if papel == 'dono' else _validar_casos(casos or [], vazio=True)), None
    horas = _validar_horas(horas)
    if confirmar and papel == 'dono':
        confirmar_senha(root, por, senha, ip)
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
        _cancelar_convites_de(tx, cid)
        _evento(tx, 'conta_desativada', cid, por)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid))


def reativar(root: Path, cid, por='cli', organizacao: str | None = None) -> dict:
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        tx.ex('UPDATE contas SET ativa = 1 WHERE id = ?', cid)
        _limpar_tentativas(tx, conta)
        _evento(tx, 'conta_reativada', cid, por)
        return _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid))


def atualizar(root: Path, cid, por='cli', *, nome=None, papel=None, casos=None, cota_diaria=None,
              organizacao: str | None = None, confirmar=False, senha=None, ip=None) -> dict:
    """Change name, role, participations or daily quota. Takes effect on the account's next request.

    A change of role keeps the participations. Whoever stops being dono or reporter no longer answers for cases.
    With `confirmar` (a session of the Mesa), promoting to dono and changing the role of a dono ask the password of
    who does it, as `mudar_papel` does (contract, 5.15): the name of the operation is not a way around it."""
    if nome is not None:
        nome = _validar_nome(nome)
    if papel is not None:
        papel = papel_valido(papel)
    if casos is not None:
        casos = _validar_casos(casos, vazio=True)
    if cota_diaria is not None:
        cota_diaria = _validar_cota(cota_diaria)

    def sensivel(tx):
        atual = _conta(tx, cid, organizacao)['papel']
        return papel is not None and atual != papel and 'dono' in (atual, papel)
    confirmada = confirmar and _senha_se(root, por, senha, ip, sensivel)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        if confirmar and papel == 'convidado' and conta['papel'] != 'convidado':
            # The legacy profile only exists in accounts that came with it (contract, 2.3): nobody is given it again.
            raise ValueError('Papel de acesso inválido.')
        if confirmar and sensivel(tx) and not confirmada:
            raise SenhaNecessaria(SENHA_NECESSARIA)
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
        if novo_papel != 'dono':
            _cancelar_convites_de(tx, cid, momento)
        depois = _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento)
        campos = [nome_campo for nome_campo, chave in (('nome', 'nome'), ('papel', 'papel'), ('casos', 'casos'),
                                                       ('cota', 'cota_diaria')) if antes[chave] != depois[chave]]
        _evento(tx, 'acesso_alterado', cid, por, momento, campos=campos or None, papel=depois['papel'])
        return depois


def recuperar(root: Path, cid, por='cli', horas=ATIVACAO_HORAS, organizacao: str | None = None, *, confirmar=False,
              senha=None, ip=None) -> tuple[dict, str]:
    """Administrative recovery: end every session, clear the password and issue a new activation link.
    With `confirmar` (a session of the Mesa) it always asks the password of who does it: the link it gives back
    opens the other person's account (contract, 5.15). The account is checked first, so one that does not exist, or
    is of another newsroom, answers the same with or without a password."""
    horas = _validar_horas(horas)
    if confirmar:
        with _bd(root) as tx:
            _conta(tx, cid, organizacao)
        confirmar_senha(root, por, senha, ip)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid, organizacao)
        momento = agora()
        _derrubar_sessoes(tx, cid)
        if tx.um('SELECT 1 FROM fatores WHERE conta = ?', cid):
            # Recovered by the operator: the person lost the password and may have lost the device too. The
            # second factor goes with the password, and is enrolled again after the new sign-in.
            _sem_fator(tx, cid)
            _evento(tx, FATOR_RETIRADO, cid, por, momento)
        tx.ex('DELETE FROM aparelhos WHERE conta = ?', cid)
        tx.ex('UPDATE contas SET senha_hash = NULL, senha_definida_em = NULL WHERE id = ?', cid)
        token = _emitir_ativacao(tx, cid, horas, 'recuperacao', momento)
        _limpar_tentativas(tx, conta)
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
        return {'redacao': dict(redacao), 'pessoas': pessoas, 'convites': _convites_pendentes(tx, organizacao, momento),
                'recuperacoes': [_recuperacao_publica(tx, r) for r in _recuperacoes_pendentes(tx, organizacao, momento)]}


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
            if papel != 'dono':
                _cancelar_convites_de(tx, cid, momento)
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
        return _apagar_conta(tx, _conta(tx, cid, organizacao), por, agora())


def _ultimo_dono(tx: _Tx, conta) -> bool:
    return conta['papel'] == 'dono' and bool(conta['ativa']) and not _donos_ativos(tx, conta['organizacao'], exceto=conta['id'])


def _apagar_conta(tx: _Tx, conta, por: str, momento: datetime) -> dict:
    """What removing a person and deleting the own account both do (contract, 8.4: the same effect): only the id
    stays, with the situation `excluida`. The last active dono of a newsroom is refused, checked inside the same
    transaction that deletes."""
    cid = conta['id']
    if _ultimo_dono(tx, conta):
        raise UltimoDono(ULTIMO_DONO)
    _derrubar_sessoes(tx, cid)
    _cancelar_convites_de(tx, cid, momento)
    _sem_fator(tx, cid)
    tx.ex('DELETE FROM aparelhos WHERE conta = ?', cid)
    tx.ex('DELETE FROM participacoes WHERE conta = ?', cid)
    tx.ex('UPDATE termos_aceites SET ip = NULL WHERE conta = ?', cid)  # the proof stays: id, version, date (P41 b)
    _sem_responsabilidade(tx, cid)
    tx.ex('DELETE FROM uso_diario WHERE conta = ?', cid)
    _limpar_tentativas(tx, conta)
    tx.ex('DELETE FROM tentativas WHERE chave = ?', CHAVE_CONFIRMACAO + cid)
    tx.ex("UPDATE contas SET ativa = 0, nome = '', login = NULL, email = NULL, senha_hash = NULL, senha_definida_em = NULL,"
          ' cota_diaria = NULL, teto_mensal_brl = NULL, idioma = NULL, ativacao_sha256 = NULL, ativacao_expira_em = NULL,'
          ' ativacao_motivo = NULL, excluida_em = ? WHERE id = ?', _iso(momento), cid)
    _evento(tx, 'conta_excluida', cid, por, momento)
    return {'id': cid, 'situacao': 'excluida'}


def excluir_conta(root: Path, cid, nome, senha, ip=None) -> dict:
    """`conta-excluir`: the person deletes the own account (contract, 8.4 and the delivery 4b-3), with the same
    effect as `equipe-remover`. The order is the one agreed with the Frontend: the typed name first (the account's
    current name, ignoring the ends' spaces and the case; a wrong one is not a wrong password), then the last dono,
    so that an impossible deletion never spends an attempt, then the password."""
    with _bd(root) as tx:
        conta = _conta(tx, cid)
        digitado = nome.strip().casefold() if isinstance(nome, str) and len(nome) <= 400 else None
        if not digitado or digitado != (conta['nome'] or '').strip().casefold():
            raise NomeDivergente('O nome digitado não é o da conta.')
        if _ultimo_dono(tx, conta):
            raise UltimoDono(ULTIMO_DONO)
    confirmar_senha(root, cid, senha, ip)
    with _bd(root, escrever=True) as tx:
        return _apagar_conta(tx, _conta(tx, cid), cid, agora())


# What the Mesa shows as the author of something made by an account that no longer exists (contract, 8.4 and
# decision 10). The records keep the old name; only the output changes, here, in one place.
CONTA_EXCLUIDA = 'Conta excluída'


def nomes_publicos(root: Path, ids, organizacao: str | None = None) -> dict:
    """The name to show for each account id: its name, `CONTA_EXCLUIDA` for a deleted account, and None for what is
    not an account (a fixed label of the system, an old login) or is an account of another newsroom than
    `organizacao`, when it is given: a name never tells one newsroom who is in another."""
    pedidos = sorted({i for i in ids if isinstance(i, str) and ID_CONTA.fullmatch(i)})
    if not pedidos:
        return {}
    with _bd(root) as tx:
        linhas = tx.todos(f'SELECT id, nome, organizacao, excluida_em FROM contas WHERE id IN ({", ".join("?" * len(pedidos))})',
                          *pedidos)
    return {c['id']: _nome_para_mostrar(c) for c in linhas if organizacao is None or c['organizacao'] == organizacao}


def nome_publico(root: Path, cid, organizacao: str | None = None) -> str | None:
    """One id of `nomes_publicos`."""
    return nomes_publicos(root, [cid], organizacao).get(cid)


def _nome_para_mostrar(conta) -> str:
    return CONTA_EXCLUIDA if conta['excluida_em'] else conta['nome']


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
    `antes` continues a previous page (its `proximo`).

    No number of the store leaves here: the row number of the events table counts every newsroom, and its jumps
    would tell one newsroom how much happens in the others. `proximo` is a position inside this newsroom's own
    events (1 is the oldest one kept), which only its own activity moves."""
    if type(limite) is not int or not 1 <= limite <= 200:
        raise ValueError('O limite da atividade deve ficar entre 1 e 200.')
    if antes is not None and (type(antes) is not int or antes < 1):
        raise ValueError('Continuação da atividade inválida.')
    with _bd(root) as tx:
        # At most MAX_EVENTOS rows: the window of each newsroom.
        linhas = tx.todos('SELECT em, tipo, conta, por FROM eventos WHERE organizacao = ? ORDER BY n', organizacao)
        nomes = {c['id']: _nome_para_mostrar(c) for c in tx.todos(  # a deleted one shows as `CONTA_EXCLUIDA`
            'SELECT id, nome, excluida_em FROM contas WHERE organizacao = ?', organizacao)}
        fim = len(linhas) if antes is None else min(antes - 1, len(linhas))
        inicio = max(0, fim - limite)
        return {'eventos': [{'em': l['em'], 'tipo': l['tipo'], 'conta': l['conta'], 'por': l['por'],
                             'conta_nome': nomes.get(l['conta']), 'por_nome': nomes.get(l['por'])}
                            for l in reversed(linhas[inicio:fim])],
                'proximo': inicio + 1 if inicio > 0 else None}


# --- invitations (equipe-convidar, convite-*) ---------------------------------------------------

def _validar_email(email) -> str:
    texto = email.strip().lower() if isinstance(email, str) else ''
    if not 6 <= len(texto) <= 254 or not EMAIL.fullmatch(texto):
        raise ValueError('Informe um e-mail válido.')
    return texto


def _convite_publico(tx: _Tx, convite) -> dict:
    """What the dono sees of an invitation of the own newsroom. Never the token, and never whether the e-mail has
    an account in another newsroom."""
    quem = tx.um('SELECT nome FROM contas WHERE id = ? AND excluida_em IS NULL', convite['criado_por'])
    return {'id': convite['id'], 'email': convite['email'], 'papel': convite['papel'], 'casos': json.loads(convite['casos']),
            'idioma': convite['idioma'] or IDIOMAS[0], 'estado': convite['estado'], 'criado_em': convite['criado_em'],
            'enviado_em': convite['enviado_em'], 'expira_em': convite['expira_em'], 'envio': convite['envio'],
            'convidado_por': convite['criado_por'], 'convidado_por_nome': quem['nome'] if quem else None}


def _contexto_do_convite(tx: _Tx, convite) -> dict:
    """What the message needs and no answer to the dono carries: the names, and whether the e-mail already has an
    account (the link then creates nothing, and the message says why)."""
    redacao = tx.um('SELECT nome FROM organizacoes WHERE id = ?', convite['organizacao'])
    quem = tx.um('SELECT nome FROM contas WHERE id = ? AND excluida_em IS NULL', convite['criado_por'])
    return {'redacao': redacao['nome'], 'convidado_por': quem['nome'] if quem else None,
            'sem_efeito': bool(tx.um('SELECT 1 FROM contas WHERE email = ?', convite['email']))}


def _pendente(convite, momento: datetime) -> bool:
    return convite['estado'] == 'pendente' and _data(convite['expira_em']) > momento


def _convites_pendentes(tx: _Tx, organizacao: str, momento: datetime) -> list[dict]:
    linhas = tx.todos("SELECT * FROM convites WHERE organizacao = ? AND estado = 'pendente' ORDER BY criado_em, rowid", organizacao)
    return [_convite_publico(tx, linha) for linha in linhas if _pendente(linha, momento)]


def _vencer_convites(tx: _Tx, momento: datetime, organizacao: str | None = None) -> int:
    """Close the pending invitations past their date (their links are dead since then) and say so in the activity."""
    vencidos = [c for c in tx.todos("SELECT id, organizacao, expira_em FROM convites WHERE estado = 'pendente'")
                if _data(c['expira_em']) <= momento and organizacao in (None, c['organizacao'])]
    for convite in vencidos:
        tx.ex("UPDATE convites SET estado = 'expirado', token_sha256 = NULL, encerrado_em = ? WHERE id = ?",
              _iso(momento), convite['id'])
        _evento(tx, 'convite_expirado', None, 'manutencao', momento, organizacao=convite['organizacao'])
    return len(vencidos)


def _convite_da_redacao(tx: _Tx, convite_id, organizacao: str, momento: datetime):
    """A pending invitation of this newsroom, or one refusal for an unknown id, an invitation of another newsroom
    and one already accepted, cancelled or expired."""
    convite = (tx.um('SELECT * FROM convites WHERE id = ? AND organizacao = ?', convite_id, organizacao)
               if isinstance(convite_id, str) else None)
    if not convite or not _pendente(convite, momento):
        raise ValueError(CONVITE_INEXISTENTE)
    return convite


def convidar(root: Path, organizacao: str, por: str, email, papel, casos=(), idioma=None, senha=None,
             ip: str | None = None) -> tuple[dict, str, dict]:
    """Invite an e-mail into the newsroom, with a role and (but for a dono) the cases the person will take part in.
    Returns (invitation as the dono sees it, token, context for the message). The token exists only in the link:
    the store keeps its hash. Inviting as dono asks the password of who invites (contract, 5.15).

    An e-mail that already has an account in ANOTHER newsroom gets the same answer as any other: the invitation is
    listed, sent again, cancelled and expires like the rest, and only the message (context `sem_efeito`) tells the
    person that the link creates nothing. An e-mail of the own newsroom is refused, saying why."""
    email = _validar_email(email)
    if papel not in ATRIBUIVEIS:
        raise ValueError('Papel de acesso inválido.')
    casos = [] if papel == 'dono' else _validar_casos(casos or [], vazio=True)
    if idioma is not None and idioma not in IDIOMAS:
        raise ValueError('Idioma inválido: use pt ou en.')

    def conferir(tx, momento):
        if tx.um('SELECT 1 FROM contas WHERE email = ? AND organizacao = ?', email, organizacao):
            raise ConviteDuplicado('Essa pessoa já faz parte da redação.')
        pendentes = [c for c in tx.todos("SELECT email, estado, expira_em FROM convites WHERE organizacao = ?"
                                         " AND estado = 'pendente'", organizacao) if _pendente(c, momento)]
        if any(c['email'] == email for c in pendentes):
            raise ConviteDuplicado('Já há um convite pendente para esse e-mail: reenvie ou cancele o que existe.')
        if len(pendentes) >= CONVITES_PENDENTES:
            raise LimiteDeConvites(f'A redação já tem {CONVITES_PENDENTES} convites pendentes. Cancele algum ou espere vencer.')
        # Cancelling and inviting again is not a way around "once an hour": each message to the address counts.
        recentes = [c for c in tx.todos('SELECT enviado_em FROM convites WHERE organizacao = ? AND email = ?', organizacao, email)
                    if _data(c['enviado_em']) + timedelta(minutes=REENVIO_MINUTOS) > momento]
        if len(recentes) >= CONVITES_POR_ENDERECO:
            raise LimiteDeConvites('Esse e-mail já recebeu convites demais desta redação na última hora. Espere para convidar de novo.')
        for caso in casos:
            _caso_da_redacao(tx, caso, organizacao)
    with _bd(root) as tx:
        conferir(tx, agora())  # what is wrong with the invitation is said before the password is asked
    if papel == 'dono':
        confirmar_senha(root, por, senha, ip)
    token = secrets.token_urlsafe(32)
    with _bd(root, escrever=True) as tx:
        momento = agora()
        _vencer_convites(tx, momento, organizacao)
        conferir(tx, momento)
        convite_id = secrets.token_hex(8)
        while tx.um('SELECT 1 FROM convites WHERE id = ?', convite_id):
            convite_id = secrets.token_hex(8)
        tx.ex('INSERT INTO convites (id, organizacao, email, papel, casos, idioma, token_sha256, criado_em, criado_por,'
              ' expira_em, enviado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', convite_id, organizacao, email, papel,
              json.dumps(casos), idioma, _hash(token), _iso(momento), por, _iso(momento + timedelta(days=CONVITE_DIAS)),
              _iso(momento))
        convite = tx.um('SELECT * FROM convites WHERE id = ?', convite_id)
        contexto = _contexto_do_convite(tx, convite)
        _evento(tx, 'convite_enviado', None, por, momento, organizacao=organizacao, papel=papel,
                **({'motivo': 'email_em_uso'} if contexto['sem_efeito'] else {}))
        return _convite_publico(tx, convite), token, contexto


def reenviar_convite(root: Path, organizacao: str, por: str, convite_id) -> tuple[dict, str, dict]:
    """Send a pending invitation again: a new token and a new week, and the link of before stops working.
    At most once an hour for each invitation. Returns what `convidar` returns."""
    token = secrets.token_urlsafe(32)
    with _bd(root, escrever=True) as tx:
        momento = agora()
        convite = _convite_da_redacao(tx, convite_id, organizacao, momento)
        if _data(convite['enviado_em']) + timedelta(minutes=REENVIO_MINUTOS) > momento:
            raise LimiteDeConvites('Esse convite foi enviado há menos de uma hora. Espere para reenviar.')
        tx.ex('UPDATE convites SET token_sha256 = ?, expira_em = ?, enviado_em = ?, envio = NULL WHERE id = ?',
              _hash(token), _iso(momento + timedelta(days=CONVITE_DIAS)), _iso(momento), convite['id'])
        convite = tx.um('SELECT * FROM convites WHERE id = ?', convite['id'])
        contexto = _contexto_do_convite(tx, convite)
        _evento(tx, 'convite_reenviado', None, por, momento, organizacao=organizacao)
        return _convite_publico(tx, convite), token, contexto


def cancelar_convite(root: Path, organizacao: str, por: str, convite_id) -> dict:
    """Cancel a pending invitation: its link stops working at once."""
    with _bd(root, escrever=True) as tx:
        momento = agora()
        convite = _convite_da_redacao(tx, convite_id, organizacao, momento)
        tx.ex("UPDATE convites SET estado = 'cancelado', token_sha256 = NULL, encerrado_em = ? WHERE id = ?",
              _iso(momento), convite['id'])
        _evento(tx, 'convite_cancelado', None, por, momento, organizacao=organizacao)
        return _convite_publico(tx, tx.um('SELECT * FROM convites WHERE id = ?', convite['id']))


def registrar_envio(root: Path, convite_id: str, resultado: str) -> None:
    """How the delivery of the invitation's message went (`enviado`, `falha`, or `tela` when the link was shown to
    who invited): the dono sees it in the list of pending invitations."""
    if resultado not in ('enviado', 'falha', 'tela'):
        raise ValueError('Resultado de envio desconhecido.')
    with _bd(root, escrever=True) as tx:
        tx.ex('UPDATE convites SET envio = ? WHERE id = ?', resultado, convite_id)


def _por_convite(tx: _Tx, token, momento: datetime):
    """The pending invitation of a link that can still create an account, or ConviteInvalido."""
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise ConviteInvalido()
    convite = tx.um("SELECT * FROM convites WHERE token_sha256 = ? AND estado = 'pendente'", _hash(token))
    if not convite:
        raise ConviteInvalido()
    if _data(convite['expira_em']) <= momento:
        raise ConviteInvalido('link_expirado')
    if tx.um('SELECT 1 FROM contas WHERE email = ?', convite['email']):
        raise ConviteInvalido('email_em_uso')  # one account belongs to one newsroom only
    redacao = tx.um('SELECT situacao FROM organizacoes WHERE id = ?', convite['organizacao'])
    if not redacao or redacao['situacao'] != 'ativa':
        raise ConviteInvalido()
    return convite


def _convite_recusado(exc: ConviteInvalido) -> None:
    registro_acesso.registrar('ativacao_falha', 'falha', motivo=exc.motivo, acesso_operacao='aceitar')


# --- terms of service with a version (contract of accounts, 8.4 and the delivery 4b-1) ---------------------------

TERMOS_VERSAO = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,31}')
TERMOS_ENDERECO = re.compile(r'https://[^\s"<>\\]{1,490}')
TERMOS_NOVOS = 'Os termos de uso mudaram. Leia a versão em vigor e aceite-a para continuar.'


def termos_vigentes() -> dict | None:
    """The terms in force, from whoever runs the service: `VLADO_TERMOS_VERSAO` and `VLADO_TERMOS_ENDERECO` (the text
    is the Documentation's and lives at that address; the server never serves it). None without a version: nobody
    has the pending item and the acceptance takes no version, as before. A version without a valid address, or a
    malformed one, raises ValueError: the server refuses to start rather than ask to accept what nobody can read."""
    versao = os.environ.get('VLADO_TERMOS_VERSAO', '').strip()
    endereco = os.environ.get('VLADO_TERMOS_ENDERECO', '').strip()
    if not versao:
        if endereco:
            raise ValueError('VLADO_TERMOS_ENDERECO definido sem VLADO_TERMOS_VERSAO.')
        return None
    if not TERMOS_VERSAO.fullmatch(versao):
        raise ValueError('VLADO_TERMOS_VERSAO inválida: até 32 letras, dígitos, ponto, hífen ou sublinhado.')
    if not TERMOS_ENDERECO.fullmatch(endereco):
        raise ValueError('VLADO_TERMOS_ENDERECO ausente ou inválido: o endereço https:// do texto dos termos.')
    return {'versao': versao, 'endereco': endereco}


def _ultimo_aceite(tx: _Tx, cid: str):
    return tx.um('SELECT versao, aceito_em FROM termos_aceites WHERE conta = ? ORDER BY aceito_em DESC, rowid DESC LIMIT 1',
                 cid)


def _aceitar(tx: _Tx, cid: str, versao: str, momento: datetime, ip: str | None) -> None:
    """One row per acceptance; nothing is ever rewritten (only the address goes, when the account is deleted)."""
    tx.ex('INSERT INTO termos_aceites (conta, versao, aceito_em, ip) VALUES (?, ?, ?, ?)', cid, versao, _iso(momento), ip)
    _evento(tx, 'termos_aceitos', cid, cid, momento, versao=versao)


def _versao_aceita(termos_versao, termos: dict | None) -> str | None:
    """The version an acceptance may carry: the one in force, or None when there are no terms."""
    if termos is None:
        if termos_versao is not None:
            raise ValueError('Versão dos termos desconhecida.')
        return None
    if termos_versao != termos['versao']:
        raise TermosDesatualizados(TERMOS_NOVOS)
    return termos_versao


def aceitar_termos(root: Path, cid, versao, termos: dict | None, ip: str | None = None) -> dict:
    """`conta-termos-aceitar`: the person accepts the version in force. Accepting the one already accepted writes
    nothing. Returns `{versao, aceito_em}` of the last acceptance. Without terms in force, any version is not the one
    in force: the same refusal, one code for the page."""
    if termos is None:
        raise TermosDesatualizados('Não há termos de uso a aceitar neste serviço.')
    _versao_aceita(versao, termos)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid)
        ultimo = _ultimo_aceite(tx, conta['id'])
        if not ultimo or ultimo['versao'] != termos['versao']:
            _aceitar(tx, conta['id'], termos['versao'], agora(), ip)
        return dict(_ultimo_aceite(tx, conta['id']))


def consultar_convite(root: Path, token, termos: dict | None = None) -> dict:
    """What the acceptance page shows (read-only): newsroom, e-mail, role, who invited, until when, and the terms in
    force (`termos`, from `termos_vigentes` where the service has them). The e-mail comes from the invitation and is
    not changed on acceptance."""
    try:
        with _bd(root) as tx:
            convite = _por_convite(tx, token, agora())
            contexto = _contexto_do_convite(tx, convite)
            return {'redacao': contexto['redacao'], 'email': convite['email'], 'papel': convite['papel'],
                    'convidado_por': contexto['convidado_por'], 'expira_em': convite['expira_em'],
                    'idioma': convite['idioma'] or IDIOMAS[0], 'termos_versao': termos['versao'] if termos else None,
                    'termos_endereco': termos['endereco'] if termos else None}
    except ConviteInvalido as exc:
        _convite_recusado(exc)
        raise


def aceitar_convite(root: Path, token, nome, senha, termos_versao=None, ip: str | None = None, cliente='web',
                    aparelho=None, marca=None, termos: dict | None = None) -> tuple[str, str, dict]:
    """Accept an invitation: the account is born with the invitation's e-mail, role and participations, and its
    first session opens. Returns what `entrar` returns. The link works once. Where the service has terms
    (`termos`), `termos_versao` must be the one in force, and the acceptance is written with the account."""
    nome, senha = _validar_nome(nome), _validar_senha(senha)
    versao = _versao_aceita(termos_versao, termos)
    try:
        with _bd(root) as tx:
            _por_convite(tx, token, agora())  # refuse before spending time on the hash
        with _VezDoHash():
            senha_hash = _HASHER.hash(senha)
        with _bd(root, escrever=True) as tx:
            momento = agora()
            convite = _por_convite(tx, token, momento)
            cid = secrets.token_hex(8)
            while tx.um('SELECT 1 FROM contas WHERE id = ?', cid):
                cid = secrets.token_hex(8)
            tx.ex('INSERT INTO contas (id, organizacao, papel, nome, email, idioma, senha_hash, senha_definida_em, criada_em,'
                  ' criada_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', cid, convite['organizacao'], convite['papel'], nome,
                  convite['email'], convite['idioma'], senha_hash, _iso(momento), _iso(momento), convite['criado_por'])
            # A case deleted, or moved, since the invitation is left out: the rest of the invitation still holds.
            casos = [caso for caso in json.loads(convite['casos'])
                     if tx.um('SELECT 1 FROM casos WHERE caso = ? AND organizacao = ? AND apagada_em IS NULL',
                              caso, convite['organizacao'])]
            _definir_participacoes(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), casos, convite['criado_por'], momento)
            tx.ex("UPDATE convites SET estado = 'aceito', token_sha256 = NULL, encerrado_em = ?, conta = ? WHERE id = ?",
                  _iso(momento), cid, convite['id'])
            _evento(tx, 'convite_aceito', cid, cid, momento, papel=convite['papel'])
            if versao is not None:
                _aceitar(tx, cid, versao, momento, ip)
            sid, csrf = _abrir_sessao(tx, cid, momento, cliente, aparelho, ip)
            _registrar_aparelho(tx, cid, marca, momento)  # the browser that accepted is the account's first known device
            return sid, csrf, _publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', cid), momento)
    except ConviteInvalido as exc:
        _convite_recusado(exc)
        raise


def manutencao(root: Path) -> dict:
    """The daily sweep (`acesso.py manutencao`, and once when the server starts): closes the invitations past their
    date and prunes the newsrooms' activity older than ATIVIDADE_DIAS (what leaves goes to the audit log, as when
    the window is full). Inactive accounts come with the life cycle."""
    with _bd(root, escrever=True) as tx:
        momento = agora()
        vencidos = _vencer_convites(tx, momento)
        limite, podados = _iso(momento - timedelta(days=ATIVIDADE_DIAS)), 0
        for antigo in tx.todos('SELECT n, em, tipo, conta, por FROM eventos WHERE em <= ? ORDER BY n', limite):
            copia = {k: antigo[k] for k in ('em', 'tipo', 'conta', 'por')}
            tx.depois.append(lambda copia=copia: registro_acesso.arquivar_evento(copia))
            tx.ex('DELETE FROM eventos WHERE n = ?', antigo['n'])
            podados += 1
        # Recovery requests nobody confirmed in time, and links past their date, are just cleared.
        recuperacoes = tx.ex("UPDATE recuperacoes SET estado = 'expirada', encerrada_em = ? WHERE estado = 'pendente'"
                             ' AND expira_em <= ?', _iso(momento), _iso(momento)).rowcount
        tx.ex('DELETE FROM links WHERE expira_em <= ?', _iso(momento))
        return {'convites_vencidos': vencidos, 'eventos_podados': podados, 'recuperacoes_vencidas': recuperacoes}


# --- password reset by e-mail (senha-esqueci, senha-redefinir) ------------------------------------

def _destinatario(conta) -> dict:
    """What a message to the account's own address needs: never shown to anybody else."""
    return {'id': conta['id'], 'email': conta['email'], 'nome': conta['nome'], 'idioma': conta['idioma'] or IDIOMAS[0]}


def pedir_redefinicao(root: Path, email) -> tuple[str, dict] | None:
    """A person forgot the password and typed the e-mail. Returns (token, who to write to) when a message must go,
    or None; the caller answers the same in both cases, and what it does next must not depend on which.

    The store is written the same way whether an account has the address or not (when a reset was last asked for
    it), so neither the answer nor its time tells. An address gets at most one message every
    REDEFINICAO_INTERVALO_MINUTOS, and a new link kills the one before. Only an active account with a password, in
    an active newsroom, gets a link; the token exists only in the message."""
    texto = email.strip().lower() if isinstance(email, str) else ''
    if not 6 <= len(texto) <= 254 or not EMAIL.fullmatch(texto):
        return None
    token, chave = secrets.token_urlsafe(32), CHAVE_ESQUECI + texto
    with _bd(root, escrever=True) as tx:
        momento = agora()
        ultimo = tx.um('SELECT em FROM tentativas WHERE chave = ?', chave)
        conta = tx.um('SELECT * FROM contas WHERE email = ?', texto)
        if ultimo and ultimo['em'] and _data(ultimo['em']) + timedelta(minutes=REDEFINICAO_INTERVALO_MINUTOS) > momento:
            return None  # asked a moment ago: nothing new is sent, to anybody
        tx.ex('INSERT INTO tentativas (chave, falhas, bloqueado_ate, em) VALUES (?, 0, NULL, ?) ON CONFLICT (chave) DO UPDATE'
              ' SET em = excluded.em', chave, _iso(momento))
        _podar_tentativas(tx, momento)
        redacao = tx.um('SELECT situacao FROM organizacoes WHERE id = ?', conta['organizacao']) if conta else None
        if not conta or not conta['ativa'] or not conta['senha_hash'] or not redacao or redacao['situacao'] != 'ativa':
            tx.depois.append(lambda: registro_acesso.registrar(
                'redefinicao_pedida', 'falha', conta['id'] if conta else None, momento,
                motivo='conta_inativa' if conta else 'nao_encontrado',
                login_ref=None if conta else registro_acesso.referencia_do_login(texto)))
            return None
        tx.ex("DELETE FROM links WHERE conta = ? AND tipo = 'redefinicao'", conta['id'])
        tx.ex("INSERT INTO links (token_sha256, tipo, conta, criado_em, expira_em) VALUES (?, 'redefinicao', ?, ?, ?)",
              _hash(token), conta['id'], _iso(momento), _iso(momento + timedelta(minutes=REDEFINICAO_MINUTOS)))
        _evento(tx, 'redefinicao_pedida', conta['id'], conta['id'], momento)
        return token, _destinatario(conta)


def _por_link(tx: _Tx, token, tipos: tuple, momento: datetime, mensagem=None):
    """(link, account) of a link that can still be used, or LinkInvalido."""
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise LinkInvalido(mensagem=mensagem)
    link = tx.um('SELECT * FROM links WHERE token_sha256 = ?', _hash(token))
    if not link or link['tipo'] not in tipos:
        raise LinkInvalido(mensagem=mensagem)
    if _data(link['expira_em']) <= momento:
        raise LinkInvalido('link_expirado', mensagem)
    conta = tx.um('SELECT * FROM contas WHERE id = ?', link['conta'])
    if not conta or not conta['ativa'] or conta['excluida_em']:
        raise LinkInvalido(mensagem=mensagem)
    return link, conta


LINKS_DE_SENHA = ('redefinicao', 'recuperacao')  # the person asked ("esqueci a senha") or a dono asked for the person


def redefinir_senha(root: Path, token, senha, codigo=None, ip: str | None = None, marca=None) -> dict:
    """Set a new password from the link of the reset message, or of the recovery a dono asked: every session of the
    account ends, the link (and any other pending one) dies, and the person signs in next. Returns who to tell
    that the password changed.

    An account with a second factor also gives its code (`codigo`) to reset by e-mail: the mailbox alone is not
    enough. A recovery asked by a dono, already confirmed by two parties, removes the factor instead: the person
    lost it, and enrols again.

    `marca` is the device mark of the browser that uses the link: it becomes the ONLY known device of the account.
    The link is something only the owner of the mailbox has, so this is the way out for somebody kept in protected
    mode by another person's wrong passwords; and whoever had got into the account stops being a known device."""
    senha = _validar_senha(senha)
    try:
        with _bd(root) as tx:
            link, conta = _por_link(tx, token, LINKS_DE_SENHA, agora())  # refuse before spending time on the hash
            pede_codigo = link['tipo'] == 'redefinicao' and bool(
                tx.um('SELECT 1 FROM fatores WHERE conta = ? AND ativo = 1', conta['id']))
        if pede_codigo:
            exigir_codigo(root, conta['id'], codigo, ip)
        with _VezDoHash():
            senha_hash = _HASHER.hash(senha)
        with _bd(root, escrever=True) as tx:
            momento = agora()
            link, conta = _por_link(tx, token, LINKS_DE_SENHA, momento)
            cid = conta['id']
            if link['tipo'] == 'recuperacao' and tx.um('SELECT 1 FROM fatores WHERE conta = ?', cid):
                _sem_fator(tx, cid)
                # Not `fator_removido`, which is the person taking away the own factor: the activity of the
                # newsroom tells the two apart.
                _evento(tx, FATOR_RETIRADO, cid, cid, momento)
            tx.ex('UPDATE contas SET senha_hash = ?, senha_definida_em = ?, ativacao_sha256 = NULL, ativacao_expira_em = NULL,'
                  ' ativacao_motivo = NULL WHERE id = ?', senha_hash, _iso(momento), cid)
            _derrubar_sessoes(tx, cid)
            _so_este_aparelho(tx, cid, marca, momento)
            _limpar_tentativas(tx, conta)
            tx.ex('DELETE FROM tentativas WHERE chave = ?', CHAVE_CONFIRMACAO + cid)
            _evento(tx, 'senha_redefinida', cid, cid, momento)
            return _destinatario(conta)
    except LinkInvalido as exc:
        registro_acesso.registrar('ativacao_falha', 'falha', motivo=exc.motivo, acesso_operacao='redefinir')
        raise


# --- the second factor (conta-fator-*, entrar-segundo-fator) --------------------------------------

def _sem_fator(tx: _Tx, cid: str) -> None:
    tx.ex('DELETE FROM fatores WHERE conta = ?', cid)
    tx.ex('DELETE FROM codigos_reserva WHERE conta = ?', cid)
    tx.ex('DELETE FROM tentativas WHERE chave IN (?, ?)', CHAVE_FATOR + cid, CHAVE_RESERVA + cid)


def _estado_do_fator(tx: _Tx, cid: str) -> dict:
    fator = tx.um('SELECT ativado_em FROM fatores WHERE conta = ? AND ativo = 1', cid)
    restantes = tx.um('SELECT COUNT(*) AS n FROM codigos_reserva WHERE conta = ? AND usado_em IS NULL', cid)['n']
    return {'ativo': bool(fator), 'ativado_em': fator['ativado_em'] if fator else None,
            'codigos_restantes': restantes if fator else 0}


def _usar_codigo(tx: _Tx, root: Path, cid: str, codigo, momento: datetime) -> str | None:
    """'totp' or 'reserva' when `codigo` is good for the account's active factor, and then it is spent (the step of
    the authenticator, or the reserve code); None otherwise. Neither kind is ever accepted twice."""
    fator = tx.um('SELECT semente, ultimo_passo FROM fatores WHERE conta = ? AND ativo = 1', cid)
    if not fator:
        return None
    # The reserve code first, by its shape: it is checked against its own hash and needs neither the seed nor the
    # key of the seeds, so it still lets the person in when that key is missing (a restore without `segredos/`).
    resumo = segundo_fator.resumo_da_reserva(codigo)
    if resumo:
        if tx.ex('UPDATE codigos_reserva SET usado_em = ? WHERE conta = ? AND resumo = ? AND usado_em IS NULL',
                 _iso(momento), cid, resumo).rowcount:
            _evento(tx, 'codigo_reserva_usado', cid, cid, momento)
            return 'reserva'
        return None
    passo = segundo_fator.conferir(_semente_do_fator(root, fator['semente'], cid), codigo, momento, fator['ultimo_passo'])
    if passo is not None:
        tx.ex('UPDATE fatores SET ultimo_passo = ? WHERE conta = ?', passo, cid)
        return 'totp'
    return None


def _semente_do_fator(root: Path, guardada, cid: str) -> bytes:
    """The seed of an account, opened. When it does not open (the key file is missing or is another one) that is
    told to the operator in the audit log and to the person as FatorIndisponivel: not a wrong code."""
    try:
        return segundo_fator.decifrar(root, guardada, cid)
    except (segundo_fator.ChaveIlegivel, segundo_fator.SementeIlegivel) as exc:
        registro_acesso.registrar('fator_indisponivel', 'falha', cid,
                                  motivo='chave_ausente' if isinstance(exc, segundo_fator.ChaveIlegivel) else 'semente_ilegivel')
        raise FatorIndisponivel(FATOR_INDISPONIVEL) from exc


def conferir_chave_do_fator(root: Path) -> str | None:
    """For the start of the server: the warning for the operator when accounts have a second factor and the key of
    their seeds is missing, unreadable or another one (a restore without `segredos/`), or None. It also goes to
    the audit log. Nothing is made or repaired here."""
    with _bd(root) as tx:
        ativos = tx.todos('SELECT conta, semente FROM fatores WHERE ativo = 1 ORDER BY conta')
    if not ativos:
        return None
    try:
        segundo_fator.decifrar(root, ativos[0]['semente'], ativos[0]['conta'])
        return None
    except segundo_fator.ChaveIlegivel:
        motivo, defeito = 'chave_ausente', 'não está nesta instalação, ou está ilegível'
    except segundo_fator.SementeIlegivel:
        motivo, defeito = 'semente_ilegivel', 'não é a que cifrou as sementes guardadas'
    registro_acesso.lembrar_raiz(root)
    registro_acesso.registrar('fator_indisponivel', 'falha', motivo=motivo)
    return (f'ATENÇÃO: {len(ativos)} conta(s) têm segundo fator e a chave das sementes (segredos/contas.chave) {defeito}. '
            'Os códigos do aplicativo não serão aceitos, só os códigos de reserva. Restaure o arquivo a partir da cópia '
            'guardada com os segredos (deploy/BACKUP.md). Não crie outro: as sementes já cadastradas não abririam com ele.')


def _fator_recusado(tx: _Tx, cid: str, momento: datetime, ip: str | None) -> None:
    tx.depois.append(lambda: registro_acesso.registrar('fator_recusado', 'falha', cid, momento, motivo='codigo_invalido', ip=ip))


def _falha_do_fator(tx: _Tx, cid: str, momento: datetime, ip: str | None) -> dict | None:
    """A wrong code of the second factor, counted on the account, whatever the address or the ticket it came
    with: the fifth in a row blocks the factor of the account for 15 minutes, in the sign-in and in every
    operation that asks it. After the right password the existence of the account is no secret, so counting on
    it tells nothing. Returns who to tell when this failure starts the block (event `fator_bloqueado`)."""
    _fator_recusado(tx, cid, momento, ip)
    if not _registrar_falha(tx, CHAVE_FATOR + cid, None, momento):
        return None
    _evento(tx, 'fator_bloqueado', cid, None, momento)
    return _destinatario(tx.um('SELECT * FROM contas WHERE id = ?', cid))


def _conferir_codigo(tx: _Tx, root: Path, cid: str, codigo, momento: datetime, ip: str | None) -> tuple:
    """The whole rule of a code of the second factor of an account, for the sign-in and for the operations that
    ask it: (kind accepted or None, the answer is a block, a wrong code was counted, who to tell).

    A code of the authenticator is not even tried while the factor is blocked. A reserve code crosses that block:
    it has 80 random bits, so letting it be tried gives nothing to who guesses, and it is the way in of the person
    whose password somebody else has and uses to keep the factor blocked. A right one always passes; the wrong
    ones count on a counter of their own, which never blocks the authenticator nor a right reserve code."""
    if segundo_fator.resumo_da_reserva(codigo):
        if _usar_codigo(tx, root, cid, codigo, momento):
            tx.ex('DELETE FROM tentativas WHERE chave = ? OR (chave = ? AND bloqueado_ate IS NULL)',
                  CHAVE_RESERVA + cid, CHAVE_FATOR + cid)
            return 'reserva', False, False, None
        if _bloqueado(tx, CHAVE_RESERVA + cid, momento):
            return None, True, False, None
        _fator_recusado(tx, cid, momento, ip)
        return None, _registrar_falha(tx, CHAVE_RESERVA + cid, None, momento), True, None
    if _bloqueado(tx, CHAVE_FATOR + cid, momento):
        return None, True, False, None
    if _usar_codigo(tx, root, cid, codigo, momento):
        tx.ex('DELETE FROM tentativas WHERE chave = ?', CHAVE_FATOR + cid)
        return 'totp', False, False, None
    aviso = _falha_do_fator(tx, cid, momento, ip)
    return None, bool(aviso), True, aviso


def _recusa_do_codigo(aviso: dict | None, bloqueado: bool) -> Exception:
    if aviso:
        return FatorBloqueado(aviso)
    return Bloqueado(BLOQUEADO) if bloqueado else CodigoInvalido(CODIGO_INVALIDO)


def _sem_codigo(codigo) -> bool:
    return not isinstance(codigo, str) or not codigo.strip()


def exigir_codigo(root: Path, cid: str, codigo, ip: str | None = None) -> None:
    """The second factor asked by an operation of an account that has one (new reserve codes, a new device, a reset
    of the password by e-mail). A wrong code counts: five in a row block it for this account for 15 minutes.
    A code that did not come is asked for (CodigoNecessario) and counts for nothing. Raises CodigoNecessario,
    CodigoInvalido or Bloqueado."""
    if _sem_codigo(codigo):
        raise CodigoNecessario(CODIGO_NECESSARIO)
    bloqueado, aviso = False, None
    with _bd(root, escrever=True) as tx:
        aceito, bloqueado, _, aviso = _conferir_codigo(tx, root, cid, codigo, agora(), ip)
        if aceito:
            return
    raise _recusa_do_codigo(aviso, bloqueado)


def iniciar_fator(root: Path, cid: str, senha, codigo=None, ip: str | None = None) -> dict:
    """Start enrolling an authenticator: asks the password and gives the new seed, once, as text and as an
    `otpauth://` address. Nothing changes until `confirmar_fator` proves the app has it. An account that already
    has a factor (a new phone) also gives a code of the current one, or a reserve code."""
    confirmar_senha(root, cid, senha, ip)
    with _bd(root) as tx:
        ativo = bool(tx.um('SELECT 1 FROM fatores WHERE conta = ? AND ativo = 1', cid))
        algum = bool(tx.um('SELECT 1 FROM fatores WHERE ativo = 1 LIMIT 1'))
    if ativo:
        exigir_codigo(root, cid, codigo, ip)
    semente = segundo_fator.nova_semente()
    try:
        # The key file is only made while no account has a factor. If one has and the file is gone (a restore
        # without `segredos/`), a new key would leave every stored seed unreadable for good: nobody enrols until
        # the operator puts the file back.
        cifrada = segundo_fator.cifrar(root, semente, cid, criar_chave=not algum)
    except segundo_fator.ChaveIlegivel as exc:
        registro_acesso.registrar('fator_indisponivel', 'falha', cid, motivo='chave_ausente', ip=ip)
        raise FatorIndisponivel(CADASTRO_INDISPONIVEL) from exc
    with _bd(root, escrever=True) as tx:
        conta, momento = _conta(tx, cid), agora()
        tx.ex('INSERT INTO fatores (conta, criado_em, pendente, pendente_em) VALUES (?, ?, ?, ?) ON CONFLICT (conta) DO UPDATE'
              ' SET pendente = excluded.pendente, pendente_em = excluded.pendente_em', cid, _iso(momento), cifrada, _iso(momento))
        return {'segredo': segundo_fator.em_base32(semente),
                'otpauth': segundo_fator.endereco(semente, conta['email'] or conta['login'] or cid)}


def confirmar_fator(root: Path, cid: str, codigo, ip: str | None = None, sessao_atual=None) -> list[str]:
    """Finish the enrolment with a code of the new authenticator: the factor becomes the account's (the one
    before, if any, is replaced) and ten new reserve codes are returned, to be shown once. Every other session of
    the account ends, as when the password changes: a session somebody else opened with the password alone does
    not outlive the factor. `sessao_atual` is the public id of the session that asks, the only one kept."""
    if _sem_codigo(codigo):
        raise CodigoNecessario(CODIGO_NECESSARIO)
    chave, codigos, bloqueado, aviso = CHAVE_FATOR + cid, segundo_fator.novos_codigos_de_reserva(), False, None
    with _bd(root, escrever=True) as tx:
        momento = agora()
        fator = tx.um('SELECT pendente, pendente_em FROM fatores WHERE conta = ?', cid)
        if (not fator or not fator['pendente']
                or _data(fator['pendente_em']) + timedelta(minutes=FATOR_PENDENTE_MINUTOS) <= momento):
            raise ValueError('Comece de novo o cadastro do segundo fator.')
        bloqueado = _bloqueado(tx, chave, momento)
        if not bloqueado:
            passo = segundo_fator.conferir(_semente_do_fator(root, fator['pendente'], cid), codigo, momento)
            if passo is not None:
                tx.ex('UPDATE fatores SET semente = pendente, pendente = NULL, pendente_em = NULL, ativo = 1, ativado_em = ?,'
                      ' ultimo_passo = ? WHERE conta = ?', _iso(momento), passo, cid)
                _novos_codigos(tx, cid, codigos, momento)
                tx.ex('DELETE FROM tentativas WHERE chave = ?', chave)
                tx.ex('DELETE FROM sessoes WHERE conta = ? AND publico IS NOT ?', cid, sessao_atual)
                _evento(tx, 'fator_ativado', cid, cid, momento)
                return codigos
            aviso = _falha_do_fator(tx, cid, momento, ip)
    raise _recusa_do_codigo(aviso, bloqueado)


def _novos_codigos(tx: _Tx, cid: str, codigos: list[str], momento: datetime) -> None:
    tx.ex('DELETE FROM codigos_reserva WHERE conta = ?', cid)
    for codigo in codigos:
        tx.ex('INSERT INTO codigos_reserva (conta, resumo, criado_em) VALUES (?, ?, ?)', cid,
              segundo_fator.resumo_da_reserva(codigo), _iso(momento))


def novos_codigos_do_fator(root: Path, cid: str, senha, codigo, ip: str | None = None) -> list[str]:
    """New reserve codes; the ones before stop working. Asks the password and a code."""
    confirmar_senha(root, cid, senha, ip)
    exigir_codigo(root, cid, codigo, ip)
    codigos = segundo_fator.novos_codigos_de_reserva()
    with _bd(root, escrever=True) as tx:
        momento = agora()
        if not tx.um('SELECT 1 FROM fatores WHERE conta = ? AND ativo = 1', cid):
            raise ValueError('Esta conta não tem segundo fator.')
        _novos_codigos(tx, cid, codigos, momento)
        _evento(tx, 'fator_codigos_gerados', cid, cid, momento)
        return codigos


def remover_fator(root: Path, cid: str, senha, ip: str | None = None) -> None:
    """Remove the own second factor (whoever must have one is refused before, by the gate). Asks the password."""
    confirmar_senha(root, cid, senha, ip)
    with _bd(root, escrever=True) as tx:
        if not tx.um('SELECT 1 FROM fatores WHERE conta = ?', cid):
            raise ValueError('Esta conta não tem segundo fator.')
        _sem_fator(tx, cid)
        _evento(tx, 'fator_removido', cid, cid)


def entrar_segundo_fator(root: Path, bilhete, codigo, ip: str | None = None, marca=None) -> tuple[str, str, dict]:
    """The second step of the sign-in: the ticket `entrar` gave and a code of the authenticator (or a reserve
    code). Returns what `entrar` returns. A wrong code counts on the ticket, which dies at the fifth, on the
    counters of the sign-in (identifier and address, and the identifier alone) and on the account: five wrong
    codes in a row, from any addresses and with any tickets, block the second factor of the account for 15
    minutes (FatorBloqueado on the fifth, Bloqueado while it lasts, when nothing is tried, counted or spent).
    An unknown, expired or dead ticket is EntradaExpirada. A code that did not come is asked for
    (CodigoNecessario) and leaves the ticket as it was."""
    if _sem_codigo(codigo):
        raise CodigoNecessario(CODIGO_NECESSARIO)
    momento = agora()
    try:
        _limite_ip(ip, momento)
    except Bloqueado:
        registro_acesso.registrar_limite_ip('login_falha', ip, _rede(ip), acesso_operacao='segundo_fator')
        raise
    errou, bloqueado, aviso, morto = False, False, None, False
    with _bd(root, escrever=True) as tx:
        entrada = (tx.um('SELECT * FROM entradas WHERE id_sha256 = ?', _hash(bilhete))
                   if isinstance(bilhete, str) and SID.fullmatch(bilhete) else None)
        conta = tx.um('SELECT * FROM contas WHERE id = ?', entrada['conta']) if entrada else None
        if entrada and (_data(entrada['expira_em']) <= momento or not conta or not conta['ativa']):
            tx.ex('DELETE FROM entradas WHERE id_sha256 = ?', entrada['id_sha256'])
        elif entrada:
            cid = conta['id']
            aceito, bloqueado, contou, aviso = _conferir_codigo(tx, root, cid, codigo, momento, ip)
            if aceito:
                tx.ex('DELETE FROM entradas WHERE conta = ?', cid)
                tx.ex('DELETE FROM tentativas WHERE chave = ?', entrada['chave'])
                return _sessao_aberta(tx, conta, momento, entrada['cliente'], entrada['aparelho'], ip, marca)
            if contou:  # an attempt during a block is neither tried, counted nor spent
                errou = True
                if entrada['falhas'] + 1 >= ENTRADA_FALHAS:
                    tx.ex('DELETE FROM entradas WHERE id_sha256 = ?', entrada['id_sha256'])
                    morto = True
                else:
                    tx.ex('UPDATE entradas SET falhas = falhas + 1 WHERE id_sha256 = ?', entrada['id_sha256'])
                _registrar_falha(tx, entrada['chave'], cid, momento)
                _falha_do_identificador(tx, entrada['chave'].split('|', 1)[0], cid, momento)  # the same ceilings as the password
    if errou or bloqueado:
        recusa = _recusa_do_codigo(aviso, bloqueado)
        recusa.bilhete_morto = morto  # the fifth wrong code of a ticket: whoever answers also clears its cookie
        raise recusa
    raise EntradaExpirada(ENTRADA_EXPIRADA)


# --- recovery asked by a dono (equipe-recuperar, equipe-recuperar-confirmar) ----------------------

RECUPERACAO_INEXISTENTE = 'Pedido de recuperação não encontrado.'
SO_PELO_OPERADOR = 'Essa recuperação é feita pelo operador do serviço, pelo terminal.'


def _link_de_recuperacao(tx: _Tx, conta, momento: datetime) -> str:
    """A fresh recovery link of the account (the one before dies). Nothing of the account changes until it is used."""
    token = secrets.token_urlsafe(32)
    tx.ex("DELETE FROM links WHERE conta = ? AND tipo = 'recuperacao'", conta['id'])
    tx.ex("INSERT INTO links (token_sha256, tipo, conta, criado_em, expira_em) VALUES (?, 'recuperacao', ?, ?, ?)",
          _hash(token), conta['id'], _iso(momento), _iso(momento + timedelta(hours=RECUPERACAO_HORAS)))
    return token


def _recuperacao_publica(tx: _Tx, linha) -> dict:
    nomes = {c['id']: _nome_para_mostrar(c) for c in tx.todos('SELECT id, nome, excluida_em FROM contas WHERE id IN (?, ?)'
                                                               ' AND organizacao = ?', linha['conta'], linha['pedida_por'],
                                                               linha['organizacao'])}
    return {'id': linha['id'], 'conta': linha['conta'], 'conta_nome': nomes.get(linha['conta']),
            'pedida_por': linha['pedida_por'], 'pedida_por_nome': nomes.get(linha['pedida_por']),
            'pedida_em': linha['pedida_em'], 'expira_em': linha['expira_em'], 'estado': linha['estado']}


def _recuperacoes_pendentes(tx: _Tx, organizacao: str, momento: datetime) -> list:
    linhas = tx.todos("SELECT * FROM recuperacoes WHERE organizacao = ? AND estado = 'pendente' ORDER BY pedida_em, rowid",
                      organizacao)
    return [linha for linha in linhas if _data(linha['expira_em']) > momento]


def _outros_donos(tx: _Tx, organizacao: str, *exceto) -> int:
    return len([c for c in tx.todos("SELECT id FROM contas WHERE organizacao = ? AND papel = 'dono' AND ativa = 1"
                                    ' AND excluida_em IS NULL AND senha_hash IS NOT NULL', organizacao)
                if c['id'] not in exceto])


def pedir_recuperacao(root: Path, organizacao: str, por: str, cid, senha=None, ip: str | None = None, *,
                      com_envio: bool, na_tela: bool = False) -> dict:
    """A dono asks the recovery of another person's access. Always two parties (contract, 8.2), always the password
    of who asks, and the account is checked before the password.

    - The person is not a dono, has an e-mail and there is real delivery (`com_envio`): the link goes to the person,
      who is the second party; nothing changes until it is used. Returns `{estado: 'enviada', token, destinatario,
      por_email: True}`.
    - The person is not a dono and the link may be shown on the screen (`na_tela`: the installed Mesa, one machine
      and one newsroom, never the hosted service): the password of who asks is the confirmation, and the link is
      handed to who asked (decision P33). Returns `{estado: 'confirmada', ..., por_email: False}`.
    - The person is a dono: the request waits RECUPERACAO_HORAS for a third dono (`confirmar_recuperacao`); returns
      `{estado: 'aguardando_confirmacao', recuperacao}`. It is only accepted when, once confirmed, the link has a way
      to the person (her e-mail with real delivery, or the screen where allowed).
    - No third dono, or no way to hand the link over (the hosted service never shows it): SoPeloOperador."""
    def conferir(tx, momento):
        alvo = _conta(tx, cid, organizacao)
        if cid == por:
            raise ValueError('Para a sua própria senha, use "Esqueci a senha" ou a página Minha conta.')
        if not alvo['ativa']:
            raise ValueError('Reative a conta antes de recuperar o acesso dela.')
        por_email = bool(com_envio and alvo['email'])
        direto = alvo['papel'] != 'dono' and (por_email or na_tela)
        if not direto:
            if not (por_email or na_tela) or not _outros_donos(tx, organizacao, por, cid):
                raise SoPeloOperador(SO_PELO_OPERADOR)
            if any(r['conta'] == cid for r in _recuperacoes_pendentes(tx, organizacao, momento)):
                raise ValueError('Já há um pedido de recuperação à espera de confirmação para essa conta.')
        elif tx.um("SELECT 1 FROM links WHERE conta = ? AND tipo = 'recuperacao' AND criado_em > ?", cid,
                   _iso(momento - timedelta(minutes=REDEFINICAO_INTERVALO_MINUTOS))):
            raise ValueError('Um link de recuperação acabou de ser enviado a essa pessoa. Espere alguns minutos.')
        return alvo, direto, por_email
    with _bd(root) as tx:
        conferir(tx, agora())  # an unknown account, or one of another newsroom, is refused before the password
    confirmar_senha(root, por, senha, ip)
    with _bd(root, escrever=True) as tx:
        momento = agora()
        alvo, direto, por_email = conferir(tx, momento)
        _evento(tx, 'recuperacao_pedida', cid, por, momento)
        if direto:
            return {'estado': 'enviada' if por_email else 'confirmada', 'token': _link_de_recuperacao(tx, alvo, momento),
                    'destinatario': _destinatario(alvo), 'por_email': por_email}
        rid = secrets.token_hex(8)
        while tx.um('SELECT 1 FROM recuperacoes WHERE id = ?', rid):
            rid = secrets.token_hex(8)
        tx.ex('INSERT INTO recuperacoes (id, organizacao, conta, pedida_por, pedida_em, expira_em) VALUES (?, ?, ?, ?, ?, ?)',
              rid, organizacao, cid, por, _iso(momento), _iso(momento + timedelta(hours=RECUPERACAO_HORAS)))
        return {'estado': 'aguardando_confirmacao',
                'recuperacao': _recuperacao_publica(tx, tx.um('SELECT * FROM recuperacoes WHERE id = ?', rid))}


def confirmar_recuperacao(root: Path, organizacao: str, por: str, rid, senha=None, ip: str | None = None, *,
                          com_envio: bool, na_tela: bool = False) -> dict:
    """A third dono (neither who asked nor the person) confirms a pending recovery, with the own password; the link
    is then made. Returns `{estado, token, destinatario, por_email}`: with `por_email` the caller sends the link to
    the person; without it (only where `na_tela` is allowed) the caller shows it to who confirmed.
    An unknown request, one of another newsroom, an expired one and one whose asker is no longer a dono are the same."""
    def conferir(tx, momento):
        linha = (tx.um("SELECT * FROM recuperacoes WHERE id = ? AND organizacao = ? AND estado = 'pendente'", rid, organizacao)
                 if isinstance(rid, str) else None)
        if not linha or _data(linha['expira_em']) <= momento:
            raise ValueError(RECUPERACAO_INEXISTENTE)
        pediu = tx.um("SELECT 1 FROM contas WHERE id = ? AND organizacao = ? AND papel = 'dono' AND ativa = 1"
                      ' AND excluida_em IS NULL', linha['pedida_por'], organizacao)
        alvo = tx.um('SELECT * FROM contas WHERE id = ? AND excluida_em IS NULL', linha['conta'])
        if not pediu or not alvo or not alvo['ativa']:
            raise ValueError(RECUPERACAO_INEXISTENTE)
        if por in (linha['pedida_por'], linha['conta']):
            raise ValueError('A confirmação precisa vir de outro dono: nem de quem pediu, nem da própria pessoa.')
        por_email = bool(com_envio and alvo['email'])
        if not por_email and not na_tela:
            raise SoPeloOperador(SO_PELO_OPERADOR)
        return linha, alvo, por_email
    with _bd(root) as tx:
        conferir(tx, agora())
    confirmar_senha(root, por, senha, ip)
    with _bd(root, escrever=True) as tx:
        momento = agora()
        linha, alvo, por_email = conferir(tx, momento)
        tx.ex("UPDATE recuperacoes SET estado = 'confirmada', confirmada_por = ?, encerrada_em = ? WHERE id = ?",
              por, _iso(momento), linha['id'])
        _evento(tx, 'recuperacao_confirmada', alvo['id'], por, momento)
        return {'estado': 'enviada' if por_email else 'confirmada', 'token': _link_de_recuperacao(tx, alvo, momento),
                'destinatario': _destinatario(alvo), 'por_email': por_email}


# --- the own e-mail (conta-email-trocar, email-confirmar) -----------------------------------------

LINK_DE_EMAIL_INVALIDO = 'Link inválido, usado ou vencido. Peça outro em Minha conta.'


def pedir_troca_de_email(root: Path, cid, email, senha=None, ip: str | None = None) -> dict:
    """The person asks to change the own e-mail (or to give one, for an account that came without): asks the
    password, and the change only happens when the link sent to the NEW address is used.

    An address that another account already has, of any newsroom, gets the same answer as a free one: the request
    is kept, without effect, and `enviar` tells the caller to send nothing to it. Returns
    `{token, novo, idioma, enviar, antigo}`; `antigo` is the current address, to be told of the request."""
    novo = _validar_email(email)
    confirmar_senha(root, cid, senha, ip)
    token = secrets.token_urlsafe(32)
    with _bd(root, escrever=True) as tx:
        conta = _conta(tx, cid)
        momento = agora()
        if conta['email'] == novo:
            raise ValueError('Esse já é o e-mail da conta.')
        if tx.um("SELECT 1 FROM links WHERE conta = ? AND tipo = 'email' AND criado_em > ?", cid,
                 _iso(momento - timedelta(minutes=REDEFINICAO_INTERVALO_MINUTOS))):
            raise ValueError('Você pediu essa troca há pouco. Espere alguns minutos para pedir de novo.')
        em_uso = bool(tx.um('SELECT 1 FROM contas WHERE email = ?', novo))
        tx.ex("DELETE FROM links WHERE conta = ? AND tipo = 'email'", cid)
        tx.ex("INSERT INTO links (token_sha256, tipo, conta, criado_em, expira_em, dado) VALUES (?, 'email', ?, ?, ?, ?)",
              _hash(token), cid, _iso(momento), _iso(momento + timedelta(minutes=REDEFINICAO_MINUTOS)), novo)
        _evento(tx, 'email_troca_pedida', cid, cid, momento, **({'motivo': 'email_em_uso'} if em_uso else {}))
        return {'token': token, 'novo': novo, 'idioma': conta['idioma'] or IDIOMAS[0], 'enviar': not em_uso,
                'antigo': conta['email'], 'conta': cid}


def confirmar_email(root: Path, token) -> dict:
    """The link sent to the new address was opened: the account's e-mail changes, and with it the identifier of the
    sign-in. Every pending link of the account dies. A link of an address that got an account meanwhile changes
    nothing, with the refusal of any dead link."""
    try:
        with _bd(root, escrever=True) as tx:
            momento = agora()
            link, conta = _por_link(tx, token, ('email',), momento, LINK_DE_EMAIL_INVALIDO)
            if tx.um('SELECT 1 FROM contas WHERE email = ?', link['dado']):
                raise LinkInvalido('email_em_uso', LINK_DE_EMAIL_INVALIDO)
            antigo = conta['email']
            _limpar_tentativas(tx, conta)
            tx.ex('UPDATE contas SET email = ? WHERE id = ?', link['dado'], conta['id'])
            tx.ex('DELETE FROM links WHERE conta = ?', conta['id'])
            _evento(tx, 'email_trocado', conta['id'], conta['id'], momento, campos=['email'])
            return {'conta': conta['id'], 'novo': link['dado'], 'antigo': antigo, 'idioma': conta['idioma'] or IDIOMAS[0]}
    except LinkInvalido as exc:
        registro_acesso.registrar('ativacao_falha', 'falha', motivo=exc.motivo, acesso_operacao='confirmar_email')
        raise


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


def ativar(root: Path, token, senha, marca=None) -> dict:
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
        _limpar_tentativas(tx, conta)
        _so_este_aparelho(tx, cid, marca, momento)  # the browser that used the activation link, and no other
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


def _limpar_tentativas(tx: _Tx, conta) -> None:
    """Forget the sign-in counters of every identifier of the account (the old login and the e-mail)."""
    for login in (conta['login'], conta['email']):
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
    """Forget stale counters. An active block is never evicted, and neither is a counter before its time: the
    per-identifier ones (the fixed table of BALDES counters) live for their whole window; the ones of the second
    factor of an account live FATOR_CONTADOR_HORAS, so that a few wrong codes every quarter of an hour add up to a
    block and a notice instead of being forgotten each time; the others live BLOQUEIO_MINUTOS, and only the
    per-address counters of the sign-in, which an attacker can multiply, have a ceiling."""
    agora_ = _iso(momento)
    curto, longo = _iso(momento - timedelta(minutes=BLOQUEIO_MINUTOS)), _iso(momento - timedelta(minutes=PROTECAO_JANELA_MINUTOS))
    dia = _iso(momento - timedelta(hours=FATOR_CONTADOR_HORAS))
    ativo = '(bloqueado_ate IS NOT NULL AND bloqueado_ate > ?)'
    do_identificador = f"chave LIKE '{CHAVE_BALDE}%'"
    do_fator = f"(chave LIKE '{CHAVE_FATOR}%' OR chave LIKE '{CHAVE_RESERVA}%')"
    tx.ex(f"DELETE FROM tentativas WHERE NOT {ativo} AND coalesce(em, '') <= ? AND NOT {do_identificador} AND NOT {do_fator}",
          agora_, curto)
    tx.ex(f"DELETE FROM tentativas WHERE NOT {ativo} AND coalesce(em, '') <= ? AND {do_identificador}", agora_, longo)
    tx.ex(f"DELETE FROM tentativas WHERE NOT {ativo} AND coalesce(em, '') <= ? AND {do_fator}", agora_, dia)
    excesso = tx.um("SELECT COUNT(*) AS total FROM tentativas WHERE chave NOT LIKE '#%'")['total'] - MAX_TENTATIVAS_GUARDADAS
    if excesso > 0:
        tx.ex(f"DELETE FROM tentativas WHERE chave IN (SELECT chave FROM tentativas WHERE NOT {ativo}"
              " AND chave NOT LIKE '#%' ORDER BY coalesce(em, '') LIMIT ?)", agora_, excesso)


def _chave_do_identificador(tx: _Tx, login: str, criar: bool = False) -> str:
    """Where the failures of an identifier, from every address, are counted: one of BALDES counters, chosen by a
    keyed hash of the identifier. The same for an identifier with an account and for one without: every identifier
    always has a counter, the table never grows and there is no "full" state. Two identifiers may share a counter,
    and then share its protected mode. An exact counter for the ones with an account would tell them apart: its
    protected mode would never spread to a neighbour, and a few tens of thousands of requests would confirm that
    one person has an account (B1 of the review). What is counted on the account itself (the codes of the second
    factor, the password asked again) only starts after the right password, when its existence is no secret."""
    segredo = _meta(tx, 'chave_dos_baldes')
    if not segredo:
        if not criar:
            return CHAVE_BALDE + '-'  # no counter was ever made: nothing to find
        segredo = secrets.token_hex(32)
        _definir_meta(tx, 'chave_dos_baldes', segredo)
    resumo = hmac.new(bytes.fromhex(segredo), login.encode('utf-8'), hashlib.sha256).digest()
    return CHAVE_BALDE + str(int.from_bytes(resumo[:8], 'big') % BALDES)


def _falha_do_identificador(tx: _Tx, login: str, cid: str | None, momento: datetime) -> None:
    """Count a failure of the identifier, whatever the address: PROTECAO_FALHAS inside the window start the
    protected mode. While it lasts nothing counts and nothing extends it."""
    chave = _chave_do_identificador(tx, login, criar=True)
    linha = tx.um('SELECT falhas, bloqueado_ate, em FROM tentativas WHERE chave = ?', chave)
    falhas, ate, inicio = (linha['falhas'], linha['bloqueado_ate'], linha['em']) if linha else (0, None, None)
    if ate and _data(ate) > momento:
        return
    if ate or not inicio or _data(inicio) + timedelta(minutes=PROTECAO_JANELA_MINUTOS) <= momento:
        falhas, inicio = 0, _iso(momento)  # a new window (also after a protection ended)
    falhas, ate = falhas + 1, None
    if falhas >= PROTECAO_FALHAS:
        falhas, ate = 0, _iso(momento + timedelta(minutes=PROTECAO_MINUTOS))
        if cid:
            _evento(tx, 'login_protegido', cid, None, momento)
        else:
            tx.depois.append(lambda: registro_acesso.registrar('login_protegido', 'falha', None, momento, motivo='protegido',
                                                               login_ref=registro_acesso.referencia_do_login(login)))
    tx.ex('INSERT INTO tentativas (chave, falhas, bloqueado_ate, em) VALUES (?, ?, ?, ?) ON CONFLICT (chave) DO UPDATE'
          ' SET falhas = excluded.falhas, bloqueado_ate = excluded.bloqueado_ate, em = excluded.em', chave, falhas, ate, inicio)
    _podar_tentativas(tx, momento)


# --- known devices ------------------------------------------------------------------------------------

def _marca(marca) -> str | None:
    """The device mark of a browser as the store keeps it (its hash), or None when it cannot be one."""
    return _hash(marca) if isinstance(marca, str) and SID.fullmatch(marca) else None


def _marca_conhecida(tx: _Tx, cid: str, marca, momento: datetime) -> bool:
    """Whether the browser carries the mark of a device this account already used, and that mark is not blocked by
    its own wrong passwords. A known mark crosses the protected mode; it never switches the counting off."""
    resumo = _marca(marca)
    return bool(resumo and tx.um('SELECT 1 FROM aparelhos WHERE conta = ? AND resumo = ?', cid, resumo)
                and not _bloqueado(tx, f'{CHAVE_MARCA}{cid}|{resumo}', momento))


def _registrar_aparelho(tx: _Tx, cid: str, marca, momento: datetime) -> bool:
    """The browser becomes a known device of the account (only ever after something that proves who it is: a
    sign-in that worked, or a link only the person receives). Returns whether it is a NEW device of an account
    that already had another: that is what the person is told about."""
    resumo = _marca(marca)
    if not resumo:
        return False
    if tx.ex('UPDATE aparelhos SET ultimo_uso = ? WHERE conta = ? AND resumo = ?', _iso(momento), cid, resumo).rowcount:
        return False
    tinha = tx.um('SELECT COUNT(*) AS n FROM aparelhos WHERE conta = ?', cid)['n']
    tx.ex('INSERT INTO aparelhos (conta, resumo, criado_em, ultimo_uso) VALUES (?, ?, ?, ?)', cid, resumo, _iso(momento), _iso(momento))
    for antigo in tx.todos('SELECT resumo FROM aparelhos WHERE conta = ? ORDER BY ultimo_uso DESC, rowid DESC LIMIT -1 OFFSET ?',
                           cid, APARELHOS_MAX):
        tx.ex('DELETE FROM aparelhos WHERE conta = ? AND resumo = ?', cid, antigo['resumo'])
    if tinha:
        _evento(tx, 'aparelho_novo', cid, cid, momento)
    return bool(tinha)


def _so_este_aparelho(tx: _Tx, cid: str, marca, momento: datetime) -> None:
    """The password was changed or reset: every known device of the account is forgotten but the browser that did
    it. If the account had been broken into, the intruder's browser became a known device when it signed in, and
    must not go on being one."""
    tx.ex('DELETE FROM aparelhos WHERE conta = ?', cid)
    tx.ex("DELETE FROM tentativas WHERE substr(chave, 1, ?) = ?", len(CHAVE_MARCA) + len(cid) + 1, f'{CHAVE_MARCA}{cid}|')
    resumo = _marca(marca)
    if resumo:
        tx.ex('INSERT INTO aparelhos (conta, resumo, criado_em, ultimo_uso) VALUES (?, ?, ?, ?)', cid, resumo, _iso(momento), _iso(momento))


def _sessao_aberta(tx: _Tx, conta, momento: datetime, cliente, aparelho, ip: str | None, marca) -> tuple[str, str, dict]:
    """Open the session of a sign-in that worked and make the browser a known device: what `entrar` returns, plus
    `aparelho_novo` in the account (for the caller to tell the person; it never goes to the browser)."""
    sid, csrf = _abrir_sessao(tx, conta['id'], momento, cliente, aparelho, ip)
    novo = _registrar_aparelho(tx, conta['id'], marca, momento)
    return sid, csrf, {**_publico(tx, tx.um('SELECT * FROM contas WHERE id = ?', conta['id']), momento), 'aparelho_novo': novo}


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


def _abrir_sessao(tx: _Tx, cid: str, momento: datetime, cliente, aparelho, ip: str | None) -> tuple[str, str]:
    """A new session of the account: (session id, csrf token). Only the hash of the id is kept."""
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    _limpar_sessoes(tx, momento)
    tx.ex('INSERT INTO sessoes (id_sha256, publico, conta, csrf, criada_em, expira_em, ultimo_uso, cliente,'
          ' aparelho, ip_criacao, ip_ultimo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
          _hash(sid), secrets.token_hex(8), cid, csrf, _iso(momento),
          _iso(momento + timedelta(hours=SESSAO_HORAS)), _iso(momento), _cliente(cliente),
          _aparelho(aparelho), _ip_valido(ip), _ip_valido(ip))
    tx.depois.append(lambda: registro_acesso.registrar('login_ok', 'ok', cid, momento, cliente=_cliente(cliente), ip=ip))
    return sid, csrf


def entrar(root: Path, login, senha, ip: str | None = None, cliente='web', aparelho=None, marca=None) -> tuple[str, str, dict]:
    """Return (session id, csrf token, public account). One generic refusal for every bad credential.
    Every outcome goes to the audit log: success, wrong credentials, lockout and per-address limit (never the text typed).
    `aparelho` and `ip` are kept with the session, for the person's own list of sessions.

    Two ceilings, both counted by the identifier typed, whether an account has it or not (contract, 8.2): five
    failures of an identifier from one address block that pair for 15 minutes; ten failures of an identifier in an
    hour, from any addresses, put it in protected mode for an hour, when every attempt gets the same refusal, right
    password or wrong, with no hash computed for anybody. The only attempt that crosses the protected mode carries
    `marca`, the mark of a device this account already used (cookie `vlado_aparelho`); it is still counted, on a
    counter of that mark. A sign-in that works makes `marca` a known device."""
    momento = agora()
    try:
        _limite_ip(ip, momento)
    except Bloqueado:
        registro_acesso.registrar_limite_ip('login_falha', ip, _rede(ip), cliente=_cliente(cliente))
        raise
    login = login.strip().lower() if isinstance(login, str) else ''
    senha = senha if isinstance(senha, str) and len(senha) <= SENHA_MAX else ''
    # The identifier typed is the e-mail (accounts born of an invitation) or the old login; counters, blocks and
    # answers are the same whether an account has it or not. One out of both formats makes no counter.
    por_email = '@' in login
    valido = bool(len(login) <= 254 and EMAIL.fullmatch(login)) if por_email else bool(LOGIN.fullmatch(login))
    chave = _chave_tentativa(login, ip)
    with _bd(root) as tx:
        conta = (tx.um(f'SELECT id, ativa, senha_hash FROM contas WHERE {"email" if por_email else "login"} = ?', login)
                 if valido else None)
        cid = conta['id'] if conta else None
        conhecida = bool(cid and _marca_conhecida(tx, cid, marca, momento))
        protegido = valido and not conhecida and _bloqueado(tx, _chave_do_identificador(tx, login), momento)
        bloqueado = valido and _bloqueado(tx, chave, momento)
        guardado = conta['senha_hash'] if conta and conta['ativa'] else None
    if bloqueado or protegido:
        # Refused before any hash, for an account and for none alike: neither the answer nor its time tells.
        # An attempt made during the protected mode does not count and does not extend it.
        _auditar_falha('bloqueado' if bloqueado else 'protegido', cid, login, cliente, ip)
        raise Bloqueado(BLOQUEADO)
    # The hash is checked even for unknown logins (similar timing), outside the store's transaction.
    try:
        with _VezDoHash():
            certo = _HASHER.verify(guardado or _hash_ficticio(), senha) and bool(guardado) and bool(senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        certo = False
    momento = agora()
    aberta, bloqueou, existe, bilhete = None, False, False, None
    with _bd(root, escrever=True) as tx:
        conta = tx.um('SELECT * FROM contas WHERE id = ?', cid) if cid else None
        existe = bool(conta)
        if certo and conta and conta['ativa'] and conta['senha_hash'] == guardado:
            if _bloqueado(tx, chave, momento):
                bloqueado = True
            else:
                if _HASHER.check_needs_rehash(guardado):
                    tx.ex('UPDATE contas SET senha_hash = ? WHERE id = ?', _HASHER.hash(senha), cid)
                if tx.um('SELECT 1 FROM fatores WHERE conta = ? AND ativo = 1', cid):
                    # The password alone opens nothing: a ticket for the second step, and the counters stay as
                    # they are until the code is right (wrong codes count on the same ceilings).
                    bilhete = secrets.token_urlsafe(32)
                    tx.ex('DELETE FROM entradas WHERE conta = ? OR expira_em <= ?', cid, _iso(momento))
                    tx.ex('INSERT INTO entradas (id_sha256, conta, chave, criada_em, expira_em, cliente, aparelho)'
                          ' VALUES (?, ?, ?, ?, ?, ?, ?)', _hash(bilhete), cid, chave, _iso(momento),
                          _iso(momento + timedelta(minutes=ENTRADA_MINUTOS)), _cliente(cliente), _aparelho(aparelho))
                else:
                    # The per-address counter is cleared; the per-identifier one runs out by itself, so a sign-in of
                    # the owner never gives an attacker a fresh allowance.
                    tx.ex('DELETE FROM tentativas WHERE chave = ?', chave)
                    aberta = _sessao_aberta(tx, conta, momento, cliente, aparelho, ip, marca)
        elif valido:
            bloqueou = _registrar_falha(tx, chave, cid if conta else None, momento)
            _falha_do_identificador(tx, login, cid if conta else None, momento)
            if conhecida:
                _registrar_falha(tx, f'{CHAVE_MARCA}{cid}|{_marca(marca)}', None, momento)
    if aberta:
        return aberta
    if bilhete:
        raise PedeSegundoFator(bilhete)
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


def sessao(root: Path, sid, ip: str | None = None, obrigar_fator: bool = False, termos: str | None = None) -> dict | None:
    """The calling account, re-read on every request (deactivation, role, participations and quota apply at once).
    `ip` is kept as the session's last address, at most once a minute, with its last use.

    `casos` is always the explicit reach (for a dono, every case of the own newsroom) and `responsavel_de` the cases
    the account answers for: outside the local mode no caller ever has "every case".

    `obrigar_fator` is the hosted mode: a dono or an editor without an active second factor carries the pending
    item `segundo_fator`, and the gate lets the session reach only what resolves it (contract, 4.2 and 8.2).
    `termos` is the version of the terms in force in the hosted mode: an account whose last acceptance is another
    one carries `termos`, which comes first (contract, 8.4)."""
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
            ultimo = _ultimo_aceite(tx, conta['id']) if termos else None
            pendencias = ['termos'] if termos and (not ultimo or ultimo['versao'] != termos) else []
            pendencias += (['segundo_fator'] if obrigar_fator and conta['papel'] in FATOR_OBRIGATORIO
                           and not tx.um('SELECT 1 FROM fatores WHERE conta = ? AND ativo = 1', conta['id']) else [])
            tocar = (momento - _data(registro['ultimo_uso'])).total_seconds() >= ULTIMO_USO_SEGUNDOS
            principal = {'conta': conta['id'], 'nome': conta['nome'], 'login': conta['login'], 'email': conta['email'],
                         'papel': conta['papel'],
                         'organizacao': {'id': conta['organizacao'], 'nome': conta['redacao_nome'],
                                         'situacao': conta['redacao_situacao']},
                         'casos': casos, 'responsavel_de': responsavel, 'pendencias': pendencias,
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


def ver_conta(root: Path, cid, termos: dict | None = None) -> dict:
    """The own profile: name, e-mail, login, role, language, newsroom, when the password was set, the second factor,
    the last acceptance of the terms (`termos`) and, where the service has them, the terms in force
    (`termos_vigente`)."""
    with _bd(root) as tx:
        conta = _conta(tx, cid)
        redacao = tx.um('SELECT id, nome FROM organizacoes WHERE id = ?', conta['organizacao'])
        return {'conta': {'id': conta['id'], 'nome': conta['nome'], 'email': conta['email'], 'login': conta['login'],
                          'papel': conta['papel'], 'idioma': conta['idioma'] or IDIOMAS[0],
                          'senha_definida_em': conta['senha_definida_em'], 'criada_em': conta['criada_em']},
                'organizacao': dict(redacao), 'segundo_fator': _estado_do_fator(tx, cid),
                'termos': _dict_ou_none(_ultimo_aceite(tx, conta['id'])), 'termos_vigente': dict(termos) if termos else None}


def _dict_ou_none(linha):
    return dict(linha) if linha else None


# --- export of the own data (`conta-exportar`, contract of accounts, 8.4 and the delivery 4b-2) ---------------------

FORMATO_EXPORTACAO, VERSAO_EXPORTACAO = 'vlado-meus-dados', 1
# What the file does not carry yet, as fixed codes the page translates (ressalva E4): the list of what the person
# created, which lives in other modules' files, and the accesses in the audit log, which is the Platform's.
EXPORTACAO_INCOMPLETA = ('itens_criados', 'registro_de_acesso')
# Who did an event, when it was not an account: the fixed labels this module writes in `por`.
POR_SISTEMA = frozenset({'operador', 'manutencao', 'migracao', 'migracao_contas', 'primeiro_acesso', 'primeiro_admin'})


def _quem(tx: _Tx, valor, cid: str) -> str | None:
    """The other side of an event, as the export shows it (ressalva B1): the person, a fixed label of the system, or
    just "another account", never its id nor its name."""
    if valor is None:
        return None
    if valor == cid:
        return 'voce'
    if valor in POR_SISTEMA and not tx.um('SELECT 1 FROM contas WHERE id = ?', valor):
        return valor
    return 'outra_conta'


def exportar_conta(root: Path, cid) -> dict:
    """`conta-exportar`: what the store keeps about the person, for the person (contract, 8.4). Nothing of anybody
    else, and never a secret: no password hash, token, ticket, seed, reserve code, csrf, session id or cookie, device
    mark or its summary, nor AI key. The content of the cases is the newsroom's and leaves by their own export."""
    with _bd(root) as tx:
        conta = _conta(tx, cid)
        cid, momento = conta['id'], agora()
        redacao = tx.um('SELECT id, nome FROM organizacoes WHERE id = ?', conta['organizacao'])
        eventos = [{'em': e['em'], 'tipo': e['tipo'], 'conta': _quem(tx, e['conta'], cid), 'por': _quem(tx, e['por'], cid)}
                   for e in tx.todos('SELECT em, tipo, conta, por FROM eventos WHERE (conta = ? OR por = ?) AND em > ?'
                                     ' ORDER BY n', cid, cid, _iso(momento - timedelta(days=ATIVIDADE_DIAS)))]
        return {
            'formato': FORMATO_EXPORTACAO, 'versao': VERSAO_EXPORTACAO, 'gerado_em': _iso(momento),
            'conta': {'id': cid, 'nome': conta['nome'], 'email': conta['email'], 'login': conta['login'],
                      'papel': conta['papel'], 'idioma': conta['idioma'] or IDIOMAS[0], 'situacao': _situacao(conta),
                      'criada_em': conta['criada_em'], 'senha_definida_em': conta['senha_definida_em'],
                      'cota_diaria': conta['cota_diaria'], 'teto_mensal_brl': conta['teto_mensal_brl']},
            'redacao': dict(redacao),
            'segundo_fator': _estado_do_fator(tx, cid),
            'termos': [dict(t) for t in tx.todos('SELECT versao, aceito_em, ip FROM termos_aceites WHERE conta = ?'
                                                 ' ORDER BY aceito_em, rowid', cid)],
            'sessoes': [dict(s) for s in tx.todos(
                'SELECT criada_em, ultimo_uso, expira_em, cliente, aparelho, ip_criacao, ip_ultimo FROM sessoes'
                ' WHERE conta = ? AND expira_em > ? ORDER BY criada_em', cid, _iso(momento))],
            'aparelhos': [dict(a) for a in tx.todos('SELECT criado_em, ultimo_uso FROM aparelhos WHERE conta = ?'
                                                    ' ORDER BY criado_em', cid)],
            'participacoes': _participacoes(tx, cid),
            'eventos': eventos,
            'incompleto': list(EXPORTACAO_INCOMPLETA),
        }


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


def trocar_senha(root: Path, cid, senha_atual, senha_nova, sessao_atual=None, ip: str | None = None, marca=None) -> int:
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
        tx.ex('DELETE FROM links WHERE conta = ?', cid)  # a reset link asked before the change is dead
        _so_este_aparelho(tx, cid, marca, momento)  # every other known device is forgotten with the other sessions
        _limpar_tentativas(tx, conta)
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
    sub.add_parser('manutencao', help='Varredura diária: vence convites e poda a atividade antiga')
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
    elif args.comando == 'manutencao':
        _imprimir(manutencao(ROOT))
    else:
        _imprimir(atualizar(ROOT, args.id, por='cli', casos=_casos_cli(args.casos)))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(_principal())
    except ValueError as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        raise SystemExit(1)
