"""Esperas pelo processo de extração que só pulam quando a máquina não deu CPU a ele, medida na mesma janela.

O processo de extração roda abaixo da prioridade normal e sem o núcleo 0 (SEG-01): numa máquina ocupada por
processos de prioridade normal ele só roda nas sobras, e pode passar dezenas de segundos sem os ~0,5 s de CPU de
que precisa para ler a primeira página (medido em 22/11: com três processos normais ocupando a máquina, uma sonda
nas mesmas condições teve 0,28 s de CPU em 40 s). Medir a CPU depois do prazo, com uma sonda curta, não diz o que
a extração teve durante ele: uma folga basta para a sonda passar.

``esperar_com_cpu`` espera a condição e, durante TODA a espera, roda uma sonda de prioridade baixa sem o núcleo 0
(as condições da extração), que pede CPU sem parar até a espera acabar. Esgotado o prazo:

- a sonda teve pelo menos ``necessario`` s de CPU (4 vezes o que a extração precisa): a CPU existia e a leitura não
  aconteceu, então o problema é da Mesa ou da fila, e o teste FALHA;
- teve menos: a máquina não deu CPU à prioridade baixa, e o teste PULA com o motivo e os números.

No CI o portão tem de rodar sem pular: o pulo existe só para a máquina de desenvolvimento cheia.

A sonda anota o próprio CPU num arquivo a cada 0,1 s e é morta ao fim da espera, na hora: sem CPU ela não
acumula nada, então o último valor anotado vale (no máximo 0,1 s a menos). Roda no Python base, e não no
lançador do ``.venv`` do Windows, para que matar o processo mate a sonda.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import time

NECESSARIO_PARA_LER = 2.0  # CPU s: 4 times the ~0.5 s from process start to the first page of the heavy PDF
NECESSARIO_ARQUIVO = 60.0  # CPU s: 4 times the ~15 s of reading the whole heavy PDF on one core

SONDA = r"""
import os, sys, time
limite, arquivo = float(sys.argv[1]), sys.argv[2]
if os.name == 'nt':
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    processo = k32.GetCurrentProcess()
    k32.SetPriorityClass(ctypes.c_void_p(processo), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS, as the extraction
    nucleos = os.cpu_count() or 1
    if nucleos > 1:  # without core 0, as the extraction
        k32.SetProcessAffinityMask(ctypes.c_void_p(processo), ctypes.c_size_t(sum(1 << n for n in range(1, min(nucleos, 64)))))
else:
    os.nice(10)
    nucleos = sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else []
    if len(nucleos) > 1:
        os.sched_setaffinity(0, nucleos[1:])
inicio, base = time.monotonic(), time.process_time()
anotado = inicio
with open(arquivo, 'a', encoding='ascii') as saida:
    n = 0
    while True:
        n += 1
        if n % 20000:
            continue
        agora = time.monotonic()
        if agora - anotado >= 0.1:
            anotado = agora
            saida.write(f'{time.process_time() - base:.3f}\n')
            saida.flush()
        if agora - inicio > limite:
            break
"""


def _python_base():
    """The interpreter itself: on Windows the .venv's python.exe is a launcher whose child is the real one."""
    return getattr(sys, '_base_executable', None) or sys.executable


class SondaBaixa:
    """A low-priority process without core 0 asking for CPU until ``parar`` (or ``limite`` s)."""

    def __init__(self, limite):
        self._pasta = tempfile.TemporaryDirectory()
        self._arquivo = Path(self._pasta.name) / 'cpu.txt'
        self._inicio = time.monotonic()
        self._proc = subprocess.Popen([_python_base(), '-c', SONDA, str(limite), str(self._arquivo)])
        self._medida = None

    def _cpu(self):
        try:
            linhas = self._arquivo.read_text(encoding='ascii').splitlines()
        except OSError:
            return 0.0
        for linha in reversed(linhas):  # the last whole line (the one being written may be cut)
            try:
                return float(linha)
            except ValueError:
                continue
        return 0.0

    def parar(self):
        """(wall seconds, CPU seconds) the probe had; kills it at once."""
        if self._medida is None:
            janela = time.monotonic() - self._inicio
            self._proc.kill()
            self._proc.wait(30)
            self._medida = (janela, self._cpu())
        return self._medida

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        try:
            self.parar()
        finally:
            self._pasta.cleanup()


def esperar_com_cpu(teste, condicao, prazo, necessario, mensagem, sonda=SondaBaixa, passo=0.02):
    """``condicao()``'s first true value within ``prazo`` s; else fail or skip by the parallel probe (see above)."""
    with sonda(prazo + 30) as medidor:
        limite = time.monotonic() + prazo
        while True:
            valor = condicao()
            if valor:
                return valor
            if time.monotonic() > limite:
                break
            time.sleep(passo)
        janela, cpu = medidor.parar()
    numeros = (f'a sonda de prioridade baixa sem o núcleo 0, na mesma janela, teve {cpu:.2f} s de CPU em '
               f'{janela:.1f} s (necessário {necessario:.0f} s)')
    if cpu >= necessario:
        teste.fail(f'{mensagem} em {prazo:.0f} s, com CPU disponível: {numeros}')
    teste.skipTest(f'máquina saturada para prioridade baixa: {numeros}; {mensagem} em {prazo:.0f} s')
