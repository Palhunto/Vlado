"""Fila de extração da Mesa (CONF-02): extração e OCR fora das travas, publicação atômica no fim.

O envio pela Mesa grava os originais e enfileira; a extração e o OCR correm em processos
separados (``trabalhador_extracao``), sem ``cadastro_lock`` nem a trava de cadastro; só a
publicação no manifesto, curta e atômica, pega a trava. Leitura, notas, perguntas e outros
cadastros seguem enquanto um PDF digitalizado longo é lido.

Pasta ``casos/.fila/<lote>/`` (``lote`` é o mesmo id do lote publicado em
``casos/<caso>/cadastros/<lote>``):

- ``pedido.json``: o plano (``cadastrar_documentos.planejar``), gravado uma vez;
- ``estado.json``: estado do lote e de cada arquivo (contrato abaixo), trocado de forma atômica;
- ``originais/<n>/``: os originais recebidos, com o identificador provisório;
- ``derivados/<n>/``: a cópia de trabalho de cada arquivo e ``resultado.json``;
- ``resposta.json``: a resposta do cadastro (recibo e inventário), depois de publicado.

Um lote só aparece completo: é montado em ``.novo_<id>`` e renomeado. Depois de publicado ou
recusado, originais e cópias saem da fila (o lote publicado tem os seus); ``pedido.json``,
``estado.json`` e ``resposta.json`` ficam 24 horas.

**Contrato do estado** (``consultar``, rota ``GET /api/fila?lote=<id>`` ou ``?caso=<id>``)::

    {"lote": "<32 hex>", "caso": "<id>", "operacao": "recepcao_documentos" | "preparacao_pdfs_cadastrados",
     "estado": "enfileirado" | "processando" | "publicando" | "publicado" | "falha",
     "motivo": "<texto>" | null,                 # só em falha: por que nada foi cadastrado
     "recebido_em_utc": "...", "atualizado_em_utc": "...", "total": N, "prontos": K,
     "arquivos": [{"indice": 0, "nome": "relatorio.pdf", "bytes": 123,
                   "estado": "enfileirado" | "extraindo" | "ocr" | "pronto" | "falha",
                   "etapa": "texto" | "orientacao" | "reconhecimento" | "paginas" | null,
                   "pagina": n | null, "paginas": m | null,   # extraindo: página n de m do texto nativo;
                                                              # ocr: página n de m da etapa
                   "extracao": "extraido" | "parcial" | "sem_texto" | "erro" | "pendente" | "nao_necessaria" | null,
                   "tentativas": t, "motivo": "<texto>" | null}],
     "recibo": {"arquivo_recibo", "corpus_id", "recebidos", "novos", "duplicados"} | null}  # publicado

``pronto`` quer dizer processado: o desfecho da extração está em ``extracao`` (``erro``
inclusive, como no recibo). ``falha`` num arquivo quer dizer que o processo de extração morreu
ou estourou o prazo: o original é cadastrado mesmo assim, com a falha no recibo. ``falha`` no
lote quer dizer que nada foi cadastrado (caso apagado, limite, erro ao gravar), com ``motivo``.

**Publicação.** Os lotes prontos são publicados juntos, numa só tomada da trava de cadastro
(perguntas e outros cadastros também a pegam), cada um com as regras de sempre contra o
manifesto daquele momento.

**Quedas.** Morte do processo de extração (ou processo que nem inicia): o arquivo volta para a
fila uma vez e, na segunda, fica em ``falha`` com motivo. Queda da Mesa: na partida seguinte,
depois da limpeza da trava, quem estava extraindo volta para a fila (conta uma tentativa) e quem
estava publicando é concluído; publicar de novo é idempotente (se o manifesto já tem o recibo,
só completa o catálogo e o lote é dado por publicado, mesmo sem as cópias). O estado final é
gravado antes de apagar as cópias do lote; o que sobrar de uma queda nesse meio a partida apaga.
Encerramento ordenado devolve os arquivos em curso à fila sem contar tentativa e espera a
publicação em curso. O processo de extração leva os filhos (OCRmyPDF, Tesseract) quando acaba,
morto pela fila ou pelo vigia. Um lote com registro ilegível é recusado sozinho, sem parar a
fila; um erro repetido do coordenador espera cada vez mais, até 30 s. Nenhum arquivo fica preso.
Motivos de falha não trazem caminhos do servidor: o detalhe vai só para o registro.

**Configuração** (variáveis de ambiente): ``VLADO_EXTRACAO_PROCESSOS`` (arquivos ao mesmo tempo,
padrão 2), ``VLADO_EXTRACAO_PAGINAS`` (páginas de OCR ao mesmo tempo, somadas entre os arquivos,
padrão min(4, CPUs): 4 vCPU e 8 GB da D7), ``VLADO_EXTRACAO_TEMPO_MAXIMO`` (segundos por arquivo,
padrão 4 horas). O que pode esperar na fila: ``VLADO_FILA_LOTES_POR_CASO`` (20), ``VLADO_FILA_LOTES``
(50), ``VLADO_FILA_MB_POR_CASO`` (250) e ``VLADO_FILA_MB`` (1000), contando também os envios sendo
gravados; acima disso o envio é recusado na hora com a mensagem de limite (``fila_limite_envios``).
Modo ``processos`` (Mesa pela linha de comando, contêiner) ou ``local``
(threads da própria Mesa: testes e Mesa instalada no Windows, cujo executável congelado não sobe
outro interpretador). Um só coordenador por pasta de dados (trava ``casos/.fila/.coordenador``):
uma segunda Mesa na mesma pasta só enfileira e espera.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

import cadastrar_documentos as cadastro
from comum import dentro, ler_json
import trava_cadastro

PASTA = '.fila'
PENDENTES = ('enfileirado', 'processando', 'publicando')
TERMINAIS = ('publicado', 'falha')
EM_CURSO = ('extraindo', 'ocr')
MAX_TENTATIVAS = 2
RETENCAO = 24 * 3600
OCIOSO = 5.0  # coordinator thread ends after this many seconds with nothing to do
OCIOSO_PROCESSO = 60.0  # an idle extraction process ends after this
PUBLICACAO_ESPERA = 2.0  # wait for the cadastro lock when publishing; busy: retried on the next turn
TRABALHADOR = Path(__file__).resolve().parent / 'trabalhador_extracao.py'
ID_LOTE = re.compile(r'[0-9a-f]{32}')
log = logging.getLogger('vlado.fila_extracao')


def configuracao(modo='local', **valores) -> dict:
    env = os.environ

    def inteiro(nome, padrao, minimo, maximo):
        try:
            return max(minimo, min(maximo, int(env.get(nome) or padrao)))
        except ValueError as exc:
            raise ValueError(f'{nome} deve ser um número inteiro.') from exc
    if modo not in ('local', 'processos'):
        raise ValueError('Modo da fila de extração: local ou processos.')
    config = {'modo': modo, 'processos': inteiro('VLADO_EXTRACAO_PROCESSOS', 2, 1, 16),
              'paginas': inteiro('VLADO_EXTRACAO_PAGINAS', min(4, os.cpu_count() or 1), 1, 64),
              'tempo_maximo': inteiro('VLADO_EXTRACAO_TEMPO_MAXIMO', 4 * 3600, 30, 7 * 24 * 3600),
              # What may wait in casos/.fila (C4): batches and megabytes, per case and in all. The
              # bytes keep one account from filling the volume; the counts bound the waiting line.
              'lotes_por_caso': inteiro('VLADO_FILA_LOTES_POR_CASO', 20, 1, 1000),
              'lotes': inteiro('VLADO_FILA_LOTES', 50, 1, 10000),
              'mb_por_caso': inteiro('VLADO_FILA_MB_POR_CASO', 250, 1, 1_000_000),
              'mb': inteiro('VLADO_FILA_MB', 1000, 1, 10_000_000)}
    config.update({k: v for k, v in valores.items() if v is not None})
    return config


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def pasta_fila(root) -> Path:
    return Path(root).resolve() / 'casos' / PASTA


def _gravar_json(caminho: Path, valor):
    caminho.parent.mkdir(parents=True, exist_ok=True)  # derivados/<n> is removed before a failed file's result
    cadastro._atomico(caminho, (json.dumps(valor, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))


def _ler(caminho: Path):
    for tentativa in range(40):
        try:
            return json.loads(Path(caminho).read_text(encoding='utf-8'))
        except PermissionError:
            # Windows refuses the open for a moment while os.replace swaps the file: read again.
            if tentativa == 39:
                return None
            time.sleep(0.025)
        except (OSError, ValueError):
            return None


def _idade(caminho: Path) -> float:
    try:
        return time.time() - caminho.stat().st_mtime
    except OSError:
        return 0.0


def _remover(caminho: Path):
    shutil.rmtree(caminho, ignore_errors=True)


# --- leitura (qualquer processo) ---------------------------------------------------------------

def lotes(root):
    """(folder, plan, state) of every complete batch in the queue, oldest first."""
    pasta = pasta_fila(root)
    try:
        nomes = sorted(p for p in pasta.iterdir() if ID_LOTE.fullmatch(p.name) and p.is_dir())
    except OSError:
        return []
    achados = []
    for d in nomes:
        pedido, estado = _ler(d / 'pedido.json'), _ler(d / 'estado.json')
        if isinstance(pedido, dict) and isinstance(estado, dict):
            achados.append((d, pedido, estado))
    return sorted(achados, key=lambda x: x[1].get('recebido_em_utc') or '')


def pendentes(root, caso=None) -> list:
    """Batches not yet published or refused (of ``caso``, when given): a question waits for them."""
    return [estado['lote'] for _, pedido, estado in lotes(root)
            if estado.get('estado') in PENDENTES and (caso is None or pedido.get('caso') == caso)]


def estado_publico(pedido, estado) -> dict:
    """The state as the contract above says (no paths of the server)."""
    campos = ('indice', 'nome', 'bytes', 'estado', 'etapa', 'pagina', 'paginas', 'extracao', 'tentativas', 'motivo')
    arquivos = [{k: a.get(k) for k in campos} for a in estado.get('arquivos', [])]
    return {'lote': estado.get('lote'), 'caso': pedido.get('caso'), 'operacao': pedido.get('operacao'),
            'estado': estado.get('estado'), 'motivo': estado.get('motivo'),
            'recebido_em_utc': pedido.get('recebido_em_utc'), 'atualizado_em_utc': estado.get('atualizado_em_utc'),
            'total': len(arquivos), 'prontos': sum(a['estado'] in ('pronto', 'falha') for a in arquivos),
            'arquivos': arquivos, 'recibo': estado.get('recibo')}


def consultar(root, *, lote=None, caso=None) -> dict:
    """``{'lote': state}`` of one batch, or ``{'lotes': [...]}`` (of one case, when given)."""
    if lote is not None:
        if not isinstance(lote, str) or not ID_LOTE.fullmatch(lote):
            raise ValueError('Identificador de lote inválido.')
        d = pasta_fila(root) / lote
        pedido, estado = _ler(d / 'pedido.json'), _ler(d / 'estado.json')
        if not isinstance(pedido, dict) or not isinstance(estado, dict):
            raise ValueError('Lote não encontrado na fila.')
        return {'lote': estado_publico(pedido, estado)}
    if caso is not None and (not isinstance(caso, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', caso)):
        raise ValueError('Identificador de caso inválido.')
    return {'lotes': [estado_publico(p, e) for _, p, e in lotes(root) if caso is None or p.get('caso') == caso]}


def _completar_catalogo(root, caso, manifest):
    """Roll forward a publication cut between the manifest and the catalog. Caller holds the lock."""
    caminho = dentro(root, 'casos/catalogo.json')
    catalogo = ler_json(caminho) if caminho.is_file() else {'casos': []}
    entrada = next((c for c in catalogo['casos'] if c['id'] == caso), None)
    if entrada is None:
        catalogo['casos'].append({'id': caso, 'titulo': manifest['titulo'], 'manifesto': f'casos/{caso}/manifesto.json',
                                  'exemplo': False, 'documentos': len(manifest['documentos'])})
    elif entrada.get('documentos') != len(manifest['documentos']):
        entrada['documentos'] = len(manifest['documentos'])
    else:
        return
    cadastro._atomico(caminho, cadastro._bytes(catalogo))


def _manifesto_com_recibo(root, plano):
    """The case's manifest when it already names this batch's receipt (published), else None."""
    caso, lote = plano['caso'], plano['lote']
    recibo = f'casos/{caso}/cadastros/{lote}/recibo.json'
    try:
        manifesto = dentro(root, f'casos/{caso}/manifesto.json')
    except ValueError:
        return None
    atual = _ler(manifesto) if manifesto.is_file() else None
    if isinstance(atual, dict) and any(r.get('arquivo') == recibo for r in atual.get('registros_cadastro', [])):
        return atual
    return None


def publicar_lote(root, plano, base, resultados):
    """Publish a queued batch; idempotent after a crash. Caller holds the cadastro lock."""
    caso, lote = plano['caso'], plano['lote']
    recibo = f'casos/{caso}/cadastros/{lote}/recibo.json'
    atual = _manifesto_com_recibo(root, plano)
    if atual is not None:
        _completar_catalogo(root, caso, atual)  # already published: the crash came after the manifest
        return {**ler_json(dentro(root, recibo)), 'arquivo_recibo': recibo, 'inventario': cadastro.inventario(root, caso)}
    orfao = dentro(root, f'casos/{caso}/cadastros/{lote}')
    if orfao.is_dir():
        _remover(orfao)  # renamed into place, then cut before the manifest named it: the queue has the files
    return cadastro.publicar(root, plano, base, resultados, ligar=True)


# --- quem executa a extração -------------------------------------------------------------------

class _Executor:
    tarefa = None  # (lote, indice) being processed
    inicio = 0.0
    motivo_fim = None
    pid = None

    def __init__(self, fila):
        self.fila = fila
        self.ocioso_desde = time.monotonic()


class _ExecutorLocal(_Executor):
    """A thread of the Mesa (local mode): cannot be killed, so it has no time limit."""

    def iniciar(self, base, tarefa, paralelo):
        thread = threading.Thread(target=self._rodar, args=(base, tarefa, paralelo), daemon=True,
                                  name='vlado_extracao')
        with self.fila._trava:  # encerrar() waits for these
            self.fila._locais = [t for t in self.fila._locais if t.is_alive()] + [thread]
        thread.start()

    def _rodar(self, base, tarefa, paralelo):
        def progresso(fase, feitas, total):
            self.fila._eventos.put(('msg', self, {'tipo': 'progresso', 'fase': fase, 'feitas': feitas, 'total': total}))
        try:
            mensagem = {'tipo': 'resultado', **cadastro.extrair_item(tarefa, base=Path(base), paralelo=paralelo,
                                                                     progresso=progresso)}
        except Exception as exc:  # noqa: BLE001 - the queue decides
            mensagem = {'tipo': 'erro', 'mensagem': f'{type(exc).__name__}: {str(exc)[:1000]}'}
        self.fila._eventos.put(('msg', self, mensagem))

    def matar(self):
        pass

    def fechar(self):
        self.fila._eventos.put(('fim', self, 0))


class _ExecutorProcesso(_Executor):
    """One ``trabalhador_extracao`` process, one file at a time, killed on timeout or shutdown."""

    def __init__(self, fila):
        super().__init__(fila)
        opcoes = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        self.proc = subprocess.Popen([sys.executable, str(TRABALHADOR), '--pai', str(os.getpid())],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8',
                                     cwd=str(TRABALHADOR.parent), **opcoes)
        self.pid = self.proc.pid
        threading.Thread(target=self._ler, daemon=True, name='vlado_extracao_leitor').start()

    def _ler(self):
        try:
            for linha in self.proc.stdout:
                try:
                    mensagem = json.loads(linha)
                except ValueError:
                    continue
                self.fila._eventos.put(('msg', self, mensagem))
        except (OSError, ValueError):
            pass
        finally:
            codigo = self.proc.wait()
            for fluxo in (self.proc.stdin, self.proc.stdout):
                try:
                    fluxo.close()
                except (OSError, ValueError):
                    pass
            self.fila._eventos.put(('fim', self, codigo))

    def iniciar(self, base, tarefa, paralelo):
        try:
            self.proc.stdin.write(json.dumps({'tarefa': tarefa, 'base': str(base), 'paralelo': paralelo},
                                             ensure_ascii=False) + '\n')
            self.proc.stdin.flush()
        except (OSError, ValueError):
            self.matar()  # the end event marks the task

    def matar(self):
        try:
            if os.name != 'nt':
                os.killpg(self.proc.pid, 9)  # its own session: Tesseract and OCRmyPDF go too
            else:
                self.proc.kill()
        except (OSError, ProcessLookupError):
            pass

    def fechar(self):
        try:
            self.proc.stdin.write('{"tipo": "sair"}\n')
            self.proc.stdin.close()
        except (OSError, ValueError):
            self.matar()


def mensagem_limite(arquivos, mesa=False) -> str:
    """The queue-limit message (W11 'limite' block; code ``fila_limite_envios`` in erros)."""
    lido = 'arquivo' if arquivos == 1 else 'arquivos'
    sendo = 'sendo lido' if arquivos == 1 else 'sendo lidos'
    onde = 'na Mesa' if mesa else 'desta apuração'
    return (f'Limite de envios em processamento. Há {arquivos} {lido} {onde} {sendo}. Os arquivos já enviados '
            'estão guardados; envie os próximos quando estes terminarem. Documentos, perguntas e caderno '
            'seguem funcionando.')


ERRO_EXTRACAO = 'Falha inesperada ao ler o arquivo; o detalhe está no registro do servidor.'


# --- a fila ------------------------------------------------------------------------------------

class Fila:
    """The Mesa's extraction queue: enqueue, coordinate, wait. One per server."""

    def __init__(self, root, modo='local', **config):
        self.root = Path(root).resolve()
        self.pasta = pasta_fila(self.root)
        self.config = configuracao(modo, **config)
        self._eventos = queue.Queue()
        self._mudou = threading.Condition()
        self._trava = threading.Lock()
        self._thread = None
        self._pedido = False
        self._parar = False
        self._dono = trava_cadastro.TravaExclusiva(self.pasta / '.coordenador')
        self._lotes = {}
        self._terminais = set()
        self._executores = []
        self._locais = []  # extraction threads of the local mode
        self._varrido = 0.0
        self._trava_recepcao = threading.Lock()
        self._reservas = {}  # uploads being written: staging name -> (case, files, bytes)
        self._falhas = 0  # consecutive failures of the coordinator (C8: backoff)

    # enfileirar ---------------------------------------------------------------------------------
    def receber(self, caso, gravar, *, titulo=None, natureza='nao_informada', novo=False, modo_fontes=None,
                dominio_permitido=None, ocr_imagens=False) -> str:
        """Enqueue an upload. ``gravar(pasta)`` writes the received files there and returns their paths.

        Every check that refuses a batch at once runs here, before anything is queued (formats,
        limit, case), with the same messages as the command line. Returns the batch id.
        """
        staging = self._staging()
        try:
            self._reservar(staging, caso)  # room for one more batch, before anything big is written
            sources = gravar(staging / 'recebidos')
            self._reservar(staging, caso, len(sources), sum(s.stat().st_size for s in sources))
            fontes_web = cadastro.validar_pedido(caso, natureza, sources, novo, modo_fontes, dominio_permitido)
            plano = cadastro.planejar(self.root, caso, sources, titulo=titulo, natureza=natureza, novo=novo,
                                      ocr_imagens=bool(ocr_imagens), fontes_web=fontes_web)
            cadastro.preparar_copias(plano, staging, mover=True)
            _remover(staging / 'recebidos')
            return self._gravar_lote(staging, plano)
        except BaseException:
            _remover(staging)
            raise
        finally:
            self._liberar(staging)

    def preparar_pdfs(self, caso) -> str:
        """Enqueue the OCR/extraction of this case's preserved PDFs (new corpus version at the end)."""
        staging = self._staging()
        try:
            self._reservar(staging, caso)
            plano = cadastro.plano_preparar_pdfs(self.root, caso)
            self._reservar(staging, caso, len(plano['itens']), 0)  # the originals stay in the case
            return self._gravar_lote(staging, plano)
        except BaseException:
            _remover(staging)
            raise
        finally:
            self._liberar(staging)

    def _ocupacao(self):
        """{case: [batches, files, bytes]} waiting in the queue: on disk, plus uploads being written."""
        ocupado = {}
        try:
            pastas = [p for p in self.pasta.iterdir() if ID_LOTE.fullmatch(p.name)]
        except OSError:
            pastas = []
        for pasta in pastas:
            estado = _ler(pasta / 'estado.json')
            if not isinstance(estado, dict) or estado.get('estado') not in PENDENTES:
                continue
            pedido = _ler(pasta / 'pedido.json')
            caso = pedido.get('caso') if isinstance(pedido, dict) else None
            arquivos = estado.get('arquivos') or []
            soma = ocupado.setdefault(caso, [0, 0, 0])
            soma[0] += 1
            soma[1] += len(arquivos)
            soma[2] += sum(a.get('bytes') or 0 for a in arquivos if isinstance(a, dict))
        for caso, arquivos, tamanho in self._reservas.values():
            soma = ocupado.setdefault(caso, [0, 0, 0])
            soma[0], soma[1], soma[2] = soma[0] + 1, soma[1] + arquivos, soma[2] + tamanho
        return ocupado

    def _reservar(self, staging, caso, arquivos=0, tamanho=0):
        """Refuse an upload the queue has no room for (C4): batches and bytes, per case and in all."""
        with self._trava_recepcao:
            self._reservas.pop(staging.name, None)
            ocupado = self._ocupacao()
            lotes, pendentes, usado = ocupado.get(caso, [0, 0, 0])
            total = [sum(v[i] for v in ocupado.values()) for i in range(3)]
            mb = 1024 * 1024
            if lotes + 1 > self.config['lotes_por_caso'] or usado + tamanho > self.config['mb_por_caso'] * mb:
                raise ValueError(mensagem_limite(pendentes))
            if total[0] + 1 > self.config['lotes'] or total[2] + tamanho > self.config['mb'] * mb:
                raise ValueError(mensagem_limite(total[1], mesa=True))
            self._reservas[staging.name] = (caso, arquivos, tamanho)

    def _liberar(self, staging):
        with self._trava_recepcao:
            self._reservas.pop(staging.name, None)

    def _staging(self) -> Path:
        self.pasta.mkdir(parents=True, exist_ok=True)
        staging = self.pasta / f'.novo_{uuid.uuid4().hex}'
        staging.mkdir()
        return staging

    def _gravar_lote(self, staging, plano) -> str:
        for item in plano['itens']:
            if item['copia']:
                item['origem'] = None  # the received copy now lives in the batch folder
        estado = {'esquema': 1, 'lote': plano['lote'], 'estado': 'enfileirado', 'motivo': None,
                  'atualizado_em_utc': _agora(), 'recibo': None,
                  'arquivos': [{'indice': i['indice'], 'nome': i['nome'], 'bytes': i['bytes'],
                                'estado': 'enfileirado' if i['extrair'] else 'pronto',
                                'extracao': None if i['extrair'] else 'nao_necessaria',
                                'etapa': None, 'pagina': None, 'paginas': None, 'tentativas': 0, 'motivo': None}
                               for i in plano['itens']]}
        _gravar_json(staging / 'pedido.json', plano)
        _gravar_json(staging / 'estado.json', estado)
        os.replace(staging, self.pasta / plano['lote'])
        self._varrido = 0.0  # the coordinator looks for it at once, not at the next periodic scan
        self.iniciar()
        return plano['lote']

    # esperar e consultar -------------------------------------------------------------------------
    def aguardar(self, lote, prazo=None):
        """The cadastro response once the batch is published; ValueError with the reason if refused."""
        limite = None if prazo is None else time.monotonic() + prazo
        pasta = self.pasta / lote
        while True:
            # Shutting down: wait while the coordinator still runs (a publication in course ends and
            # its receipt is answered). Checked before reading: once it stopped, the state is final.
            parado = self._parar and not self.coordenando()
            estado = _ler(pasta / 'estado.json')
            if not isinstance(estado, dict):
                raise ValueError('Lote não encontrado na fila.')
            if estado['estado'] == 'publicado':
                resposta = _ler(pasta / 'resposta.json')
                if isinstance(resposta, dict):
                    return resposta
            elif estado['estado'] == 'falha':
                raise ValueError(estado.get('motivo') or 'O lote não foi cadastrado.')
            if parado:
                raise trava_cadastro.TravaInterrompida('A Mesa está sendo encerrada; o lote ficou na fila e será '
                                                       'concluído quando ela voltar.')
            if limite is not None and time.monotonic() >= limite:
                raise TimeoutError('Lote ainda em processamento.')
            self.iniciar()
            with self._mudou:
                self._mudou.wait(0.5)

    def consultar(self, *, lote=None, caso=None):
        return consultar(self.root, lote=lote, caso=caso)

    # ciclo de vida -------------------------------------------------------------------------------
    def iniciar(self):
        """Start the coordinator if needed (enqueue, waiting, the Mesa's start)."""
        with self._trava:
            if self._parar:
                return
            self._pedido = True
            if self._thread is None:
                self._thread = threading.Thread(target=self._laco, daemon=True, name='vlado_fila')
                self._thread.start()
        self._eventos.put(('acordar',))

    def coordenando(self) -> bool:
        with self._trava:
            return self._thread is not None

    def encerrar(self, prazo=0.0):
        """Stop: files being read go back to the queue without counting an attempt; publishing ends first.

        Waits up to ``prazo`` seconds for the coordinator and then for extraction threads of the
        local mode (they cannot be killed; their late results are ignored). Nothing of this queue
        touches its folder after that, unless the time ran out.
        """
        limite = time.monotonic() + max(0.0, prazo)
        with self._trava:
            self._parar = True
            thread = self._thread
        self._eventos.put(('acordar',))
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(0.0, limite - time.monotonic()))
        with self._trava:
            locais, self._locais = self._locais, []
        for extracao in locais:
            if extracao is not threading.current_thread():
                extracao.join(max(0.0, limite - time.monotonic()))
        with self._mudou:
            self._mudou.notify_all()

    def _laco(self):
        ocioso_desde = time.monotonic()
        while True:
            try:
                trabalho = self._passo()
                self._falhas = 0
            except Exception:  # noqa: BLE001 - the coordinator never dies on one bad batch
                self._falhas += 1
                if self._falhas == 1 or self._falhas % 20 == 0:  # the trace once, then now and then (C8)
                    log.exception('Fila de extração: falha no coordenador (%s seguidas); tentando de novo.',
                                  self._falhas)
                trabalho = True
                fim = time.monotonic() + min(30.0, 0.5 * 2 ** min(self._falhas - 1, 6))  # backoff up to 30 s
                while time.monotonic() < fim and not self._parar:
                    time.sleep(0.1)
            if self._parar:
                with self._trava:
                    self._encerrar_trabalho()
                    self._thread = None
                return
            if trabalho:
                ocioso_desde = time.monotonic()
            elif time.monotonic() - ocioso_desde > OCIOSO:
                with self._trava:
                    if self._pedido:
                        self._pedido = False
                        ocioso_desde = time.monotonic()
                    else:
                        self._encerrar_trabalho()
                        self._thread = None
                        return
            self._processar_eventos(0.5)

    def _encerrar_trabalho(self):
        """Coordinator ends (idle or shutdown): running files back to the queue, processes ended."""
        for executor in list(self._executores):
            ocupado = executor.tarefa is not None
            if ocupado:
                lote, indice = executor.tarefa
                executor.tarefa = None
                reg = self._lotes.get(lote)
                if reg:
                    arquivo = reg['estado']['arquivos'][indice]
                    arquivo.update(estado='enfileirado', etapa=None, pagina=None, paginas=None,
                                   motivo='Interrompido pelo encerramento da Mesa; volta a ser lido na próxima partida.')
                    self._gravar(reg)
                executor.matar()
            else:
                executor.fechar()
        self._executores.clear()
        self._lotes.clear()
        self._dono.soltar()
        with self._mudou:
            self._mudou.notify_all()

    # coordenação ---------------------------------------------------------------------------------
    def _passo(self) -> bool:
        self._processar_eventos(0)
        if not self._dono.segura:
            if not self.pasta.is_dir():
                return False
            if not self._dono.tentar():
                return bool(pendentes(self.root))  # another Mesa coordinates; take over if it dies
            self._recuperar()
        if time.monotonic() - self._varrido > 1.0:
            self._varrer()
        self._prazos()
        self._despachar()
        self._publicar_prontos()
        self._gravar_atrasados()
        trabalho = bool(self._lotes) or any(e.tarefa for e in self._executores)
        if not trabalho:
            self._dono.soltar()
        return trabalho

    def _processar_eventos(self, espera):
        try:
            evento = self._eventos.get(timeout=espera) if espera else self._eventos.get_nowait()
        except queue.Empty:
            return
        while True:
            if evento[0] == 'msg':
                self._mensagem(evento[1], evento[2])
            elif evento[0] == 'fim':
                self._fim(evento[1], evento[2])
            try:
                evento = self._eventos.get_nowait()
            except queue.Empty:
                return

    def _registrar(self, pasta, pedido, estado) -> bool:
        """Adopt a pending batch; an incoherent one (disk damage, a hand edit) is refused on its own
        instead of failing every turn of the coordinator and stopping the whole queue."""
        try:
            itens, arquivos = pedido['itens'], estado['arquivos']
            coerente = (estado['lote'] == pasta.name == pedido['lote'] and isinstance(pedido['caso'], str)
                        and len(itens) == len(arquivos) > 0
                        and all(a['indice'] == i == itens[i]['indice'] and isinstance(a['estado'], str)
                                for i, a in enumerate(arquivos)))
        except (KeyError, TypeError, IndexError):
            coerente = False
        if not coerente:
            log.warning('Fila de extração: lote %s ilegível; recusado sem cadastrar.', pasta.name)
            for parte in ('originais', 'derivados'):
                _remover(pasta / parte)
            _gravar_json(pasta / 'estado.json', {
                'esquema': 1, 'lote': pasta.name, 'estado': 'falha', 'atualizado_em_utc': _agora(), 'recibo': None,
                'arquivos': [], 'motivo': 'Lote não cadastrado: o registro do envio na fila ficou ilegível. Nenhum '
                                          'arquivo deste lote foi confirmado; envie os arquivos de novo.'})
            self._terminais.add(pasta.name)
            return False
        self._lotes[pasta.name] = {'dir': pasta, 'pedido': pedido, 'estado': estado, 'gravado': 0.0, 'sujo': False}
        return True

    def _recuperar(self):
        """Just became the coordinator: adopt the queue as a dead coordinator left it."""
        self._lotes.clear()
        self._terminais.clear()
        try:
            itens = list(self.pasta.iterdir())
        except OSError:
            return
        for pasta in itens:
            if pasta.name.startswith('.novo_') and pasta.is_dir():
                if _idade(pasta) > 3600:
                    _remover(pasta)  # an upload cut while being written; never queued
                continue
            if not ID_LOTE.fullmatch(pasta.name) or not pasta.is_dir():
                continue
            pedido, estado = _ler(pasta / 'pedido.json'), _ler(pasta / 'estado.json')
            if not isinstance(pedido, dict) or not isinstance(estado, dict):
                if _idade(pasta) > 3600:
                    _remover(pasta)
                continue
            if estado.get('estado') in TERMINAIS:
                if _idade(pasta / 'estado.json') > RETENCAO:
                    _remover(pasta)
                else:
                    self._terminais.add(pasta.name)
                    self._limpar_partes(pasta)  # cut after the final state: the copies are no longer needed
                continue
            if not self._registrar(pasta, pedido, estado):
                continue
            reg = self._lotes[pasta.name]
            if estado.get('estado') == 'publicando' and self._ja_publicado(reg):
                self._gravar(reg)
                continue  # its files may be gone: published again idempotently, final state only
            mudou = False
            for arquivo in estado['arquivos']:
                item = pedido['itens'][arquivo['indice']]
                if arquivo['estado'] in EM_CURSO:
                    mudou = True
                    self._tentativa_perdida(reg, arquivo['indice'], 'O processamento foi interrompido por uma queda '
                                            'da Mesa ou do processo de extração.')
                elif (arquivo['estado'] == 'pronto' and item['extrair']
                      and not (pasta / f'derivados/{arquivo["indice"]}/resultado.json').is_file()):
                    arquivo.update(estado='enfileirado', extracao=None)
                    mudou = True
            if estado.get('estado') == 'publicando' and any(a['estado'] not in ('pronto', 'falha')
                                                             for a in estado['arquivos']):
                estado['estado'], mudou = 'processando', True  # files went back to the queue: read them first
            if mudou:
                self._gravar(reg)
        self._varrido = time.monotonic()

    def _ja_publicado(self, reg) -> bool:
        """A batch whose receipt the manifest already names (C1): its files are marked as published.

        The crash came after the publication and before the final state; the files' states are
        taken from what was published, and the publication runs again, idempotently.
        """
        manifesto = _manifesto_com_recibo(self.root, reg['pedido'])
        if manifesto is None:
            return False
        recibo = _ler(dentro(self.root, f"casos/{reg['pedido']['caso']}/cadastros/{reg['pedido']['lote']}/recibo.json"))
        entradas = recibo.get('arquivos', []) if isinstance(recibo, dict) else []
        documentos = {d.get('id'): d for d in manifesto.get('documentos', [])}
        for arquivo in reg['estado']['arquivos']:
            if arquivo['estado'] in ('pronto', 'falha'):
                continue
            indice = arquivo['indice']
            doc = documentos.get(entradas[indice].get('documento_id')) if indice < len(entradas) else None
            extracao = next((doc[k]['estado'] for k in ('extracao_pdf', 'extracao_office', 'ocr_imagem')
                             if doc and isinstance(doc.get(k), dict)), None)
            arquivo.update(estado='pronto', etapa=None, pagina=None, paginas=None, motivo=None, processo=None,
                           extracao=extracao or ('nao_necessaria' if doc else None))
        return True

    @staticmethod
    def _limpar_partes(pasta):
        for parte in ('originais', 'derivados'):
            _remover(pasta / parte)

    def _varrer(self):
        self._varrido = time.monotonic()
        for pasta, pedido, estado in lotes(self.root):
            nome = pasta.name
            if nome in self._lotes or nome in self._terminais:
                continue
            if estado.get('estado') in TERMINAIS:
                self._terminais.add(nome)
            else:
                self._registrar(pasta, pedido, estado)

    def _livre(self):
        for executor in self._executores:
            if executor.tarefa is None:
                return executor
        if len(self._executores) >= self.config['processos']:
            return None
        executor = (_ExecutorProcesso(self) if self.config['modo'] == 'processos' else _ExecutorLocal(self))
        self._executores.append(executor)
        return executor

    def _despachar(self):
        for reg in list(self._lotes.values()):
            if reg['estado']['estado'] not in ('enfileirado', 'processando'):
                continue
            for arquivo in reg['estado']['arquivos']:
                if arquivo['estado'] != 'enfileirado':
                    continue
                try:
                    executor = self._livre()
                except OSError as exc:  # the extraction process did not start: a lost attempt, not a stuck queue
                    log.warning('Fila de extração: processo de extração não iniciou: %s', exc)
                    self._tentativa_perdida(reg, arquivo['indice'], 'O processo de extração não pôde ser iniciado '
                                            f'({exc.strerror or exc}).')
                    self._gravar(reg)
                    continue
                if executor is None:
                    return
                item = reg['pedido']['itens'][arquivo['indice']]
                _remover(reg['dir'] / f'derivados/{arquivo["indice"]}')  # extractors never overwrite
                ocupados = sum(1 for e in self._executores if e.tarefa) + 1
                paralelo = max(1, self.config['paginas'] // ocupados)
                tarefa = cadastro.tarefa(self.root, reg['pedido'], item, reg['dir'])
                executor.tarefa, executor.inicio, executor.motivo_fim = (reg['estado']['lote'], arquivo['indice']), time.monotonic(), None
                if item['tipo'] == 'imagem':  # one OCR read, no page progress from the engine
                    arquivo.update(estado='ocr', etapa='paginas', pagina=0, paginas=1, motivo=None)
                else:
                    arquivo.update(estado='extraindo', etapa=None, pagina=None, paginas=None, motivo=None)
                arquivo['processo'] = executor.pid  # internal (diagnostics): not in the public contract
                reg['estado']['estado'] = 'processando'
                self._gravar(reg)
                executor.iniciar(reg['dir'], tarefa, paralelo)

    def _prazos(self):
        agora = time.monotonic()
        for executor in list(self._executores):
            if executor.tarefa and isinstance(executor, _ExecutorProcesso) and agora - executor.inicio > self.config['tempo_maximo']:
                executor.motivo_fim = f'Tempo máximo de extração excedido ({self.config["tempo_maximo"]} s).'
                executor.matar()
            elif executor.tarefa is None and agora - executor.ocioso_desde > OCIOSO_PROCESSO:
                self._executores.remove(executor)
                executor.fechar()

    def _mensagem(self, executor, mensagem):
        if executor.tarefa is None:
            return  # a late message of a task already given up
        lote, indice = executor.tarefa
        reg = self._lotes.get(lote)
        if reg is None:
            self._abandonar(executor)
            return
        arquivo = reg['estado']['arquivos'][indice]
        tipo = mensagem.get('tipo')
        if tipo == 'progresso':
            fase = mensagem.get('fase')
            arquivo.update(estado='extraindo' if fase == 'texto' else 'ocr', etapa=fase,
                           pagina=mensagem.get('feitas'), paginas=mensagem.get('total'))
            self._gravar(reg, urgente=False)
        elif tipo == 'resultado':
            executor.tarefa, executor.ocioso_desde = None, time.monotonic()
            _gravar_json(reg['dir'] / f'derivados/{indice}/resultado.json',
                         {'resultado': mensagem['resultado'], 'derivado': mensagem.get('derivado')})
            arquivo.update(estado='pronto', extracao=(mensagem['resultado'] or {}).get('estado'), motivo=None, processo=None)
            self._gravar(reg)
        elif tipo == 'erro':
            executor.tarefa, executor.ocioso_desde = None, time.monotonic()
            # The exception text may carry server paths: it goes to the log, the state says a fixed text (C5).
            log.warning('Fila de extração: erro ao ler o arquivo %s do lote %s: %s', indice, lote, mensagem.get('mensagem'))
            arquivo['tentativas'] = arquivo.get('tentativas', 0) + 1
            if arquivo['tentativas'] < MAX_TENTATIVAS:
                arquivo.update(estado='enfileirado', motivo=ERRO_EXTRACAO)
                self._gravar(reg)
            else:
                # Same as the command line: an exception (not an extraction outcome) aborts the batch.
                arquivo.update(estado='falha', motivo=ERRO_EXTRACAO)
                self._terminar(reg, 'falha', motivo=f'Lote não cadastrado: falha inesperada ao ler {arquivo["nome"]}. '
                                                    'Nenhum arquivo deste lote foi confirmado; o detalhe está no '
                                                    'registro do servidor. Envie os arquivos de novo.')

    def _fim(self, executor, codigo):
        if executor in self._executores:
            self._executores.remove(executor)
        if executor.tarefa is None:
            return
        lote, indice = executor.tarefa
        executor.tarefa = None
        reg = self._lotes.get(lote)
        if reg is None:
            return
        if executor.motivo_fim:  # timeout: reading it again would take as long
            reg['estado']['arquivos'][indice]['tentativas'] = MAX_TENTATIVAS - 1
        self._tentativa_perdida(reg, indice, executor.motivo_fim
                                or f'O processo de extração terminou sem resposta (código {codigo}).')
        self._gravar(reg)

    def _abandonar(self, executor):
        """Give up an executor's task: it is stopped and never reused, so a late message of that
        task (a local thread cannot be stopped) is never taken for another file's."""
        executor.tarefa = None
        if executor in self._executores:
            self._executores.remove(executor)
        executor.matar()

    def _tentativa_perdida(self, reg, indice, motivo):
        """A read that never finished: back to the queue once; then the file fails, the batch goes on."""
        arquivo = reg['estado']['arquivos'][indice]
        arquivo['tentativas'] = arquivo.get('tentativas', 0) + 1
        arquivo['processo'] = None
        _remover(reg['dir'] / f'derivados/{indice}')
        if arquivo['tentativas'] < MAX_TENTATIVAS:
            arquivo.update(estado='enfileirado', etapa=None, pagina=None, paginas=None, motivo=motivo)
            return
        item = reg['pedido']['itens'][indice]
        mensagem = f'{motivo} Tentativas: {arquivo["tentativas"]}. O original está preservado; a extração ficou pendente.'
        _gravar_json(reg['dir'] / f'derivados/{indice}/resultado.json',
                     {'resultado': cadastro.resultado_sem_extracao(item['tipo'], item['sufixo'], mensagem),
                      'derivado': None})
        arquivo.update(estado='falha', extracao='erro', etapa=None, motivo=motivo)

    def _publicar_prontos(self):
        """Publish every batch whose files are all processed, under one hold of the cadastro lock.

        One hold for all of them: question freezes and other cadastros also take the lock, and a
        coordinator that asked once per batch lost the turn to them each time.
        """
        prontos = [reg for reg in self._lotes.values() if reg['estado']['estado'] not in TERMINAIS
                   and all(a['estado'] in ('pronto', 'falha') for a in reg['estado']['arquivos'])]
        if not prontos:
            return
        for reg in prontos:
            if reg['estado']['estado'] != 'publicando':
                reg['estado']['estado'] = 'publicando'
                self._gravar(reg)
        operacoes = {reg['pedido']['operacao'] for reg in prontos}
        operacao = 'preparacao_pdfs' if operacoes == {'preparacao_pdfs_cadastrados'} else 'cadastro'
        desfechos = []
        try:
            with trava_cadastro.trava(self.root, espera=PUBLICACAO_ESPERA, operacao=operacao, avisar=False):
                for reg in prontos:
                    desfechos.append((reg, self._publicar(reg)))
        except trava_cadastro.TravaInterrompida:
            pass  # shutting down: the rest is published at the next start
        except trava_cadastro.TravaOcupada:
            pass  # another operation holds the lock: the rest on the next turn
        # Outside the lock: a crash before these writes is rolled forward at the next start.
        for reg, (estado, valor) in desfechos:
            if estado == 'publicado':
                _gravar_json(reg['dir'] / 'resposta.json', valor)
                self._terminar(reg, 'publicado', recibo={k: valor.get(k) for k in
                                                         ('arquivo_recibo', 'corpus_id', 'recebidos', 'novos', 'duplicados')})
            else:
                self._terminar(reg, 'falha', motivo=valor)

    def _publicar(self, reg):
        """Publish one batch (the caller holds the lock): ('publicado', response) or ('falha', reason)."""
        pedido, base = reg['pedido'], reg['dir']
        resultados = {}
        for item in pedido['itens']:
            if item['extrair']:
                obtido = _ler(base / f'derivados/{item["indice"]}/resultado.json')
                if isinstance(obtido, dict):
                    resultados[item['indice']] = obtido
        try:
            return 'publicado', publicar_lote(self.root, pedido, base, resultados)
        except ValueError as exc:
            return 'falha', self._sem_caminhos(str(exc))
        except OSError as exc:
            log.warning('Fila de extração: falha ao gravar o lote %s: %s', reg['estado']['lote'], exc)
            return 'falha', (f'Lote não cadastrado: falha ao gravar ({exc.strerror or type(exc).__name__}). '
                             'Nenhum arquivo deste lote foi confirmado.')

    def _sem_caminhos(self, texto):
        """A message without the server's data folder (C5): paths stay in the log only."""
        for raiz in {str(self.root), self.root.as_posix()}:
            texto = texto.replace(raiz + os.sep, '').replace(raiz + '/', '').replace(raiz, '<dados>')
        return texto

    def _terminar(self, reg, estado, *, motivo=None, recibo=None):
        lote = reg['estado']['lote']
        for executor in list(self._executores):
            if executor.tarefa and executor.tarefa[0] == lote:  # the other files of a refused batch
                self._abandonar(executor)
        reg['estado'].update(estado=estado, motivo=motivo, recibo=recibo)
        self._lotes.pop(lote, None)
        self._terminais.add(lote)
        # The final state first (C1): a crash after it only leaves copies the next start removes;
        # a crash before it finds the receipt in the manifest and concludes the batch.
        self._gravar(reg)
        self._limpar_partes(reg['dir'])  # the published batch has its own (hard-linked) files
        if not self._lotes and not any(e.tarefa for e in self._executores):
            self._dono.soltar()

    def _gravar(self, reg, urgente=True):
        agora = time.monotonic()
        if not urgente and agora - reg['gravado'] < 0.5:
            reg['sujo'] = True
            return
        reg['estado']['atualizado_em_utc'] = _agora()
        _gravar_json(reg['dir'] / 'estado.json', reg['estado'])
        reg['gravado'], reg['sujo'] = agora, False
        with self._mudou:
            self._mudou.notify_all()

    def _gravar_atrasados(self):
        for reg in list(self._lotes.values()):
            if reg['sujo'] and time.monotonic() - reg['gravado'] >= 0.5:
                self._gravar(reg)
