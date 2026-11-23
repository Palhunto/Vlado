"""Relógio fixo para os testes do registro de auditoria. As linhas agregadas (`registrar_limite_ip`, um evento por IP e por minuto)
dependem do minuto em que os pedidos caem: com o relógio de verdade, um teste que conta linhas cruza a virada do minuto de vez em
quando (o CI cruzou) e sai com duas linhas onde esperava uma. `fixar` congela o `datetime` que registro_acesso usa.

O DIA, porém, é o de verdade: o registro grava um arquivo por dia (`auditoria-AAAA-MM-DD.jsonl`), e os testes montam o cenário (setUp) com
o relógio real. Uma data fixa que não fosse a de hoje mandaria as linhas do teste para outro arquivo e quebraria quem as separa por
posição. Fixa-se só a hora, dentro do dia de hoje (UTC); quem precisar de outro dia passa o `momento` e separa as linhas pelo conteúdo."""
from datetime import datetime, timezone
from unittest.mock import patch

import registro_acesso as reg


def hoje_as(hora: int, minuto: int = 0, segundo: int = 0) -> datetime:
    """Hoje (UTC, o dia em que o teste começou) na hora dada."""
    return datetime.now(timezone.utc).replace(hour=hora, minute=minuto, second=segundo, microsecond=0)


def relogio(momento_agora):
    """Subclasse de `datetime` cujo `now()` devolve `momento_agora()`: o que o registro enxerga como "agora"."""
    class Relogio(datetime):
        @classmethod
        def now(cls, tz=None):
            momento = momento_agora()
            return momento.astimezone(tz) if tz else momento
    return Relogio


def fixar(caso, momento: datetime | None = None) -> datetime:
    """Congela o relógio do registro em `momento` (padrão: hoje às 12:30:20 UTC) até o fim do teste. Devolve o momento."""
    momento = momento or hoje_as(12, 30, 20)
    alvo = patch.object(reg, 'datetime', relogio(lambda: momento))
    alvo.start()
    caso.addCleanup(alvo.stop)
    return momento
