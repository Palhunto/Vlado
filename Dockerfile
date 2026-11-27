# VLADO — hosted pilot image (modo piloto, behind an HTTPS reverse proxy).
# Base fixada por digest (SEG-04): o build de hoje e o de daqui a seis meses partem da mesma imagem.
# Etiqueta de origem: python:3.12-slim-bookworm (Debian 12, índice multi-arquitetura; digest lido em
# 21/11/2026). Para atualizar: `docker buildx imagetools inspect python:3.12-slim-bookworm`, troque o
# digest abaixo, rode `python deploy/gerar_trava.py` (usa esta mesma imagem) e reconstrua.
# --- Imagem de backup (SEG-03): só o script de backup (biblioteca padrão), `age` (cifra para chaves públicas) e
# `rclone` (envio a S3 compatível, SFTP etc.). Fica separada da imagem do app para que o app não carregue
# ferramentas de rede e de cifra, e o serviço de backup não carregue o OCR nem as bibliotecas da Mesa.
# Alvo: `docker build --target backup .` (o Compose faz isso). O último estágio deste arquivo, `vlado`, é o padrão.
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS backup
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# Versões fixadas (J4): age 1.1.1 e rclone 1.60.1, as de bookworm em 21/11/2026. O `=1.1.1-1*` fixa a versão
# do projeto e a revisão do Debian, mas deixa passar o sufixo de recompilação (`+b3`, que muda por arquitetura) e as
# correções de segurança do Debian na mesma versão (`+deb12uN`). O build FALHA, de propósito, se o Debian passar a
# oferecer outra versão: nada muda sozinho. Para subir de versão, troque aqui e em testes/test_dockerfile_endurecido.py
# depois de ler as notas de lançamento (rclone: https://rclone.org/changelog/; age: github.com/FiloSottile/age).
RUN apt-get update \
    && apt-get install -y --no-install-recommends "age=1.1.1-1*" "rclone=1.60.1+dfsg-2*" ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && age --version | grep -q '^1\.1\.1' \
    && rclone version | head -1 | grep -q 'v1\.60\.1'

# Mesmo uid do app: lê os volumes de dados (contas ficam em 0600, só do dono). As pastas de dados existem aqui,
# do mesmo dono, para que um volume NOVO montado primeiro por este serviço (restauração num servidor novo) nasça
# gravável pelo uid 10001 e o app, depois, o encontre com as permissões certas.
RUN useradd --create-home --uid 10001 vlado \
    && mkdir -p /app/casos /app/conversas /app/execucoes /app/lixeira /app/entrada /app/segredos /app/ajustes /app/acesso /trabalho \
    && chown -R vlado:vlado /app /trabalho
WORKDIR /app
COPY scripts/backup.py ./scripts/backup.py
USER vlado
HEALTHCHECK --interval=5m --timeout=10s --start-period=2m --retries=1 \
  CMD ["python", "scripts/backup.py", "saude"]
CMD ["python", "scripts/backup.py", "agendado"]

# --- Imagem do app (estágio padrão: o último do arquivo) ---
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS vlado

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
# Scripts: lista de inclusão por arquivo (I5). Entram os módulos que a Mesa importa em execução (o fecho de imports
# de interface_pesquisa.py, que testes/test_dockerfile_endurecido.py recalcula) e os dois que o operador roda dentro
# do contêiner (semear_ambiente.py e o seu dados_sinteticos.py; acesso.py já faz parte do fecho). Ficam de fora as
# ferramentas de desenvolvimento e do Windows: gerar_instalador, vlado_lancador, demo_evidencias, preparar_notebook,
# empacotar_entrega, verificar_projeto, montar_fluxo, selecionar_caso, achados (CLI do agente de chat); e backup.py, que vive na imagem `backup`.
# Módulo novo que a Mesa importe: o teste acusa, e basta acrescentá-lo aqui.
COPY scripts/acesso.py \
     scripts/ambiente.py \
     scripts/apagamento.py \
     scripts/apuracao.py \
     scripts/autorizacao.py \
     scripts/banco.py \
     scripts/cadastrar_documentos.py \
     scripts/caderno.py \
     scripts/codex_apuracao.py \
     scripts/comparador.py \
     scripts/comum.py \
     scripts/custo.py \
     scripts/conferencia_briefing.py \
     scripts/conferencia_redacao.py \
     scripts/continuidade.py \
     scripts/correio.py \
     scripts/criar_caso.py \
     scripts/dados_sinteticos.py \
     scripts/diligencias.py \
     scripts/entrevistas.py \
     scripts/erros.py \
     scripts/evidencias.py \
     scripts/exportar_apuracao.py \
     scripts/extrair_office.py \
     scripts/extrair_pdf.py \
     scripts/fila_extracao.py \
     scripts/fluxo_codex.py \
     scripts/fontes_web.py \
     scripts/hipoteses.py \
     scripts/indice_achados.py \
     scripts/indice_sqlite.py \
     scripts/inferencia_api.py \
     scripts/instrucoes_mesa.py \
     scripts/interface_pesquisa.py \
     scripts/limites.py \
     scripts/linha_tempo.py \
     scripts/lixeira.py \
     scripts/mapa_relacoes.py \
     scripts/nova_rodada.py \
     scripts/ocr.py \
     scripts/provedor_anthropic.py \
     scripts/provedor_openai.py \
     scripts/proxies_confiaveis.py \
     scripts/rascunhos.py \
     scripts/registro_acesso.py \
     scripts/registros_achados.py \
     scripts/revisao_humana.py \
     scripts/rotas_achados.py \
     scripts/rotas_caderno.py \
     scripts/rotas_contas.py \
     scripts/rotas_conversa.py \
     scripts/rotas_documentos.py \
     scripts/rotas_downloads.py \
     scripts/rotas_equipe.py \
     scripts/rotas_estaticas.py \
     scripts/rotas_evidencia.py \
     scripts/rotas_gestao.py \
     scripts/rotas_redacao.py \
     scripts/rotas_tabelas.py \
     scripts/segredos.py \
     scripts/seletor_evidencia.py \
     scripts/segundo_fator.py \
     scripts/semear_ambiente.py \
     scripts/sugestoes_quadros.py \
     scripts/tabelas_apuracao.py \
     scripts/tetos_extracao.py \
     scripts/trabalhador_extracao.py \
     scripts/trava_cadastro.py \
     scripts/vinculo_ia.py \
     ./scripts/
COPY interface/ ./interface/
COPY prompts/ ./prompts/
COPY modelos/ ./modelos/
# precos_modelos.json: tabela de preços que scripts/custo.py lê de ROOT (/app) a cada pergunta; sem ela a Mesa não pergunta.
COPY configuracao.json AGENTS.md README.md precos_modelos.json ./
COPY casos/README.md casos/catalogo.json ./casos/
COPY entrada/README.md ./entrada/

# Data folders are Docker volumes (see docker-compose.yml). Only they are writable by the
# app user; the code stays read-only for it (and the whole root filesystem is read-only in Compose).
RUN mkdir -p conversas execucoes lixeira segredos ajustes acesso registro /var/tmp/vlado \
    && chown -R vlado:vlado casos conversas execucoes lixeira entrada segredos ajustes acesso registro /var/tmp/vlado
USER vlado

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/saude', timeout=4).status == 200 else 1)"

# TMPDIR é um volume em disco (compose): esvazia o que um encerramento brusco deixou antes de partir.
CMD ["sh", "-c", "find /var/tmp/vlado -mindepth 1 -delete 2>/dev/null; exec python scripts/interface_pesquisa.py --modo piloto --host 0.0.0.0 --porta 8765 --sem-abrir --origem \"${VLADO_ORIGEM:-https://${VLADO_DOMINIO:?defina VLADO_DOMINIO}}\""]
