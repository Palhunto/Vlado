import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dados_sinteticos  # noqa: E402


class DadosSinteticosTest(unittest.TestCase):
    def test_gera_pdf_com_texto_e_pdf_sem_camada_de_texto(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as pasta:
            lotes = dados_sinteticos.gerar(Path(pasta))
            self.assertEqual([p.name for p in lotes['lote1']],
                             ['contrato_041_2025_sintetico.pdf', 'medicao_03_digitalizada_sintetica.pdf'])
            texto = PdfReader(lotes['lote1'][0]).pages[0].extract_text()
            self.assertIn('FICTICIO', texto)
            self.assertIn('8.750.000,00', texto)
            self.assertEqual(PdfReader(lotes['lote1'][1]).pages[0].extract_text().strip(), '')
            self.assertIn('ADITIVO', PdfReader(lotes['lote2'][0]).pages[0].extract_text())


if __name__ == '__main__':
    unittest.main()
