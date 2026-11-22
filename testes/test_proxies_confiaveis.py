"""SEG-05: lista de proxies confiáveis e IP do cliente (primeiro salto não confiável, da direita para a esquerda).

Parte pura (scripts/proxies_confiaveis.py) e parte HTTP (o limite de tentativas por IP usa o IP certo). Sem lista, o
comportamento anterior (VLADO_CONFIAR_PROXY) continua igual.
"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import proxies_confiaveis as pc
from test_autorizacao import Http, ORIGEM
from test_acesso import SENHA


def ip(par, encaminhado, lista):
    return pc.ip_do_cliente(par, encaminhado, pc.analisar(lista))


class AnaliseDaListaTest(unittest.TestCase):
    def test_aceita_ips_redes_ipv6_e_varios_separadores(self):
        redes = pc.analisar('172.18.0.0/16, 203.0.113.7;2001:db8::/32  10.0.0.1')
        self.assertEqual([str(r) for r in redes], ['172.18.0.0/16', '203.0.113.7/32', '2001:db8::/32', '10.0.0.1/32'])

    def test_vazia_ou_ausente_e_none_e_invalida_diz_qual_item(self):
        for vazio in (None, '', '  ', ' , ; '):
            self.assertIsNone(pc.analisar(vazio))
        with self.assertRaisesRegex(ValueError, r"VLADO_PROXIES_CONFIAVEIS.*'cloudflare'"):
            pc.analisar('10.0.0.0/8, cloudflare')
        with self.assertRaises(ValueError):
            pc.analisar('10.0.0.0/33')

    def test_ambiente_invalido_vale_so_o_par_tcp_no_pedido_e_barra_a_partida(self):
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '10.0.0.0/8, lixo'}):
            self.assertEqual(pc.do_ambiente(), (), 'inválida nunca vira "confiar em todos"')
            with self.assertRaises(ValueError):
                pc.validar_ambiente()
            self.assertEqual(pc.ip_do_cliente('10.0.0.2', '203.0.113.9', pc.do_ambiente()), '10.0.0.2')
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': ''}):
            self.assertIsNone(pc.do_ambiente())
            pc.validar_ambiente()


class PrimeiroSaltoNaoConfiavelTest(unittest.TestCase):
    LISTA = '172.18.0.0/16, 203.0.113.0/24'  # o Caddy e a faixa da CDN

    def test_cliente_direto_nao_forja_o_ip(self):
        # O par TCP não é proxy confiável: o cabeçalho é do cliente e vale zero.
        self.assertEqual(ip('198.51.100.20', '1.2.3.4', self.LISTA), '198.51.100.20')
        self.assertEqual(ip('198.51.100.20', '1.2.3.4, 172.18.0.2', self.LISTA), '198.51.100.20')

    def test_um_proxy_o_cliente_e_o_ultimo_salto(self):
        self.assertEqual(ip('172.18.0.2', '198.51.100.20', self.LISTA), '198.51.100.20')

    def test_atras_de_cdn_o_cliente_e_o_primeiro_nao_confiavel_da_direita(self):
        # cliente, borda da CDN (confiável): Caddy é o par TCP.
        self.assertEqual(ip('172.18.0.2', '198.51.100.20, 203.0.113.50', self.LISTA), '198.51.100.20')
        # duas bordas da CDN em cadeia
        self.assertEqual(ip('172.18.0.2', '198.51.100.20, 203.0.113.50, 203.0.113.60', self.LISTA), '198.51.100.20')

    def test_valor_forjado_a_esquerda_do_cliente_real_e_ignorado(self):
        # O atacante manda 'XFF: 9.9.9.9'; a CDN acrescenta o IP real: ficou 9.9.9.9, 198.51.100.20, <borda>.
        self.assertEqual(ip('172.18.0.2', '9.9.9.9, 198.51.100.20, 203.0.113.50', self.LISTA), '198.51.100.20')
        # Mesmo com um falso "proxy confiável" escrito pelo atacante à esquerda, o primeiro não confiável da direita vence.
        self.assertEqual(ip('172.18.0.2', '203.0.113.1, 198.51.100.20, 203.0.113.50', self.LISTA), '198.51.100.20')

    def test_sem_cabecalho_ou_so_proxies_vale_o_mais_a_esquerda_ou_o_par(self):
        self.assertEqual(ip('172.18.0.2', '', self.LISTA), '172.18.0.2')
        self.assertEqual(ip('172.18.0.2', None, self.LISTA), '172.18.0.2')
        self.assertEqual(ip('172.18.0.2', '203.0.113.5, 203.0.113.6', self.LISTA), '203.0.113.5')

    def test_salto_ilegivel_interrompe_e_vale_o_par_tcp(self):
        for lixo in ('abc', '999.1.1.1', '198.51.100.20, nao-ip', '198.51.100.20,   , lixo', 'unknown'):
            self.assertEqual(ip('172.18.0.2', lixo, self.LISTA), '172.18.0.2', lixo)
        # Lixo só à esquerda do primeiro salto não confiável: não atrapalha.
        self.assertEqual(ip('172.18.0.2', 'lixo, 198.51.100.20', self.LISTA), '198.51.100.20')

    def test_ipv6_e_ipv4_mapeado(self):
        lista = '2001:db8:aaaa::/48, 172.18.0.0/16'
        self.assertEqual(ip('2001:db8:aaaa::1', '2001:db8:bbbb::7', lista), '2001:db8:bbbb::7')
        self.assertEqual(ip('::ffff:172.18.0.2', '198.51.100.20', lista), '198.51.100.20')
        self.assertEqual(ip('172.18.0.2', '::ffff:198.51.100.21', lista), '198.51.100.21')
        self.assertEqual(ip('172.18.0.2', '[2001:db8:bbbb::7]', lista), '2001:db8:bbbb::7')
        # Família diferente nunca casa por acidente.
        self.assertEqual(ip('198.51.100.20', '2001:db8:aaaa::5', lista), '198.51.100.20')

    def test_espacos_e_maiusculas(self):
        self.assertEqual(ip('172.18.0.2', '  198.51.100.20 ,  203.0.113.50  ', self.LISTA), '198.51.100.20')
        self.assertEqual(ip('2001:DB8::1', '2001:DB8::99', '2001:db8::1'), '2001:db8::99')


class HttpTest(Http):
    """O limite de 20 tentativas por minuto usa o IP calculado: atrás de CDN deixa de ser compartilhado."""

    def tentar(self, numero, xff, login=None):
        return self.publico('entrar', {'login': login or f'ninguem{numero}', 'senha': SENHA},
                            extra={'X-Forwarded-For': xff} if xff else None)[0]

    def test_sem_a_lista_o_comportamento_anterior_continua(self):
        acesso.limpar_limites()
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '', 'VLADO_CONFIAR_PROXY': ''}):
            for numero in range(20):
                self.tentar(numero, f'198.51.100.{numero}')
            self.assertEqual(self.tentar(99, '198.51.100.99'), 429, 'sem proxy confiável: todos dividem o socket')
        acesso.limpar_limites()
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '', 'VLADO_CONFIAR_PROXY': '1'}):
            for numero in range(20):
                self.tentar(numero, '10.0.0.1, 203.0.113.7')
            self.assertEqual(self.tentar(98, '203.0.113.7'), 429)
            self.assertEqual(self.tentar(99, '203.0.113.8'), 401, 'último salto da direita, como antes')

    def test_com_a_lista_atras_de_cdn_cada_cliente_tem_o_proprio_limite(self):
        acesso.limpar_limites()
        # O par TCP deste teste é 127.0.0.1 (o "Caddy"); 203.0.113.0/24 é a faixa da CDN.
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '127.0.0.1, 203.0.113.0/24'}):
            for numero in range(20):
                self.assertEqual(self.tentar(numero, '198.51.100.7, 203.0.113.50'), 401)
            self.assertEqual(self.tentar(98, '198.51.100.7, 203.0.113.50'), 429, 'o mesmo cliente atrás da CDN esgota o dele')
            # Outro cliente atrás da MESMA borda da CDN não é afetado (antes dividiam todos o último salto).
            self.assertEqual(self.tentar(99, '198.51.100.8, 203.0.113.50'), 401)

    def test_com_a_lista_um_cabecalho_forjado_a_esquerda_nao_troca_o_cliente(self):
        acesso.limpar_limites()
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '127.0.0.1, 203.0.113.0/24'}):
            for numero in range(20):  # o atacante troca o valor forjado a cada tentativa, o IP real é o mesmo
                self.tentar(numero, f'9.9.9.{numero}, 198.51.100.7, 203.0.113.50')
            self.assertEqual(self.tentar(99, '9.9.9.200, 198.51.100.7, 203.0.113.50'), 429)

    def test_par_tcp_fora_da_lista_ignora_o_cabecalho(self):
        acesso.limpar_limites()
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '10.0.0.0/8', 'VLADO_CONFIAR_PROXY': '1'}):
            for numero in range(20):  # 127.0.0.1 não está na lista: XFF não vale, nem com VLADO_CONFIAR_PROXY=1
                self.tentar(numero, f'198.51.100.{numero}')
            self.assertEqual(self.tentar(99, '198.51.100.99'), 429)

    def test_varias_linhas_de_x_forwarded_for_sao_lidas_juntas(self):
        acesso.limpar_limites()
        import http.client
        with patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': '127.0.0.1'}):
            for numero in range(21):
                con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
                con.putrequest('POST', '/api/entrar', skip_host=True, skip_accept_encoding=True)
                for nome, valor in (('Host', 'vlado.test'), ('Origin', ORIGEM), ('Content-Type', 'application/json'),
                                    ('Content-Length', str(len(b'{"login": "x", "senha": "y"}'))),
                                    ('X-Forwarded-For', '9.9.9.9'), ('X-Forwarded-For', '198.51.100.7')):
                    con.putheader(nome, valor)
                con.endheaders(b'{"login": "x", "senha": "y"}')
                status = con.getresponse().status
                con.close()
            self.assertEqual(status, 429, 'duas linhas viram "9.9.9.9,198.51.100.7": o cliente é 198.51.100.7')


if __name__ == '__main__':
    unittest.main()
