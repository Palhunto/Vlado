"""Pasta de teste copiada de um modelo construído uma vez por processo.

Serve para fixtures caras cujo resultado só depende de dados sintéticos fixos: o primeiro pedido de
cada chave constrói o modelo pelo caminho normal; os seguintes copiam a pasta para um diretório
temporário novo. Cada teste continua com estado próprio, e alterações não chegam ao modelo nem a
outros testes. Só serve quando a fixture grava caminhos relativos à raiz (nunca a raiz absoluta).
"""
import copy
from pathlib import Path
import shutil
import tempfile

_MODELOS = {}


def copiar(chave, construir):
    """Devolve `(temp, raiz, valor)`.

    `construir(raiz)` monta o modelo numa pasta vazia e devolve um valor qualquer; `valor` é uma
    cópia profunda dele. `temp` é o `TemporaryDirectory` da cópia, que o chamador limpa.
    """
    if chave not in _MODELOS:
        modelo = tempfile.TemporaryDirectory()
        try:
            valor = construir(Path(modelo.name))
        except BaseException:
            modelo.cleanup()
            raise
        _MODELOS[chave] = (modelo, valor)
    modelo, valor = _MODELOS[chave]
    temp = tempfile.TemporaryDirectory()
    try:
        shutil.copytree(modelo.name, temp.name, dirs_exist_ok=True)
    except BaseException:
        temp.cleanup()
        raise
    return temp, Path(temp.name), copy.deepcopy(valor)
