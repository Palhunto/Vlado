"""API inference adapter with the same contract the conversation backend expects.

The backend (`Conversas`) speaks a small JSON-RPC-like protocol: `call()` for
requests, notifications through a callback, and server requests (tool calls)
answered with `send()`. This module implements that contract on top of a
provider API (Anthropic or OpenAI). Keys are read from the server environment
only and never written to configuration, events, logs or history files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import queue
import re
import threading
import uuid

from comum import ler_json
from cadastrar_documentos import _atomico
import segredos

MODELOS_PADRAO = {'anthropic': 'claude-sonnet-5-5', 'openai': 'gpt-6.1-sol'}
CHAVES = {'anthropic': 'ANTHROPIC_API_KEY', 'openai': 'OPENAI_API_KEY'}
MAX_TOKENS_PADRAO = 16000
MAX_PASSOS = 60
ESPERA_FERRAMENTA = 300
ESPERA_ENCERRAMENTO = 15
MAX_IMAGENS_CONTEXTO = 3
VERSAO = 'api-1'
HISTORICO = 'api_historico.json'


def seguro(value) -> str:
    """Remove credentials from any text that may reach events, logs or the browser."""
    text = str(value)
    # Exact configured values first, whatever their format (gateways, future key shapes).
    valores = {os.environ.get(nome, '').strip() for nome in CHAVES.values()} | segredos.conhecidas()
    for segredo in sorted(valores, key=len, reverse=True):
        if len(segredo) >= 8:
            text = text.replace(segredo, '[credencial omitida]')
    text = re.sub(r'(?i)((?:bearer|basic)\s+)[\w.\-+/=]+', r'\1[credencial omitida]', text)
    text = re.sub(r'(?<![A-Za-z0-9])sk-[\w\-]+', '[credencial omitida]', text)
    text = re.sub(r'eyJ[\w-]+\.[\w-]+\.[\w-]+', '[token omitido]', text)
    text = re.sub(r'(?i)((?:access_token|refresh_token|id_token|api[_-]?key|x-api-key)["\s:=]+)[^\s",}]+',
                  r'\1[omitido]', text)
    return text[:4000]


class ErroIA(ValueError):
    """User-facing inference failure; `codigo` classifies it (autenticacao, limite, conexao...)."""

    def __init__(self, mensagem: str, codigo: str | None = None):
        super().__init__(mensagem)
        self.codigo = codigo


_CODIGOS_SDK = (
    (('AuthenticationError', 'PermissionDeniedError'), 'autenticacao',
     'A API recusou a chave ou a permissão. Confira a chave configurada no servidor.'),
    (('RateLimitError', 'OverloadedError', 'EnforcedSpendLimitReachedError', 'ServiceUnavailableError'),
     'limite', 'Limite de uso ou capacidade da API atingido. Tente novamente mais tarde.'),
    (('APIConnectionError', 'APITimeoutError', 'GatewayTimeoutError', 'DeadlineExceededError',
      'RequestTimeoutError'), 'conexao', 'Falha de conexão ou prazo esgotado na API.'),
    (('InternalServerError',), 'servidor', 'Erro temporário no servidor do provedor. Tente novamente.'),
)


def mapear_erro(exc: Exception) -> ErroIA:
    """Classify SDK errors by class name (both SDKs share them) without importing the SDKs."""
    if isinstance(exc, ErroIA):
        return exc
    nomes = {cls.__name__ for cls in type(exc).__mro__}
    for classes, codigo, mensagem in _CODIGOS_SDK:
        if nomes.intersection(classes):
            return ErroIA(f'{mensagem} Detalhe: {seguro(exc)}', codigo=codigo)
    return ErroIA('Falha na API: ' + seguro(exc))


@dataclass(frozen=True)
class Inferencia:
    provedor: str
    modelo: str
    max_tokens: int


@dataclass(frozen=True)
class Resposta:
    """One provider call: text, requested tool calls, token usage and reported model.

    `opaco` holds provider-specific items to replay verbatim in later calls
    (e.g. encrypted reasoning), each tagged {'provedor': name, 'item': {...}}.
    """
    texto: str
    chamadas: tuple = ()
    uso: dict = field(default_factory=dict)
    modelo: str | None = None
    opaco: tuple = ()


def _ajustes(root: Path) -> Path:
    """Choices made in the Mesa override configuracao.json without touching the versioned file."""
    return Path(root) / 'ajustes' / 'inferencia.json'


def ler_inferencia(root: Path) -> Inferencia:
    try:
        config = ler_json(Path(root) / 'configuracao.json')
    except (OSError, ValueError) as exc:
        raise ErroIA('configuracao.json ilegível; não foi possível ler a inferência.') from exc
    if not isinstance(config, dict):
        raise ErroIA('configuracao.json deve conter um objeto JSON.')
    if _ajustes(root).is_file():
        try:
            ajustes = ler_json(_ajustes(root))
        except (OSError, ValueError) as exc:
            raise ErroIA('ajustes/inferencia.json ilegível; salve o provedor novamente na Mesa.') from exc
        if not isinstance(ajustes, dict):
            raise ErroIA('ajustes/inferencia.json deve conter um objeto JSON; salve o provedor novamente na Mesa.')
        config = {**config, **{k: v for k, v in ajustes.items() if k in ('provedor', 'modelo_preferido')}}
    provedor = config.get('provedor')
    if provedor not in MODELOS_PADRAO:
        raise ErroIA('provedor em configuracao.json deve ser "anthropic" ou "openai".')
    modelo = config.get('modelo_preferido')
    if modelo is None:
        modelo = MODELOS_PADRAO[provedor]
    elif not isinstance(modelo, str) or not modelo.strip():
        raise ErroIA('modelo_preferido em configuracao.json deve ser o nome de um modelo ou null.')
    limite = config.get('max_tokens_saida', MAX_TOKENS_PADRAO)
    if type(limite) is not int or limite < 1:
        raise ErroIA('max_tokens_saida em configuracao.json deve ser um inteiro positivo.')
    return Inferencia(provedor, modelo.strip(), limite)


def resumo_inferencia(root: Path) -> dict:
    """What the settings panel may show: never a key, only presence and its last four characters."""
    inferencia = ler_inferencia(root)
    ajustes = ler_json(_ajustes(root)) if _ajustes(root).is_file() else {}
    import custo
    try:
        permitidos = custo.modelos_permitidos(root)
    except ValueError:
        permitidos = []  # the question says why; the panel still shows the rest
    return {'provedor': inferencia.provedor, 'modelo': inferencia.modelo,
            'modelo_preferido': ajustes.get('modelo_preferido') if 'modelo_preferido' in ajustes else None,
            'max_tokens_saida': inferencia.max_tokens, 'modelos_padrao': dict(MODELOS_PADRAO),
            'modelos_permitidos': permitidos, 'chaves': segredos.resumo(root)}


def salvar_inferencia(root: Path, dados: dict) -> dict:
    """Validate everything first, then save the key (if any) and the provider/model choice."""
    if not isinstance(dados, dict) or set(dados) - {'provedor', 'modelo_preferido', 'chave', 'remover_chave'}:
        raise ValueError('Campos de configuração inválidos.')
    provedor = dados.get('provedor')
    if provedor not in MODELOS_PADRAO:
        raise ValueError('Escolha o provedor: Anthropic ou OpenAI.')
    modelo = dados.get('modelo_preferido')
    if modelo is not None and (not isinstance(modelo, str) or not modelo.strip() or len(modelo) > 100):
        raise ValueError('Modelo inválido: informe o nome do modelo ou deixe em branco para o padrão.')
    chave = dados.get('chave')
    if chave not in (None, '') and (not isinstance(chave, str) or not segredos.FORMATO.fullmatch(chave.strip())):
        raise ValueError('Chave de API em formato inválido: cole somente a chave, sem espaços (20 a 300 caracteres).')
    if type(dados.get('remover_chave', False)) is not bool:
        raise ValueError('Indicação de remoção da chave inválida.')
    import custo
    # Only a model of the installation's list, which always has a price (CUS-03); nothing saved otherwise.
    custo.conferir_modelo(root, provedor, modelo.strip() if modelo else MODELOS_PADRAO[provedor])
    if chave:
        segredos.salvar_chave(root, provedor, chave)
    elif dados.get('remover_chave'):
        segredos.remover_chave(root, provedor)
    destino = _ajustes(root)
    destino.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {'provedor': provedor, 'modelo_preferido': modelo.strip() if modelo else None}
    _atomico(destino, (json.dumps(conteudo, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return resumo_inferencia(root)


def criar_provedor_padrao(inferencia: Inferencia, chave: str):
    if inferencia.provedor == 'anthropic':
        from provedor_anthropic import ProvedorAnthropic
        return ProvedorAnthropic(chave)
    from provedor_openai import ProvedorOpenAI
    return ProvedorOpenAI(chave)


def _imagem(url: str) -> dict | None:
    match = re.fullmatch(r'data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=]+)', url or '')
    return {'mime': match.group(1), 'dados': match.group(2)} if match else None


class _Thread:
    def __init__(self, identifier, arquivo, ferramentas, mensagens=None, provedor=None):
        self.id = identifier
        self.provedor = provedor
        self.arquivo = arquivo
        self.ferramentas = ferramentas
        self.mensagens = mensagens or []
        self.instrucoes = ''
        self.modelo = None
        self.turno = None
        self.cancelar = threading.Event()
        self.ocioso = threading.Event()  # set when no worker is running for this thread
        self.ocioso.set()

    def persistir(self):
        mensagens = [dict(m, imagens=[]) if m.get('imagens') else m for m in self.mensagens]
        conteudo = {'versao': 1, 'thread': self.id, 'provedor': self.provedor,
                    'ferramentas': self.ferramentas, 'mensagens': mensagens}
        _atomico(self.arquivo, (json.dumps(conteudo, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


class ServidorAPI:
    """Drop-in for the former app-server transport, backed by a provider API."""

    def __init__(self, root, callback, *, criar_provedor=criar_provedor_padrao):
        self.root = Path(root).resolve()
        self.callback = callback
        self.criar_provedor = criar_provedor
        self.version = VERSAO
        self.closed = False
        self.lock = threading.RLock()
        self.threads = {}
        self.pendentes = {}
        ler_inferencia(self.root)

    # -- protocol -----------------------------------------------------------
    def call(self, method, params=None, timeout=None):
        params = params or {}
        if self.closed:
            raise ErroIA('Conexão com a API encerrada. Tente novamente.', codigo='conexao')
        handlers = {'account/read': self._conta, 'model/list': self._catalogo,
                    'config/read': lambda p: {'config': {}}, 'thread/start': self._iniciar,
                    'thread/resume': self._retomar, 'turn/start': self._turno,
                    'turn/interrupt': self._interromper}
        if method not in handlers:
            raise ErroIA(f'Método não suportado pela integração de API: {method}')
        return handlers[method](params)

    def send(self, message):
        with self.lock:
            answer = self.pendentes.get(message.get('id'))
        if answer is not None:
            try:
                answer.put_nowait(message)
            except queue.Full:
                pass

    def close(self):
        with self.lock:
            self.closed = True
            threads = list(self.threads.values())
            pendentes = list(self.pendentes.values())
        for thread in threads:
            thread.cancelar.set()
        for answer in pendentes:
            try:
                answer.put_nowait({'error': {'message': 'Servidor encerrado.'}})
            except queue.Full:
                pass

    # -- account and catalog ------------------------------------------------
    def _chave(self, provedor):
        """Environment variable first, then the key saved from the Mesa."""
        return segredos.ler_chave(self.root, provedor) or ''

    def _conta(self, params):
        inferencia = ler_inferencia(self.root)
        if not self._chave(inferencia.provedor):
            return {'account': None}
        conta = {'type': 'api', 'provedor': inferencia.provedor, 'modelo': inferencia.modelo}
        import custo
        try:  # a model outside the installation's list is refused before any question (CUS-03)
            custo.conferir_modelo(self.root, inferencia.provedor, inferencia.modelo)
        except ValueError as exc:
            conta['recusa_modelo'] = str(exc)
        return {'account': conta}

    def _catalogo(self, params):
        modelo = ler_inferencia(self.root).modelo
        return {'data': [{'model': modelo, 'isDefault': True}], 'nextCursor': None}

    # -- threads ------------------------------------------------------------
    def _arquivo(self, cwd):
        pasta = Path(cwd or '').resolve()
        conversas = self.root / 'conversas'
        if pasta.parent.parent != conversas or pasta.name != 'workspace':
            raise ErroIA('O workspace da thread deve ficar em conversas/<id>/workspace.')
        return pasta.parent / HISTORICO

    def _preparar(self, thread, params):
        thread.instrucoes = params.get('developerInstructions') or ''
        thread.modelo = params.get('model') or ler_inferencia(self.root).modelo
        with self.lock:
            self.threads[thread.id] = thread
        return {'thread': {'id': thread.id}, 'model': thread.modelo}

    def _iniciar(self, params):
        arquivo = self._arquivo(params.get('cwd'))
        ferramentas = [{'name': t['name'], 'description': t.get('description', ''),
                        'parameters': t.get('inputSchema') or {'type': 'object', 'properties': {}}}
                       for t in params.get('dynamicTools') or []]
        thread = _Thread(uuid.uuid4().hex, arquivo, ferramentas, provedor=ler_inferencia(self.root).provedor)
        thread.persistir()
        return self._preparar(thread, params)

    def _retomar(self, params):
        arquivo = self._arquivo(params.get('cwd'))
        with self.lock:
            existente = self.threads.get(params.get('threadId'))
        if existente is not None and existente.arquivo == arquivo:
            # Same process: keep the live object so a cancelled worker cannot overwrite a newer history.
            self._mesmo_provedor(existente.provedor)
            self._aparar_turno_incompleto(existente)
            return self._preparar(existente, params)
        try:
            dados = ler_json(arquivo)
        except FileNotFoundError as exc:
            raise ErroIA('Esta conversa não tem histórico da integração de API (foi criada com a integração '
                         'anterior ou o histórico se perdeu). Abra uma nova conversa.') from exc
        except (OSError, ValueError) as exc:
            raise ErroIA('Não foi possível ler o histórico desta conversa na API.') from exc
        if dados.get('thread') != params.get('threadId'):
            raise ErroIA('O histórico da conversa não corresponde à thread solicitada.')
        atual = self._mesmo_provedor(dados.get('provedor'))
        thread = _Thread(dados['thread'], arquivo, dados.get('ferramentas') or [], dados.get('mensagens') or [],
                         provedor=atual)
        self._aparar_turno_incompleto(thread)
        return self._preparar(thread, params)

    def _aparar_turno_incompleto(self, thread):
        """Resuming after a failure: drop trailing user prompts that never got a reply.

        A turn that failed before the provider answered leaves its prompt at the end of the history;
        the retry sends the prompt again, and two consecutive user messages are not a valid history."""
        with self.lock:
            if thread.turno is not None or not thread.ocioso.is_set():
                return
            while thread.mensagens and thread.mensagens[-1].get('papel') == 'usuario':
                thread.mensagens.pop()
            thread.persistir()

    def _mesmo_provedor(self, provedor_da_conversa):
        atual = ler_inferencia(self.root).provedor
        if provedor_da_conversa != atual:
            raise ErroIA(f'Esta conversa foi iniciada com o provedor {provedor_da_conversa}; a configuração '
                         f'atual usa {atual}. Abra uma nova conversa para trocar de provedor.')
        return atual

    def _thread(self, identifier):
        with self.lock:
            thread = self.threads.get(identifier)
        if thread is None:
            raise ErroIA('Thread desconhecida; inicie ou retome a conversa.')
        return thread

    # -- turns --------------------------------------------------------------
    def _turno(self, params):
        thread = self._thread(params.get('threadId'))
        texto = '\n'.join(item.get('text', '') for item in params.get('input') or [] if item.get('type') == 'text')
        with self.lock:
            if thread.turno is not None and not thread.cancelar.is_set():
                raise ErroIA('Já há um turno em andamento nesta conversa.')
        # A cancelled worker may still be inside a provider call; never run two workers on one history.
        if not thread.ocioso.wait(ESPERA_ENCERRAMENTO):
            raise ErroIA('O turno anterior ainda está sendo encerrado pela API. Tente novamente em instantes.',
                         codigo='ocupado')
        with self.lock:
            if thread.turno is not None or not thread.ocioso.is_set():
                raise ErroIA('Já há um turno em andamento nesta conversa.')
            turno = uuid.uuid4().hex
            thread.turno = turno
            thread.ocioso.clear()
            thread.cancelar.clear()
            thread.mensagens.append({'papel': 'usuario', 'texto': texto})
        threading.Thread(target=self._executar, args=(thread, turno), daemon=True).start()
        return {'turn': {'id': turno, 'status': 'inProgress'}}

    def _interromper(self, params):
        thread = self._thread(params.get('threadId'))
        with self.lock:
            if params.get('turnId') and params['turnId'] != thread.turno:
                return {}  # late interrupt for a finished turn must not cancel a newer one
            thread.cancelar.set()
        with self.lock:
            pendentes = [a for k, a in self.pendentes.items() if k.startswith(thread.id)]
        for answer in pendentes:
            try:
                answer.put_nowait({'error': {'message': 'Interrompido.'}})
            except queue.Full:
                pass
        return {}

    def _emitir(self, method, thread, **params):
        if self.closed:
            return
        try:
            self.callback({'method': method, 'params': {'threadId': thread.id, **params}})
        except Exception:  # noqa: BLE001 - a backend recording failure must not stall the provider turn
            pass

    def _executar(self, thread, turno):
        status, erro = 'completed', None
        try:
            self._emitir('turn/started', thread, turn={'id': turno})
            status = self._laco(thread, turno)
        except ErroIA as exc:
            status, erro = 'failed', {'message': seguro(exc), 'codexErrorInfo': exc.codigo}
        except Exception as exc:  # provider SDK bugs must not leave the turn hanging
            status, erro = 'failed', {'message': 'Falha inesperada na API: ' + seguro(exc), 'codexErrorInfo': None}
        try:
            self._fechar_chamadas(thread)
            for mensagem in thread.mensagens:
                if mensagem.get('imagens'):
                    mensagem['imagens'] = []
            thread.persistir()
        except Exception as exc:  # noqa: BLE001 - reported to the backend as a failed turn
            status, erro = 'failed', {'message': 'Falha ao salvar o histórico da conversa: ' + seguro(exc),
                                      'codexErrorInfo': 'historico'}
        finally:
            with self.lock:
                thread.turno = None
            turn = {'id': turno, 'status': status}
            if erro:
                turn['error'] = erro
            self._emitir('turn/completed', thread, turn=turn)
            thread.ocioso.set()

    def _laco(self, thread, turno):
        inferencia = ler_inferencia(self.root)
        chave = self._chave(inferencia.provedor)
        if not chave:
            raise ErroIA(f'Chave de API ausente para {inferencia.provedor}: cole a chave em Perguntar à IA › '
                         f'Conexão e opções, ou defina {CHAVES[inferencia.provedor]} no ambiente do servidor.',
                         codigo='autenticacao')
        provedor = self.criar_provedor(inferencia, chave)
        for passo in range(MAX_PASSOS):
            if thread.cancelar.is_set():
                return 'interrupted'
            item = f'{turno}-{passo}'
            resposta = provedor.gerar(
                modelo=thread.modelo, instrucoes=thread.instrucoes, historico=thread.mensagens,
                ferramentas=thread.ferramentas, max_tokens=inferencia.max_tokens,
                ao_texto=lambda delta, item=item: self._emitir('item/agentMessage/delta', thread,
                                                                itemId=item, delta=delta),
                cancelado=thread.cancelar.is_set)
            chamadas = [dict(c) for c in resposta.chamadas]
            mensagem = {'papel': 'assistente', 'texto': resposta.texto}
            if chamadas:
                mensagem['chamadas'] = chamadas
            if resposta.opaco:
                mensagem['opaco'] = [dict(item) for item in resposta.opaco]
            thread.mensagens.append(mensagem)
            if resposta.texto:
                self._emitir('item/completed', thread, item={'type': 'agentMessage', 'id': item,
                                                             'text': resposta.texto})
            self._emitir('item/usage', thread, turnId=turno, uso=dict(resposta.uso),
                         modelo=resposta.modelo or thread.modelo)
            if thread.cancelar.is_set():
                return 'interrupted'
            if not chamadas:
                return 'completed'
            for chamada in chamadas:
                if thread.cancelar.is_set():
                    return 'interrupted'
                thread.mensagens.append(self._ferramenta(thread, turno, chamada))
                self._podar_imagens(thread)
        raise ErroIA(f'Limite de {MAX_PASSOS} passos por etapa atingido sem resposta final.', codigo='passos')

    def _ferramenta(self, thread, turno, chamada):
        chave = f'{thread.id}:{uuid.uuid4().hex}'
        answer = queue.Queue(maxsize=1)
        with self.lock:
            self.pendentes[chave] = answer
        try:
            if self.closed or thread.cancelar.is_set():
                # Checked after registration so close()/interrupt cannot slip between check and wait.
                message = {'error': {'message': 'Interrompido.'}}
            else:
                try:
                    self.callback({'id': chave, 'method': 'item/tool/call', 'params': {
                        'threadId': thread.id, 'turnId': turno, 'callId': chamada['id'],
                        'tool': chamada['nome'], 'arguments': chamada['argumentos']}})
                    message = answer.get(timeout=ESPERA_FERRAMENTA)
                except queue.Empty:
                    message = {'error': {'message': 'A ferramenta não respondeu a tempo.'}}
                except Exception as exc:  # noqa: BLE001 - the model gets the failure as a tool error
                    message = {'error': {'message': 'Falha ao executar a ferramenta: ' + seguro(exc)}}
        finally:
            with self.lock:
                self.pendentes.pop(chave, None)
        if 'error' in message:
            return {'papel': 'ferramenta', 'id': chamada['id'], 'texto': seguro(message['error'].get('message')),
                    'erro': True, 'imagens': []}
        result = message.get('result') or {}
        textos, imagens = [], []
        for item in result.get('contentItems') or []:
            if item.get('type') == 'inputText':
                textos.append(item.get('text', ''))
            elif item.get('type') == 'inputImage' and (imagem := _imagem(item.get('imageUrl'))):
                imagens.append(imagem)
        return {'papel': 'ferramenta', 'id': chamada['id'], 'texto': '\n'.join(textos),
                'erro': not result.get('success', False), 'imagens': imagens}

    @staticmethod
    def _podar_imagens(thread):
        """Keep only the most recent page images in the context sent to the provider (cost and size cap)."""
        vistas = 0
        for mensagem in reversed(thread.mensagens):
            if mensagem.get('imagens'):
                vistas += 1
                if vistas > MAX_IMAGENS_CONTEXTO:
                    mensagem['imagens'] = []
                    mensagem['texto'] = (mensagem.get('texto') or '') + \
                        '\n[imagem retirada do contexto para limitar o tamanho; releia a página se precisar dela]'

    @staticmethod
    def _fechar_chamadas(thread):
        """Every requested call gets a result, so the next turn is a valid provider history."""
        respondidas = {m['id'] for m in thread.mensagens if m.get('papel') == 'ferramenta'}
        for mensagem in list(thread.mensagens):
            for chamada in mensagem.get('chamadas') or []:
                if chamada['id'] not in respondidas:
                    thread.mensagens.append({'papel': 'ferramenta', 'id': chamada['id'], 'erro': True,
                                             'texto': 'Chamada não executada: turno interrompido.', 'imagens': []})
                    respondidas.add(chamada['id'])
