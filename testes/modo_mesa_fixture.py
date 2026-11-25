"""Liga o modo mesa numa raiz de teste: copia o prompts/MESA.md do projeto e regrava o manifesto de prompts.

As fixtures que montam prompts sintéticos (test_codex_integracao.CodexIntegrationTest.montar) não têm MESA.md,
então as rodadas delas congelam um manifesto sem a chave `mesa` e ficam no modo legado, como uma instalação de
antes da 1.5.0. Depois de `ligar_mesa(raiz)`, as rodadas novas congelam a chave e vão para o modo mesa.
"""
from pathlib import Path
import shutil
import sys

PROJETO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJETO / 'scripts'))
from comum import conferir_prompts, escrever_json, manifesto_prompts  # noqa: E402


def ligar_mesa(raiz: Path) -> None:
    shutil.copyfile(PROJETO / 'prompts' / 'MESA.md', raiz / 'prompts' / 'MESA.md')
    escrever_json(raiz / 'prompts' / 'manifesto_prompts.json', manifesto_prompts(raiz))
    conferir_prompts(raiz)
