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

Para a Mesa, que roda em prioridade normal, uma sonda normal disputaria os núcleos com ela e mudaria o tempo
medido. Ali vale ``decidir_por_ociosa``: a CPU que sobrou ociosa na máquina durante a mesma janela
(``cpu_ociosa_s``, sem consumir nada), contra o que a própria Mesa gastou nela.

A sonda anota o próprio CPU num arquivo a cada 0,1 s e é morta ao fim da espera, na hora: sem CPU ela não
acumula nada, então o último valor anotado vale (no máximo 0,1 s a menos). Roda no Python base, e não no
lançador do ``.venv`` do Windows, para que matar o processo mate a sonda. A primeira linha (``0``) ela anota
ainda em prioridade normal, antes de baixar a sua: sem nenhuma linha, ou tendo terminado sozinha antes do fim
da espera, quem falhou foi a sonda, e a espera FALHA dizendo que ela não mediu (nunca pula por uma sonda que
não rodou).

Numa máquina de 2 núcleos, sem o núcleo 0 a sonda e a extração dividem o único núcleo que sobra: cada uma tem
cerca de metade dele durante a espera. A regra continua valendo (as duas recebem o mesmo), mas a extração anda
mais devagar enquanto a sonda roda.

Com ``VLADO_EXIGIR_SEM_PULO=1`` (o job do CI), todo pulo destas regras vira falha, com o mesmo motivo: o portão
só fecha a onda rodando sem pular.
"""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

NECESSARIO_PARA_LER = 2.0  # CPU s: 4 times the ~0.5 s from process start to the first page of the heavy PDF
NECESSARIO_ARQUIVO = 60.0  # CPU s: 4 times the ~15 s of reading the whole heavy PDF on one core
NECESSARIO_PARA_SAIR = 0.5  # CPU s: 4 times the ~0.1 s for the watcher to wake and end the process
OCIOSA_MINIMA = 1.0  # CPU s left idle that always counts as "the machine had CPU" (decidir_por_ociosa)
EXIGIR_SEM_PULO = 'VLADO_EXIGIR_SEM_PULO'

SONDA = r"""
import os, sys, time
limite, arquivo = float(sys.argv[1]), sys.argv[2]
with open(arquivo, 'a', encoding='ascii') as saida:  # still at normal priority: proof that this code ran
    saida.write('0\n')
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
    """A low-priority process without core 0 asking for CPU until ``parar`` (or ``limite`` s).

    ``problema`` (after ``parar``): why the probe did not measure (ended by itself before the wait did, or never
    wrote a line), else None. ``codigo``: the probe's program (tests give a broken one)."""

    def __init__(self, limite, codigo=SONDA):
        self._pasta = tempfile.TemporaryDirectory()
        self._arquivo = Path(self._pasta.name) / 'cpu.txt'
        self._inicio = time.monotonic()
        self._proc = subprocess.Popen([_python_base(), '-c', codigo, str(limite), str(self._arquivo)])
        self._medida = None
        self.problema = None

    def _cpu(self):
        """(last CPU seconds written, how many whole lines)."""
        try:
            linhas = self._arquivo.read_text(encoding='ascii').splitlines()
        except OSError:
            return 0.0, 0
        valores = []
        for linha in linhas:  # the one being written may be cut
            try:
                valores.append(float(linha))
            except ValueError:
                continue
        return (valores[-1] if valores else 0.0), len(valores)

    def parar(self):
        """(wall seconds, CPU seconds) the probe had; kills it at once."""
        if self._medida is None:
            janela = time.monotonic() - self._inicio
            saiu = self._proc.poll()  # it only ends by itself on an error: its limit is past the wait's
            if saiu is None:
                self._proc.kill()
            self._proc.wait(30)
            cpu, linhas = self._cpu()
            if saiu is not None:
                self.problema = f'a sonda terminou sozinha antes do fim da espera (código {saiu})'
            elif not linhas:
                self.problema = 'a sonda não anotou nenhuma medida (não chegou a rodar)'
            self._medida = (janela, cpu)
        return self._medida

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        try:
            self.parar()
        finally:
            self._pasta.cleanup()


def cpu_ociosa_s():
    """Idle CPU seconds of the whole machine so far (all cores added up), or None where it cannot be read."""
    if os.name == 'nt':
        ociosa, nucleo, usuario = (ctypes.c_ulonglong() for _ in range(3))
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(ociosa), ctypes.byref(nucleo), ctypes.byref(usuario)):
            return None
        return ociosa.value / 10_000_000
    try:
        with open('/proc/stat', encoding='ascii') as estado:
            campos = estado.readline().split()
        return (int(campos[4]) + int(campos[5])) / os.sysconf('SC_CLK_TCK')  # idle + iowait
    except (OSError, ValueError, IndexError):
        return None


def pular(teste, motivo):
    """Skip with ``motivo``; with VLADO_EXIGIR_SEM_PULO=1 (CI) the skip is a failure with the same reason."""
    if os.environ.get(EXIGIR_SEM_PULO) == '1':
        teste.fail(f'pulo proibido ({EXIGIR_SEM_PULO}=1): {motivo}')
    teste.skipTest(motivo)


def decidir_por_ociosa(teste, ociosa, gasto, janela, mensagem):
    """A time of the Mesa over its limit: FAIL when the machine left idle, in the same window of ``janela`` clock
    seconds, at least max(OCIOSA_MINIMA, min(4 x what the Mesa spent, janela)) CPU seconds (P38: never more than a
    whole idle core for the window), or when idle time cannot be read; SKIP otherwise, with the numbers."""
    necessario = max(OCIOSA_MINIMA, min(4 * gasto, janela))
    if ociosa is None:
        teste.fail(f'{mensagem} (CPU ociosa da máquina ilegível nesta plataforma; a Mesa gastou {gasto:.2f} s)')
    numeros = (f'na mesma janela de {janela:.2f} s a máquina deixou {ociosa:.2f} s de CPU ociosa; a Mesa gastou '
               f'{gasto:.2f} s (necessário {necessario:.2f} s ociosos)')
    if ociosa >= necessario:
        teste.fail(f'{mensagem}, com CPU disponível: {numeros}')
    pular(teste, f'máquina saturada para prioridade normal: {numeros}; {mensagem}')


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
    problema = getattr(medidor, 'problema', None)
    if problema:  # a probe that did not run proves nothing about the machine: never a skip
        teste.fail(f'{mensagem} em {prazo:.0f} s, e a sonda da CPU não mediu: {problema}')
    numeros = (f'a sonda de prioridade baixa sem o núcleo 0, na mesma janela, teve {cpu:.2f} s de CPU em '
               f'{janela:.1f} s (necessário {necessario:.0f} s)')
    if cpu >= necessario:
        teste.fail(f'{mensagem} em {prazo:.0f} s, com CPU disponível: {numeros}')
    pular(teste, f'máquina saturada para prioridade baixa: {numeros}; {mensagem} em {prazo:.0f} s')
