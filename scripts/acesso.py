"""Hosted access: individual accounts with passwords, activation links and server-side sessions.

Store `acesso/acesso.json` (gitignored) or the path in VLADO_ACESSO (e.g. a Docker volume),
`versao: 2`, written atomically under a cross-process lock. Passwords use argon2id
(argon2-cffi). Activation tokens and session ids are random (secrets.token_urlsafe) and only
their SHA-256 is stored. Events never carry passwords, tokens, links or hashes.

Every event here also goes to the audit log (scripts/registro_acesso.py: JSON lines with UTC time, account, IP and result,
rotated by day, 30 days by default). The 1000 newest events stay in `acesso.json` for the admin screen; an event pushed out
of that window is first copied to the audit log as `evento_arquivado`, never dropped silently.

A v1 store (invitations) migrates on first read: each invitation becomes an account with the
SAME id (authorship in notes, reviews and conversations is kept), without password; v1 sessions
are dropped and a copy of the v1 file is kept as acesso.v1.json.

CLI (run on the server; the activation link goes to this terminal's stdout only, or to
--saida ARQUIVO with permission 0600):
  python scripts/acesso.py criar-admin --nome "Editora" --login editora --origem https://vlado.example.org
  python scripts/acesso.py criar-conta --nome "Ana" --login ana.silva --casos caso_a,caso_b --cota 20 --origem ...
  python scripts/acesso.py listar
  python scripts/acesso.py desativar ID | reativar ID
  python scripts/acesso.py recuperar ID --origem https://vlado.example.org
  python scripts/acesso.py casos ID --casos caso_a,caso_b
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cadastrar_documentos import _atomico  # noqa: E402
from comum import trava_arquivo  # noqa: E402
import registro_acesso  # noqa: E402

PAPEIS = ('admin', 'convidado')
CLIENTES = ('web', 'android')
ID_CASO = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
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
CREDENCIAIS = 'Login ou senha incorretos.'
ATIVACAO_INVALIDA = 'Link de ativação inválido ou expirado. Peça um novo link à administração.'
BLOQUEADO = 'Muitas tentativas. Aguarde alguns minutos e tente de novo.'

_HASHER = PasswordHasher()  # library defaults (argon2id); check_needs_rehash follows them
_TRAVA = threading.RLock()
_FICTICIO: dict[int, str] = {}
_IPS: dict[str, deque] = {}
_IPS_TRAVA = threading.Lock()
HASH_ESPERA_S = 10
_HASH_SEMAFORO = threading.BoundedSemaphore(4)  # argon2 uses ~64 MiB per hash: bound concurrent work
SID = re.compile(r'[A-Za-z0-9_-]{43}')  # secrets.token_urlsafe(32)


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


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(momento: datetime) -> str:
    return momento.strftime('%Y-%m-%dT%H:%M:%SZ')


def _data(texto: str) -> datetime:
    return datetime.strptime(texto, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode('utf-8')).hexdigest()


def caminho(root: Path) -> Path:
    destino = os.environ.get('VLADO_ACESSO', '').strip()
    return Path(destino) if destino else Path(root) / 'acesso' / 'acesso.json'


def limpar_limites() -> None:
    """Forget per-address attempt counters (memory only; used by tests and restarts)."""
    with _IPS_TRAVA:
        _IPS.clear()


# --- storage -------------------------------------------------------------------------------

def _vazio() -> dict:
    return {'versao': 2, 'contas': {}, 'sessoes': {}, 'tentativas': {}, 'uso': {}, 'eventos': []}


def _ilegivel() -> ValueError:
    return RegistroIlegivel('Registro de acesso ilegível; restaure o backup de acesso/.')


def _ler(root: Path) -> dict:
    """Read (and migrate a v1 store once). Callers hold _TRAVA and the file lock."""
    registro_acesso.lembrar_raiz(root)  # the audit log follows the data root unless VLADO_REGISTRO says otherwise
    arquivo = caminho(root)
    if not arquivo.is_file():
        return _vazio()
    try:
        bruto = arquivo.read_text(encoding='utf-8')
        dados = json.loads(bruto)
    except (OSError, ValueError) as exc:
        raise _ilegivel() from exc
    if not isinstance(dados, dict):
        raise _ilegivel()
    if dados.get('versao') != 2:
        # Only a real v1 store migrates; anything else is refused instead of being overwritten.
        if dados.get('versao') not in (None, 1) or not isinstance(dados.get('convites'), dict):
            raise _ilegivel()
        dados = _migrar(root, arquivo, bruto, dados)
    for chave, tipo in (('contas', dict), ('sessoes', dict), ('tentativas', dict), ('uso', dict), ('eventos', list)):
        dados.setdefault(chave, tipo())
        if not isinstance(dados[chave], tipo):
            raise _ilegivel()
    return dados


def _gravar(root: Path, dados: dict) -> None:
    arquivo = caminho(root)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    if len(dados['eventos']) > MAX_EVENTOS:
        for antigo in dados['eventos'][:-MAX_EVENTOS]:  # leaving the window is not silent: it goes to the audit log
            if isinstance(antigo, dict):
                registro_acesso.arquivar_evento(antigo)
    dados['eventos'] = dados['eventos'][-MAX_EVENTOS:]
    _atomico(arquivo, (json.dumps(dados, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    try:
        os.chmod(arquivo, 0o600)
    except OSError:
        pass


def _evento(dados: dict, tipo: str, conta: str | None, por: str | None, momento: datetime | None = None,
            **detalhes) -> None:
    """Audit trail: type, account, author and time only (never secrets). The audit log adds the client IP and
    the few allowed details (`detalhes`: changed fields, role)."""
    dados['eventos'].append({'em': _iso(momento or agora()), 'tipo': tipo, 'conta': conta, 'por': por})
    registro_acesso.do_acesso(tipo, conta, por, momento, **detalhes)


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


def _migrar(root: Path, arquivo: Path, bruto: str, v1: dict) -> dict:
    copia = arquivo.with_name('acesso.v1.json')
    if copia.exists():
        copia = arquivo.with_name(f'acesso.v1.{agora().strftime("%Y%m%dT%H%M%S%f")}.json')
    _atomico(copia, bruto.encode('utf-8'))
    try:
        os.chmod(copia, 0o600)
    except OSError:
        pass
    dados, usados, momento = _vazio(), set(), agora()
    convites = sorted((v1.get('convites') or {}).items(), key=lambda item: str(item[1].get('criado_em', '')))
    for cid, convite in convites:
        if not isinstance(convite, dict) or convite.get('papel') not in PAPEIS:
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
    _evento(dados, 'migracao_v1', None, 'migracao', momento)
    _gravar(root, dados)
    return dados


# --- validation and public view ---------------------------------------------------------------

def _validar_nome(nome) -> str:
    if not isinstance(nome, str) or not nome.strip() or len(nome) > 120:
        raise ValueError('Informe o nome da pessoa (até 120 caracteres).')
    return nome.strip()


def _validar_login(login) -> str:
    if not isinstance(login, str) or not LOGIN.fullmatch(login.strip().lower()):
        raise ValueError('Login inválido: use de 3 a 64 letras minúsculas, números, ponto, hífen ou sublinhado, '
                         'começando por letra ou número.')
    return login.strip().lower()


def _validar_casos(casos) -> list[str]:
    if (not isinstance(casos, (list, tuple)) or not casos or len(casos) > 50
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


def _situacao(conta: dict) -> str:
    if not conta.get('ativa'):
        return 'desativada'
    return 'ativa' if conta.get('senha_hash') else 'aguardando_senha'


def _publico(cid: str, conta: dict, momento: datetime | None = None) -> dict:
    ativacao = conta.get('ativacao') or {}
    expira = ativacao.get('expira_em')
    return {'id': cid, 'nome': conta['nome'], 'login': conta['login'], 'papel': conta['papel'],
            'casos': conta.get('casos'), 'cota_diaria': conta.get('cota_diaria'), 'ativa': bool(conta.get('ativa')),
            'situacao': _situacao(conta), 'criada_em': conta.get('criada_em'),
            'senha_definida_em': conta.get('senha_definida_em'), 'ativacao_expira_em': expira,
            'ativacao_vencida': bool(expira and _data(expira) <= (momento or agora())),
            'migrada_de_convite': bool(conta.get('migrada_de_convite'))}


def _conta(dados: dict, cid) -> dict:
    conta = dados['contas'].get(cid) if isinstance(cid, str) else None
    if not conta:
        raise ValueError('Conta não encontrada.')
    return conta


def _admins_ativos(dados: dict, exceto: str | None = None) -> int:
    return sum(1 for k, c in dados['contas'].items() if k != exceto and c['papel'] == 'admin' and c.get('ativa'))


def _derrubar_sessoes(dados: dict, cid: str) -> None:
    dados['sessoes'] = {k: s for k, s in dados['sessoes'].items() if s.get('conta') != cid}


def _emitir_ativacao(conta: dict, horas: int, motivo: str, momento: datetime) -> str:
    token = secrets.token_urlsafe(32)
    conta['ativacao'] = {'token_sha256': _hash(token), 'expira_em': _iso(momento + timedelta(hours=horas)),
                         'motivo': motivo}
    return token


# --- administration ---------------------------------------------------------------------------

def criar_conta(root: Path, nome, login, papel='convidado', casos=(), cota_diaria=20,
                horas=ATIVACAO_HORAS, por='cli') -> tuple[dict, str]:
    """Return (public record, activation token). The token is shown once and only its hash is kept."""
    nome, login = _validar_nome(nome), _validar_login(login)
    if papel not in PAPEIS:
        raise ValueError('Papel de acesso inválido.')
    if papel == 'convidado':
        casos, cota_diaria = _validar_casos(casos), _validar_cota(cota_diaria)
    horas = _validar_horas(horas)
    momento = agora()
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        if any(c['login'] == login for c in dados['contas'].values()):
            raise ValueError('Esse login já existe. Escolha outro.')
        cid = secrets.token_hex(8)
        while cid in dados['contas']:
            cid = secrets.token_hex(8)
        conta = {'nome': nome, 'login': login, 'papel': papel,
                 'casos': casos if papel == 'convidado' else None,
                 'cota_diaria': cota_diaria if papel == 'convidado' else None,
                 'ativa': True, 'senha_hash': None, 'senha_definida_em': None,
                 'criada_em': _iso(momento), 'criada_por': por}
        token = _emitir_ativacao(conta, horas, 'criacao', momento)
        dados['contas'][cid] = conta
        _evento(dados, 'conta_criada', cid, por, momento)
        _gravar(root, dados)
    return _publico(cid, conta, momento), token


def listar(root: Path) -> list[dict]:
    momento = agora()
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
    return [_publico(cid, c, momento) for cid, c in sorted(dados['contas'].items(),
                                                          key=lambda item: item[1].get('criada_em', ''))]


def eventos(root: Path, limite: int = 50) -> list[dict]:
    with _TRAVA, trava_arquivo(caminho(root)):
        return list(reversed(_ler(root)['eventos'][-limite:]))


def _alterar(root: Path, cid, por: str, mudar) -> dict:
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        conta = _conta(dados, cid)
        mudar(dados, conta)
        _gravar(root, dados)
        return _publico(cid, conta)


def desativar(root: Path, cid, por='cli') -> dict:
    def mudar(dados, conta):
        if conta['papel'] == 'admin' and conta.get('ativa') and not _admins_ativos(dados, exceto=cid):
            raise ValueError('Não é possível desativar o último administrador ativo.')
        conta['ativa'] = False
        conta.pop('ativacao', None)  # an old link must not come back to life after reactivation
        _derrubar_sessoes(dados, cid)
        _evento(dados, 'conta_desativada', cid, por)
    return _alterar(root, cid, por, mudar)


def reativar(root: Path, cid, por='cli') -> dict:
    def mudar(dados, conta):
        conta['ativa'] = True
        _limpar_tentativas(dados, conta['login'])
        _evento(dados, 'conta_reativada', cid, por)
    return _alterar(root, cid, por, mudar)


def atualizar(root: Path, cid, por='cli', *, nome=None, papel=None, casos=None, cota_diaria=None) -> dict:
    """Change name, role, released cases or daily quota. Takes effect on the account's next request."""
    if nome is not None:
        nome = _validar_nome(nome)
    if papel is not None and papel not in PAPEIS:
        raise ValueError('Papel de acesso inválido.')
    if casos is not None:
        casos = _validar_casos(casos)
    if cota_diaria is not None:
        cota_diaria = _validar_cota(cota_diaria)

    def mudar(dados, conta):
        novo_papel = papel or conta['papel']
        if (conta['papel'] == 'admin' and novo_papel != 'admin' and conta.get('ativa')
                and not _admins_ativos(dados, exceto=cid)):
            raise ValueError('Não é possível rebaixar o último administrador ativo.')
        antes = dict(conta)
        if nome is not None:
            conta['nome'] = nome
        if novo_papel == 'admin':
            conta.update(papel='admin', casos=None, cota_diaria=None)
        else:
            novos_casos = casos if casos is not None else conta.get('casos')
            nova_cota = cota_diaria if cota_diaria is not None else (conta.get('cota_diaria') or 20)
            conta.update(papel='convidado', casos=_validar_casos(novos_casos or []), cota_diaria=nova_cota)
        campos = [nome_campo for nome_campo, chave in (('nome', 'nome'), ('papel', 'papel'), ('casos', 'casos'),
                                                       ('cota', 'cota_diaria')) if antes.get(chave) != conta.get(chave)]
        _evento(dados, 'acesso_alterado', cid, por, campos=campos or None, papel=conta['papel'])
    return _alterar(root, cid, por, mudar)


def recuperar(root: Path, cid, por='cli', horas=ATIVACAO_HORAS) -> tuple[dict, str]:
    """Administrative recovery: end every session, clear the password and issue a new activation link."""
    horas = _validar_horas(horas)
    resultado = {}

    def mudar(dados, conta):
        momento = agora()
        _derrubar_sessoes(dados, cid)
        conta.update(senha_hash=None, senha_definida_em=None)
        resultado['token'] = _emitir_ativacao(conta, horas, 'recuperacao', momento)
        _limpar_tentativas(dados, conta['login'])
        _evento(dados, 'recuperacao_emitida', cid, por, momento)
    publico = _alterar(root, cid, por, mudar)
    return publico, resultado['token']


# --- first administrator (local mode with accounts) ----------------------------------------------

PRIMEIRO_ACESSO_ENCERRADO = 'A conta de administração já foi criada. Entre com login e senha.'


def primeiro_acesso_disponivel(root: Path) -> bool:
    """True only while the store has never held an account (deactivated ones still count)."""
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
    return not dados['contas'] and not dados.get('primeiro_admin_em')


def criar_primeiro_admin(root: Path, nome, login, senha) -> dict:
    """Create the first administrator with a password, once. The check and the write share the store lock,
    so two concurrent forms (threads or processes) end with exactly one account."""
    nome, login, senha = _validar_nome(nome), _validar_login(login), _validar_senha(senha)
    if not primeiro_acesso_disponivel(root):
        raise PrimeiroAcessoEncerrado(PRIMEIRO_ACESSO_ENCERRADO)
    with _VezDoHash():
        senha_hash = _HASHER.hash(senha)
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        if dados['contas'] or dados.get('primeiro_admin_em'):
            raise PrimeiroAcessoEncerrado(PRIMEIRO_ACESSO_ENCERRADO)
        momento = agora()
        cid = secrets.token_hex(8)
        conta = {'nome': nome, 'login': login, 'papel': 'admin', 'casos': None, 'cota_diaria': None,
                 'ativa': True, 'senha_hash': senha_hash, 'senha_definida_em': _iso(momento),
                 'criada_em': _iso(momento), 'criada_por': 'primeiro_acesso'}
        dados['contas'][cid] = conta
        dados['primeiro_admin_em'] = _iso(momento)
        _evento(dados, 'primeiro_admin', cid, 'primeiro_acesso', momento)
        _gravar(root, dados)
        return _publico(cid, conta, momento)


# --- activation -------------------------------------------------------------------------------

def _por_ativacao(dados: dict, token, momento: datetime) -> tuple[str, dict]:
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise AtivacaoInvalida(ATIVACAO_INVALIDA)
    digest = _hash(token)
    for cid, conta in dados['contas'].items():
        ativacao = conta.get('ativacao')
        if ativacao and secrets.compare_digest(ativacao.get('token_sha256', ''), digest):
            if not conta.get('ativa') or _data(ativacao['expira_em']) <= momento:
                break
            return cid, conta
    raise AtivacaoInvalida(ATIVACAO_INVALIDA)


def consultar_ativacao(root: Path, token) -> dict:
    """Login and name shown on the set-password form (read-only)."""
    with _TRAVA, trava_arquivo(caminho(root)):
        try:
            _, conta = _por_ativacao(_ler(root), token, agora())
        except AtivacaoInvalida:
            registro_acesso.registrar('ativacao_falha', 'falha', motivo='link_invalido', acesso_operacao='consultar')
            raise
        return {'login': conta['login'], 'nome': conta['nome']}


def ativar(root: Path, token, senha) -> dict:
    """Set the password from a single-use link. Does not open a session (the person signs in next)."""
    senha = _validar_senha(senha)
    with _TRAVA, trava_arquivo(caminho(root)):
        try:
            _por_ativacao(_ler(root), token, agora())  # refuse before spending time on the hash
        except AtivacaoInvalida:
            registro_acesso.registrar('ativacao_falha', 'falha', motivo='link_invalido', acesso_operacao='ativar')
            raise
    with _VezDoHash():
        senha_hash = _HASHER.hash(senha)
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        momento = agora()
        cid, conta = _por_ativacao(dados, token, momento)
        conta.update(senha_hash=senha_hash, senha_definida_em=_iso(momento))
        conta.pop('ativacao', None)
        _limpar_tentativas(dados, conta['login'])
        _evento(dados, 'senha_definida', cid, cid, momento)
        _gravar(root, dados)
        return _publico(cid, conta, momento)


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


def _limpar_tentativas(dados: dict, login: str) -> None:
    for chave in [k for k in dados['tentativas'] if k == login or k.startswith(login + '|')]:
        dados['tentativas'].pop(chave, None)


def _bloqueado(dados: dict, login: str, momento: datetime) -> bool:
    registro = dados['tentativas'].get(login)
    ate = registro.get('bloqueado_ate') if registro else None
    return bool(ate and _data(ate) > momento)


def _registrar_falha(dados: dict, login: str, cid: str | None, momento: datetime) -> bool:
    """Count a failure; return True when it starts a block."""
    registro = dados['tentativas'].get(login) or {'falhas': 0, 'bloqueado_ate': None}
    if registro.get('bloqueado_ate') and _data(registro['bloqueado_ate']) <= momento:
        registro = {'falhas': 0, 'bloqueado_ate': None}
    registro['falhas'] = registro.get('falhas', 0) + 1
    registro['em'] = _iso(momento)
    bloqueou = registro['falhas'] >= FALHAS_BLOQUEIO
    if bloqueou:
        registro.update(falhas=0, bloqueado_ate=_iso(momento + timedelta(minutes=BLOQUEIO_MINUTOS)))
    dados['tentativas'][login] = registro
    _podar_tentativas(dados, momento)
    if cid and bloqueou:
        # Only blocks are audited: single failures would push account events out of the 1000-event window.
        _evento(dados, 'login_bloqueado', cid, None, momento)
    return bloqueou


def _podar_tentativas(dados: dict, momento: datetime) -> None:
    """Forget stale counters; active blocks are never evicted."""
    limite = momento - timedelta(minutes=BLOQUEIO_MINUTOS)

    def ativo(registro):
        ate = registro.get('bloqueado_ate')
        return bool(ate and _data(ate) > momento)
    dados['tentativas'] = {k: r for k, r in dados['tentativas'].items()
                           if ativo(r) or _data(r.get('em', '1970-01-01T00:00:00Z')) > limite}
    excesso = len(dados['tentativas']) - MAX_TENTATIVAS_GUARDADAS
    if excesso > 0:
        livres = sorted((k for k, r in dados['tentativas'].items() if not ativo(r)),
                        key=lambda k: dados['tentativas'][k].get('em', ''))
        for chave in livres[:excesso]:
            dados['tentativas'].pop(chave, None)


def _motivo_vencida(registro: dict, momento: datetime) -> str:
    try:
        return 'expirada' if _data(registro['expira_em']) <= momento else 'inatividade'
    except (KeyError, TypeError, ValueError):
        return 'expirada'


def _limpar_sessoes(dados: dict, momento: datetime) -> None:
    """Drop expired sessions; each one is audited (`sessao_expirada`), so an expiry never goes unrecorded."""
    vencidas = {k: s for k, s in dados['sessoes'].items() if _sessao_vencida(s, momento)}
    for chave, registro in vencidas.items():
        dados['sessoes'].pop(chave, None)
        registro_acesso.registrar('sessao_expirada', 'ok', registro.get('conta'), momento,
                                  motivo=_motivo_vencida(registro, momento), cliente=registro.get('cliente'))


def _sessao_vencida(registro: dict, momento: datetime) -> bool:
    try:
        return (_data(registro['expira_em']) <= momento
                or _data(registro['ultimo_uso']) + timedelta(hours=INATIVIDADE_HORAS) <= momento)
    except (KeyError, TypeError, ValueError):
        return True


def entrar(root: Path, login, senha, ip: str | None = None, cliente='web') -> tuple[str, str, dict]:
    """Return (session id, csrf token, public account). One generic refusal for every bad credential.
    Every outcome goes to the audit log: success, wrong credentials, lockout and per-address limit (never the text typed)."""
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
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        cid, conta = next(((k, c) for k, c in dados['contas'].items() if c['login'] == login), (None, None))
        if valido and _bloqueado(dados, chave, momento):
            _auditar_falha('bloqueado', cid, login, cliente, ip)
            raise Bloqueado(BLOQUEADO)
        guardado = conta.get('senha_hash') if conta and conta.get('ativa') else None
    # The hash is checked even for unknown logins (similar timing), outside the store lock.
    try:
        with _VezDoHash():
            certo = _HASHER.verify(guardado or _hash_ficticio(), senha) and bool(guardado) and bool(senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        certo = False
    momento = agora()
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        conta = dados['contas'].get(cid) if cid else None
        if certo and conta and conta.get('ativa') and conta.get('senha_hash') == guardado:
            if _bloqueado(dados, chave, momento):
                _auditar_falha('bloqueado', cid, login, cliente, ip)
                raise Bloqueado(BLOQUEADO)
            if _HASHER.check_needs_rehash(guardado):
                conta['senha_hash'] = _HASHER.hash(senha)
            dados['tentativas'].pop(chave, None)
            sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            _limpar_sessoes(dados, momento)
            dados['sessoes'][_hash(sid)] = {
                'conta': cid, 'csrf': csrf, 'criada_em': _iso(momento),
                'expira_em': _iso(momento + timedelta(hours=SESSAO_HORAS)), 'ultimo_uso': _iso(momento),
                'cliente': _cliente(cliente)}
            _gravar(root, dados)
            registro_acesso.registrar('login_ok', 'ok', cid, momento, cliente=_cliente(cliente), ip=ip)
            return sid, csrf, _publico(cid, conta, momento)
        bloqueou = _registrar_falha(dados, chave, cid if conta else None, momento) if valido else False
        _gravar(root, dados)
    _auditar_falha('bloqueado' if bloqueou else 'credenciais', cid if conta else None, login, cliente, ip)
    raise (Bloqueado(BLOQUEADO) if bloqueou else CredenciaisInvalidas(CREDENCIAIS))


def _cliente(cliente) -> str:
    return cliente if cliente in CLIENTES else 'web'


def _auditar_falha(motivo: str, cid: str | None, login: str, cliente, ip: str | None) -> None:
    """A failed sign-in: the account id when it exists, otherwise a keyed reference of the typed login (never the
    text, which may be a password typed in the wrong field)."""
    registro_acesso.registrar('login_falha', 'falha', cid, motivo=motivo,
                              login_ref=None if cid else registro_acesso.referencia_do_login(login),
                              cliente=_cliente(cliente), ip=ip)


def sessao(root: Path, sid) -> dict | None:
    """The calling account, re-read on every request (deactivation, cases and quota apply at once)."""
    if not isinstance(sid, str) or not SID.fullmatch(sid):
        return None  # malformed ids never touch the store lock
    momento = agora()
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        chave = _hash(sid)
        registro = dados['sessoes'].get(chave)
        if registro and _sessao_vencida(registro, momento):
            _limpar_sessoes(dados, momento)  # audited once (`sessao_expirada`) and forgotten: no event per later request
            _gravar(root, dados)
            return None
        if not registro:
            return None
        conta = dados['contas'].get(registro.get('conta'))
        if not conta or not conta.get('ativa') or not conta.get('senha_hash'):
            return None
        if (momento - _data(registro['ultimo_uso'])).total_seconds() >= ULTIMO_USO_SEGUNDOS:
            registro['ultimo_uso'] = _iso(momento)
            _limpar_sessoes(dados, momento)
            _gravar(root, dados)
        return {'conta': registro['conta'], 'nome': conta['nome'], 'login': conta['login'], 'papel': conta['papel'],
                'casos': conta.get('casos'), 'cota_diaria': conta.get('cota_diaria'), 'csrf': registro['csrf'],
                'expira_em': registro['expira_em'], 'cliente': registro.get('cliente', 'web')}


def encerrar(root: Path, sid) -> None:
    if not isinstance(sid, str):
        return
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        registro = dados['sessoes'].pop(_hash(sid), None)
        if registro is not None:
            _evento(dados, 'sessao_encerrada', registro.get('conta'), registro.get('conta'))
            _gravar(root, dados)


# --- daily quota ------------------------------------------------------------------------------

def registrar_consulta(root: Path, cid: str) -> int:
    """Count one question for today (UTC). Guests over their daily quota are refused."""
    dia = agora().strftime('%Y-%m-%d')
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        conta = dados['contas'].get(cid) if isinstance(cid, str) else None
        if not conta or not conta.get('ativa'):
            raise ValueError('Conta indisponível. Entre novamente.')
        feitas = dados['uso'].get(cid, {}).get(dia, 0)
        if conta.get('cota_diaria') is not None and feitas >= conta['cota_diaria']:
            raise ValueError(f'Limite diário de {conta["cota_diaria"]} pergunta(s) atingido. Tente novamente amanhã.')
        dados['uso'][cid] = {dia: feitas + 1}  # keep only today
        _gravar(root, dados)
        return feitas + 1


def devolver_consulta(root: Path, cid: str) -> None:
    """Give back today's question when the server refused it after counting."""
    dia = agora().strftime('%Y-%m-%d')
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        feitas = dados['uso'].get(cid, {}).get(dia, 0)
        if feitas > 0:
            dados['uso'][cid] = {dia: feitas - 1}
            _gravar(root, dados)


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
        if nome == 'criar-conta':
            cria.add_argument('--casos', required=True, help='IDs separados por vírgula')
            cria.add_argument('--cota', type=int, default=20)
    sub.add_parser('listar')
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
    args = parser.parse_args()
    if args.comando in ('criar-admin', 'criar-conta', 'recuperar'):
        if args.comando == 'criar-admin':
            registro, token = criar_conta(ROOT, args.nome, args.login, papel='admin', horas=args.horas)
        elif args.comando == 'criar-conta':
            registro, token = criar_conta(ROOT, args.nome, args.login, casos=_casos_cli(args.casos),
                                          cota_diaria=args.cota, horas=args.horas)
        else:
            registro, token = recuperar(ROOT, args.id, por='cli', horas=args.horas)
        print(json.dumps(registro, ensure_ascii=False, indent=2))
        _entregar_link(_link(args.origem, token), args.saida)
    elif args.comando == 'listar':
        print(json.dumps(listar(ROOT), ensure_ascii=False, indent=2))
    elif args.comando == 'desativar':
        print(json.dumps(desativar(ROOT, args.id, por='cli'), ensure_ascii=False, indent=2))
    elif args.comando == 'reativar':
        print(json.dumps(reativar(ROOT, args.id, por='cli'), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(atualizar(ROOT, args.id, por='cli', casos=_casos_cli(args.casos)), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(_principal())
    except ValueError as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        raise SystemExit(1)
