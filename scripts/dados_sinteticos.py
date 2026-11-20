"""Synthetic newsroom corpus for homologation and the classroom demo.

Every file is fictitious and says so on each page. Two batches:
  lote 1: a PDF with native text (contract) and a scanned PDF (image only, needs local OCR);
  lote 2: an amendment PDF with native text, for the "second batch keeps the previous round" check.

Nothing here calls a model or the network.

  python scripts/dados_sinteticos.py --destino PASTA
"""
from __future__ import annotations

import argparse
from pathlib import Path

AVISO = 'DOCUMENTO SINTETICO - FICTICIO - CRIADO PARA TESTES DO VLADO'

CONTRATO = [
    'PREFEITURA MUNICIPAL DE VILA SERENA (ficticia)',
    'CONTRATO No 041/2025 - PAVIMENTACAO DA ESTRADA DO CAMPO VERDE',
    'Contratada: Construtora Horizonte Azul Ltda. (ficticia), CNPJ 00.000.000/0001-00.',
    'Objeto: pavimentacao asfaltica de 12,4 km da Estrada do Campo Verde.',
    'Valor global: R$ 8.750.000,00 (oito milhoes, setecentos e cinquenta mil reais).',
    'Prazo de execucao: 240 dias corridos a partir da ordem de servico.',
    'Data de assinatura: 3 de marco de 2025.',
    'Fiscal do contrato: engenheira Lucia Prates (ficticia), matricula 7781.',
    'Clausula 9: pagamentos mediante medicao aprovada pela fiscalizacao.',
]

MEDICAO = [
    'PREFEITURA MUNICIPAL DE VILA SERENA (ficticia) - SECRETARIA DE OBRAS',
    'BOLETIM DE MEDICAO No 3 - CONTRATO 041/2025',
    'Periodo: 1 a 31 de julho de 2025.',
    'Extensao pavimentada acumulada: 4,1 km.',
    'Valor medido no periodo: R$ 1.230.000,00.',
    'Valor acumulado pago: R$ 3.900.000,00.',
    'Assinatura do fiscal: Lucia Prates (ficticia).',
]

ADITIVO = [
    'PREFEITURA MUNICIPAL DE VILA SERENA (ficticia)',
    'PRIMEIRO TERMO ADITIVO AO CONTRATO No 041/2025',
    'Acrescimo de valor: R$ 2.187.500,00 (25% do valor original).',
    'Novo valor global: R$ 10.937.500,00.',
    'Prorrogacao de prazo: 120 dias.',
    'Justificativa declarada: chuvas acima da media e revisao do projeto de drenagem.',
    'Data de assinatura: 18 de setembro de 2025.',
]


def _pdf_texto(destino: Path, linhas: list[str]) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pagina = canvas.Canvas(str(destino), pagesize=A4, invariant=1)
    pagina.setTitle(destino.stem)
    _, altura = A4
    pagina.setFont('Helvetica-Bold', 9)
    pagina.drawString(50, altura - 40, AVISO)
    pagina.setFont('Helvetica', 12)
    y = altura - 90
    for linha in linhas:
        pagina.drawString(50, y, linha)
        y -= 24
    pagina.setFont('Helvetica-Bold', 9)
    pagina.drawString(50, 40, AVISO)
    pagina.showPage()
    pagina.save()
    return destino


def _pdf_digitalizado(destino: Path, linhas: list[str]) -> Path:
    """Render a text page to an image and keep only the image: a PDF without a text layer."""
    import fitz

    temporario = destino.with_suffix('.tmp.pdf')
    _pdf_texto(temporario, linhas)
    try:
        with fitz.open(temporario) as origem, fitz.open() as saida:
            imagem = origem[0].get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), colorspace=fitz.csGRAY)
            pagina = saida.new_page(width=origem[0].rect.width, height=origem[0].rect.height)
            pagina.insert_image(pagina.rect, stream=imagem.tobytes('png'))
            saida.save(destino, garbage=4, deflate=True)
    finally:
        temporario.unlink(missing_ok=True)
    return destino


def gerar(destino: Path) -> dict[str, list[Path]]:
    destino = Path(destino)
    lote1, lote2 = destino / 'lote1', destino / 'lote2'
    lote1.mkdir(parents=True, exist_ok=True)
    lote2.mkdir(parents=True, exist_ok=True)
    return {
        'lote1': [_pdf_texto(lote1 / 'contrato_041_2025_sintetico.pdf', CONTRATO),
                  _pdf_digitalizado(lote1 / 'medicao_03_digitalizada_sintetica.pdf', MEDICAO)],
        'lote2': [_pdf_texto(lote2 / 'aditivo_01_sintetico.pdf', ADITIVO)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--destino', required=True)
    args = parser.parse_args()
    for lote, arquivos in gerar(Path(args.destino)).items():
        for arquivo in arquivos:
            print(f'{lote}: {arquivo}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
