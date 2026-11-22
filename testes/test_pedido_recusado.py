"""SEG-02 x CONF-03: o 429 por excesso de pedidos em curso do mesmo endereço entra no registro de auditoria como UMA linha por IP e por
minuto, com a contagem, na classe anônima (teto do dia), sem custar nada aos eventos de entrada e de administração.
Fixture própria, no molde de test_recursos_servidor (que não é alterado)."""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import interface_pesquisa
import registro_acesso as reg
import test_codex_integracao as integracao


class Base(unittest.TestCase):
    def setUp(self):
        from modelo_pasta import copiar
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.registro = Path(pasta.name) / 'registro'
        ambiente = mock.patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': '',
                                                'VLADO_PROXIES_CONFIAVEIS': '127.0.0.1/32', 'VLADO_REGISTRO': str(self.registro),
                                                'VLADO_REGISTRO_CHAVE': str(Path(pasta.name) / 'segredos' / 'chave'),
                                                'VLADO_REGISTRO_DIA_MAX_MB': '', 'VLADO_REGISTRO_RETENCAO_DIAS': ''})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        reg._AGREGADOS.clear()
        self.addCleanup(reg._AGREGADOS.clear)
        reg.encerrar_requisicao()
        self.addCleanup(reg.encerrar_requisicao)
        reg._ESTADO['cheio'].clear()
        teto = mock.patch.object(interface_pesquisa, 'MAXIMO_POR_IP', 2)
        teto.start()
        self.addCleanup(teto.stop)
        self.server = interface_pesquisa.Servidor(('127.0.0.1', 0), self.root, modo='piloto', origem='https://vlado.test')
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(5)))

    def em_curso(self, cliente):
        conexao = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=10)
        self.addCleanup(conexao.close)
        linhas = ['POST /api/entrar HTTP/1.1', 'Host: vlado.test', 'Content-Type: application/json', 'Content-Length: 100',
                  f'X-Forwarded-For: {cliente}', '', '']
        conexao.sendall('\r\n'.join(linhas).encode('ascii'))
        return conexao

    def saude(self, cliente):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            con.request('GET', '/saude', headers={'Host': 'vlado.test', 'X-Forwarded-For': cliente})
            return con.getresponse().status
        finally:
            con.close()

    def linhas(self):
        reg.descarregar(tudo=True)
        saida = []
        for arquivo in reg.arquivos(self.registro):
            saida += [json.loads(l) for l in arquivo.read_text(encoding='ascii').splitlines()]
        return saida


class PedidoRecusadoNoRegistroTest(Base):
    def test_muitos_429_do_mesmo_endereco_viram_uma_linha_com_a_contagem(self):
        self.em_curso('203.0.113.7'), self.em_curso('203.0.113.7')
        time.sleep(0.3)
        codigos = [self.saude('203.0.113.7') for _ in range(7)]
        self.assertEqual(codigos, [429] * 7)
        linhas = [l for l in self.linhas() if l['evento'] == 'pedido_recusado']
        self.assertEqual(len(linhas), 1, 'uma linha para os sete pedidos')
        self.assertEqual((linhas[0]['ip'], linhas[0]['quantidade'], linhas[0]['motivo'], linhas[0]['resultado']),
                         ('203.0.113.7', 7, 'limite_ip', 'falha'))
        self.assertEqual(linhas[0]['origem'], 'web')

    def test_cada_endereco_tem_a_sua_linha_e_quem_nao_estourou_nao_aparece(self):
        self.em_curso('203.0.113.7'), self.em_curso('203.0.113.7')
        self.em_curso('198.51.100.9'), self.em_curso('198.51.100.9')
        time.sleep(0.3)
        for _ in range(3):
            self.assertEqual(self.saude('203.0.113.7'), 429)
        for _ in range(2):
            self.assertEqual(self.saude('198.51.100.9'), 429)
        self.assertEqual(self.saude('192.0.2.50'), 200)  # outro cliente: segue, e não gera linha
        por_ip = {l['ip']: l['quantidade'] for l in self.linhas() if l['evento'] == 'pedido_recusado'}
        self.assertEqual(por_ip, {'203.0.113.7': 3, '198.51.100.9': 2})

    def test_a_linha_nao_leva_conteudo_so_o_que_a_auditoria_ja_permite(self):
        self.em_curso('203.0.113.7'), self.em_curso('203.0.113.7')
        time.sleep(0.3)
        self.saude('203.0.113.7')
        linha = [l for l in self.linhas() if l['evento'] == 'pedido_recusado'][0]
        self.assertLessEqual(set(linha), {'em', 'evento', 'resultado', 'conta', 'ip', 'origem', 'motivo', 'quantidade'})
        self.assertIsNone(linha['conta'])

    def test_o_registro_vai_para_a_pasta_configurada_sem_vazar_contexto_para_a_proxima_requisicao(self):
        self.em_curso('203.0.113.7'), self.em_curso('203.0.113.7')
        time.sleep(0.3)
        self.saude('203.0.113.7')
        self.assertFalse(hasattr(reg._CTX, 'dados'), 'a thread de teste não ganhou contexto')
        self.assertTrue(self.linhas())

    def test_sem_a_cota_do_teto_ocupar_a_dos_eventos_protegidos(self):
        """O pedido recusado é da classe anônima: com o dia cheio dele, um login e uma criação de conta ainda gravam."""
        self.assertIn('pedido_recusado', reg.ANONIMOS)
        with mock.patch.dict(os.environ, {'VLADO_REGISTRO_DIA_MAX_MB': '1'}):
            reg.iniciar_requisicao(lambda: None)
            for i in range(10000):
                reg.registrar('pedido_recusado', 'falha', None, motivo='limite_ip', quantidade=i + 1, ip=f'203.0.{i // 250}.{i % 250 + 1}')
            antes = len([l for l in self.linhas()])
            reg.registrar('login_ok', 'ok', 'a1b2c3d4e5f60718', cliente='web')
            reg.registrar('conta_criada', 'ok', 'f0e1d2c3b4a59687', por='a1b2c3d4e5f60718')
            reg.encerrar_requisicao()
        eventos = [l['evento'] for l in self.linhas()]
        self.assertEqual(eventos[-2:], ['login_ok', 'conta_criada'])
        self.assertEqual([l['classe'] for l in self.linhas() if l['evento'] == 'registro_cheio'], ['anonimo'])
        self.assertGreater(antes, 100)


class AgrupamentoTest(Base):
    def test_enderecos_ipv6_da_mesma_rede_64_dividem_a_linha(self):
        reg.iniciar_requisicao(lambda: None)
        for ip in ('2001:db8:aaaa:1::1', '2001:db8:aaaa:1::2', '2001:db8:aaaa:1:ffff::9'):
            reg.registrar_limite_ip('pedido_recusado', ip, acesso._rede(ip))
        reg.registrar_limite_ip('pedido_recusado', '2001:db8:aaaa:2::1', acesso._rede('2001:db8:aaaa:2::1'))
        linhas = [l for l in self.linhas() if l['evento'] == 'pedido_recusado']
        self.assertEqual(sorted(l['quantidade'] for l in linhas), [1, 3])

    def test_a_documentacao_lista_o_evento(self):
        texto = (Path(__file__).resolve().parents[1] / 'deploy' / 'MONITORAMENTO.md').read_text(encoding='utf-8')
        self.assertIn('`pedido_recusado`', texto)
        self.assertIn('uma linha por IP e por minuto', texto)


if __name__ == '__main__':
    unittest.main()
