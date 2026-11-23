"""Registro de auditoria da Mesa hospedada (SEG-02): uma linha JSON por evento, sem conteúdo.

O que entra: autenticação (entrada ok e falha, saída, sessão expirada, senha definida, ativação recusada), administração
(conta criada, desativada, reativada, acesso alterado, recuperação, primeiro administrador, acesso negado com o motivo ou
operação recusada), redações, apurações e participações (contrato de contas) e downloads de originais e exportações.
O motivo de um acesso negado e o id da redação (`organizacao`, nunca o nome) ficam só neste registro, que só o operador lê:
nada daqui volta em resposta nem aparece na atividade da equipe. Cada linha leva horário UTC, evento, resultado, conta, IP e os poucos campos
permitidos abaixo.

O que NUNCA entra, por construção: só campos de uma lista fechada são aceitos e cada valor passa por um formato estrito
(identificadores curtos, números, nomes de evento e de motivo de listas fixas). Texto livre, nome de documento ou de
arquivo, pergunta, senha, token, cookie, chave e nome de caso não cabem nesses formatos e são descartados. Para poder
correlacionar sem expor o texto, o login tentado (quando a conta não existe) e o caso de um download entram como
referência: os 12 primeiros caracteres de um HMAC-SHA256 com uma chave aleatória que só existe neste volume.

Onde: `<pasta>/auditoria-AAAA-MM-DD.jsonl` (um arquivo por dia UTC), em `VLADO_REGISTRO` (padrão `<raiz de dados>/registro`,
que o modo local também cria; no Compose, o volume `registro`, que o serviço de backup NÃO monta). Retenção
`VLADO_REGISTRO_RETENCAO_DIAS` (padrão 30, o mesmo do registro do Caddy). IP é dado pessoal: trate como o registro do Caddy.

Tamanho, sem dar a um anônimo o poder de apagar a auditoria: o teto por dia `VLADO_REGISTRO_DIA_MAX_MB` (padrão 50) vale só para
os eventos que qualquer um na internet consegue gerar sem conta (`login_falha` e `ativacao_falha`); passado o teto eles são
descartados e o dia grava um aviso `registro_cheio` (classe `anonimo`). Entrada com sucesso, administração, downloads e os demais
eventos têm cota própria, 4 vezes maior (teto total, aviso `registro_cheio` com classe `total`), e continuam gravando com o dia
"cheio" de falhas. Além disso, as falhas repetidas do mesmo IP acima do limite de tentativas viram UMA linha agregada por IP e por
minuto, com a contagem (`quantidade`), em vez de uma por pedido.

A chave das referências fica FORA do volume do registro: em `segredos/registro_ref.chave` (o serviço de backup não monta `segredos/`
e o backup comum não o inclui). Quem copiar só o volume do registro não consegue conferir palpites de senha ou de caso.

O registro nunca derruba um pedido: erro ao gravar vira um aviso (sem conteúdo) no log do processo, no máximo um por minuto.
Guia: deploy/MONITORAMENTO.md e deploy/INCIDENTE.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import atexit
import secrets
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
RETENCAO_PADRAO_DIAS = 30
DIA_MAX_MB_PADRAO = 50
FATOR_TETO_TOTAL = 4   # cota dos eventos que não são falha anônima: 4 x o teto do dia
PREFIXO = 'auditoria-'
SUFIXO = '.jsonl'
ARQUIVO_DIA = re.compile(r'auditoria-(\d{4}-\d{2}-\d{2})\.jsonl')
log = logging.getLogger('vlado.auditoria')

EVENTOS = frozenset({
    # autenticação
    'login_ok', 'login_falha', 'login_bloqueado', 'logout', 'sessao_expirada', 'senha_definida', 'ativacao_falha',
    # administração
    'conta_criada', 'conta_desativada', 'conta_reativada', 'acesso_alterado', 'recuperacao_emitida', 'primeiro_admin',
    # operacao_negada: nome antigo da recusa, mantido para as linhas antigas e o tipo_original; o contrato grava acesso_negado
    'operacao_negada', 'acesso_negado', 'admin_recusada', 'migracao_v1', 'migracao_contas',
    # redações, apurações e contas (contrato de contas, Onda 2, entregas E1 a E4)
    'redacao_criada', 'redacao_suspensa', 'redacao_reativada', 'redacao_encerrada', 'chave_redacao_alterada',
    'caso_criado', 'caso_atribuido', 'participacao_incluida', 'participacao_retirada', 'responsavel_alterado',
    'senha_trocada', 'senha_redefinida', 'papel_alterado', 'teto_alterado', 'conta_atualizada', 'conta_excluida',
    'conta_exportada', 'conta_expirada', 'sessao_encerrada_a_distancia',
    'convite_enviado', 'convite_reenviado', 'convite_cancelado', 'convite_aceito',
    'fator_ativado', 'fator_removido', 'fator_recusado', 'codigo_reserva_usado',
    'recuperacao_pedida', 'recuperacao_confirmada', 'termos_aceitos',
    # convite, e-mail, redefinição e troca de e-mail (E3); segundo fator, entrada em dois passos e ciclo de vida (E4)
    'convite_expirado', 'redefinicao_pedida', 'email_troca_pedida', 'email_trocado', 'email_enviado', 'email_falhou',
    'aparelho_novo', 'login_protegido', 'fator_codigos_gerados', 'conta_inativa_avisada',
    # a varredura diária desativa a conta inativa (E4b-4, por = manutencao)
    'conta_desativada_por_inatividade',
    # segundo fator (E4): bloqueado por tentativas (atividade); indisponível, sem a chave ou com a semente ilegível
    'fator_bloqueado', 'fator_indisponivel',
    # o segundo fator retirado ao terminar uma recuperação (pelo link de redefinição ou pelo terminal)
    'fator_removido_na_recuperacao',
    # chave de IA própria da redação (contrato 8.5): salva e removida pelo dono; arquivo das chaves ilegível na partida
    'chave_ia_salva', 'chave_ia_removida', 'chaves_ia_ilegiveis',
    # downloads
    'download',
    # pedido recusado por excesso de pedidos em curso do mesmo endereço (429, CONF-03)
    'pedido_recusado',
    # do próprio registro
    'evento_arquivado', 'registro_cheio'})
RESULTADOS = frozenset({'ok', 'falha', 'negado', 'interrompido'})
MOTIVOS = frozenset({'credenciais', 'bloqueado', 'limite_ip', 'expirada', 'inatividade', 'validacao', 'link_invalido',
                     'papel', 'conta_inativa', 'erro', 'nao_encontrado',
                     # por que um acesso foi negado (acesso_negado): só o operador lê este registro
                     'sem_participacao', 'outra_redacao', 'inexistente', 'redacao_suspensa', 'senha_incorreta',
                     'ultimo_dono',
                     # convite e e-mail (E3); segundo fator e ciclo de vida (E4)
                     'link_expirado', 'email_em_uso', 'limite', 'codigo_invalido', 'protegido', 'pendencia',
                     # por que o segundo fator ficou indisponível (fator_indisponivel)
                     'chave_ausente', 'semente_ilegivel'})
TIPOS_DOWNLOAD = frozenset({'original', 'exportacao'})
CODIGOS = frozenset({'operacao_proibida', 'caso_nao_liberado', 'campos_nao_permitidos', 'servico_nao_encerravel',
                     'caso_indisponivel', 'conversa_indisponivel', 'lote_inexistente', 'redacao_suspensa',
                     'pendencia_de_conta', 'operacao_inexistente', 'acesso_indisponivel', 'senha_atual_incorreta',
                     'ultimo_dono', 'senha_necessaria',
                     # convite e e-mail (E3); segundo fator (E4)
                     'convite_duplicado', 'limite_de_convites', 'transporte_indisponivel', 'codigo_invalido',
                     'fator_necessario',
                     # recusas da E3 (recuperacao_pelo_operador vai em admin_recusada; os outros dois, por paridade
                     # com as respostas, mesmo que hoje não cheguem ao registro como código)
                     'recuperacao_pelo_operador', 'link_invalido', 'senha_invalida',
                     # segundo fator indisponível (E4); o padrão de acesso.Recusada, que pode chegar em admin_recusada
                     'fator_indisponivel', 'requisicao_invalida',
                     # pergunta recusada porque a chave de IA da redação não pôde ser lida (P3, C3)
                     'chave_redacao_ilegivel',
                     # excluir a própria conta com o nome digitado diferente (E4b-3, admin_recusada com validacao)
                     'nome_confirmacao_divergente',
                     # teto de exportações da própria conta (E4b-2b, 429, motivo limite, admin_recusada de conta-exportar)
                     'limite_de_exportacoes'})
# Qual e-mail saiu ou falhou (email_enviado, email_falhou): só o tipo, nunca o endereço nem o texto.
MENSAGENS = frozenset({'convite', 'redefinicao', 'novo_acesso', 'senha_trocada', 'fator_alterado', 'recuperacao',
                       'muitas_tentativas', 'email_novo', 'conta_inativa', 'fator_bloqueado'})
# Nomes de operação da API: lista fechada que o servidor registra ao importar (permitir_operacoes). Um nome fora dela
# (um texto qualquer em forma de nome) é descartado.
OPERACOES_PERMITIDAS: set = set()
CAMPOS_DE_ACESSO = frozenset({'nome', 'papel', 'casos', 'cota', 'teto', 'idioma', 'email'})
# Papéis da redação (contrato de contas); admin e convidado ficam para ler as linhas de antes da migração.
PAPEIS = frozenset({'dono', 'editor', 'reporter', 'leitor', 'admin', 'convidado'})
CLIENTES = frozenset({'web', 'android', 'cli'})
OPERACOES_DE_ACESSO = frozenset({'entrar', 'ativar', 'consultar', 'primeiro_admin',
                                 'aceitar', 'redefinir', 'esqueci', 'confirmar_email', 'segundo_fator'})
# Mapeamento dos tipos de evento do cadastro de contas (acesso.json) para os do registro.
DO_ACESSO = {'sessao_encerrada': 'logout'}

_ID = re.compile(r'[0-9a-f]{16}')                  # id de conta (secrets.token_hex(8)): nunca um nome nem um token
# manutencao: a varredura diária (acesso.py manutencao) que vence convites, avisa e desativa conta inativa.
AUTORES = frozenset({'cli', 'migracao', 'primeiro_acesso', 'operador', 'manutencao'})
# Redação: só o id (org + 16 hex, acesso.ID_ORGANIZACAO) ou 'instalacao' (modo sem contas); nunca o nome.
_ORGANIZACAO = re.compile(r'org[0-9a-f]{16}|instalacao')
_OPERACAO = re.compile(r'[a-z0-9-]{1,40}')         # nome de operação da API (lista fechada do servidor)
_REF = re.compile(r'[0-9a-f]{12}')
_DATA = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?')

_CTX = threading.local()
_ESCRITA = threading.Lock()
_ESTADO = {'limpeza': 0.0, 'cheio': set(), 'aviso': 0.0, 'chave': {}}
# Falhas que um anônimo gera à vontade: só elas sofrem o teto do dia e a agregação por IP.
ANONIMOS = frozenset({'login_falha', 'ativacao_falha', 'pedido_recusado'})
_AGREGADOS: dict = {}
_AGREGA = threading.Lock()


# --- contexto da requisição ---------------------------------------------------------------------

def iniciar_requisicao(ip=None, origem: str = 'web', raiz=None) -> None:
    """Chamado no começo de cada requisição: `ip` é uma função sem argumentos (o IP do cliente pela regra de proxy) e
    `raiz` a pasta de dados do servidor (onde fica `registro/` se VLADO_REGISTRO não estiver definida)."""
    _CTX.ip = ip
    _CTX.dados = {'origem': origem}
    if raiz is not None:
        _CTX.raiz = Path(raiz)


def definir(**campos) -> None:
    """Acrescenta ao contexto da requisição: conta, operacao, organizacao (só o id) e caso (só vira referência)."""
    if hasattr(_CTX, 'dados'):
        _CTX.dados.update({k: v for k, v in campos.items() if v is not None})


def encerrar_requisicao() -> None:
    for nome in ('ip', 'dados', 'raiz'):
        _CTX.__dict__.pop(nome, None)


def lembrar_raiz(root) -> None:
    """A raiz de dados em uso por esta thread (para o padrão `<raiz>/registro`)."""
    _CTX.raiz = Path(root)


def _contexto() -> dict:
    return getattr(_CTX, 'dados', None) or {}


def _ip_do_contexto() -> str | None:
    funcao = getattr(_CTX, 'ip', None)
    if funcao is None:
        return None
    try:
        valor = funcao() if callable(funcao) else funcao
        return str(ipaddress.ip_address(str(valor))) if valor else None
    except Exception:  # noqa: BLE001 - an unreadable address is just "no address"
        return None


# --- configuração -------------------------------------------------------------------------------

def pasta() -> Path:
    destino = os.environ.get('VLADO_REGISTRO', '').strip()
    if destino:
        return Path(destino)
    return getattr(_CTX, 'raiz', ROOT) / 'registro'


def _inteiro(nome: str, padrao: int, minimo: int, maximo: int) -> int:
    bruto = os.environ.get(nome, '').strip()
    if not bruto:
        return padrao
    try:
        return max(minimo, min(maximo, int(bruto)))
    except ValueError:
        _avisar(f'{nome} inválida; usando {padrao}.')
        return padrao


def retencao_dias() -> int:
    return _inteiro('VLADO_REGISTRO_RETENCAO_DIAS', RETENCAO_PADRAO_DIAS, 1, 3650)


def dia_max_bytes() -> int:
    return _inteiro('VLADO_REGISTRO_DIA_MAX_MB', DIA_MAX_MB_PADRAO, 1, 10240) * (1 << 20)


def _avisar(mensagem: str) -> None:
    agora = time.monotonic()
    if agora - _ESTADO['aviso'] >= 60:
        _ESTADO['aviso'] = agora
        log.warning('registro de auditoria: %s', mensagem)


# --- referências (HMAC) -------------------------------------------------------------------------

def arquivo_da_chave() -> Path:
    """`segredos/registro_ref.chave` (ao lado de chaves.json): fora do volume do registro e fora do backup comum."""
    explicito = os.environ.get('VLADO_REGISTRO_CHAVE', '').strip()
    if explicito:
        return Path(explicito)
    import segredos
    return segredos.caminho(getattr(_CTX, 'raiz', ROOT)).parent / 'registro_ref.chave'


def _chave(arquivo: Path) -> bytes:
    em_memoria = _ESTADO['chave'].get(str(arquivo))
    if em_memoria:
        return em_memoria
    try:
        bruto = arquivo.read_text(encoding='ascii').strip()
        chave = bytes.fromhex(bruto) if len(bruto) == 64 else b''
    except (OSError, ValueError):
        chave = b''
    if not chave:
        chave = secrets.token_bytes(32)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        descritor = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_BINARY', 0), 0o600)
        with os.fdopen(descritor, 'w', encoding='ascii') as saida:
            saida.write(chave.hex() + '\n')
    _ESTADO['chave'][str(arquivo)] = chave
    return chave


def referencia(espaco: str, valor, arquivo_chave: Path | None = None) -> str | None:
    """12 hex de HMAC-SHA256(chave guardada em segredos/, espaço:valor): correlaciona sem revelar o texto."""
    if not isinstance(valor, str) or not valor:
        return None
    try:
        chave = _chave(arquivo_chave or arquivo_da_chave())
    except OSError:
        return None
    return hmac.new(chave, f'{espaco}:{valor}'.encode('utf-8'), hashlib.sha256).hexdigest()[:12]


# --- validação dos campos -----------------------------------------------------------------------

def _id(valor):
    return valor if isinstance(valor, str) and (_ID.fullmatch(valor) or valor in AUTORES) else None


def _enum(conjunto):
    return lambda valor: valor if isinstance(valor, str) and valor in conjunto else None


def _inteiro_pos(valor):
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor < 1 << 62 else None


def _lista_de_campos(valor):
    if isinstance(valor, (list, tuple)) and valor and all(isinstance(v, str) and v in CAMPOS_DE_ACESSO for v in valor):
        return sorted(set(valor))
    return None


# campo -> validador. Qualquer outro campo é descartado.
CAMPOS = {
    'conta': _id, 'por': _id, 'alvo': _id,
    'motivo': _enum(MOTIVOS), 'tipo': _enum(TIPOS_DOWNLOAD), 'papel': _enum(PAPEIS), 'cliente': _enum(CLIENTES),
    'operacao': lambda v: v if isinstance(v, str) and v in OPERACOES_PERMITIDAS else None,
    'acesso_operacao': _enum(OPERACOES_DE_ACESSO),
    'caso_ref': lambda v: v if isinstance(v, str) and _REF.fullmatch(v) else None,
    'login_ref': lambda v: v if isinstance(v, str) and _REF.fullmatch(v) else None,
    'bytes': _inteiro_pos, 'quantidade': _inteiro_pos, 'codigo': _enum(CODIGOS), 'mensagem': _enum(MENSAGENS),
    'organizacao': lambda v: v if isinstance(v, str) and _ORGANIZACAO.fullmatch(v) else None,
    'campos': _lista_de_campos,
    'tipo_original': lambda v: v if isinstance(v, str) and (v in EVENTOS or v in DO_ACESSO) else None,
    'em_original': lambda v: v if isinstance(v, str) and _DATA.fullmatch(v) else None,
}


def montar(evento: str, resultado: str = 'ok', conta=None, momento: datetime | None = None, **extras) -> dict | None:
    """A linha, já filtrada; None se o evento não existe. Não grava."""
    if evento not in EVENTOS or resultado not in RESULTADOS:
        return None
    momento = (momento or datetime.now(timezone.utc)).astimezone(timezone.utc)
    contexto = _contexto()
    ip_dado = extras.pop('ip', None)  # IP já conhecido de quem chama (entrar); senão o da requisição
    origem = extras.pop('origem', None)
    try:
        ip = str(ipaddress.ip_address(str(ip_dado))) if ip_dado else _ip_do_contexto()
    except ValueError:
        ip = _ip_do_contexto()
    linha = {'em': momento.strftime('%Y-%m-%dT%H:%M:%SZ'), 'evento': evento, 'resultado': resultado,
             'conta': _id(conta), 'ip': ip,
             'origem': origem if origem in ('web', 'cli', 'servidor') else contexto.get('origem', 'cli')}
    campos = {k: v for k, v in {'operacao': contexto.get('operacao'), 'caso_ref': contexto.get('caso_ref'),
                                'organizacao': contexto.get('organizacao'), **extras}.items() if v is not None}
    for nome, valor in campos.items():
        validador = CAMPOS.get(nome)
        limpo = validador(valor) if validador else None
        if limpo is not None:
            linha[nome] = limpo
    return linha


# --- gravação, limite e retenção ----------------------------------------------------------------

def registrar(evento: str, resultado: str = 'ok', conta=None, momento: datetime | None = None, **extras) -> None:
    """Grava uma linha. Nunca levanta: o registro não derruba o pedido."""
    destino = extras.pop('destino', None)  # pasta já resolvida (agregação em outra thread)
    try:
        linha = montar(evento, resultado, conta, momento, **extras)
        if linha is None:
            return
        _gravar(destino or pasta(), linha, momento or datetime.now(timezone.utc))
    except Exception as exc:  # noqa: BLE001 - audit must never break the request
        _avisar(f'não consegui gravar ({type(exc).__name__}).')
    if destino is None:
        descarregar()  # aproveita para fechar as janelas de agregação já vencidas


def registrar_limite_ip(evento: str, ip, chave=None, **extras) -> None:
    """Falha por excesso de tentativas do mesmo IP: UMA linha por IP e por minuto, com a contagem (`quantidade`).

    Sem isso, cada pedido anônimo acima do limite seria uma linha e o dia encheria de ruído. A linha do minuto é gravada quando a
    janela fecha (no próximo evento, na próxima falha ou ao encerrar o processo). `chave` agrupa o IP (para IPv6, a rede /64).
    """
    if evento not in ANONIMOS:
        return
    try:
        momento = datetime.now(timezone.utc)
        minuto = momento.replace(second=0, microsecond=0)
        contexto = _contexto()
        grupo = (evento, str(chave or ip))
        with _AGREGA:
            atual = _AGREGADOS.get(grupo)
            if atual and atual['minuto'] == minuto:
                atual['quantidade'] += 1
                return
            if atual:  # janela anterior deste IP: fecha antes de abrir a nova
                _fechar(grupo, atual)
            _AGREGADOS[grupo] = {'minuto': minuto, 'quantidade': 1, 'ip': ip, 'destino': pasta(),
                                 'origem': contexto.get('origem', 'cli'),
                                 'extras': {**{k: v for k, v in extras.items() if v is not None},
                                            **({'operacao': contexto['operacao']} if contexto.get('operacao') else {})}}
        descarregar()
    except Exception as exc:  # noqa: BLE001
        _avisar(f'não consegui agregar ({type(exc).__name__}).')


def _fechar(grupo, janela) -> None:
    """Grava a linha agregada de uma janela (quem chama segura _AGREGA ou já tirou a janela do dicionário)."""
    _AGREGADOS.pop(grupo, None)
    registrar(grupo[0], 'falha', None, janela['minuto'], motivo='limite_ip', quantidade=janela['quantidade'],
              ip=janela['ip'], origem=janela['origem'], destino=janela['destino'], **janela['extras'])


def descarregar(tudo: bool = False, agora: datetime | None = None) -> int:
    """Fecha as janelas de agregação vencidas (ou todas, ao encerrar). Devolve quantas linhas gravou."""
    momento = (agora or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    fechadas = 0
    with _AGREGA:
        for grupo, janela in list(_AGREGADOS.items()):
            if tudo or janela['minuto'] < momento:
                _fechar(grupo, janela)
                fechadas += 1
    return fechadas


atexit.register(lambda: descarregar(tudo=True))


def referencia_do_login(login) -> str | None:
    """Referência do login digitado quando a conta não existe (nunca o texto: pode ser a senha digitada no campo errado)."""
    return referencia('login', login.strip().lower() if isinstance(login, str) else None)


def referenciar_caso(caso) -> None:
    """Põe a referência do caso do pedido no contexto (o nome do caso não vai para o registro)."""
    ref = referencia('caso', caso) if isinstance(caso, str) else None
    if ref:
        definir(caso_ref=ref)


def _serializar(linha: dict) -> bytes:
    return (json.dumps(linha, ensure_ascii=True, separators=(',', ':')) + '\n').encode('ascii')


def _gravar(destino: Path, linha: dict, momento: datetime) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(destino, 0o700)
    except OSError:
        pass
    arquivo = destino / f'{PREFIXO}{momento.astimezone(timezone.utc):%Y-%m-%d}{SUFIXO}'
    dado = _serializar(linha)
    anonimo = linha['evento'] in ANONIMOS
    # Falha anônima: teto do dia. Todo o resto: cota própria (4x), para que um dia "cheio" de falhas nunca apague a
    # entrada de um administrador nem a criação de uma conta (B1 da revisão).
    teto = dia_max_bytes() if anonimo else dia_max_bytes() * FATOR_TETO_TOTAL
    with _ESCRITA:
        try:
            tamanho = arquivo.stat().st_size
        except FileNotFoundError:
            tamanho = 0
        if tamanho >= teto:
            aviso = (str(arquivo), 'anonimo' if anonimo else 'total')
            if aviso not in _ESTADO['cheio']:
                _ESTADO['cheio'].add(aviso)
                _anexar(arquivo, _serializar({'em': linha['em'], 'evento': 'registro_cheio', 'resultado': 'falha',
                                              'conta': None, 'ip': None, 'origem': 'servidor', 'classe': aviso[1]}))
            return
        _anexar(arquivo, dado)
        _limpar_se_preciso(destino, momento)


def _anexar(arquivo: Path, dado: bytes) -> None:
    descritor = os.open(arquivo, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o600)
    try:
        os.write(descritor, dado)
    finally:
        os.close(descritor)


def _limpar_se_preciso(destino: Path, momento: datetime) -> None:
    """Apaga os arquivos com mais de N dias (no máximo uma varredura por hora e por processo)."""
    agora = time.monotonic()
    if _ESTADO['limpeza'] and agora - _ESTADO['limpeza'] < 3600:
        return
    _ESTADO['limpeza'] = agora
    podar(destino, momento)


def podar(destino: Path | None = None, momento: datetime | None = None) -> list[str]:
    """Remove os arquivos de dias fora da retenção; devolve os nomes removidos."""
    destino = destino or pasta()
    limite = (momento or datetime.now(timezone.utc)).astimezone(timezone.utc).date() - timedelta(days=retencao_dias())
    removidos = []
    try:
        arquivos = list(destino.iterdir())
    except OSError:
        return removidos
    for item in arquivos:
        achado = ARQUIVO_DIA.fullmatch(item.name)
        if not achado:
            continue
        try:
            if datetime.strptime(achado[1], '%Y-%m-%d').date() < limite:
                item.unlink()
                removidos.append(item.name)
                _ESTADO['cheio'].difference_update({(str(item), 'anonimo'), (str(item), 'total')})
        except (OSError, ValueError):
            continue
    return removidos


def arquivos(destino: Path | None = None) -> list[Path]:
    destino = destino or pasta()
    try:
        return sorted(p for p in destino.iterdir() if ARQUIVO_DIA.fullmatch(p.name))
    except OSError:
        return []


# --- ponte com o cadastro de contas (acesso.py) --------------------------------------------------

def do_acesso(tipo: str, conta, por, momento: datetime | None = None, **detalhes) -> None:
    """Um evento do cadastro de contas (`acesso.json`) também vai para o registro, com IP e contexto."""
    evento = DO_ACESSO.get(tipo, tipo)
    if evento not in EVENTOS:
        return
    registrar(evento, 'ok', conta, momento, por=por if por != conta else None, **detalhes)


def arquivar_evento(evento: dict) -> None:
    """Evento que `acesso.json` vai deixar de guardar (passou do limite da janela): guardado aqui, sem aviso silencioso."""
    registrar('evento_arquivado', 'ok', evento.get('conta') if isinstance(evento.get('conta'), str) else None,
              por=evento.get('por') if isinstance(evento.get('por'), str) else None,
              tipo_original=evento.get('tipo'), em_original=evento.get('em'))


# --- leitura para a própria pessoa (exportar meus dados, E4b-2b de Contas) ------------------------------------

# Eventos com a conta preenchida que outra pessoa pode disparar sem provar ser ela (uma senha errada, um pedido de
# redefinição pelo e-mail, um código errado depois da senha) ou que o sistema grava sozinho: o IP ali não é o dela.
SEM_AUTORIA_PROVADA = ANONIMOS | frozenset({'login_bloqueado', 'redefinicao_pedida', 'recuperacao_pedida',
                                            'email_enviado', 'email_falhou', 'fator_recusado', 'fator_bloqueado',
                                            'evento_arquivado', 'registro_cheio'})
MAX_ACESSOS_DA_CONTA = 2000


def acessos_da_conta(root, conta) -> list[dict]:
    """The lines of the audit log the account itself caused, for its own data export: ``{em, evento, resultado}``
    and, when the line has them, ``cliente`` and ``ip`` (its own, as in its sessions). Only lines with ``conta`` equal
    to it, without ``por`` (someone else acting on it: the IP would be theirs) and outside SEM_AUTORIA_PROVADA;
    never alvo, another account, a name or free text. The window the log keeps, oldest first, newest last, at most
    MAX_ACESSOS_DA_CONTA. A last line cut short (a write in progress, or a crash) is skipped; any other line that
    cannot be read raises ValueError, and a folder or file that cannot be read raises OSError: the export says
    then that this part is incomplete."""
    from collections import deque
    if not isinstance(conta, str) or not _ID.fullmatch(conta):
        raise ValueError('Conta inválida para o registro de acesso.')
    destino = os.environ.get('VLADO_REGISTRO', '').strip()
    destino = Path(destino) if destino else Path(root) / 'registro'
    try:
        nomes = sorted(p for p in destino.iterdir() if ARQUIVO_DIA.fullmatch(p.name))
    except FileNotFoundError:
        return []
    saida = deque(maxlen=MAX_ACESSOS_DA_CONTA)
    for arquivo in nomes:
        with open(arquivo, 'rb') as f:  # line by line: a day of the log may be large
            for bruta in f:
                if not bruta.strip():
                    continue
                try:
                    linha = json.loads(bruta)
                    if not isinstance(linha, dict):
                        raise ValueError
                except ValueError:
                    if not bruta.endswith(b'\n'):  # the last one, cut short: not a line of the log yet
                        continue
                    raise ValueError(f'Linha ilegível no registro de acesso ({arquivo.name}).') from None
                item = _acesso_da_conta(linha, conta)
                if item is not None:
                    saida.append(item)
    return list(saida)


def _acesso_da_conta(linha: dict, conta: str) -> dict | None:
    if (linha.get('conta') != conta or 'por' in linha or linha.get('evento') not in EVENTOS
            or linha['evento'] in SEM_AUTORIA_PROVADA or linha.get('resultado') not in RESULTADOS
            or not isinstance(linha.get('em'), str) or not _DATA.fullmatch(linha['em'])):
        return None
    item = {'em': linha['em'], 'evento': linha['evento'], 'resultado': linha['resultado']}
    if linha.get('cliente') in CLIENTES:
        item['cliente'] = linha['cliente']
    if isinstance(linha.get('ip'), str):
        try:
            item['ip'] = str(ipaddress.ip_address(linha['ip']))
        except ValueError:
            pass
    return item


def permitir_operacoes(nomes) -> None:
    """O servidor informa os nomes de operação que existem; só eles entram no campo `operacao`."""
    OPERACOES_PERMITIDAS.update(n for n in nomes if isinstance(n, str) and _OPERACAO.fullmatch(n))


def valor_do_contexto(nome: str):
    """Um valor guardado no contexto da requisição (conta, operacao), ou None."""
    return _contexto().get(nome)
