"""Testes da infraestrutura de regressão visual (sem navegador, só Pillow).

O que ficaria verde em silêncio é o que mais importa aqui: o comparador precisa reprovar mudança
pequena de texto, de cor e de posição, tamanho diferente, captura ausente e captura sem referência;
e a linha de base versionada precisa bater com o manifesto (nenhuma imagem trocada ou apagada à mão).
A captura em si (Playwright) roda à mão: `python testes/regressao_visual.py comparar`.
"""
import hashlib
import json
from pathlib import Path
import re
import tempfile
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
        for padrao in rv.MASCARAS:
            texto = re.sub(padrao, '‹data›', texto)
        return texto

    def test_datas_e_horas(self):
        self.assertEqual(self.mascarar('Atualizada em 21/11/2026'), 'Atualizada em ‹data›')
        self.assertEqual(self.mascarar('21/11/2026, 17:02:11 · Admin'), '‹data› · Admin')
        self.assertEqual(self.mascarar('Salvo às 17:02'), 'Salvo às ‹data›')
        self.assertEqual(self.mascarar('2026-11-21T17:02:11.123456Z'), '‹data›')

    def test_nao_mascara_conteudo(self):
        for texto in ('Contrato 041/2025 de pavimentação', 'Medição nº 3', 'Valor R$ 1.234,56', 'Reunião 14:00 na obra'):
            self.assertEqual(self.mascarar(texto), texto)


class LinhaDeBaseTest(unittest.TestCase):
    """A linha de base versionada confere com o manifesto e cobre todas as telas esperadas."""

    def pastas(self):
        return [p for p in sorted(rv.REFERENCIAS.glob('*')) if p.is_dir()]

    def test_ha_linha_de_base(self):
        self.assertTrue(self.pastas(), 'testes/referencias_visuais/ está vazia: rode `regressao_visual.py gerar`.')

    def test_manifesto_confere_com_as_imagens(self):
        esperados = set(rv.nomes_esperados(rv.TELAS + (rv.TELA_ENTRAR,), rv.VIEWPORTS, rv.TEMAS))
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


class SelecaoTest(unittest.TestCase):
    def test_nomes(self):
        self.assertEqual(rv.nome_captura('inicio', 375, 'claro'), 'inicio__375__claro')
        self.assertEqual(len(rv.nomes_esperados(rv.TELAS + (rv.TELA_ENTRAR,), rv.VIEWPORTS, rv.TEMAS)), 96)

    def test_larguras_e_temas_do_plano(self):
        self.assertEqual(sorted(rv.VIEWPORTS), [375, 768, 1024, 1440])
        self.assertEqual(sorted(rv.TEMAS), ['claro', 'escuro'])
        pedidas = {'inicio', 'documentos', 'cadastro', 'codex', 'achados', 'apuracao', 'diligencias', 'quadros', 'gerenciar'}
        self.assertTrue(pedidas <= set(rv.TELAS))


if __name__ == '__main__':
    unittest.main()
