"""Processo auxiliar dos testes da trava de cadastro (CONF-01). Não é módulo de teste.

    python apoio_trava_processo.py segurar RAIZ
        Pega a trava de cadastro, imprime uma linha JSON {"pid": ...} e a segura até receber
        uma linha na entrada padrão (ou até ser morto).

    python apoio_trava_processo.py servidor RAIZ [--pausa-cadastro MARCA] [--pausa-congelamento MARCA]
                                                 [--segundos N] [--prazo N] [--extracao local|processos]
        Sobe a Mesa (modo local) com provedor simulado, que nunca chama a API, e imprime uma
        linha JSON {"porta", "token", "pid"}. As pausas gravam MARCA quando a operação está dentro
        da trava, com a pasta de preparo criada, e esperam N segundos: a do cadastro antes de
        publicar o lote; a do congelamento antes de montar o índice da rodada. Roda por
        ``interface_pesquisa.servir``, o mesmo caminho de ``main``: limpeza na partida, sinais e
        encerramento ordenado com prazo N (``--prazo``).
"""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
sys.path.insert(0, str(TESTES))


def pausar(modulo, nome, marca, segundos):
    original = getattr(modulo, nome)

    def pausa(*args, **kwargs):
        # atomic, like agente_api_sintetico.marcar: seen only whole; one .tmp per thread (calls may overlap)
        temporario = Path(f'{marca}.{os.getpid()}.{threading.get_ident()}.tmp')
        temporario.write_text('dentro', encoding='utf-8')
        os.replace(temporario, marca)
        time.sleep(segundos)
        return original(*args, **kwargs)
    setattr(modulo, nome, pausa)


def segurar(raiz):
    import cadastrar_documentos
    with cadastrar_documentos._trava(raiz, espera=10, operacao='teste_segurar'):
        print(json.dumps({'pid': __import__('os').getpid()}), flush=True)
        sys.stdin.readline()


def servidor(raiz, args):
    import cadastrar_documentos
    import indice_sqlite
    import interface_pesquisa
    from test_codex_integracao import FakeServer
    if args.pausa_cadastro:
        pausar(cadastrar_documentos, '_resumo_pdfs', args.pausa_cadastro, args.segundos)
    if args.pausa_congelamento:
        pausar(indice_sqlite, 'construir_snapshot', args.pausa_congelamento, args.segundos)
    # The real environment check probes the OCR tools (about 8 s on Windows); these tests send
    # only text files, so a fixed synthetic answer keeps each start fast.
    interface_pesquisa.diagnostico = lambda: {'pronto': True, 'extracao_pdf': {'disponivel': False},
                                              'ocr': {'disponivel': False}}
    server = interface_pesquisa.Servidor(('127.0.0.1', 0), root=raiz, extracao=args.extracao)
    server.conversas.factory = FakeServer
    with server:
        print(json.dumps({'porta': server.server_port, 'token': server.token,
                          'pid': __import__('os').getpid()}), flush=True)
        interface_pesquisa.servir(server, prazo=args.prazo)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('modo', choices=('segurar', 'servidor'))
    parser.add_argument('raiz', type=Path)
    parser.add_argument('--pausa-cadastro')
    parser.add_argument('--pausa-congelamento')
    parser.add_argument('--segundos', type=float, default=3600)
    parser.add_argument('--prazo', type=float, default=8.0)
    parser.add_argument('--extracao', choices=('local', 'processos'), default='local',
                        help='Fila de extração em threads da Mesa (padrão dos testes) ou em processos separados.')
    args = parser.parse_args()
    if args.modo == 'segurar':
        segurar(args.raiz)
    else:
        servidor(args.raiz, args)


if __name__ == '__main__':
    main()
