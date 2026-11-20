"""Mesa em tela estreita: aceitação no navegador com armazenamento, conversa e PDF sintéticos.

Sem inferência: a conversa é lida de eventos gravados e o acompanhamento ao vivo é simulado no
navegador (interceptação de `codex-eventos`). Uso:

    python testes/qa_mobile.py --modulos-node .ferramentas/node/node_modules --saida SAIDA \
        --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" [--capturas docs/capturas/mesa]
"""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fixture_achados import Ambiente  # noqa: E402
from test_codex_integracao import FakeServer  # noqa: E402
from interface_pesquisa import Servidor  # noqa: E402
from comum import escrever_json  # noqa: E402
from indice_sqlite import pesquisar  # noqa: E402

# ASCII only: the standard Helvetica encoding of a bare Type1 font has no Latin-1 accents.
LINHAS = [
    ['Prefeitura Municipal de Exemplo (documento sintetico)', 'Relatorio de execucao do contrato 001/2026',
     'Pagina de abertura. Nenhum dado real.'],
    ['Quadro 2 - Pagamentos do transporte escolar', 'Empresa Sintetica Ltda. recebeu R$ 12.400,00 em marco.',
     'O valor refere-se a 31 dias de rota escolar.', 'Fonte: planilha de liquidacao sintetica.'],
    ['Anexo - Observacoes', 'Este anexo existe apenas para testar a navegacao.'],
]


def pdf_paginas(path, paginas):
    """PDF real com texto em fonte padrão, várias linhas por página (A4)."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    font_ref = writer._add_object(font)
    for linhas in paginas:
        page = writer.add_blank_page(width=595, height=842)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref})})
        partes = []
        for numero, texto in enumerate(linhas):
            literal = texto.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            partes.append(f'BT /F1 {16 if numero == 0 else 12} Tf 56 {760 - numero * 28} Td ({literal}) Tj ET')
        stream = DecodedStreamObject()
        stream.set_data('\n'.join(partes).encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modulos-node', required=True)
    parser.add_argument('--saida', required=True)
    parser.add_argument('--chrome', default='')
    parser.add_argument('--capturas', default='')
    args = parser.parse_args()
    output = Path(args.saida).resolve()
    output.mkdir(parents=True, exist_ok=True)
    fx = Ambiente()
    server = None
    try:
        fx.completo(quantidade=12)
        hit = pesquisar(fx.root, 'alpha', 'R001', 'valor')['resultados'][0]
        hit.update(rodada='R001', geracao='v1')
        chat = 'b' * 32
        escrever_json(fx.root / f'conversas/{chat}/conversa.json', {
            'id': chat, 'caso': 'alpha', 'titulo': 'Conversa sintética em tela estreita',
            'estado': 'concluido', 'rodadas': ['R001'], 'criada_em_utc': '2026-01-01T00:00:00Z'})
        events = [('pergunta', {'texto': 'Quanto a empresa sintética recebeu em março?'}),
                  ('escopo', {'caso': 'alpha', 'rodada': 'R001', 'corpus_id': 'alpha_v1', 'modelo': 'fixture sem inferência'}),
                  ('fonte', hit),
                  ('resposta', {'item': 'final', 'texto': '## Leitura sintética\n\nA fonte declara valor 12. [fonte:'
                                + hit['referencia'] + ']\n\nConteúdo de teste, sem execução de modelo.',
                                'fase': 'final_answer', 'publicada': True, 'rodada': 'R001'})]
        (fx.root / f'conversas/{chat}/eventos.jsonl').write_text(''.join(json.dumps({
            'seq': i, 'tipo': kind, 'dados': data, 'em_utc': '2026-01-01T00:00:00Z'}, ensure_ascii=False) + '\n'
            for i, (kind, data) in enumerate(events, 1)), encoding='utf-8')
        pdf = pdf_paginas(fx.root / 'citado.pdf', LINHAS)
        (output / 'citado.pdf.b64').write_text(base64.b64encode(pdf.read_bytes()).decode('ascii'), encoding='ascii')
        # The default listen backlog (5) refuses part of Chrome's burst of ~25 parallel requests on
        # Windows under load (ERR_CONNECTION_REFUSED, page left half-initialised). Reported to the
        # main session; the harness widens it so the QA measures the interface, not the backlog.
        Servidor.request_queue_size = 64
        server = Servidor(('127.0.0.1', 0), fx.root)
        server.conversas.factory = FakeServer
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {**os.environ, 'NODE_PATH': str(Path(args.modulos_node).resolve())}
        capturas = str(Path(args.capturas).resolve()) if args.capturas else ''
        return subprocess.run(['node', str(Path(__file__).with_suffix('.cjs')), server.origin, str(output),
                               args.chrome, chat, capturas], env=env, timeout=900).returncode
    finally:
        if server:
            server.shutdown()
            server.server_close()
        fx.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
