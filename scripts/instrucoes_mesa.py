"""Qual instrução a Mesa manda ao modelo numa rodada: a do ``prompts/MESA.md`` (modo ``mesa``) ou a antiga (``legado``).

A escolha é feita pela RODADA, nunca pelo projeto: vale o ``manifesto_prompts.json`` congelado em ``entradas/prompts``
quando a rodada foi criada.

- Com a chave ``mesa`` no manifesto e o hash de ``entradas/prompts/MESA.md`` igual ao declarado, o modo é ``mesa``: a
  instrução de sistema é o bloco ``mesa:sistema`` e cada turno de etapa leva ``mesa:controle`` e ``mesa:formato:<etapa>``.
- Sem a chave (as rodadas de antes da 1.5.0), o modo é ``legado``: AGENTS.md, FLUXO_COMPLETO.md, README.md e os
  formatos escritos em ``fluxo_codex`` (os da 1.4.1, sem edição).
- Com a chave e o arquivo ausente, divergente ou sem algum bloco, a rodada é recusada: as entradas foram adulteradas,
  e nada volta em silêncio ao legado.

A presença de um MESA.md na pasta da rodada não decide nada: ``nova_rodada`` copia todo ``prompts/*.md``.
"""
from __future__ import annotations

from pathlib import Path
import re

from comum import ler_json, sha256

ETAPAS = ('inventario', 'plano', 'busca', 'geracao_inicial', 'revisao', 'sintese')
BLOCO = re.compile(r'<!-- mesa:([a-z_:]+) -->\n(.*?)\n<!-- /mesa -->', re.S)
MARCAS_CONTROLE = ('pergunta', 'etapa', 'etapa_ferramenta', 'tentativa')
_MARCA = re.compile(r'\{(' + '|'.join(MARCAS_CONTROLE) + r')\}')
LEGADO = {'modo': 'legado', 'versao': None, 'sha256': None}


def blocos_mesa(texto: str) -> dict:
    """{nome: conteúdo} dos blocos ``<!-- mesa:NOME -->`` ... ``<!-- /mesa -->`` do MESA.md; recusa o incompleto."""
    blocos = {}
    for nome, conteudo in BLOCO.findall(texto.replace('\r\n', '\n')):
        if nome in blocos:
            raise ValueError(f'Bloco repetido no MESA.md: {nome}')
        blocos[nome] = conteudo
    faltam = [n for n in ('sistema', 'controle', *(f'formato:{e}' for e in ETAPAS)) if n not in blocos]
    if faltam:
        raise ValueError('Blocos ausentes no MESA.md: ' + ', '.join(faltam))
    sem_marca = [f'{{{m}}}' for m in MARCAS_CONTROLE if f'{{{m}}}' not in blocos['controle']]
    if sem_marca:
        raise ValueError('Bloco mesa:controle sem as marcas: ' + ', '.join(sem_marca))
    return blocos


def modo_da_rodada(run: Path) -> dict:
    """{'modo', 'versao', 'sha256'} e, no modo mesa, 'blocos': a instrução que esta rodada congelou."""
    entradas = Path(run) / 'entradas'
    caminho = entradas / 'prompts' / 'manifesto_prompts.json'
    manifesto = ler_json(caminho) if caminho.is_file() else {}
    entrada = manifesto.get('mesa')
    if entrada is None:
        return {**LEGADO, 'versao_prompts': manifesto.get('versao')}
    if (not isinstance(entrada, dict) or entrada.get('arquivo') != 'prompts/MESA.md'
            or not isinstance(entrada.get('versao'), str) or not isinstance(entrada.get('sha256'), str)):
        raise ValueError('Manifesto de prompts da rodada com a entrada da Mesa inválida; rodada recusada.')
    arquivo = entradas / 'prompts' / 'MESA.md'
    if not arquivo.is_file() or sha256(arquivo) != entrada['sha256']:
        raise ValueError('A instrução da Mesa congelada na rodada está ausente ou não confere com o hash do '
                         'manifesto; rodada recusada. Envie a pergunta de novo numa conversa nova.')
    blocos = blocos_mesa(arquivo.read_bytes().decode('utf-8-sig'))
    return {'modo': 'mesa', 'versao': entrada['versao'], 'sha256': entrada['sha256'],
            'versao_prompts': manifesto.get('versao'), 'blocos': blocos}


def publico(instrucoes: dict) -> dict:
    """O que vai para a conversa e o evento ``escopo``: modo, versão e hash, sem o texto."""
    return {k: instrucoes.get(k) for k in ('modo', 'versao', 'sha256', 'versao_prompts')}


def controle(instrucoes: dict, pergunta: str, etapa: str, tentativa: int) -> str:
    """O bloco ``mesa:controle`` preenchido numa passada só (a pergunta não reabre as marcas)."""
    valores = {'pergunta': pergunta, 'etapa': etapa, 'tentativa': str(tentativa),
               # The tool enum has no 'comparacao': the comparison travels as etapa=sintese (codex_apuracao).
               'etapa_ferramenta': 'sintese' if etapa == 'comparacao' else etapa}
    return _MARCA.sub(lambda m: valores[m.group(1)], instrucoes['blocos']['controle'])
