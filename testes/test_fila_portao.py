"""Portão da Onda 1 (CONF-02): dez sessões ao mesmo tempo com uma extração longa em curso.

A Mesa roda com a fila em modo ``processos`` (o de ``main``) e recebe um PDF pesado, lido
por cerca de 15 s num processo de extração. Enquanto ele é lido:

- um cadastro de outro documento na mesma apuração responde em menos de ``LIMITE`` segundos;
- dez sessões simultâneas leem o catálogo e o inventário, gravam e listam notas e perguntam em
  outra apuração (provedor simulado; na apuração com lote na fila a primeira pergunta é recusada
  de propósito): cada pedido responde em menos de ``LIMITE`` segundos;
- as mesmas dez sessões cadastram, cada uma, outro documento: todos publicados sem esperar o
  arquivo longo. Dez publicações e dez congelamentos de pergunta dividem a trava de cadastro do
  projeto (CONF-01) e passam um por vez, por isso o limite próprio.

O lote longo continua em processamento até o fim: essa é a prova de que ninguém o esperou, e ela
é sempre exigida.

**Carga da máquina.** Antes do PDF longo, as dez sessões cadastram um documento cada ao mesmo tempo,
sem extração nenhuma em curso: o tempo do mais lento é ``T_ref``, medido na mesma máquina e no mesmo
minuto. Só cadastros, que terminam: uma rodada inteira de referência deixaria dez perguntas em curso
no provedor simulado e mudaria o que se mede. Com a extração longa, os dez cadastros têm até
``max(LIMITE_CADASTROS, 2·T_ref)``, com ``T_ref`` limitado a ``TETO_REF`` (acima dele, a Mesa está
lenta para cadastrar): com o teto de 6 s o limite é 12 s, e o 2·T_ref só conta se o teto subir. Se a
fila travasse a Mesa, o tempo saltaria para perto do tempo do arquivo longo (15 s ou mais). Os dois
tempos saem na saída do teste.

**Diagnóstico na falha.** Durante as sessões, uma thread do processo do teste (onde a Mesa também roda)
só dorme 0,1 s de cada vez e anota a maior parada que viu, as faltas de página do processo e a memória
livre da máquina (mínima e máxima). Nada disso decide nada: vai só na mensagem quando um pedido passa do
limite, para dizer se o processo inteiro parou (a máquina) ou se só os pedidos esperaram (a Mesa).

**Pular só sem CPU, medida na mesma janela.** Lentidão nunca pula por si: uma Mesa que regrida e fique
lenta falha. Os tempos da própria Mesa (``T_ref`` acima de ``TETO_REF``, o cadastro avulso acima de
``LIMITE`` e os pedidos das sessões acima dos seus limites) são medidos numa ``JanelaCpu``: falham
quando, nos mesmos segundos, a máquina deixou ociosos pelo menos 4 vezes o CPU que o processo do teste
(onde a Mesa roda) gastou neles, sem passar da duração da janela (um núcleo inteiro ocioso) e com
mínimo de 1 s; pulam com os números quando não deixou (``apoio_cpu_baixa.decidir_por_ociosa``). Uma
sonda normal tirada depois não servia: com a máquina 93% ocupada ela teve os seus 0,2 s em 0,27 s e
culpou a Mesa; uma sonda normal durante a janela disputaria os núcleos com a própria Mesa. Com a CPU
ociosa ilegível, falha. O processo de extração roda abaixo da prioridade normal e sem o núcleo 0 (SEG-01), para não
tirar CPU da Mesa, e com a máquina saturada por outros processos pode nem começar: a espera de até
60 s pelo começo da leitura roda, durante toda ela, uma sonda nas mesmas condições dele (prioridade
abaixo do normal, sem o núcleo 0). Se a sonda teve na janela pelo menos 2 s de CPU (4 vezes os ~0,5 s
de que a extração precisa até a primeira página) e a leitura não começou, falha; senão, pula com os
números (``apoio_cpu_baixa``). Uma sonda curta depois do prazo não servia: uma folga basta para ela
passar, sem dizer o que a extração teve durante a espera. Para fechar a Onda 1, o portão tem de rodar
sem pular (no CI, ``VLADO_EXIGIR_SEM_PULO=1`` faz de todo pulo uma falha).

Medido no Windows de 4 núcleos (22/11): ``T_ref`` de 0,9 a 1,7 s com nenhum, dois ou os quatro
núcleos ocupados por outros processos; os dez cadastros com a extração longa, de 1,6 a 5,9 s. Com os
quatro núcleos ocupados, uma sonda de prioridade baixa sem o núcleo 0 tem 0,06 s de CPU em 10,7 s.

Dados sintéticos; sem rede nem modelo.
"""
import base64
import ctypes
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import uuid

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import fila_extracao  # noqa: E402
from interface_pesquisa import Servidor  # noqa: E402
from modelo_pasta import copiar  # noqa: E402
import test_codex_integracao as integracao  # noqa: E402
from test_extracao_cadastro_pdf import HAS_PYPDF  # noqa: E402
from test_fila_extracao import pdf_pesado  # noqa: E402
from apoio_cpu_baixa import NECESSARIO_PARA_LER, JanelaCpu, esperar_com_cpu  # noqa: E402

SESSOES = 10
LIMITE = 2.0
LIMITE_CADASTROS = 12.0
TETO_REF = 6.0  # T_ref above this (measured 0.9 to 1.7 s, even with all 4 cores busy): the Mesa is slow


def faltas_de_pagina():
    """Page faults of this process so far (Windows: all of them; POSIX: the major ones, from disk), or None."""
    if os.name == 'nt':
        class Contadores(ctypes.Structure):
            _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong)] + [
                (nome, ctypes.c_size_t) for nome in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                                                     'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                                                     'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        contadores = Contadores()
        contadores.cb = ctypes.sizeof(Contadores)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(k32.GetCurrentProcess()), ctypes.byref(contadores),
                                                        contadores.cb):
            return None
        return contadores.PageFaultCount
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_majflt
    except (ImportError, OSError):
        return None


def memoria_livre_mb():
    """Free physical memory of the machine in MB (Linux: MemAvailable), or None."""
    if os.name == 'nt':
        class Estado(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong)] + [
                (nome, ctypes.c_ulonglong) for nome in ('ullTotalPhys', 'ullAvailPhys', 'ullTotalPageFile',
                                                        'ullAvailPageFile', 'ullTotalVirtual', 'ullAvailVirtual',
                                                        'ullAvailExtendedVirtual')]
        estado = Estado()
        estado.dwLength = ctypes.sizeof(Estado)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
            return None
        return estado.ullAvailPhys >> 20
    try:
        with open('/proc/meminfo', encoding='ascii') as info:
            for linha in info:
                if linha.startswith('MemAvailable:'):
                    return int(linha.split()[1]) >> 10
    except OSError:
        pass
    return None


class Diagnostico:
    """What the process and the machine did while the sessions ran; only for the failure message.

    A thread that only sleeps ``PASSO`` s at a time notes the longest gap between two wake-ups: a
    gap far above ``PASSO`` means the whole process stood still (no thread of it ran), not that
    the requests waited for something of the Mesa."""
    PASSO = 0.1
    AMOSTRA = 0.5  # free memory and page faults are read at most this often

    def __init__(self):
        self.parar = threading.Event()
        self.maior_parada = 0.0
        self.faltas_inicio = self.faltas_fim = faltas_de_pagina()
        self.memoria = []
        self._anterior = self._amostra = None
        self._thread = threading.Thread(target=self._rodar, daemon=True, name='diagnostico_portao')

    def anotar(self, agora):
        """One wake-up at ``agora`` (monotonic seconds)."""
        if self._anterior is not None:
            self.maior_parada = max(self.maior_parada, agora - self._anterior)
        self._anterior = agora
        if self._amostra is None or agora - self._amostra >= self.AMOSTRA:
            self._amostra = agora
            livre = memoria_livre_mb()
            if livre is not None:
                self.memoria.append(livre)
            self.faltas_fim = faltas_de_pagina()

    def _rodar(self):
        while not self.parar.is_set():
            self.anotar(time.monotonic())
            time.sleep(self.PASSO)
        self.anotar(time.monotonic())

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *erro):
        self.parar.set()
        self._thread.join(5)

    def texto(self):
        faltas = ('?' if self.faltas_inicio is None or self.faltas_fim is None
                  else str(self.faltas_fim - self.faltas_inicio))
        memoria = f'entre {min(self.memoria)} e {max(self.memoria)} MB' if self.memoria else '?'
        return (f'durante as sessões, no processo do teste: maior parada de uma thread que só dorme '
                f'{self.PASSO:.1f} s de cada vez {self.maior_parada:.2f} s; faltas de página {faltas}; '
                f'memória livre da máquina {memoria}')


class DiagnosticoTest(unittest.TestCase):
    """The failure message's diagnostic, fed with chosen wake-up times (no Mesa)."""

    def test_maior_parada_e_texto(self):
        diagnostico = Diagnostico()
        for agora in (10.0, 10.1, 10.2, 24.2, 24.3):  # the process stood still for 14 s
            diagnostico.anotar(agora)
        self.assertAlmostEqual(diagnostico.maior_parada, 14.0)
        texto = diagnostico.texto()
        self.assertIn('maior parada de uma thread que só dorme 0.1 s de cada vez 14.00 s', texto)
        self.assertRegex(texto, r'faltas de página (\d+|\?); memória livre da máquina (entre \d+ e \d+ MB|\?)$')
        if os.name == 'nt':  # both counters exist on the machines the gate runs on
            self.assertNotIn('?', texto)

    def test_roda_e_para(self):
        with Diagnostico() as diagnostico:
            time.sleep(0.35)
        self.assertFalse(diagnostico._thread.is_alive())
        # It ran and measured; no ceiling on the gap: that would test the machine, not the thread (D1).
        self.assertGreater(diagnostico.maior_parada, 0.0)


@unittest.skipUnless(HAS_PYPDF, 'Instalar requirements.txt para testar extração real')
class PortaoFilaTest(unittest.TestCase):
    def setUp(self):
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
        # The gate measures that the queue never blocks the Mesa: the ceilings of questions at the same
        # time (CUS-01, tested in test_custo) are opened for its ten simultaneous questions.
        config = json.loads((self.root / 'configuracao.json').read_text(encoding='utf-8'))
        config['orcamento'] = {'execucoes_simultaneas_por_conta': SESSOES, 'execucoes_simultaneas': SESSOES}
        config['maximo_documentos_inicial'] = 50  # the reference uploads go into the same case
        (self.root / 'configuracao.json').write_text(json.dumps(config), encoding='utf-8')
        self.server = Servidor(('127.0.0.1', 0), self.root, extracao='processos')
        self.server.conversas.factory = integracao.FakeServer
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.encerrar(10), self.server.server_close(),
                                 thread.join(10)))

    def pedir(self, metodo, caminho, dados=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        try:
            con.request(metodo, caminho, json.dumps(dados) if dados is not None else None,
                        {'Content-Type': 'application/json', 'Origin': self.server.origin,
                         'X-Session-Token': self.server.token})
            resposta = con.getresponse()
            return resposta.status, json.loads(resposta.read())
        finally:
            con.close()

    def sessao(self, numero, tempos, erros):
        texto = f'Documento sintético da sessão {numero}.'.encode('utf-8')
        pedidos = [
            ('catalogo', 'GET', '/api/catalogo', None),
            ('inventario', 'POST', '/api/inventario', {'caso': 'alpha'}),
            ('nota', 'POST', '/api/apuracao-nota-salvar', {'caso': 'alpha', 'titulo': f'Nota {numero}',
                                                           'texto': 'Nota sintética.', 'requisicao_id': uuid.uuid4().hex}),
            ('notas', 'POST', '/api/apuracao-notas', {'caso': 'alpha'}),
            ('pergunta', 'POST', '/api/codex-perguntar', {'caso': 'beta', 'pergunta': f'Pergunta sintética {numero}.'}),
            # Into the case whose long file is being read: published without waiting for it.
            ('cadastro', 'POST', '/api/cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos', 'arquivos': [
                {'nome': f'sessao_{numero}.txt', 'base64': base64.b64encode(texto).decode('ascii')}]}),
        ]
        for nome, metodo, caminho, dados in pedidos:
            inicio = time.monotonic()
            try:
                status, corpo = self.pedir(metodo, caminho, dados)
            except Exception as exc:  # noqa: BLE001 - reported by the test
                erros.append((numero, nome, repr(exc)))
                continue
            tempos.append((round(time.monotonic() - inicio, 2), numero, nome))
            if status != 200:
                erros.append((numero, nome, status, corpo))

    def cadastros_simultaneos(self, prefixo):
        """Seconds of the slowest of SESSOES simultaneous uploads (one small file each, into alpha)."""
        tempos, erros = [], []

        def cadastrar(numero):
            texto = f'Documento sintético de referência {numero}.'.encode('utf-8')
            inicio = time.monotonic()
            try:
                status, corpo = self.pedir('POST', '/api/cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos', 'arquivos': [
                    {'nome': f'{prefixo}_{numero}.txt', 'base64': base64.b64encode(texto).decode('ascii')}]})
            except Exception as exc:  # noqa: BLE001 - reported by the test
                erros.append((numero, repr(exc)))
                return
            tempos.append(time.monotonic() - inicio)
            if status != 200:
                erros.append((numero, status, corpo))
        threads = [threading.Thread(target=cadastrar, args=(n,), daemon=True) for n in range(SESSOES)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(120)
        self.assertEqual(erros, [])
        self.assertEqual(len(tempos), SESSOES)
        return max(tempos)

    def test_dez_sessoes_com_extracao_longa_em_curso(self):
        # The same ten uploads with no extraction in course: the reference of this machine, this minute.
        # In the same window: the machine's idle CPU and what this process (the Mesa runs in it) spent. A normal
        # probe would compete with the Mesa and change T_ref itself (apoio_cpu_baixa.JanelaCpu).
        with JanelaCpu() as janela_ref:
            referencia = self.cadastros_simultaneos('referencia')
        if referencia > TETO_REF:
            janela_ref.decidir(self, f'T_ref = {referencia:.2f} s, acima de {TETO_REF:.0f} s: a Mesa está lenta para cadastrar')
        limite_cadastros = max(LIMITE_CADASTROS, 2 * referencia)
        with tempfile.TemporaryDirectory() as pasta:
            pesado = pdf_pesado(Path(pasta) / 'pesado.pdf')  # about 15 s of reading on one core
            conteudo = base64.b64encode(pesado.read_bytes()).decode('ascii')
        status, corpo = self.pedir('POST', '/api/cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos', 'assincrono': True,
                                                             'arquivos': [{'nome': 'pesado.pdf', 'base64': conteudo}]})
        self.assertEqual(status, 200, corpo)
        lote = corpo['lote']['lote']
        esperar_com_cpu(self, lambda: (fila_extracao._ler(fila_extracao.pasta_fila(self.root) / lote / 'estado.json')
                                       or {}).get('arquivos', [{}])[0].get('pagina'),
                        60, NECESSARIO_PARA_LER, f'o processo de extração não começou a ler (T_ref = {referencia:.2f} s)',
                        passo=0.05)
        texto = base64.b64encode('Documento sintético avulso.'.encode('utf-8')).decode('ascii')
        with JanelaCpu() as janela_avulso:
            inicio = time.monotonic()
            status, recibo = self.pedir('POST', '/api/cadastrar', {'caso': 'alpha', 'natureza': 'sinteticos',
                                                                   'arquivos': [{'nome': 'avulso.txt', 'base64': texto}]})
            avulso = time.monotonic() - inicio
        self.assertEqual((status, recibo.get('novos')), (200, 1), recibo)
        if avulso >= LIMITE:
            janela_avulso.decidir(self, f'o cadastro avulso levou {avulso:.2f} s (limite {LIMITE:.0f} s): '
                                        'o cadastro esperou a extração longa')
        tempos, erros = [], []
        sessoes = [threading.Thread(target=self.sessao, args=(n, tempos, erros), daemon=True) for n in range(SESSOES)]
        # The window of the sessions, from the first request to the last: it decides a request over its limit.
        # The Diagnostico only goes in the message.
        with Diagnostico() as diagnostico, JanelaCpu() as janela_sessoes:
            for sessao in sessoes:
                sessao.start()
            for sessao in sessoes:
                sessao.join(120)
        self.assertEqual(erros, [])
        self.assertEqual(len(tempos), SESSOES * 6)
        lentos = sorted((t for t in tempos if t[0] >= (limite_cadastros if t[2] == 'cadastro' else LIMITE)), reverse=True)
        if lentos:
            janela_sessoes.decidir(self, f'pedidos acima do limite com a extração longa em curso: {lentos} '
                                         f'(T_ref = {referencia:.2f} s, limite dos cadastros {limite_cadastros:.2f} s; '
                                         f'{diagnostico.texto()})')
        # The long file was still being read the whole time (otherwise the check proves nothing).
        estado = self.pedir('GET', f'/api/fila?lote={lote}')[1]['lote']
        self.assertEqual((estado['estado'], estado['arquivos'][0]['estado']), ('processando', 'extraindo'),
                         'a extração longa terminou antes das sessões; usar um PDF mais pesado')
        inventario = self.pedir('POST', '/api/inventario', {'caso': 'alpha'})[1]
        self.assertEqual(inventario['total_documentos'], 2 + 2 * SESSOES)  # the reference uploads too
        outros = max(t for t in tempos if t[2] != 'cadastro')
        cadastros = max(t for t in tempos if t[2] == 'cadastro')
        print(f' [cadastro avulso {avulso:.2f} s; leitura, notas e perguntas até {outros[0]:.2f} s ({outros[2]}); '
              f'dez cadastros simultâneos até {cadastros[0]:.2f} s, sem extração (T_ref) {referencia:.2f} s]',
              end=' ', file=sys.stderr)


if __name__ == '__main__':
    unittest.main()
