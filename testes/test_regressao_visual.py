"""Testes da infraestrutura de regressão visual (sem navegador, só Pillow).

O que ficaria verde em silêncio é o que mais importa aqui: o comparador precisa reprovar mudança
pequena de texto, de cor e de posição, tamanho diferente, captura ausente e captura sem referência;
e a linha de base versionada precisa bater com o manifesto (nenhuma imagem trocada ou apagada à mão).
A captura em si (Playwright) roda à mão: `python testes/regressao_visual.py comparar`.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
import unittest

from PIL import Image, ImageDraw

import regressao_visual as rv
import regressao_visual_comparador as cmp


def pagina(tamanho=(400, 300), fundo=(250, 250, 245)):
    imagem = Image.new('RGB', tamanho, fundo)
    desenho = ImageDraw.Draw(imagem)
    desenho.rectangle((20, 20, 380, 60), fill=(30, 70, 55))
    for linha in range(4):
        desenho.text((24, 90 + linha * 30), 'Documentos cadastrados e conferidos', fill=(40, 40, 40))
    return imagem


class ComparadorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)

    def salvar(self, imagem, nome):
        caminho = self.pasta / nome
        imagem.save(caminho)
        return caminho

    def comparar(self, atual, referencia=None):
        ref = self.salvar(referencia or pagina(), 'ref.png')
        atu = self.salvar(atual, 'atu.png')
        return cmp.comparar_imagens(ref, atu, 'tela__375__claro', self.pasta / 'dif')

    def test_identica(self):
        r = self.comparar(pagina())
        self.assertEqual(r.estado, 'igual')
        self.assertTrue(r.aprovado)

    def test_ruido_abaixo_da_tolerancia_passa(self):
        atual = pagina()
        atual.putpixel((10, 10), (253, 250, 245))   # 3 níveis num pixel
        r = self.comparar(atual)
        self.assertEqual(r.estado, 'dentro_da_tolerancia')
        self.assertTrue(r.aprovado)

    def test_palavra_trocada_reprova(self):
        atual = pagina()
        ImageDraw.Draw(atual).text((24, 90), 'Documentos descartados', fill=(40, 40, 40))
        r = self.comparar(atual)
        self.assertEqual(r.estado, 'diferente')
        self.assertFalse(r.aprovado)
        self.assertTrue(r.regioes)
        self.assertTrue(Path(r.caminho_diff).is_file())

    def test_cor_de_token_reprova(self):
        atual = pagina()
        ImageDraw.Draw(atual).rectangle((20, 20, 380, 60), fill=(30, 70, 70))   # verde → verde-azulado
        r = self.comparar(atual)
        self.assertEqual(r.estado, 'diferente')

    def test_elemento_deslocado_em_um_pixel_reprova(self):
        atual = pagina()
        ImageDraw.Draw(atual).rectangle((20, 20, 380, 60), fill=(250, 250, 245))
        ImageDraw.Draw(atual).rectangle((21, 20, 381, 60), fill=(30, 70, 55))
        self.assertEqual(self.comparar(atual).estado, 'diferente')

    def test_mudanca_de_tamanho_reprova(self):
        r = self.comparar(pagina((400, 340)))
        self.assertEqual(r.estado, 'tamanho')
        self.assertFalse(r.aprovado)

    def test_pastas_com_ausente_e_nova(self):
        refs, atuais = self.pasta / 'refs', self.pasta / 'atuais'
        refs.mkdir(), atuais.mkdir()
        pagina().save(refs / 'a__375__claro.png')
        pagina().save(refs / 'b__375__claro.png')
        pagina().save(atuais / 'a__375__claro.png')
        pagina().save(atuais / 'c__375__claro.png')
        estados = {r.nome: r.estado for r in cmp.comparar_pastas(refs, atuais)}
        self.assertEqual(estados, {'a__375__claro': 'igual', 'b__375__claro': 'ausente', 'c__375__claro': 'nova'})

    def test_esperado_sem_referencia_nem_captura_reprova(self):
        refs, atuais = self.pasta / 'refs', self.pasta / 'atuais'
        refs.mkdir(), atuais.mkdir()
        resultados = cmp.comparar_pastas(refs, atuais, esperados=['x__375__claro'])
        self.assertEqual([(r.nome, r.estado) for r in resultados], [('x__375__claro', 'ausente')])
        self.assertFalse(resultados[0].aprovado)

    def test_relatorio_lista_so_as_reprovadas(self):
        refs, atuais = self.pasta / 'refs', self.pasta / 'atuais'
        refs.mkdir(), atuais.mkdir()
        pagina().save(refs / 'ok__375__claro.png')
        pagina().save(atuais / 'ok__375__claro.png')
        pagina().save(refs / 'mudou__375__claro.png')
        mudada = pagina()
        ImageDraw.Draw(mudada).text((24, 90), 'Outra frase aqui', fill=(0, 0, 0))
        mudada.save(atuais / 'mudou__375__claro.png')
        resultados = cmp.comparar_pastas(refs, atuais, self.pasta / 'dif')
        html = cmp.escrever_relatorio(resultados, self.pasta / 'rel', refs, atuais).read_text(encoding='utf-8')
        self.assertIn('mudou__375__claro', html)
        self.assertNotIn('ok__375__claro', html)
        dados = json.loads((self.pasta / 'rel/relatorio.json').read_text(encoding='utf-8'))
        self.assertEqual(dados['resumo']['reprovadas'], 1)
        self.assertEqual(dados['resumo']['tolerancia']['canal'], cmp.TOLERANCIA_CANAL)


class MascarasTest(unittest.TestCase):
    """As máscaras trocam só data e hora gravadas pelo servidor; o resto do texto passa intacto."""

    def mascarar(self, texto):
        for padrao in rv.mascaras(datetime(2026, 11, 21, 17, 2, tzinfo=timezone.utc)):
            texto = re.sub(padrao, '‹data›', texto)
        return texto

    def test_datas_e_horas(self):
        self.assertEqual(self.mascarar('Atualizada em 21/11/2026'), 'Atualizada em ‹data›')
        self.assertEqual(self.mascarar('21/11/2026, 17:02:11 · Admin'), '‹data› · Admin')
        self.assertEqual(self.mascarar('Salvo às 17:02'), 'Salvo às ‹data›')
        self.assertEqual(self.mascarar('2026-11-21T17:02:11.123456Z'), '‹data›')
        self.assertEqual(self.mascarar('Análise R001 · 21/11 · Revisão'), 'Análise R001 · ‹data› · Revisão')
        self.assertEqual(self.mascarar('Atualizada em 20/11/2026'), 'Atualizada em ‹data›')   # ontem

    def test_nao_mascara_conteudo(self):
        for texto in ('Contrato 041/2025 de pavimentação', 'Medição nº 3', 'Valor R$ 1.234,56', 'Reunião 14:00 na obra',
                      'prazo 25/03/2030', 'Assinatura em 03/03/2025', 'Análise de 15/03'):
            self.assertEqual(self.mascarar(texto), texto)


class LinhaDeBaseTest(unittest.TestCase):
    """A linha de base versionada confere com o manifesto e cobre todas as telas esperadas."""

    def pastas(self):
        return [p for p in sorted(rv.REFERENCIAS.glob('*')) if p.is_dir()]

    def test_ha_linha_de_base(self):
        self.assertTrue(self.pastas(), 'testes/referencias_visuais/ está vazia: rode `regressao_visual.py gerar`.')

    def test_manifesto_confere_com_as_imagens(self):
        esperados = set(rv.nomes_esperados(rv.TODAS, rv.VIEWPORTS, rv.TEMAS))
        for pasta in self.pastas():
            with self.subTest(pasta=pasta.name):
                manifesto = json.loads((pasta / 'manifesto.json').read_text(encoding='utf-8'))
                self.assertEqual(set(manifesto['capturas']), esperados)
                self.assertEqual({p.stem for p in pasta.glob('*.png')}, esperados)
                for nome, dados in manifesto['capturas'].items():
                    arquivo = pasta / f'{nome}.png'
                    self.assertEqual(hashlib.sha256(arquivo.read_bytes()).hexdigest(), dados['sha256'],
                                     f'{nome}.png foi alterada sem atualizar o manifesto')
                self.assertEqual(manifesto['total_bytes'], sum(d['bytes'] for d in manifesto['capturas'].values()))

    def test_imagens_tem_a_largura_da_captura_e_conteudo(self):
        """Uma página em branco ou de erro, capturada igual para sempre, não pode virar referência."""
        for pasta in self.pastas():
            for arquivo in sorted(pasta.glob('*.png')):
                tela, largura, tema = arquivo.stem.split('__')
                with Image.open(arquivo) as imagem:
                    rgb = imagem.convert('RGB')
                    # Pode ser mais larga que a janela: a captura de página inteira inclui o estouro horizontal.
                    self.assertGreaterEqual(rgb.width, int(largura), arquivo.name)
                    self.assertGreaterEqual(rgb.height, rv.VIEWPORTS[int(largura)], arquivo.name)
                    cinza = rgb.convert('L').histogram()
                    self.assertLess(max(cinza) / sum(cinza), 0.985, f'{arquivo.name} parece em branco')

    def test_comparador_reprova_alteracao_pequena_numa_referencia_real(self):
        arquivo = next(iter(sorted((self.pastas() or [None])[0].glob('inicio__1440__claro.png'))), None) if self.pastas() else None
        if arquivo is None:
            self.skipTest('sem linha de base')
        with tempfile.TemporaryDirectory() as tmp:
            with Image.open(arquivo) as imagem:
                atual = imagem.convert('RGB')
            ImageDraw.Draw(atual).rectangle((300, 140, 340, 152), fill=(0, 0, 0))   # uma palavra de um título
            caminho = Path(tmp) / 'atual.png'
            atual.save(caminho)
            self.assertEqual(cmp.comparar_imagens(arquivo, caminho, 'inicio__1440__claro').estado, 'diferente')


class RodadaSinteticaTest(unittest.TestCase):
    def test_ids_fixos_por_rotulo(self):
        import regressao_visual_rodada as rodada
        self.assertEqual(rodada.rid('h1'), rodada.rid('h1'))
        self.assertNotEqual(rodada.rid('h1'), rodada.rid('h2'))
        self.assertRegex(rodada.rid('h1'), r'^[a-f0-9]{32}$')

    def test_rodada_so_grava_na_pasta_dada_e_sem_modelo(self):
        """A semeadura da rodada nunca importa provedor de modelo nem aponta para casos/ do projeto."""
        codigo = (Path(__file__).with_name('regressao_visual_rodada.py')).read_text(encoding='utf-8')
        for proibido in ('inferencia_api', 'provedor_', 'anthropic', 'openai', 'requests', 'urllib', 'ROOT'):
            self.assertNotIn(proibido, codigo)


class AtividadeDeRedeTest(unittest.TestCase):
    """Pedido lento em andamento não é silêncio: foi o que deixava capturar `quadros` ainda "carregando"."""

    def _pagina_falsa(self):
        class Pagina:
            def __init__(self):
                self.ouvintes = {}
                self.esperas = 0

            def on(self, evento, f):
                self.ouvintes[evento] = f

            def wait_for_timeout(self, ms):
                self.esperas += 1
        return Pagina()

    def test_pedido_em_andamento_conta_ate_terminar(self):
        pagina = self._pagina_falsa()
        rede = rv.AtividadeDeRede(pagina)
        pedido = object()
        pagina.ouvintes['request'](pedido)
        self.assertEqual(rede.pendentes(), 1)
        pagina.ouvintes['requestfinished'](pedido)
        self.assertEqual(rede.pendentes(), 0)

    def test_pedido_falho_tambem_termina(self):
        pagina = self._pagina_falsa()
        rede = rv.AtividadeDeRede(pagina)
        pedido = object()
        pagina.ouvintes['request'](pedido)
        pagina.ouvintes['requestfailed'](pedido)
        self.assertEqual(rede.pendentes(), 0)

    def test_conexao_de_longa_duracao_deixa_de_contar(self):
        pagina = self._pagina_falsa()
        rede = rv.AtividadeDeRede(pagina)
        rede.em_andamento[1] = time.monotonic() - 60
        self.assertEqual(rede.pendentes(), 0)

    def test_espera_enquanto_houver_pedido_novo_em_andamento(self):
        pagina = self._pagina_falsa()
        rede = rv.AtividadeDeRede(pagina)
        rede.ultima -= 10   # já passou o silêncio, mas há um pedido em curso
        rede.em_andamento[1] = time.monotonic()
        rede.esperar_quieta(pagina, quieto=0.1, limite=0.3)
        self.assertGreater(pagina.esperas, 0)


class SelecaoTest(unittest.TestCase):
    def test_focos_so_nas_larguras_alcancaveis(self):
        self.assertEqual(rv.larguras_da_tela('foco_mesa_barra', rv.VIEWPORTS), [1440])
        self.assertEqual(rv.larguras_da_tela('inicio', rv.VIEWPORTS), list(rv.VIEWPORTS))

    def test_nomes(self):
        self.assertEqual(rv.nome_captura('inicio', 375, 'claro'), 'inicio__375__claro')
        self.assertEqual(len(rv.nomes_esperados(rv.TODAS, rv.VIEWPORTS, rv.TEMAS)), 130)

    def test_larguras_e_temas_do_plano(self):
        self.assertEqual(sorted(rv.VIEWPORTS), [375, 768, 1024, 1440])
        self.assertEqual(sorted(rv.TEMAS), ['claro', 'escuro'])
        pedidas = {'inicio', 'documentos', 'cadastro', 'codex', 'achados', 'apuracao', 'diligencias', 'quadros', 'gerenciar'}
        self.assertTrue(pedidas <= set(rv.TELAS))


if __name__ == '__main__':
    unittest.main()
