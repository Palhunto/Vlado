"""Regera deploy/requirements.lock (versões exatas com hashes) para a imagem Linux do Vlado (SEG-04).

Roda pip-compile dentro da mesma imagem-base do Dockerfile (a do digest), para que os marcadores de
plataforma e os hashes valham para Linux/CPython 3.12 mesmo quando o script é executado no Windows.
Precisa do Docker e de rede (PyPI). Não lê segredos nem dados de casos.

Uso:  python deploy/gerar_trava.py
"""
from pathlib import Path
import re
import subprocess
import sys

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "deploy" / "requirements.lock"
PIP_TOOLS = "pip-tools==7.4.1"
CABECALHO = (
    "# Trava das dependências Python da imagem (SEG-04): versões exatas e hashes SHA-256 de todas as\n"
    "# diretas e transitivas, para Linux/CPython 3.12. O Dockerfile instala com `pip --require-hashes`.\n"
    "# GERADO por `python deploy/gerar_trava.py` a partir de requirements.txt e requirements-opcional.txt;\n"
    "# não edite à mão. Para atualizar uma versão: mude o requirements.txt, rode o script e revise o diff.\n"
)


def imagem_base() -> str:
    """Primeira referência `FROM <imagem>@sha256:...` do Dockerfile."""
    texto = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    achado = re.search(r"^FROM\s+(\S+@sha256:[0-9a-f]{64})", texto, flags=re.MULTILINE)
    if not achado:
        sys.exit("Dockerfile sem FROM por digest: fixe a imagem-base antes de gerar a trava.")
    return achado.group(1)


def main() -> int:
    comando = [
        "docker", "run", "--rm", "-v", f"{RAIZ}:/w:ro", "-w", "/w", imagem_base(), "sh", "-c",
        f"pip install -q --no-cache-dir --root-user-action=ignore {PIP_TOOLS} && "
        "pip-compile -q --generate-hashes --allow-unsafe --strip-extras --no-header "
        "--output-file /tmp/trava.txt requirements.txt requirements-opcional.txt && cat /tmp/trava.txt",
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8")
    if resultado.returncode != 0:
        sys.stderr.write(resultado.stderr)
        return resultado.returncode
    SAIDA.write_text(CABECALHO + resultado.stdout.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    print(f"Trava gravada em {SAIDA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
