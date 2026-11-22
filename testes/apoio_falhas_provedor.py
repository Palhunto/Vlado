"""Mesa com o ServidorAPI de verdade e o agente sintético, para ser morta no meio de uma etapa (CONF-04).

Uso: apoio_falhas_provedor.py <pasta> <marca> <etapa>. Faz uma pergunta no caso 'alpha', escreve
{"conversa": id} na saída e, ao chegar ao primeiro passo de <etapa>, grava <marca> e espera ali até
o teste matar o processo (TerminateProcess no Windows, SIGKILL no Linux). Dados sintéticos; sem rede.
"""
import json
from pathlib import Path
import sys
import time

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
sys.path.insert(0, str(TESTES))
from agente_api_sintetico import AgenteSintetico  # noqa: E402
from codex_apuracao import Conversas  # noqa: E402
from inferencia_api import ServidorAPI  # noqa: E402


def main():
    raiz, marca, etapa = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    agente = AgenteSintetico('anthropic', parar_em=(etapa, 0), marca=marca)
    manager = Conversas(raiz, lambda root, callback: ServidorAPI(root, callback,
                                                                 criar_provedor=lambda inferencia, chave: agente))
    conversa = manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'})['conversa']
    print(json.dumps({'conversa': conversa}), flush=True)
    time.sleep(600)


if __name__ == '__main__':
    main()
