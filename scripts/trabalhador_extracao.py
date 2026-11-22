"""Processo de extração da fila da Mesa (CONF-02), isolado (SEG-01). Não é para uso direto.

Um processo por arquivo: lê uma tarefa pela entrada padrão (uma linha JSON), responde pela
saída padrão (uma linha JSON por mensagem) e termina. Nada de um arquivo passa para o próximo.

    entrada  {"tarefa": {...}, "base": "<pasta do lote>", "paralelo": 2}
             {"renderizar": {"pdf": "<caminho>", "pagina": 3}}   (página como imagem, para o modelo)
    saída    {"tipo": "limites", "aplicado": {...}}               (o que o sistema aceitou, na partida)
             {"tipo": "progresso", "fase": "texto|orientacao|reconhecimento|paginas", "feitas": N, "total": M}
             {"tipo": "resultado", "resultado": {...}, "derivado": "derivados/3/....md" | null, "teto"?: "..."}
             {"tipo": "imagem", "png": "<base64>"}
             {"tipo": "limite", "mensagem": "..."}                (teto de CPU: o processo termina em seguida)
             {"tipo": "erro", "mensagem": "..."}

A extração é ``cadastrar_documentos.extrair_item``, a mesma da linha de comando, com os tetos de
páginas e pixels de ``tetos_extracao``. Este processo só lê o original e escreve a cópia de
trabalho na pasta do lote: não abre manifesto, catálogo nem trava. Qualquer outra coisa escrita na
saída padrão (avisos de bibliotecas) vai para a saída de erro.

**Isolamento** (``aplicar_limites``, antes de qualquer outra coisa, inclusive das threads):

- Windows: um Job Object com teto de memória do processo e dos filhos somados, teto de CPU de
  usuário do conjunto (reserva do vigia), afinidade sem o núcleo 0, prioridade abaixo do normal,
  limite de processos e morte dos filhos quando este processo acaba. Sem bloqueio de rede pelo
  sistema (exige administrador ou AppContainer): a rede é bloqueada no Python deste processo; o
  OCRmyPDF, o Tesseract e o Ghostscript não abrem conexão.
- Linux: ``RLIMIT_AS`` (memória por processo, herdada por cada filho), ``RLIMIT_CPU`` (reserva do
  vigia), sem core dump, afinidade sem o núcleo 0, ``nice`` 10 e um filtro seccomp que recusa
  sockets de rede (IPv4, IPv6, pacote, netlink), io_uring e qualquer chamada pela interface de
  outra arquitetura (no x86_64, a de 32 bits), herdado pelos filhos; sockets Unix ficam
  permitidos. Sem o filtro, a fila registra o aviso. Teto de memória do conjunto e da Mesa,
  ``read_only``, ``cap_drop`` e rede do contêiner dependem do Compose.
- Nos dois: a rede é recusada também no módulo ``socket`` do Python, e um vigia de CPU encerra o
  processo, com motivo claro, quando o arquivo passa do teto de segundos de CPU (deste processo e
  dos filhos que já terminaram). O tempo de relógio é da fila.

Termina com a tarefa feita, com a entrada fechada, morto pela fila (prazo) ou quando a Mesa que o
abriu morre (vigia), levando os filhos junto: no Windows pelo Job Object (``proc.kill()`` da fila,
vigia ou queda); no Linux ele é líder do próprio grupo (a fila o abre com ``start_new_session``), e
o vigia e a fila matam o grupo.
"""
import base64
import errno
import json
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tetos_extracao as tetos  # noqa: E402

MARGEM_CPU_SISTEMA = 15  # seconds past the CPU cap before the system cap (the vigia speaks first)
PROCESSOS_NO_JOB = 64
_JOB = None  # Windows: the job handle, open for this process's whole life (its children die with it)
MENSAGEM_REDE = 'Rede bloqueada no processo de extração (SEG-01).'


# --- isolamento ----------------------------------------------------------------------------------

def _nucleos_escolhidos(disponiveis, quantos):
    """The cores to use: without the first one (left to the Mesa) when there is more than one."""
    disponiveis = sorted(disponiveis)
    if len(disponiveis) > 1:
        disponiveis = disponiveis[1:]
    return disponiveis[:max(1, quantos)]


def _limites_windows(config):
    global _JOB
    import ctypes
    from ctypes import wintypes

    class Basico(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD)]

    class Contadores(ctypes.Structure):
        _fields_ = [(nome, ctypes.c_uint64) for nome in ('Read', 'Write', 'Other', 'ReadBytes', 'WriteBytes', 'OtherBytes')]

    class Estendido(ctypes.Structure):
        _fields_ = [('Basic', Basico), ('Io', Contadores), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t),
                    ('PeakJobMemoryUsed', ctypes.c_size_t)]

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t),
                                           ctypes.POINTER(ctypes.c_size_t)]
    aplicado = {'memoria': None, 'cpu': None, 'nucleos': None, 'prioridade': None,
                'filhos': 'encerrados com o processo' if _JOB is not None else None}
    processo = k32.GetCurrentProcess()
    mascara, sistema = ctypes.c_size_t(), ctypes.c_size_t()
    nucleos = None
    if k32.GetProcessAffinityMask(processo, ctypes.byref(mascara), ctypes.byref(sistema)):
        nucleos = _nucleos_escolhidos([n for n in range(ctypes.sizeof(ctypes.c_size_t) * 8)
                                       if mascara.value >> n & 1], config['nucleos'])
    novo = _JOB is None  # juntar_filhos may already have put this process in its job
    job = k32.CreateJobObjectW(None, None) if novo else _JOB
    if not job:
        return {**aplicado, 'falha': f'CreateJobObject: {ctypes.get_last_error()}'}
    info = Estendido()
    flags = 0x2000 | 0x400 | 0x200 | 0x8 | 0x20 | 0x4  # kill on close, no error dialog, job memory, processes, priority, job time
    info.Basic.PerJobUserTimeLimit = (config['cpu_s'] + MARGEM_CPU_SISTEMA) * 10_000_000
    info.JobMemoryLimit = config['memoria_mb'] * 1024 * 1024
    info.Basic.ActiveProcessLimit = PROCESSOS_NO_JOB
    info.Basic.PriorityClass = 0x4000  # BELOW_NORMAL_PRIORITY_CLASS
    if nucleos:
        flags |= 0x10  # affinity
        info.Basic.Affinity = sum(1 << n for n in nucleos)
    info.Basic.LimitFlags = flags
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):  # extended limits
        aplicado['falha'] = f'SetInformationJobObject: {ctypes.get_last_error()}'
        if novo:
            k32.CloseHandle(job)
            juntar_filhos()  # at least the children still die with this process
            aplicado['filhos'] = 'encerrados com o processo' if _JOB is not None else None
        return aplicado
    if novo and not k32.AssignProcessToJobObject(job, processo):
        aplicado['falha'] = f'AssignProcessToJobObject: {ctypes.get_last_error()}'
        k32.CloseHandle(job)
        return aplicado
    _JOB = job
    return {'memoria': f'job {config["memoria_mb"]} MB (processo e filhos)',
            'cpu': f'vigia {config["cpu_s"]} s; job {config["cpu_s"] + MARGEM_CPU_SISTEMA} s de usuário',
            'nucleos': nucleos, 'prioridade': 'abaixo do normal', 'filhos': 'encerrados com o processo'}


def _limites_posix(config):
    import resource
    aplicado = {'memoria': None, 'cpu': None, 'nucleos': None, 'prioridade': None,
                'filhos': 'encerrados com o processo (grupo próprio)'}
    memoria = config['memoria_mb'] * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memoria, memoria))
        aplicado['memoria'] = f'RLIMIT_AS {config["memoria_mb"]} MB por processo'
    except (OSError, ValueError) as exc:
        aplicado['falha_memoria'] = str(exc)
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (config['cpu_s'] + MARGEM_CPU_SISTEMA,
                                                 config['cpu_s'] + 2 * MARGEM_CPU_SISTEMA))
        aplicado['cpu'] = f'vigia {config["cpu_s"]} s; RLIMIT_CPU {config["cpu_s"] + MARGEM_CPU_SISTEMA} s'
    except (OSError, ValueError) as exc:
        aplicado['falha_cpu'] = str(exc)
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))  # no core dump of a hostile document
    except (OSError, ValueError):
        pass
    if hasattr(os, 'sched_getaffinity'):
        try:
            nucleos = _nucleos_escolhidos(os.sched_getaffinity(0), config['nucleos'])
            os.sched_setaffinity(0, nucleos)
            aplicado['nucleos'] = nucleos
        except OSError as exc:
            aplicado['falha_nucleos'] = str(exc)
    try:
        os.nice(10)
        aplicado['prioridade'] = 'nice 10'
    except OSError:
        pass
    return aplicado


def _seccomp_sem_rede():
    """Linux: a seccomp filter refusing network sockets and io_uring, for this process and its children.

    Refused: sockets of IPv4, IPv6, packet and netlink families; io_uring (it creates sockets without
    the socket call); x32 calls; and every call through another architecture's interface (on x86_64,
    the 32-bit ``int 0x80`` one, whose socket calls have other numbers). Unix sockets stay allowed
    (OCRmyPDF's worker pool). Returns a description, or None when it cannot be installed (other
    architectures, old kernel).
    """
    import ctypes
    import platform
    import struct
    arquiteturas = {'x86_64': (0xC000003E, 41), 'amd64': (0xC000003E, 41),
                    'aarch64': (0xC00000B7, 198), 'arm64': (0xC00000B7, 198)}
    alvo = arquiteturas.get(platform.machine().lower())
    if alvo is None:
        return None
    arquitetura, socket_nr = alvo
    io_uring_setup, recusa, permite = 425, 0x00050000 | errno.EACCES, 0x7FFF0000
    ld, jeq, jge, ret = 0x20, 0x15, 0x35, 0x06
    # (operation, constant, jump if true, jump if false), jumps by label; resolved below.
    programa = [
        ('arch', ld, 4, None, None), (None, jeq, arquitetura, 'nr', 'recusa'),  # another ABI: refused (S1)
        ('nr', ld, 0, None, None), (None, jge, 0x40000000, 'recusa', None),  # x32 syscalls
        (None, jeq, io_uring_setup, 'recusa', None), (None, jeq, socket_nr, 'familia', 'permite'),
        ('familia', ld, 16, None, None), (None, jeq, 2, 'recusa', None),  # AF_INET
        (None, jeq, 10, 'recusa', None), (None, jeq, 16, 'recusa', None),  # AF_INET6, AF_NETLINK
        (None, jeq, 17, 'recusa', 'permite'),  # AF_PACKET
        ('permite', ret, permite, None, None), ('recusa', ret, recusa, None, None)]
    rotulos = {r[0]: i for i, r in enumerate(programa) if r[0]}
    codigo = b''
    for i, (_, op, k, verdadeiro, falso) in enumerate(programa):
        salto = lambda destino: 0 if destino is None else rotulos[destino] - i - 1  # noqa: E731
        codigo += struct.pack('HBBI', op, salto(verdadeiro), salto(falso), k)

    class Programa(ctypes.Structure):
        _fields_ = [('len', ctypes.c_ushort), ('filter', ctypes.c_void_p)]
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.restype = ctypes.c_int
    libc.prctl.argtypes = [ctypes.c_int] + [ctypes.c_ulong] * 4  # variadic: no stray high bits
    filtro = ctypes.create_string_buffer(codigo)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        return None
    prog = Programa(len(programa), ctypes.cast(filtro, ctypes.c_void_p))
    if libc.prctl(22, 2, ctypes.addressof(prog), 0, 0) != 0:  # PR_SET_SECCOMP, SECCOMP_MODE_FILTER
        return None
    return ('seccomp: sockets IPv4, IPv6, de pacote e netlink, io_uring e chamadas de outra arquitetura '
            'recusados, também nos filhos; sockets Unix permitidos')


def _bloquear_socket_python():
    """Network refused to Python code of this process (``socket`` and ``_socket``)."""
    import _socket
    import socket
    redes = {socket.AF_INET, getattr(socket, 'AF_INET6', socket.AF_INET)}

    def sem_rede(base):
        class SocketSemRede(base):
            def __init__(self, family=-1, type=-1, proto=-1, fileno=None):
                if fileno is None and (socket.AF_INET if family == -1 else family) in redes:
                    raise PermissionError(errno.EACCES, MENSAGEM_REDE)
                # The base by name, not super(): socket.socket calls _socket.socket.__init__(self, ...)
                # on its own instances, which are not of this subclass (Unix sockets stay usable).
                base.__init__(self, family, type, proto, fileno)
        return SocketSemRede

    def recusar(*_args, **_kwargs):
        raise PermissionError(errno.EACCES, MENSAGEM_REDE)
    socket.socket = sem_rede(socket.socket)
    _socket.socket = sem_rede(_socket.socket)
    for modulo in (socket, _socket):
        for nome in ('create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr'):
            if hasattr(modulo, nome):
                setattr(modulo, nome, recusar)
    return 'Python: módulos socket e _socket sem rede'


def aplicar_limites(config=None) -> dict:
    """SEG-01: the caps of this process, by the operating system. Call before any other thread.

    Returns what was applied (also sent to the queue at start); a cap the system refused is
    reported, never silently assumed.
    """
    config = config or tetos.configuracao()
    aplicado = _limites_windows(config) if os.name == 'nt' else _limites_posix(config)
    rede = [_bloquear_socket_python()]
    if sys.platform.startswith('linux'):
        try:
            sistema = _seccomp_sem_rede()
        except (OSError, AttributeError, ValueError) as exc:
            sistema = None
            aplicado['falha_rede'] = f'seccomp: {exc}'
        if sistema:
            rede.insert(0, sistema)
        else:  # the queue logs it: the network is then refused only to Python code (S3)
            aplicado.setdefault('falha_rede', 'seccomp não instalado (arquitetura ou kernel sem suporte); '
                                              'a rede fica recusada só no Python deste processo')
    aplicado['rede'] = rede
    aplicado['tetos'] = config
    return aplicado


def _cpu_usado() -> float:
    """CPU seconds of this file: this process and its finished children (Windows: the whole job)."""
    if _JOB is not None:
        import ctypes

        class Contas(ctypes.Structure):
            _fields_ = [('TotalUserTime', ctypes.c_int64), ('TotalKernelTime', ctypes.c_int64),
                        ('ThisPeriodTotalUserTime', ctypes.c_int64), ('ThisPeriodTotalKernelTime', ctypes.c_int64),
                        ('TotalPageFaultCount', ctypes.c_uint32), ('TotalProcesses', ctypes.c_uint32),
                        ('ActiveProcesses', ctypes.c_uint32), ('TotalTerminatedProcesses', ctypes.c_uint32)]
        contas = Contas()
        k32 = ctypes.windll.kernel32
        if k32.QueryInformationJobObject(ctypes.c_void_p(_JOB), 1, ctypes.byref(contas), ctypes.sizeof(contas), None):
            return (contas.TotalUserTime + contas.TotalKernelTime) / 10_000_000
    tempos = os.times()
    return tempos.user + tempos.system + tempos.children_user + tempos.children_system


def juntar_filhos():
    """Windows: put this process in a Job Object that kills every process in it when this one ends.

    Its children (and theirs) are created inside the job (``aplicar_limites`` adds the caps to the
    same job). Returns True when it is in place. POSIX needs nothing here: the process leads its
    own group and ``_encerrar_tudo`` ends it.
    """
    global _JOB
    if os.name != 'nt' or _JOB is not None:
        return _JOB is not None
    import ctypes
    from ctypes import wintypes

    class Basico(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD)]

    class Estendido(ctypes.Structure):
        _fields_ = [('Basic', Basico), ('Io', ctypes.c_uint64 * 6), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t),
                    ('PeakJobMemoryUsed', ctypes.c_size_t)]

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return False
    info = Estendido()
    info.Basic.LimitFlags = 0x2000 | 0x400  # kill on job close; no error dialog for a crashed child
    if not (k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
            and k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())):
        k32.CloseHandle(job)
        return False
    _JOB = job
    return True


def _encerrar_tudo(codigo):
    """End this process and its children now (POSIX: its own process group; Windows: the job)."""
    if os.name != 'nt':
        try:
            if os.getpgid(0) == os.getpid():  # only as the leader of its own group (the queue starts it so)
                os.killpg(os.getpid(), 9)
        except OSError:
            pass
    os._exit(codigo)


def vigiar_cpu(config, enviar):
    """End the file's processing, saying why, once it used more CPU seconds than the cap."""
    limite = config['cpu_s']

    def vigiar():
        while True:
            time.sleep(0.25)
            if _cpu_usado() > limite:
                try:
                    enviar({'tipo': 'limite', 'mensagem': (
                        f'O arquivo excedeu o teto de {limite} s de CPU da extração (VLADO_EXTRACAO_TETO_CPU_S). '
                        'O original está preservado; o texto não foi extraído.')})
                finally:
                    _encerrar_tudo(5)
    threading.Thread(target=vigiar, daemon=True, name='vigia_de_cpu').start()


def vigiar_pai(pid):
    """End this process and its children when the Mesa that started it (``pid``) dies.

    Linux: compared with the pid the Mesa gave, not with the parent read here: a process born
    after the Mesa died is already adopted and ends at once. Windows: a handle to the Mesa's
    process, opened while it is alive, is signalled when it ends; if it is already gone, end now.
    """
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        sincronizar, infinito, inexistente = 0x00100000, 0xFFFFFFFF, 87  # ERROR_INVALID_PARAMETER
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        alca = k32.OpenProcess(sincronizar, False, pid)
        if not alca:
            if ctypes.get_last_error() == inexistente:
                _encerrar_tudo(3)
            return  # access refused: nothing to watch (the queue's deadline still applies)

        def esperar():
            k32.WaitForSingleObject(alca, infinito)
            _encerrar_tudo(3)
    else:
        def esperar():
            while os.getppid() == pid:
                time.sleep(0.5)
            _encerrar_tudo(3)
    threading.Thread(target=esperar, daemon=True, name='vigia_da_mesa').start()


# --- tarefa ------------------------------------------------------------------------------------

def _responder(pedido, enviar):
    if 'renderizar' in pedido:
        alvo = pedido['renderizar']
        try:
            png = tetos.renderizar_png(Path(alvo['pdf']), int(alvo['pagina']))
        except ValueError as exc:
            enviar({'tipo': 'erro', 'mensagem': str(exc)[:1000]})
        else:
            enviar({'tipo': 'imagem', 'png': base64.b64encode(png).decode('ascii')})
        return
    import cadastrar_documentos

    def progresso(fase, feitas, total):
        enviar({'tipo': 'progresso', 'fase': fase, 'feitas': feitas, 'total': total})
    resultado = cadastrar_documentos.extrair_item(pedido['tarefa'], base=Path(pedido['base']),
                                                  paralelo=pedido.get('paralelo'), progresso=progresso)
    enviar({'tipo': 'resultado', **resultado})


def main():
    config = tetos.configuracao()
    aplicado = aplicar_limites(config)  # first: the seccomp filter is inherited only by later threads
    # Keep the real stdout for the protocol; anything else printed goes to stderr.
    protocolo = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', newline='\n')
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    escrita = threading.Lock()

    def enviar(mensagem):
        with escrita:
            protocolo.write(json.dumps(mensagem, ensure_ascii=False) + '\n')
            protocolo.flush()

    if len(sys.argv) == 3 and sys.argv[1] == '--pai' and sys.argv[2].isdigit():
        vigiar_pai(int(sys.argv[2]))
    vigiar_cpu(config, enviar)
    enviar({'tipo': 'limites', 'aplicado': aplicado})
    entrada = open(sys.stdin.fileno(), 'r', encoding='utf-8', closefd=False)
    for linha in entrada:
        if not linha.strip():
            continue
        pedido = json.loads(linha)
        if pedido.get('tipo') == 'sair':
            break
        try:
            _responder(pedido, enviar)
        except MemoryError:
            enviar({'tipo': 'limite', 'mensagem': (
                'O arquivo excedeu o teto de memória da extração (VLADO_EXTRACAO_TETO_MEMORIA_MB). '
                'O original está preservado; o texto não foi extraído.')})
        except Exception as exc:  # noqa: BLE001 - reported to the queue, which decides
            enviar({'tipo': 'erro', 'mensagem': f'{type(exc).__name__}: {str(exc)[:1000]}'})
        break  # one file per process: nothing of a document reaches the next one
    protocolo.flush()


if __name__ == '__main__':
    main()
