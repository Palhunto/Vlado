"""Apagamento definitivo num processo à parte, para ser morto no meio da remoção (quarentena).

Uso: apoio_apagamento_queda.py <pasta> <item> <confirmacao> <marca>. Remove os arquivos da quarentena
devagar; depois de alguns, grava <marca> e segue devagar até o teste matar o processo
(TerminateProcess no Windows, SIGKILL no Linux). Dados sintéticos; sem rede.
"""
import os
from pathlib import Path
import sys
import time

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import apagamento  # noqa: E402


def main():
    raiz, item, confirmacao, marca = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
    real, removidos = os.unlink, [0]

    def devagar(caminho, *args, **kwargs):
        partes = Path(caminho).parts
        if apagamento.QUARENTENA in partes and 'lixeira' not in partes:
            removidos[0] += 1
            if removidos[0] == 5:
                # atomic, like agente_api_sintetico.marcar: the test sees the mark only whole
                temporario = marca.with_name(marca.name + '.tmp')
                temporario.write_text('removendo', encoding='utf-8')
                os.replace(temporario, marca)
            time.sleep(0.2)
        return real(caminho, *args, **kwargs)
    os.unlink = devagar
    apagamento.apagar(raiz, item, confirmacao, quem='admin sintético')
    time.sleep(600)


if __name__ == '__main__':
    main()
