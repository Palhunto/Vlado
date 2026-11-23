"""Idioma inicial das páginas (P42 do dono): a mesma ordem no Entrar e na Mesa.

1. a escolha da pessoa neste navegador (``vlado-idioma``, só do lado do navegador: i18n.cjs e entrar_idioma.cjs);
2. o ``idioma`` da conta, quando há sessão;
3. o ``Accept-Language`` do pedido, só ``pt`` ou ``en`` (qualidades respeitadas; ``pt-BR`` e ``pt-PT`` são ``pt``);
4. o padrão do servidor (hospedado ``en``, demais ``pt``).
O servidor só põe 2 a 4 em ``data-idioma-padrao`` do ``<body>``; aqui, o servidor do cenário de duas redações (piloto).
"""
from pathlib import Path
import re
import sys
import unittest

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
sys.path.insert(0, str(TESTES))
import acesso  # noqa: E402
import cenario_redacoes as cenario  # noqa: E402
import rotas_estaticas  # noqa: E402

PADRAO = re.compile(rb'data-idioma-padrao="([^"]*)"')


class CabecalhoTest(unittest.TestCase):
    def test_so_pt_ou_en_com_as_qualidades(self):
        casos = (('pt-BR,pt;q=0.9,en;q=0.8', 'pt'), ('pt-PT', 'pt'), ('en-US,en;q=0.9', 'en'), ('en;q=0.4, pt;q=0.6', 'pt'),
                 ('fr-FR,fr;q=0.9,en;q=0.5', 'en'), ('fr, de;q=0.8', None), ('*', None), ('', None), (None, None),
                 ('pt;q=0, en;q=0.1', 'en'), ('pt;q=abc, en', 'en'), ('ptx, en', 'en'), ('PT-br', 'pt'), ('en, pt', 'en'),
                 ('pt;q=1.5, en', 'en'))
        for valor, esperado in casos:
            with self.subTest(valor=valor):
                self.assertEqual(rotas_estaticas.idioma_do_cabecalho(valor), esperado)

    def test_a_ordem_conta_navegador_padrao_do_servidor(self):
        ini = rotas_estaticas.idioma_inicial
        self.assertEqual(ini(da_conta='en', do_navegador='pt-BR', modo='piloto'), 'en')
        self.assertEqual(ini(da_conta='pt', do_navegador='en', modo='piloto'), 'pt')
        self.assertEqual(ini(do_navegador='pt-BR', modo='piloto'), 'pt')
        self.assertEqual(ini(do_navegador='fr-FR', modo='piloto'), 'en')
        self.assertEqual(ini(do_navegador='fr-FR', modo='local'), 'pt')
        self.assertEqual(ini(modo='local-contas'), 'pt')
        self.assertEqual(ini(da_conta='<script>', do_navegador=None, modo='piloto'), 'en', 'só pt ou en vão para a página')


class PaginasTest(cenario.DuasRedacoes):
    """O servidor piloto: o Entrar (sem sessão) e a Mesa (com a sessão de uma conta)."""

    def idioma_da(self, caminho, accept=None, quem=None):
        cabecalhos = {}
        if accept is not None:
            cabecalhos['Accept-Language'] = accept
        if quem is not None:
            cabecalhos['Cookie'] = self.sessoes[quem][0]
        status, _, corpo = self.pedir('GET', caminho, cabecalhos=cabecalhos)
        self.assertEqual(status, 200, corpo[:200])
        achado = PADRAO.search(corpo)
        self.assertIsNotNone(achado, f'{caminho} sem data-idioma-padrao')
        return achado.group(1).decode('ascii')

    def test_entrar_navegador_pt_br_abre_em_portugues_no_piloto(self):
        self.assertEqual(self.idioma_da('/entrar', 'pt-BR,pt;q=0.9,en;q=0.8'), 'pt')
        self.assertEqual(self.idioma_da('/entrar', 'en-US,en;q=0.9'), 'en')
        self.assertEqual(self.idioma_da('/entrar'), 'en', 'sem cabeçalho: o padrão do piloto')
        self.assertEqual(self.idioma_da('/entrar', 'fr-FR,fr;q=0.9'), 'en', 'idioma que a Mesa não fala: o padrão do piloto')

    def test_mesa_navegador_pt_br_abre_em_portugues_no_piloto(self):
        self.assertEqual(self.idioma_da('/', 'pt-BR,pt;q=0.9', quem='leitor'), 'pt')

    def test_conta_com_idioma_en_abre_em_ingles_mesmo_com_navegador_pt(self):
        acesso.atualizar_perfil(self.root, self.ids['leitor'], idioma='en')
        self.addCleanup(acesso.atualizar_perfil, self.root, self.ids['leitor'], idioma='pt')
        self.assertEqual(self.idioma_da('/', 'pt-BR,pt;q=0.9', quem='leitor'), 'en')
        self.assertEqual(self.idioma_da('/', None, quem='leitor'), 'en')

    def test_conta_em_portugues_vence_o_navegador_em_ingles(self):
        self.assertEqual(self.idioma_da('/', 'en-US,en;q=0.9', quem='convidado'), 'pt')

    def test_a_pagina_nao_muda_de_idioma_entre_o_entrar_e_a_mesa(self):
        # sem escolha no navegador, a mesma pessoa (conta em pt, navegador pt-BR) vê o mesmo idioma nas duas páginas
        for accept in ('pt-BR,pt;q=0.9', 'pt-PT'):
            with self.subTest(accept=accept):
                self.assertEqual(self.idioma_da('/entrar', accept), self.idioma_da('/', accept, quem='editor'))

    def test_a_pagina_de_pendencia_com_sessao_usa_o_idioma_da_conta(self):
        acesso.atualizar_perfil(self.root, self.ids['reporter'], idioma='en')
        self.addCleanup(acesso.atualizar_perfil, self.root, self.ids['reporter'], idioma='pt')
        self.assertEqual(self.idioma_da('/conta/segundo-fator', 'pt-BR', quem='reporter'), 'en')
        self.assertEqual(self.idioma_da('/conta/segundo-fator', 'pt-BR'), 'pt', 'sem sessão, o navegador')

    def test_so_pt_ou_en_chega_a_pagina(self):
        for accept in ('pt-BR', 'en', '"><script>', 'xx'):
            self.assertIn(self.idioma_da('/entrar', accept), acesso.IDIOMAS)


if __name__ == '__main__':
    unittest.main()
