"""A Mesa conta cada cliente pelo IP que o Caddy escreve no X-Forwarded-For (limite de tentativas, teto de pedidos por endereço da
CONF-03 e auditoria). O par TCP dela é sempre o Caddy; sem lista de proxies confiáveis o Caddy seria o "cliente" de todos. O Compose
fixa a sub-rede da rede do ambiente e a lista SEMPRE a leva, sem depender de VLADO_CONFIAR_PROXY."""
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
import proxies_confiaveis as pc

EXEMPLOS = ('homologacao', 'demonstracao', 'editorial', 'local')
PADRAO = '172.29.99.0/24'
LINHA = '      VLADO_PROXIES_CONFIAVEIS: ${VLADO_REDE_SUBNET:-172.29.99.0/24}${VLADO_PROXIES_CONFIAVEIS:+,${VLADO_PROXIES_CONFIAVEIS}}\n'


def exemplo(nome) -> str:
    return (RAIZ / 'deploy' / 'ambientes' / f'{nome}.env.example').read_text(encoding='utf-8')


def sub_rede_do_exemplo(nome) -> str:
    return re.search(r'(?m)^VLADO_REDE_SUBNET=(\S+)$', exemplo(nome))[1]


class TextoDoComposeTest(unittest.TestCase):
    def setUp(self):
        self.compose = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')

    def test_a_lista_do_app_sempre_leva_a_sub_rede_e_so_acrescenta_o_que_o_operador_pede(self):
        self.assertIn(LINHA, self.compose)
        self.assertEqual(self.compose.count('\n      VLADO_PROXIES_CONFIAVEIS: '), 1, 'definida uma vez, no app')

    def test_nao_depende_mais_de_confiar_proxy(self):
        codigo = '\n'.join(l for l in self.compose.splitlines() if not l.lstrip().startswith('#'))
        self.assertNotIn('VLADO_CONFIAR_PROXY', codigo)

    def test_a_rede_do_compose_tem_sub_rede_fixa_pela_mesma_variavel(self):
        bloco = self.compose.split('\nnetworks:\n', 1)[1]
        self.assertRegex(bloco, r'(?s)^  default:\n    ipam:\n      config:\n        - subnet: \$\{VLADO_REDE_SUBNET:-172\.29\.99\.0/24\}')

    def test_so_o_app_recebe_a_lista(self):
        for servico in ('caddy', 'backup', 'restauracao'):
            bloco = self.compose.split(f'\n  {servico}:\n', 1)[1].split('\n  ', 1)[0]
            self.assertNotIn('VLADO_PROXIES_CONFIAVEIS', bloco, servico)


class SubRedesDosExemplosTest(unittest.TestCase):
    def test_cada_ambiente_tem_a_sua_sub_rede_privada_e_nenhuma_e_o_padrao(self):
        redes = {nome: ipaddress.ip_network(sub_rede_do_exemplo(nome)) for nome in EXEMPLOS}
        privada = ipaddress.ip_network('172.16.0.0/12')
        for nome, rede in redes.items():
            self.assertTrue(rede.subnet_of(privada), f'{nome}: {rede} não é faixa privada 172.16/12')
            self.assertGreaterEqual(rede.prefixlen, 16, nome)
            self.assertNotEqual(str(rede), PADRAO, f'{nome}: usa o padrão do Compose, que é só para quem não configura')
            self.assertGreaterEqual(rede.prefixlen, pc.PREFIXO_MINIMO[4], 'a lista da Mesa a aceita sem confirmação')
        for a in EXEMPLOS:
            for b in EXEMPLOS:
                if a < b:
                    self.assertFalse(redes[a].overlaps(redes[b]), f'{a} e {b} colidem')
        self.assertFalse(ipaddress.ip_network(PADRAO).overlaps(next(iter(redes.values()))))

    def test_os_exemplos_explicam_que_a_lista_extra_e_somada(self):
        for nome in ('homologacao', 'demonstracao', 'editorial'):
            texto = exemplo(nome)
            self.assertIn('# VLADO_PROXIES_CONFIAVEIS=', texto)
            self.assertIn('ACRESCENTADAS', texto)
            self.assertIn('SEMPRE leva esta', texto)

    def test_documentacao_explica_a_sub_rede_o_extra_e_como_conferir(self):
        texto = (RAIZ / 'deploy' / 'MONITORAMENTO.md').read_text(encoding='utf-8')
        secao = texto[texto.index('## IP do cliente atrás do Caddy e de CDN ou WAF'):texto.index('## Cabeçalhos e conexões (SEG-06)')]
        for trecho in ('sub-rede fixa', 'VLADO_REDE_SUBNET', 'sempre começa por ela', 'Pool overlaps', 'somadas', 'um limite e um teto só',
                       'Não depende mais de `VLADO_CONFIAR_PROXY`', 'dois `ip` diferentes'):
            self.assertIn(trecho, secao, trecho)


@unittest.skipUnless(shutil.which('docker'), 'sem docker no PATH')
class ComposeConfigTest(unittest.TestCase):
    def config(self, extra_env=None, arquivo_env=None, local=False) -> str:
        with tempfile.TemporaryDirectory() as pasta:
            env = Path(pasta) / 'x.env'
            env.write_text(arquivo_env if arquivo_env is not None else 'VLADO_AMBIENTE=homologacao\nVLADO_DOMINIO=x.example\n', encoding='utf-8')
            comando = ['docker', 'compose', '-p', 'vlado-teste-rede', '--env-file', str(env), '-f', 'docker-compose.yml']
            if local:
                comando += ['-f', 'deploy/compose.local.yml']
            r = subprocess.run(comando + ['config'], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8',
                               env={k: v for k, v in dict(os.environ, **(extra_env or {})).items()
                                    if not k.startswith(('VLADO_PROXIES', 'VLADO_REDE', 'VLADO_CONFIAR'))} | (extra_env or {}))
        if r.returncode != 0 and 'unknown shorthand flag' in r.stderr:
            self.skipTest('docker sem o plugin compose')
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def lista(self, saida) -> str:
        return re.search(r'(?m)^      VLADO_PROXIES_CONFIAVEIS: (.+)$', saida)[1].strip().strip('"')

    def sub_rede(self, saida) -> str:
        return re.search(r'(?m)^\s+- subnet: (\S+)$', saida)[1]

    def test_sem_configurar_nada_a_lista_e_a_sub_rede_padrao_e_a_rede_a_usa(self):
        saida = self.config()
        self.assertEqual(self.lista(saida), PADRAO)
        self.assertEqual(self.sub_rede(saida), PADRAO)
        self.assertNotIn('VLADO_CONFIAR_PROXY', saida)

    def test_cada_exemplo_entrega_a_sua_sub_rede_na_lista_e_na_rede(self):
        for nome in ('homologacao', 'demonstracao', 'editorial'):
            esperado = sub_rede_do_exemplo(nome)
            texto = exemplo(nome).replace('VLADO_DOMINIO=homologacao.vlado.example.org', 'VLADO_DOMINIO=x.example')
            saida = self.config(arquivo_env=texto + '\nVLADO_DOMINIO=x.example\n')
            self.assertEqual(self.lista(saida), esperado, nome)
            self.assertEqual(self.sub_rede(saida), esperado, nome)

    def test_faixas_da_cdn_sao_somadas_depois_da_sub_rede_nunca_no_lugar(self):
        saida = self.config({'VLADO_REDE_SUBNET': '172.29.10.0/24', 'VLADO_PROXIES_CONFIAVEIS': '203.0.113.0/24, 2001:db8::/32'})
        lista = self.lista(saida)
        self.assertTrue(lista.startswith('172.29.10.0/24,'), lista)
        self.assertIn('203.0.113.0/24', lista)
        self.assertEqual(self.sub_rede(saida), '172.29.10.0/24')
        redes = pc.analisar(lista)
        self.assertEqual([str(r) for r in redes], ['172.29.10.0/24', '203.0.113.0/24', '2001:db8::/32'])

    def test_ambiente_local_entrega_a_dele(self):
        texto = exemplo('local').replace('C:/Users/SEU-USUARIO/Vlado-backups-teste', tempfile.gettempdir().replace(chr(92), '/'))
        saida = self.config(arquivo_env=texto, local=True)
        self.assertEqual(self.lista(saida), '172.29.40.0/24')
        self.assertEqual(self.sub_rede(saida), '172.29.40.0/24')


class ComoAMesaLeAListaTest(unittest.TestCase):
    """A lista que o Compose entrega, lida pelo código da Mesa: cada cliente atrás do Caddy é contado separado."""

    def test_dois_clientes_atras_do_caddy_sao_contados_separados_e_o_caddy_nunca_e_o_cliente(self):
        redes = pc.analisar('172.29.10.0/24')
        caddy = '172.29.10.2'
        self.assertEqual(pc.ip_do_cliente(caddy, '198.51.100.7', redes), '198.51.100.7')
        self.assertEqual(pc.ip_do_cliente(caddy, '198.51.100.8', redes), '198.51.100.8')
        self.assertNotEqual(pc.ip_do_cliente(caddy, '198.51.100.7', redes), caddy)

    def test_sem_a_lista_o_caddy_seria_o_cliente_de_todos_o_que_o_compose_evita(self):
        self.assertEqual(pc.ip_do_cliente('172.29.10.2', '198.51.100.7', ()), '172.29.10.2')

    def test_quem_fala_direto_de_fora_da_sub_rede_nao_forja_o_ip(self):
        redes = pc.analisar('172.29.10.0/24')
        self.assertEqual(pc.ip_do_cliente('198.51.100.99', '1.2.3.4', redes), '198.51.100.99')
        self.assertEqual(pc.ip_do_cliente('172.29.20.5', '1.2.3.4', redes), '172.29.20.5', 'rede de outro ambiente não é de confiança')

    def test_o_padrao_do_compose_e_a_lista_dos_exemplos_passam_na_validacao_da_mesa(self):
        for nome in EXEMPLOS:
            self.assertIsNotNone(pc.analisar(sub_rede_do_exemplo(nome)), nome)
        self.assertIsNotNone(pc.analisar(PADRAO))


if __name__ == '__main__':
    unittest.main()
