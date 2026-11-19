"""The suite runs without API keys and never opens a connection outside 127.0.0.1.

A subprocess starts with ANTHROPIC_API_KEY and OPENAI_API_KEY removed from its
environment, installs a socket guard that refuses non-loopback hosts before any
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
# Modules that import the providers or the API adapter; all use fake clients.
MODULOS = ('test_provedores_api', 'test_inferencia_api', 'test_config_ia', 'test_erros')

GUARDA = textwrap.dedent('''
    import json, socket, sys, unittest
    from pathlib import Path

    LOCAIS = {'127.0.0.1', 'localhost', '::1', '', None}
    tentativas = []

    def _host(endereco):
        return endereco[0] if isinstance(endereco, tuple) and endereco else endereco

    def _conferir(onde, host):
        if host in LOCAIS or (isinstance(host, str) and host.startswith('127.')):
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

    raiz, saida, modulos = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    sys.path[:0] = [str(raiz / 'scripts'), str(raiz / 'testes')]

    # The guard itself must refuse an external host without touching the network.
    autoteste = False
    try:
        socket.create_connection(('example.invalid', 443), timeout=1)
    except ConnectionRefusedError:
        autoteste = True
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
        'autoteste': autoteste, 'sdks': sdks, 'tentativas_importacao': tentativas_importacao,
        'tentativas': tentativas, 'executados': resultado.testsRun,
        'falhas': len(resultado.failures), 'erros': len(resultado.errors),
    }), encoding='utf-8')
''')


def ambiente_sem_chaves():
    """Copy of the environment without the key variables, filtered by name only."""
    return {nome: valor for nome, valor in os.environ.items() if nome.upper() not in CHAVES}


class SemChavesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pasta = tempfile.TemporaryDirectory()
        cls.addClassCleanup(pasta.cleanup)
        guarda, saida = Path(pasta.name) / 'guarda.py', Path(pasta.name) / 'resultado.json'
        guarda.write_text(GUARDA, encoding='utf-8')
        env = ambiente_sem_chaves()
        env['PYTHONIOENCODING'] = 'utf-8'
        processo = subprocess.run([sys.executable, str(guarda), str(RAIZ), str(saida), *MODULOS],
                                  cwd=str(RAIZ), env=env, capture_output=True, text=True,
                                  encoding='utf-8', errors='replace', timeout=600)
        cls.saida_processo = processo.stderr[-4000:]
        cls.resultado = json.loads(saida.read_text(encoding='utf-8')) if saida.exists() else None

    def setUp(self):
        self.assertIsNotNone(self.resultado, self.saida_processo)

    def test_ambiente_do_subprocesso_nao_tem_chaves(self):
        env = ambiente_sem_chaves()
        self.assertFalse(set(map(str.upper, env)) & set(CHAVES))

    def test_guarda_recusa_host_externo(self):
        self.assertTrue(self.resultado['autoteste'])

    def test_importar_provedores_nao_abre_conexao(self):
        self.assertEqual(self.resultado['tentativas_importacao'], [])
        self.assertEqual(set(self.resultado['sdks']), {'anthropic', 'openai'})

    def test_modulos_de_provedor_passam_sem_chave_nem_rede(self):
        self.assertGreater(self.resultado['executados'], 0)
        self.assertEqual((self.resultado['falhas'], self.resultado['erros']), (0, 0), self.saida_processo)
        self.assertEqual(self.resultado['tentativas'], [])


if __name__ == '__main__':
    unittest.main()
