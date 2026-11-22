"""Relógio fixo para os testes do registro de auditoria. As linhas agregadas (`registrar_limite_ip`, um evento por IP e por minuto)
dependem do minuto em que os pedidos caem: com o relógio de verdade, um teste que conta linhas cruza a virada do minuto de vez em
quando (o CI cruzou) e sai com duas linhas onde esperava uma. `fixar` congela o `datetime` que registro_acesso usa."""
from datetime import datetime, timezone
from unittest.mock import patch

import registro_acesso as reg

MOMENTO = datetime(2026, 11, 22, 12, 30, 20, tzinfo=timezone.utc)


def fixar(caso, momento: datetime = MOMENTO) -> None:
    class Relogio(datetime):
        @classmethod
        def now(cls, tz=None):
            return momento.astimezone(tz) if tz else momento

    alvo = patch.object(reg, 'datetime', Relogio)
    alvo.start()
    caso.addCleanup(alvo.stop)
