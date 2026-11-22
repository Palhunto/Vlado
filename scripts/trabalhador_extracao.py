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


def aplicar_limites():
    """SEG-01 (fase 3): tetos de CPU, memória, tempo, páginas e pixels, e sem rede. Sem efeito hoje."""
    return None


def vigiar_pai(pid):
    """End this process when the Mesa that started it dies (no orphan keeps reading a file).

    Linux: the parent changes when the Mesa dies (the child is adopted). Windows: a handle to
    the Mesa's process, opened while it is alive, is signalled when it ends (no pid reuse).
    """
    if os.name == 'nt':
        import ctypes
        sincronizar, infinito = 0x00100000, 0xFFFFFFFF
        alca = ctypes.windll.kernel32.OpenProcess(sincronizar, False, pid)
        if not alca:
            return

        def esperar():
            ctypes.windll.kernel32.WaitForSingleObject(alca, infinito)
            os._exit(3)
    else:
        original = os.getppid()

        def esperar():
            while os.getppid() == original:
                time.sleep(1)
            os._exit(3)
    threading.Thread(target=esperar, daemon=True, name='vigia_da_mesa').start()


def main():
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
