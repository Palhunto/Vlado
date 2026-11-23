"""Segundo fator das contas da Mesa (contrato de contas, seções 7 e 8.2): TOTP, códigos de reserva e a semente cifrada.

Só as contas de aritmética e de cifra ficam aqui; quem guarda, conta tentativas e decide quem é obrigado é
``acesso.py``. Sem rede e sem relógio próprio: o momento vem de quem chama.

- **TOTP** (RFC 6238): HMAC-SHA1, 6 dígitos, passo de 30 segundos, um passo de tolerância para cada lado.
  ``conferir`` devolve o passo aceito, e quem chama o guarda: um passo já aceito, ou anterior a ele, não vale de
  novo, de modo que o mesmo código não serve duas vezes.
- **Códigos de reserva:** dez, de uso único, com 80 bits cada, mostrados uma vez. O armazenamento guarda só o
  SHA-256 de cada um. Com 80 bits ao acaso, percorrê-los a partir de uma cópia do banco não é viável, e a
  conferência não depende de chave nenhuma: a das sementes pode faltar depois de uma restauração, e é aí que o
  código de reserva mais importa.
- **A semente é cifrada** (AES-GCM, biblioteca ``cryptography``) com uma chave de 32 bytes em
  ``segredos/contas.chave``, fora da pasta das contas e fora do backup comum: quem copiar só o banco não gera
  códigos. O id da conta entra como dado autenticado, então a semente de uma conta não decifra na linha de outra.
"""
from __future__ import annotations

import base64
from datetime import datetime
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import struct
import threading
from urllib.parse import quote

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import segredos

DIGITOS = 6
PASSO_S = 30
TOLERANCIA = 1  # steps accepted before and after the current one (clocks of phones drift)
BYTES_DA_SEMENTE = 20  # 160 bits, the size RFC 4226 recommends for HMAC-SHA1
CODIGOS_DE_RESERVA = 10
EMISSOR = 'Vlado'
_CODIGO = re.compile(r'[0-9]{6}')  # ASCII digits only: `\d` would let other scripts' digits through
_ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # 32 symbols, without the ones people mix up (0/O, 1/I)
GRUPOS_DA_RESERVA, LETRAS_POR_GRUPO = 4, 4  # 16 symbols of 5 bits: 80 bits
_RESERVA = re.compile(r'[A-HJ-NP-Z2-9]{%d}' % (GRUPOS_DA_RESERVA * LETRAS_POR_GRUPO))
_TRAVA = threading.Lock()
_CHAVES: dict[str, bytes] = {}


class ChaveIlegivel(OSError):
    """The key of the seeds cannot be read or made: nobody enrols or passes a second factor until it can."""


class SementeIlegivel(ValueError):
    """A stored seed does not open with the key in use (another key, another account's row, or damage)."""


# --- TOTP ---------------------------------------------------------------------------------------

def nova_semente() -> bytes:
    return secrets.token_bytes(BYTES_DA_SEMENTE)


def em_base32(semente: bytes) -> str:
    """The seed as authenticator apps take it by hand: base32 without padding."""
    return base64.b32encode(semente).decode('ascii').rstrip('=')


def passo_de(momento: datetime) -> int:
    return int(momento.timestamp()) // PASSO_S


def codigo_do_passo(semente: bytes, passo: int) -> str:
    resumo = hmac.new(semente, struct.pack('>Q', passo), hashlib.sha1).digest()
    inicio = resumo[-1] & 0x0F
    valor = struct.unpack('>I', resumo[inicio:inicio + 4])[0] & 0x7FFFFFFF
    return str(valor % 10 ** DIGITOS).zfill(DIGITOS)


def conferir(semente: bytes, codigo, momento: datetime, ultimo_passo: int | None = None) -> int | None:
    """The step the code belongs to, or None. Only steps after `ultimo_passo` (the last one this account used) are
    accepted. Every candidate step is compared, in constant time, whether an earlier one matched or not."""
    texto = ''.join(codigo.split()) if isinstance(codigo, str) else ''
    if not _CODIGO.fullmatch(texto):
        return None
    atual, aceito = passo_de(momento), None
    for passo in range(atual - TOLERANCIA, atual + TOLERANCIA + 1):
        igual = hmac.compare_digest(codigo_do_passo(semente, passo), texto)
        if igual and aceito is None and (ultimo_passo is None or passo > ultimo_passo):
            aceito = passo
    return aceito


def endereco(semente: bytes, rotulo: str) -> str:
    """The `otpauth://` address the page turns into a QR code (drawn in the browser, with nothing loaded from
    outside). `rotulo` is the e-mail or the login of the account."""
    nome = quote(f'{EMISSOR}:{rotulo}', safe='')
    return (f'otpauth://totp/{nome}?secret={em_base32(semente)}&issuer={quote(EMISSOR)}'
            f'&algorithm=SHA1&digits={DIGITOS}&period={PASSO_S}')


# --- reserve codes --------------------------------------------------------------------------------

def novos_codigos_de_reserva() -> list[str]:
    """Ten single-use codes, shown once: 'ABCD-EFGH-JKLM-NPQR' (80 bits each)."""
    return ['-'.join(''.join(secrets.choice(_ALFABETO) for _ in range(LETRAS_POR_GRUPO)) for _ in range(GRUPOS_DA_RESERVA))
            for _ in range(CODIGOS_DE_RESERVA)]


def normalizar_reserva(codigo) -> str | None:
    """A reserve code as typed (spaces, hyphens, lower case) in its canonical form, or None if it cannot be one."""
    texto = re.sub(r'[\s-]', '', codigo).upper() if isinstance(codigo, str) and len(codigo) <= 40 else ''
    return texto if _RESERVA.fullmatch(texto) else None


def resumo_da_reserva(codigo) -> str | None:
    """What the store keeps of a reserve code: its SHA-256. No key: the code has 80 random bits, out of reach of a
    search over a copy of the store, and checking it must not depend on a key file that may be missing."""
    texto = normalizar_reserva(codigo)
    return hashlib.sha256(('reserva:' + texto).encode('ascii')).hexdigest() if texto else None


# --- the key and the encrypted seed ---------------------------------------------------------------

def arquivo_da_chave(root: Path) -> Path:
    """Next to the API keys, never in the accounts folder: `segredos/contas.chave`."""
    return segredos.caminho(Path(root)).parent / 'contas.chave'


def _chave(root: Path) -> bytes:
    arquivo = arquivo_da_chave(root)
    with _TRAVA:
        guardada = _CHAVES.get(str(arquivo))
        if guardada and arquivo.is_file():
            return guardada
        try:
            if arquivo.is_file():
                texto = arquivo.read_text(encoding='ascii').strip()
                chave = bytes.fromhex(texto) if len(texto) == 64 else b''
                if len(chave) != 32:  # never replaced silently: the seeds already stored would be lost with it
                    raise ChaveIlegivel('A chave do segundo fator está ilegível; restaure segredos/contas.chave.')
            else:
                chave = secrets.token_bytes(32)
                arquivo.parent.mkdir(parents=True, exist_ok=True)
                descritor = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
                with os.fdopen(descritor, 'w', encoding='ascii') as saida:
                    saida.write(chave.hex() + '\n')
        except ChaveIlegivel:
            raise
        except (OSError, ValueError) as exc:
            raise ChaveIlegivel('A chave do segundo fator não pôde ser lida nem criada.') from exc
        _CHAVES[str(arquivo)] = chave
        return chave


def cifrar(root: Path, semente: bytes, conta: str) -> str:
    """The seed as the store keeps it: base64 of nonce + AES-GCM(seed), bound to the account's id."""
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + AESGCM(_chave(root)).encrypt(nonce, semente, conta.encode('ascii'))).decode('ascii')


def decifrar(root: Path, guardada, conta: str) -> bytes:
    try:
        bruto = base64.b64decode(guardada, validate=True)
        return AESGCM(_chave(root)).decrypt(bruto[:12], bruto[12:], conta.encode('ascii'))
    except (InvalidTag, ValueError, TypeError) as exc:
        raise SementeIlegivel('A semente do segundo fator não pôde ser lida.') from exc
