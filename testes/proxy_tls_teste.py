"""Test-only HTTPS front for the hosted Mesa (piloto mode needs an https:// origin).

Generates a throw-away self-signed certificate for localhost in a temporary folder and
pipes TLS connections to the plain HTTP server. Never use outside homologation tests:
the browser client must explicitly accept this certificate (Playwright ignoreHTTPSErrors).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ipaddress
from pathlib import Path
import socket
import ssl
import threading


def certificado(pasta: Path) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    chave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    agora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(agora - timedelta(minutes=5))
            .not_valid_after(agora + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),
                                                        x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
            .sign(chave, hashes.SHA256()))
    crt, key = pasta / 'teste.crt', pasta / 'teste.key'
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
    return crt, key


class ProxyTLS:
    def __init__(self, pasta: Path, destino_porta: int, porta: int = 0):
        crt, key = certificado(pasta)
        self.contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.contexto.load_cert_chain(crt, key)
        self.destino = ('127.0.0.1', destino_porta)
        self.socket = socket.create_server(('127.0.0.1', porta), backlog=64)
        self.porta = self.socket.getsockname()[1]
        self.ativo = True
        threading.Thread(target=self._aceitar, daemon=True).start()

    @property
    def origem(self) -> str:
        return f'https://localhost:{self.porta}'

    def _aceitar(self) -> None:
        while self.ativo:
            try:
                cliente, _ = self.socket.accept()
            except OSError:
                return
            threading.Thread(target=self._atender, args=(cliente,), daemon=True).start()

    def _atender(self, cliente: socket.socket) -> None:
        try:
            seguro = self.contexto.wrap_socket(cliente, server_side=True)
            servidor = socket.create_connection(self.destino)
        except (OSError, ssl.SSLError):
            cliente.close()
            return

        def copiar(origem, destino):
            try:
                while dados := origem.recv(65536):
                    destino.sendall(dados)
            except (OSError, ssl.SSLError):
                pass
            finally:
                for lado in (origem, destino):
                    try:
                        lado.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        threading.Thread(target=copiar, args=(servidor, seguro), daemon=True).start()
        copiar(seguro, servidor)
        seguro.close()
        servidor.close()

    def fechar(self) -> None:
        self.ativo = False
        self.socket.close()
