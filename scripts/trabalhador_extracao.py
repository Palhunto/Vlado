"""Processo de extração da fila da Mesa (CONF-02). Não é para uso direto.

Lê tarefas pela entrada padrão, uma linha JSON por tarefa, e responde pela saída padrão, também
uma linha JSON por mensagem:

    entrada  {"tarefa": {...}, "base": "<pasta do lote>", "paralelo": 2}   (ou {"tipo": "sair"})
    saída    {"tipo": "progresso", "fase": "texto|orientacao|reconhecimento|paginas", "feitas": N, "total": M}
             {"tipo": "resultado", "resultado": {...}, "derivado": "derivados/3/....md" | null}
             {"tipo": "erro", "mensagem": "..."}

A tarefa é a de ``cadastrar_documentos.tarefa`` e a extração é ``cadastrar_documentos.extrair_item``,
a mesma do cadastro pela linha de comando. O processo só lê o original e escreve a cópia de
trabalho na pasta do lote: não abre manifesto, catálogo nem trava. Qualquer outra coisa escrita
na saída padrão (avisos de bibliotecas) vai para a saída de erro, para não misturar com as
mensagens. Termina com a entrada fechada, com {"tipo": "sair"} ou morto pela fila (prazo).

Os filhos (OCRmyPDF, Tesseract, Ghostscript) terminam junto: no Windows o processo entra num Job
Object que mata todos quando ele acaba (``proc.kill()`` da fila, vigia ou queda); no Linux ele é
líder do próprio grupo (a fila o abre com ``start_new_session``), e o vigia e a fila matam o grupo.

``aplicar_limites`` é o ponto único onde entram os tetos do isolamento (SEG-01, fase 3): CPU,
memória, tempo, páginas, pixels e rede deste processo. Hoje não limita nada.
"""
import json
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
_JOB = None  # Windows: kept open for this process's whole life; closing it kills the children


def juntar_filhos():
    """Windows: put this process in a Job Object that kills every process in it when this one ends.

    Its children (and theirs) are created inside the job. Returns True when it is in place.
    POSIX needs nothing here: the process leads its own group and ``_encerrar_tudo`` ends it.
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
    """End this process and its children now (POSIX: its own group; Windows: the job closes)."""
    if os.name != 'nt':
        try:
            if os.getpgid(0) == os.getpid():  # only as the leader of its own group (the queue starts it so)
                os.killpg(os.getpid(), 9)
        except OSError:
            pass
    os._exit(codigo)


def aplicar_limites():
    """SEG-01 (fase 3): tetos de CPU, memória, tempo, páginas e pixels, e sem rede. Sem efeito hoje."""
    return None


def vigiar_pai(pid):
    """End this process and its children when the Mesa that started it (``pid``) dies.

    Linux: compared with the pid the Mesa gave, not with the parent read here: a process born
    after the Mesa died is already adopted and ends at once. Windows: a handle to the Mesa's
    process, opened while it is alive, is signalled when it ends; if it is already gone, end now.
    """
    if os.name == 'nt':
        import ctypes
        sincronizar, infinito, inexistente = 0x00100000, 0xFFFFFFFF, 87  # ERROR_INVALID_PARAMETER
        from ctypes import wintypes
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


def main():
    juntar_filhos()
    if len(sys.argv) == 3 and sys.argv[1] == '--pai' and sys.argv[2].isdigit():
        vigiar_pai(int(sys.argv[2]))
    # Keep the real stdout for the protocol; anything else printed goes to stderr.
    protocolo = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', newline='\n')
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    entrada = open(sys.stdin.fileno(), 'r', encoding='utf-8', closefd=False)
    escrita = threading.Lock()

    def enviar(mensagem):
        with escrita:
            protocolo.write(json.dumps(mensagem, ensure_ascii=False) + '\n')
            protocolo.flush()

    aplicar_limites()
    import cadastrar_documentos

    for linha in entrada:
        if not linha.strip():
            continue
        pedido = json.loads(linha)
        if pedido.get('tipo') == 'sair':
            break

        def progresso(fase, feitas, total):
            enviar({'tipo': 'progresso', 'fase': fase, 'feitas': feitas, 'total': total})
        try:
            resultado = cadastrar_documentos.extrair_item(pedido['tarefa'], base=Path(pedido['base']),
                                                          paralelo=pedido.get('paralelo'), progresso=progresso)
        except Exception as exc:  # noqa: BLE001 - reported to the queue, which decides
            enviar({'tipo': 'erro', 'mensagem': f'{type(exc).__name__}: {str(exc)[:1000]}'})
        else:
            enviar({'tipo': 'resultado', **resultado})


if __name__ == '__main__':
    main()
