# VLADO — hosted pilot image (modo piloto, behind an HTTPS reverse proxy).
# Base fixada por digest (SEG-04): o build de hoje e o de daqui a seis meses partem da mesma imagem.
# Etiqueta de origem: python:3.12-slim-bookworm (Debian 12, índice multi-arquitetura; digest lido em
# 21/11/2026). Para atualizar: `docker buildx imagetools inspect python:3.12-slim-bookworm`, troque o
# digest abaixo, rode `python deploy/gerar_trava.py` (usa esta mesma imagem) e reconstrua.
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Local OCR for scanned PDFs (OCRmyPDF engine + direct Tesseract fallback). Nothing leaves the container.
# Bookworm versions observed in a build on 13/11/2026 (not pinned in apt, so security updates keep
# applying): tesseract-ocr 5.3.0 (+ -por, -eng, -osd), ghostscript 10.00.0, pngquant 2.17.0,
# unpaper 7.0.0. OCRmyPDF itself is pinned in deploy/requirements.lock.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr tesseract-ocr-por tesseract-ocr-eng tesseract-ocr-osd \
       ghostscript pngquant unpaper \
    && rm -rf /var/lib/apt/lists/*
ENV VLADO_OCR_IDIOMAS=por+eng

WORKDIR /app
RUN useradd --create-home --uid 10001 vlado

# Dependências: versões exatas e hashes de todas as diretas e transitivas (deploy/requirements.lock,
# gerado a partir de requirements.txt e requirements-opcional.txt). Pacote sem hash conhecido ou com
# hash diferente derruba o build.
COPY deploy/requirements.lock ./deploy/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r deploy/requirements.lock

# Lista de inclusão (SEG-04): só o que a Mesa hospedada lê em execução entra na imagem. Nada de
# `COPY . .`; pastas de agente, testes, docs, instalador, Android e dados ficam de fora mesmo que
# alguém afrouxe o .dockerignore. Arquivo novo que a aplicação precise ler em execução: acrescente aqui
# (testes/test_dockerfile_endurecido.py confere a lista).
COPY scripts/ ./scripts/
COPY interface/ ./interface/
COPY prompts/ ./prompts/
COPY modelos/ ./modelos/
COPY configuracao.json AGENTS.md README.md ./
COPY casos/README.md casos/catalogo.json ./casos/
COPY entrada/README.md ./entrada/

# Data folders are Docker volumes (see docker-compose.yml). Only they are writable by the
# app user; the code stays read-only for it (and the whole root filesystem is read-only in Compose).
RUN mkdir -p conversas execucoes lixeira segredos ajustes acesso \
    && chown -R vlado:vlado casos conversas execucoes lixeira entrada segredos ajustes acesso
USER vlado

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/saude', timeout=4).status == 200 else 1)"

CMD ["sh", "-c", "exec python scripts/interface_pesquisa.py --modo piloto --host 0.0.0.0 --porta 8765 --sem-abrir --origem \"${VLADO_ORIGEM:-https://${VLADO_DOMINIO:?defina VLADO_DOMINIO}}\""]
