"""The suite runs without API keys and never opens a connection outside 127.0.0.1.

A subprocess starts with ANTHROPIC_API_KEY and OPENAI_API_KEY removed from its
environment (and VLADO_SEGREDOS, which could point at a real key file),
installs a socket guard that refuses non-loopback hosts before any
DNS lookup or traffic, imports the providers (and their SDKs, when installed)
and runs the provider-facing test modules under that guard. Key values are
never read or printed: the environment is filtered by name only.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

RAIZ = Path(__file__).resolve().parents[1]
CHAVES = ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY')
# Removed by name together with the keys: a token variable and the path to a key file.
REMOVIDAS = CHAVES + ('ANTHROPIC_AUTH_TOKEN', 'VLADO_SEGREDOS')
# Modules that import the providers or the API adapter; all use fake clients.
MODULOS = ('test_provedores_api', 'test_inferencia_api', 'test_config_ia', 'test_erros')

GUARDA = textwrap.dedent('''
    import ipaddress, json, os, socket, sys, unittest
    from pathlib import Path

    NOMES_LOCAIS = {'localhost', '', None}
    tentativas = []

    def _local(host):
        if host in NOMES_LOCAIS:
            return True
        try:  # only literal loopback addresses; a name such as "127.example.com" is external
            endereco = ipaddress.ip_address(str(host).split('%', 1)[0])
        except ValueError:
            return False
        mapeado = getattr(endereco, 'ipv4_mapped', None)
        return (mapeado or endereco).is_loopback

    def _host(endereco):
        return endereco[0] if isinstance(endereco, tuple) and endereco else endereco

    def _conferir(onde, host):
        if _local(host):
            return
        tentativas.append({'onde': onde, 'host': str(host)})
        raise ConnectionRefusedError(f'conexão externa bloqueada no teste: {host}')

    _create, _connect, _connect_ex, _getaddrinfo = (
        socket.create_connection, socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo)

    def create_connection(endereco, *a, **k):
        _conferir('create_connection', _host(endereco))
        return _create(endereco, *a, **k)

    def connect(self, endereco):
        _conferir('connect', _host(endereco))
        return _connect(self, endereco)

    def connect_ex(self, endereco):
        _conferir('connect_ex', _host(endereco))
        return _connect_ex(self, endereco)

    def getaddrinfo(host, *a, **k):
        _conferir('getaddrinfo', host.decode() if isinstance(host, bytes) else host)
        return _getaddrinfo(host, *a, **k)

    socket.create_connection, socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = (
        create_connection, connect, connect_ex, getaddrinfo)

    raiz, saida, removidas, modulos = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].split(','), sys.argv[4:]
    presentes = sorted(n for n in removidas if n in {k.upper() for k in os.environ})  # names only
    sys.path[:0] = [str(raiz / 'scripts'), str(raiz / 'testes')]

    # The guard itself must refuse an external host without touching the network.
    autoteste = False
    try:
        socket.create_connection(('example.invalid', 443), timeout=1)
    except ConnectionRefusedError:
        autoteste = True
    try:  # a name that only looks like a loopback address is refused too
        socket.getaddrinfo('127.exemplo.invalid', 443)
    except ConnectionRefusedError:
        pass
    else:
        autoteste = False
    tentativas.clear()

    import inferencia_api, provedor_anthropic, provedor_openai  # noqa: F401
    sdks = {}
    for nome, construir in (('anthropic', lambda m: m.Anthropic(api_key='chave-falsa-de-teste', max_retries=0)),
                            ('openai', lambda m: m.OpenAI(api_key='chave-falsa-de-teste', max_retries=0))):
        try:
            modulo = __import__(nome)
        except ImportError:
            sdks[nome] = 'ausente'
            continue
        construir(modulo)
        sdks[nome] = 'importado'
    tentativas_importacao = list(tentativas)

    suite = unittest.defaultTestLoader.loadTestsFromNames(modulos)
    resultado = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    saida.write_text(json.dumps({
        'autoteste': autoteste, 'presentes': presentes, 'sdks': sdks, 'tentativas_importacao': tentativas_importacao,
        'tentativas': tentativas, 'executados': resultado.testsRun,
        'falhas': len(resultado.failures), 'erros': len(resultado.errors),
    }), encoding='utf-8')
''')


def ambiente_sem_chaves():
    """Copy of the environment without the key variables, filtered by name only."""
    return {nome: valor for nome, valor in os.environ.items() if nome.upper() not in REMOVIDAS}


class SemChavesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pasta = tempfile.TemporaryDirectory()
        cls.addClassCleanup(pasta.cleanup)
        guarda, saida = Path(pasta.name) / 'guarda.py', Path(pasta.name) / 'resultado.json'
        guarda.write_text(GUARDA, encoding='utf-8')
        env = ambiente_sem_chaves()
        env['PYTHONIOENCODING'] = 'utf-8'
        processo = subprocess.run([sys.executable, str(guarda), str(RAIZ), str(saida), ','.join(REMOVIDAS), *MODULOS],
                                  cwd=str(RAIZ), env=env, capture_output=True, text=True,
                                  encoding='utf-8', errors='replace', timeout=600)
        cls.saida_processo = processo.stderr[-4000:]
        cls.resultado = json.loads(saida.read_text(encoding='utf-8')) if saida.exists() else None

    def setUp(self):
        self.assertIsNotNone(self.resultado, self.saida_processo)

    def test_ambiente_do_subprocesso_nao_tem_chaves(self):
        # Checked inside the child process, which reports variable names only, never values.
        self.assertEqual(self.resultado['presentes'], [])

    def test_guarda_recusa_host_externo(self):
        self.assertTrue(self.resultado['autoteste'])

    def test_importar_provedores_nao_abre_conexao(self):
        self.assertEqual(self.resultado['tentativas_importacao'], [])
        # A missing SDK is reported as 'ausente'; the providers themselves were imported either way.
        self.assertEqual(set(self.resultado['sdks']), {'anthropic', 'openai'})
        self.assertLessEqual(set(self.resultado['sdks'].values()), {'importado', 'ausente'})

    def test_modulos_de_provedor_passam_sem_chave_nem_rede(self):
        self.assertGreater(self.resultado['executados'], 0)
        self.assertEqual((self.resultado['falhas'], self.resultado['erros']), (0, 0), self.saida_processo)
        self.assertEqual(self.resultado['tentativas'], [])


if __name__ == '__main__':
    unittest.main()
